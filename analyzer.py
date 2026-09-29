"""
⚛️ SigmaRadar v4.0 — المحلل متعدد الأطر الزمنية
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v2.6 استخدم 1h فقط. v4.0 يستخدم 3 أطر:
- 15m: للدخول (توقيت دقيق)
- 1h: للاتجاه (تأكيد)
- 4h: للسياق (اتجاه عام)

هذا يمنع الإشارات المتناقضة.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import ccxt
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from config import TIMEFRAMES


class Analyzer:
    """تحليل متعدد الأطر الزمنية"""
    
    def __init__(self, exchange: ccxt.Exchange):
        self.exchange = exchange
    
    def analyze(self, symbol: str) -> Optional[Dict]:
        """
        تحليل شامل لعملة على 3 أطر زمنية
        
        Returns:
            Dict مع كل المؤشرات، أو None إذا فشل
        """
        try:
            # جلب البيانات
            data = self._fetch_multi_tf(symbol)
            if not data:
                return None
            
            # ═══ المؤشرات لكل إطار ═══
            tf_15m = self._calc_indicators(data['15m'])
            tf_1h = self._calc_indicators(data['1h'])
            tf_4h = self._calc_indicators(data['4h'])
            
            if not all([tf_15m, tf_1h, tf_4h]):
                return None
            
            # ═══ القيم الحالية ═══
            price = data['15m']['close'].iloc[-1]
            
            # ═══ التوافق بين الأطر ═══
            alignment = self._check_alignment(tf_15m, tf_1h, tf_4h)
            
            result = {
                'symbol': symbol,
                'price': float(price),
                
                # 15m — الدخول
                'rsi_15m': tf_15m['rsi'],
                'stoch_15m': tf_15m['stoch'],
                'adx_15m': tf_15m['adx'],
                
                # 1h — الاتجاه
                'rsi_1h': tf_1h['rsi'],
                'stoch_1h': tf_1h['stoch'],
                'adx_1h': tf_1h['adx'],
                'cmf_1h': tf_1h['cmf'],
                'atr_1h': tf_1h['atr'],
                'atr_pct_1h': tf_1h['atr_pct'],
                
                # 4h — السياق
                'rsi_4h': tf_4h['rsi'],
                'adx_4h': tf_4h['adx'],
                'trend_4h': tf_4h['trend'],
                
                # التوافق
                'alignment_score': alignment['score'],
                'alignment_reasons': alignment['reasons'],
                
                # سياق
                'volume_24h': data['volume_24h'],
                'change_24h': data['change_24h'],
                'high_24h': data['high_24h'],
                'low_24h': data['low_24h'],
                'drawdown': data['drawdown'],
            }
            
            return result
        
        except Exception as e:
            print(f"⚠️ analyze {symbol}: {e}")
            return None
    
    # ═══════════════════════════════════
    # Private methods
    # ═══════════════════════════════════
    
    def _fetch_multi_tf(self, symbol: str) -> Optional[Dict]:
        """جلب البيانات لـ 3 أطر"""
        try:
            result = {}
            
            # 15m
            ohlcv_15m = self.exchange.fetch_ohlcv(
                symbol, TIMEFRAMES['entry'], 
                limit=TIMEFRAMES['candles']['15m']
            )
            result['15m'] = pd.DataFrame(
                ohlcv_15m, 
                columns=['time', 'open', 'high', 'low', 'close', 'vol']
            )
            
            # 1h
            ohlcv_1h = self.exchange.fetch_ohlcv(
                symbol, TIMEFRAMES['trend'],
                limit=TIMEFRAMES['candles']['1h']
            )
            result['1h'] = pd.DataFrame(
                ohlcv_1h,
                columns=['time', 'open', 'high', 'low', 'close', 'vol']
            )
            
            # 4h
            ohlcv_4h = self.exchange.fetch_ohlcv(
                symbol, TIMEFRAMES['context'],
                limit=TIMEFRAMES['candles']['4h']
            )
            result['4h'] = pd.DataFrame(
                ohlcv_4h,
                columns=['time', 'open', 'high', 'low', 'close', 'vol']
            )
            
            # سياق السوق
            ticker = self.exchange.fetch_ticker(symbol)
            result['change_24h'] = ticker.get('percentage', 0)
            result['volume_24h'] = ticker.get('quoteVolume', 0)
            result['high_24h'] = ticker.get('high', 0)
            result['low_24h'] = ticker.get('low', 0)
            
            # drawdown من 30 يوم
            daily = self.exchange.fetch_ohlcv(symbol, '1d', limit=30)
            if daily:
                ath_30d = max(c[2] for c in daily)
                current = ticker.get('last', 0)
                result['drawdown'] = ((ath_30d - current) / ath_30d * 100) if ath_30d > 0 else 0
            else:
                result['drawdown'] = 0
            
            return result
        
        except Exception as e:
            print(f"⚠️ fetch_multi_tf {symbol}: {e}")
            return None
    
    def _calc_indicators(self, df: pd.DataFrame) -> Optional[Dict]:
        """حساب المؤشرات لإطار واحد"""
        try:
            if len(df) < 50:
                return None
            
            close = df['close']
            high = df['high']
            low = df['low']
            volume = df['vol']
            
            # RSI
            rsi = self._calc_rsi(close)
            
            # StochRSI
            stoch = self._calc_stoch_rsi(close)
            
            # ADX
            adx = self._calc_adx(high, low, close)
            
            # CMF
            cmf = self._calc_cmf(high, low, close, volume)
            
            # ATR
            atr = self._calc_atr(high, low, close)
            atr_pct = (atr / close.iloc[-1]) * 100 if close.iloc[-1] > 0 else 0
            
            # Trend (EMA20 vs EMA50)
            ema20 = close.ewm(span=20).mean().iloc[-1]
            ema50 = close.ewm(span=50).mean().iloc[-1]
            trend = 'up' if ema20 > ema50 else 'down'
            
            return {
                'rsi': round(float(rsi), 2),
                'stoch': round(float(stoch), 2),
                'adx': round(float(adx), 2),
                'cmf': round(float(cmf), 4),
                'atr': float(atr),
                'atr_pct': round(float(atr_pct), 2),
                'trend': trend,
            }
        
        except Exception as e:
            print(f"⚠️ calc_indicators: {e}")
            return None
    
    def _check_alignment(self, tf_15m: Dict, tf_1h: Dict, tf_4h: Dict) -> Dict:
        """فحص التوافق بين الأطر"""
        score = 0
        reasons = []
        
        # 1. RSI متوافق
        if tf_15m['rsi'] < 40 and tf_1h['rsi'] < 50:
            score += 15
            reasons.append("RSI متوافق")
        
        # 2. الاتجاه
        if tf_4h['trend'] == 'up' and tf_1h['trend'] == 'up':
            score += 10
            reasons.append("اتجاه صاعد")
        elif tf_4h['trend'] == 'down' and tf_1h['trend'] == 'down':
            score -= 15
            reasons.append("⚠️ اتجاه هابط")
        
        # 3. ADX
        if 25 <= tf_1h['adx'] <= 55:
            score += 10
            reasons.append("ADX صحي")
        elif tf_1h['adx'] > 70:
            score -= 20
            reasons.append("⚠️ ADX متطرف")
        
        # 4. Stoch
        if tf_15m['stoch'] < 20 and tf_1h['stoch'] < 40:
            score += 10
            reasons.append("Stoch متوافق")
        
        return {'score': score, 'reasons': reasons}
    
    # ═══════════════════════════════════
    # Indicator calculations
    # ═══════════════════════════════════
    
    def _calc_rsi(self, close: pd.Series, period: int = 14) -> float:
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        return float(val) if not pd.isna(val) else 50.0
    
    def _calc_stoch_rsi(self, close: pd.Series, period: int = 14) -> float:
        rsi = close.diff().where(close.diff() > 0, 0).rolling(period).mean()
        # calc_stoch_rsi بشكل صحيح
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        rsi_full = 100 - (100 / (1 + rs))
        
        min_rsi = rsi_full.rolling(period, min_periods=period).min()
        max_rsi = rsi_full.rolling(period, min_periods=period).max()
        denom = (max_rsi - min_rsi).replace(0, np.nan)
        stoch = 100 * (rsi_full - min_rsi) / denom
        val = stoch.iloc[-1]
        return float(val) if not pd.isna(val) else 50.0
    
    def _calc_adx(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        
        up_move = high.diff()
        down_move = -low.diff()
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        plus_di = 100 * (pd.Series(plus_dm).rolling(period).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm).rolling(period).mean() / atr)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        
        val = adx.iloc[-1]
        return float(val) if not pd.isna(val) else 0.0
    
    def _calc_cmf(self, high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 20) -> float:
        range_hl = (high - low).replace(0, np.nan)
        mfm = ((close - low) - (high - close)) / range_hl
        mfm = mfm.fillna(0)
        mfv = mfm * volume
        cmf = mfv.rolling(period).sum() / volume.rolling(period).sum()
        val = cmf.iloc[-1]
        return float(val) if not pd.isna(val) else 0.0
    
    def _calc_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        val = atr.iloc[-1]
        return float(val) if not pd.isna(val) else 0.0
