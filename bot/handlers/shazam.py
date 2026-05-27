import asyncio, os, tempfile, json, logging, traceback
from pathlib import Path
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from services.shazam_service import recognize_file
from services.music_search import search_tracks, format_duration, build_youtube_query
from services.downloader import cleanup
from db.crud import get_user, upsert_user
from config import BOT_ID

def t(lang, key):
    p = Path(__file__).parent.parent.parent/"locales"/f"{lang}.json"
    try: return json.loads(p.read_text()).get(key, key)
    except: return key

async def gl(uid):
    r = await get_user(uid); return r[1] if r else "uz"

def register(app):
    @app.on_message(filters.private & (filters.audio|filters.voice|filters.video|filters.video_note))
    async def h(client, msg):
        if msg.from_user.id == BOT_ID: return
        uid = msg.from_user.id; lang = await gl(uid)
        await upsert_user(uid, msg.from_user.username or "", msg.from_user.language_code or "uz")
        st = await msg.reply_text("🎤 Aniqlanmoqda...")
        fp = None
        try:
            fp = await asyncio.wait_for(msg.download(file_name=tempfile.mktemp(dir="/tmp")), timeout=60)
            if not fp or not os.path.exists(fp):
                try: await st.edit_text(t(lang,"error"))
                except: pass
                return
            result = await asyncio.wait_for(recognize_file(fp), timeout=40)
            if not result:
                try: await st.edit_text(t(lang,"shazam_not_found"))
                except: pass
                return
            title, artist, cover = result["title"], result["artist"], result.get("cover")
            tracks = await search_tracks(f"{artist} {title}", limit=1)
            dur = f"\n⏱  {format_duration(tracks[0]['duration'])}" if tracks else ""
            tx = f"🎵  <b>{title}</b>\n👤  {artist}{dur}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬇️ Yuklab olish",
                    callback_data=f"mdl:{tracks[0]['id']}:{tracks[0]['source']}" if tracks else "mcl")],
                [InlineKeyboardButton("🔍 YouTube",
                    url=f"https://www.youtube.com/results?search_query={build_youtube_query(title,artist).replace(' ','+')}")]])
            await st.delete()
            if cover:
                try: await msg.reply_photo(photo=cover, caption=tx, reply_markup=kb, parse_mode=enums.ParseMode.HTML); return
                except: pass
            await msg.reply_text(tx, reply_markup=kb, parse_mode=enums.ParseMode.HTML)
        except: traceback.print_exc()
        finally:
            if fp: cleanup(fp)
