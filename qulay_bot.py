#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import uuid
import shutil
import asyncio
import logging
import subprocess
import time
import traceback
import sys
import json
import threading
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from collections import defaultdict, deque
from functools import wraps
from datetime import datetime, timedelta

import requests
from pyrogram import Client, filters, raw, enums
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    InlineQueryResultVideo, InlineQueryResultAudio
)
from pyrogram.enums import ChatAction
from pyrogram.errors import FloodWait, MessageNotModified
import yt_dlp
import sqlite3

# ─── CONFIG ───────────────────────────────────────────────────────────────────

API_ID     = int(os.getenv("API_ID", "39474802"))
API_HASH   = os.getenv("API_HASH", "f505449dd881e1408c033541734c11ae")
BOT_TOKEN  = os.getenv("BOT_TOKEN", "8140094720:AAHUPpqSm4UqocYpC5_ZPZok8CVzdnH2Qhg")
ADMIN_IDS  = [int(x) for x in os.getenv("ADMIN_IDS", "8471569554").split(",")]

BOT_DIR       = Path(__file__).parent
TEMP_BASE     = BOT_DIR / "tmp"
MEDIA_STORAGE = BOT_DIR / "media"
DB_PATH       = str(BOT_DIR / "lyra.db")
LOG_FILE      = str(BOT_DIR / "bot.log")
COOKIES_FILE  = str(BOT_DIR / "cookies.txt")
BOT_USERNAME  = "@qulayskachat_bot"
CACHE_CHANNEL = "@lyarkanal"

RATE_LIMIT_SEC   = 3.0
URL_CACHE_TTL    = 3600
DEEZER_CACHE_TTL = 300
MEDIA_CACHE_MAX  = 2000
TRACK_CACHE_MAX  = 500

TEMP_BASE.mkdir(exist_ok=True)
MEDIA_STORAGE.mkdir(exist_ok=True)

# ─── YT-DLP GLOBAL OPTIONS ────────────────────────────────────────────────────

YTDL_BASE = {
    "quiet":                        True,
    "no_warnings":                  True,
    "socket_timeout":               60,
    "retries":                      10,
    "fragment_retries":             10,
    "extractor_retries":            10,
    "skip_unavailable_fragments":   True,
    "concurrent_fragment_downloads": 4,
    "http_chunk_size":              10485760,
    "nocheckcertificate":           True,
    "geo_bypass":                   True,
    "geo_bypass_country":           "US",
    "extractor_args": {
        "youtube": {
            "player_client": ["ios", "android", "web"],
        }
    },
}

if Path(COOKIES_FILE).exists():
    YTDL_BASE["cookiefile"] = COOKIES_FILE

def _make_progress_hook(callback):
    """yt-dlp progress hook - foizni qaytaradi"""
    last_pct = [0]
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = int(downloaded * 100 / total)
                if pct >= last_pct[0] + 10:
                    last_pct[0] = pct
                    callback(pct)
        elif d["status"] == "finished":
            callback(100)
    return hook

# ─── LOGGING ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# ─── I18N ─────────────────────────────────────────────────────────────────────

STRINGS = {
    "uz": {
        "start":        "Yuklab olish uchun link yuboring.\nMusiqa uchun nomini yuboring.\n\n/imkoniyatlar — qo'llab-quvvatlanadigan saytlar",
        "wait":         "⏳ Iltimos kuting...",
        "banned":       "🚫 Siz bloklangansiz.",
        "rate":         "⏳ Iltimos kuting...",
        "not_found":    "❌ Topilmadi.",
        "dl_fail":      "❌ Yuklab bo'lmadi.",
        "link_fail":    "❌ Bu havola ishlamadi.",
        "quality":      "📊 Sifat tanlang:",
        "search_title": "🎧 <b>{query}</b>\n\n{lines}",
        "shazam_fail":  "❌ Musiqa aniqlanmadi.",
        "audio_extract_fail": "❌ Audio ajratib bo'lmadi.",
        "media_not_found": "❌ Media topilmadi.",
        "file_not_found":  "❌ Fayl topilmadi.",
        "already_audio":   "Bu allaqachon audio.",
        "share":        "↗️ Ulashish",
        "shazam_btn":   "🔍 Shazam",
        "audio_btn":    "🎵 Audio",
        "caption":      "✨ @qulayskachat_bot orqali yuklab olindi",
        "lang_set":     "🇺🇿 Til o'zgartirildi: O'zbek",
        "select_lang":  "🌐 Tilni tanlang:",
        "joined":       "✅ Muvaffaqiyatli! Endi botdan foydalanishingiz mumkin.",
        "not_joined":   "❌ Siz hali kanallarga a'zo bo'lmagansiz.",
        "check_btn":    "✅ Tekshirish",
        "join_btn":     "📢 Obuna bo'lish",
        "force_sub":    "📢 Botdan foydalanish uchun kanalga obuna bo'ling!",
        "capabilities": (
            "📹 <b>Video:</b> YouTube, TikTok, Instagram, Twitter/X, Facebook, "
            "Vimeo, Dailymotion, Twitch, Reddit, Bilibili, Rumble, VK\n\n"
            "🎵 <b>Musiqa:</b> Spotify, Deezer, YouTube Music\n\n"
            "🖼 <b>Rasm:</b> Instagram, Pinterest, Twitter/X, Flickr\n\n"
            "➕ <b>Qo'shimcha:</b> Shazam, Audio ajratish, Inline ulashish"
        ),
    },
    "ru": {
        "start":        "Отправьте ссылку для скачивания.\nДля музыки — отправьте название.\n\n/imkoniyatlar — поддерживаемые сайты",
        "wait":         "⏳ Пожалуйста, подождите...",
        "banned":       "🚫 Вы заблокированы.",
        "rate":         "⏳ Пожалуйста, подождите...",
        "not_found":    "❌ Не найдено.",
        "dl_fail":      "❌ Не удалось скачать.",
        "link_fail":    "❌ Ссылка не работает.",
        "quality":      "📊 Выберите качество:",
        "search_title": "🎧 <b>{query}</b>\n\n{lines}",
        "shazam_fail":  "❌ Музыка не распознана.",
        "audio_extract_fail": "❌ Не удалось извлечь аудио.",
        "media_not_found": "❌ Медиа не найдено.",
        "file_not_found":  "❌ Файл не найден.",
        "already_audio":   "Это уже аудио.",
        "share":        "↗️ Поделиться",
        "shazam_btn":   "🔍 Shazam",
        "audio_btn":    "🎵 Аудио",
        "caption":      "✨ Скачано через @qulayskachat_bot",
        "lang_set":     "🇷🇺 Язык изменён: Русский",
        "select_lang":  "🌐 Выберите язык:",
        "joined":       "✅ Отлично! Теперь вы можете пользоваться ботом.",
        "not_joined":   "❌ Вы ещё не подписались на все каналы.",
        "check_btn":    "✅ Проверить",
        "join_btn":     "📢 Подписаться",
        "force_sub":    "📢 Подпишитесь на канал, чтобы использовать бота!",
        "capabilities": (
            "📹 <b>Видео:</b> YouTube, TikTok, Instagram, Twitter/X, Facebook, "
            "Vimeo, Dailymotion, Twitch, Reddit, Bilibili, Rumble, VK\n\n"
            "🎵 <b>Музыка:</b> Spotify, Deezer, YouTube Music\n\n"
            "🖼 <b>Фото:</b> Instagram, Pinterest, Twitter/X, Flickr\n\n"
            "➕ <b>Дополнительно:</b> Shazam, извлечение аудио, inline-отправка"
        ),
    },
    "en": {
        "start":        "Send a link to download.\nFor music — send the song name.\n\n/imkoniyatlar — supported sites",
        "wait":         "⏳ Please wait...",
        "banned":       "🚫 You are banned.",
        "rate":         "⏳ Please wait...",
        "not_found":    "❌ Not found.",
        "dl_fail":      "❌ Download failed.",
        "link_fail":    "❌ This link doesn't work.",
        "quality":      "📊 Select quality:",
        "search_title": "🎧 <b>{query}</b>\n\n{lines}",
        "shazam_fail":  "❌ Music not recognized.",
        "audio_extract_fail": "❌ Could not extract audio.",
        "media_not_found": "❌ Media not found.",
        "file_not_found":  "❌ File not found.",
        "already_audio":   "This is already audio.",
        "share":        "↗️ Share",
        "shazam_btn":   "🔍 Shazam",
        "audio_btn":    "🎵 Audio",
        "caption":      "✨ Downloaded via @qulayskachat_bot",
        "lang_set":     "🇬🇧 Language changed: English",
        "select_lang":  "🌐 Select language:",
        "joined":       "✅ Great! You can now use the bot.",
        "not_joined":   "❌ You haven't joined all channels yet.",
        "check_btn":    "✅ Check",
        "join_btn":     "📢 Join Channel",
        "force_sub":    "📢 Please join our channel to use the bot!",
        "capabilities": (
            "📹 <b>Video:</b> YouTube, TikTok, Instagram, Twitter/X, Facebook, "
            "Vimeo, Dailymotion, Twitch, Reddit, Bilibili, Rumble, VK\n\n"
            "🎵 <b>Music:</b> Spotify, Deezer, YouTube Music\n\n"
            "🖼 <b>Photos:</b> Instagram, Pinterest, Twitter/X, Flickr\n\n"
            "➕ <b>Extra:</b> Shazam, audio extraction, inline sharing"
        ),
    },
    "tr": {
        "start":        "İndirmek için link gönderin.\nMüzik için şarkı adını gönderin.\n\n/imkoniyatlar — desteklenen siteler",
        "wait":         "⏳ Lütfen bekleyin...",
        "banned":       "🚫 Engellendiniz.",
        "rate":         "⏳ Lütfen bekleyin...",
        "not_found":    "❌ Bulunamadı.",
        "dl_fail":      "❌ İndirme başarısız.",
        "link_fail":    "❌ Bu link çalışmıyor.",
        "quality":      "📊 Kalite seçin:",
        "search_title": "🎧 <b>{query}</b>\n\n{lines}",
        "shazam_fail":  "❌ Müzik tanınamadı.",
        "audio_extract_fail": "❌ Ses çıkarılamadı.",
        "media_not_found": "❌ Medya bulunamadı.",
        "file_not_found":  "❌ Dosya bulunamadı.",
        "already_audio":   "Bu zaten ses dosyası.",
        "share":        "↗️ Paylaş",
        "shazam_btn":   "🔍 Shazam",
        "audio_btn":    "🎵 Ses",
        "caption":      "✨ @qulayskachat_bot aracılığıyla indirildi",
        "lang_set":     "🇹🇷 Dil değiştirildi: Türkçe",
        "select_lang":  "🌐 Dil seçin:",
        "joined":       "✅ Harika! Artık botu kullanabilirsiniz.",
        "not_joined":   "❌ Henüz tüm kanallara abone olmadınız.",
        "check_btn":    "✅ Kontrol Et",
        "join_btn":     "📢 Abone Ol",
        "force_sub":    "📢 Botu kullanmak için kanalımıza abone olun!",
        "capabilities": (
            "📹 <b>Video:</b> YouTube, TikTok, Instagram, Twitter/X, Facebook, "
            "Vimeo, Dailymotion, Twitch, Reddit, Bilibili, Rumble, VK\n\n"
            "🎵 <b>Müzik:</b> Spotify, Deezer, YouTube Music\n\n"
            "🖼 <b>Fotoğraf:</b> Instagram, Pinterest, Twitter/X, Flickr\n\n"
            "➕ <b>Ekstra:</b> Shazam, ses çıkarma, inline paylaşım"
        ),
    },
}

TG_LANG_MAP = {
    "uz": "uz", "ru": "ru", "en": "en", "tr": "tr",
    "uk": "ru", "be": "ru", "kk": "ru",
}

def t(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in STRINGS else "uz"
    text = STRINGS[lang].get(key, STRINGS["uz"].get(key, key))
    return text.format(**kwargs) if kwargs else text

def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang:uz"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
    ], [
        InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
        InlineKeyboardButton("🇹🇷 Türkçe",  callback_data="lang:tr"),
    ]])

# ─── DATABASE ─────────────────────────────────────────────────────────────────

_db_lock = threading.Lock()
_thread_local = threading.local()

def _db_conn() -> sqlite3.Connection:
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _thread_local.conn = conn
    return conn

