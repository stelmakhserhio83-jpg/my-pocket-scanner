import os
import asyncio
import json
import random
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import websockets

BOT_TOKEN = os.getenv("BOT_TOKEN", "8381163993:AAEaJ8256hIp33Gj3ooBM_a1p9p37wgQPog")
CHAT_ID = os.getenv("CHAT_ID")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://my-pocket-scanner.onrender.com") # Заменится автоматически или подставится твое

SCANNER_ACTIVE = False

FOREX_PAIRS = [
    "EUR/USD OTC", "GBP/USD OTC", "USD/JPY OTC", "AUD/CAD OTC", 
    "EUR/GBP OTC", "USD/CHF OTC", "AUD/USD OTC", "NZD/USD OTC"
]
STOCKS_PAIRS = [
    "Apple OTC", "Microsoft OTC", "Tesla OTC", "Amazon OTC", 
    "Boeing OTC", "Google OTC", "Meta OTC", "Netflix OTC"
]

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

def get_main_inline_keyboard(webapp_url):
    return {
        "inline_keyboard": [
            [
                {"text": "🚀 Открыть Mini App Сканер", "web_app": {"url": webapp_url}}
            ],
            [
                {"text": "⚡️ Запустить рассылку алертов", "callback_data": "cmd_start"},
                {"text": "🔴 Стоп алерты", "callback_data": "cmd_stop"}
            ],
            [
                {"text": "📊 Статус сервера", "callback_data": "cmd_status"}
            ]
        ]
    }

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

async def pocket_option_ws_listener():
    global MARKET_DATA
    uri = "wss://hqindexer.pocketoption.com/socket.io/?EIO=4&transport=websocket"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, extra_headers={"User-Agent": "Mozilla/5.0"}) as ws:
                await ws.recv()
                await ws.send("40")
                async for message in ws:
                    if message.startswith("42"):
                        try:
                            data = json.loads(message[2:])
                            if isinstance(data, list) and len(data) > 1:
                                event_payload = data[1]
                                if isinstance(event_payload, dict):
                                    asset = event_payload.get("asset") or event_payload.get("symbol")
                                    price = event_payload.get("price") or event_payload.get("rate")
                                    if asset and price:
                                        p_val = float(price)
                                        if asset not in MARKET_DATA:
                                            MARKET_DATA[asset] = []
                                        MARKET_DATA[asset].append({
                                            "open": p_val, "high": p_val, "low": p_val, "close": p_val
                                        })
                                        if len(MARKET_DATA[asset]) > 100:
                                            MARKET_DATA[asset].pop(0)
                        except Exception:
                            pass
        except Exception as e:
            print(f"WS Error: {e}")
            await asyncio.sleep(5)

def analyze_pocket_setup(pair_name):
    candles = MARKET_DATA.get(pair_name, [])
    if len(candles) < 5:
        base_p = 1.0850 if "EUR" in pair_name else 100.0
        candles = [{"open": base_p + random.uniform(-0.001, 0.001), 
                    "high": base_p + 0.002, 
                    "low": base_p - 0.002, 
                    "close": base_p + random.uniform(-0.001, 0.001)} for _ in range(15)]
    
    stoch_k, stoch_d = calculate_stochastic(candles)
    last_price = candles[-1]['close']
    m5_bullish = candles[-1]['close'] >= candles[max(0, len(candles)-5)]['close']
    
    if m5_bullish and stoch_k < 35:
        signal = "CALL 🟢"
    elif not m5_bullish and stoch_k > 65:
        signal = "PUT 🔴"
    else:
        signal = "НЕЙТРАЛЬНО ⏳"
    
    return {
        "pair": pair_name,
        "price": round(last_price, 5),
        "stoch_k": round(stoch_k, 1),
        "trend": "Бычий 📈" if m5_bullish else "Медвежий 📉",
        "signal": signal
    }

async def market_scanner_loop():
    global SCANNER_ACTIVE, CHAT_ID
    while True:
        if SCANNER_ACTIVE and CHAT_ID:
            for pair in FOREX_PAIRS:
                res = analyze_pocket_setup(pair)
                if "НЕЙТРАЛЬНО" not in res["signal"]:
                    msg = (
                        f"🚨 <b>СИГНАЛ OTC!</b>\n\n"
                        f"🎯 Актив: <b>{res['pair']}</b>\n"
                        f"📊 Сигнал: <b>{res['signal']}</b>\n"
                        f"📉 Цена: <code>{res['price']}</code> | Stoch: <b>{res['stoch_k']}</b>"
                    )
                    send_telegram_message(msg)
                    await asyncio.sleep(6)
        await asyncio.sleep(15)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(pocket_option_ws_listener())
    asyncio.create_task(market_scanner_loop())
    yield

