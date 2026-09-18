import json
import time
import os
import threading
import requests
from flask import Flask

# === ФИКТИВНЫЙ ВЕБ-СЕРВЕР ДЛЯ RENDER (Убирает ошибку Port Scan Timeout) ===
app = Flask(__name__)

@app.route('/')
def home():
    return "Pocket Option Scanner is Running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Запускаем Flask в отдельном фоновом потоке
threading.Thread(target=run_flask, daemon=True).start()


# === НАСТРОЙКИ TELEGRAM ===
TELEGRAM_BOT_TOKEN = "8381163993:AAEaJ8256hIp33Gj3ooBM_a1p9p37wgQPog"
TELEGRAM_CHAT_ID = "6371759359"

# === СПИСОК АКТИВОВ (15 ВАЛЮТ + 12 АКЦИЙ) ===
ASSETS_CONFIG = {
    # 15 Валютных пар
    "EURUSD_otc": "EUR/USD OTC",
    "GBPUSD_otc": "GBP/USD OTC",
    "USDJPY_otc": "USD/JPY OTC",
    "AUDUSD_otc": "AUD/USD OTC",
    "USDCAD_otc": "USD/CAD OTC",
    "EURGBP_otc": "EUR/GBP OTC",
    "EURJPY_otc": "EUR/JPY OTC",
    "GBPJPY_otc": "GBP/JPY OTC",
    "AUDJPY_otc": "AUD/JPY OTC",
    "NZDUSD_otc": "NZD/USD OTC",
    "EURUSD": "EUR/USD (Real)",
    "GBPUSD": "GBP/USD (Real)",
    "USDJPY": "USD/JPY (Real)",
    "AUDUSD": "AUD/USD (Real)",
    "USDCAD": "USD/CAD (Real)",

    # 12 Акций
    "#AAPL_otc": "Apple OTC",
    "#TSLA_otc": "Tesla OTC",
    "#MSFT_otc": "Microsoft OTC",
    "#AMZN_otc": "Amazon OTC",
    "#GOOG_otc": "Google OTC",
    "#META_otc": "Meta OTC",
    "#NVDA_otc": "NVIDIA OTC",
    "#NFLX_otc": "Netflix OTC",
    "#AMD_otc": "AMD OTC",
    "#INTC_otc": "Intel OTC",
    "#BA_otc": "Boeing OTC",
    "#KO_otc": "Coca-Cola OTC"
}

