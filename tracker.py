"""
⚛️ SigmaRadar v4.0 — تتبع الصفقات والمرشحات
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يتتبع:
1. الصفقات المقبولة (المُرسلة)
2. المرشحات المرفوضة (Shadow)
3. التحديثات حتى الإغلاق
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import ccxt
from datetime import datetime, timedelta
from typing import Optional, Dict
from storage import storage


class Tracker:
    """تتبع الصفقات"""
    
    def __init__(self, exchange: ccxt.Exchange):
        self.exchange = exchange
    
    def track_all(self):
        """تتبع كل شيء"""
        self._track_active_trades()
        self._track_pending_candidates()
    
    # ═══════════════════════════════════
    # تتبع الصفقات النشطة
    # ═══════════════════════════════════
    
    def _track_active_trades(self):
        """تتبع الصفقات المفتوحة"""
        active = storage.get_active_trades()
        if not active:
            return
        
        print(f"\n🔍 تتبع {len(active)} صفقة نشطة...")
        
        for trade in active:
            try:
                self._check_trade(trade)
            except Exception as e:
                print(f"⚠️ track {trade['symbol']}: {e}")
    
    def _check_trade(self, trade: Dict):
        """فحص صفقة واحدة"""
        symbol = f"{trade['symbol']}/USDT"
        
        # جلب الشموع منذ الدخول
        entry_time = datetime.fromisoformat(trade['entry_time'])
        age_hours = (datetime.now() - entry_time).total_seconds() / 3600
        limit = max(6, int(age_hours) + 3)
        
        ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=limit)
        if not ohlcv:
            return
        
        # فلترة منذ الدخول
        entry_ms = int(entry_time.timestamp() * 1000)
        filtered = [c for c in ohlcv if c[0] >= entry_ms - 3600_000]
        
        if not filtered:
            return
        
        highs = [c[2] for c in filtered]
        lows = [c[3] for c in filtered]
        max_price = max(highs)
        min_price = min(lows)
        
        # فحص
        if max_price >= trade['tp2']:
            pnl = ((trade['tp2'] - trade['entry']) / trade['entry']) * 100
            storage.close_trade(trade['id'], 'TP2', trade['tp2'], pnl)
            print(f"  🚀 {trade['symbol']} → TP2 (+{pnl:.2f}%)")
            self._add_to_blacklist_after_win(trade['symbol'])
        
        elif max_price >= trade['tp1']:
            pnl = ((trade['tp1'] - trade['entry']) / trade['entry']) * 100
            # نغلق عند TP1 (لا ننتظر TP2)
            storage.close_trade(trade['id'], 'TP1', trade['tp1'], pnl)
            print(f"  ✅ {trade['symbol']} → TP1 (+{pnl:.2f}%)")
            self._add_to_blacklist_after_win(trade['symbol'])
        
        elif min_price <= trade['sl']:
            pnl = ((trade['sl'] - trade['entry']) / trade['entry']) * 100
            storage.close_trade(trade['id'], 'SL', trade['sl'], pnl)
            print(f"  ❌ {trade['symbol']} → SL ({pnl:.2f}%)")
            # نضيف للـ blacklist بعد خسارة
            storage.add_to_blacklist(trade['symbol'], "خسرت في v4.0", permanent=False)
        
        elif age_hours > 48:
            # خروج زمني
            last_price = ohlcv[-1][4]
            pnl = ((last_price - trade['entry']) / trade['entry']) * 100
            storage.close_trade(trade['id'], 'EXPIRED', last_price, pnl)
            print(f"  ⏰ {trade['symbol']} → EXPIRE ({pnl:.2f}%)")
    
    def _add_to_blacklist_after_win(self, symbol: str):
        """بعد ربح — نضيف للـ blacklist (لأننا لن ندخلها مجدداً)"""
        storage.add_to_blacklist(symbol, "ربحت — تم إغلاقها", permanent=False)
    
    # ═══════════════════════════════════
    # تتبع المرشحات (Shadow)
    # ═══════════════════════════════════
    
    def _track_pending_candidates(self):
        """تتبع المرشحات المعلقة"""
        pending = storage.get_pending_candidates()
        if not pending:
            return
        
        print(f"\n🔍 تتبع {len(pending)} مرشحة...")
        
        for cand in pending:
            try:
                self._check_candidate(cand)
            except Exception as e:
                print(f"⚠️ candidate {cand['symbol']}: {e}")
    
    def _check_candidate(self, cand: Dict):
        """فحص مرشحة"""
        if not cand.get('entry'):
            return
        
        symbol = f"{cand['symbol']}/USDT"
        entry_time = datetime.fromisoformat(cand['entry_time'])
        age_hours = (datetime.now() - entry_time).total_seconds() / 3600
        
        # نتوقف بعد 48 ساعة
        if age_hours > 48:
            # EXPIRE
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                last_price = ticker['last']
                pnl = ((last_price - cand['entry']) / cand['entry']) * 100
                storage.update_candidate_result(cand['id'], 'EXPIRED', last_price, pnl)
            except:
                pass
            return
        
        # جلب الشموع
        try:
            limit = max(6, int(age_hours) + 3)
            ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=limit)
        except:
            return
        
        if not ohlcv:
            return
        
        entry_ms = int(entry_time.timestamp() * 1000)
        filtered = [c for c in ohlcv if c[0] >= entry_ms - 3600_000]
        
        if not filtered:
            return
        
        highs = [c[2] for c in filtered]
        lows = [c[3] for c in filtered]
        max_price = max(highs)
        min_price = min(lows)
        
        # فحص
        if max_price >= cand['tp2']:
            pnl = ((cand['tp2'] - cand['entry']) / cand['entry']) * 100
            storage.update_candidate_result(cand['id'], 'TP2', cand['tp2'], pnl)
        
        elif max_price >= cand['tp1']:
            pnl = ((cand['tp1'] - cand['entry']) / cand['entry']) * 100
            storage.update_candidate_result(cand['id'], 'TP1', cand['tp1'], pnl)
        
        elif min_price <= cand['sl']:
            pnl = ((cand['sl'] - cand['entry']) / cand['entry']) * 100
            storage.update_candidate_result(cand['id'], 'SL', cand['sl'], pnl)
