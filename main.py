#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚛️ SigmaRadar v4.0.5 — Token in Code
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v4.0.5:
- التوكن مكتوب مباشرة في Config
- SIG-XXXX في كل الرسائل
- MAX_SIGNALS = 4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import asyncio
import time
import random
import ccxt
import numpy as np
import pandas as pd
import aiohttp
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from storage import storage


# ═══════════════════════════════════
# 1️⃣ الإعدادات
# ═══════════════════════════════════

class Config:
    # ⚠️ التوكن مكتوب مباشرة (المستودع خاص)
    TELEGRAM_TOKEN = "8892386642:AAFrH8mz-XQjYDnsjY2RkPoJz7oMcbIDTdw"
    TELEGRAM_CHAT_ID = "6499356593"
    
    BTC_STRONG_BEAR = -3.0
    BTC_BEAR = -1.0
    BTC_BULL = 1.0
    BTC_STRONG_BULL = 3.0
    BREADTH_LOW = 0.30
    BREADTH_HIGH = 0.70
    
    MIN_SCORE = 50
    MAX_SCORE = 85
    
    MAX_CHANGE_24H = 15.0
    PUMP_ADX_COMBO = 60.0
    MIN_DD = 10.0
    MAX_ADX = 75.0
    MAX_RSI = 75.0
    MIN_ADX = 15.0
    
    MAX_CANDIDATES = 300
    MAX_SIGNALS = 4
    MIN_VOLUME = 100_000
    PAPER_TRADING = True
    SCAN_COOLDOWN = 300
    
    MAX_WORKERS = 2
    DELAY_MIN = 0.05
    DELAY_MAX = 0.15
    RETRY_ATTEMPTS = 2


# ═══════════════════════════════════
# 2️⃣ كشف النظام
# ═══════════════════════════════════

class RegimeDetector:
    def __init__(self, exchange):
        self.exchange = exchange
    
    def detect(self):
        btc_change = self._btc_change()
        btc_vol = self._btc_volatility_7d()
        breadth = self._market_breadth()
        
        if btc_change < Config.BTC_STRONG_BEAR and breadth < Config.BREADTH_LOW:
            regime = "STRONG_BEAR"
        elif btc_change < Config.BTC_BEAR:
            regime = "BEAR"
        elif btc_change > Config.BTC_STRONG_BULL and breadth > Config.BREADTH_HIGH:
            regime = "STRONG_BULL"
        elif btc_change > Config.BTC_BULL:
            regime = "BULL"
        else:
            regime = "NEUTRAL"
        
        return regime, {
            'regime': regime,
            'btc_change': round(btc_change, 2),
            'btc_volatility_7d': round(btc_vol, 2),
            'market_breadth': round(breadth, 2),
        }
    
    def can_trade(self, regime):
        if regime in ("STRONG_BEAR", "BEAR"):
            return False, "لا تداول في BEAR"
        if regime == "STRONG_BULL":
            return False, "البامب = فخ"
        return True, "conservative" if regime == "BULL" else "standard"
    
    def _btc_change(self):
        try:
            t = self.exchange.fetch_ticker('BTC/USDT')
            return t.get('percentage', 0.0)
        except:
            return 0.0
    
    def _btc_volatility_7d(self):
        try:
            o = self.exchange.fetch_ohlcv('BTC/USDT', '1d', limit=7)
            if not o or len(o) < 2:
                return 0.0
            closes = [c[4] for c in o]
            returns = [(closes[i] - closes[i-1]) / closes[i-1] * 100 for i in range(1, len(closes))]
            return float(np.std(returns))
        except:
            return 0.0
    
    def _market_breadth(self):
        try:
            tickers = self.exchange.fetch_tickers()
            pairs = [t for sym, t in tickers.items() if sym.endswith('/USDT') and t.get('quoteVolume', 0) > 100_000]
            if not pairs:
                return 0.5
            pairs.sort(key=lambda x: x.get('quoteVolume', 0), reverse=True)
            top = pairs[:100]
            rising = sum(1 for t in top if t.get('percentage', 0) > 0)
            return rising / len(top)
        except:
            return 0.5