def _db_retry(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        for attempt in range(3):
            try:
                return fn(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < 2:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise
    return wrapper

@_db_retry
def db_init():
    with _db_lock:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            lang        TEXT DEFAULT 'uz',
            joined_at   TEXT,
            last_active TEXT,
            downloads   INTEGER DEFAULT 0,
            is_banned   INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS downloads (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            url        TEXT,
            platform   TEXT,
            status     TEXT,
            created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS file_ids (
            media_id   TEXT PRIMARY KEY,
            file_id    TEXT NOT NULL,
            media_type TEXT NOT NULL,
            created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS rate_limits (
            user_id  INTEGER PRIMARY KEY,
            last_req REAL NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS force_sub_channels (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            channel  TEXT UNIQUE NOT NULL,
            added_at TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_dl_user ON downloads(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_active ON users(last_active)")
        c.execute("CREATE TABLE IF NOT EXISTS url_cache (url TEXT PRIMARY KEY, file_id TEXT NOT NULL, media_type TEXT NOT NULL, title TEXT DEFAULT '', created_at TEXT)")
        conn.commit()

@_db_retry
def db_user(user_id: int, username=None, first_name=None, lang=None):
    with _db_lock:
        conn = _db_conn()
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            c.execute("""INSERT OR IGNORE INTO users
                (user_id, username, first_name, lang, joined_at, last_active)
                VALUES (?,?,?,?,?,?)""",
                (user_id, username, first_name, lang or "uz", now, now))
            if lang:
                c.execute("UPDATE users SET last_active=?,username=?,first_name=?,lang=? WHERE user_id=?",
                          (now, username, first_name, lang, user_id))
            else:
                c.execute("UPDATE users SET last_active=?,username=?,first_name=? WHERE user_id=?",
                          (now, username, first_name, user_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

@_db_retry
def db_set_lang(user_id: int, lang: str):
    with _db_lock:
        conn = _db_conn()
        try:
            conn.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

@_db_retry
def db_get_lang(user_id: int) -> str:
    conn = _db_conn()
    c = conn.cursor()
    c.execute("SELECT lang FROM users WHERE user_id=?", (user_id,))
    r = c.fetchone()
    return r[0] if r else "uz"

@_db_retry
def db_is_banned(user_id: int) -> bool:
    conn = _db_conn()
    c = conn.cursor()
    c.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
    r = c.fetchone()
    return bool(r and r[0])

@_db_retry
def db_check_rate(user_id: int) -> bool:
    now = time.time()
    with _db_lock:
        conn = _db_conn()
        c = conn.cursor()
        c.execute("SELECT last_req FROM rate_limits WHERE user_id=?", (user_id,))
        r = c.fetchone()
        if r and now - r[0] < RATE_LIMIT_SEC:
            return False
        c.execute("INSERT OR REPLACE INTO rate_limits (user_id, last_req) VALUES (?,?)",
                  (user_id, now))
        conn.commit()
        return True

@_db_retry
def db_add_download(user_id: int, url: str, platform: str, status: str):
    with _db_lock:
        conn = _db_conn()
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            c.execute("INSERT INTO downloads (user_id,url,platform,status,created_at) VALUES (?,?,?,?,?)",
                      (user_id, url, platform, status, now))
            c.execute("UPDATE users SET downloads=downloads+1 WHERE user_id=?", (user_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

@_db_retry
def db_stats() -> tuple:
    conn = _db_conn()
    c = conn.cursor()
    today    = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    c.execute("SELECT COUNT(*) FROM users"); total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE last_active LIKE ?", (today+"%",)); at = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE last_active >= ?", (week_ago,)); aw = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM downloads WHERE created_at LIKE ?", (today+"%",)); dt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM downloads"); dtotal = c.fetchone()[0]
    return total, at, aw, dt, dtotal

@_db_retry
def save_file_id(media_id: str, file_id: str, media_type: str):
    with _db_lock:
        conn = _db_conn()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn.execute("INSERT OR REPLACE INTO file_ids (media_id,file_id,media_type,created_at) VALUES (?,?,?,?)",
                     (media_id, file_id, media_type, now))
        conn.commit()

@_db_retry
def load_file_id(media_id: str) -> Optional[dict]:
    conn = _db_conn()
    c = conn.cursor()
    c.execute("SELECT file_id, media_type FROM file_ids WHERE media_id=?", (media_id,))
    r = c.fetchone()
    return {"file_id": r[0], "type": r[1]} if r else None

@_db_retry
def db_get_force_channels() -> list:
    try:
        conn = _db_conn()
        c = conn.cursor()
        c.execute("SELECT channel FROM force_sub_channels ORDER BY id")
        rows = [r[0] for r in c.fetchall()]
        return rows
    except:
        return []

@_db_retry
def db_add_force_channel(channel: str):
    with _db_lock:
        conn = _db_conn()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn.execute("INSERT OR IGNORE INTO force_sub_channels (channel,added_at) VALUES (?,?)",
                     (channel, now))
        conn.commit()

@_db_retry
def db_remove_force_channel(channel: str):
    with _db_lock:
        conn = _db_conn()
        conn.execute("DELETE FROM force_sub_channels WHERE channel=?", (channel,))
        conn.commit()

@_db_retry
def db_get_url_cache(url: str) -> Optional[dict]:
    conn = _db_conn()
    c = conn.cursor()
    c.execute("SELECT file_id, media_type, title FROM url_cache WHERE url=?", (url,))
    r = c.fetchone()
    return {"file_id": r[0], "type": r[1], "title": r[2]} if r else None

@_db_retry
def db_set_url_cache(url: str, file_id: str, media_type: str, title: str = ""):
    with _db_lock:
        conn = _db_conn()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn.execute("INSERT OR REPLACE INTO url_cache (url,file_id,media_type,title,created_at) VALUES (?,?,?,?,?)",
                     (url, file_id, media_type, title, now))
        conn.commit()

@_db_retry
def db_check_user_status(user_id: int, username=None, first_name=None) -> tuple:
    now_ts = time.time()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with _db_lock:
        conn = _db_conn()
        c = conn.cursor()
        c.execute("SELECT is_banned, lang FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT OR IGNORE INTO users (user_id,username,first_name,lang,joined_at,last_active) VALUES (?,?,?,?,?,?)",
                (user_id, username, first_name, "uz", now_str, now_str))
            conn.commit()
            is_banned, lang = False, "uz"
        else:
            is_banned, lang = bool(row[0]), row[1]
        if is_banned:
            return True, False, lang
        c.execute("SELECT last_req FROM rate_limits WHERE user_id=?", (user_id,))
        rr = c.fetchone()
        if rr and now_ts - rr[0] < RATE_LIMIT_SEC:
            return False, False, lang
        c.execute("INSERT OR REPLACE INTO rate_limits (user_id, last_req) VALUES (?,?)", (user_id, now_ts))
        c.execute("UPDATE users SET last_active=?,username=?,first_name=? WHERE user_id=?",
                  (now_str, username, first_name, user_id))
        conn.commit()
        return False, True, lang

def _task_done_cb(name: str):
    def cb(t: asyncio.Task):
        if not t.cancelled() and t.exception():
            logger.error(f"Background task '{name}' failed: {t.exception()}")
    return cb

def safe_task(coro, name: str = "task"):
    """Exception lari logga tushadigan background task"""
    t = asyncio.create_task(coro)
    t.add_done_callback(_task_done_cb(name))
    return t

async def cache_to_channel(client, file_path: str, media_type: str, **kwargs) -> tuple:
    """Kanalga yuborish va (file_id, real_type) qaytarish"""
    try:
        if media_type == "audio":
            msg = await client.send_audio(CACHE_CHANNEL, file_path, **kwargs)
            if msg.audio: return msg.audio.file_id, "audio"
        elif media_type == "video":
            msg = await client.send_video(CACHE_CHANNEL, file_path, **kwargs)
            if msg.video: return msg.video.file_id, "video"
            if msg.animation: return msg.animation.file_id, "animation"
        elif media_type == "photo":
            msg = await client.send_photo(CACHE_CHANNEL, file_path, **kwargs)
            if msg.photo: return msg.photo.file_id, "photo"
    except Exception as e:
        logger.error(f"cache_to_channel: {e}")
    return None, None

async def bg_cache(client, file_path, media_type, url, loop, **kwargs):
    """Background da kanalga yuborish va DB ga saqlash"""
    try:
        await asyncio.sleep(1)
        kwargs.pop("thumb", None)
        fid, ftype = await cache_to_channel(client, file_path, media_type, **kwargs)
        if fid:
            await loop.run_in_executor(None, lambda: db_set_url_cache(url, fid, ftype or media_type))
    except Exception as e:
        logger.error(f"bg_cache: {e}")

async def reply_cached(msg, fid, ftype, **kwargs):
    """Keshlangan media ni togri method bilan yuborish"""
    try:
        if ftype == "audio":
            return await msg.reply_audio(fid, **kwargs)
        elif ftype == "animation":
            return await msg.reply_animation(fid, **kwargs)
        elif ftype == "photo":
            return await msg.reply_photo(fid, **kwargs)
        else:
            return await msg.reply_video(fid, **kwargs)
    except Exception as e:
        logger.error(f"reply_cached {ftype}: {e}")
        try:
            return await msg.reply_document(fid, **kwargs)
        except Exception:
            pass


db_init()

# ─── CACHES ───────────────────────────────────────────────────────────────────

from collections import OrderedDict

class BoundedDict(OrderedDict):
    """LRU cache — eng ko'p ishlatiladigan elementlar saqlanadi"""
    def __init__(self, maxsize=1000):
        super().__init__()
        self.maxsize = maxsize

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.maxsize:
            self.popitem(last=False)

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

user_modes:        Dict[int, str] = {}
track_cache:       BoundedDict    = BoundedDict(TRACK_CACHE_MAX)
track_cache_time:  Dict[str, float] = {}
_youtube_url_cache: BoundedDict   = BoundedDict(200)
media_cache:       BoundedDict    = BoundedDict(MEDIA_CACHE_MAX)
media_cache_time:  Dict[str, float] = {}
user_last_media:   Dict[int, str] = {}
_url_media_cache:  BoundedDict    = BoundedDict(500)
_deezer_cache:     BoundedDict    = BoundedDict(200)
user_semaphores:   Dict[int, asyncio.Semaphore] = {}
_sem_lock = asyncio.Lock()

async def get_semaphore(user_id: int) -> asyncio.Semaphore:
    async with _sem_lock:
        if user_id not in user_semaphores:
            user_semaphores[user_id] = asyncio.Semaphore(4)
        return user_semaphores[user_id]

def _get_url_cache(url: str):
    entry = _url_media_cache.get(url)
    if entry and time.time() - entry[2] < URL_CACHE_TTL:
        return entry[0], entry[1]
    return None, None

def _set_url_cache(url: str, media_id: str, media_type: str):
    _url_media_cache[url] = (media_id, media_type, time.time())

# ─── HELPERS ──────────────────────────────────────────────────────────────────

async def keep_action(client, chat_id, action, stop_event):
    """Chat action ni upload tugaguncha har 4 sekundda takrorlaydi"""
    while not stop_event.is_set():
        try:
            await client.send_chat_action(chat_id, action)
        except Exception: pass
        await asyncio.sleep(4)

def catch_errors(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            logger.warning(f"FloodWait {e.value}s in {func.__name__}")
            await asyncio.sleep(e.value)
            try:
                return await func(*args, **kwargs)
            except Exception as e2:
                logger.error(f"{func.__name__} retry: {e2}")
        except MessageNotModified:
            pass
        except Exception as e:
            logger.error(f"{func.__name__}: {e}\n{traceback.format_exc()}")
            if args and isinstance(args[0], CallbackQuery):
                try: await args[0].answer("❌", show_alert=True)
                except Exception: pass
    return wrapper

def get_user_media_dir(user_id: int) -> Path:
    d = MEDIA_STORAGE / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d

def extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/v/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def extract_shorts_id(url: str) -> Optional[str]:
    m = re.search(r"(?:youtube\.com/shorts/|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else None
def extract_spotify_id(url: str) -> Optional[str]:
    m = re.search(r"open\.spotify\.com/track/([a-zA-Z0-9]+)", url)
    return m.group(1) if m else None

def format_duration(seconds: int) -> str:
    return f"{seconds//60}:{seconds%60:02d}" if seconds else "?:??"

def format_size(size: int) -> str:
    if not size: return ""
    if size < 1024**2: return f"{size/1024:.1f}KB"
    if size < 1024**3: return f"{size/1024**2:.1f}MB"
    return f"{size/1024**3:.1f}GB"

def _get_audio_duration(path) -> int:
    try:
        r = subprocess.run(
            ["ffprobe","-v","quiet","-print_format","json","-show_streams",str(path)],
            capture_output=True, text=True, timeout=10
        )
        for s in json.loads(r.stdout).get("streams", []):
            d = s.get("duration")
            if d: return int(float(d))
    except Exception: pass
    return 0

def _get_video_meta(path: Path) -> Tuple[int, int, int, Optional[str]]:
    w, h, dur, thumb = 0, 0, 0, None
    try:
        probe = subprocess.run(
            ["ffprobe","-v","quiet","-print_format","json","-show_streams",str(path)],
            capture_output=True, text=True, timeout=10
        )
        for s in json.loads(probe.stdout).get("streams", []):
            if s.get("codec_type") == "video":
                w   = int(s.get("width", 0))
                h   = int(s.get("height", 0))
                dur = int(float(s.get("duration", 0)))
                break
    except Exception: pass
    try:
        tp = path.parent / f"_th_{path.stem}.jpg"
        subprocess.run(
            ["ffmpeg","-i",str(path),"-ss","00:00:01","-vframes","1","-vf","scale=320:-1",str(tp),"-y"],
            capture_output=True, timeout=10
        )
        if tp.exists() and tp.stat().st_size > 0:
            thumb = str(tp)
    except Exception: pass
    return w, h, dur, thumb

def _save_media(uid: int, src: Path, media_type: str, title: str = "") -> Tuple[str, Path]:
    media_dir = get_user_media_dir(uid)
    prefix = "audio" if media_type == "audio" else "video"
    final  = media_dir / f"{prefix}_{uuid.uuid4().hex[:8]}{src.suffix}"
    shutil.move(str(src), str(final))
    media_id = uuid.uuid4().hex[:8]
    media_cache[media_id]      = (media_type, final, 0, uid, None, title)
    media_cache_time[media_id] = time.time()
    user_last_media[uid]       = media_id
    return media_id, final

def _update_file_id(media_id: str, msg):
    info = media_cache.get(media_id)
    if not info: return
    file_id = None
    if msg.video:      file_id = msg.video.file_id
    elif msg.animation: file_id = msg.animation.file_id
    elif msg.audio:    file_id = msg.audio.file_id
    elif msg.photo:    file_id = msg.photo.file_id
    elif msg.document: file_id = msg.document.file_id
    if file_id:
        media_cache[media_id] = (info[0], info[1], msg.id, info[3], file_id,
                                  info[5] if len(info) > 5 else "")
        save_file_id(media_id, file_id, info[0])

# ─── KEYBOARDS ────────────────────────────────────────────────────────────────

def _share_kb(media_id: str, lang: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "share"),      switch_inline_query=media_id)],
        [InlineKeyboardButton(t(lang, "shazam_btn"), callback_data=f"shazam:{media_id}"),
         InlineKeyboardButton(t(lang, "audio_btn"),  callback_data=f"extract:{media_id}")]
    ])

def _share_kb_audio(media_id: str, lang: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "share"),      switch_inline_query=media_id)],
        [InlineKeyboardButton(t(lang, "shazam_btn"), callback_data=f"shazam:{media_id}")]
    ])

def audio_format_kb(tid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("MP3",  callback_data=f"mp3:{tid}"),
        InlineKeyboardButton("FLAC", callback_data=f"flac:{tid}"),
    ]])

def track_kb(tracks: List[dict]) -> InlineKeyboardMarkup:
    tids = []
    for track in tracks[:10]:
        tid = uuid.uuid4().hex[:6]
        track_cache[tid]      = track
        track_cache_time[tid] = time.time()
        tids.append(tid)
    row1 = [InlineKeyboardButton(str(i+1), callback_data=f"track:{tids[i]}") for i in range(min(5, len(tids)))]
    row2 = [InlineKeyboardButton(str(i+1), callback_data=f"track:{tids[i]}") for i in range(5, min(10, len(tids)))]
    return InlineKeyboardMarkup([row1] + ([row2] if row2 else []))

# ─── AUDIO FILTER ─────────────────────────────────────────────────────────────

SKIP_WORDS = [
    "remix","cover","mashup","nightcore","slowed","reverb","karaoke",
    "instrumental","acoustic","1 hour","loop","live","concert",
    "fan made","lyric video","lyrics video","visualizer","extended",
    "full album","bass boosted","sped up",
]

def _is_bad_title(title: str) -> bool:
    t_low = title.lower()
    return any(w in t_low for w in SKIP_WORDS)

def _find_audio_file(out_dir: Path, quality: str) -> Optional[Path]:
    direct = out_dir / f"audio.{quality}"
    if direct.exists(): return direct
    for f in out_dir.glob("audio.*"):
        if f.suffix.lstrip(".") in ("mp3","flac","opus","m4a","ogg","webm"):
            return f
    files = [f for f in out_dir.glob("*") if f.is_file()]
    return max(files, key=os.path.getctime) if files else None

# ─── DOWNLOAD AUDIO ───────────────────────────────────────────────────────────

async def download_audio(query: str, quality: str, out_dir: Path,
                         expected_duration: int = 0, client=None, chat_id=None, status_msg=None) -> Optional[Path]:
    loop = asyncio.get_event_loop()
    progress = {"pct": 0}
    def on_progress(pct):
        progress["pct"] = pct
    async def progress_updater():
        last = 0
        while progress["pct"] < 100:
            await asyncio.sleep(1.5)
            p = progress["pct"]
            if status_msg and p > last and p < 100:
                last = p
                bar = "█" * (p // 10) + "░" * (10 - p // 10)
                try:
                    await status_msg.edit_text(f"⏳ Yuklanmoqda...\n{bar} {p}%")
                except Exception: pass
    task = asyncio.create_task(progress_updater()) if status_msg else None
    result = await loop.run_in_executor(
        None, lambda: _download_audio_sync(query, quality, out_dir, expected_duration, on_progress))
    if task:
        progress["pct"] = 100
        task.cancel()
    return result

def _download_audio_sync(query: str, quality: str, out_dir: Path,
                          expected_duration: int = 0, progress_cb=None) -> Optional[Path]:
    try:
        base_opts = {
            **YTDL_BASE,
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio",
                                "preferredcodec": quality,
                                "preferredquality": "192" if quality == "mp3" else "0"}],
            "outtmpl": str(out_dir / "audio.%(ext)s"),
        }
        search_opts = {**base_opts, "skip_download": True}
        dl_opts     = {**base_opts}
        if progress_cb:
            dl_opts["progress_hooks"] = [_make_progress_hook(progress_cb)]

        with yt_dlp.YoutubeDL(search_opts) as ydl:
            info = ydl.extract_info(
                f"ytsearch5:{query} official audio -live -remix -slowed",
                download=False
            )
            if not info or "entries" not in info:
                return None

            best = fallback = None
            for entry in info["entries"]:
                if not entry: continue
                if entry.get("age_limit", 0) >= 18: continue
                title    = entry.get("title", "") or ""
                channel  = (entry.get("channel", "") or "").lower()
                uploader = (entry.get("uploader","") or "").lower()
                if _is_bad_title(title): continue
                if expected_duration > 0:
                    entry_dur = entry.get("duration") or 0
                    if entry_dur and abs(entry_dur - expected_duration) > 25:
                        continue
                combined   = channel + " " + uploader + " " + title.lower()
                is_official = any(x in combined for x in
                    ["vevo","- topic","official audio","official video","records"])
                if is_official and best is None:
                    best = entry
                elif fallback is None:
                    fallback = entry

            target = best or fallback
            if not target: return None

            video_url = target.get("webpage_url") or target.get("url")
            with yt_dlp.YoutubeDL(dl_opts) as ydl_dl:
                ydl_dl.extract_info(video_url, download=True)
            return _find_audio_file(out_dir, quality)
    except Exception as e:
        logger.error(f"download_audio: {e}")
    return None

