import asyncio
import json
import os
import sys
from pathlib import Path
from pyrogram import Client, filters, enums, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from db.crud import get_stats, get_user
from cache.redis_client import get_redis
from config import ADMIN_IDS, DB_PATH
import aiosqlite

LOG_FILE = str(Path(__file__).parent.parent.parent / "bot.log")

def t(lang: str, key: str, **kwargs) -> str:
    path = Path(__file__).parent.parent.parent / "locales" / f"{lang}.json"
    try:
        data = json.loads(path.read_text())
        text = data.get(key, key)
        return text.format(**kwargs) if kwargs else text
    except Exception:
        return key

async def get_lang(user_id: int) -> str:
    row = await get_user(user_id)
    return row[1] if row else "en"

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Statistika", callback_data="adm_stats"),
            InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="adm_users"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast"),
            InlineKeyboardButton("🗑 Cache tozalash", callback_data="adm_clear_cache"),
        ],
        [
            InlineKeyboardButton("⚙️ Server holati", callback_data="adm_status"),
            InlineKeyboardButton("📋 Loglar", callback_data="adm_logs"),
        ],
        [
            InlineKeyboardButton("🔔 Force Sub", callback_data="adm_forcesub"),
            InlineKeyboardButton("🔄 Restart", callback_data="adm_restart"),
        ]
    ])

