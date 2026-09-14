import os
import asyncio
from fastapi import FastAPI
from telegram import Bot

app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

@app.get("/")
def read_root():
    return {"status": "Scanner is running online!"}

@app.get("/ping")
async def ping_bot():
    if bot:
        me = await bot.get_me()
        return {"bot_status": "Connected", "bot_name": me.first_name}
    return {"error": "No BOT_TOKEN set"}
