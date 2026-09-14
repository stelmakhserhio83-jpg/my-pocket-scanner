import os
import asyncio
import json
import requests
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import websockets

BOT_TOKEN = os.getenv("BOT_TOKEN", "8381163993:AAEaJ8256hIp33Gj3ooBM_a1p9p37wgQPog")
CHAT_ID = os.getenv("CHAT_ID")

SCANNER_ACTIVE = False

# Основные OTC-активы Pocket Option
FOREX_PAIRS = [
    "EUR/USD OTC", "GBP/USD OTC", "USD/JPY OTC", "AUD/CAD OTC", 
    "EUR/GBP OTC", "USD/CHF OTC", "AUD/USD OTC", "NZD/USD OTC"
]
STOCKS_PAIRS = [
    "Apple OTC", "Microsoft OTC", "Tesla OTC", "Amazon OTC", 
    "Boeing OTC", "Google OTC", "Meta OTC", "Netflix OTC"
]

# Хранилище реальных свечей, поступающих из WebSocket Pocket Option
MARKET_DATA = {}

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

def edit_telegram_message(message_id: int, text: str, reply_markup=None):
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {"chat_id": CHAT_ID, "message_id": message_id, "text": text, "parse_mode": "HTML"}
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
                {"text": "💱 Валютные пары (Forex OTC)", "callback_data": "cat_forex"},
                {"text": "📈 Акции (Stocks OTC)", "callback_data": "cat_stocks"}
            ],
            [
                {"text": "⚡️ Запустить сканер", "callback_data": "cmd_start"},
                {"text": "🔴 Стоп сканер", "callback_data": "cmd_stop"}
            ],
            [
                {"text": "📊 Статус WebSocket", "callback_data": "cmd_status"}
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

# Фоновый коннектор к потоку котировок Pocket Option WebSocket
async def pocket_option_ws_listener():
    global MARKET_DATA
    uri = "wss://hqindexer.pocketoption.com/socket.io/?EIO=4&transport=websocket"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                print("Connected to Pocket Option WS Feed")
                async for message in ws:
                    # Обработка входящих пакетов котировок брокера
                    if message.startswith("42"):
                        try:
                            data = json.loads(message[2:])
                            if isinstance(data, list) and len(data) > 1:
                                event_name = data[0]
                                event_payload = data[1]
                                if event_name == "update_asset" or "rate" in str(event_payload):
                                    # Парсим актив и цену из потока брокера
                                    asset = event_payload.get("asset", "EUR/USD OTC")
                                    price = float(event_payload.get("price", 0))
                                    if price > 0:
                                        if asset not in MARKET_DATA:
                                            MARKET_DATA[asset] = []
                                        MARKET_DATA[asset].append({
                                            "open": price, "high": price, "low": price, "close": price
                                        })
                                        # Держим хвост свечей в памяти для расчета
                                        if len(MARKET_DATA[asset]) > 100:
                                            MARKET_DATA[asset].pop(0)
                        except Exception:
                            pass
        except Exception as e:
            print(f"WS Connection Error: {e}")
            await asyncio.sleep(5)

def analyze_pocket_setup(pair_name):
    candles = MARKET_DATA.get(pair_name, [])
    if len(candles) < 15:
        # Если данных из потока еще мало (только запустились), даем базовый срез из накопленного
        return {
            "status": "waiting",
            "text": f"⏳ Актив {pair_name} калибрует потоковые котировки WS... Подождите 10 секунд и повторите клик."
        }
    
    stoch_k, stoch_d = calculate_stochastic(candles)
    last_price = candles[-1]['close']
    prev_price = candles[-2]['close']
    
    m5_bullish = candles[-1]['close'] >= candles[max(0, len(candles)-5)]['close']
    
    signal = "CALL (ВВЕРХ) 🟢" if m5_bullish and stoch_k < 30 else ("PUT (НИЗ) 🔴" if not m5_bullish and stoch_k > 70 else "НЕЙТРАЛЬНО")
    
    return {
        "status": "ok",
        "pair": pair_name,
        "price": last_price,
        "stoch_k": round(stoch_k, 1),
        "m5_trend": "Бычий 📈" if m5_bullish else "Медвежий 📉",
        "signal": signal,
        "exp": "1 мин"
    }

async def market_scanner_loop():
    global SCANNER_ACTIVE, CHAT_ID
    while True:
        if SCANNER_ACTIVE and CHAT_ID:
            for pair in FOREX_PAIRS:
                res = analyze_pocket_setup(pair)
                if res["status"] == "ok" and "НЕЙТРАЛЬНО" not in res["signal"]:
                    msg = (
                        f"🚨 <b>СИГНАЛ POCKET OPTION OTC!</b>\n\n"
                        f"🎯 Актив: <b>{res['pair']}</b>\n"
                        f"📊 Сигнал: <b>{res['signal']}</b>\n"
                        f"⏱ Экспирация: <b>{res['exp']}</b>\n"
                        f"📉 Цена: <code>{res['price']}</code>\n"
                        f"📈 Stoch K: <b>{res['stoch_k']}</b>"
                    )
                    send_telegram_message(msg)
                    await asyncio.sleep(5)
        await asyncio.sleep(15)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(pocket_option_ws_listener())
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

    if "callback_query" in data:
        cb = data["callback_query"]
        cb_data = cb.get("data", "")
        message_id = cb["message"]["message_id"]
        
        if cb_data == "cat_forex":
            edit_telegram_message(message_id, "💱 <b>Выберите Forex OTC актив:</b>", get_pairs_keyboard(FOREX_PAIRS))
        elif cb_data == "cat_stocks":
            edit_telegram_message(message_id, "📈 <b>Выберите Stock OTC актив:</b>", get_pairs_keyboard(STOCKS_PAIRS))
        elif cb_data == "cat_main":
            edit_telegram_message(message_id, "🎛 <b>Главное меню Pocket Option WS Scanner:</b>", get_main_inline_keyboard())
        elif cb_data == "cmd_start":
            SCANNER_ACTIVE = True
            edit_telegram_message(message_id, "⚡️ <b>WebSocket сканер Pocket Option ЗАПУЩЕН!</b>", get_main_inline_keyboard())
        elif cb_data == "cmd_stop":
            SCANNER_ACTIVE = False
            edit_telegram_message(message_id, "🔴 <b>Сканер остановлен.</b>", get_main_inline_keyboard())
        elif cb_data == "cmd_status":
            active_pairs_count = len(MARKET_DATA)
            edit_telegram_message(message_id, f"📊 <b>Статус WS:</b> Активных потоков пар в памяти: <b>{active_pairs_count}</b>", get_main_inline_keyboard())
        elif cb_data.startswith("scan_pair_"):
            pair_name = cb_data.replace("scan_pair_", "")
            analysis = analyze_pocket_setup(pair_name)
            
            if analysis["status"] == "ok":
                result_text = (
                    f"🎯 <b>Анализ OTC: {analysis['pair']}</b>\n\n"
                    f"💵 Цена: <code>{analysis['price']}</code>\n"
                    f"📊 Stochastic K: <b>{analysis['stoch_k']}</b>\n"
                    f"📈 Тренд: <b>{analysis['m5_trend']}</b>\n"
                    f"💡 Вердикт: <b>{analysis['signal']}</b>"
                )
            else:
                result_text = analysis["text"]
                
            back_cat = FOREX_PAIRS if pair_name in FOREX_PAIRS else STOCKS_PAIRS
            edit_telegram_message(message_id, result_text, get_pairs_keyboard(back_cat))

    elif "message" in data and "text" in data["message"]:
        text = data["message"]["text"].strip()
        if text in ["/start", "/menu"]:
            send_telegram_message("🎛 <b>Панель управления Pocket Option WS Scanner:</b>", get_main_inline_keyboard())
                
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"status": "PO WebSocket Scanner Active", "tracked_assets": list(MARKET_DATA.keys())}
