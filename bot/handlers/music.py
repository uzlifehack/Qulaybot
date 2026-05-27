import asyncio, os, time, json, logging, traceback
from pathlib import Path
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from services.music_search import search_tracks, format_duration, build_youtube_query, get_track_by_id
from services.downloader import download_audio, cleanup
from cache.channel_cache import forward_to_user
from db.crud import get_user, upsert_user, get_cached, set_cached, inc_stat
from cache.redis_client import get_redis
from config import DOWNLOAD_SEMAPHORE, RATE_LIMIT, CACHE_CHANNEL_ID, BOT_ID

logger = logging.getLogger(__name__)
_sem = asyncio.Semaphore(DOWNLOAD_SEMAPHORE)
_sc: dict[str, dict] = {}

def t(lang, key):
    p = Path(__file__).parent.parent.parent/"locales"/f"{lang}.json"
    try: return json.loads(p.read_text()).get(key, key)
    except: return key

async def gl(uid):
    r = await get_user(uid); return r[1] if r else "uz"

def rtxt(tracks, query):
    lines = [f"🔍  <b>{query}</b>\n"]
    for i, tr in enumerate(tracks, 1):
        lines.append(f"<b>{i}.</b>  {tr['artist']} — {tr['title']}  <i>{format_duration(tr['duration'])}</i>")
    return "\n".join(lines)

def rbtn(tracks, pg=0, tot=0):
    row = [InlineKeyboardButton(str(pg*5+i+1), callback_data=f"mtr:{i}:{pg}") for i in range(len(tracks))]
    rows = [row]; nav = []
    if pg > 0: nav.append(InlineKeyboardButton("◀️", callback_data=f"mpg:{pg-1}"))
    if tot > (pg+1)*5: nav.append(InlineKeyboardButton("▶️", callback_data=f"mpg:{pg+1}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton("❌", callback_data="mcl")])
    return InlineKeyboardMarkup(rows)

def tbtn(tr):
    yt = build_youtube_query(tr['title'],tr['artist']).replace(' ','+')
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬇️ Yuklab olish", callback_data=f"mdl:{tr['id']}:{tr['source']}")],
        [InlineKeyboardButton("🔍 YouTube", url=f"https://www.youtube.com/results?search_query={yt}"),
         InlineKeyboardButton("🔙", callback_data="mbk")]])

