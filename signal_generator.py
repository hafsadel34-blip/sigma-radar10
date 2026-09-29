"""
⚛️ SigmaRadar v4.0 — إنتاج الإشارات
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
هذا هو "المصنع" الذي:
1. يفحص 300 عملة
2. يحلل 3 أطر
3. يطبق الفلاتر
4. يحسب النقاط
5. ينتج الإشارات النهائية
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import ccxt
import time
from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import SYSTEM
from storage import storage
from regime import RegimeDetector
from analyzer import Analyzer
from scoring import Scorer
from filters import FilterEngine


class SignalGenerator:
    """مصنع الإشارات"""
    
    def __init__(self, exchange: ccxt.Exchange):
        self.exchange = exchange
        self.analyzer = Analyzer(exchange)
        self.scorer = Scorer()
        self.filter_engine = FilterEngine()
        self.regime_detector = RegimeDetector(exchange)
    
    def run_scan(self) -> Dict:
        """فحص شامل"""
        start_time = time.time()
        
        # 1. كشف النظام
        regime, regime_details = self.regime_detector.detect()
        print(f"\n{'='*60}")
        print(f"  📊 Regime: {regime} | BTC: {regime_details['btc_change']:+.2f}%")
        print(f"  📈 Breadth: {regime_details['market_breadth']:.0%}")
        print(f"{'='*60}\n")
        
        # 2. هل يمكن التداول؟
        can_trade, mode = self.regime_detector.can_trade(regime)
        if not can_trade:
            print(f"⛔ لا تداول: {mode}")
            storage.log_scan(regime, regime_details['btc_change'], 0, 0, time.time() - start_time)
            return {'regime': regime, 'signals': [], 'reason': mode}
        
        print(f"✅ التداول مسموح — الوضع: {mode}\n")
        
        # 3. جلب العملات
        symbols = self._get_symbols()
        print(f"📡 فحص {len(symbols)} عملة...\n")
        
        # 4. تحليل متوازي
        candidates = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(self._process_symbol, sym, regime): sym
                for sym in symbols
            }
            
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()
                    if result:
                        candidates.append(result)
                except Exception as e:
                    print(f"⚠️ {e}")
                
                if i % 50 == 0:
                    print(f"  ... {i}/{len(symbols)}")
        
        print(f"\n✅ تم فحص {len(symbols)} عملة")
        print(f"📊 مرشحات: {len(candidates)}")
        
        # 5. فصل المقبول والمرفوض
        accepted = [c for c in candidates if c['accepted']]
        rejected = [c for c in candidates if not c['accepted']]
        
        print(f"✅ مقبول: {len(accepted)}")
        print(f"❌ مرفوض: {len(rejected)}")
        
        # 6. رتب حسب النقاط
        accepted.sort(key=lambda x: -x['score'])
        
        # 7. خذ أفضل N
        final_signals = accepted[:SYSTEM['max_signals_per_run']]
        
        # 8. حفظ الكل (Shadow)
        for c in candidates:
            self._save_candidate(c, regime)
        
        # 9. تسجيل
        duration = time.time() - start_time
        storage.log_scan(
            regime, regime_details['btc_change'],
            len(candidates), len(final_signals), duration
        )
        
        print(f"\n⏱️ المدة: {duration:.1f}s")
        print(f"🎯 إشارات نهائية: {len(final_signals)}")
        
        return {
            'regime': regime,
            'regime_details': regime_details,
            'signals': final_signals,
            'candidates_count': len(candidates),
            'duration': duration,
        }
    
    # ═══════════════════════════════════
    # Private
    # ═══════════════════════════════════
    
    def _get_symbols(self) -> List[str]:
        """جلب قائمة العملات"""
        tickers = self.exchange.fetch_tickers()
        
        # فلترة
        symbols = []
        for sym, t in tickers.items():
            if not sym.endswith('/USDT'):
                continue
            
            base = sym.split('/')[0]
            
            # استثناء stablecoins
            if base in {'USDC', 'USDT', 'DAI', 'TUSD', 'BUSD', 'FDUSD', 'USDP'}:
                continue
            
            # حجم أدنى
            if t.get('quoteVolume', 0) < 100_000:
                continue
            
            symbols.append(sym)
        
        # رتب حسب الحجم
        symbols.sort(key=lambda s: tickers[s].get('quoteVolume', 0), reverse=True)
        
        return symbols[:SYSTEM['max_candidates_per_run']]
    
    def _process_symbol(self, symbol: str, regime: str) -> Optional[Dict]:
        """معالجة عملة واحدة"""
        try:
            # Blacklist
            base = symbol.split('/')[0]
            if storage.is_blacklisted(base):
                return None
            
            # تحليل
            analysis = self.analyzer.analyze(symbol)
            if not analysis:
                return None
            
            # فحص الفلاتر
            passed, reject_reason = self.filter_engine.check(analysis)
            
            # حساب النقاط
            score, reasons, warnings = self.scorer.score(analysis)
            
            accepted = passed and score is not None
            
            candidate = {
                'symbol': base,
                'regime': regime,
                'score': score or 0,
                'accepted': accepted,
                'reject_reason': reject_reason if not passed else None,
                'reasons': reasons,
                'warnings': warnings,
                **analysis,
            }
            
            # حساب TP/SL
            if accepted:
                candidate.update(self._calc_targets(analysis))
            
            return candidate
        
        except Exception as e:
            print(f"⚠️ process {symbol}: {e}")
            return None
    
    def _calc_targets(self, analysis: Dict) -> Dict:
        """حساب TP1/TP2/SL"""
        entry = analysis['price']
        atr_pct = analysis.get('atr_pct_1h', 3.0)
        
        # SL بناءً على ATR
        sl_pct = max(2.0, min(8.0, atr_pct * 1.5))
        
        # TP1
        tp1_pct = max(3.0, min(15.0, atr_pct * 2.0))
        
        # TP2
        tp2_pct = tp1_pct * 1.8
        
        return {
            'entry': entry,
            'tp1': entry * (1 + tp1_pct / 100),
            'tp2': entry * (1 + tp2_pct / 100),
            'sl': entry * (1 - sl_pct / 100),
            'tp1_pct': round(tp1_pct, 2),
            'tp2_pct': round(tp2_pct, 2),
            'sl_pct': round(sl_pct, 2),
            'rr': round(tp2_pct / sl_pct, 2) if sl_pct > 0 else 0,
        }
    
    def _save_candidate(self, candidate: Dict, regime: str):
        """حفظ المرشحة في Shadow"""
        storage.save_candidate({
            'symbol': candidate['symbol'],
            'score': candidate['score'],
            'accepted': candidate['accepted'],
            'reject_reason': candidate.get('reject_reason'),
            'regime': regime,
            'entry': candidate.get('entry'),
            'tp1': candidate.get('tp1'),
            'tp2': candidate.get('tp2'),
            'sl': candidate.get('sl'),
            'features': {
                'change_24h': candidate.get('change_24h'),
                'rsi_1h': candidate.get('rsi_1h'),
                'adx_1h': candidate.get('adx_1h'),
                'dd': candidate.get('drawdown'),
                'alignment': candidate.get('alignment_score'),
            }
        })
