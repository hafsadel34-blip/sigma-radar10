"""
⚛️ SigmaRadar v4.0 — Backtester
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
لا نستخدم أي منطق قبل اجتياز الاختبار على 200+ صفقة.

الشروط الإلزامية:
- WR > 55%
- Sharpe > 1.5
- Max Drawdown < 15%
- Profit Factor > 1.8
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import sqlite3
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from config import DB_PATH, REQUIRED_METRICS


class Backtester:
    """اختبار المنطق على بيانات تاريخية"""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
    
    def load_historical_data(self) -> List[Dict]:
        """تحميل كل الصفقات المغلقة (v2.6 + v4.0)"""
        rows = self.conn.execute("""
            SELECT * FROM trades WHERE result IS NOT NULL
        """).fetchall()
        return [dict(r) for r in rows]
    
    def backtest(self, logic_func, data: Optional[List[Dict]] = None) -> Dict:
        """
        اختبار منطق على البيانات
        
        Args:
            logic_func: دالة تأخذ صفقة، ترجع True/False
            data: البيانات (إذا None، نحمل من DB)
        
        Returns:
            Dict مع كل المقاييس
        """
        if data is None:
            data = self.load_historical_data()
        
        if not data:
            return {"error": "لا بيانات"}
        
        results = {
            'total': 0,
            'wins': 0,
            'losses': 0,
            'trades': [],
            'pnl_list': [],
        }
        
        for trade in data:
            try:
                # نطبق المنطق على الميزات
                features = json.loads(trade.get('features', '{}'))
                features['symbol'] = trade['symbol']
                features['score'] = trade['score']
                features['regime'] = trade['regime']
                
                decision = logic_func(features)
                if not decision:
                    continue
                
                # نحاكي النتيجة
                result = trade['result']
                pnl = trade.get('pnl_pct', 0)
                
                results['total'] += 1
                results['pnl_list'].append(pnl)
                
                if result in ('TP1', 'TP2'):
                    results['wins'] += 1
                elif result == 'SL':
                    results['losses'] += 1
                
                results['trades'].append({
                    'symbol': trade['symbol'],
                    'result': result,
                    'pnl': pnl,
                })
            except Exception as e:
                print(f"⚠️ backtest trade: {e}")
                continue
        
        # حساب المقاييس
        metrics = self._calculate_metrics(results)
        
        return {**results, **metrics}
    
    def _calculate_metrics(self, results: Dict) -> Dict:
        """حساب كل المقاييس"""
        total = results['total']
        if total == 0:
            return {'error': 'لا صفقات مطابقة'}
        
        wins = results['wins']
        losses = results['losses']
        pnl_list = results['pnl_list']
        
        # 1. WR
        wr = wins / total
        
        # 2. R/R (متوسط الربح / متوسط الخسارة)
        wins_pnl = [p for p in pnl_list if p > 0]
        losses_pnl = [p for p in pnl_list if p < 0]
        
        avg_win = np.mean(wins_pnl) if wins_pnl else 0
        avg_loss = abs(np.mean(losses_pnl)) if losses_pnl else 1
        rr = avg_win / avg_loss if avg_loss > 0 else 0
        
        # 3. Sharpe Ratio
        if len(pnl_list) > 1:
            sharpe = (np.mean(pnl_list) / np.std(pnl_list)) * np.sqrt(252)
        else:
            sharpe = 0
        
        # 4. Max Drawdown
        cumulative = np.cumsum(pnl_list)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (running_max - cumulative) / 100
        max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0
        
        # 5. Profit Factor
        total_wins = sum(wins_pnl)
        total_losses = abs(sum(losses_pnl))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        # 6. Trimmed WR (حذف أفضل وأسوأ 5%)
        sorted_pnl = sorted(pnl_list)
        trim_n = max(1, int(len(sorted_pnl) * 0.05))
        trimmed = sorted_pnl[trim_n:-trim_n] if trim_n * 2 < len(sorted_pnl) else sorted_pnl
        trimmed_wins = sum(1 for p in trimmed if p > 0)
        trimmed_wr = trimmed_wins / len(trimmed) if trimmed else 0
        
        return {
            'wr': round(wr, 4),
            'rr': round(rr, 2),
            'sharpe': round(sharpe, 2),
            'max_dd': round(max_dd, 4),
            'profit_factor': round(profit_factor, 2),
            'trimmed_wr': round(trimmed_wr, 4),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(-avg_loss, 2),
        }
    
    def validate(self, metrics: Dict) -> Tuple[bool, List[str]]:
        """فحص هل المنطق يستحق؟"""
        failures = []
        
        if metrics.get('wr', 0) < REQUIRED_METRICS['min_wr']:
            failures.append(f"WR {metrics['wr']:.2%} < {REQUIRED_METRICS['min_wr']:.0%}")
        
        if metrics.get('rr', 0) < REQUIRED_METRICS['min_rr']:
            failures.append(f"R/R {metrics['rr']} < {REQUIRED_METRICS['min_rr']}")
        
        if metrics.get('sharpe', 0) < REQUIRED_METRICS['min_sharpe']:
            failures.append(f"Sharpe {metrics['sharpe']} < {REQUIRED_METRICS['min_sharpe']}")
        
        if metrics.get('max_dd', 1) > REQUIRED_METRICS['max_drawdown']:
            failures.append(f"Drawdown {metrics['max_dd']:.2%} > {REQUIRED_METRICS['max_drawdown']:.0%}")
        
        if metrics.get('profit_factor', 0) < REQUIRED_METRICS['min_profit_factor']:
            failures.append(f"Profit Factor {metrics['profit_factor']} < {REQUIRED_METRICS['min_profit_factor']}")
        
        return len(failures) == 0, failures
    
    def save_result(self, logic_name: str, metrics: Dict, notes: str = ""):
        """حفظ نتيجة Backtest"""
        self.conn.execute("""
            INSERT INTO backtest_results
            (timestamp, logic_name, total_trades, wr, rr, sharpe, max_dd, profit_factor, trimmed_wr, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            logic_name,
            metrics.get('total', 0),
            metrics.get('wr', 0),
            metrics.get('rr', 0),
            metrics.get('sharpe', 0),
            metrics.get('max_dd', 0),
            metrics.get('profit_factor', 0),
            metrics.get('trimmed_wr', 0),
            notes
        ))
        self.conn.commit()
    
    def close(self):
        self.conn.close()