def register(app):
    @app.on_message(filters.private & filters.text & ~filters.regex(r"https?://") &
        ~filters.command(["start","help","lang","admin","stats","broadcast","setforcesub"]))
    async def h(client, msg):
        if msg.from_user.id == BOT_ID: return
        q = msg.text.strip()
        if len(q) < 2 or len(q) > 100: return
        uid = msg.from_user.id; lang = await gl(uid)
        await upsert_user(uid, msg.from_user.username or "", msg.from_user.language_code or "uz")
        redis = await get_redis(); rl = f"rl:{uid}:{int(time.time()//60)}"
        cnt = await redis.incr(rl)
        if cnt == 1: await redis.expire(rl, 60)
        if cnt > RATE_LIMIT: await msg.reply_text(t(lang,"rate_limit")); return
        st = await msg.reply_text("🔍")
        try:
            tracks = await asyncio.wait_for(search_tracks(q, limit=10), timeout=15)
            if not tracks:
                try: await st.edit_text(t(lang,"no_results"))
                except: pass
                return
            _sc[f"s:{uid}:{st.id}"] = {"tracks": tracks, "query": q}
            pt = tracks[:5]
            await st.edit_text(rtxt(pt, q), reply_markup=rbtn(pt, 0, len(tracks)), parse_mode=enums.ParseMode.HTML)
        except asyncio.TimeoutError:
            try: await st.edit_text(t(lang,"error"))
            except: pass
        except: traceback.print_exc()

    @app.on_callback_query(filters.regex(r"^mpg:(\d+)$"))
    async def hpg(client, cb):
        if cb.from_user.id == BOT_ID: return
        await cb.answer()
        pg = int(cb.matches[0].group(1)); ck = f"s:{cb.from_user.id}:{cb.message.id}"
        d = _sc.get(ck)
        if not d: await cb.answer("Qayta qidiring", show_alert=True); return
        pt = d["tracks"][pg*5:pg*5+5]
        if not pt: return
        try: await cb.message.edit_text(rtxt(pt, d["query"]), reply_markup=rbtn(pt, pg, len(d["tracks"])), parse_mode=enums.ParseMode.HTML)
        except: pass

    @app.on_callback_query(filters.regex(r"^mtr:(\d+):(\d+)$"))
    async def htr(client, cb):
        if cb.from_user.id == BOT_ID: return
        await cb.answer()
        idx = int(cb.matches[0].group(1)); pg = int(cb.matches[0].group(2))
        ck = f"s:{cb.from_user.id}:{cb.message.id}"
        d = _sc.get(ck)
        if not d: await cb.answer("Qayta qidiring", show_alert=True); return
        ri = pg*5+idx
        if ri >= len(d["tracks"]): return
        tr = d["tracks"][ri]
        tx = f"🎵  <b>{tr['title']}</b>\n👤  {tr['artist']}\n💿  {tr['album']}\n⏱  {format_duration(tr['duration'])}"
        try: await cb.message.edit_text(tx, reply_markup=tbtn(tr), parse_mode=enums.ParseMode.HTML)
        except: pass

    @app.on_callback_query(filters.regex(r"^mdl:(.+):(.+)$"))
    async def hdl(client, cb):
        if cb.from_user.id == BOT_ID: return
        await cb.answer("⏳")
        tid = cb.matches[0].group(1); src = cb.matches[0].group(2)
        uid = cb.from_user.id; lang = await gl(uid)
        tr = await get_track_by_id(tid, src)
        if not tr: await cb.answer(t(lang,"error"), show_alert=True); return
        st = await cb.message.reply_text("⏳ Yuklanmoqda...")
        async with _sem:
            fp = None
            try:
                yt = f"ytsearch1:{build_youtube_query(tr['title'], tr['artist'])}"
                c = await get_cached(yt)
                if c: await forward_to_user(client,uid,c); await st.delete(); await inc_stat("downloads"); return
                fp = await asyncio.wait_for(download_audio(yt), timeout=300)
                if not fp or not os.path.exists(fp):
                    try: await st.edit_text(t(lang,"error"))
                    except: pass
                    return
                try: await st.edit_text("📤 Yuborilmoqda...")
                except: pass
                sent = await client.send_audio(chat_id=CACHE_CHANNEL_ID, audio=fp,
                    title=tr["title"], performer=tr["artist"], duration=tr["duration"])
                await set_cached(yt, sent.id)
                await client.forward_messages(chat_id=uid, from_chat_id=CACHE_CHANNEL_ID, message_ids=sent.id)
                await st.delete(); await inc_stat("downloads")
            except asyncio.TimeoutError:
                try: await st.edit_text(t(lang,"error"))
                except: pass
            except FloodWait as e: await asyncio.sleep(e.value+1)
            except: traceback.print_exc()
            finally:
                if fp: cleanup(fp)

    @app.on_callback_query(filters.regex(r"^mbk$"))
    async def hbk(client, cb):
        if cb.from_user.id == BOT_ID: return
        await cb.answer(); ck = f"s:{cb.from_user.id}:{cb.message.id}"
        d = _sc.get(ck)
        if not d: await cb.answer("Qayta qidiring", show_alert=True); return
        pt = d["tracks"][:5]
        try: await cb.message.edit_text(rtxt(pt, d["query"]), reply_markup=rbtn(pt, 0, len(d["tracks"])), parse_mode=enums.ParseMode.HTML)
        except: pass

    @app.on_callback_query(filters.regex(r"^mcl$"))
    async def hcl(client, cb):
        await cb.answer(); _sc.pop(f"s:{cb.from_user.id}:{cb.message.id}", None)
        try: await cb.message.delete()
        except: pass