# ─── DEEZER ───────────────────────────────────────────────────────────────────

def _search_deezer_sync(query: str, limit: int) -> List[dict]:
    try:
        r = requests.get("https://api.deezer.com/search",
                         params={"q": query, "limit": limit}, timeout=8)
        if r.status_code == 200:
            return [{"id": t["id"], "title": t["title"],
                     "artist": t["artist"]["name"],
                     "album":  t["album"]["title"],
                     "duration": t.get("duration", 0),
                     "cover": t["album"]["cover_big"]}
                    for t in r.json().get("data", [])]
    except Exception as e:
        logger.error(f"deezer: {e}")
    return []

async def search_deezer(query: str, limit: int = 10) -> List[dict]:
    key = f"{query}:{limit}"
    cached = _deezer_cache.get(key)
    if cached and time.time() - cached[1] < DEEZER_CACHE_TTL:
        return cached[0]
    loop    = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _search_deezer_sync, query, limit)
    if results:
        _deezer_cache[key] = (results, time.time())
    return results

# ─── VIDEO DOWNLOAD ───────────────────────────────────────────────────────────

INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://inv.us.projectsegfau.lt",
    "https://invidious.privacyredirect.com",
    "https://iv.ggtyler.dev",
    "https://yt.artemislena.eu",
    "https://invidious.fdn.fr",
]

