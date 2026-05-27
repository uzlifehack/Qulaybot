import asyncio, json, logging, os, sys
from pathlib import Path
from pyrogram import Client, filters, idle, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserNotParticipant
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_IDS, BOT_ID
from db.models import init_db
from db.crud import get_user, upsert_user, set_user_lang
from cache.redis_client import get_redis, close_redis
from services.music_search import close_session
from bot.handlers import media, music, shazam, image, admin

BASE_DIR = Path(__file__).parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(str(BASE_DIR/"bot.log")), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

STRINGS = {}
for _l in ["uz","ru","en","tr"]:
    _p = BASE_DIR/"locales"/f"{_l}.json"
    try: STRINGS[_l] = json.loads(_p.read_text())
    except: STRINGS[_l] = {}

def t(lang, key, **kw):
    tx = STRINGS.get(lang,{}).get(key) or STRINGS.get("uz",{}).get(key, key)
    return tx.format(**kw) if kw else tx

async def get_lang(uid):
    r = await get_user(uid); return r[1] if r else "uz"

async def check_fs(client, uid):
    redis = await get_redis()
    ch = await redis.get("forcesub_channel")
    if not ch: return True
    try:
        m = await client.get_chat_member(ch, uid)
        return m.status.value not in ["kicked","left"]
    except UserNotParticipant: return False
    except: return True

app = Client("lyra_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir=str(BASE_DIR))
image.register(app)
shazam.register(app)
media.register(app, STRINGS)
music.register(app)
admin.register(app)

@app.on_message(filters.command("start") & filters.private)
async def h_start(client, msg):
    if msg.from_user.id == BOT_ID: return
    u = msg.from_user
    lc = (u.language_code or "uz").split("-")[0].lower()
    lang = lc if lc in ["uz","ru","en","tr"] else "uz"
    await upsert_user(u.id, u.username or "", lang)
    redis = await get_redis(); ch = await redis.get("forcesub_channel")
    if ch and not await check_fs(client, u.id):
        await msg.reply_text(t(lang,"force_sub"), reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Qo'shilish", url=f"https://t.me/{ch.lstrip('@')}")],
            [InlineKeyboardButton("✅ Tekshirish", callback_data="chksub")]]))
        return
    await msg.reply_text(t(lang,"start"), reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("🌐 Til", callback_data="lmenu")]]))

@app.on_callback_query(filters.regex(r"^chksub$"))
async def h_chk(client, cb):
    if await check_fs(client, cb.from_user.id):
        await cb.answer("✅")
        try: await cb.message.delete()
        except: pass
        await client.send_message(cb.from_user.id, t(await get_lang(cb.from_user.id),"start"))
    else: await cb.answer("❌ Kanalga qo'shiling", show_alert=True)

@app.on_callback_query(filters.regex(r"^lmenu$"))
async def h_lm(client, cb):
    await cb.answer()
    await cb.message.edit_text(t(await get_lang(cb.from_user.id),"choose_lang"), reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇿 O'zbek", callback_data="sl:uz"), InlineKeyboardButton("🇷🇺 Русский", callback_data="sl:ru")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="sl:en"), InlineKeyboardButton("🇹🇷 Türkçe", callback_data="sl:tr")]]))

@app.on_callback_query(filters.regex(r"^sl:(.+)$"))
async def h_sl(client, cb):
    lang = cb.matches[0].group(1)
    if lang not in ["uz","ru","en","tr"]: await cb.answer("❌", show_alert=True); return
    await set_user_lang(cb.from_user.id, lang)
    await cb.answer(t(lang,"lang_changed"), show_alert=True)
    try: await cb.message.delete()
    except: pass

@app.on_message(filters.command(["lang","help"]) & filters.private)
async def h_lh(client, msg):
    if msg.from_user.id == BOT_ID: return
    lang = await get_lang(msg.from_user.id)
    if msg.command[0] == "help":
        await msg.reply_text(t(lang,"start"))
    else:
        await msg.reply_text(t(lang,"choose_lang"), reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🇺🇿 O'zbek", callback_data="sl:uz"), InlineKeyboardButton("🇷🇺 Русский", callback_data="sl:ru")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="sl:en"), InlineKeyboardButton("🇹🇷 Türkçe", callback_data="sl:tr")]]))

async def main():
    await init_db(); await app.start()
    me = await app.get_me()
    logger.info(f"Bot: @{me.username}"); print(f"✅ @{me.username}")
    for a in ADMIN_IDS:
        try: await app.send_message(a, "✅ Lyra ishga tushdi")
        except: pass
    await idle(); await close_redis(); await close_session(); await app.stop()

if __name__ == "__main__":
    app.run(main())