# ═══════════════════════════════════
# 3️⃣ التحليل
# ═══════════════════════════════════

class Analyzer:
    def __init__(self, exchange):
        self.exchange = exchange
    
    def analyze(self, symbol):
        try:
            time.sleep(random.uniform(Config.DELAY_MIN, Config.DELAY_MAX))
            
            o15 = self.exchange.fetch_ohlcv(symbol, '15m', limit=100)
            o1h = self.exchange.fetch_ohlcv(symbol, '1h', limit=200)
            o4h = self.exchange.fetch_ohlcv(symbol, '4h', limit=100)
            
            if not o15 or not o1h or not o4h:
                return None
            
            df15 = pd.DataFrame(o15, columns=['t','o','h','l','c','v'])
            df1h = pd.DataFrame(o1h, columns=['t','o','h','l','c','v'])
            df4h = pd.DataFrame(o4h, columns=['t','o','h','l','c','v'])
            
            ind15 = self._indicators(df15)
            ind1h = self._indicators(df1h)
            ind4h = self._indicators(df4h)
            
            if not ind15 or not ind1h or not ind4h:
                return None
            
            ticker = self.exchange.fetch_ticker(symbol)
            price = ticker.get('last', 0)
            change = ticker.get('percentage', 0)
            volume = ticker.get('quoteVolume', 0)
            
            daily = self.exchange.fetch_ohlcv(symbol, '1d', limit=30)
            if daily:
                ath = max(c[2] for c in daily)
                dd = ((ath - price) / ath * 100) if ath > 0 else 0
            else:
                dd = 0
            
            alignment = self._alignment(ind15, ind1h, ind4h)
            
            return {
                'price': price,
                'change_24h': change,
                'volume_24h': volume,
                'drawdown': dd,
                'rsi_1h': ind1h['rsi'],
                'adx_1h': ind1h['adx'],
                'atr_pct_1h': ind1h['atr_pct'],
                'cmf_1h': ind1h['cmf'],
                'rsi_4h': ind4h['rsi'],
                'alignment_score': alignment,
            }
        except:
            return None
    
    def _indicators(self, df):
        try:
            if len(df) < 50:
                return None
            
            close, high, low, volume = df['c'], df['h'], df['l'], df['v']
            
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi_val = (100 - (100 / (1 + rs))).iloc[-1]
            rsi = float(rsi_val) if not pd.isna(rsi_val) else 50.0
            
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()
            
            up = high.diff()
            down = -low.diff()
            plus_dm = np.where((up > down) & (up > 0), up, 0)
            minus_dm = np.where((down > up) & (down > 0), down, 0)
            
            plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / atr)
            minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / atr)
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx_val = dx.rolling(14).mean().iloc[-1]
            adx = float(adx_val) if not pd.isna(adx_val) else 0.0
            
            rng = (high - low).replace(0, np.nan)
            mfm = ((close - low) - (high - close)) / rng
            mfm = mfm.fillna(0)
            mfv = mfm * volume
            cmf_val = (mfv.rolling(20).sum() / volume.rolling(20).sum()).iloc[-1]
            cmf = float(cmf_val) if not pd.isna(cmf_val) else 0.0
            
            atr_val = atr.iloc[-1]
            atr_pct = (atr_val / close.iloc[-1]) * 100 if close.iloc[-1] > 0 else 0
            
            return {'rsi': rsi, 'adx': adx, 'cmf': cmf, 'atr_pct': atr_pct}
        except:
            return None
    
    def _alignment(self, i15, i1h, i4h):
        score = 0
        if i15['rsi'] < 40 and i1h['rsi'] < 50:
            score += 15
        if 25 <= i1h['adx'] <= 55:
            score += 10
        elif i1h['adx'] > 70:
            score -= 20
        if i15['rsi'] < 20 and i1h['rsi'] < 40:
            score += 10
        return score


# ═══════════════════════════════════
# 4️⃣ نظام النقاط
# ═══════════════════════════════════

