import os
import time
import json
import threading
import requests
import websocket
from flask import Flask

# =====================================================================
# 1. FLASK KEEP-ALIVE (Обеспечение порта для Render)
# =====================================================================
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Pocket Option Multi-TF SMC Bot Status: ACTIVE", 200

def start_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=start_flask, daemon=True).start()


# =====================================================================
# 2. КОНФИГУРАЦИЯ И СЕТКА 24 АКТИВОВ (БЕЗ СЫРЬЯ)
# =====================================================================
TELEGRAM_BOT_TOKEN = "8381163993:AAEaJ8256hIp33Gj3ooBM_a1p9p37wgQPog"
TELEGRAM_CHAT_ID = "6371759359"

ASSETS = {
    # Валютные пары OTC
    "EURUSD_otc": "EUR/USD OTC", "GBPUSD_otc": "GBP/USD OTC", "USDJPY_otc": "USD/JPY OTC",
    "AUDUSD_otc": "AUD/USD OTC", "USDCAD_otc": "USD/CAD OTC", "USDCHF_otc": "USD/CHF OTC",
    "EURGBP_otc": "EUR/GBP OTC", "EURJPY_otc": "EUR/JPY OTC", "GBPJPY_otc": "GBP/JPY OTC",
    # Валютные пары Real
    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD", "USDCHF": "USD/CHF",
    # Акции OTC
    "#AAPL_otc": "Apple OTC", "#TSLA_otc": "Tesla OTC", "#AMZN_otc": "Amazon OTC",
    "#MSFT_otc": "Microsoft OTC", "#GOOG_otc": "Google OTC", "#META_otc": "Meta OTC",
    "#NVDA_otc": "Nvidia OTC",
    # Акции Real
    "#AAPL": "Apple Real", "#TSLA": "Tesla Real"
}


