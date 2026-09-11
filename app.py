#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📡⚛️ SigmaRadar v2.3 – تتبع ذكي + أرقام فريدة + حماية كاملة
"""

import ccxt
import pandas as pd
import numpy as np
import json
import os
import threading
import time
from datetime import datetime
from flask import Flask
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# ═══════════════ الإعدادات ═══════════════
TELEGRAM_TOKEN = "8892386642:AAFrH8mz-XQjYDnsjY2RkPoJz7oMcbIDTdw"
CHAT_ID = "6499356593"
MIN_VOLUME = 100_000
MIN_SCORE = 40
MIN_RR = 1.8
TOP_N = 8
MAX_SL_PCT = 8.0
MAX_RSI_ENTRY = 72.0
MAX_STOCH_ENTRY = 98.0

BLACKLIST_FILE = "sigma_blacklist.json"
ACTIVE_FILE = "sigma_active.json"
COUNTER_FILE = "sigma_counter.json"
HISTORY_FILE = "sigma_history.json"

app = Flask(__name__)
is_scanning = False
_scan_lock = threading.Lock()

# ═══════════════ حساب المؤشرات ═══════════════
def calc_rsi(close, period=14):
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_adx(high, low, close, period=14):
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
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
    range_hl = (df['high'] - df['low']).replace(0, np.nan)
    mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / range_hl
    mfm = mfm.fillna(0)
    mfv = mfm * df['vol']
    cmf = mfv.rolling(window=period).sum() / df['vol'].rolling(window=period).sum()
    return cmf

# ═══════════════ إدارة الذاكرة ═══════════════
class SmartMemory:
    def __init__(self, blacklist_file=BLACKLIST_FILE, active_file=ACTIVE_FILE):
        self.blacklist_file = blacklist_file
        self.active_file = active_file
        self.counter_file = COUNTER_FILE
        self.history_file = HISTORY_FILE
        self._lock = threading.Lock()
        self._active_lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._blacklist_lock = threading.Lock()
        self.blacklist = self._load(blacklist_file)
        self.active = self._load(active_file)
        self.counter = self._load(self.counter_file) or {"n": 0}

    def _load(self, filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except:
            return {}

    def _save(self, filename, data):
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ فشل حفظ {filename}: {e}")

    def next_trade_id(self) -> str:
        with self._lock:
            self.counter["n"] = self.counter.get("n", 0) + 1
            self._save(self.counter_file, self.counter)
            return f"SIG-{self.counter['n']:04d}"

    def is_blocked(self, symbol: str, cmf_1h: float) -> bool:
        with self._blacklist_lock:
            if symbol not in self.blacklist:
                return False
            if cmf_1h > 0.2:
                print(f"🔓 {symbol}: تم رفع الحظر – CMF={cmf_1h:.3f}")
                del self.blacklist[symbol]
                self._save(self.blacklist_file, self.blacklist)
                return False
            return True

    def add_failure(self, symbol: str, entry: float, sl: float):
        with self._blacklist_lock:
            self.blacklist[symbol] = {'entry': entry, 'sl': sl, 'time': datetime.now().isoformat()}
            self._save(self.blacklist_file, self.blacklist)
            print(f"⛔ {symbol}: أضيفت للقائمة السوداء")

    def is_active(self, symbol: str) -> bool:
        with self._active_lock:
            return symbol in self.active and self.active[symbol].get('status') != 'closed'

    def save_active(self, symbol: str, data: dict):
        with self._active_lock:
            self.active[symbol] = data
            self._save(self.active_file, self.active)

    def close_active(self, symbol: str, status: str):
        with self._active_lock:
            if symbol in self.active:
                self.active[symbol]['status'] = status
                self._save(self.active_file, self.active)

    def get_active_snapshot(self):
        with self._active_lock:
            return dict(self.active)

    def log_history(self, trade_id, symbol, result, entry, exit_price, pct, score):
        with self._history_lock:
            try:
                try:
                    with open(self.history_file, 'r') as f:
                        hist = json.load(f)
                except:
                    hist = []
                hist.append({
                    'id': trade_id, 'symbol': symbol, 'result': result,
                    'entry': entry, 'exit': exit_price,
                    'pct': round(pct, 2), 'score': score,
                    'time': datetime.now().isoformat()
                })
                with open(self.history_file, 'w') as f:
                    json.dump(hist, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"⚠️ history save: {e}")

# ═══════════════ إرسال تليجرام ═══════════════
def send_telegram(message: str):
    try:
        for chunk in [message[i:i+4000] for i in range(0, len(message), 4000)]:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": CHAT_ID, "text": chunk, "parse_mode": "Markdown"}, timeout=15)
            time.sleep(0.5)
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")

# ═══════════════ الرادار ═══════════════
class SigmaRadar:
    def __init__(self):
        self.exchange = ccxt.kucoin({'enableRateLimit': True, 'timeout': 30000})
        self.memory = SmartMemory()

    def fetch_btc(self):
        try:
            print("  📡 جلب بيانات BTC...")
            ticker = self.exchange.fetch_ticker('BTC/USDT')
            change = ticker.get('percentage', 0.0)
            if change > 1.0: regime = "BULL"
            elif change < -1.0: regime = "BEAR"
            else: regime = "NEUTRAL"
            print(f"  ✅ BTC: {change:+.2f}% | {regime}")
            return regime, change
        except Exception as e:
            print(f"  ❌ فشل جلب BTC: {e}")
            return "NEUTRAL", 0.0

    def get_symbols(self, limit=300):
        try:
            print("  📡 جلب قائمة العملات من KuCoin...")
            tickers = self.exchange.fetch_tickers()
            symbols = []
            for sym, t in tickers.items():
                if not sym.endswith('/USDT'): continue
                if sym.split('/')[0] in {'USDC','PAX','DAI','TUSD','BUSD','FDUSD','USDP'}: continue
                if t.get('quoteVolume', 0) >= MIN_VOLUME:
                    symbols.append(sym)
            symbols.sort(key=lambda s: tickers[s]['quoteVolume'], reverse=True)
            print(f"  ✅ تم جلب {len(symbols)} عملة (أخذ أول {limit})")
            return symbols[:limit]
        except Exception as e:
            print(f"  ❌ فشل جلب العملات: {e}")
            return []

    def analyze(self, symbol: str, regime: str):
        try:
            print(f"    🔍 تحليل {symbol}...", end=' ')
            ohlcv_1h = self.exchange.fetch_ohlcv(symbol, timeframe='1h', limit=200)
            ohlcv_1d = self.exchange.fetch_ohlcv(symbol, timeframe='1d', limit=90)
            if not ohlcv_1h or len(ohlcv_1h) < 50:
                print("❌ بيانات غير كافية")
                return None
            df = pd.DataFrame(ohlcv_1h, columns=['time','open','high','low','close','vol'])
            df_daily = pd.DataFrame(ohlcv_1d, columns=['time','open','high','low','close','vol']) if ohlcv_1d else pd.DataFrame()

            df['RSI'] = calc_rsi(df['close'])
            df['StochK'] = calc_stoch_rsi(df['close'])
            df['ADX'] = calc_adx(df['high'], df['low'], df['close'])
            df['ATR'] = calc_atr(df['high'], df['low'], df['close'])
            df['CMF_1h'] = calc_cmf(df)

            price = df['close'].iloc[-1]
            cmf_1h = df['CMF_1h'].iloc[-1]
            if pd.isna(cmf_1h):
                cmf_1h = 0.0
            name = symbol.split('/')[0]

            if self.memory.is_blocked(name, cmf_1h):
                print("⛔ محظور")
                return None
            if self.memory.is_active(name):
                print("🔄 نشط")
                return None

            ticker = self.exchange.fetch_ticker(symbol)
            change_24h = ticker.get('percentage', 0.0)
            volume_24h = ticker.get('quoteVolume', 0)

            rsi = df['RSI'].iloc[-1] if not pd.isna(df['RSI'].iloc[-1]) else 50
            stoch_k = df['StochK'].iloc[-1] if not pd.isna(df['StochK'].iloc[-1]) else 50
            adx = df['ADX'].iloc[-1] if not pd.isna(df['ADX'].iloc[-1]) else 0
            atr = df['ATR'].iloc[-1] if not pd.isna(df['ATR'].iloc[-1]) else price * 0.02
            atr_pct = (atr / price) * 100 if price > 0 else 2.0

            if regime in ("BULL", "NEUTRAL"):
                if rsi >= MAX_RSI_ENTRY:
                    print(f"❌ RSI متطرف ({rsi:.1f})")
                    return None
                if stoch_k >= MAX_STOCH_ENTRY:
                    print(f"❌ StochRSI متطرف ({stoch_k:.1f})")
                    return None

            ath = df_daily['high'].max() if not df_daily.empty else price
            dd = ((ath - price) / ath) * 100 if ath > 0 else 0
            if dd >= 70: zone = '🟢🟢 تجميع مؤسسي عميق'
            elif dd >= 50: zone = '🟢 منطقة تجميع قوية'
            elif dd >= 30: zone = '🟡 تراجع معتدل'
            elif dd >= 15: zone = '⚪ تصحيح طبيعي'
            else: zone = '🔴 قريب من القمة'

            returns = df['close'].pct_change()
            mom = returns.rolling(20).mean().iloc[-1] if len(returns) >= 20 else 0
            sma20 = df['close'].rolling(20).mean().iloc[-1] if len(df) >= 20 else price
            mr = (price - sma20) / sma20 if sma20 > 0 else 0
            alpha = (mom * 100) - (mr * 50)

            if len(df) >= 20:
                typical = (df['high'] + df['low'] + df['close']) / 3
                vp = typical * df['vol']
                vwap = vp.rolling(20).sum() / df['vol'].rolling(20).sum()
                vwap_dev = (price - vwap.iloc[-1]) / vwap.iloc[-1] if vwap.iloc[-1] != 0 else 0
                if pd.isna(vwap_dev):
                    vwap_dev = 0
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

            if score < MIN_SCORE:
                print(f"❌ نقاط منخفضة ({score})")
                return None

            sl_pct = max(2.0, min(MAX_SL_PCT, atr_pct * 1.5))
            tp1_pct = max(3.0, min(25.0, atr_pct * 2.0))
            tp2_pct = tp1_pct * 1.8

            tp1 = price * (1 + tp1_pct/100)
            tp2 = price * (1 + tp2_pct/100)
            sl = price * (1 - sl_pct/100)

            rr = (tp2_pct / sl_pct) if sl_pct > 0 else 0
            if rr < MIN_RR:
                print(f"❌ R/R منخفض ({rr:.1f})")
                return None

            trade_id = self.memory.next_trade_id()

            self.memory.save_active(name, {
                'trade_id': trade_id,
                'entry': price, 'tp1': tp1, 'tp2': tp2, 'sl': sl,
                'tp1_pct': round(tp1_pct,1), 'tp2_pct': round(tp2_pct,1), 'sl_pct': round(sl_pct,1),
                'entry_time': datetime.now().isoformat(), 'status': 'active',
                'cmf_1h': cmf_1h, 'change_24h': change_24h, 'volume_24h': volume_24h,
                'drawdown': round(dd,1), 'zone': zone,
                'rsi': round(rsi,1), 'adx': round(adx,1), 'stoch_k': round(stoch_k,1),
                'signals': signals[:4], 'score': score
            })

            print(f"✅ نقاط {score} | {trade_id}")
            return {
                'trade_id': trade_id,
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
            print(f"⚠️ خطأ في {symbol}: {e}")
            return None

    def track_active_signals(self):
        print("  🔍 تتبع الصفقات المفتوحة...")
        snapshot = self.memory.get_active_snapshot()
        for symbol, data in list(snapshot.items()):
            status = data.get('status')
            if status == 'closed':
                continue
            try:
                ohlcv = self.exchange.fetch_ohlcv(f"{symbol}/USDT", timeframe='1h', limit=6)
                if not ohlcv:
                    continue
                highs = [c[2] for c in ohlcv]
                lows = [c[3] for c in ohlcv]
                max_price = max(highs)
                min_price = min(lows)

                tp1 = data['tp1']
                tp2 = data['tp2']
                sl = data['sl']
                entry = data['entry']
                trade_id = data.get('trade_id', symbol)
                score = data.get('score', 0)

                if max_price >= tp2:
                    profit_pct = ((tp2 - entry) / entry) * 100
                    send_telegram(
                        f"🚀 `{trade_id}` *{symbol}* حقق الهدف الثاني TP2 🎉\n"
                        f"💰 سعر الدخول: {entry:.6f}\n"
                        f"🎯 سعر الهدف: {tp2:.6f} (أعلى: {max_price:.6f})\n"
                        f"📈 الربح: +{profit_pct:.2f}%\n"
                        f"⭐ النقاط: {score}"
                    )
                    self.memory.log_history(trade_id, symbol, 'TP2', entry, tp2, profit_pct, score)
                    self.memory.close_active(symbol, 'closed')

                elif max_price >= tp1 and status != 'tp1_hit':
                    profit_pct = ((tp1 - entry) / entry) * 100
                    send_telegram(
                        f"✅ `{trade_id}` *{symbol}* حقق الهدف الأول TP1\n"
                        f"💰 سعر الدخول: {entry:.6f}\n"
                        f"🎯 سعر الهدف: {tp1:.6f} (أعلى: {max_price:.6f})\n"
                        f"📈 الربح: +{profit_pct:.2f}%\n"
                        f"⏳ لا يزال قيد التتبع نحو TP2 ({tp2:.6f})\n"
                        f"⭐ النقاط: {score}"
                    )
                    self.memory.log_history(trade_id, symbol, 'TP1', entry, tp1, profit_pct, score)
                    data['status'] = 'tp1_hit'
                    self.memory.save_active(symbol, data)

                elif min_price <= sl:
                    loss_pct = ((sl - entry) / entry) * 100
                    send_telegram(
                        f"❌ `{trade_id}` *{symbol}* ضرب وقف الخسارة SL\n"
                        f"💰 سعر الدخول: {entry:.6f}\n"
                        f"🛑 سعر الوقف: {sl:.6f} (أدنى: {min_price:.6f})\n"
                        f"📉 الخسارة: {loss_pct:.2f}%\n"
                        f"⭐ النقاط: {score}"
                    )
                    self.memory.log_history(trade_id, symbol, 'SL', entry, sl, loss_pct, score)
                    self.memory.add_failure(symbol, entry, sl)
                    self.memory.close_active(symbol, 'closed')
            except Exception as e:
                print(f"⚠️ خطأ في تتبع {symbol}: {e}")

    def hunt(self):
        print("\n" + "="*60)
        print("  📡⚛️ SigmaRadar v2.3")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)

        self.track_active_signals()

        regime, btc_change = self.fetch_btc()
        print(f"  Market: {regime} | BTC: {btc_change:+.2f}%")

        symbols = self.get_symbols(300)
        if not symbols:
            print("  ❌ لا توجد عملات!")
            return

        print(f"  🔍 تحليل {len(symbols)} عملة...")
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self.analyze, sym, regime): sym for sym in symbols}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: -x['score'])
        top = results[:TOP_N]
        if not top:
            print("  📭 لا توجد فرص.")
            return

        print(f"  ✅ تم العثور على {len(top)} فرصة!")

        msg = f"📡⚛️ *توصيات SigmaRadar الكمّية* — {datetime.now().strftime('%H:%M')}\n"
        msg += f"{'─'*30}\n"
        msg += f"السوق: {regime} | BTC: {btc_change:+.2f}%\n"
        msg += f"أفضل {len(top)} فرص تم رصدها\n"
        msg += f"{'─'*30}\n\n"

        for i, s in enumerate(top, 1):
            msg += f"*{i}. {s['symbol']}*   ⭐ {s['score']} نقطة   `{s['trade_id']}`\n"
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

        send_telegram(msg)
        print("  ✅ تم إرسال التوصيات إلى تليجرام.")

# ═══════════════ Flask Endpoints ═══════════════
def run_hunt_background():
    global is_scanning
    with _scan_lock:
        if is_scanning:
            print("⏳ الفحص قيد التشغيل بالفعل")
            return
        is_scanning = True
    def _run():
        global is_scanning
        try:
            radar = SigmaRadar()
            radar.hunt()
        except Exception as e:
            print(f"❌ خطأ في الخلفية: {e}")
        finally:
            with _scan_lock:
                is_scanning = False
    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()

@app.route('/')
def home():
    return "📡⚛️ SigmaRadar v2.3 يعمل!", 200

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

@app.route('/status')
def status():
    mem = SmartMemory()
    active = {k: v for k, v in mem.active.items() if v.get('status') != 'closed'}
    if not active:
        return "<h3 style='font-family:sans-serif'>لا توجد صفقات نشطة حالياً</h3>", 200
    html = """
    <html><head><title>SigmaRadar - Active Trades</title>
    <meta http-equiv="refresh" content="30"></head>
    <body style='font-family:sans-serif;padding:20px;background:#111;color:#eee'>
    <h2>📊 الصفقات النشطة</h2>
    <table border='1' cellpadding='8' style='border-collapse:collapse;width:100%'>
    <tr style='background:#222'>
      <th>ID</th><th>العملة</th><th>الحالة</th><th>الدخول</th>
      <th>TP1</th><th>TP2</th><th>SL</th><th>النقاط</th>
    </tr>
    """
    for sym, d in active.items():
        html += (
            f"<tr><td><b>{d.get('trade_id','-')}</b></td>"
            f"<td>{sym}</td>"
            f"<td>{d.get('status','-')}</td>"
            f"<td>{d['entry']:.6f}</td>"
            f"<td>{d['tp1']:.6f}</td>"
            f"<td>{d['tp2']:.6f}</td>"
            f"<td>{d['sl']:.6f}</td>"
            f"<td>{d.get('score','-')}</td></tr>"
        )
    html += "</table></body></html>"
    return html, 200

@app.route('/history')
def history():
    try:
        with open(HISTORY_FILE, 'r') as f:
            hist = json.load(f)
    except:
        hist = []
    if not hist:
        return "<h3 style='font-family:sans-serif'>لا يوجد سجل بعد</h3>", 200
    tp1 = sum(1 for h in hist if h['result'] == 'TP1')
    tp2 = sum(1 for h in hist if h['result'] == 'TP2')
    sl = sum(1 for h in hist if h['result'] == 'SL')
    total = len(hist)
    wins = tp1 + tp2
    wr = (wins / total * 100) if total > 0 else 0
    net = sum(h['pct'] for h in hist)
    html = f"""
    <html><head><title>SigmaRadar - History</title></head>
    <body style='font-family:sans-serif;padding:20px;background:#111;color:#eee'>
    <h2>📜 السجل التاريخي</h2>
    <p>إجمالي: <b>{total}</b> | ✅ TP1: <b>{tp1}</b> | 🚀 TP2: <b>{tp2}</b>
    | ❌ SL: <b>{sl}</b> | 🎯 Win Rate: <b>{wr:.1f}%</b>
    | 📈 صافي: <b>{net:+.2f}%</b></p>
    <table border='1' cellpadding='8' style='border-collapse:collapse;width:100%'>
    <tr style='background:#222'>
      <th>ID</th><th>العملة</th><th>النتيجة</th><th>الدخول</th>
      <th>الخروج</th><th>%</th><th>النقاط</th><th>التاريخ</th>
    </tr>
    """
    for h in reversed(hist[-200:]):
        color = '#2a5' if h['result'] in ('TP1','TP2') else '#a33'
        html += (
            f"<tr style='background:{color}22'>"
            f"<td><b>{h['id']}</b></td>"
            f"<td>{h['symbol']}</td>"
            f"<td>{h['result']}</td>"
            f"<td>{h['entry']:.6f}</td>"
            f"<td>{h['exit']:.6f}</td>"
            f"<td>{h['pct']:+.2f}%</td>"
            f"<td>{h.get('score','-')}</td>"
            f"<td>{h['time'][:16]}</td></tr>"
        )
    html += "</table></body></html>"
    return html, 200

# ═══ 🧹 كود التنظيف المؤقت – احذف هذا القسم كاملاً بعد الاستخدام ═══
if __name__ == "__main__":
    # 🗑️ حذف الصفقات النشطة + القائمة السوداء فقط
    _files_to_clean = ["sigma_active.json", "sigma_blacklist.json"]
    for _f in _files_to_clean:
        if os.path.exists(_f):
            try:
                os.remove(_f)
                print(f"🗑️ تم حذف {_f}")
            except Exception as _e:
                print(f"⚠️ فشل حذف {_f}: {_e}")
    
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
# ═══ نهاية كود التنظيف ═══