class Scorer:
    def score(self, coin):
        score = 0
        reasons = []
        warnings = []
        
        change = coin.get('change_24h', 0)
        rsi = coin.get('rsi_1h', 50)
        adx = coin.get('adx_1h', 0)
        dd = coin.get('drawdown', 0)
        
        if change > Config.MAX_CHANGE_24H:
            return None, [], [f"بامب {change:.1f}%"]
        if dd < Config.MIN_DD:
            return None, [], [f"قريب ATH (dd {dd:.1f}%)"]
        if adx > Config.MAX_ADX:
            return None, [], [f"ADX متطرف {adx:.1f}"]
        if rsi > Config.MAX_RSI:
            return None, [], [f"RSI متطرف {rsi:.1f}"]
        
        if -15 <= change <= -3:
            score += 40
            reasons.append(f"✅ 24h ذهبي ({change:.1f}%)")
        elif -20 <= change < -15:
            score += 20
        elif -3 < change < 5:
            score += 15
        elif change > 10:
            score -= 50
            warnings.append(f"⚠️ شبه بامب ({change:.1f}%)")
        
        if 15 <= rsi <= 40:
            score += 20
            reasons.append(f"✅ RSI منطقة ({rsi:.1f})")
        elif rsi > 60:
            score -= 20
        
        if 25 <= adx <= 55:
            score += 15
            reasons.append(f"✅ ADX صحي ({adx:.1f})")
        elif adx > 70:
            score -= 30
        
        if dd > 40:
            score += 10
            reasons.append(f"✅ dd عميق ({dd:.1f}%)")
        elif dd < 15:
            score -= 40
        
        if score < Config.MIN_SCORE:
            return None, [], [f"نقاط منخفضة ({score})"]
        
        if score > Config.MAX_SCORE:
            score = Config.MAX_SCORE
            warnings.append(f"⚠️ نقاط مخفضة إلى {Config.MAX_SCORE}")
        
        return score, reasons, warnings


# ═══════════════════════════════════
# 5️⃣ الفلاتر
# ═══════════════════════════════════

class Filters:
    def check(self, coin):
        if storage.is_blacklisted(coin['symbol']):
            return False, "Blacklist"
        
        change = coin.get('change_24h', 0)
        adx = coin.get('adx_1h', 0)
        rsi = coin.get('rsi_1h', 50)
        dd = coin.get('drawdown', 0)
        
        if change > Config.MAX_CHANGE_24H:
            return False, f"بامب {change:.1f}%"
        if change > 10 and adx > Config.PUMP_ADX_COMBO:
            return False, f"بامب + ADX"
        if dd < Config.MIN_DD:
            return False, f"قريب ATH (dd {dd:.1f}%)"
        if adx > Config.MAX_ADX:
            return False, f"ADX متطرف {adx:.1f}"
        if adx < Config.MIN_ADX:
            return False, f"ADX ضعيف {adx:.1f}"
        if rsi > Config.MAX_RSI:
            return False, f"RSI متطرف {rsi:.1f}"
        
        return True, ""


# ═══════════════════════════════════
# 6️⃣ تيليجرام
# ═══════════════════════════════════

