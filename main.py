import json
import time
import os
import threading
import requests

# === ТВОИ ДАННЫЕ TELEGRAM ===
TELEGRAM_BOT_TOKEN = "8381163993:AAEaJ8256hIp33Gj3ooBM_a1p9p37wgQPog"
TELEGRAM_CHAT_ID = "6371759359"

class RiskManager:
    """Модуль Мани-Менеджмента (Лесенка Мартингейла)"""
    def __init__(self, initial_balance=100.0, base_bet=1.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.base_bet = base_bet
        self.ladder = [1.0, 2.3, 5.5, 13.0]  # Наша фиксированная лесенка
        self.current_step = 0
        self.total_wins = 0
        self.total_losses = 0

    def get_current_bet(self):
        return round(self.base_bet * self.ladder[self.current_step], 2)

    def process_result(self, is_win):
        bet = self.get_current_bet()
        if is_win:
            self.total_wins += 1
            self.current_balance += bet * 0.85
            self.current_step = 0  # Сброс на 1-й шаг
        else:
            self.total_losses += 1
            self.current_balance -= bet
            self.current_step += 1
            if self.current_step >= len(self.ladder):
                self.current_step = 0  # Сброс при круге просадки

class MicroSMCStrategy:
    """Полная торговая стратегия: Trend/Flat + SMC + Stoch + MACD + ATR"""
    def __init__(self, history_len=60):
        self.history_len = history_len
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
        """Определение фазы: TREND vs FLAT"""
        if len(self.candles) < 20:
            return "FLAT", 0.0001
        atr = self.calculate_atr(14)
        ema20 = self.calculate_ema(20)
        current_close = self.candles[-1]['close']
        
        # Дистанция от EMA20 в абсолютных значениях
        dist_from_ema = abs(current_close - ema20)
        
        # Если волатильность высокая и цена оторвалась от EMA -> ТРЕНД
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

        # Sweep (Снятие ликвидности)
        if c3['high'] > recent_high and c3['close'] < recent_high:
            return "BEARISH_SWEEP", "Закол локального хая (Sweep)"
        if c3['low'] < recent_low and c3['close'] > recent_low:
            return "BULLISH_SWEEP", "Закол локального лоя (Sweep)"

        # FVG (Имбаланс)
        if c3['low'] > c1['high']:
            return "BULLISH_FVG", "Бычий FVG (Имбаланс)"
        if c3['high'] < c1['low']:
            return "BEARISH_FVG", "Медвежий FVG (Имбаланс)"

        return None, None

    def analyze(self):
        if len(self.candles) < 20:
            return None, "Формирование свечной истории...", 1, "FLAT"

        regime, atr = self.detect_market_regime()
        stoch = self.calculate_stochastic(5)
        macd = self.calculate_macd(12, 26)
        smc_pattern, smc_desc = self.check_smc_structures()

        # Динамическая экспирация
        expiration = 1 if atr > 0.00015 else 2

        # --- РЕЖИМ 1: ТОРГОВЛЯ ВО ФЛЭТЕ (От границ / Заколы) ---
        if regime == "FLAT":
            if (smc_pattern == "BULLISH_SWEEP" or stoch < 18) and macd >= 0:
                return "CALL", f"[FLAT] {smc_desc or 'Отскок от нижней границы'} | Stoch:{stoch}", expiration, regime
            elif (smc_pattern == "BEARISH_SWEEP" or stoch > 82) and macd <= 0:
                return "PUT", f"[FLAT] {smc_desc or 'Отскок от верхней границы'} | Stoch:{stoch}", expiration, regime

        # --- РЕЖИМ 2: ТОРГОВЛЯ ПО ТРЕНДУ (На откате к FVG/OB) ---
        elif "TREND" in regime:
            if regime == "TREND_UP" and smc_pattern in ["BULLISH_FVG", "BULLISH_SWEEP"] and stoch < 35:
                return "CALL", f"[TREND UP] Ретест {smc_desc} | Stoch:{stoch}", expiration, regime
            elif regime == "TREND_DOWN" and smc_pattern in ["BEARISH_FVG", "BEARISH_SWEEP"] and stoch > 65:
                return "PUT", f"[TREND DOWN] Ретест {smc_desc} | Stoch:{stoch}", expiration, regime

        return None, f"Консолидация ({regime} | Stoch: {stoch})", expiration, regime

class TelegramInteractiveBot:
    """Интерактивный ТГ Бот с поддержкой кнопок управления лесенкой"""
    def __init__(self, risk_manager):
        self.rm = risk_manager
        self.last_update_id = 0

    def send_signal(self, signal, reason, expiration, regime):
        bet_amount = self.rm.get_current_bet()
        step = self.rm.current_step + 1
        emoji = "🟢" if signal == "CALL" else "🔴"

        text = (
            f"📊 **СИГНАЛ POCKET OPTION (5s Micro-SMC)**\n\n"
            f" Направление: {emoji} **{signal}**\n"
            f" 🌐 Фаза рынка: `{regime}`\n"
            f" 🎯 Структура: `{reason}`\n"
            f" ⏱ Экспирация: **{expiration} мин.** (по ATR)\n"
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
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": reply_markup
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"[!] Ошибка отправки в Telegram: {e}")

    def listen_callbacks(self):
        while True:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={self.last_update_id + 1}&timeout=10"
                res = requests.get(url, timeout=12).json()
                if res.get("ok"):
                    for update in res.get("result", []):
                        self.last_update_id = update["update_id"]
                        if "callback_query" in update:
                            cq = update["callback_query"]
                            data = cq["data"]
                            
                            if data == "win":
                                self.rm.process_result(is_win=True)
                                msg = f"✅ Плюс! Шаг сброшен на 1. Баланс: ${round(self.rm.current_balance, 2)}"
                            elif data == "loss":
                                self.rm.process_result(is_win=False)
                                msg = f"❌ Минус. Переход на шаг {self.rm.current_step + 1} (${self.rm.get_current_bet()})"

                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cq["id"], "text": msg})
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": f"📋 **Статус:** {msg}", "parse_mode": "Markdown"})
            except Exception:
                pass
            time.sleep(2)

if __name__ == "__main__":
    risk_manager = RiskManager(initial_balance=100.0, base_bet=1.0)
    tg_bot = TelegramInteractiveBot(risk_manager)
    strategy = MicroSMCStrategy()

    threading.Thread(target=tg_bot.listen_callbacks, daemon=True).start()

    print("=== Бот запущен (Trend/Flat + SMC + ATR + Лесенка + ТГ) ===")
    
    # Симулятор тикового потока для локальной проверки
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
                    
                    print(f"[{time.strftime('%H:%M:%S')}] 5s: {ticks[-1]} | {regime} | {reason}")
                    
                    if signal:
                        print(f"[+] СИГНАЛ: {signal} ({reason}) -> Отправка в Telegram...")
                        tg_bot.send_signal(signal, reason, exp, regime)
                        time.sleep(30) # Кулдаун пауза
                    ticks = []
                last_candle = time.time()
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n[!] Остановлено пользователем.")
