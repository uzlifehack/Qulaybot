import asyncio, os, json, time, logging, traceback
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto
from pyrogram.errors import FloodWait
from services.image_service import download_images, cleanup_dir, get_parent_dir
from db.crud import get_user, upsert_user, inc_stat
from cache.redis_client import get_redis
from config import RATE_LIMIT, BOT_ID

def t(lang, key):
    p = Path(__file__).parent.parent.parent/"locales"/f"{lang}.json"
    try: return json.loads(p.read_text()).get(key, key)
    except: return key

async def gl(uid):
    r = await get_user(uid); return r[1] if r else "uz"

def register(app):
    @app.on_message(filters.private & filters.text &
        filters.regex(r"https?://(www\.)?(instagram\.com|pinterest\.com|twitter\.com|x\.com|flickr\.com|tumblr\.com|imgur\.com)"))
    async def h(client, msg):
        if msg.from_user.id == BOT_ID: return
        uid = msg.from_user.id; lang = await gl(uid); url = msg.text.strip()
        await upsert_user(uid, msg.from_user.username or "", msg.from_user.language_code or "uz")
        redis = await get_redis(); rl = f"rl:{uid}:{int(time.time()//60)}"
        cnt = await redis.incr(rl)
        if cnt == 1: await redis.expire(rl, 60)
        if cnt > RATE_LIMIT: await msg.reply_text(t(lang,"rate_limit")); return
        st = await msg.reply_text("⏳ Yuklanmoqda...")
        od = None
        try:
            files = await asyncio.wait_for(download_images(url), timeout=90)
            if not files:
                try: await st.edit_text(t(lang,"error"))
                except: pass
                return
            od = get_parent_dir(files[0])
            try: await st.edit_text("📤 Yuborilmoqda...")
            except: pass
            if len(files) == 1: await client.send_photo(chat_id=uid, photo=files[0])
            else:
                mg = [InputMediaPhoto(f) for f in files]
                for i in range(0, len(mg), 10):
                    try: await client.send_media_group(chat_id=uid, media=mg[i:i+10])
                    except FloodWait as e: await asyncio.sleep(e.value+1)
                    except: break
            await st.delete(); await inc_stat("downloads")
        except: traceback.print_exc()
        finally:
            if od: cleanup_dir(od)
