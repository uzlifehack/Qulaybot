import hashlib
import aiosqlite
from datetime import datetime
from config import DB_PATH

def hash_url(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, lang FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            return await cursor.fetchone()

async def upsert_user(user_id: int, username: str, lang: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, lang, last_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                last_seen = excluded.last_seen
        """, (user_id, username, lang, datetime.now()))
        await db.commit()

async def set_user_lang(user_id: int, lang: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id)
        )
        await db.commit()

async def get_cached(url: str):
    url_hash = hash_url(url)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT msg_id FROM cache WHERE url_hash = ?", (url_hash,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_cached(url: str, msg_id: int):
    url_hash = hash_url(url)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO cache (url_hash, msg_id, created_at)
            VALUES (?, ?, ?)
        """, (url_hash, msg_id, datetime.now()))
        await db.commit()

async def inc_stat(field: str):
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"""
            INSERT INTO stats (date, {field}) VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET {field} = {field} + 1
        """, (today,))
        await db.commit()

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
        async with db.execute("SELECT SUM(downloads) FROM stats") as c:
            total_downloads = (await c.fetchone())[0] or 0
        async with db.execute(
            "SELECT downloads FROM stats WHERE date = ?",
            (datetime.now().strftime("%Y-%m-%d"),)
        ) as c:
            row = await c.fetchone()
            today_downloads = row[0] if row else 0
    return {
        "total_users": total_users,
        "total_downloads": total_downloads,
        "today_downloads": today_downloads,
    }