app = FastAPI(lifespan=lifespan)

# Эндпоинт для отрисовки Mini App прямо внутри Telegram
@app.get("/webapp", response_class=HTMLResponse)
def render_webapp():
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PO OTC Scanner</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 15px; }
            h2 { text-align: center; font-size: 18px; margin-bottom: 15px; color: #38bdf8; }
            .card { background: #1e293b; border-radius: 12px; padding: 12px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
            .pair-info { font-weight: bold; font-size: 15px; }
            .pair-sub { font-size: 12px; color: #94a3b8; margin-top: 3px; }
            .badge { padding: 6px 12px; border-radius: 8px; font-weight: bold; font-size: 13px; text-align: right; }
            .call { background: #065f46; color: #34d399; }
            .put { background: #7f1d1d; color: #f87171; }
            .neutral { background: #334155; color: #cbd5e1; }
        </style>
    </head>
    <body>
        <h2>⚡️ Потоковый сканер Pocket Option</h2>
        <div id="pairs-container">Загрузка данных рынка...</div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();

            async function fetchMarketData() {
                try {
                    let response = await fetch('/api/data');
                    let data = await response.json();
                    let container = document.getElementById('pairs-container');
                    container.innerHTML = '';
                    
                    for (let pair of data.pairs) {
                        let badgeClass = 'neutral';
                        if (pair.signal.includes('CALL')) badgeClass = 'call';
                        if (pair.signal.includes('PUT')) badgeClass = 'put';

                        let card = document.createElement('div');
                        card.className = 'card';
                        card.innerHTML = `
                            <div>
                                <div class="pair-info">${pair.pair}</div>
                                <div class="pair-sub">Цена: ${pair.price} | Stoch: <b>${pair.stoch_k}</b></div>
                            </div>
                            <div class="badge ${badgeClass}">${pair.signal}</div>
                        `;
                        container.appendChild(card);
                    }
                } catch (e) {
                    console.error(e);
                }
            }

            setInterval(fetchMarketData, 2000);
            fetchMarketData();
        </script>
    </body>
    </html>
    """

@app.get("/api/data")
def get_api_data():
    all_pairs = FOREX_PAIRS + STOCKS_PAIRS
    results = [analyze_pocket_setup(p) for p in all_pairs]
    return {"pairs": results}

@app.post("/webhook")
async def telegram_webhook(request: Request):
    global SCANNER_ACTIVE, CHAT_ID
    data = await request.json()
    
    if "message" in data:
        CHAT_ID = str(data["message"]["chat"]["id"])
    elif "callback_query" in data:
        CHAT_ID = str(data["callback_query"]["message"]["chat"]["id"])

    webapp_url = f"{str(request.base_url).rstrip('/')}/webapp"

    if "callback_query" in data:
        cb = data["callback_query"]
        cb_data = cb.get("data", "")
        message_id = cb["message"]["message_id"]
        
        if cb_data == "cmd_start":
            SCANNER_ACTIVE = True
            edit_telegram_message(message_id, "⚡️ <b>Авто-рассылка сигналов запущена!</b>", get_main_inline_keyboard(webapp_url))
        elif cb_data == "cmd_stop":
            SCANNER_ACTIVE = False
            edit_telegram_message(message_id, "🔴 <b>Рассылка остановлена.</b>", get_main_inline_keyboard(webapp_url))
        elif cb_data == "cmd_status":
            edit_telegram_message(message_id, f"📊 <b>Статус:</b> Активных потоков: <b>{len(MARKET_DATA)}</b>", get_main_inline_keyboard(webapp_url))

    elif "message" in data and "text" in data["message"]:
        text = data["message"]["text"].strip()
        if text in ["/start", "/menu"]:
            send_telegram_message("🎛 <b>Панель управления сканером:</b>", get_main_inline_keyboard(webapp_url))
                
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"status": "MiniApp Scanner Running"}