class Telegram:
    def __init__(self):
        self.token = Config.TELEGRAM_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID
        self.base = f"https://api.telegram.org/bot{self.token}"
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def send(self, text):
        if not self.session or not self.token:
            return
        try:
            chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for chunk in chunks:
                await self.session.post(
                    f"{self.base}/sendMessage",
                    json={"chat_id": self.chat_id, "text": chunk, "parse_mode": "HTML"},
                    timeout=aiohttp.ClientTimeout(total=15)
                )
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Telegram: {e}")
    
    async def send_signals(self, result):
        regime = result['regime']
        details = result['regime_details']
        signals = result['signals']
        
        if not signals:
            return
        
        msg = f"⚛️ <b>SigmaRadar v4.0.5</b>\n"
        msg += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += f"📊 <b>السوق:</b> {regime}\n"
        msg += f"₿ BTC: {details['btc_change']:+.2f}%\n"
        msg += f"📈 Breadth: {details['market_breadth']:.0%}\n"
        msg += f"📉 Volatility 7d: {details['btc_volatility_7d']:.2f}%\n\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, s in enumerate(signals, 1):
            msg += self._format(s, i)
            msg += f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        msg += f"⚠️ <i>Paper Trading — ليس نصيحة مالية</i>"
        await self.send(msg)
    
    def _format(self, s, idx):
        display = f"{s['symbol']}/USDT"
        trade_id = s.get('trade_id', 0)
        
        msg = f"<b>{idx}. SIG-{trade_id:04d} {display}</b>  ⭐ {s['score']}\n"
        msg += f"💰 الدخول: <code>{s['entry']:.6f}</code>\n"
        msg += f"🎯 TP1: <code>{s['tp1']:.6f}</code> (+{s['tp1_pct']}%)\n"
        msg += f"🚀 TP2: <code>{s['tp2']:.6f}</code> (+{s['tp2_pct']}%)\n"
        msg += f"🛑 SL:  <code>{s['sl']:.6f}</code> (-{s['sl_pct']}%)\n"
        msg += f"⚖️ R/R: {s['rr']}\n\n"
        msg += f"📊 24h: {s['change_24h']:+.1f}%\n"
        msg += f"📉 RSI (1h): {s['rsi_1h']:.1f}\n"
        msg += f"📈 ADX (1h): {s['adx_1h']:.1f}\n"
        msg += f"📉 dd: {s['drawdown']:.1f}%\n"
        msg += f"🔄 Alignment: {s.get('alignment_score', 0)}\n\n"
        
        if s.get('reasons'):
            msg += f"✅ <b>الأسباب:</b>\n"
            for r in s['reasons'][:4]:
                msg += f"  • {r}\n"
        if s.get('warnings'):
            msg += f"\n⚠️ <b>تحذيرات:</b>\n"
            for w in s['warnings'][:2]:
                msg += f"  • {w}\n"
        return msg


# ═══════════════════════════════════
# 7️⃣ مصنع الإشارات
# ═══════════════════════════════════