# ═══════════════════════════════════
# Logics للاختبار
# ═══════════════════════════════════

def logic_v2_6_baseline(coin: Dict) -> bool:
    """منطق v2.6 (للمقارنة)"""
    score = coin.get('score', 0)
    return score >= 50


def logic_v4_golden_zone(coin: Dict) -> bool:
    """منطق v4.0: المنطقة الذهبية"""
    change = coin.get('change_24h', 0)
    rsi = coin.get('rsi_1h', 50)
    adx = coin.get('adx_1h', 0)
    dd = coin.get('drawdown', 0)
    
    # Kill switches
    if change > 15: return False
    if dd < 10: return False
    if adx > 75: return False
    if rsi > 75: return False
    
    # الشروط
    if not (-15 <= change <= -3): return False
    if not (15 <= rsi <= 40): return False
    if not (25 <= adx <= 55): return False
    
    return True


def logic_v4_conservative(coin: Dict) -> bool:
    """منطق v4.0 محافظ"""
    change = coin.get('change_24h', 0)
    rsi = coin.get('rsi_1h', 50)
    dd = coin.get('drawdown', 0)
    
    if change > 10: return False
    if dd < 15: return False
    if not (-20 <= change <= -2): return False
    if not (15 <= rsi <= 45): return False
    
    return True
