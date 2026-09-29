"""
⚛️ SigmaRadar v4.0 — نقطة البدء
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
هذا الملف يشغّل الفحص الكامل:
1. كشف Regime
2. فحص العملات
3. توليد الإشارات
4. إرسالها
5. تتبع الصفقات

يمكن تشغيله:
- يدوياً: python main.py
- cron: كل ساعة
- Flask endpoint: /scan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import ccxt
import sys
import os
from datetime import datetime

from config import SYSTEM
from storage import storage
from signal_generator import SignalGenerator
from tracker import Tracker
from telegram_bot import TelegramBot


# ═══════════════════════════════════
# ⚙️ الإعدادات
# ═══════════════════════════════════

def create_exchange() -> ccxt.Exchange:
    """إنشاء اتصال KuCoin"""
    return ccxt.kucoin({
        'enableRateLimit': True,
        'timeout': 30000,
        'options': {
            'defaultType': 'spot',
        }
    })


# ═══════════════════════════════════
# 🚀 الدورة الرئيسية
# ═══════════════════════════════════

async def run_scan():
    """دورة الفحص الكاملة"""
    print(f"\n{'='*60}")
    print(f"  ⚛️ SigmaRadar v4.0")
    print(f"  🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  📊 Mode: {'Paper Trading' if SYSTEM['paper_trading'] else 'LIVE'}")
    print(f"{'='*60}")
    
    exchange = create_exchange()
    
    try:
        # 1. تتبع الصفقات والمرشحات
        print("\n🔍 تتبع الصفقات...")
        tracker = Tracker(exchange)
        tracker.track_all()
        
        # 2. فحص جديد
        print("\n📡 بدء الفحص...")
        generator = SignalGenerator(exchange)
        result = generator.run_scan()
        
        # 3. إرسال الإشارات
        if result.get('signals'):
            async with TelegramBot() as bot:
                await bot.send_signals(result)
            print(f"\n📱 تم إرسال {len(result['signals'])} إشارة")
        else:
            print(f"\n📭 لا إشارات")
            
            # إذا لم تكن هناك إشارات، أرسل سبب
            if result.get('reason'):
                async with TelegramBot() as bot:
                    await bot.send(f"⛔ لا تداول: {result['reason']}")
        
        # 4. إحصائيات
        stats = storage.get_stats()
        print(f"\n📊 إجمالي الصفقات: {stats.get('total', 0)} | WR: {stats.get('wr', 0)*100:.1f}%")
        
        return result
    
    except Exception as e:
        print(f"\n❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        
        # إرسال الخطأ على تيليجرام
        try:
            async with TelegramBot() as bot:
                await bot.send_error(str(e))
        except:
            pass
        
        return None
    
    finally:
        try:
            await asyncio.sleep(0.1)
        except:
            pass


# ═══════════════════════════════════
# 🧪 Backtest Mode
# ═══════════════════════════════════

def run_backtest():
    """تشغيل Backtest على البيانات التاريخية"""
    from backtester import Backtester, logic_v2_6_baseline, logic_v4_golden_zone, logic_v4_conservative
    
    print(f"\n{'='*60}")
    print(f"  🧪 Backtest Mode")
    print(f"{'='*60}\n")
    
    bt = Backtester()
    data = bt.load_historical_data()
    
    print(f"📊 البيانات: {len(data)} صفقة\n")
    
    # 1. v2.6 baseline
    print("━" * 50)
    print("1️⃣  v2.6 Baseline")
    print("━" * 50)
    metrics = bt.backtest(logic_v2_6_baseline, data)
    print_metrics(metrics)
    bt.save_result("v2.6_baseline", metrics)
    
    # 2. v4.0 golden zone
    print("\n" + "━" * 50)
    print("2️⃣  v4.0 Golden Zone")
    print("━" * 50)
    metrics = bt.backtest(logic_v4_golden_zone, data)
    print_metrics(metrics)
    bt.save_result("v4.0_golden_zone", metrics)
    
    # 3. v4.0 conservative
    print("\n" + "━" * 50)
    print("3️⃣  v4.0 Conservative")
    print("━" * 50)
    metrics = bt.backtest(logic_v4_conservative, data)
    print_metrics(metrics)
    bt.save_result("v4.0_conservative", metrics)
    
    bt.close()
    print(f"\n{'='*60}\n")


def print_metrics(m: dict):
    """طباعة المقاييس"""
    if 'error' in m:
        print(f"❌ {m['error']}")
        return
    
    print(f"  📈 صفقات: {m['total']}")
    print(f"  🎯 WR: {m['wr']*100:.1f}%")
    print(f"  ⚖️ R/R: {m['rr']}")
    print(f"  📊 Sharpe: {m['sharpe']}")
    print(f"  📉 Max DD: {m['max_dd']*100:.1f}%")
    print(f"  💰 Profit Factor: {m['profit_factor']}")
    print(f"  ✂️ Trimmed WR: {m['trimmed_wr']*100:.1f}%")


# ═══════════════════════════════════
# 📊 Stats Mode
# ═══════════════════════════════════

def show_stats():
    """عرض الإحصائيات"""
    print(f"\n{'='*60}")
    print(f"  📊 SigmaRadar v4.0 — Stats")
    print(f"{'='*60}\n")
    
    stats = storage.get_stats()
    
    print(f"📈 إجمالي الصفقات: {stats.get('total', 0)}")
    print(f"✅ رابحة: {stats.get('wins', 0)}")
    print(f"❌ خاسرة: {stats.get('losses', 0)}")
    print(f"🎯 WR: {stats.get('wr', 0)*100:.1f}%\n")
    
    if stats.get('by_regime'):
        print("حسب النظام:")
        for regime, data in stats['by_regime'].items():
            print(f"  {regime}: {data['wins']}/{data['total']} ({data['wr']*100:.0f}%)")
    
    # Blacklist
    bl = storage.get_blacklist()
    print(f"\n🚫 Blacklist: {len(bl)} عملة")
    for b in bl[:10]:
        print(f"  • {b['symbol']}: {b['reason']}")
    
    print(f"\n{'='*60}\n")


# ═══════════════════════════════════
# 🎯 Entry Point
# ═══════════════════════════════════

if __name__ == "__main__":
    args = sys.argv[1:] if len(sys.argv) > 1 else ['scan']
    command = args[0]
    
    if command == 'scan':
        asyncio.run(run_scan())
    elif command == 'backtest':
        run_backtest()
    elif command == 'stats':
        show_stats()
    else:
        print(f"Usage: python main.py [scan|backtest|stats]")