class SignalGenerator:
    def __init__(self, exchange):
        self.exchange = exchange
        self.analyzer = Analyzer(exchange)
        self.scorer = Scorer()
        self.filters = Filters()
        self.regime_detector = RegimeDetector(exchange)
    
    def run(self):
        start = time.time()
        
        regime, details = self.regime_detector.detect()
        print(f"\n{'='*60}")
        print(f"  📊 Regime: {regime} | BTC: {details['btc_change']:+.2f}%")
        print(f"  📈 Breadth: {details['market_breadth']:.0%}")
        print(f"{'='*60}\n")
        
        can_trade, mode = self.regime_detector.can_trade(regime)
        if not can_trade:
            print(f"⛔ {mode}")
            storage.log_scan(regime, details['btc_change'], 0, 0, time.time()-start)
            return {'regime': regime, 'regime_details': details, 'signals': [], 'reason': mode}
        
        print(f"✅ التداول مسموح — {mode}\n")
        
        symbols = self._get_symbols()
        print(f"📡 فحص {len(symbols)} عملة...\n")
        
        candidates = []
        with ThreadPoolExecutor(max_workers=Config.MAX_WORKERS) as executor:
            futures = {executor.submit(self._process, sym, regime): sym for sym in symbols}
            for f in as_completed(futures):
                try:
                    r = f.result()
                    if r:
                        candidates.append(r)
                except:
                    pass
        
        print(f"\n{'─'*60}")
        print(f"✅ مرشحات: {len(candidates)}")
        
        accepted = [c for c in candidates if c['accepted']]
        rejected = [c for c in candidates if not c['accepted']]
        print(f"✅ مقبول: {len(accepted)} | ❌ مرفوض: {len(rejected)}")
        
        accepted.sort(key=lambda x: -x['score'])
        final = accepted[:Config.MAX_SIGNALS]
        
        # حفظ الإشارات مع SIG ID
        for sig in final:
            trade_id = storage.save_trade({
                'symbol': sig['symbol'],
                'regime': regime,
                'score': sig['score'],
                'entry': sig['entry'],
                'tp1': sig['tp1'],
                'tp2': sig['tp2'],
                'sl': sig['sl'],
                'features': {
                    'change_24h': sig.get('change_24h'),
                    'rsi_1h': sig.get('rsi_1h'),
                    'adx_1h': sig.get('adx_1h'),
                    'dd': sig.get('drawdown'),
                }
            })
            sig['trade_id'] = trade_id
            print(f"  💾 SIG-{trade_id:04d} {sig['symbol']} في trades")
        
        # حفظ المرشحات (Shadow)
        for c in candidates:
            storage.save_candidate({
                'symbol': c['symbol'],
                'score': c['score'],
                'accepted': c['accepted'],
                'reject_reason': c.get('reject_reason'),
                'regime': regime,
                'entry': c.get('entry'),
                'tp1': c.get('tp1'),
                'tp2': c.get('tp2'),
                'sl': c.get('sl'),
                'features': {
                    'change_24h': c.get('change_24h'),
                    'rsi_1h': c.get('rsi_1h'),
                    'adx_1h': c.get('adx_1h'),
                    'dd': c.get('drawdown'),
                }
            })
        
        storage.log_scan(regime, details['btc_change'], len(candidates), len(final), time.time()-start)
        
        print(f"\n⏱️ {time.time()-start:.1f}s")
        print(f"🎯 إشارات: {len(final)}")
        
        return {
            'regime': regime,
            'regime_details': details,
            'signals': final,
            'duration': time.time() - start,
        }
    
    def _get_symbols(self):
        tickers = self.exchange.fetch_tickers()
        symbols = []
        for sym, t in tickers.items():
            if not sym.endswith('/USDT'):
                continue
            base = sym.split('/')[0]
            if base in {'USDC','USDT','DAI','TUSD','BUSD','FDUSD','USDP'}:
                continue
            if t.get('quoteVolume', 0) < Config.MIN_VOLUME:
                continue
            symbols.append(sym)
        symbols.sort(key=lambda s: tickers[s].get('quoteVolume', 0), reverse=True)
        return symbols[:Config.MAX_CANDIDATES]
    
    def _process(self, symbol, regime):
        base = symbol.split('/')[0]
        
        try:
            if storage.is_blacklisted(base):
                print(f"  🔍 {base:<10} ⛔ Blacklist")
                return None
            
            analysis = None
            for attempt in range(Config.RETRY_ATTEMPTS):
                analysis = self.analyzer.analyze(symbol)
                if analysis:
                    break
                if attempt < Config.RETRY_ATTEMPTS - 1:
                    time.sleep(0.5)
            
            if not analysis:
                print(f"  🔍 {base:<10} ❌ بيانات غير كافية")
                return None
            
            analysis['symbol'] = base
            
            passed, filter_reason = self.filters.check(analysis)
            score, reasons, warnings = self.scorer.score(analysis)
            
            if not passed:
                print(f"  🔍 {base:<10} ❌ {filter_reason}")
                return self._build_candidate(base, regime, analysis, 0, False, filter_reason, [], [])
            
            if score is None:
                reject_reason = warnings[0] if warnings else "نقاط منخفضة"
                print(f"  🔍 {base:<10} ❌ {reject_reason}")
                return self._build_candidate(base, regime, analysis, 0, False, reject_reason, [], warnings)
            
            print(f"  🔍 {base:<10} ✅ مقبول ({score})")
            return self._build_candidate(base, regime, analysis, score, True, None, reasons, warnings)
        
        except Exception as e:
            print(f"  🔍 {base:<10} ⚠️ خطأ: {e}")
            return None
    
    def _build_candidate(self, base, regime, analysis, score, accepted, reject_reason, reasons, warnings):
        candidate = {
            'regime': regime,
            'score': score,
            'accepted': accepted,
            'reject_reason': reject_reason,
            'reasons': reasons,
            'warnings': warnings,
            **{k: v for k, v in analysis.items() if k != 'symbol'},
            'symbol': base,
        }
        
        if accepted:
            candidate.update(self._calc_targets(analysis))
        
        return candidate
    
    def _calc_targets(self, a):
        entry = a['price']
        atr_pct = a.get('atr_pct_1h', 3.0)
        
        sl_pct = max(2.0, min(8.0, atr_pct * 1.5))
        tp1_pct = max(3.0, min(15.0, atr_pct * 2.0))
        tp2_pct = tp1_pct * 1.8
        
        return {
            'entry': entry,
            'tp1': entry * (1 + tp1_pct/100),
            'tp2': entry * (1 + tp2_pct/100),
            'sl': entry * (1 - sl_pct/100),
            'tp1_pct': round(tp1_pct, 2),
            'tp2_pct': round(tp2_pct, 2),
            'sl_pct': round(sl_pct, 2),
            'rr': round(tp2_pct / sl_pct, 2) if sl_pct > 0 else 0,
        }


