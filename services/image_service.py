"""
Image / gallery / reel downloader built on gallery-dl.

Handles Instagram, Pinterest, X/Twitter, Flickr, Tumblr and Imgur. Returns
both images and videos so reels and video posts are delivered too.
"""

import asyncio
import os
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Optional

COOKIES_FILE = str(Path(__file__).parent.parent / "cookies.txt")

SUPPORTED_DOMAINS = [
    "instagram.com", "pinterest.com", "twitter.com",
    "x.com", "flickr.com", "tumblr.com", "imgur.com",
]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

# Telegram album limit.
MAX_ITEMS = 10


def is_supported(url: str) -> bool:
    return any(d in url for d in SUPPORTED_DOMAINS)


def _download_sync(url: str, out_dir: str) -> list[str]:
    cmd = [
        "gallery-dl",
        "--dest", out_dir,
        "--filename", "{num:>03}_{id}.{extension}",
        "--no-download-archive",
        "--quiet",
    ]
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
        cmd += ["--cookies", COOKIES_FILE]
    cmd.append(url)

    subprocess.run(cmd, capture_output=True, text=True, timeout=75)

    files = [
        str(f)
        for f in sorted(Path(out_dir).rglob("*"))
        if f.is_file() and f.suffix.lower() in MEDIA_EXTS
    ]
    return files


async def download_media(url: str) -> list[str]:
    """Download up to MAX_ITEMS media files (images + videos)."""
    out_dir = tempfile.mkdtemp(dir="/tmp")
    loop = asyncio.get_event_loop()
    try:
        files = await asyncio.wait_for(
            loop.run_in_executor(None, _download_sync, url, out_dir),
            timeout=90,
        )
        return files[:MAX_ITEMS]
    except (asyncio.TimeoutError, subprocess.TimeoutExpired):
        cleanup_dir(out_dir)
        return []
    except Exception:
        cleanup_dir(out_dir)
        return []


# Backwards-compatible alias.
async def download_images(url: str) -> list[str]:
    return await download_media(url)


def is_video(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


def cleanup_dir(dir_path: str):
    try:
        shutil.rmtree(dir_path, ignore_errors=True)
    except Exception:
        pass


def get_parent_dir(file_path: str) -> str:
    return str(Path(file_path).parent)
