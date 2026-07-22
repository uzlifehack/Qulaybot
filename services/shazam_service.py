"""
Shazam recognition wrapper.

Works across shazamio versions: 0.4.x uses `recognize_song()`, 0.5+ uses
`recognize()`. We resolve the method name once at first use and cache it.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from shazamio import Shazam

from services.downloader import extract_audio_from_file, cleanup

logger = logging.getLogger(__name__)

_shazam: Optional[Shazam] = None
_method_name: Optional[str] = None


def _get_client():
    global _shazam, _method_name
    if _shazam is None:
        _shazam = Shazam()
        for name in ("recognize", "recognize_song"):
            if hasattr(_shazam, name):
                _method_name = name
                break
        if _method_name is None:
            raise AttributeError(
                "shazamio: neither .recognize nor .recognize_song exists"
            )
        logger.info(f"shazamio ready — using method: {_method_name}")
    return _shazam, _method_name


async def _recognize(path_or_bytes) -> Optional[dict]:
    client, name = _get_client()
    return await asyncio.wait_for(
        getattr(client, name)(path_or_bytes),
        timeout=25,
    )


def _extract(result: dict) -> Optional[dict]:
    if not result:
        return None
    track = (result or {}).get("track") or {}
    title = track.get("title") or ""
    artist = track.get("subtitle") or ""
    if not title:
        return None
    images = track.get("images") or {}
    cover = images.get("coverarthq") or images.get("coverart")
    return {
        "title": title,
        "artist": artist,
        "cover": cover,
        "query": f"{artist} {title}".strip(),
    }


async def recognize_file(file_path: str) -> Optional[dict]:
    audio_path = None
    try:
        p = Path(file_path)
        if not p.exists():
            logger.warning(f"shazam: file missing: {file_path}")
            return None
        ext = p.suffix.lower()
        if ext in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
            audio_path = await extract_audio_from_file(file_path)
            if not audio_path or not os.path.exists(audio_path):
                logger.warning("shazam: audio extraction produced no file")
                return None
            recognize_path = audio_path
        else:
            recognize_path = file_path
        try:
            size = os.path.getsize(recognize_path)
        except OSError:
            size = 0
        if size < 1024:
            logger.warning(f"shazam: audio too small ({size} bytes)")
            return None
        return _extract(await _recognize(recognize_path))
    except asyncio.TimeoutError:
        logger.error("shazam: timeout after 25s")
    except Exception as e:
        logger.error(f"shazam: {type(e).__name__}: {e}")
    finally:
        if audio_path:
            cleanup(audio_path)
    return None


async def recognize_url(audio_url: str) -> Optional[dict]:
    try:
        return _extract(await _recognize(audio_url))
    except asyncio.TimeoutError:
        logger.error("shazam: timeout after 25s")
    except Exception as e:
        logger.error(f"shazam: {type(e).__name__}: {e}")
    return None