async def download_video(url: str, out_dir: Path, quality: str = None,
                         client=None, chat_id=None, status_msg=None) -> Optional[Tuple[Path, str, str]]:
    loop = asyncio.get_event_loop()
    progress = {"pct": 0}
    def on_progress(pct):
        progress["pct"] = pct
    async def progress_updater():
        last = 0
        while progress["pct"] < 100:
            await asyncio.sleep(1.5)
            p = progress["pct"]
            if status_msg and p > last and p < 100:
                last = p
                bar = "█" * (p // 10) + "░" * (10 - p // 10)
                try:
                    await status_msg.edit_text(f"⏳ Yuklanmoqda...\n{bar} {p}%")
                except Exception: pass
    task = asyncio.create_task(progress_updater()) if status_msg else None
    result = await loop.run_in_executor(
        None, lambda: _download_video_sync(url, out_dir, quality, on_progress))
    if task:
        progress["pct"] = 100
        task.cancel()
    return result

def _download_video_sync(url: str, out_dir: Path,
                          quality: str = None, progress_cb=None) -> Optional[Tuple[Path, str, str]]:
    import re as _re
    try:
        is_youtube = "youtube.com" in url or "youtu.be" in url
        is_shorts  = "youtube.com/shorts/" in url

        # ── FORMAT STRING ────────────────────────────────────────────
        if is_youtube:
            if is_shorts:
                fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            elif quality and quality != "audio":
                fmt = (f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]"
                       f"/bestvideo[height<={quality}]+bestaudio/best")
            elif quality == "audio":
                fmt = "bestaudio[ext=m4a]/bestaudio/best"
            else:
                fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        else:
            fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

        opts = {
            **YTDL_BASE,
            "format": fmt,
            "outtmpl": str(out_dir / "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "ignoreerrors": False,
        }
        if quality == "audio":
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                        "preferredcodec": "mp3", "preferredquality": "192"}]
        if progress_cb:
            opts["progress_hooks"] = [_make_progress_hook(progress_cb)]

        # ── 1. YT-DLP (ASOSIY) ───────────────────────────────────────
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info: raise Exception("no info")
                fname = ydl.prepare_filename(info)
                if fname and not fname.endswith('.mp4') and quality != "audio":
                    fname = _re.sub(r'\.[^.]+$', '.mp4', fname)
                if not os.path.exists(fname):
                    files = list(out_dir.glob("*"))
                    fname = str(max(files, key=os.path.getctime)) if files else None
                if not fname: raise Exception("no file")
                site_map = {"youtube": "YouTube", "tiktok": "TikTok",
                            "instagram": "Instagram", "twitter": "Twitter",
                            "facebook": "Facebook", "vimeo": "Vimeo"}
                extractor = (info.get("extractor_key") or "").lower()
                site  = next((v for k, v in site_map.items() if k in extractor),
                             info.get("webpage_url_domain", "Video"))
                title = info.get("title", "") or ""
                return Path(fname), site, title
        except Exception as e:
            err = str(e).lower()
            logger.warning(f"yt-dlp failed: {e}")
            # yt-dlp xato bo'lsa Invidious fallback ga o'tamiz
            if not is_youtube:
                raise

        # ── 2. INVIDIOUS FALLBACK (faqat YouTube) ────────────────────
        vid_id = extract_video_id(url)
        if not vid_id:
            return None

        for instance in INVIDIOUS_INSTANCES:
            try:
                r = requests.get(f"{instance}/api/v1/videos/{vid_id}",
                                  timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code != 200: continue
                data    = r.json()
                title   = data.get("title", "")
                # Progressive streamlar (video+audio birlashgan)
                prog_streams = data.get("formatStreams", [])
                adap_streams = data.get("adaptiveFormats", [])

                video_url = audio_url = None

                if quality and quality != "audio":
                    # Avval progressive (birlashgan) stream qidirish
                    for s in prog_streams:
                        if str(quality) in s.get("qualityLabel", "") and s.get("url"):
                            video_url = s["url"]; break
                    # Topilmasa eng yuqori progressive
                    if not video_url:
                        for s in reversed(prog_streams):
                            if s.get("url"):
                                video_url = s["url"]; break
                    # Hali topilmasa adaptive video + alohida audio
                    if not video_url:
                        for s in adap_streams:
                            if str(quality) in s.get("qualityLabel","") and "video" in s.get("type",""):
                                video_url = s["url"]; break
                        if not video_url:
                            for s in reversed(adap_streams):
                                if "video" in s.get("type","") and s.get("url"):
                                    video_url = s["url"]; break
                        for s in adap_streams:
                            if "audio" in s.get("type","") and s.get("url"):
                                audio_url = s["url"]; break
                else:
                    # Eng yuqori progressive stream
                    for s in reversed(prog_streams):
                        if s.get("url"):
                            video_url = s["url"]; break

                if not video_url: continue

                def _dl_stream(stream_url, out_path):
                    resp = requests.get(stream_url, stream=True, timeout=120,
                                        headers={"User-Agent": "Mozilla/5.0"})
                    if resp.status_code != 200:
                        raise Exception(f"HTTP {resp.status_code}")
                    with open(out_path, "wb") as f:
                        for chunk in resp.iter_content(65536): f.write(chunk)

                vid_path = out_dir / f"inv_v_{vid_id}.mp4"
                _dl_stream(video_url, vid_path)

                # Audio alohida bo'lsa — FFmpeg bilan birlashtirish
                if audio_url:
                    aud_path = out_dir / f"inv_a_{vid_id}.m4a"
                    _dl_stream(audio_url, aud_path)
                    merged = out_dir / f"inv_{vid_id}_merged.mp4"
                    ret = subprocess.run(
                        ["ffmpeg", "-i", str(vid_path), "-i", str(aud_path),
                         "-c:v", "copy", "-c:a", "aac", "-strict", "experimental",
                         str(merged), "-y"],
                        capture_output=True, timeout=120
                    )
                    vid_path.unlink(missing_ok=True)
                    aud_path.unlink(missing_ok=True)
                    if merged.exists() and merged.stat().st_size > 0:
                        return merged, "YouTube", title
                else:
                    if vid_path.exists() and vid_path.stat().st_size > 0:
                        return vid_path, "YouTube", title

            except Exception as inv_e:
                logger.warning(f"Invidious {instance}: {inv_e}")
                continue

        return None
    except Exception as e:
        logger.error(f"download_video: {e}")
        return None

async def download_tiktok_video(url: str, out_dir: Path) -> Optional[Tuple[Path, str, str]]:
    result = await download_video(url, out_dir)
    if result: return result
    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: requests.get(f"https://www.tikwm.com/api/?url={url}&hd=1",
                                  headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data") and data["data"].get("hdplay"):
                out_f = out_dir / "tiktok.mp4"
                r = requests.get(data["data"]["hdplay"], stream=True, timeout=30)
                if r.status_code == 200:
                    with open(out_f, "wb") as f:
                        for chunk in r.iter_content(8192): f.write(chunk)
                    return out_f, "TikTok", ""
    except Exception as e:
        logger.error(f"tiktok api: {e}")
    return None

async def download_tiktok_slideshow(url: str, out_dir: Path) -> Optional[dict]:
    """TikTok slideshow: rasmlar + audio"""
    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: requests.get(f"https://www.tikwm.com/api/?url={url}&hd=1",
                                  headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", {})
        images = data.get("images", [])
        if not images:
            return None
        img_paths = []
        for i, img_url in enumerate(images):
            try:
                r = requests.get(img_url, timeout=15)
                if r.status_code == 200:
                    p = out_dir / f"slide_{i}.jpg"
                    p.write_bytes(r.content)
                    img_paths.append(p)
            except Exception:
                pass
        audio_path = None
        music_url = data.get("music", "")
        if music_url:
            try:
                r = requests.get(music_url, stream=True, timeout=20)
                if r.status_code == 200:
                    audio_path = out_dir / "tiktok_audio.mp3"
                    with open(audio_path, "wb") as f:
                        for chunk in r.iter_content(8192): f.write(chunk)
            except Exception:
                pass
        if img_paths:
            return {"images": img_paths, "audio": audio_path, "title": data.get("title", "")}
    except Exception as e:
        logger.error(f"tiktok slideshow: {e}")
    return None

# ─── GALLERY-DL ───────────────────────────────────────────────────────────────

GALLERY_SKIP_DOMAINS = ["imdb.com", "ok.ru", "odnoklassniki.ru"]

async def download_gallery(url: str, out_dir: Path, client=None, chat_id=None,
                           original_msg=None, lang="uz") -> bool:
    if any(d in url for d in GALLERY_SKIP_DOMAINS):
        return False
    try:
        subprocess.run(
            ["gallery-dl","--cookies",COOKIES_FILE,"--dest",str(out_dir),"--no-mtime","-q",url],
            capture_output=True, text=True, timeout=30
        )
        files = sorted([f for f in out_dir.rglob("*") if f.is_file()], key=os.path.getctime)
        if not files: return False
        # Webp -> JPG convert
        for f in files:
            if f.suffix.lower() == ".webp":
                jpg = f.with_suffix(".jpg")
                try:
                    subprocess.run(["ffmpeg","-i",str(f),"-q:v","1",str(jpg),"-y"],
                        capture_output=True, timeout=15)
                    if jpg.exists() and jpg.stat().st_size > 0:
                        f.unlink()
                except Exception: pass
        files = sorted([f for f in out_dir.rglob("*") if f.is_file()], key=os.path.getctime)
        images    = [f for f in files if f.suffix.lower() in (".jpg",".jpeg",".png",".gif")]
        videos    = [f for f in files if f.suffix.lower() in (".mp4",".webm",".mov")]
        all_media = images + videos
        if not all_media: return False

        from pyrogram.types import InputMediaPhoto, InputMediaVideo
        is_social  = any(d in url.lower() for d in ["tiktok","twitter.com","x.com"])
        actual_uid = chat_id
        media_dir  = get_user_media_dir(actual_uid)
        cap = t(lang, "caption")

        loop_gal = asyncio.get_event_loop()
        for i in range(0, len(all_media), 10):
            batch        = all_media[i:i+10]
            reply_target = original_msg or client
            if len(batch) == 1:
                f = batch[0]
                if f.suffix.lower() in (".mp4",".mov",".webm"):
                    mid  = uuid.uuid4().hex[:8]
                    perm = media_dir / f"video_{mid}{f.suffix}"
                    await loop_gal.run_in_executor(None, shutil.copy2, str(f), str(perm))
                    media_cache[mid]      = ("video", perm, 0, actual_uid, None, "")
                    media_cache_time[mid] = time.time()
                    kb   = _share_kb(mid, lang)
                    sent = await reply_target.reply_video(str(f), caption=cap, supports_streaming=True, reply_markup=kb, quote=True)
                    _update_file_id(mid, sent)
                elif f.suffix.lower() == ".gif":
                    mid  = uuid.uuid4().hex[:8]
                    perm = media_dir / f"gif_{mid}{f.suffix}"
                    await loop_gal.run_in_executor(None, shutil.copy2, str(f), str(perm))
                    media_cache[mid]      = ("video", perm, 0, actual_uid, None, "")
                    media_cache_time[mid] = time.time()
                    kb   = _share_kb(mid, lang) if is_social else InlineKeyboardMarkup([[InlineKeyboardButton(t(lang,"share"), switch_inline_query=mid)]])
                    sent = await reply_target.reply_animation(str(f), caption=cap, reply_markup=kb, quote=True)
                    _update_file_id(mid, sent)
                else:
                    mid  = uuid.uuid4().hex[:8]
                    perm = media_dir / f"photo_{mid}{f.suffix}"
                    await loop_gal.run_in_executor(None, shutil.copy2, str(f), str(perm))
                    media_cache[mid]      = ("photo", perm, 0, actual_uid, None, "")
                    media_cache_time[mid] = time.time()
                    kb   = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang,"share"), switch_inline_query=mid)]])
                    sent = await reply_target.reply_photo(str(f), caption=cap, reply_markup=kb, quote=True)
                    _update_file_id(mid, sent)
            else:
                media_group = []
                for idx, f in enumerate(batch):
                    c2 = cap if idx == 0 else ""
                    if f.suffix.lower() in (".mp4",".mov",".webm"):
                        media_group.append(InputMediaVideo(str(f), caption=c2))
                    else:
                        media_group.append(InputMediaPhoto(str(f), caption=c2))
                sent_group = await reply_target.reply_media_group(media_group, quote=True)
                group_mid  = uuid.uuid4().hex[:8]
                fid = sent_group[0].photo.file_id if sent_group and sent_group[0].photo else None
                media_cache[group_mid]      = ("photo", Path(), 0, actual_uid, fid, "")
                media_cache_time[group_mid] = time.time()
                if fid: save_file_id(group_mid, fid, "photo")
                await reply_target.reply_text("⬆️", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang,"share"), switch_inline_query=group_mid)]]), quote=True)
        return True
    except Exception as e:
        logger.error(f"gallery-dl: {e}")
        try:
            return len([f for f in out_dir.rglob("*") if f.is_file()]) > 0
        except Exception:
            return False

# ─── SPOTIFY ──────────────────────────────────────────────────────────────────

async def get_spotify_track_info(track_id: str) -> Optional[Dict]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
               "Accept-Language": "en-US,en;q=0.9"}
    loop = asyncio.get_event_loop()
    for attempt in range(3):
        try:
            r = await loop.run_in_executor(
                None,
                lambda: requests.get(f"https://open.spotify.com/track/{track_id}",
                                     headers=headers, timeout=10)
            )
            if r.status_code == 200 and "<meta property=\"og:title\"" in r.text:
                title_m  = re.search(r"<meta property=\"og:title\" content=\"([^\"]+)\"", r.text)
                artist_m = re.search(r"<meta property=\"og:description\" content=\"([^\"]+)\"", r.text)
                cover_m  = re.search(r"<meta property=\"og:image\" content=\"([^\"]+)\"", r.text)
                title  = title_m.group(1).replace(" - song by","").replace(" | Spotify","").strip() if title_m else None
                artist = None
                if artist_m:
                    txt    = artist_m.group(1)
                    artist = txt.split("\xb7")[0].strip() if "\xb7" in txt else txt
                cover_url = cover_m.group(1) if cover_m else None
                if title and artist:
                    return {"title": title, "artist": artist,
                            "query": f"{artist} {title}", "cover": cover_url}
        except Exception as e:
            logger.error(f"spotify: {e}")
        await asyncio.sleep(1.5 * (attempt + 1))
    return None

# ─── SHAZAM (serverda to'g'ridan) ─────────────────────────────────────────────

async def shazam_audio(audio_path: Path) -> Optional[Dict]:
    try:
        from shazamio import Shazam
        shazam = Shazam()
        out    = await shazam.recognize(str(audio_path))
        track  = out.get("track", {})
        title  = track.get("title", "")
        artist = track.get("subtitle", "")
        if title:
            return {"title": title, "artist": artist}
    except Exception as e:
        logger.error(f"shazam: {e}")
    return None

def extract_audio_from_video(video_path: Path, out_path: Path, seconds: int = 25) -> Optional[Path]:
    try:
        cmd = ["ffmpeg","-i",str(video_path),"-t",str(seconds),
               "-q:a","0","-map","a?",str(out_path),"-y"]
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        return out_path if out_path.exists() and out_path.stat().st_size > 0 else None
    except Exception as e:
        logger.error(f"ffmpeg extract: {e}")
        return None

# ─── YOUTUBE QUALITY KB ───────────────────────────────────────────────────────

async def youtube_quality_kb(vid: str, url: str, lang: str = "uz") -> InlineKeyboardMarkup:
    # Standart sifat tugmalari (yt-dlp ga murojaat qilmaydi)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1080p", callback_data=f"yt:1080:{vid}"),
         InlineKeyboardButton("720p", callback_data=f"yt:720:{vid}")],
        [InlineKeyboardButton("480p", callback_data=f"yt:480:{vid}"),
         InlineKeyboardButton("audio", callback_data=f"yt:audio:{vid}")]
    ])

