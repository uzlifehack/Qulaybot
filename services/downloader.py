import asyncio
import tempfile
import os
from pathlib import Path
from typing import Optional
import yt_dlp
from config import MAX_FILE_SIZE

COOKIES_FILE = str(Path(__file__).parent.parent / "cookies.txt")

YDL_BASE = {
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 60,
    "retries": 10,
    "fragment_retries": 10,
    "extractor_retries": 10,
    "skip_unavailable_fragments": True,
    "concurrent_fragment_downloads": 4,
    "http_chunk_size": 10485760,
    "nocheckcertificate": True,
    "geo_bypass": True,
    "geo_bypass_country": "US",
    "max_filesize": MAX_FILE_SIZE,
    "extractor_args": {
        "youtube": [
            "player_client=android,web,ios,tv_embedded",
        ]
    },
}

if Path(COOKIES_FILE).exists():
    YDL_BASE["cookiefile"] = COOKIES_FILE

def _download_video_sync(url: str, out_path: str) -> str:
    opts = {
        **YDL_BASE,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
        "outtmpl": out_path,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return out_path

def _download_audio_sync(url: str, out_path: str) -> str:
    opts = {
        **YDL_BASE,
        "format": "bestaudio/best",
        "outtmpl": out_path,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return out_path + ".mp3"

def _get_info_sync(url: str) -> dict:
    opts = {**YDL_BASE, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

async def get_info(url: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_info_sync, url)

async def download_video(url: str) -> Optional[str]:
    tmp = tempfile.mktemp(suffix=".mp4", dir="/tmp")
    loop = asyncio.get_event_loop()
    try:
        path = await loop.run_in_executor(None, _download_video_sync, url, tmp)
        if os.path.exists(path):
            return path
        return None
    except Exception as e:
        for f in [tmp, tmp + ".mp4"]:
            if os.path.exists(f):
                os.unlink(f)
        raise e

async def download_audio(url: str) -> Optional[str]:
    tmp = tempfile.mktemp(dir="/tmp")
    loop = asyncio.get_event_loop()
    try:
        path = await loop.run_in_executor(None, _download_audio_sync, url, tmp)
        if os.path.exists(path):
            return path
        return None
    except Exception as e:
        for f in [tmp, tmp + ".mp3"]:
            if os.path.exists(f):
                os.unlink(f)
        raise e

async def extract_audio_from_file(file_path: str) -> str:
    out = tempfile.mktemp(suffix=".mp3", dir="/tmp")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", file_path,
        "-vn", "-ar", "44100", "-ac", "2", "-ab", "192k",
        "-f", "mp3", out, "-y",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()
    return out

def cleanup(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.unlink(p)
            except:
                pass
