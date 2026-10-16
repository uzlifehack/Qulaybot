import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from shazamio import Shazam

from services.downloader import extract_audio_from_file, cleanup

logger = logging.getLogger(__name__)

_shazam: Optional[Shazam] = None


def _get_client() -> Shazam:
    global _shazam
    if _shazam is None:
        _shazam = Shazam()
    return _shazam


async def _recognize(path_or_bytes) -> Optional[dict]:
    return await asyncio.wait_for(_get_client().recognize(path_or_bytes), timeout=25)


def _extract(result: dict) -> Optional[dict]:
    track = (result or {}).get("track") or {}
    title = track.get("title") or ""
    artist = track.get("subtitle") or ""
    if not title:
        return None
    images = track.get("images") or {}
    return {
        "title": title,
        "artist": artist,
        "cover": images.get("coverarthq") or images.get("coverart"),
        "query": f"{artist} {title}".strip(),
    }


async def recognize_file(file_path: str) -> Optional[dict]:
    audio_path = None
    try:
        p = Path(file_path)
        if not p.exists():
            logger.warning(f"shazam: file missing: {file_path}")
            return None
        if p.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
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