# ─── FORCE SUB ────────────────────────────────────────────────────────────────

async def check_force_sub(c: Client, user_id: int) -> bool:
    if user_id in ADMIN_IDS: return True
    loop     = asyncio.get_event_loop()
    channels = await loop.run_in_executor(None, db_get_force_channels)
    if not channels: return True
    from pyrogram.enums import ChatMemberStatus
    from pyrogram.errors import UserNotParticipant, ChatAdminRequired, ChannelPrivate
    ok_statuses = (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    for ch in channels:
        try:
            member = await c.get_chat_member(ch, user_id)
            if member.status not in ok_statuses:
                return False
        except UserNotParticipant:
            return False
        except (ChatAdminRequired, ChannelPrivate):
            continue
        except Exception as e:
            logger.error(f"force_sub {ch}: {e}")
            continue
    return True

async def send_force_sub(c: Client, m: Message, lang: str):
    loop     = asyncio.get_event_loop()
    channels = await loop.run_in_executor(None, db_get_force_channels)
    if not channels: return
    from pyrogram.enums import ChatMemberStatus
    ok_statuses = (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    buttons = []
    for ch in channels:
        ch_clean = ch if ch.startswith("@") else "@" + ch
        link = f"https://t.me/{ch_clean.lstrip('@')}"
        try:
            member = await c.get_chat_member(ch, m.from_user.id)
            if member.status in ok_statuses: continue
        except Exception: pass
        buttons.append([InlineKeyboardButton(ch_clean, url=link)])
    buttons.append([InlineKeyboardButton(t(lang, "check_btn"), callback_data="forcesub_check")])
    await m.reply_text(t(lang, "force_sub"), reply_markup=InlineKeyboardMarkup(buttons), quote=True)

# ─── APP ──────────────────────────────────────────────────────────────────────

app = Client("qulay_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def admin_filter(_, __, m):
    uid = m.from_user.id if hasattr(m, "from_user") and m.from_user else None
    return uid in ADMIN_IDS

admin_f = filters.create(admin_filter)

# ─── CLEANUP ──────────────────────────────────────────────────────────────────

async def cache_cleanup_loop():
    while True:
        try:
            await asyncio.sleep(300)
            now = time.time()
            for k in [k for k, ts in list(track_cache_time.items()) if now - ts > 3600]:
                track_cache.pop(k, None); track_cache_time.pop(k, None)
            for k in [k for k, ts in list(media_cache_time.items()) if now - ts > 3600]:
                info = media_cache.pop(k, None); media_cache_time.pop(k, None)
                if info and info[1] and isinstance(info[1], Path):
                    try: info[1].unlink(missing_ok=True)
                    except Exception: pass
            for k in [k for k, v in list(_deezer_cache.items()) if now - v[1] > DEEZER_CACHE_TTL]:
                _deezer_cache.pop(k, None)
            stale = [uid for uid in list(user_last_media) if uid not in media_cache_time]
            for uid in stale[:200]:
                user_last_media.pop(uid, None)
            idle = [uid for uid, sem in list(user_semaphores.items())
                    if not sem.locked() and uid not in user_last_media]
            for uid in idle[:100]:
                user_semaphores.pop(uid, None)
            try:
                cutoff = now - 86400
                for user_dir in MEDIA_STORAGE.iterdir():
                    if not user_dir.is_dir(): continue
                    for f in user_dir.iterdir():
                        try:
                            if f.is_file() and f.stat().st_mtime < cutoff:
                                f.unlink(missing_ok=True)
                        except Exception: pass
            except Exception: pass
        except Exception as e:
            logger.error(f"cache_cleanup_loop error: {e}")

async def temp_cleanup_loop():
    """Har 6 soatda 1 soatdan eski tmp papkalarni tozalash"""
    while True:
        try:
            await asyncio.sleep(6 * 3600)
            now = time.time()
            for item in TEMP_BASE.iterdir():
                try:
                    if item.is_dir() and now - item.stat().st_mtime > 3600:
                        shutil.rmtree(item, ignore_errors=True)
                        logger.info(f"Cleaned old tmp: {item.name}")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"temp_cleanup_loop error: {e}")

async def temp_cleanup():
    try:
        for item in TEMP_BASE.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
        logger.warning("Temp cleanup done")
    except Exception: pass

# ─── SHAZAM CORE ──────────────────────────────────────────────────────────────

async def _do_shazam(c: Client, uid: int, media_id: str,
                     reply_to, cb_message=None, lang="uz") -> None:
    media_info = media_cache.get(media_id)
    if not media_info:
        await reply_to.reply_text(t(lang,"media_not_found"), quote=True); return
    media_type = media_info[0]
    media_path = media_info[1]
    if not media_path or not media_path.exists():
        await reply_to.reply_text(t(lang,"file_not_found"), quote=True); return
    sem = await get_semaphore(uid)
    if sem.locked():
        await reply_to.reply_text(t(lang,"wait"), quote=True); return
    await sem.acquire()
    tmp = TEMP_BASE / f"shazam_{uid}_{uuid.uuid4().hex[:6]}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        chat_id = reply_to.chat.id if hasattr(reply_to,"chat") else cb_message.chat.id
        await c.send_chat_action(chat_id, ChatAction.TYPING)
        if media_type == "video":
            sample     = tmp / "sample.mp3"
            audio_path = extract_audio_from_video(media_path, sample)
            if not audio_path:
                await reply_to.reply_text(t(lang,"audio_extract_fail"), quote=True)
                return
        else:
            audio_path = media_path
        res = await shazam_audio(audio_path)
        if res:
            artist = res.get("artist","")
            title  = res.get("title","")
            deezer = await search_deezer(f"{artist} {title}", 1)
            track  = deezer[0] if deezer else {
                "title": title, "artist": artist, "album":"", "duration":0, "cover":None
            }
            tid = uuid.uuid4().hex[:6]
            track_cache[tid]      = track
            track_cache_time[tid] = time.time()
            text = f"{artist} - {title}"
            if track.get("album"): text += f"\n{track['album']}"
            await reply_to.reply_text(text, reply_markup=audio_format_kb(tid), quote=True)
        else:
            await reply_to.reply_text(t(lang,"shazam_fail"), quote=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        sem.release()

# ─── COMMANDS ─────────────────────────────────────────────────────────────────

@app.on_message(filters.command("start"))
@catch_errors
async def start_cmd(c: Client, m: Message):
    uid     = m.from_user.id
    tg_lang = (m.from_user.language_code or "uz").lower()[:2]
    lang    = TG_LANG_MAP.get(tg_lang, "uz")
    loop    = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: db_user(
        uid, m.from_user.username, m.from_user.first_name, lang
    ))
    await m.reply_text(t(lang,"start"), reply_markup=lang_kb(), quote=True)

@app.on_message(filters.command("lang"))
@catch_errors
async def lang_cmd(_, m: Message):
    lang = await asyncio.get_event_loop().run_in_executor(None, db_get_lang, m.from_user.id)
    await m.reply_text(t(lang,"select_lang"), reply_markup=lang_kb(), quote=True)

@app.on_callback_query(filters.regex(r"^lang:(uz|ru|en|tr)$"))
@catch_errors
async def lang_cb(_, cb: CallbackQuery):
    lang = cb.matches[0].group(1)
    uid  = cb.from_user.id
    await asyncio.get_event_loop().run_in_executor(None, lambda: db_set_lang(uid, lang))
    await cb.answer(t(lang,"lang_set"))
    try: await cb.message.edit_text(t(lang,"lang_set"))
    except Exception: pass

@app.on_message(filters.command("imkoniyatlar"))
@catch_errors
async def imkoniyatlar_cmd(_, m: Message):
    lang = await asyncio.get_event_loop().run_in_executor(None, db_get_lang, m.from_user.id)
    await m.reply_text(t(lang,"capabilities"), parse_mode=enums.ParseMode.HTML, quote=True)

# ─── TEXT HANDLER ─────────────────────────────────────────────────────────────

@app.on_message(
    filters.text
    & ~filters.command(["start","lang","imkoniyatlar","admin",
                        "broadcast","ban","unban","user_info","setchannel"])
    & ~filters.bot
)
@catch_errors
async def text_handler(c: Client, m: Message):
    if not m.from_user:
        return
    uid  = m.from_user.id
    loop = asyncio.get_event_loop()
    is_banned, rate_ok, lang = await loop.run_in_executor(
        None, lambda: db_check_user_status(uid, m.from_user.username, m.from_user.first_name))
    if is_banned:
        await m.reply_text(t(lang,"banned"), quote=True); return
    if not rate_ok:
        await m.reply_text(t(lang,"rate"), quote=True); return
    if not await check_force_sub(c, uid):
        await send_force_sub(c, m, lang); return
    text = m.text.strip()
    if re.match(r"https?://", text):
        await handle_url(c, m, text, lang)
    else:
        await handle_search(c, m, text, lang)

# ─── URL HANDLER ──────────────────────────────────────────────────────────────

async def handle_url(c: Client, m: Message, url: str, lang: str = "uz"):
    uid     = m.from_user.id
    sem     = await get_semaphore(uid)
    try:
        await asyncio.wait_for(sem.acquire(), timeout=5)
    except asyncio.TimeoutError:
        await m.reply_text(t(lang,"wait"), quote=True); return
    tmp = TEMP_BASE / f"tmp_{uid}_{uuid.uuid4().hex[:6]}"
    tmp.mkdir(parents=True, exist_ok=True)
    chat_id = m.chat.id
    loop    = asyncio.get_event_loop()
    cap     = t(lang,"caption")
    stop_action = asyncio.Event()
    action_task = None
    try:
        # Persistent URL cache
        cached = await loop.run_in_executor(None, db_get_url_cache, url)
        is_yt_url = "youtube.com" in url or "youtu.be" in url
        if cached and not is_yt_url:
            mid = uuid.uuid4().hex[:8]
            fid, ftype = cached["file_id"], cached["type"]
            media_cache[mid] = (ftype, None, 0, uid, fid, cached.get("title",""))
            media_cache_time[mid] = time.time()
            try:
                if ftype == "audio":
                    await m.reply_audio(fid, caption=cap, reply_markup=_share_kb_audio(mid, lang), quote=True)
                else:
                    await reply_cached(m, fid, ftype, caption=cap, reply_markup=_share_kb(mid, lang), quote=True)
            except Exception:
                await m.reply_document(fid, caption=cap, quote=True)
            return
        # In-memory cache
        _cached_id, _cached_type = _get_url_cache(url)
        if _cached_id and not is_yt_url:
            _ci = media_cache.get(_cached_id)
            if not _ci:
                disk = await loop.run_in_executor(None, load_file_id, _cached_id)
                if disk: _ci = (disk["type"], None, 0, 0, disk["file_id"], "")
            if _ci and _ci[4]:
                if _cached_type == "audio":
                    await m.reply_audio(_ci[4], caption=cap,
                        reply_markup=_share_kb_audio(_cached_id, lang), quote=True)
                else:
                    await m.reply_video(_ci[4], caption=cap,
                        reply_markup=_share_kb(_cached_id, lang), quote=True)
                return

        # IMDB
        if "imdb.com" in url:
            try:
                r = await loop.run_in_executor(
                    None, lambda: requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
                )
                img_m = re.search(r"<meta property=\"og:image\" content=\"([^\"]+)\"", r.text)
                if img_m:
                    img_r = await loop.run_in_executor(
                        None, lambda: requests.get(img_m.group(1), timeout=10)
                    )
                    if img_r.status_code == 200:
                        img_path = tmp / "imdb.jpg"
                        img_path.write_bytes(img_r.content)
                        mid  = uuid.uuid4().hex[:8]
                        perm = get_user_media_dir(uid) / f"photo_{mid}.jpg"
                        await loop.run_in_executor(None, shutil.copy2, str(img_path), str(perm))
                        media_cache[mid]      = ("photo", perm, 0, uid, None, "")
                        media_cache_time[mid] = time.time()
                        kb   = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang,"share"), switch_inline_query=mid)]])
                        sent = await m.reply_photo(str(img_path), caption=cap, reply_markup=kb, quote=True)
                        _update_file_id(mid, sent)
                        return
            except Exception as e:
                logger.error(f"imdb: {e}")
            await m.reply_text(t(lang,"link_fail"), quote=True); return

        # Direct video
        if re.search(r"\.(mp4|mkv|avi|mov|webm)(\?|$)", url, re.I):
            await c.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
            try:
                r = await loop.run_in_executor(
                    None,
                    lambda: requests.get(url, stream=True, timeout=60,
                                         headers={"User-Agent":"Mozilla/5.0"})
                )
                if r.status_code == 200:
                    direct = tmp / "video.mp4"
                    with open(direct, "wb") as f:
                        for chunk in r.iter_content(65536): f.write(chunk)
                    if direct.stat().st_size > 0:
                        media_id, final = _save_media(uid, direct, "video")
                        msg = await m.reply_video(str(final), caption=cap,
                            supports_streaming=True, reply_markup=_share_kb(media_id, lang), quote=True)
                        _update_file_id(media_id, msg)
                        _set_url_cache(url, media_id, "video")
                        safe_task(bg_cache(c, str(final), "video", url, loop, caption=cap, supports_streaming=True))
                        return
            except Exception as e:
                logger.error(f"direct mp4: {e}")

        # Twitter/X
        if "twitter.com" in url or "x.com" in url:
            action_task = asyncio.create_task(keep_action(c, chat_id, ChatAction.UPLOAD_VIDEO, stop_action))
            result = await download_video(url, tmp)
            if result:
                vpath, *_ = result
                media_id, final = _save_media(uid, vpath, "video")
                msg = await m.reply_video(str(final), caption=cap,
                    supports_streaming=True, reply_markup=_share_kb(media_id, lang), quote=True)
                _update_file_id(media_id, msg)
                _set_url_cache(url, media_id, "video")
                safe_task(bg_cache(c, str(final), "video", url, loop, caption=cap, supports_streaming=True))
            else:
                await m.reply_text(t(lang,"dl_fail"), quote=True)
            return

        # Spotify
        spotify_id = extract_spotify_id(url)
        if spotify_id:
            await c.send_chat_action(chat_id, ChatAction.TYPING)
            track_info = await get_spotify_track_info(spotify_id)
            if track_info:
                await c.send_chat_action(chat_id, ChatAction.UPLOAD_AUDIO)
                audio = await download_audio(track_info["query"], user_modes.get(uid,"mp3"), tmp)
                if audio:
                    media_id, final = _save_media(uid, audio, "audio")
                    thumb = None
                    if track_info.get("cover"):
                        try:
                            cr = await loop.run_in_executor(
                                None, lambda: requests.get(track_info["cover"], timeout=10))
                            if cr.status_code == 200:
                                tp = tmp / "sp_cover.jpg"
                                tp.write_bytes(cr.content)
                                thumb = str(tp)
                        except Exception: pass
                    dur = _get_audio_duration(final)
                    msg = await m.reply_audio(
                        str(final), title=track_info["title"],
                        performer=track_info["artist"], thumb=thumb,
                        duration=dur, caption=cap,
                        reply_markup=_share_kb_audio(media_id, lang), quote=True
                    )
                    _update_file_id(media_id, msg)
                    _set_url_cache(url, media_id, "audio")
                    safe_task(bg_cache(c, str(final), "audio", url, loop,
                        title=track_info["title"], performer=track_info["artist"],
                        thumb=thumb, duration=dur, caption=cap))
                else:
                    await m.reply_text(t(lang,"dl_fail"), quote=True)
            else:
                await m.reply_text(t(lang,"not_found"), quote=True)
            return

        # TikTok
        if "tiktok.com" in url:
            action_task = asyncio.create_task(keep_action(c, chat_id, ChatAction.UPLOAD_VIDEO, stop_action))
            result = await download_tiktok_video(url, tmp)
            if result:
                vpath, *_ = result
                has_video = False
                try:
                    probe = subprocess.run(
                        ["ffprobe","-v","quiet","-print_format","json","-show_streams",str(vpath)],
                        capture_output=True, text=True, timeout=10
                    )
                    for s in json.loads(probe.stdout).get("streams",[]):
                        if s.get("codec_type")=="video" and s.get("avg_frame_rate","0/1")!="0/1":
                            has_video = True; break
                except Exception: pass
                if has_video:
                    media_id, final = _save_media(uid, vpath, "video")
                    msg = await m.reply_video(str(final), caption=cap,
                        supports_streaming=True, reply_markup=_share_kb(media_id, lang), quote=True)
                    _update_file_id(media_id, msg)
                    _set_url_cache(url, media_id, "video")
                    safe_task(bg_cache(c, str(final), "video", url, loop, caption=cap, supports_streaming=True))
                else:
                    # Slideshow bo'lishi mumkin - rasmlarni tekshiramiz
                    slideshow = await download_tiktok_slideshow(url, tmp)
                    if slideshow and slideshow["images"]:
                        from pyrogram.types import InputMediaPhoto
                        imgs = slideshow["images"]
                        for i in range(0, len(imgs), 10):
                            batch = imgs[i:i+10]
                            if len(batch) == 1:
                                await m.reply_photo(str(batch[0]), caption=cap, quote=True)
                            else:
                                media_group = [InputMediaPhoto(str(f), caption=cap if j==0 else "") for j, f in enumerate(batch)]
                                await m.reply_media_group(media_group, quote=True)
                        if slideshow.get("audio") and slideshow["audio"].exists():
                            media_id, final = _save_media(uid, slideshow["audio"], "audio")
                            msg = await m.reply_audio(str(final), caption=cap,
                                reply_markup=_share_kb_audio(media_id, lang), quote=True)
                            _update_file_id(media_id, msg)
                    else:
                        mp3 = tmp / "audio.mp3"
                        subprocess.run(["ffmpeg","-i",str(vpath),"-q:a","0","-map","a",str(mp3),"-y"],
                                       capture_output=True, timeout=60)
                        if mp3.exists() and mp3.stat().st_size > 0:
                            media_id, final = _save_media(uid, mp3, "audio")
                            msg = await m.reply_audio(str(final), caption=cap,
                                reply_markup=_share_kb_audio(media_id, lang), quote=True)
                            _update_file_id(media_id, msg)
                        else:
                            await m.reply_text(t(lang,"dl_fail"), quote=True)
            else:
                # Video yo'q, slideshow tekshirish
                slideshow = await download_tiktok_slideshow(url, tmp)
                if slideshow and slideshow["images"]:
                    from pyrogram.types import InputMediaPhoto
                    imgs = slideshow["images"]
                    for i in range(0, len(imgs), 10):
                        batch = imgs[i:i+10]
                        if len(batch) == 1:
                            await m.reply_photo(str(batch[0]), caption=cap, quote=True)
                        else:
                            media_group = [InputMediaPhoto(str(f), caption=cap if j==0 else "") for j, f in enumerate(batch)]
                            await m.reply_media_group(media_group, quote=True)
                    if slideshow.get("audio") and slideshow["audio"].exists():
                        media_id, final = _save_media(uid, slideshow["audio"], "audio")
                        msg = await m.reply_audio(str(final), caption=cap,
                            reply_markup=_share_kb_audio(media_id, lang), quote=True)
                        _update_file_id(media_id, msg)
                else:
                    await m.reply_text(t(lang,"dl_fail"), quote=True)
            return

        # Instagram
        if "instagram.com" in url or "instagr.am" in url:
            action_task = asyncio.create_task(keep_action(c, chat_id, ChatAction.UPLOAD_VIDEO, stop_action))
            result = await download_video(url, tmp)
            if result:
                vpath, *_ = result
                media_id, final = _save_media(uid, vpath, "video")
                msg = await m.reply_video(str(final), caption=cap,
                    supports_streaming=True, reply_markup=_share_kb(media_id, lang), quote=True)
                _update_file_id(media_id, msg)
                _set_url_cache(url, media_id, "video")
                safe_task(bg_cache(c, str(final), "video", url, loop, caption=cap, supports_streaming=True))
            else:
                # Rasm post - gallery-dl bilan
                await c.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
                if not await download_gallery(url, tmp, c, chat_id, original_msg=m, lang=lang):
                    await m.reply_text(t(lang,"dl_fail"), quote=True)
            return

        # YouTube Shorts - quality menu yoq, avtomatik eng yuqori sifat
        shorts_id = extract_shorts_id(url)
        if shorts_id:
            action_task = asyncio.create_task(keep_action(c, chat_id, ChatAction.UPLOAD_VIDEO, stop_action))
            status_msg = await m.reply_text("⏳ Yuklanmoqda...", quote=True)
            result = await download_video(url, tmp, client=c, chat_id=chat_id, status_msg=status_msg)
            try: await status_msg.delete()
            except Exception: pass
            if result:
                vpath, _, title = result
                media_id, final = _save_media(uid, vpath, "video", title)
                w, h, dur, thumb = _get_video_meta(final)
                try:
                    tr = await loop.run_in_executor(
                        None, lambda: requests.get(
                            f"https://i.ytimg.com/vi/{shorts_id}/hqdefault.jpg", timeout=5))
                    if tr.status_code == 200:
                        th_file = tmp / "thumb.jpg"
                        th_file.write_bytes(tr.content)
                        thumb = str(th_file)
                except Exception: pass
                msg = await m.reply_video(str(final), caption=cap, supports_streaming=True, width=w, height=h, duration=dur, thumb=thumb, reply_markup=_share_kb(media_id, lang), quote=True)
                _update_file_id(media_id, msg)
                _set_url_cache(url, media_id, "video")
                safe_task(bg_cache(c, str(final), "video", url, loop, caption=cap, supports_streaming=True))
                await loop.run_in_executor(None, lambda: db_add_download(uid, url, "YouTube Shorts", "ok"))
            else:
                await m.reply_text(t(lang,"dl_fail"), quote=True)
            return

        # YouTube oddiy video - quality menu
        vid = extract_video_id(url)
        if vid:
            _youtube_url_cache[vid] = url
            await c.send_chat_action(chat_id, ChatAction.TYPING)
            kb = await youtube_quality_kb(vid, url, lang)
            await m.reply_text(t(lang,"quality"), reply_markup=kb, quote=True)
            return

        # gallery-dl
        await c.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
        if await download_gallery(url, tmp, c, chat_id, original_msg=m, lang=lang):
            return

        # Boshqa saytlar
        action_task = asyncio.create_task(keep_action(c, chat_id, ChatAction.UPLOAD_VIDEO, stop_action))
        result = await download_video(url, tmp)
        if result:
            vpath, _, title = result
            media_id, final = _save_media(uid, vpath, "video", title)
            w, h, dur, thumb = _get_video_meta(final)
            msg = await m.reply_video(str(final), caption=cap,
                supports_streaming=True, width=w, height=h, duration=dur,
                thumb=thumb, reply_markup=_share_kb(media_id, lang), quote=True)
            _update_file_id(media_id, msg)
            _set_url_cache(url, media_id, "video")
            safe_task(bg_cache(c, str(final), "video", url, loop,
                caption=cap, supports_streaming=True, width=w, height=h, duration=dur, thumb=thumb))
            await loop.run_in_executor(None, lambda: db_add_download(
                uid, url, url.split("/")[2] if "/" in url else "other", "ok"
            ))
        else:
            await m.reply_text(t(lang,"link_fail"), quote=True)
    finally:
        stop_action.set()
        if action_task and not action_task.done():
            action_task.cancel()
            try:
                await action_task
            except asyncio.CancelledError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)
        sem.release()