class RiskManager:
    """Управление рисками и лесенка"""
    def __init__(self, initial_balance=100.0, base_bet=1.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.base_bet = base_bet
        self.ladder = [1.0, 2.3, 5.5, 13.0]
        self.current_step = 0

    def get_current_bet(self):
        return round(self.base_bet * self.ladder[self.current_step], 2)

    def process_result(self, is_win):
        bet = self.get_current_bet()
        if is_win:
            self.current_balance += bet * 0.85
            self.current_step = 0
        else:
            self.current_balance -= bet
            self.current_step += 1
            if self.current_step >= len(self.ladder):
                self.current_step = 0

class MicroSMCStrategy:
    """Стратегия SMC + Indicators"""
    def __init__(self, history_len=60):
        self.history_len = history_len
        self.candles = []

    def reset_candles(self):
        self.candles = []

    def add_candle(self, open_p, high_p, low_p, close_p):
        self.candles.append({
            'open': open_p, 'high': high_p, 'low': low_p, 'close': close_p, 'time': time.time()
        })
        if len(self.candles) > self.history_len:
            self.candles.pop(0)

    def calculate_ema(self, period=20):
        if len(self.candles) < period:
            return self.candles[-1]['close'] if self.candles else 0.0
        closes = [c['close'] for c in self.candles]
        alpha = 2 / (period + 1)
        val = closes[0]
        for p in closes[1:]:
            val = alpha * p + (1 - alpha) * val
        return val

    def calculate_atr(self, period=14):
        if len(self.candles) < period + 1:
            return 0.0001
        tr_list = []
        for i in range(1, len(self.candles)):
            c, prev_c = self.candles[i], self.candles[i-1]
            tr = max(c['high'] - c['low'], abs(c['high'] - prev_c['close']), abs(c['low'] - prev_c['close']))
            tr_list.append(tr)
        return sum(tr_list[-period:]) / period

    def calculate_stochastic(self, period=5):
        if len(self.candles) < period:
            return 50.0
        closes = [c['close'] for c in self.candles[-period:]]
        highs = [c['high'] for c in self.candles[-period:]]
        lows = [c['low'] for c in self.candles[-period:]]
        lowest_low, highest_high = min(lows), max(highs)
        if highest_high == lowest_low:
            return 50.0
        return round(((closes[-1] - lowest_low) / (highest_high - lowest_low)) * 100, 2)

    def calculate_macd(self, fast=12, slow=26):
        if len(self.candles) < slow:
            return 0.0
        closes = [c['close'] for c in self.candles]
        def ema(data, window):
            alpha = 2 / (window + 1)
            val = data[0]
            for p in data[1:]:
                val = alpha * p + (1 - alpha) * val
            return val
        return round(ema(closes[-fast:], fast) - ema(closes[-slow:], slow), 6)

    def detect_market_regime(self):
        if len(self.candles) < 20:
            return "FLAT", 0.0001
        atr = self.calculate_atr(14)
        ema20 = self.calculate_ema(20)
        current_close = self.candles[-1]['close']
        dist_from_ema = abs(current_close - ema20)
        
        if atr > 0.00012 and dist_from_ema > (atr * 0.8):
            regime = "TREND_UP" if current_close > ema20 else "TREND_DOWN"
        else:
            regime = "FLAT"
        return regime, atr

    def check_smc_structures(self):
        if len(self.candles) < 15:
            return None, None
        c1, c2, c3 = self.candles[-3], self.candles[-2], self.candles[-1]
        recent_high = max(c['high'] for c in self.candles[-15:-1])
        recent_low = min(c['low'] for c in self.candles[-15:-1])

        if c3['high'] > recent_high and c3['close'] < recent_high:
            return "BEARISH_SWEEP", "Закол локального хая (Sweep)"
        if c3['low'] < recent_low and c3['close'] > recent_low:
            return "BULLISH_SWEEP", "Закол локального лоя (Sweep)"
        if c3['low'] > c1['high']:
            return "BULLISH_FVG", "Бычий FVG (Имбаланс)"
        if c3['high'] < c1['low']:
            return "BEARISH_FVG", "Медвежий FVG (Имбаланс)"

        return None, None

    def analyze(self):
        if len(self.candles) < 20:
            return None, "Сбор свечной истории...", 1, "FLAT"

        regime, atr = self.detect_market_regime()
        stoch = self.calculate_stochastic(5)
        macd = self.calculate_macd(12, 26)
        smc_pattern, smc_desc = self.check_smc_structures()

        expiration = 1 if atr > 0.00015 else 2

        if regime == "FLAT":
            if (smc_pattern in ["BULLISH_SWEEP", "BULLISH_FVG"] or (smc_pattern is None and stoch < 20)) and stoch <= 22 and macd >= 0:
                return "CALL", f"[FLAT] {smc_desc or 'Отскок от нижней границы'} | Stoch:{stoch}", expiration, regime
            elif (smc_pattern in ["BEARISH_SWEEP", "BEARISH_FVG"] or (smc_pattern is None and stoch > 80)) and stoch >= 78 and macd <= 0:
                return "PUT", f"[FLAT] {smc_desc or 'Отскок от верхней границы'} | Stoch:{stoch}", expiration, regime

        elif "TREND" in regime:
            if regime == "TREND_UP" and smc_pattern in ["BULLISH_FVG", "BULLISH_SWEEP"] and stoch < 35:
                return "CALL", f"[TREND UP] Ретест {smc_desc} | Stoch:{stoch}", expiration, regime
            elif regime == "TREND_DOWN" and smc_pattern in ["BEARISH_FVG", "BEARISH_SWEEP"] and stoch > 65:
                return "PUT", f"[TREND DOWN] Ретест {smc_desc} | Stoch:{stoch}", expiration, regime

        return None, f"Консолидация ({regime} | Stoch: {stoch})", expiration, regime

class TelegramInteractiveBot:
    """ТГ Интерфейс с выбором активов"""
    def __init__(self, risk_manager, strategy):
        self.rm = risk_manager
        self.strategy = strategy
        self.active_asset_id = "EURUSD_otc"
        self.last_update_id = 0

    def send_asset_menu(self):
        """Отправка меню выбора из 27 активов"""
        keyboard = []
        items = list(ASSETS_CONFIG.items())
        for i in range(0, len(items), 2):
            row = [{"text": items[i][1], "callback_data": f"set_{items[i][0]}"}]
            if i + 1 < len(items):
                row.append({"text": items[i+1][1], "callback_data": f"set_{items[i+1][0]}"})
            keyboard.append(row)

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"🎛 **ВЫБОР АКТИВА ДЛЯ АНАЛИЗА**\nТекущий актив: **{ASSETS_CONFIG.get(self.active_asset_id)}**\n\nВыбери актив из списка:",
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": keyboard}
        }
        requests.post(url, json=payload)

    def send_signal(self, signal, reason, expiration, regime):
        bet_amount = self.rm.get_current_bet()
        step = self.rm.current_step + 1
        emoji = "🟢" if signal == "CALL" else "🔴"
        asset_name = ASSETS_CONFIG.get(self.active_asset_id, self.active_asset_id)

        text = (
            f"📊 **СИГНАЛ POCKET OPTION (5s SMC)**\n\n"
            f" 📌 Актив: **{asset_name}**\n"
            f" Направление: {emoji} **{signal}**\n"
            f" 🌐 Фаза рынка: `{regime}`\n"
            f" 🎯 Структура: `{reason}`\n"
            f" ⏱ Экспирация: **{expiration} мин.**\n"
            f" 💰 Шаг лесенки: **{step} из 4** (Ставка: **${bet_amount}**)\n"
            f" 📈 Баланс: `${round(self.rm.current_balance, 2)}`\n"
            f" ⏰ Время: {time.strftime('%H:%M:%S')}"
        )

        reply_markup = {
            "inline_keyboard": [[
                {"text": "✅ ПЛЮС", "callback_data": "win"},
                {"text": "❌ МИНУС", "callback_data": "loss"}
            ]]
        }

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown", "reply_markup": reply_markup})

    def listen_updates(self):
        while True:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={self.last_update_id + 1}&timeout=10"
                res = requests.get(url, timeout=12).json()
                if res.get("ok"):
                    for update in res.get("result", []):
                        self.last_update_id = update["update_id"]
                        
                        if "message" in update and "text" in update["message"]:
                            txt = update["message"]["text"]
                            if txt in ["/start", "/assets", "/menu"]:
                                self.send_asset_menu()

                        if "callback_query" in update:
                            cq = update["callback_query"]
                            data = cq["data"]
                            
                            if data.startswith("set_"):
                                new_asset = data.replace("set_", "")
                                self.active_asset_id = new_asset
                                self.strategy.reset_candles()
                                asset_name = ASSETS_CONFIG.get(new_asset)
                                
                                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cq["id"], "text": f"Актив изменен на {asset_name}"})
                                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🔄 **Бот переключен на актив:** `{asset_name}`\nНачинаю сбор 5s-свечей...", "parse_mode": "Markdown"})

                            elif data in ["win", "loss"]:
                                is_win = (data == "win")
                                self.rm.process_result(is_win)
                                status_txt = f"✅ Плюс! Шаг сброшен на 1." if is_win else f"❌ Минус. Шаг: {self.rm.current_step + 1}"
                                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cq["id"], "text": status_txt})
                                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": f"📋 **Статус:** {status_txt} | Баланс: ${round(self.rm.current_balance, 2)}", "parse_mode": "Markdown"})
            except Exception:
                pass
            time.sleep(2)

