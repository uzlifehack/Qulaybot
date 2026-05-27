import asyncio
import aiohttp
from typing import Optional

DEEZER_API = "https://api.deezer.com"
ITUNES_API = "https://itunes.apple.com"

_session: Optional[aiohttp.ClientSession] = None

async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        connector = aiohttp.TCPConnector(limit=20, ssl=False)
        timeout = aiohttp.ClientTimeout(total=15)
        _session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return _session

async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None

async def search_tracks(query: str, limit: int = 5) -> list[dict]:
    # Avval Deezer, ishlamasa iTunes
    result = await _search_deezer(query, limit)
    if not result:
        result = await _search_itunes(query, limit)
    return result

async def _search_deezer(query: str, limit: int) -> list[dict]:
    try:
        session = await get_session()
        async with session.get(
            f"{DEEZER_API}/search",
            params={"q": query, "limit": limit}
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            tracks = data.get("data", [])
            return [_parse_deezer(t) for t in tracks]
    except Exception:
        return []

async def _search_itunes(query: str, limit: int) -> list[dict]:
    try:
        session = await get_session()
        async with session.get(
            f"{ITUNES_API}/search",
            params={
                "term": query,
                "media": "music",
                "limit": limit,
                "entity": "song"
            }
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return [_parse_itunes(t) for t in data.get("results", [])]
    except Exception:
        return []

def _parse_deezer(t: dict) -> dict:
    return {
        "id": str(t.get("id", "")),
        "title": t.get("title", ""),
        "artist": t.get("artist", {}).get("name", ""),
        "album": t.get("album", {}).get("title", ""),
        "duration": t.get("duration", 0),
        "preview": t.get("preview", ""),
        "cover": (t.get("album", {}).get("cover_xl")
                  or t.get("album", {}).get("cover_big")
                  or t.get("album", {}).get("cover", "")),
        "source": "deezer",
    }

def _parse_itunes(t: dict) -> dict:
    duration_ms = t.get("trackTimeMillis", 0)
    cover = t.get("artworkUrl100", "").replace("100x100", "600x600")
    return {
        "id": str(t.get("trackId", "")),
        "title": t.get("trackName", ""),
        "artist": t.get("artistName", ""),
        "album": t.get("collectionName", ""),
        "duration": duration_ms // 1000,
        "preview": t.get("previewUrl", ""),
        "cover": cover,
        "source": "itunes",
    }

async def get_track_by_id(track_id: str, source: str = "deezer") -> Optional[dict]:
    if source == "deezer":
        try:
            session = await get_session()
            async with session.get(f"{DEEZER_API}/track/{track_id}") as resp:
                if resp.status != 200:
                    return None
                return _parse_deezer(await resp.json())
        except Exception:
            return None
    return None

def format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"

def build_youtube_query(title: str, artist: str) -> str:
    return f"{artist} {title} official audio"