# ─── SEARCH HANDLER ───────────────────────────────────────────────────────────

async def handle_search(c: Client, m: Message, query: str, lang: str = "uz"):
    uid = m.from_user.id
    sem = await get_semaphore(uid)
    if sem.locked():
        await m.reply_text(t(lang,"wait"), quote=True); return
    await sem.acquire()
    try:
        await c.send_chat_action(m.chat.id, ChatAction.TYPING)
        tracks = await search_deezer(query, 10)
        if not tracks:
            await m.reply_text(t(lang,"not_found"), quote=True); return
        lines = []
        for i, tr in enumerate(tracks[:10], 1):
            dur = format_duration(tr["duration"])
            lines.append(f"{i}. <b>{tr['artist']}</b> — {tr['title']}  <code>{dur}</code>")
        text = t(lang, "search_title", query=query, lines="\n".join(lines))
        await m.reply_text(text, reply_markup=track_kb(tracks),
                           parse_mode=enums.ParseMode.HTML, quote=True)
    finally:
        sem.release()

# ─── CALLBACKS ────────────────────────────────────────────────────────────────

@app.on_callback_query(filters.regex(r"^yt:(\d+|audio):([a-zA-Z0-9_-]+)$"))
@catch_errors
async def youtube_quality_cb(c: Client, cb: CallbackQuery):
    quality = cb.matches[0].group(1)
    vid     = cb.matches[0].group(2)
    url     = _youtube_url_cache.get(vid, None)
    if not url:
        await cb.answer("❌ Eski so'rov", show_alert=True); return
    uid  = cb.from_user.id
    lang = await asyncio.get_event_loop().run_in_executor(None, db_get_lang, uid)
    sem  = await get_semaphore(uid)
    if sem.locked():
        await cb.answer(t(lang,"wait"), show_alert=True); return
    await sem.acquire()
    tmp = TEMP_BASE / f"tmp_{uid}_{uuid.uuid4().hex[:6]}"
    tmp.mkdir(parents=True, exist_ok=True)
    await cb.answer()
    chat_id = cb.message.chat.id
    cap = t(lang,"caption")
    try:
        await c.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
        status_msg = await cb.message.reply_text("⏳", quote=True)
        result = await download_video(url, tmp, quality if quality != "audio" else "audio",
                                      client=c, chat_id=chat_id, status_msg=status_msg)
        try: await status_msg.delete()
        except Exception: pass
        if result:
            vpath, *_ = result
            mtype    = "audio" if quality == "audio" else "video"
            media_id, final = _save_media(uid, vpath, mtype)
            if quality == "audio":
                msg = await cb.message.reply_audio(str(final), caption=cap,
                    reply_markup=_share_kb_audio(media_id, lang), quote=True)
                _update_file_id(media_id, msg)
            else:
                w, h, dur, th_local = _get_video_meta(final)
                thumb = None
                try:
                    vid_id = extract_video_id(url)
                    if vid_id:
                        tr = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: requests.get(
                                f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg", timeout=5))
                        if tr.status_code == 200:
                            thumb = tmp / "thumb.jpg"
                            thumb.write_bytes(tr.content)
                    if not thumb and th_local:
                        thumb = Path(th_local)
                except Exception: pass
                msg = await cb.message.reply_video(str(final), caption=cap,
                    supports_streaming=True, width=w, height=h, duration=dur,
                    thumb=str(thumb) if thumb else None,
                    reply_markup=_share_kb(media_id, lang), quote=True)
                _update_file_id(media_id, msg)
                _set_url_cache(url, media_id, "video")
                safe_task(bg_cache(c, str(final), "video", url, asyncio.get_event_loop(),
                    caption=cap, supports_streaming=True))
        else:
            await cb.message.reply_text(t(lang,"dl_fail"), quote=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        sem.release()

@app.on_callback_query(filters.regex(r"^track:([a-f0-9]{6})$"))
@catch_errors
async def track_select_cb(_, cb: CallbackQuery):
    tid   = cb.matches[0].group(1)
    track = track_cache.get(tid)
    if not track:
        await cb.answer("❌ Eski", show_alert=True); return
    new_tid = uuid.uuid4().hex[:6]
    track_cache[new_tid]      = track
    track_cache_time[new_tid] = time.time()
    await cb.message.reply_text(
        f"<b>{track['artist']}</b> — {track['title']}\n"
        f"{track.get('album','')}  <code>{format_duration(track['duration'])}</code>",
        reply_markup=audio_format_kb(new_tid),
        parse_mode=enums.ParseMode.HTML,
        quote=True
    )

@app.on_callback_query(filters.regex(r"^(mp3|flac):([a-f0-9]{6})$"))
@catch_errors
async def download_audio_cb(c: Client, cb: CallbackQuery):
    quality = cb.matches[0].group(1)
    tid     = cb.matches[0].group(2)
    track   = track_cache.get(tid)
    if not track:
        await cb.answer("❌ Eski", show_alert=True); return
    uid  = cb.from_user.id
    lang = await asyncio.get_event_loop().run_in_executor(None, db_get_lang, uid)
    sem  = await get_semaphore(uid)
    if sem.locked():
        await cb.answer(t(lang,"wait"), show_alert=True); return
    await sem.acquire()
    tmp = TEMP_BASE / f"tmp_{uid}_{uuid.uuid4().hex[:6]}"
    tmp.mkdir(parents=True, exist_ok=True)
    await cb.answer()
    chat_id = cb.message.chat.id
    cap = t(lang,"caption")
    track_key = "track:" + track["artist"].lower() + ":" + track["title"].lower() + ":" + quality
    try:
        # Keshdan tekshirish
        loop2 = asyncio.get_event_loop()
        cached = await loop2.run_in_executor(None, load_file_id, track_key)
        if cached and cached.get("file_id"):
            await cb.message.reply_audio(
                cached["file_id"], caption=cap,
                reply_markup=_share_kb_audio(uuid.uuid4().hex[:8], lang), quote=True
            )
            return
        await c.send_chat_action(chat_id, ChatAction.UPLOAD_AUDIO)
        status_msg = await cb.message.reply_text("⏳", quote=True)
        exp_dur = int(track.get("duration") or 0)
        audio = await download_audio(
            f"{track['artist']} {track['title']}", quality, tmp,
            expected_duration=exp_dur, client=c, chat_id=chat_id, status_msg=status_msg
        )
        try: await status_msg.delete()
        except Exception: pass
        if audio:
            media_id, final = _save_media(uid, audio, "audio", track["title"])
            thumb = None
            if track.get("cover"):
                try:
                    r = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: requests.get(track["cover"], timeout=10))
                    if r.status_code == 200:
                        tp = tmp / "cover.jpg"
                        tp.write_bytes(r.content)
                        thumb = str(tp)
                except Exception: pass
            _dur = exp_dur or _get_audio_duration(final)
            msg = await cb.message.reply_audio(
                str(final), title=track["title"], performer=track["artist"],
                thumb=thumb, duration=_dur, caption=cap,
                reply_markup=_share_kb_audio(media_id, lang), quote=True
            )
            _update_file_id(media_id, msg)
            if msg.audio:
                save_file_id(track_key, msg.audio.file_id, "audio")
                safe_task(bg_cache(c, str(final), "audio", track_key, asyncio.get_event_loop(),
                    title=track["title"], performer=track["artist"],
                    duration=_dur, caption=cap))
        else:
            await cb.message.reply_text(t(lang,"dl_fail"), quote=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        sem.release()

@app.on_callback_query(filters.regex(r"^shazam:([a-f0-9]{8})$"))
@catch_errors
async def shazam_button_cb(c: Client, cb: CallbackQuery):
    await cb.answer()
    uid  = cb.from_user.id
    lang = await asyncio.get_event_loop().run_in_executor(None, db_get_lang, uid)
    await _do_shazam(c, uid, cb.matches[0].group(1),
                     reply_to=cb.message, cb_message=cb.message, lang=lang)

@app.on_message(filters.video | filters.audio | filters.voice)
@catch_errors
async def media_handler(c: Client, m: Message):
    if not m.from_user:
        return
    uid  = m.from_user.id
    loop = asyncio.get_event_loop()
    lang = await loop.run_in_executor(None, db_get_lang, uid)
    if not await check_force_sub(c, uid):
        await send_force_sub(c, m, lang); return
    sem  = await get_semaphore(uid)
    if sem.locked():
        await m.reply_text(t(lang,"wait"), quote=True); return
    await sem.acquire()
    media_dir = get_user_media_dir(uid)
    try:
        if m.video:
            file_path  = media_dir / f"video_{uuid.uuid4().hex[:8]}.mp4"
            media_type = "video"; file_id = m.video.file_id
        elif m.audio:
            ext        = (m.audio.file_name or "audio.mp3").rsplit(".",1)[-1]
            file_path  = media_dir / f"audio_{uuid.uuid4().hex[:8]}.{ext}"
            media_type = "audio"; file_id = m.audio.file_id
        else:
            file_path  = media_dir / f"voice_{uuid.uuid4().hex[:8]}.ogg"
            media_type = "audio"; file_id = m.voice.file_id
        await m.download(file_path)
        media_id = uuid.uuid4().hex[:8]
        media_cache[media_id]      = (media_type, file_path, m.id, uid, file_id, "")
        media_cache_time[media_id] = time.time()
        user_last_media[uid]       = media_id
        kb = _share_kb(media_id, lang) if media_type == "video" else _share_kb_audio(media_id, lang)
        await m.reply_text("🔍 Shazam / 🎵 Audio", reply_markup=kb, quote=True)
    finally:
        sem.release()

@app.on_callback_query(filters.regex(r"^extract:([a-f0-9]{8})$"))
@catch_errors
async def extract_audio_cb(c: Client, cb: CallbackQuery):
    media_id = cb.matches[0].group(1)
    uid      = cb.from_user.id
    loop     = asyncio.get_event_loop()
    lang     = await loop.run_in_executor(None, db_get_lang, uid)
    info     = media_cache.get(media_id)
    if not info:
        await cb.answer(t(lang,"media_not_found"), show_alert=True); return
    media_type = info[0]; media_path = info[1]
    if media_type != "video":
        await cb.answer(t(lang,"already_audio"), show_alert=True); return
    if not media_path or not media_path.exists():
        await cb.answer(t(lang,"file_not_found"), show_alert=True); return
    await cb.answer()
    sem = await get_semaphore(uid)
    if sem.locked():
        await cb.message.reply_text(t(lang,"wait"), quote=True); return
    await sem.acquire()
    tmp = TEMP_BASE / f"extract_{uid}_{uuid.uuid4().hex[:6]}"
    tmp.mkdir(parents=True, exist_ok=True)
    cap = t(lang,"caption")
    try:
        await c.send_chat_action(cb.message.chat.id, ChatAction.UPLOAD_AUDIO)
        vid_title = media_path.stem
        for prefix in ["video_","audio_"]:
            vid_title = vid_title.replace(prefix,"")
        vid_title = re.sub(r"[a-f0-9]{8}$","", vid_title).strip("_- ")
        if len(vid_title) < 3:
            vid_title = "Audio " + datetime.now().strftime("%d.%m %H:%M")
        out    = tmp / "audio.mp3"
        result = extract_audio_from_video(media_path, out, seconds=9999)
        if result:
            new_mid = uuid.uuid4().hex[:8]
            media_cache[new_mid]      = ("audio", result, 0, uid, None, vid_title)
            media_cache_time[new_mid] = time.time()
            thumb = None
            try:
                tp = tmp / "thumb_ex.jpg"
                subprocess.run(
                    ["ffmpeg","-i",str(media_path),"-ss","00:00:02","-vframes","1",
                     "-vf","scale=320:-1",str(tp),"-y"],
                    capture_output=True, timeout=10
                )
                if tp.exists() and tp.stat().st_size > 0:
                    thumb = str(tp)
            except Exception: pass
            msg2 = await cb.message.reply_audio(
                str(result), title=vid_title, thumb=thumb, caption=cap,
                reply_markup=_share_kb_audio(new_mid, lang), quote=True
            )
            _update_file_id(new_mid, msg2)
        else:
            await cb.message.reply_text(t(lang,"audio_extract_fail"), quote=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        sem.release()

@app.on_callback_query(filters.regex(r"^forcesub_check$"))
@catch_errors
async def forcesub_check_cb(c: Client, cb: CallbackQuery):
    uid  = cb.from_user.id
    loop = asyncio.get_event_loop()
    lang = await loop.run_in_executor(None, db_get_lang, uid)
    ok   = await check_force_sub(c, uid)
    if ok:
        await cb.answer(t(lang,"joined"), show_alert=True)
        try: await cb.message.delete()
        except Exception: pass
    else:
        await cb.answer(t(lang,"not_joined"), show_alert=True)

# ─── INLINE HANDLER ───────────────────────────────────────────────────────────

@app.on_inline_query()
async def inline_handler(c: Client, iq):
    from pyrogram.types import (InlineQueryResultArticle, InputTextMessageContent,
                                InlineQueryResultCachedVideo, InlineQueryResultCachedAudio,
                                InlineQueryResultCachedDocument, InlineQueryResultCachedPhoto)
    query = iq.query.strip()
    if not query:
        await iq.answer([], cache_time=300); return

    loop = asyncio.get_event_loop()
    lang = await loop.run_in_executor(None, db_get_lang, iq.from_user.id)

    info = media_cache.get(query)
    if not info:
        disk = await loop.run_in_executor(None, load_file_id, query)
        if disk: info = (disk["type"], None, 0, 0, disk["file_id"], "")

    if info:
        media_type = info[0]; file_id = info[4]
        cap = t(lang,"caption")
        if file_id:
            if media_type == "video":
                await iq.answer([InlineQueryResultCachedVideo(
                    video_file_id=file_id, title="Video", caption=cap
                )], cache_time=300)
            elif media_type == "audio":
                await iq.answer([InlineQueryResultCachedAudio(
                    audio_file_id=file_id, caption=cap
                )], cache_time=300)
            elif media_type == "photo":
                await iq.answer([InlineQueryResultCachedPhoto(
                    photo_file_id=file_id, title="Photo", caption=cap
                )], cache_time=300)
            else:
                await iq.answer([InlineQueryResultCachedDocument(
                    document_file_id=file_id, title="File", caption=cap
                )], cache_time=300)
            return

    tracks = await search_deezer(query, 8)
    results = []
    for track in tracks:
        tid = uuid.uuid4().hex[:6]
        track_cache[tid]      = track
        track_cache_time[tid] = time.time()
        results.append(InlineQueryResultArticle(
            title=f"{track['artist']} - {track['title']}",
            description=f"{track['album']} [{format_duration(track['duration'])}]",
            input_message_content=InputTextMessageContent(
                f"{track['artist']} - {track['title']}\n{track['album']}"
            ),
            reply_markup=audio_format_kb(tid),
            thumb_url=track.get("cover")
        ))
    await iq.answer(results, cache_time=300)

# ─── ADMIN ────────────────────────────────────────────────────────────────────

def _admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Foydalanuvchilar", callback_data="adm_users"),
         InlineKeyboardButton("📊 Statistika",       callback_data="adm_stats")],
        [InlineKeyboardButton("📢 Broadcast",         callback_data="adm_broadcast"),
         InlineKeyboardButton("📋 Loglar",            callback_data="adm_logs")],
        [InlineKeyboardButton("🖥 Server",            callback_data="adm_server"),
         InlineKeyboardButton("🔄 Restart",           callback_data="adm_restart")],
        [InlineKeyboardButton("🔍 User info",         callback_data="adm_userinfo"),
         InlineKeyboardButton("📥 Downloads",         callback_data="adm_downloads")],
        [InlineKeyboardButton("🚫 Ban list",          callback_data="adm_banlist"),
         InlineKeyboardButton("📣 Force sub",         callback_data="adm_forcesub")],
    ])

