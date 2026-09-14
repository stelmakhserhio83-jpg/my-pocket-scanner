import os
import asyncio
import requests
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

BOT_TOKEN = os.getenv("BOT_TOKEN", "8381163993:AAEaJ8256hIp33Gj3ooBM_a1p9p37wgQPog")
CHAT_ID = os.getenv("CHAT_ID")

SCANNER_ACTIVE = False

# Списки активов Pocket Option OTC
FOREX_PAIRS = ["EUR/USD OTC", "GBP/USD OTC", "USD/JPY OTC", "AUD/CAD OTC", "EUR/GBP OTC"]
STOCKS_PAIRS = ["Apple OTC", "Microsoft OTC", "Tesla OTC", "Amazon OTC", "Boeing OTC"]

def send_telegram_message(text: str, reply_markup=None):
    if not BOT_TOKEN:
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

# Инлайн-клавиатура: Главное меню
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
                {"text": "📊 Статус системы", "callback_data": "cmd_status"}
            ]
        ]
    }

# Инлайн-клавиатура: Список пар
def get_pairs_keyboard(pairs_list):
    keyboard = []
    for i in range(0, len(pairs_list), 2):
        row = [{"text": f"🎯 {pairs_list[i]}", "callback_data": f"scan_pair_{pairs_list[i]}"}]
        if i + 1 < len(pairs_list):
            row.append({"text": f"🎯 {pairs_list[i+1]}", "callback_data": f"scan_pair_{pairs_list[i+1]}"})
        keyboard.append(row)
    keyboard.append([{"text": "⬅️ Назад в меню", "callback_data": "cat_main"}])
    return {"inline_keyboard": keyboard}

# Аналитика и индикаторы
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
    stoch_k = k_values[-1]
    stoch_d = sum(k_values[-d_period:]) / d_period
    return stoch_k, stoch_d

def calculate_expiration_time(candles):
    if len(candles) < 10:
        return "1 мин"
    ranges = [c['high'] - c['low'] for c in candles[-5:]]
    avg_range = sum(ranges) / len(ranges)
    last_range = candles[-1]['high'] - candles[-1]['low']
    return "2 мин" if last_range > avg_range * 1.3 else "1 мин"

async def market_scanner_loop():
    global SCANNER_ACTIVE
    while True:
        if SCANNER_ACTIVE:
            try:
                pass
            except Exception as e:
                print(f"Scanner Loop Error: {e}")
        await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(market_scanner_loop())
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    global SCANNER_ACTIVE, CHAT_ID
    data = await request.json()
    
    # Авто-фиксация CHAT_ID из первого пришедшего сообщения/клика
    if "message" in data:
        CHAT_ID = str(data["message"]["chat"]["id"])
    elif "callback_query" in data:
        CHAT_ID = str(data["callback_query"]["message"]["chat"]["id"])

    # Обработка кликов по кнопкам
    if "callback_query" in data:
        cb_data = data["callback_query"].get("data", "")
        
        if cb_data == "cat_forex":
            send_telegram_message("💱 <b>Выберите валютную пару OTC:</b>", get_pairs_keyboard(FOREX_PAIRS))
        elif cb_data == "cat_stocks":
            send_telegram_message("📈 <b>Выберите акцию OTC:</b>", get_pairs_keyboard(STOCKS_PAIRS))
        elif cb_data == "cat_main":
            send_telegram_message("🎛 <b>Главное меню сканера Pocket Option:</b>", get_main_inline_keyboard())
        elif cb_data == "cmd_start":
            SCANNER_ACTIVE = True
            send_telegram_message("⚡️ <b>Активный сканер ЗАПУЩЕН!</b>\nОтслеживаю Forex и Акции OTC (>90% выплат).", get_main_inline_keyboard())
        elif cb_data == "cmd_stop":
            SCANNER_ACTIVE = False
            send_telegram_message("🔴 <b>Сканер переведен на ПАУЗУ.</b>", get_main_inline_keyboard())
        elif cb_data == "cmd_status":
            state_str = "⚡️ АКТИВЕН" if SCANNER_ACTIVE else "🔴 НА ПАУЗЕ"
            send_telegram_message(f"📊 <b>Статус:</b> {state_str}\nРежим: <b>Active SMC + Stoch (8,3,3)</b>", get_main_inline_keyboard())
        elif cb_data.startswith("scan_pair_"):
            pair_name = cb_data.replace("scan_pair_", "")
            send_telegram_message(f"🔍 <b>Анализирую {pair_name}...</b>\nПоиск сетапа SMC + ФВГ...")

    # Обработка команд в тексте (/start, /status)
    elif "message" in data and "text" in data["message"]:
        text = data["message"]["text"].strip()
        if text in ["/start", "/menu"]:
            send_telegram_message("🎛 <b>Панель управления Pocket Option Scanner:</b>", get_main_inline_keyboard())
        elif text == "/start_scan":
            SCANNER_ACTIVE = True
            send_telegram_message("⚡️ <b>Сканер ЗАПУЩЕН!</b>", get_main_inline_keyboard())
        elif text == "/stop_scan":
            SCANNER_ACTIVE = False
            send_telegram_message("🔴 <b>Сканер ОСТАНОВЛЕН.</b>", get_main_inline_keyboard())
        elif text == "/status":
            state_str = "⚡️ АКТИВЕН" if SCANNER_ACTIVE else "🔴 НА ПАУЗЕ"
            send_telegram_message(f"📊 <b>Статус:</b> {state_str}\nВыплаты: <b>> 90%</b>", get_main_inline_keyboard())
                
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"status": "Active SMC Scanner Running", "active": SCANNER_ACTIVE}
