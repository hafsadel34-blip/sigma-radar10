#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📡⚛️ SigmaRadar v1.2 – بدون pandas_ta/numba (يعمل على Python 3.14)
"""

import asyncio
import aiohttp
import pandas as pd
import numpy as np
import nest_asyncio
import logging
import json
import os
import threading
from datetime import datetime
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

try:
    import ccxt.async_support as ccxt
except ImportError:
    raise ImportError("مكتبة ccxt غير مثبتة. استخدم: pip install ccxt")
try:
    from telegram import Bot
except ImportError:
    Bot = None

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ═══════════════ الإعدادات ═══════════════
TELEGRAM_TOKEN = "8892386642:AAFrH8mz-XQjYDnsjY2RkPoJz7oMcbIDTdw"
CHAT_ID = "6499356593"
MIN_VOLUME = 100_000
MIN_SCORE = 40
MIN_RR = 1.8
TOP_N = 8
BLACKLIST_FILE = "sigma_blacklist.json"
ACTIVE_FILE = "sigma_active.json"

app = Flask(__name__)
is_scanning = False

# ═══════════════ حساب المؤشرات يدوياً (بدون pandas_ta) ═══════════════
def calc_rsi(close, period=14):
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_adx(high, low, close, period=14):
    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    # Directional Movement
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    plus_di = 100 * (pd.Series(plus_dm).rolling(window=period).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm).rolling(window=period).mean() / atr)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    return adx

def calc_atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

def calc_stoch_rsi(close, period=14):
    rsi = calc_rsi(close, period)
    min_rsi = rsi.rolling(window=period).min()
    max_rsi = rsi.rolling(window=period).max()
    stoch = 100 * (rsi - min_rsi) / (max_rsi - min_rsi)
    return stoch

def calc_cmf(df, period=20):
    mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
    mfv = mfm * df['vol']
    cmf = mfv.rolling(window=period).sum() / df['vol'].rolling(window=period).sum()
    return cmf

# ═══════════════ إدارة الذاكرة ═══════════════
class SmartMemory:
    def __init__(self, blacklist_file=BLACKLIST_FILE, active_file=ACTIVE_FILE):
        self.blacklist_file = blacklist_file
        self.active_file = active_file
        self.blacklist = self._load(blacklist_file)
        self.active = self._load(active_file)

    def _load(self, filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except:
            return {}

    def _save(self, filename, data):
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"فشل حفظ {filename}: {e}")

    def is_blocked(self, symbol: str, cmf_1h: float) -> bool:
        if symbol not in self.blacklist:
            return False
        if cmf_1h > 0.2:
            logger.info(f"🔓 {symbol}: تم رفع الحظر – CMF={cmf_1h:.3f}")
            del self.blacklist[symbol]
            self._save(self.blacklist_file, self.blacklist)
            return False
        return True

    def add_failure(self, symbol: str, entry: float, sl: float):
        self.blacklist[symbol] = {'entry': entry, 'sl': sl, 'time': datetime.now().isoformat()}
        self._save(self.blacklist_file, self.blacklist)
        logger.info(f"⛔ {symbol}: أضيفت للقائمة السوداء")

    def is_active(self, symbol: str) -> bool:
        return symbol in self.active and self.active[symbol].get('status') != 'closed'

    def save_active(self, symbol: str, data: dict):
        self.active[symbol] = data
        self._save(self.active_file, self.active)

    def close_active(self, symbol: str, status: str):
        if symbol in self.active:
            self.active[symbol]['status'] = status
            self._save(self.active_file, self.active)

# ═══════════════ الرادار ═══════════════
class SigmaRadar:
    def __init__(self):
        self.exchange = None
        self.session = None
        self.semaphore = asyncio.Semaphore(30)
        self.memory = SmartMemory()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        self.exchange = ccxt.kucoin({'enableRateLimit': True})
        return self

    async def __aexit__(self, *args):
        if self.exchange: await self.exchange.close()
        if self.session: await self.session.close()

    async def fetch_btc(self):
        try:
            ticker = await self.exchange.fetch_ticker('BTC/USDT')
            change = ticker.get('percentage', 0.0)
            if change > 1.0: regime = "BULL"
            elif change < -1.0: regime = "BEAR"
            else: regime = "NEUTRAL"
            return regime, change
        except:
            return "NEUTRAL", 0.0

    async def get_symbols(self, limit=300):
        try:
            tickers = await self.exchange.fetch_tickers()
            symbols = []
            for sym, t in tickers.items():
                if not sym.endswith('/USDT'): continue
                if sym.split('/')[0] in {'USDC','PAX','DAI','TUSD','BUSD','FDUSD','USDP'}: continue
                if t.get('quoteVolume', 0) >= MIN_VOLUME:
                    symbols.append(sym)
            symbols.sort(key=lambda s: tickers[s]['quoteVolume'], reverse=True)
            return symbols[:limit]
        except:
            return []

    async def analyze(self, symbol: str, regime: str):
        try:
            ohlcv_1h, ohlcv_1d = await asyncio.gather(
                self.exchange.fetch_ohlcv(symbol, timeframe='1h', limit=200),
                self.exchange.fetch_ohlcv(symbol, timeframe='1d', limit=90)
            )
            if not ohlcv_1h or len(ohlcv_1h) < 50: return None
            df = pd.DataFrame(ohlcv_1h, columns=['time','open','high','low','close','vol'])
            df_daily = pd.DataFrame(ohlcv_1d, columns=['time','open','high','low','close','vol']) if ohlcv_1d else pd.DataFrame()

            # حساب المؤشرات يدوياً
            df['RSI'] = calc_rsi(df['close'])
            df['StochK'] = calc_stoch_rsi(df['close'])
            df['ADX'] = calc_adx(df['high'], df['low'], df['close'])
            df['ATR'] = calc_atr(df['high'], df['low'], df['close'])
            df['CMF_1h'] = calc_cmf(df)

            price = df['close'].iloc[-1]
            cmf_1h = df['CMF_1h'].iloc[-1]
            name = symbol.split('/')[0]

            if self.memory.is_blocked(name, cmf_1h):
                return None
            if self.memory.is_active(name):
                return None

            ticker = await self.exchange.fetch_ticker(symbol)
            change_24h = ticker.get('percentage', 0.0)
            volume_24h = ticker.get('quoteVolume', 0)

            rsi = df['RSI'].iloc[-1]
            stoch_k = df['StochK'].iloc[-1]
            adx = df['ADX'].iloc[-1]
            atr = df['ATR'].iloc[-1]
            atr_pct = (atr / price) * 100 if price > 0 else 2.0

            # Drawdown
            ath = df_daily['high'].max() if not df_daily.empty else price
            dd = ((ath - price) / ath) * 100 if ath > 0 else 0
            if dd >= 70: zone = '🟢🟢 تجميع مؤسسي عميق'
            elif dd >= 50: zone = '🟢 منطقة تجميع قوية'
            elif dd >= 30: zone = '🟡 تراجع معتدل'
            elif dd >= 15: zone = '⚪ تصحيح طبيعي'
            else: zone = '🔴 قريب من القمة'

            # Alpha Composite (تقريبي)
            returns = df['close'].pct_change()
            mom = returns.rolling(20).mean().iloc[-1] if len(returns) >= 20 else 0
            sma20 = df['close'].rolling(20).mean().iloc[-1] if len(df) >= 20 else price
            mr = (price - sma20) / sma20 if sma20 > 0 else 0
            alpha = (mom * 100) - (mr * 50)

            # VWAP Deviation
            if len(df) >= 20:
                typical = (df['high'] + df['low'] + df['close']) / 3
                vp = typical * df['vol']
                vwap = vp.rolling(20).sum() / df['vol'].rolling(20).sum()
                vwap_dev = (price - vwap.iloc[-1]) / vwap.iloc[-1] if vwap.iloc[-1] != 0 else 0
            else:
                vwap_dev = 0

            score = 0
            signals = []
            if regime == "BULL":
                if alpha > 2.0: score += 30; signals.append(f"ألفا قوي {alpha:.2f}")
                if 5 < change_24h < 25: score += 20; signals.append(f"زخم +{change_24h:.1f}%")
                if 50 < rsi < 70: score += 15; signals.append("RSI صحي")
            elif regime == "BEAR":
                if change_24h > 0: score += 30; signals.append(f"مقاوم +{change_24h:.1f}%")
                if vwap_dev < -0.03: score += 25; signals.append(f"خصم VWAP {vwap_dev*100:.1f}%")
                if rsi < 35: score += 20; signals.append(f"تشبع بيعي RSI={rsi:.1f}")
            else:
                if vwap_dev < -0.02: score += 20; signals.append(f"تحت VWAP {vwap_dev*100:.1f}%")
                if alpha > 1.0: score += 20; signals.append(f"ألفا إيجابي {alpha:.2f}")
                if rsi < 40: score += 15

            if adx > 25: score += 10; signals.append(f"ADX قوي {adx:.1f}")
            if atr_pct > 3: score += 5

            if score < MIN_SCORE: return None

            sl_pct = max(2.0, min(15.0, atr_pct * 1.5))
            tp1_pct = max(3.0, min(25.0, atr_pct * 2.0))
            tp2_pct = tp1_pct * 1.8

            tp1 = price * (1 + tp1_pct/100)
            tp2 = price * (1 + tp2_pct/100)
            sl = price * (1 - sl_pct/100)

            rr = (tp2_pct / sl_pct) if sl_pct > 0 else 0
            if rr < MIN_RR: return None

            # حفظ في التتبع
            self.memory.save_active(name, {
                'entry': price, 'tp1': tp1, 'tp2': tp2, 'sl': sl,
                'tp1_pct': round(tp1_pct,1), 'tp2_pct': round(tp2_pct,1), 'sl_pct': round(sl_pct,1),
                'entry_time': datetime.now().isoformat(), 'status': 'active',
                'cmf_1h': cmf_1h, 'change_24h': change_24h, 'volume_24h': volume_24h,
                'drawdown': round(dd,1), 'zone': zone,
                'rsi': round(rsi,1), 'adx': round(adx,1), 'stoch_k': round(stoch_k,1),
                'signals': signals[:4], 'score': score
            })

            return {
                'symbol': name, 'score': score, 'price': price,
                'change_24h': change_24h, 'volume_24h': volume_24h,
                'drawdown': {'ath': ath, 'drawdown': round(dd,1), 'zone': zone},
                'rsi': round(rsi,1), 'stoch_k': round(stoch_k,1), 'adx': round(adx,1),
                'alpha': round(alpha,2), 'vwap_dev': round(vwap_dev,4), 'cmf_1h': round(cmf_1h,3),
                'tp1': tp1, 'tp2': tp2, 'sl': sl,
                'tp1_pct': round(tp1_pct,1), 'tp2_pct': round(tp2_pct,1),
                'sl_pct': round(sl_pct,1), 'rr': round(rr,1),
                'signals': signals[:4]
            }
        except Exception as e:
            logger.debug(f"خطأ {symbol}: {e}")
            return None

    async def track_active_signals(self):
        for symbol, data in list(self.memory.active.items()):
            if data.get('status') == 'closed':
                continue
            try:
                ticker = await self.exchange.fetch_ticker(f"{symbol}/USDT")
                price = ticker['last']
                if price >= data['tp2']:
                    await self.send_telegram(f"🚀 {symbol} حقق الهدف الثاني (TP2) عند {price:.6f} 🎉")
                    self.memory.close_active(symbol, 'closed')
                elif price >= data['tp1']:
                    await self.send_telegram(f"✅ {symbol} حقق الهدف الأول (TP1) عند {price:.6f}")
                    self.memory.close_active(symbol, 'tp1_hit')
                elif price <= data['sl']:
                    await self.send_telegram(f"❌ {symbol} ضرب وقف الخسارة (SL) عند {price:.6f}")
                    self.memory.add_failure(symbol, data['entry'], data['sl'])
                    self.memory.close_active(symbol, 'closed')
            except Exception as e:
                logger.error(f"خطأ في تتبع {symbol}: {e}")

    async def send_telegram(self, message: str):
        if not Bot: return
        try:
            bot = Bot(token=TELEGRAM_TOKEN)
            async with bot:
                for chunk in [message[i:i+4000] for i in range(0, len(message), 4000)]:
                    await bot.send_message(chat_id=CHAT_ID, text=chunk, parse_mode='Markdown')
                    await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Telegram error: {e}")

    async def hunt(self):
        print("\n" + "="*60)
        print("  📡⚛️ SigmaRadar v1.2 (بدون pandas_ta)")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await self.track_active_signals()

        regime, btc_change = await self.fetch_btc()
        print(f"  Market: {regime} | BTC: {btc_change:+.2f}%")
        symbols = await self.get_symbols(300)
        if not symbols: return

        tasks = [self.analyze(sym, regime) for sym in symbols]
        results = await asyncio.gather(*tasks)
        results = [r for r in results if r is not None]
        results.sort(key=lambda x: -x['score'])
        top = results[:TOP_N]
        if not top:
            print("  No signals.")
            return

        msg = f"📡⚛️ *توصيات SigmaRadar الكمّية* — {datetime.now().strftime('%H:%M')}\n"
        msg += f"{'─'*30}\n"
        msg += f"السوق: {regime} | BTC: {btc_change:+.2f}%\n"
        msg += f"أفضل {len(top)} فرص تم رصدها (بعد فلترة الذاكرة)\n"
        msg += f"{'─'*30}\n\n"

        for i, s in enumerate(top, 1):
            msg += f"*{i}. {s['symbol']}*   ⭐ {s['score']} نقطة\n"
            msg += f"💰 السعر: {s['price']:.6f} USDT\n"
            msg += f"📈 التغير 24h: {s['change_24h']:+.1f}%\n"
            msg += f"💵 حجم التداول: {s['volume_24h']:,.0f}$\n"
            msg += f"📉 الهبوط من القمة: {s['drawdown']['drawdown']}% | {s['drawdown']['zone']}\n"
            msg += f"💧 CMF: {s['cmf_1h']:.3f} | {'✅ تجميع' if s['cmf_1h']>0.05 else '⚠️ توزيع'}\n"
            msg += f"📊 RSI: {s['rsi']:.1f} | ADX: {s['adx']:.1f} | ستوكاستك: {s['stoch_k']:.1f}\n"
            msg += f"🎯 TP1: {s['tp1']:.6f} (+{s['tp1_pct']}%)\n"
            msg += f"🚀 TP2: {s['tp2']:.6f} (+{s['tp2_pct']}%)\n"
            msg += f"🛑 SL: {s['sl']:.6f} (-{s['sl_pct']}%) | ⚖️ R/R: {s['rr']}:1\n"
            msg += f"💡 {s['signals'][0] if s['signals'] else ''}\n"
            msg += f"{'─'*30}\n\n"

        await self.send_telegram(msg)

# ═══════════════ نقاط النهاية Flask ═══════════════
def run_hunt_background():
    global is_scanning
    if is_scanning:
        print("⏳ الفحص قيد التشغيل بالفعل")
        return
    def _run():
        global is_scanning
        is_scanning = True
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            async def runner():
                async with SigmaRadar() as radar:
                    await radar.hunt()
            loop.run_until_complete(runner())
            loop.close()
        except Exception as e:
            logger.error(f"خطأ في الخلفية: {e}")
        finally:
            is_scanning = False
    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()

@app.route('/')
def home():
    return "📡⚛️ SigmaRadar v1.2 يعمل (بدون pandas_ta)!", 200

@app.route('/health')
def health():
    return "OK", 200

@app.route('/run')
def run():
    run_hunt_background()
    return "✅ تم بدء الفحص!", 200

@app.route('/cron')
def cron():
    run_hunt_background()
    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
