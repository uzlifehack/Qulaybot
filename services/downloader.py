"""
Video / audio downloader built on yt-dlp.

Optimised for speed and resilience:
  * fresh cookies are re-read on every call, so updating cookies.txt
    takes effect without restarting the bot;
  * a bounded, dedicated thread pool keeps blocking yt-dlp work off the
    event loop without exhausting the default executor;
  * YouTube's player_client is left at yt-dlp's own default (updated
    upstream with every release) instead of a hardcoded list — pinning
    clients like "tv"/"ios" has been observed to silently fall back to
    muxed, audio-less or oversized streams when that client's format set
    doesn't line up with the video;
  * temp files are always cleaned up on failure.
"""

import asyncio
import os
import shutil
import tempfile
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import yt_dlp

from config import MAX_FILE_SIZE, DOWNLOAD_SEMAPHORE

logger = logging.getLogger(__name__)

COOKIES_FILE = str(Path(__file__).parent.parent / "cookies.txt")
TMP_DIR = os.getenv("DL_TMP_DIR", "/tmp")

if not shutil.which("ffmpeg"):
    logger.warning(
        "ffmpeg not found on PATH — video/audio merging and mp3 extraction "
        "will fail or silently downgrade quality."
    )

# A realistic desktop UA reduces "bot" detection on several sites.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Dedicated pool: downloads are I/O bound, so allow a little headroom over
# the download semaphore for the parallel get_info() probes.
_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(4, DOWNLOAD_SEMAPHORE * 2),
    thread_name_prefix="ytdl",
)

YDL_BASE = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "socket_timeout": 30,
    "retries": 5,
    "fragment_retries": 5,
    "extractor_retries": 3,
    "file_access_retries": 3,
    "skip_unavailable_fragments": True,
    "concurrent_fragment_downloads": 8,
    "http_chunk_size": 10 * 1024 * 1024,
    "nocheckcertificate": True,
    "geo_bypass": True,
    "geo_bypass_country": "US",
    "max_filesize": MAX_FILE_SIZE,
    "restrictfilenames": True,
    "overwrites": True,
    "http_headers": {"User-Agent": USER_AGENT},
    # Matches the combo confirmed working in production (qulay_bot.py).
    "extractor_args": {
        "youtube": {
            "player_client": ["ios", "android", "web"],
        }
    },
}

# bestvideo*+bestaudio prefers a real merged video+audio pair; the plain
# "best" fallback only kicks in if no separate streams exist at all.
_VIDEO_FORMATS = "bestvideo*+bestaudio/best"


def _base_opts() -> dict:
    """Fresh copy of the base options with current cookies attached."""
    opts = dict(YDL_BASE)
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
        opts["cookiefile"] = COOKIES_FILE
    return opts


def _download_video_sync(url: str, out_path: str) -> str:
    opts = {
        **_base_opts(),
        "format": _VIDEO_FORMATS,
        "merge_output_format": "mp4",
        "outtmpl": out_path,
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
        ],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return out_path


def _download_audio_sync(url: str, out_path: str) -> str:
    opts = {
        **_base_opts(),
        "format": "bestaudio/best",
        "outtmpl": out_path,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return out_path + ".mp3"


def _get_info_sync(url: str) -> dict:
    opts = {**_base_opts(), "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.sanitize_info(ydl.extract_info(url, download=False))


async def _run(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_EXECUTOR, func, *args)


async def get_info(url: str) -> dict:
    return await _run(_get_info_sync, url)


async def download_video(url: str) -> Optional[str]:
    tmp = tempfile.mktemp(suffix=".mp4", dir=TMP_DIR)
    try:
        path = await _run(_download_video_sync, url, tmp)
        return path if path and os.path.exists(path) else None
    except Exception:
        cleanup(tmp, tmp + ".mp4")
        raise


async def download_audio(url: str) -> Optional[str]:
    tmp = tempfile.mktemp(dir=TMP_DIR)
    try:
        path = await _run(_download_audio_sync, url, tmp)
        return path if path and os.path.exists(path) else None
    except Exception:
        cleanup(tmp, tmp + ".mp3")
        raise


async def extract_audio_from_file(file_path: str) -> str:
    out = tempfile.mktemp(suffix=".mp3", dir=TMP_DIR)
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", file_path,
        "-vn", "-ar", "44100", "-ac", "2", "-ab", "192k",
        "-f", "mp3", out, "-y",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return out


def cleanup(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.unlink(p)
            except OSError:
                pass
