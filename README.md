# ⚛️ SigmaRadar v4.0

> مشروع جديد — مبني على دروس 111 صفقة من v2.6

## 🎯 الفلسفة

**v2.6:** منطق ← كود ← سوق ← فشل  
**v4.0:** بيانات ← منطق ← Backtest ← نجاح

## 🔥 الفروق الجذرية عن v2.6

| العنصر | v2.6 | v4.0 |
|---|---|---|
| **Regime Detection** | BTC change فقط | متكامل (BTC + breadth + volatility) |
| **نظام النقاط** | اعتباطي (90 = فشل) | Kill switches + Weights |
| **الفلاتر** | 30+ | 3 فقط |
| **Backtest** | لا يوجد | إلزامي |
| **التخزين** | JSON مؤقت | SQLite دائم |
| **أنماط** | تنكسر | اختبار إحصائي |
| **Multi-TF** | 1h فقط | 3 أطر (15m/1h/4h) |

## 🚀 التشغيل

### 1. تثبيت المتطلبات
\`\`\`bash
pip install -r requirements.txt
\`\`\`

### 2. إعداد متغيرات البيئة
\`\`\`bash
export TELEGRAM_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
export DATA_DIR="./data"
\`\`\`

### 3. تشغيل Backtest أولاً
\`\`\`bash
python main.py backtest
\`\`\`

**⚠️ لا تشغّل الفحص قبل Backtest ناجح!**

### 4. تشغيل الفحص
\`\`\`bash
python main.py scan
\`\`\`

### 5. تشغيل Web Server
\`\`\`bash
python flask_app.py
\`\`\`

## 📊 Web Endpoints

| Endpoint | الوصف |
|---|---|
| `/` | Home |
| `/health` | Health check |
| `/scan` | تشغيل فحص |
| `/cron` | Cron trigger |
| `/stats` | إحصائيات JSON |
| `/trades` | الصفقات |
| `/candidates` | المرشحات |
| `/blacklist` | Blacklist |
| `/dashboard` | لوحة تحكم |
| `/backtest` | تشغيل Backtest |

## ⚙️ الإعدادات

كل الإعدادات في `config.py` — لا تعدّل غيرها.

## 🎯 القواعد الذهبية

### ✅ ما نفعله:
- Backtest قبل أي تشغيل
- 3 أطر زمنية إلزامية
- Paper Trading 45+ يوم
- Hard Blacklist دائم
- Trimmed metrics (حذف أفضل/أسوأ 5%)

### ❌ ما لا نفعله:
- بناء Score على افتراضات
- تشغيل بدون Backtest
- الاعتماد على CMF
- رفض Stoch > 50
- 30+ فلتر
- تجاهل Regime
- الاعتماد على outlier

## 📈 مقاييس القبول

| المقياس | الحد الأدنى |
|---|---|
| Win Rate | 55% |
| R/R | 2.0 |
| Sharpe | 1.5 |
| Max Drawdown | 15% |
| Profit Factor | 1.8 |

## 🚦 مراحل التشغيل

\`\`\`
1. Backtest على 200+ صفقة → WR > 55%
2. Paper Trading 50 صفقة → WR > 55%
3. Paper Trading 100 صفقة → WR > 55%
4. المال الحقيقي (بحذر)
\`\`\`

**المدة الإجمالية: 45-60 يوم.**

## 📁 هيكل المشروع

\`\`\`
sigma_v4/
├── config.py              # الإعدادات
├── storage.py             # SQLite
├── regime.py              # كشف النظام
├── analyzer.py            # تحليل multi-TF
├── scoring.py             # نظام النقاط
├── filters.py             # 3 فلاتر
├── backtester.py          # Backtest
├── signal_generator.py    # مصنع الإشارات
├── tracker.py             # تتبع
├── telegram_bot.py        # إرسال
├── main.py                # Entry point
├── flask_app.py           # Web
└── requirements.txt
\`\`\`

## 🔐 Rights

© 2026 — مشروع تعليمي — Paper Trading فقط