if __name__ == "__main__":
    risk_manager = RiskManager(initial_balance=100.0, base_bet=1.0)
    strategy = MicroSMCStrategy()
    tg_bot = TelegramInteractiveBot(risk_manager, strategy)

    threading.Thread(target=tg_bot.listen_updates, daemon=True).start()

    print("=== Бот запущен на Render ===")
    tg_bot.send_asset_menu()

    import random
    base_p = 1.08500
    ticks = []
    last_candle = time.time()

    try:
        while True:
            base_p += random.choice([-0.00004, -0.00001, 0.00001, 0.00005])
            ticks.append(round(base_p, 5))
            
            if time.time() - last_candle >= 5.0:
                if ticks:
                    strategy.add_candle(ticks[0], max(ticks), min(ticks), ticks[-1])
                    signal, reason, exp, regime = strategy.analyze()
                    
                    active_name = ASSETS_CONFIG.get(tg_bot.active_asset_id)
                    print(f"[{time.strftime('%H:%M:%S')}] [{active_name}] 5s: {ticks[-1]} | {regime} | {reason}")
                    
                    if signal:
                        print(f"[+] СИГНАЛ по {active_name}: {signal} -> Отправка в Telegram...")
                        tg_bot.send_signal(signal, reason, exp, regime)
                        time.sleep(30)
                    ticks = []
                last_candle = time.time()
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n[!] Остановлено.")
