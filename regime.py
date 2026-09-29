"""
⚛️ SigmaRadar v4.0 — كشف النظام (Regime Detection)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v2.6 كان يفشل في BEAR (15% WR).
v4.0 يفصل الأنظمة — لكل نظام منطق مختلف.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import ccxt
import numpy as np
from typing import Dict, Tuple
from config import REGIME_CONFIG, REGIME_RULES


class RegimeDetector:
    """كشف نظام السوق الحقيقي — ليس BTC وحده"""
    
    def __init__(self, exchange: ccxt.Exchange):
        self.exchange = exchange
        self._cache = {}
        self._cache_ttl = 300  # 5 دقائق
    
    def detect(self) -> Tuple[str, Dict]:
        """
        كشف النظام الحالي
        
        Returns:
            (regime_name, details_dict)
        """
        # 1. BTC change
        btc_change = self._get_btc_change()
        
        # 2. BTC volatility (7d)
        btc_vol = self._get_btc_volatility_7d()
        
        # 3. Market breadth
        breadth = self._get_market_breadth()
        
        # 4. Volume trend (اختياري)
        # volume_trend = self._get_volume_trend()
        
        # ═══ القرار ═══
        cfg = REGIME_CONFIG
        
        # STRONG_BEAR
        if btc_change < cfg['btc_strong_bear'] and breadth < cfg['breadth_low']:
            regime = "STRONG_BEAR"
        
        # BEAR
        elif btc_change < cfg['btc_bear']:
            regime = "BEAR"
        
        # STRONG_BULL (نادر ومهم: البامب = فخ)
        elif btc_change > cfg['btc_strong_bull'] and breadth > cfg['breadth_high']:
            regime = "STRONG_BULL"
        
        # BULL
        elif btc_change > cfg['btc_bull']:
            regime = "BULL"
        
        # NEUTRAL
        else:
            regime = "NEUTRAL"
        
        details = {
            "regime": regime,
            "btc_change": round(btc_change, 2),
            "btc_volatility_7d": round(btc_vol, 2),
            "market_breadth": round(breadth, 2),
            "rules": REGIME_RULES.get(regime, {}),
        }
        
        return regime, details
    
    def can_trade(self, regime: str) -> Tuple[bool, str]:
        """هل يمكن التداول في هذا النظام؟"""
        rules = REGIME_RULES.get(regime, {})
        if not rules.get('trade', False):
            return False, rules.get('reason', 'لا تداول')
        return True, rules.get('mode', 'standard')
    
    # ═══════════════════════════════════
    # Private methods
    # ═══════════════════════════════════
    
    def _get_btc_change(self) -> float:
        """BTC change 24h"""
        try:
            ticker = self.exchange.fetch_ticker('BTC/USDT')
            return ticker.get('percentage', 0.0)
        except Exception as e:
            print(f"⚠️ BTC change error: {e}")
            return 0.0
    
    def _get_btc_volatility_7d(self) -> float:
        """BTC volatility (7 أيام)"""
        try:
            ohlcv = self.exchange.fetch_ohlcv('BTC/USDT', '1d', limit=7)
            if not ohlcv or len(ohlcv) < 2:
                return 0.0
            
            closes = [c[4] for c in ohlcv]
            returns = [
                (closes[i] - closes[i-1]) / closes[i-1] * 100
                for i in range(1, len(closes))
            ]
            
            return float(np.std(returns))
        except Exception as e:
            print(f"⚠️ BTC vol error: {e}")
            return 0.0
    
    def _get_market_breadth(self) -> float:
        """نسبة العملات الصاعدة (من top 100)"""
        try:
            tickers = self.exchange.fetch_tickers()
            usdt_pairs = [
                t for sym, t in tickers.items()
                if sym.endswith('/USDT') and t.get('quoteVolume', 0) > 100_000
            ]
            
            if not usdt_pairs:
                return 0.5
            
            # خذ top 100 بالحجم
            usdt_pairs.sort(key=lambda x: x.get('quoteVolume', 0), reverse=True)
            top_100 = usdt_pairs[:100]
            
            # عدد الصاعدة
            rising = sum(1 for t in top_100 if t.get('percentage', 0) > 0)
            
            return rising / len(top_100)
        except Exception as e:
            print(f"⚠️ Breadth error: {e}")
            return 0.5


# ═══════════════════════════════════
# Standalone function للاستخدام السريع
# ═══════════════════════════════════

def get_current_regime(exchange: ccxt.Exchange) -> Tuple[str, Dict]:
    """اختصار للاستخدام"""
    detector = RegimeDetector(exchange)
    return detector.detect()
