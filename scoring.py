"""
⚛️ SigmaRadar v4.0 — نظام النقاط الجديد
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v2.6: نقاط اعتباطية (90 = فشل مؤكد)
v4.0: نقاط مبنية على 111 صفقة موثقة.

القواعد:
- كل وزن له correlation إحصائي
- لا نقبل > 85 (90 = فشل)
- العقوبات تطغى على أي شيء
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from typing import Dict, Tuple
from config import SCORING


class Scorer:
    """نظام النقاط v4.0"""
    
    def __init__(self):
        self.cfg = SCORING
        self.weights = self.cfg['weights']
        self.penalties = self.cfg['penalties']
    
    def score(self, coin: Dict) -> Tuple[Optional[int], list, list]:
        """
        حساب النقاط لعملة
        
        Returns:
            (score, reasons, warnings) أو (None, [], [reasons]) إذا رُفضت
        """
        score = 0
        reasons = []
        warnings = []
        
        change = coin.get('change_24h', 0)
        rsi = coin.get('rsi_1h', coin.get('rsi_15m', 50))
        adx = coin.get('adx_1h', coin.get('adx_15m', 0))
        dd = coin.get('drawdown', 0)
        
        # ═══════════════════════════════════
        # 🔴 Kill Switches (رفض فوري)
        # ═══════════════════════════════════
        
        # 1. البامب (KAIO +103% خسر)
        if change > self.cfg.get('max_change_24h', 15):
            return None, [], [f"⛔ بامب {change:.1f}%"]
        
        # 2. القمة
        if dd < 10:
            return None, [], [f"⛔ قريب ATH (dd {dd:.1f}%)"]
        
        # 3. ADX متطرف
        if adx > 75:
            return None, [], [f"⛔ ADX متطرف {adx:.1f}"]
        
        # 4. RSI متطرف
        if rsi > 75:
            return None, [], [f"⛔ RSI متطرف {rsi:.1f}"]
        
        # ═══════════════════════════════════
        # 💰 الأوزان (بناءً على 111 صفقة)
        # ═══════════════════════════════════
        
        # 1. 24h — المنطقة الذهبية (-15% إلى -3%)
        if -15 <= change <= -3:
            score += self.weights['change_24h_golden']
            reasons.append(f"✅ 24h ذهبي ({change:.1f}%)")
        elif -20 <= change < -15:
            score += self.weights['change_24h_secondary']
            reasons.append(f"24h ثانوي ({change:.1f}%)")
        elif -3 < change < 5:
            score += self.weights['change_24h_neutral']
            reasons.append(f"24h محايد ({change:.1f}%)")
        elif change > 10:
            score += self.penalties['pump']
            warnings.append(f"⚠️ شبه بامب ({change:.1f}%)")
        
        # 2. RSI — منطقة الدخول
        if 15 <= rsi <= 40:
            score += self.weights['rsi_optimal']
            reasons.append(f"✅ RSI منطقة ({rsi:.1f})")
        elif rsi > 60:
            score += self.penalties['rsi_overbought']
            warnings.append(f"⚠️ RSI مرتفع ({rsi:.1f})")
        
        # 3. ADX — الاتجاه الصحي
        if 25 <= adx <= 55:
            score += self.weights['adx_optimal']
            reasons.append(f"✅ ADX صحي ({adx:.1f})")
        elif adx > 70:
            score += self.penalties['adx_extreme']
            warnings.append(f"⚠️ ADX متطرف ({adx:.1f})")
        
        # 4. dd — القاع
        if dd > 40:
            score += self.weights['dd_deep']
            reasons.append(f"✅ dd عميق ({dd:.1f}%)")
        elif dd < 15:
            score += self.penalties['near_ath']
            warnings.append(f"⚠️ قريب قمة (dd {dd:.1f}%)")
        
        # ═══════════════════════════════════
        # 🎯 القرار النهائي
        # ═══════════════════════════════════
        
        min_score = self.cfg['min_score']
        max_score = self.cfg['max_score']
        
        # إذا كان أقل من الحد الأدنى
        if score < min_score:
            return None, [], [f"❌ نقاط منخفضة ({score})"]
        
        # إذا كان أعلى من الحد الأقصى (90 = فشل)
        if score > max_score:
            # نقلل قليلاً بدلاً من الرفض
            score = max_score
            warnings.append(f"⚠️ نقاط مخفضة من {score}+ إلى {max_score}")
        
        return score, reasons, warnings


# ═══════════════════════════════════
# Standalone function
# ═══════════════════════════════════

def calculate_score(coin: Dict) -> Tuple[Optional[int], list, list]:
    """اختصار"""
    scorer = Scorer()
    return scorer.score(coin)
