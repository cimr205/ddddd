import asyncio
import os
import uvicorn
from dashboard.app import app
from core.database import init_db
from telegram_bot import telegram_bot


async def main():
    os.makedirs("data", exist_ok=True)
    await init_db()

    # Start Telegram bot in background (no-op if TELEGRAM_BOT_TOKEN not set)
    asyncio.create_task(telegram_bot.start())

    config = uvicorn.Config(
        app=app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        log_level=os.getenv("LOG_LEVEL", "info"),
        ws_ping_interval=20,
        ws_ping_timeout=30,
    )
    server = uvicorn.Server(config)
    await server.serve()

    await telegram_bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