# ═══════════════════════════════════
# 8️⃣ التتبع
# ═══════════════════════════════════

class Tracker:
    def __init__(self, exchange):
        self.exchange = exchange
    
    def track_all(self):
        self._track_trades()
        self._track_candidates()
    
    def _track_trades(self):
        active = storage.get_active_trades()
        if not active:
            return
        print(f"\n🔍 تتبع {len(active)} صفقة نشطة...")
        for trade in active:
            try:
                self._check_trade(trade)
            except Exception as e:
                print(f"⚠️ {trade['symbol']}: {e}")
    
    def _check_trade(self, trade):
        symbol = f"{trade['symbol']}/USDT"
        entry_time = datetime.fromisoformat(trade['entry_time'])
        age_hours = (datetime.now() - entry_time).total_seconds() / 3600
        
        limit = max(6, int(age_hours) + 3)
        ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=limit)
        if not ohlcv:
            return
        
        entry_ms = int(entry_time.timestamp() * 1000)
        filtered = [c for c in ohlcv if c[0] >= entry_ms - 3600_000]
        if not filtered:
            return
        
        highs = [c[2] for c in filtered]
        lows = [c[3] for c in filtered]
        max_p = max(highs)
        min_p = min(lows)
        
        trade_id = trade.get('id', 0)
        
        if max_p >= trade['tp2']:
            pnl = ((trade['tp2'] - trade['entry']) / trade['entry']) * 100
            storage.close_trade(trade['id'], 'TP2', trade['tp2'], pnl)
            print(f"  🚀 SIG-{trade_id:04d} {trade['symbol']} TP2 (+{pnl:.2f}%)")
            self._notify(trade, 'TP2', trade['tp2'], pnl, age_hours)
        
        elif max_p >= trade['tp1']:
            pnl = ((trade['tp1'] - trade['entry']) / trade['entry']) * 100
            storage.close_trade(trade['id'], 'TP1', trade['tp1'], pnl)
            print(f"  ✅ SIG-{trade_id:04d} {trade['symbol']} TP1 (+{pnl:.2f}%)")
            self._notify(trade, 'TP1', trade['tp1'], pnl, age_hours)
        
        elif min_p <= trade['sl']:
            pnl = ((trade['sl'] - trade['entry']) / trade['entry']) * 100
            storage.close_trade(trade['id'], 'SL', trade['sl'], pnl)
            storage.add_to_blacklist(trade['symbol'], "خسرت في v4.0", permanent=False)
            print(f"  ❌ SIG-{trade_id:04d} {trade['symbol']} SL ({pnl:.2f}%)")
            self._notify(trade, 'SL', trade['sl'], pnl, age_hours)
        
        elif age_hours > 48:
            last = ohlcv[-1][4]
            pnl = ((last - trade['entry']) / trade['entry']) * 100
            storage.close_trade(trade['id'], 'EXPIRED', last, pnl)
            print(f"  ⏰ SIG-{trade_id:04d} {trade['symbol']} EXPIRE ({pnl:.2f}%)")
            self._notify(trade, 'EXPIRED', last, pnl, age_hours)
    
    def _notify(self, trade, result, exit_price, pnl, age_hours):
        """إرسال إشعار على تيليجرام"""
        if not Config.TELEGRAM_TOKEN:
            return
        
        icons = {
            'TP1': '✅',
            'TP2': '🚀',
            'SL': '❌',
            'EXPIRED': '⏰',
        }
        icon = icons.get(result, '📊')
        trade_id = trade.get('id', 0)
        
        msg = f"{icon} <b>SigmaRadar v4.0.5</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += f"🆔 <b>SIG-{trade_id:04d}</b>\n"
        msg += f"<b>{trade['symbol']}/USDT</b> — {result}\n\n"
        msg += f"💰 الدخول: <code>{trade['entry']:.6f}</code>\n"
        msg += f"💵 الخروج: <code>{exit_price:.6f}</code>\n"
        msg += f"📊 P&L: <b>{pnl:+.2f}%</b>\n"
        msg += f"⏱️ المدة: {age_hours:.1f}h\n"
        
        if trade.get('score'):
            msg += f"⭐ Score: {trade['score']}\n"
        if trade.get('regime'):
            msg += f"📊 Regime: {trade['regime']}\n"
        
        try:
            requests.post(
                f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": Config.TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
                timeout=10
            )
        except Exception as e:
            print(f"⚠️ notify: {e}")
    
    def _track_candidates(self):
        pending = storage.get_pending_candidates()
        if not pending:
            return
        print(f"\n🔍 تتبع {len(pending)} مرشحة...")
        for c in pending:
            try:
                self._check_candidate(c)
            except:
                pass
    
    def _check_candidate(self, c):
        if not c.get('entry'):
            return
        
        symbol = f"{c['symbol']}/USDT"
        entry_time = datetime.fromisoformat(c['entry_time'])
        age_hours = (datetime.now() - entry_time).total_seconds() / 3600
        
        if age_hours > 48:
            try:
                t = self.exchange.fetch_ticker(symbol)
                pnl = ((t['last'] - c['entry']) / c['entry']) * 100
                storage.update_candidate_result(c['id'], 'EXPIRED', t['last'], pnl)
            except:
                pass
            return
        
        try:
            limit = max(6, int(age_hours) + 3)
            ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=limit)
        except:
            return
        
        if not ohlcv:
            return
        
        entry_ms = int(entry_time.timestamp() * 1000)
        filtered = [x for x in ohlcv if x[0] >= entry_ms - 3600_000]
        if not filtered:
            return
        
        max_p = max(c[2] for c in filtered)
        min_p = min(c[3] for c in filtered)
        
        if max_p >= c['tp2']:
            pnl = ((c['tp2'] - c['entry']) / c['entry']) * 100
            storage.update_candidate_result(c['id'], 'TP2', c['tp2'], pnl)
        elif max_p >= c['tp1']:
            pnl = ((c['tp1'] - c['entry']) / c['entry']) * 100
            storage.update_candidate_result(c['id'], 'TP1', c['tp1'], pnl)
        elif min_p <= c['sl']:
            pnl = ((c['sl'] - c['entry']) / c['entry']) * 100
            storage.update_candidate_result(c['id'], 'SL', c['sl'], pnl)