# =====================================================================
# 3. МЕНЕДЖЕР РИСКОВ (ЛЕСЕНКА МАРТИНГЕЙЛА 4 ШАГА)
# =====================================================================
class RiskManager:
    def __init__(self, initial_balance=100.0, base_bet=1.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.base_bet = base_bet
        self.ladder = [1.0, 2.3, 5.5, 13.0]
        self.current_step = 0

    def get_bet(self) -> float:
        return round(self.base_bet * self.ladder[self.current_step], 2)

    def process_result(self, is_win: bool):
        bet = self.get_bet()
        if is_win:
            self.current_balance += bet * 0.85
            self.current_step = 0
        else:
            self.current_balance -= bet
            self.current_step += 1
            if self.current_step >= len(self.ladder):
                self.current_step = 0


# =====================================================================
# 4. ЯДРО СТРАТЕГИИ (M5 -> M1 -> S15)
# =====================================================================
class StrategyEngine:
    def __init__(self):
        self.candles_m5 = []
        self.candles_m1 = []
        self.candles_s15 = []

    def clear(self):
        self.candles_m5.clear()
        self.candles_m1.clear()
        self.candles_s15.clear()

    def update_candles(self, tf: str, candles: list):
        if tf == "M5":
            self.candles_m5 = candles[-60:]
        elif tf == "M1":
            self.candles_m1 = candles[-60:]
        elif tf == "S15":
            self.candles_s15 = candles[-60:]

    def _ema(self, prices: list, period: int) -> float:
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        k = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = (price * k) + (ema * (1 - k))
        return ema

    def _stochastic(self, candles: list, period=5, smooth_k=3) -> float:
        if len(candles) < period:
            return 50.0
        raw_k = []
        for i in range(len(candles) - period + 1, len(candles) + 1):
            sub = candles[i - period:i]
            closes = [c['close'] for c in sub]
            highs = [c['high'] for c in sub]
            lows = [c['low'] for c in sub]
            lowest, highest = min(lows), max(highs)
            if highest == lowest:
                raw_k.append(50.0)
            else:
                raw_k.append(((closes[-1] - lowest) / (highest - lowest)) * 100)
        return sum(raw_k[-smooth_k:]) / smooth_k if len(raw_k) >= smooth_k else raw_k[-1]

    def _macd(self, candles: list, fast=8, slow=21, signal=5) -> tuple:
        if len(candles) < slow + signal:
            return 0.0, 0.0, 0.0
        closes = [c['close'] for c in candles]
        macd_series = []
        for i in range(slow, len(closes) + 1):
            sub = closes[:i]
            macd_series.append(self._ema(sub, fast) - self._ema(sub, slow))
        k = 2 / (signal + 1)
        sig_line = sum(macd_series[:signal]) / signal
        for val in macd_series[signal:]:
            sig_line = (val * k) + (sig_line * (1 - k))
        return macd_series[-1], sig_line, macd_series[-1] - sig_line

    def _atr(self, candles: list, period=14) -> float:
        if len(candles) < period + 1:
            return 0.0001
        tr_list = []
        for i in range(1, len(candles)):
            h, l, pc = candles[i]['high'], candles[i]['low'], candles[i-1]['close']
            tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
        return sum(tr_list[-period:]) / period

    def _analyze_m5(self) -> dict:
        closes = [c['close'] for c in self.candles_m5]
        ema20 = self._ema(closes, 20)
        ema50 = self._ema(closes, 50)
        trend = "UP" if ema20 > ema50 else "DOWN"
        
        sub = self.candles_m5[-30:]
        sr_high, sr_low = max(c['high'] for c in sub), min(c['low'] for c in sub)
        atr = self._atr(self.candles_m5, 14)
        
        return {
            "trend": trend,
            "near_support": abs(closes[-1] - sr_low) <= (atr * 1.2),
            "near_resistance": abs(closes[-1] - sr_high) <= (atr * 1.2),
            "atr": atr
        }

    def _analyze_m1(self) -> dict:
        c1 = self.candles_m1[-1]
        prev_sub = self.candles_m1[-15:-1]
        recent_high = max(c['high'] for c in prev_sub)
        recent_low = min(c['low'] for c in prev_sub)
        
        return {
            "bull_sweep": c1['low'] < recent_low and c1['close'] > recent_low,
            "bear_sweep": c1['high'] > recent_high and c1['close'] < recent_high,
            "stoch": self._stochastic(self.candles_m1, 5, 3),
            "macd_hist": self._macd(self.candles_m1, 8, 21, 5)[2]
        }

    def _check_s15_trigger(self, direction: str) -> bool:
        if len(self.candles_s15) < 2:
            return False
        last_s15 = self.candles_s15[-1]
        if direction == "CALL" and last_s15['close'] > last_s15['open']:
            return True
        if direction == "PUT" and last_s15['close'] < last_s15['open']:
            return True
        return False

    def get_signal(self) -> tuple:
        if len(self.candles_m5) < 30 or len(self.candles_m1) < 15 or len(self.candles_s15) < 2:
            return None, "Набор истории свечей...", 0

        m5 = self._analyze_m5()
        m1 = self._analyze_m1()
        expiration = 1 if self._atr(self.candles_m1, 14) > (m5['atr'] * 0.4) else 2

        # CALL (Покупка)
        if (m5['trend'] == "UP" or m5['near_support']) and m1['bull_sweep']:
            if m1['stoch'] <= 20 and m1['macd_hist'] >= 0:
                if self._check_s15_trigger("CALL"):
                    return "CALL", f"Sweep Low M1 | Stoch:{round(m1['stoch'],1)} | S15 OK", expiration

        # PUT (Продажа)
        if (m5['trend'] == "DOWN" or m5['near_resistance']) and m1['bear_sweep']:
            if m1['stoch'] >= 80 and m1['macd_hist'] <= 0:
                if self._check_s15_trigger("PUT"):
                    return "PUT", f"Sweep High M1 | Stoch:{round(m1['stoch'],1)} | S15 OK", expiration

        return None, "Поиск сетапа...", 0


# =====================================================================
# 5. WEBSOCKET СТРИМЕР КОТИРОВОК POCKET OPTION
# =====================================================================
class PocketDataStreamer:
    def __init__(self, strategy_engine):
        self.strategy = strategy_engine
        self.current_asset = "EURUSD_otc"
        self.ws = None
        self.ticks_s15 = []
        self.ticks_m1 = []
        self.ticks_m5 = []
        self.running = False

    def change_asset(self, new_asset: str):
        self.current_asset = new_asset
        self.ticks_s15.clear()
        self.ticks_m1.clear()
        self.ticks_m5.clear()
        self.strategy.clear()
        if self.ws and self.ws.sock and self.ws.sock.connected:
            sub_msg = json.dumps({"action": "subscribe", "asset": self.current_asset})
            self.ws.send(sub_msg)

    def _process_tick(self, price: float):
        now = time.time()
        self.ticks_s15.append(price)
        self.ticks_m1.append(price)
        self.ticks_m5.append(price)

        # Сборка S15 (каждые 15 сек)
        if len(self.ticks_s15) >= 15:
            candle = {"open": self.ticks_s15[0], "high": max(self.ticks_s15), "low": min(self.ticks_s15), "close": self.ticks_s15[-1]}
            self.strategy.candles_s15.append(candle)
            self.ticks_s15.clear()

        # Сборка M1 (каждые 60 сек)
        if len(self.ticks_m1) >= 60:
            candle = {"open": self.ticks_m1[0], "high": max(self.ticks_m1), "low": min(self.ticks_m1), "close": self.ticks_m1[-1]}
            self.strategy.candles_m1.append(candle)
            self.ticks_m1.clear()

        # Сборка M5 (каждые 300 сек)
        if len(self.ticks_m5) >= 300:
            candle = {"open": self.ticks_m5[0], "high": max(self.ticks_m5), "low": min(self.ticks_m5), "close": self.ticks_m5[-1]}
            self.strategy.candles_m5.append(candle)
            self.ticks_m5.clear()

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "price" in data:
                self._process_tick(float(data["price"]))
        except Exception:
            pass

    def start(self):
        def run():
            while True:
                try:
                    # Подключение к серверу котировок Pocket Option
                    self.ws = websocket.WebSocketApp(
                        "wss://api.pocketoption.com/flags/stream",
                        on_message=self._on_message
                    )
                    self.ws.run_forever(ping_interval=20, ping_timeout=10)
                except Exception:
                    time.sleep(5)
        threading.Thread(target=run, daemon=True).start()


# =====================================================================
# 6. ИНТЕРАКТИВНЫЙ ТЕЛЕГРАМ БОТ
# =====================================================================
class TelegramBot:
    def __init__(self, rm: RiskManager, strategy: StrategyEngine, streamer: PocketDataStreamer):
        self.rm = rm
        self.strategy = strategy
        self.streamer = streamer
        self.last_update_id = 0

    def send_msg(self, text, reply_markup=None):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception:
            pass

    def show_menu(self):
        keyboard = []
        row = []
        for code, name in ASSETS.items():
            prefix = "✅ " if code == self.streamer.current_asset else ""
            row.append({"text": f"{prefix}{name}", "callback_data": f"set_{code}"})
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        self.send_msg("🎛 **Выберите актив для анализа (M5->M1->S15):**", {"inline_keyboard": keyboard})

    def send_signal(self, signal: str, reason: str, exp: int):
        emoji = "🟢" if signal == "CALL" else "🔴"
        asset_name = ASSETS.get(self.streamer.current_asset, self.streamer.current_asset)
        step = self.rm.current_step + 1

        text = (
            f"📊 **СИГНАЛ POCKET OPTION (MULTI-TF SMC)**\n\n"
            f"📌 Актив: **{asset_name}**\n"
            f"Направление: {emoji} **{signal}**\n"
            f"🎯 Сетап: `{reason}`\n"
            f"⏱ Экспирация: **{exp} мин.**\n"
            f"💰 Шаг: **{step} из 4** (Ставка: **${self.rm.get_bet()}**)\n"
            f"📈 Баланс: `${round(self.rm.current_balance, 2)}`\n"
            f"⏰ Время: {time.strftime('%H:%M:%S')}"
        )
        markup = {
            "inline_keyboard": [[
                {"text": "✅ ПЛЮС", "callback_data": "win"},
                {"text": "❌ МИНУС", "callback_data": "loss"}
            ]]
        }
        self.send_msg(text, markup)

    def poll_updates(self):
        while True:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={self.last_update_id + 1}&timeout=10"
                res = requests.get(url, timeout=12).json()
                if res.get("ok"):
                    for update in res.get("result", []):
                        self.last_update_id = update["update_id"]
                        
                        if "message" in update and "text" in update["message"]:
                            if update["message"]["text"] in ["/start", "/menu"]:
                                self.show_menu()

                        if "callback_query" in update:
                            cq = update["callback_query"]
                            data = cq["data"]
                            
                            if data.startswith("set_"):
                                new_asset = data.replace("set_", "")
                                self.streamer.change_asset(new_asset)
                                self.send_msg(f"🎯 Актив переключен на: **{ASSETS.get(new_asset)}**")
                            
                            elif data in ["win", "loss"]:
                                self.rm.process_result(data == "win")
                                status = "✅ Плюс! Сброс на 1-й шаг." if data == "win" else f"❌ Минус. Переход на шаг {self.rm.current_step + 1}"
                                self.send_msg(f"📋 {status}\nТекущий баланс: **${round(self.rm.current_balance, 2)}**")

            except Exception:
                pass
            time.sleep(2)


# =====================================================================
# 7. ГЛАВНЫЙ ЦИКЛ И ТОЧКА ВХОДА
# =====================================================================
if __name__ == "__main__":
    rm = RiskManager()
    strategy = StrategyEngine()
    streamer = PocketDataStreamer(strategy)
    bot = TelegramBot(rm, strategy, streamer)

    # Запуск параллельных потоков
    streamer.start()
    threading.Thread(target=bot.poll_updates, daemon=True).start()

    bot.show_menu()
    print("=== Бот SMC Multi-TF (M5->M1->S15) успешно запущен ===")

    # Бесконечный цикл анализа
    while True:
        sig, reason, exp = strategy.get_signal()
        if sig:
            bot.send_signal(sig, reason, exp)
            time.sleep(exp * 60) # Защита от дублирования сигналов во время экспирации
        
        time.sleep(1)
