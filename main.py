import os
import requests
from fastapi import FastAPI

app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram_message(message: str):
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

@app.get("/")
def read_root():
    return {"status": "Scanner is running online!"}

@app.get("/ping")
def ping():
    if not BOT_TOKEN:
        return {"error": "No BOT_TOKEN set"}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    try:
        res = requests.get(url, timeout=5).json()
        if res.get("ok"):
            return {"bot_status": "Connected", "bot_name": res["result"]["username"]}
    except Exception as e:
        return {"error": str(e)}
    return {"bot_status": "Failed to connect"}

@app.get("/test-signal")
def test_signal():
    msg = "🚀 <b>[POCKET SCANNER]</b>\n\nПара: <b>EUR/USD</b>\nСигнал: <b>CALL (ВВЕРХ)</b> 🟢\nВремя: 1 мин\nRSI: 28 (Перепроданность)"
    success = send_telegram_message(msg)
    if success:
        return {"status": "Signal sent successfully to Telegram!"}
    return {"error": "Failed to send signal. Check CHAT_ID and BOT_TOKEN."}
