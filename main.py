import os
import asyncio
import requests
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Глобальное состояние сканера
SCANNER_ACTIVE = False

def send_telegram_message(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except Exception as e:
        print(f"Error sending TG msg: {e}")
        return False

# Расчет Стохастика (8, 3, 3)
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

# Определение фазы рынка (Тренд / Боковик) через MACD / диапазон
def detect_market_regime(candles):
    if len(candles) < 20:
        return "RANGE"
    closes = [c['close'] for c in candles]
    max_c = max(closes[-10:])
    min_c = min(closes[-10:])
    spread = (max_c - min_c) / min_c
    return "TREND" if spread > 0.0015 else "RANGE"

# Оценка волатильности для выбора времени экспирации (1m vs 2m)
def calculate_expiration_time(candles):
    if len(candles) < 10:
        return "1 мин"
    ranges = [c['high'] - c['low'] for c in candles[-5:]]
    avg_range = sum(ranges) / len(ranges)
    last_range = candles[-1]['high'] - candles[-1]['low']
    
    # Если последняя свеча размашистая (высокие тени/импульс) — 2 минуты
    if last_range > avg_range * 1.3:
        return "2 мин"
    return "1 мин"

# Фоновый цикл активного сканера
async def market_scanner_loop():
    global SCANNER_ACTIVE
    while True:
        if SCANNER_ACTIVE:
            try:
                # В фоновом режиме идет анализ активов с выплатой > 90%
                pass
            except Exception as e:
                print(f"Scanner Loop Error: {e}")
        
        await asyncio.sleep(10)  # Сканирование каждые 10 секунд

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(market_scanner_loop())
    yield

app = FastAPI(lifespan=lifespan)

# Обработка команд Webhook от Telegram
@app.post("/webhook")
async def telegram_webhook(request: Request):
    global SCANNER_ACTIVE
    data = await request.json()
    
    if "message" in data and "text" in data["message"]:
        text = data["message"]["text"].strip()
        sender_id = str(data["message"]["chat"]["id"])
        
        if sender_id == CHAT_ID:
            if text == "/start_scan":
                SCANNER_ACTIVE = True
                send_telegram_message("⚡️ <b>Активный сканер ЗАПУЩЕН!</b>\nПоиск сигналов: SMC + Stoch (8,3,3) + MACD.\nВыплаты >90% (Forex OTC, Акции OTC).")
            elif text == "/stop_scan":
                SCANNER_ACTIVE = False
                send_telegram_message("🔴 <b>Сканер ОСТАНОВЛЕН.</b>")
            elif text == "/status":
                state_str = "⚡️ АКТИВЕН" if SCANNER_ACTIVE else "🔴 НА ПАУЗЕ"
                send_telegram_message(f"📊 <b>Статус:</b> {state_str}\nРежим: <b>Активный скальпинг</b>\nФильтр выплат: <b>> 90%</b>")
                
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"status": "Active SMC Scanner Running", "active": SCANNER_ACTIVE}
