"""
⚛️ SigmaRadar v4.0 — الإعدادات الرئيسية
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
كل الإعدادات في مكان واحد.
كل قيمة هنا مبنية على تحليل 111 صفقة من v2.6.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
from datetime import timedelta

# ═══════════════════════════════════
# 🔑 API Keys
# ═══════════════════════════════════
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

# ═══════════════════════════════════
# 📁 Storage
# ═══════════════════════════════════
DATA_DIR = os.environ.get("DATA_DIR", "./data")
DB_PATH = os.path.join(DATA_DIR, "sigma_v4.db")
LOG_DIR = os.path.join(DATA_DIR, "logs")

# ═══════════════════════════════════
# 🎯 Regime Detection
# ═══════════════════════════════════
REGIME_CONFIG = {
    # BTC thresholds
    "btc_strong_bear": -3.0,   # BTC < -3% → STRONG_BEAR
    "btc_bear": -1.0,           # BTC < -1% → BEAR
    "btc_bull": 1.0,            # BTC > 1% → BULL
    "btc_strong_bull": 3.0,     # BTC > 3% → STRONG_BULL
    
    # Market breadth
    "breadth_low": 0.30,        # < 30% صاعدة = ضعف
    "breadth_high": 0.70,       # > 70% صاعدة = قوة
    
    # Volatility
    "high_volatility": 5.0,     # BTC vol 7d > 5% = خطر
}

# ═══════════════════════════════════
# 🚦 Regime Rules (قرارات التداول)
# ═══════════════════════════════════
REGIME_RULES = {
    "STRONG_BEAR": {"trade": False, "reason": "لا تداول في BEAR قوي"},
    "BEAR":        {"trade": False, "reason": "لا تداول في BEAR"},
    "NEUTRAL":     {"trade": True,  "mode": "standard"},
    "BULL":        {"trade": True,  "mode": "conservative"},
    "STRONG_BULL": {"trade": False, "reason": "البامب = فخ"},
}

# ═══════════════════════════════════
# 📊 نظام النقاط v4
# ═══════════════════════════════════
SCORING = {
    "min_score": 50,
    "max_score": 85,          # لا نقبل 90+ (فشل مؤكد)
    
    # Weights (بناءً على 111 صفقة)
    "weights": {
        "change_24h_golden": 40,     # -15% إلى -3%
        "change_24h_secondary": 20,  # -20% إلى -15%
        "change_24h_neutral": 15,    # -3% إلى +5%
        
        "rsi_optimal": 20,           # 15-40
        "adx_optimal": 15,           # 25-55
        "dd_deep": 10,               # > 40%
    },
    
    # Penalties
    "penalties": {
        "pump": -50,                 # 24h > +15%
        "rsi_overbought": -20,       # RSI > 60
        "adx_extreme": -30,          # ADX > 70
        "near_ath": -40,             # dd < 15%
    }
}

# ═══════════════════════════════════
# 🚫 الفلاتر (Kill Switches)
# ═══════════════════════════════════
FILTERS = {
    # فلتر البامب
    "max_change_24h": 15.0,       # > 15% = رفض
    "pump_adx_combo": 60.0,       # > 10% + ADX > 60 = رفض
    
    # فلتر القمة
    "min_dd": 10.0,               # dd < 10% = رفض
    
    # فلتر المتطرف
    "max_adx": 75.0,              # ADX > 75 = رفض
    "max_rsi": 75.0,              # RSI > 75 = رفض
}

# ═══════════════════════════════════
# 💰 Risk Management
# ═══════════════════════════════════
RISK = {
    "default_sl_pct": 6.0,        # وقف افتراضي
    "default_tp1_pct": 8.0,       # هدف أول
    "default_tp2_pct": 15.0,      # هدف ثاني
    "min_rr": 2.0,                # أدنى R/R
    "max_position_pct": 2.0,      # أقصى حجم صفقة
}

# ═══════════════════════════════════
# ⏱️ Timeframes
# ═══════════════════════════════════
TIMEFRAMES = {
    "entry": "15m",               # للدخول
    "trend": "1h",                # للاتجاه
    "context": "4h",              # للسياق
    "candles": {
        "15m": 100,
        "1h": 200,
        "4h": 100,
    }
}

# ═══════════════════════════════════
# 📈 Performance Metrics
# ═══════════════════════════════════
REQUIRED_METRICS = {
    "min_wr": 0.55,               # Win Rate
    "min_rr": 2.0,                # Risk/Reward
    "min_sharpe": 1.5,            # Sharpe Ratio
    "max_drawdown": 0.15,         # Max Drawdown
    "min_profit_factor": 1.8,     # Profit/Loss
}

# ═══════════════════════════════════
# ⚙️ System
# ═══════════════════════════════════
SYSTEM = {
    "scan_interval_minutes": 60,   # كل ساعة
    "max_candidates_per_run": 300,
    "max_signals_per_run": 8,
    "paper_trading": True,         # ⚠️ مهم: Paper Trading فقط
    "backtest_mode": True,         # Backtest قبل أي إشارة
}

# ═══════════════════════════════════
# 🚫 Hard Blacklist (دائم)
# ═══════════════════════════════════
PERMANENT_BLACKLIST = {
    "MHA": "خسرت 3 مرات",
    "LONGXIA": "خسرت 4 مرات",
    "TRIA": "خسرت 3 مرات",
    "STAR": "90 نقطة → خسارة",
    "SEI": "90 نقطة → خسارة",
    "GRT": "90 نقطة → خسارة",
    "AXL": "90 نقطة → خسارة",
}