@app.on_message(filters.command("getcode") & admin_f)
@catch_errors
async def getcode_cmd(c: Client, m: Message):
    await m.reply_document("/root/bot/bot_fixed.py", caption="bot_fixed.py", quote=True)

@app.on_message(filters.command("admin") & admin_f)
@catch_errors
async def admin_cmd(c: Client, m: Message):
    total, at, aw, dt, dtotal = db_stats()
    text = (f"Admin panel\n\n👤 Jami: {total}\n🔥 Bugun: {at}\n"
            f"📅 Hafta: {aw}\n⬇️ Bugun dl: {dt}\n📦 Jami dl: {dtotal}")
    await m.reply_text(text, reply_markup=_admin_kb(), quote=True)

@app.on_callback_query(filters.regex(r"^adm_") & admin_f)
@catch_errors
async def admin_cb(c: Client, cb: CallbackQuery):
    action = cb.data
    back   = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="adm_back")]])

    if action == "adm_stats":
        total, at, aw, dt, dtotal = db_stats()
        await cb.message.edit_text(
            f"📊 Statistika\n\nJami: {total}\nBugun: {at}\nHafta: {aw}\nBugun dl: {dt}\nJami dl: {dtotal}",
            reply_markup=back)

    elif action == "adm_server":
        import shutil as _su
        td, ud, _ = _su.disk_usage("/")
        disk = f"{round(ud/1024**3,1)}/{round(td/1024**3,1)}GB"
        ram = "n/a"
        try:
            with open("/proc/meminfo") as f:
                mem = {l.split(":")[0]: int(l.split()[1]) for l in f if ":" in l}
            ram = f"{round((mem['MemTotal']-mem['MemAvailable'])/1024**2,1)}/{round(mem['MemTotal']/1024**2,1)}GB"
        except Exception: pass
        cpu = "n/a"
        try:
            with open("/proc/loadavg") as f: cpu = f.read().split()[0]
        except Exception: pass
        await cb.message.edit_text(f"🖥 Server\n\nCPU: {cpu}\nRAM: {ram}\nDisk: {disk}", reply_markup=back)

    elif action == "adm_logs":
        try:
            with open(LOG_FILE) as f: lines = f.readlines()
            last = "".join(lines[-20:])
            await cb.message.edit_text(last[-3000:] or "log bosh", reply_markup=back)
        except Exception: await cb.answer("log yoq")

    elif action == "adm_restart":
        await cb.message.edit_text("🔄 Restarting...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    elif action == "adm_users":
        conn = _db_conn(); cur = conn.cursor()
        cur.execute("SELECT user_id,username,first_name,downloads FROM users ORDER BY downloads DESC LIMIT 10")
        rows = cur.fetchall()
        text = "👤 Top 10:\n\n"
        for r in rows:
            text += f"{r[0]} @{r[1] or '-'} {r[2] or ''} | {r[3]} dl\n"
        await cb.message.edit_text(text, reply_markup=back)

    elif action == "adm_downloads":
        conn = _db_conn(); cur = conn.cursor()
        cur.execute("SELECT user_id,platform,status,created_at FROM downloads ORDER BY id DESC LIMIT 10")
        rows = cur.fetchall()
        text = "📥 Oxirgi 10:\n\n"
        for r in rows: text += f"{r[0]} | {r[1]} | {r[2]} | {r[3]}\n"
        if not rows: text += "hali yoq"
        await cb.message.edit_text(text, reply_markup=back)

    elif action == "adm_banlist":
        conn = _db_conn(); cur = conn.cursor()
        cur.execute("SELECT user_id,username,first_name FROM users WHERE is_banned=1")
        rows = cur.fetchall()
        text = "🚫 Banlangan:\n\n"
        for r in rows: text += f"{r[0]} @{r[1] or '-'} {r[2] or ''}\n"
        if not rows: text += "hech kim yoq"
        await cb.message.edit_text(text, reply_markup=back)

    elif action == "adm_broadcast":
        await cb.message.edit_text(
            "📢 Broadcast:\n/broadcast all Matn\n/broadcast uz Matn\n/broadcast ru Matn\n/broadcast en Matn\n/broadcast tr Matn",
            reply_markup=back)

    elif action == "adm_userinfo":
        await cb.message.edit_text("🔍 /user_info 12345678", reply_markup=back)

    elif action == "adm_forcesub":
        channels = db_get_force_channels()
        status   = "\n".join(channels) if channels else "Ochilgan"
        await cb.message.edit_text(
            f"📣 Force sub\n\nKanallar:\n{status}\n\n"
            "/setchannel @kanal — qoshish\n"
            "/setchannel -@kanal — ochirish\n"
            "/setchannel list — royxat\n"
            "/setchannel off — hammasini ochirish",
            reply_markup=back)

    elif action.startswith("adm_ban_"):
        uid2 = int(action.split("_")[2])
        with _db_lock:
            conn = _db_conn()
            conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (uid2,))
            conn.commit()
        await cb.answer(f"banned: {uid2}", show_alert=True)

    elif action.startswith("adm_unban_"):
        uid2 = int(action.split("_")[2])
        with _db_lock:
            conn = _db_conn()
            conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (uid2,))
            conn.commit()
        await cb.answer(f"unbanned: {uid2}", show_alert=True)

    elif action == "adm_back":
        total, at, aw, dt, dtotal = db_stats()
        text = (f"Admin panel\n\n👤 Jami: {total}\n🔥 Bugun: {at}\n"
                f"📅 Hafta: {aw}\n⬇️ Bugun dl: {dt}\n📦 Jami dl: {dtotal}")
        await cb.message.edit_text(text, reply_markup=_admin_kb())