# ═══════════════════════════════════
# 9️⃣ الدورة الرئيسية
# ═══════════════════════════════════

_last_scan_time = 0


def create_exchange():
    return ccxt.kucoin({
        'enableRateLimit': True,
        'timeout': 30000,
        'options': {'defaultType': 'spot'},
    })


async def run_scan(force: bool = False):
    global _last_scan_time
    
    print(f"\n{'='*60}")
    print(f"  ⚛️ SigmaRadar v4.0.5")
    print(f"  🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    exchange = create_exchange()
    
    try:
        tracker = Tracker(exchange)
        tracker.track_all()
        
        if not force and time.time() - _last_scan_time < Config.SCAN_COOLDOWN:
            remaining = int(Config.SCAN_COOLDOWN - (time.time() - _last_scan_time))
            print(f"\n⏳ Cooldown للفحص — {remaining}s (لكن التتبع يعمل)")
            return None
        
        _last_scan_time = time.time()
        
        generator = SignalGenerator(exchange)
        result = generator.run()
        
        if result.get('signals'):
            async with Telegram() as bot:
                await bot.send_signals(result)
            print(f"\n📱 أُرسلت {len(result['signals'])} إشارة")
        
        return result
    except Exception as e:
        print(f"\n❌ {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'scan'
    
    if cmd == 'scan':
        asyncio.run(run_scan(force=True))
    elif cmd == 'stats':
        print(storage.get_stats())
