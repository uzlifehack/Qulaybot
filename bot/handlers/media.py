import asyncio, os, re, time, json, logging, traceback
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import DOWNLOAD_SEMAPHORE, RATE_LIMIT, MAX_FILE_SIZE, BOT_ID
from cache.channel_cache import get_or_download, forward_to_user
from services.downloader import download_video, download_audio, get_info, cleanup
from db.crud import get_user, upsert_user, inc_stat, get_cached
from cache.redis_client import get_redis

logger = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://[^\s]+")
AUDIO_D = ["music.youtube.com","soundcloud.com","spotify.com","music.apple.com"]
IMAGE_D = ["instagram.com","pinterest.com","twitter.com","x.com","flickr.com","tumblr.com","imgur.com"]
_sem = asyncio.Semaphore(DOWNLOAD_SEMAPHORE)

def t(lang, key):
    p = Path(__file__).parent.parent.parent/"locales"/f"{lang}.json"
    try: return json.loads(p.read_text()).get(key, key)
    except: return key

async def gl(uid):
    r = await get_user(uid); return r[1] if r else "uz"

def register(app, strings=None):
    @app.on_message(filters.text & filters.private & filters.regex(URL_RE))
    async def h(client, msg):
        if msg.from_user.id == BOT_ID: return
        m = URL_RE.search(msg.text)
        if not m: return
        url = m.group()
        if any(d in url for d in IMAGE_D): return
        uid = msg.from_user.id; lang = await gl(uid)
        redis = await get_redis(); rl = f"rl:{uid}:{int(time.time()//60)}"
        cnt = await redis.incr(rl)
        if cnt == 1: await redis.expire(rl, 60)
        if cnt > RATE_LIMIT: await msg.reply_text(t(lang,"rate_limit")); return
        await upsert_user(uid, msg.from_user.username or "", msg.from_user.language_code or "uz")
        st = await msg.reply_text("⏳ Yuklanmoqda...")
        async with _sem:
            fp = None
            try:
                c = await get_cached(url)
                if c: await forward_to_user(client,uid,c); await st.delete(); await inc_stat("downloads"); return
                try: info = await asyncio.wait_for(get_info(url), timeout=30)
                except:
                    try: await st.edit_text(t(lang,"unsupported"))
                    except: pass
                    return
                fs = info.get("filesize") or info.get("filesize_approx") or 0
                if fs and fs > MAX_FILE_SIZE:
                    try: await st.edit_text(t(lang,"file_too_large"))
                    except: pass
                    return
                if any(d in url for d in AUDIO_D): fp = await asyncio.wait_for(download_audio(url), timeout=300)
                else: fp = await asyncio.wait_for(download_video(url), timeout=300)
                if not fp or not os.path.exists(fp):
                    try: await st.edit_text(t(lang,"error"))
                    except: pass
                    return
                try: await st.edit_text("📤 Yuborilmoqda...")
                except: pass
                cap = fp
                async def _p(_u): return cap
                mid = await get_or_download(client, url, _p)
                await forward_to_user(client, uid, mid); await st.delete(); await inc_stat("downloads")
            except asyncio.TimeoutError:
                try: await st.edit_text(t(lang,"error"))
                except: pass
            except FloodWait as e: await asyncio.sleep(e.value+1)
            except: traceback.print_exc()
            finally:
                if fp: cleanup(fp)
