import asyncio
from pyrogram import Client
from pyrogram.errors import FloodWait
from cache.redis_client import get_redis
from db.crud import get_cached, set_cached
from config import CACHE_CHANNEL_ID

_locks = {}

async def get_or_download(client: Client, url: str, download_func) -> int:
    redis = await get_redis()

    # 1. Redis cache tekshir
    cached = await redis.get(f"cache:{url}")
    if cached:
        return int(cached)

    # 2. DB cache tekshir
    msg_id = await get_cached(url)
    if msg_id:
        await redis.setex(f"cache:{url}", 86400, msg_id)
        return msg_id

    # 3. Lock — race condition oldini olish
    if url not in _locks:
        _locks[url] = asyncio.Lock()

    async with _locks[url]:
        # Ikkinchi tekshir — boshqa process yuklab bo'lgan bo'lishi mumkin
        msg_id = await get_cached(url)
        if msg_id:
            return msg_id

        # 4. Yuklab kesh kanalga yuborish
        file_path = await download_func(url)

        while True:
            try:
                sent = await client.send_document(
                    chat_id=CACHE_CHANNEL_ID,
                    document=file_path,
                    force_document=True
                )
                break
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)

        # 5. Saqlash
        await set_cached(url, sent.id)
        await redis.setex(f"cache:{url}", 86400, sent.id)

        # Lock tozalash
        _locks.pop(url, None)

        return sent.id

async def forward_to_user(client: Client, user_id: int, msg_id: int):
    while True:
        try:
            await client.forward_messages(
                chat_id=user_id,
                from_chat_id=CACHE_CHANNEL_ID,
                message_ids=msg_id
            )
            break
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
