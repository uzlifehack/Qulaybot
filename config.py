import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_ID            = int(os.getenv("API_ID", "39474802"))
API_HASH          = os.getenv("API_HASH", "f505449dd881e1408c033541734c11ae")
BOT_TOKEN         = os.getenv("BOT_TOKEN", "8755804730:AAEAQauTao3y0MnCwamHlNyinV9njnLAnic")
ADMIN_IDS         = [int(x) for x in os.getenv("ADMIN_IDS", "8471569554").split(",")]
CACHE_CHANNEL_ID  = int(os.getenv("CACHE_CHANNEL_ID", "-1003893318252"))
REDIS_URL         = os.getenv("REDIS_URL", "redis://localhost:6379")
DB_PATH           = os.getenv("DB_PATH", "/root/lyra/lyra.db")
MAX_FILE_SIZE     = 2 * 1024 * 1024 * 1024
RATE_LIMIT        = 5
PROGRESS_UPDATE_INTERVAL = 10
DOWNLOAD_SEMAPHORE = 3
BOT_ID = int(BOT_TOKEN.split(":")[0])
BOT_ID = int(BOT_TOKEN.split(":")[0])
