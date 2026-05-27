import asyncio
import os
import tempfile
import subprocess
from typing import Optional
from pathlib import Path

COOKIES_FILE = str(Path(__file__).parent.parent / "cookies.txt")

SUPPORTED_DOMAINS = [
    "instagram.com", "pinterest.com", "twitter.com",
    "x.com", "flickr.com", "tumblr.com", "imgur.com",
]

def is_supported(url: str) -> bool:
    return any(d in url for d in SUPPORTED_DOMAINS)

def _download_sync(url: str, out_dir: str) -> list[str]:
    cmd = [
        "gallery-dl",
        "--dest", out_dir,
        "--filename", "{id}.{extension}",
        "--no-download-archive",
    ]
    if os.path.exists(COOKIES_FILE):
        cmd += ["--cookies", COOKIES_FILE]
    cmd.append(url)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60
    )

    files = []
    for f in sorted(Path(out_dir).rglob("*")):
        if f.is_file() and f.suffix.lower() in [
            ".jpg", ".jpeg", ".png", ".gif", ".webp"
        ]:
            files.append(str(f))
    return files

async def download_images(url: str) -> list[str]:
    out_dir = tempfile.mkdtemp(dir="/tmp")
    loop = asyncio.get_event_loop()
    try:
        files = await asyncio.wait_for(
            loop.run_in_executor(None, _download_sync, url, out_dir),
            timeout=90
        )
        # Telegram: album uchun max 10 ta rasm
        return files[:10]
    except asyncio.TimeoutError:
        return []
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []

def cleanup_dir(dir_path: str):
    import shutil
    try:
        shutil.rmtree(dir_path, ignore_errors=True)
    except Exception:
        pass

def get_parent_dir(file_path: str) -> str:
    return str(Path(file_path).parent)
