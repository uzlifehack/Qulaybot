import asyncio
import os
from typing import Optional
from shazamio import Shazam
from services.downloader import extract_audio_from_file, cleanup

_shazam = None

def get_shazam() -> Shazam:
    global _shazam
    if _shazam is None:
        _shazam = Shazam()
    return _shazam

async def recognize_file(file_path: str) -> Optional[dict]:
    audio_path = None
    try:
        # Video yoki voice bo'lsa audio ajratib olish
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".mp4", ".avi", ".mov", ".mkv", ".webm"]:
            audio_path = await extract_audio_from_file(file_path)
            recognize_path = audio_path
        else:
            recognize_path = file_path

        shazam = get_shazam()
        result = await asyncio.wait_for(
            shazam.recognize(recognize_path),
            timeout=30
        )

        if not result or "track" not in result:
            return None

        track = result["track"]
        title = track.get("title", "")
        artist = track.get("subtitle", "")

        if not title:
            return None

        # Cover art
        cover = None
        images = track.get("images", {})
        cover = images.get("coverarthq") or images.get("coverart")

        # Deezer search uchun query
        search_query = f"{artist} {title}"

        return {
            "title": title,
            "artist": artist,
            "cover": cover,
            "query": search_query,
        }

    except asyncio.TimeoutError:
        return None
    except Exception:
        return None
    finally:
        if audio_path:
            cleanup(audio_path)

async def recognize_url(audio_url: str) -> Optional[dict]:
    try:
        shazam = get_shazam()
        result = await asyncio.wait_for(
            shazam.recognize(audio_url),
            timeout=30
        )

        if not result or "track" not in result:
            return None

        track = result["track"]
        title = track.get("title", "")
        artist = track.get("subtitle", "")

        if not title:
            return None

        images = track.get("images", {})
        cover = images.get("coverarthq") or images.get("coverart")

        return {
            "title": title,
            "artist": artist,
            "cover": cover,
            "query": f"{artist} {title}",
        }

    except asyncio.TimeoutError:
        return None
    except Exception:
        return None