@app.on_message(filters.command("broadcast") & admin_f)
@catch_errors
async def broadcast_cmd(c: Client, m: Message):
    if len(m.command) < 3:
        await m.reply_text("Ishlatish: /broadcast <all|uz|ru|en|tr> <matn>", quote=True); return
    target_lang = m.command[1].lower()
    text        = " ".join(m.command[2:])
    if target_lang not in {"all","uz","ru","en","tr"}:
        await m.reply_text("Til: all, uz, ru, en, tr", quote=True); return
    conn = _db_conn(); cur = conn.cursor()
    if target_lang == "all":
        cur.execute("SELECT user_id FROM users WHERE is_banned=0")
    else:
        cur.execute("SELECT user_id FROM users WHERE is_banned=0 AND lang=?", (target_lang,))
    users = [r[0] for r in cur.fetchall()]
    ok = fail = 0
    for uid in users:
        try:
            await c.send_message(uid, text); ok += 1
            await asyncio.sleep(0.05)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try: await c.send_message(uid, text); ok += 1
            except: fail += 1
        except: fail += 1
    await m.reply_text(f"📢 Yuborildi: {ok}/{len(users)}\n❌ Xato: {fail}\n🌐 Til: {target_lang}", quote=True)

@app.on_message(filters.command("ban") & admin_f)
@catch_errors
async def ban_cmd(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("/ban user_id", quote=True); return
    uid = int(m.command[1])
    with _db_lock:
        conn = _db_conn()
        conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (uid,))
        conn.commit()
    await m.reply_text(f"🚫 banned: {uid}", quote=True)

@app.on_message(filters.command("unban") & admin_f)
@catch_errors
async def unban_cmd(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("/unban user_id", quote=True); return
    uid = int(m.command[1])
    with _db_lock:
        conn = _db_conn()
        conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (uid,))
        conn.commit()
    await m.reply_text(f"✅ unbanned: {uid}", quote=True)

@app.on_message(filters.command("user_info") & admin_f)
@catch_errors
async def user_info_cmd(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("/user_info user_id", quote=True); return
    uid  = int(m.command[1])
    conn = _db_conn(); cur = conn.cursor()
    cur.execute("SELECT user_id,username,first_name,lang,joined_at,last_active,downloads,is_banned FROM users WHERE user_id=?", (uid,))
    u = cur.fetchone()
    cur.execute("SELECT url,platform,status,created_at FROM downloads WHERE user_id=? ORDER BY id DESC LIMIT 5", (uid,))
    dls = cur.fetchall()
    if not u:
        await m.reply_text("topilmadi", quote=True); return
    text = (f"👤 {u[0]}\n@{u[1] or '-'} {u[2] or ''}\n"
            f"🌐 {u[3]}\n📅 {u[4]}\n⏱ {u[5]}\n"
            f"⬇️ {u[6]}\n🚫 {'ha' if u[7] else 'yoq'}\n\nOxirgi 5:\n")
    for d in dls: text += f"{d[1]} | {d[2]} | {d[3]}\n"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚫 Ban" if not u[7] else "✅ Unban",
            callback_data=f"adm_ban_{uid}" if not u[7] else f"adm_unban_{uid}")
    ]])
    await m.reply_text(text, reply_markup=kb, quote=True)

@app.on_message(filters.command("setchannel") & admin_f)
@catch_errors
async def setchannel_cmd(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("/setchannel @kanal | -@kanal | list | off", quote=True); return
    val  = m.command[1].lower()
    loop = asyncio.get_event_loop()
    if val == "off":
        with _db_lock:
            conn = _db_conn()
            conn.execute("DELETE FROM force_sub_channels")
            conn.commit()
        await m.reply_text("Barcha force sub kanallari ochirildi", quote=True)
    elif val == "list":
        channels = await loop.run_in_executor(None, db_get_force_channels)
        text = "Kanallar:\n" + "\n".join(channels) if channels else "Force sub ochilgan"
        await m.reply_text(text, quote=True)
    elif val.startswith("-"):
        ch = val[1:] if val[1:].startswith("@") else "@" + val[1:]
        await loop.run_in_executor(None, db_remove_force_channel, ch)
        await m.reply_text(f"Ochirildi: {ch}", quote=True)
    else:
        ch = val if val.startswith("@") else "@" + val
        await loop.run_in_executor(None, db_add_force_channel, ch)
        channels = await loop.run_in_executor(None, db_get_force_channels)
        await m.reply_text(f"Qoshildi: {ch}\nJami: {len(channels)} ta", quote=True)

# ─── MAIN ─────────────────────────────────────────────────────────────────────

async def main():
    await temp_cleanup()
    safe_task(cache_cleanup_loop(), "cleanup_loop")
    safe_task(temp_cleanup_loop(), "temp_cleanup_loop")
    await app.start()
    print("🤖 Lyra ishga tushdi")
    await asyncio.get_event_loop().create_future()

if __name__ == "__main__":
    app.run(main())