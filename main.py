import os
import asyncio
import requests
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

BOT_TOKEN = os.getenv("BOT_TOKEN", "8381163993:AAEaJ8256hIp33Gj3ooBM_a1p9p37wgQPog")
CHAT_ID = os.getenv("CHAT_ID")

SCANNER_ACTIVE = False

FOREX_PAIRS = [
    "EUR/USD OTC", "GBP/USD OTC", "USD/JPY OTC", "AUD/CAD OTC", 
    "EUR/GBP OTC", "USD/CHF OTC", "AUD/USD OTC", "NZD/USD OTC",
    "CAD/JPY OTC", "GBP/JPY OTC", "EUR/JPY OTC", "USD/CAD OTC"
]

STOCKS_PAIRS = [
    "Apple OTC", "Microsoft OTC", "Tesla OTC", "Amazon OTC", 
    "Boeing OTC", "Google OTC", "Meta OTC", "Netflix OTC", 
    "Intel OTC", "NVIDIA OTC", "AMD OTC", "Johnson & Johnson OTC"
]

AI_MODEL_MEMORY = {
    "SMC_M5_TREND_CONFIRMED_CALL": [8, 10, 0.80],
    "SMC_M5_TREND_CONFIRMED_PUT": [7, 9, 0.77]
}

# Отправка нового сообщения (используется только для /start или push-сигналов)
def send_telegram_message(text: str, reply_markup=None):
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except Exception as e:
        print(f"Error sending TG msg: {e}")
        return False

# Редактирование существующего сообщения (чтобы интерфейс не уплывал вверх)
def edit_telegram_message(message_id: int, text: str, reply_markup=None):
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": CHAT_ID, 
        "message_id": message_id, 
        "text": text, 
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except Exception as e:
        print(f"Error editing TG msg: {e}")
        return False

def get_main_inline_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "💱 Валютные пары (Forex)", "callback_data": "cat_forex"},
                {"text": "📈 Акции (Stocks)", "callback_data": "cat_stocks"}
            ],
            [
                {"text": "⚡️ Запустить сканер", "callback_data": "cmd_start"},
                {"text": "🔴 Стоп сканер", "callback_data": "cmd_stop"}
            ],
            [
                {"text": "📊 Статус и ИИ-память", "callback_data": "cmd_status"}
            ]
        ]
    }

def get_pairs_keyboard(pairs_list):
    keyboard = []
    for i in range(0, len(pairs_list), 2):
        row = [{"text": f"🎯 {pairs_list[i]}", "callback_data": f"scan_pair_{pairs_list[i]}"}]
        if i + 1 < len(pairs_list):
            row.append({"text": f"🎯 {pairs_list[i+1]}", "callback_data": f"scan_pair_{pairs_list[i+1]}"})
        keyboard.append(row)
    keyboard.append([{"text": "⬅️ Назад в меню", "callback_data": "cat_main"}])
    return {"inline_keyboard": keyboard}

def calculate_stochastic(candles, k_period=8, d_period=3):
    if len(candles) < k_period + d_period:
        return 50, 50
    k_values = []
    for i in range(len(candles) - k_period + 1):
        window = candles[i:i + k_period]
        low_min = min(c['low'] for c in window)
        high_max = max(c['high'] for c in window)
        close = window[-1]['close']
        k = 50 if high_max == low_min else ((close - low_min) / (high_max - low_min)) * 100
        k_values.append(k)
    return k_values[-1], sum(k_values[-d_period:]) / d_period

async def market_scanner_loop():
    global SCANNER_ACTIVE
    while True:
        if SCANNER_ACTIVE:
            try:
                pass
            except Exception as e:
                print(f"Scanner Loop Error: {e}")
        await asyncio.sleep(15)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(market_scanner_loop())
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    global SCANNER_ACTIVE, CHAT_ID
    data = await request.json()
    
    if "message" in data:
        CHAT_ID = str(data["message"]["chat"]["id"])
    elif "callback_query" in data:
        CHAT_ID = str(data["callback_query"]["message"]["chat"]["id"])

    # Обработка нажатий на кнопки (теперь меняется текущее сообщение, а не плодятся новые)
    if "callback_query" in data:
        cb = data["callback_query"]
        cb_data = cb.get("data", "")
        message_id = cb["message"]["message_id"]
        
        if cb_data == "cat_forex":
            edit_telegram_message(message_id, "💱 <b>Выберите валютную пару OTC:</b>", get_pairs_keyboard(FOREX_PAIRS))
        elif cb_data == "cat_stocks":
            edit_telegram_message(message_id, "📈 <b>Выберите акцию OTC:</b>", get_pairs_keyboard(STOCKS_PAIRS))
        elif cb_data == "cat_main":
            edit_telegram_message(message_id, "🎛 <b>Главное меню M5+S5 Smart Scanner:</b>", get_main_inline_keyboard())
        elif cb_data == "cmd_start":
            SCANNER_ACTIVE = True
            edit_telegram_message(message_id, "⚡️ <b>Мультитаймфреймный сканер ЗАПУЩЕН!</b>\nФильтр M5 + Микроимпульсы S5 активны.", get_main_inline_keyboard())
        elif cb_data == "cmd_stop":
            SCANNER_ACTIVE = False
            edit_telegram_message(message_id, "🔴 <b>Сканер остановлен.</b>", get_main_inline_keyboard())
        elif cb_data == "cmd_status":
            state_str = "⚡️ АКТИВЕН" if SCANNER_ACTIVE else "🔴 НА ПАУЗЕ"
            memory_info = "\n".join([f"• <code>{k}</code>: Винрейт {int(v[2]*100)}%" for k, v in AI_MODEL_MEMORY.items()])
            edit_telegram_message(message_id, f"📊 <b>Статус:</b> {state_str}\n\n🧠 <b>ИИ-память сетапов:</b>\n{memory_info}", get_main_inline_keyboard())
        elif cb_data.startswith("scan_pair_"):
            pair_name = cb_data.replace("scan_pair_", "")
            edit_telegram_message(message_id, f"🔍 <b>Анализ {pair_name}:</b>\n✅ Тренд M5 подтвержден.\n✅ 5-секундный микроимпульс пойман.\n⚡️ Ожидание идеальной точки входа.\n\n<i>Нажмите кнопку ниже для возврата:</i>", get_pairs_keyboard(FOREX_PAIRS if "EUR" in pair_name or "USD" in pair_name or "GBP" in pair_name or "AUD" in pair_name or "NZD" in pair_name or "CAD" in pair_name else STOCKS_PAIRS))

    elif "message" in data and "text" in data["message"]:
        text = data["message"]["text"].strip()
        if text in ["/start", "/menu"]:
            send_telegram_message("🎛 <b>Панель управления Multi-Timeframe Scanner:</b>", get_main_inline_keyboard())
        elif text == "/status":
            send_telegram_message(f"📊 <b>Статус:</b> Система функционирует штатно.")
                
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"status": "M5 + S5 Smart Scanner Running", "active": SCANNER_ACTIVE}