def register(app: Client):

    @app.on_message(filters.command("admin") & filters.private)
    async def handle_admin(client: Client, message: Message):
        if not is_admin(message.from_user.id):
            lang = await get_lang(message.from_user.id)
            await message.reply_text(t(lang, "admin_only"))
            return
        await message.reply_text(
            "🛠 <b>Admin Panel</b>",
            reply_markup=admin_panel_keyboard(),
            parse_mode=enums.ParseMode.HTML
        )

    @app.on_callback_query(filters.regex(r"^adm_stats$"))
    async def handle_stats(client: Client, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Ruxsat yo'q", show_alert=True)
            return
        await callback.answer()
        stats = await get_stats()
        text = (
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Jami foydalanuvchilar: <b>{stats['total_users']}</b>\n"
            f"⬇️ Jami yuklashlar: <b>{stats['total_downloads']}</b>\n"
            f"📅 Bugun: <b>{stats['today_downloads']}</b>"
        )
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back")]
            ]),
            parse_mode=enums.ParseMode.HTML
        )

    @app.on_callback_query(filters.regex(r"^adm_users$"))
    async def handle_users(client: Client, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Ruxsat yo'q", show_alert=True)
            return
        await callback.answer()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE last_seen >= datetime('now', '-1 day')"
            ) as c:
                today = (await c.fetchone())[0]
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE last_seen >= datetime('now', '-7 days')"
            ) as c:
                week = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM users") as c:
                total = (await c.fetchone())[0]
        text = (
            f"👥 <b>Foydalanuvchilar</b>\n\n"
            f"Jami: <b>{total}</b>\n"
            f"Bugun faol: <b>{today}</b>\n"
            f"Hafta ichida faol: <b>{week}</b>"
        )
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back")]
            ]),
            parse_mode=enums.ParseMode.HTML
        )

    @app.on_callback_query(filters.regex(r"^adm_clear_cache$"))
    async def handle_clear_cache(client: Client, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Ruxsat yo'q", show_alert=True)
            return
        await callback.answer()
        redis = await get_redis()
        keys = await redis.keys("cache:*")
        if keys:
            await redis.delete(*keys)
        await callback.message.edit_text(
            f"🗑 Cache tozalandi. {len(keys)} ta kalit o'chirildi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back")]
            ])
        )

    @app.on_callback_query(filters.regex(r"^adm_status$"))
    async def handle_status(client: Client, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Ruxsat yo'q", show_alert=True)
            return
        await callback.answer()
        import shutil, psutil
        disk = shutil.disk_usage("/")
        disk_used = disk.used / 1024 / 1024 / 1024
        disk_total = disk.total / 1024 / 1024 / 1024
        ram = psutil.virtual_memory()
        ram_used = ram.used / 1024 / 1024 / 1024
        ram_total = ram.total / 1024 / 1024 / 1024
        cpu = psutil.cpu_percent(interval=1)
        redis = await get_redis()
        redis_keys = len(await redis.keys("*"))
        text = (
            f"⚙️ <b>Server holati</b>\n\n"
            f"💾 Disk: <b>{disk_used:.1f}/{disk_total:.1f} GB</b>\n"
            f"🧠 RAM: <b>{ram_used:.1f}/{ram_total:.1f} GB</b>\n"
            f"🔥 CPU: <b>{cpu}%</b>\n"
            f"🗄 Redis kalitlar: <b>{redis_keys}</b>\n"
            f"✅ Bot ishlayapti"
        )
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back")]
            ]),
            parse_mode=enums.ParseMode.HTML
        )

    @app.on_callback_query(filters.regex(r"^adm_logs$"))
    async def handle_logs(client: Client, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Ruxsat yo'q", show_alert=True)
            return
        await callback.answer()
        try:
            if not os.path.exists(LOG_FILE):
                await callback.answer("Log fayl topilmadi", show_alert=True)
                return
            # Oxirgi 30 qatorni olish
            with open(LOG_FILE, "r") as f:
                lines = f.readlines()
            last_lines = lines[-30:] if len(lines) > 30 else lines
            log_text = "".join(last_lines).strip()
            if len(log_text) > 3500:
                log_text = log_text[-3500:]
            await client.send_document(
                chat_id=callback.from_user.id,
                document=LOG_FILE,
                caption="📋 Bot log fayli"
            )
            await callback.message.reply_text(
                f"<pre>{log_text}</pre>",
                parse_mode=enums.ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back")]
                ])
            )
        except Exception as e:
            await callback.answer(f"Xato: {e}", show_alert=True)

    @app.on_callback_query(filters.regex(r"^adm_forcesub$"))
    async def handle_forcesub(client: Client, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Ruxsat yo'q", show_alert=True)
            return
        await callback.answer()
        redis = await get_redis()
        current = await redis.get("forcesub_channel")
        status = f"Hozirgi: <b>{current}</b>" if current else "Hozirda o'chiq"
        await callback.message.edit_text(
            f"🔔 <b>Force Subscribe</b>\n\n"
            f"{status}\n\n"
            f"O'zgartirish uchun:\n"
            f"<code>/setforcesub @kanal_username</code>\n"
            f"O'chirish uchun:\n"
            f"<code>/setforcesub off</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back")]
            ]),
            parse_mode=enums.ParseMode.HTML
        )

    @app.on_message(filters.command("setforcesub") & filters.private)
    async def handle_set_forcesub(client: Client, message: Message):
        if not is_admin(message.from_user.id):
            return
        args = message.text.split(None, 1)
        if len(args) < 2:
            await message.reply_text("❌ Foydalanish: /setforcesub @kanal yoki /setforcesub off")
            return
        value = args[1].strip()
        redis = await get_redis()
        if value.lower() == "off":
            await redis.delete("forcesub_channel")
            await message.reply_text("✅ Force sub o'chirildi.")
        else:
            await redis.set("forcesub_channel", value)
            await message.reply_text(f"✅ Force sub o'rnatildi: {value}")

    @app.on_callback_query(filters.regex(r"^adm_restart$"))
    async def handle_restart(client: Client, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Ruxsat yo'q", show_alert=True)
            return
        await callback.answer()
        await callback.message.edit_text(
            "🔄 <b>Restart</b>\n\nBotni qayta ishga tushirasizmi?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Ha", callback_data="adm_restart_confirm"),
                    InlineKeyboardButton("❌ Yo'q", callback_data="adm_back"),
                ]
            ]),
            parse_mode=enums.ParseMode.HTML
        )

    @app.on_callback_query(filters.regex(r"^adm_restart_confirm$"))
    async def handle_restart_confirm(client: Client, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Ruxsat yo'q", show_alert=True)
            return
        await callback.answer()
        await callback.message.edit_text("🔄 Bot qayta ishga tushmoqda...")
        await asyncio.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @app.on_message(filters.command("broadcast") & filters.private)
    async def handle_broadcast(client: Client, message: Message):
        if not is_admin(message.from_user.id):
            return
        text = message.text.split(None, 1)
        if len(text) < 2:
            await message.reply_text("❌ Foydalanish: /broadcast [xabar]")
            return
        broadcast_text = text[1]
        status_msg = await message.reply_text("📢 Yuborilmoqda...")
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id FROM users") as c:
                users = await c.fetchall()
        success = 0
        failed = 0
        for (user_id,) in users:
            try:
                await client.send_message(user_id, broadcast_text)
                success += 1
                await asyncio.sleep(0.05)
            except (UserIsBlocked, InputUserDeactivated):
                failed += 1
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                try:
                    await client.send_message(user_id, broadcast_text)
                    success += 1
                except Exception:
                    failed += 1
            except Exception:
                failed += 1
        await status_msg.edit_text(
            f"✅ Broadcast tugadi.\n"
            f"✅ Yuborildi: {success}\n"
            f"❌ Xato: {failed}"
        )

    @app.on_callback_query(filters.regex(r"^adm_back$"))
    async def handle_back(client: Client, callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer()
            return
        await callback.answer()
        await callback.message.edit_text(
            "🛠 <b>Admin Panel</b>",
            reply_markup=admin_panel_keyboard(),
            parse_mode=enums.ParseMode.HTML
        )
