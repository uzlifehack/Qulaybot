import redis.asyncio as redis
from config import REDIS_URL

_redis = None

async def get_redis():
    global _redis
    if _redis is None:
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis

async def close_redis():
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
