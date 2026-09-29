"""
⚛️ SigmaRadar v4.0 — الفلاتر الثلاثة
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v2.6: 30+ فلتر → يرفض الرابحة ويقبل الخاسرة (64.9% vs 84.8%)
v4.0: 3 فلاتر فقط — كلها مبنية على بيانات

الفلاتر:
1. فلتر البامب (KAIO +103% خسر)
2. فلتر القمة (XPL, AERO خسرا)
3. فلتر المتطرف (STAR, SEI بـ 90 نقطة خسرا)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from typing import Dict, Tuple
from config import FILTERS
from storage import storage


class FilterEngine:
    """3 فلاتر فقط — Kill Switches"""
    
    def __init__(self):
        self.cfg = FILTERS
    
    def check(self, coin: Dict) -> Tuple[bool, str]:
        """
        فحص كل الفلاتر
        
        Returns:
            (passed, reason)
        """
        # 1. Blacklist (أولاً — الأهم)
        if storage.is_blacklisted(coin['symbol']):
            return False, "Blacklist"
        
        # 2. فلتر البامب
        passed, reason = self._filter_pump(coin)
        if not passed:
            return False, reason
        
        # 3. فلتر القمة
        passed, reason = self._filter_ath(coin)
        if not passed:
            return False, reason
        
        # 4. فلتر المتطرف
        passed, reason = self._filter_extreme(coin)
        if not passed:
            return False, reason
        
        return True, ""
    
    # ═══════════════════════════════════
    # الفلاتر الفردية
    # ═══════════════════════════════════
    
    def _filter_pump(self, coin: Dict) -> Tuple[bool, str]:
        """
        فلتر البامب
        KAIO +103% → 90 نقطة → خسارة
        """
        change = coin.get('change_24h', 0)
        
        # بامب صريح
        if change > self.cfg['max_change_24h']:
            return False, f"بامب {change:.1f}%"
        
        # بامب + ADX
        adx = coin.get('adx_1h', 0)
        if change > 10 and adx > self.cfg['pump_adx_combo']:
            return False, f"بامب {change:.1f}% + ADX {adx:.1f}"
        
        return True, ""
    
    def _filter_ath(self, coin: Dict) -> Tuple[bool, str]:
        """
        فلتر القمة
        XPL (dd 12%), AERO (dd 8.4%) → خسائر
        """
        dd = coin.get('drawdown', 0)
        
        if dd < self.cfg['min_dd']:
            return False, f"قريب ATH (dd {dd:.1f}%)"
        
        return True, ""
    
    def _filter_extreme(self, coin: Dict) -> Tuple[bool, str]:
        """
        فلتر المتطرف
        STAR (ADX 67), SEI (ADX 46) → خسائر
        """
        adx = coin.get('adx_1h', coin.get('adx_15m', 0))
        rsi = coin.get('rsi_1h', coin.get('rsi_15m', 50))
        
        if adx > self.cfg['max_adx']:
            return False, f"ADX {adx:.1f} > {self.cfg['max_adx']}"
        
        if rsi > self.cfg['max_rsi']:
            return False, f"RSI {rsi:.1f} > {self.cfg['max_rsi']}"
        
        return True, ""


# ═══════════════════════════════════
# Standalone function
# ═══════════════════════════════════

def apply_filters(coin: Dict) -> Tuple[bool, str]:
    """اختصار"""
    engine = FilterEngine()
    return engine.check(coin)
