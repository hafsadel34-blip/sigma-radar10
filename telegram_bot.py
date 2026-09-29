"""
⚛️ SigmaRadar v4.0 — تيليجرام
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
إرسال الإشارات وتحديثات الصفقات.
كل رسالة تحتوي على: Regime، Score، الأسباب، TP/SL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import aiohttp
from datetime import datetime
from typing import List, Dict, Optional

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


class TelegramBot:
    """بوت تيليجرام — v4.0"""
    
    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def send(self, text: str) -> bool:
        """إرسال رسالة"""
        if not self.session:
            return False
        
        try:
            # تقسيم الرسائل الطويلة
            chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
            
            for chunk in chunks:
                async with self.session.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": chunk,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    data = await resp.json()
                    if not data.get('ok'):
                        print(f"⚠️ Telegram: {data.get('description')}")
                        return False
                
                await asyncio.sleep(0.5)
            
            return True
        
        except Exception as e:
            print(f"⚠️ Telegram error: {e}")
            return False
    
    # ═══════════════════════════════════
    # رسائل محددة
    # ═══════════════════════════════════
    
    async def send_signals(self, scan_result: Dict):
        """إرسال إشارات الفحص"""
        regime = scan_result['regime']
        details = scan_result['regime_details']
        signals = scan_result['signals']
        
        if not signals:
            return
        
        # Header
        msg = f"⚛️ <b>SigmaRadar v4.0</b>\n"
        msg += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Regime info
        msg += f"📊 <b>السوق:</b> {regime}\n"
        msg += f"₿ BTC: {details['btc_change']:+.2f}%\n"
        msg += f"📈 Breadth: {details['market_breadth']:.0%}\n"
        msg += f"📉 Volatility 7d: {details['btc_volatility_7d']:.2f}%\n\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Signals
        for i, sig in enumerate(signals, 1):
            msg += self._format_signal(sig, i)
            msg += f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Footer
        msg += f"⚠️ <i>Paper Trading — ليس نصيحة مالية</i>"
        
        await self.send(msg)
    
    def _format_signal(self, sig: Dict, idx: int) -> str:
        """تنسيق إشارة واحدة"""
        msg = f"<b>{idx}. {sig['symbol']}</b>  ⭐ {sig['score']}\n"
        msg += f"💰 الدخول: <code>{sig['entry']:.6f}</code>\n"
        msg += f"🎯 TP1: <code>{sig['tp1']:.6f}</code> (+{sig['tp1_pct']}%)\n"
        msg += f"🚀 TP2: <code>{sig['tp2']:.6f}</code> (+{sig['tp2_pct']}%)\n"
        msg += f"🛑 SL:  <code>{sig['sl']:.6f}</code> (-{sig['sl_pct']}%)\n"
        msg += f"⚖️ R/R: {sig['rr']}\n\n"
        
        msg += f"📊 24h: {sig['change_24h']:+.1f}%\n"
        msg += f"📉 RSI (1h): {sig['rsi_1h']:.1f}\n"
        msg += f"📈 ADX (1h): {sig['adx_1h']:.1f}\n"
        msg += f"📉 dd: {sig['drawdown']:.1f}%\n"
        msg += f"🔄 Alignment: {sig.get('alignment_score', 0)}\n\n"
        
        # الأسباب
        if sig.get('reasons'):
            msg += f"✅ <b>الأسباب:</b>\n"
            for r in sig['reasons'][:4]:
                msg += f"  • {r}\n"
        
        # التحذيرات
        if sig.get('warnings'):
            msg += f"\n⚠️ <b>تحذيرات:</b>\n"
            for w in sig['warnings'][:2]:
                msg += f"  • {w}\n"
        
        return msg
    
    async def send_trade_update(self, symbol: str, result: str, pnl: float, details: Dict):
        """إرسال تحديث صفقة"""
        icons = {
            'TP1': '✅',
            'TP2': '🚀',
            'SL': '❌',
            'EXPIRED': '⏰',
        }
        icon = icons.get(result, '📊')
        
        msg = f"{icon} <b>{symbol}</b> — {result}\n"
        msg += f"📈 P&L: <b>{pnl:+.2f}%</b>\n"
        
        if details.get('entry'):
            msg += f"💰 الدخول: {details['entry']:.6f}\n"
        if details.get('exit'):
            msg += f"💵 الخروج: {details['exit']:.6f}\n"
        if details.get('duration'):
            msg += f"⏱️ المدة: {details['duration']:.1f}h\n"
        
        await self.send(msg)
    
    async def send_daily_summary(self, stats: Dict):
        """ملخص يومي"""
        msg = f"📊 <b>ملخص v4.0 اليومي</b>\n"
        msg += f"🕐 {datetime.now().strftime('%Y-%m-%d')}\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        msg += f"📈 إجمالي الصفقات: {stats.get('total', 0)}\n"
        msg += f"✅ رابحة: {stats.get('wins', 0)}\n"
        msg += f"❌ خاسرة: {stats.get('losses', 0)}\n"
        msg += f"🎯 WR: {stats.get('wr', 0)*100:.1f}%\n\n"
        
        # حسب Regime
        if stats.get('by_regime'):
            msg += f"<b>حسب السوق:</b>\n"
            for regime, data in stats['by_regime'].items():
                msg += f"  {regime}: {data['wins']}/{data['total']} ({data['wr']*100:.0f}%)\n"
        
        await self.send(msg)
    
    async def send_error(self, error: str):
        """إرسال خطأ"""
        msg = f"⚠️ <b>خطأ v4.0</b>\n<code>{error}</code>"
        await self.send(msg)


# ═══════════════════════════════════
# Standalone helpers (للاستخدام السريع)
# ═══════════════════════════════════

async def send_signals(scan_result: Dict):
    """إرسال إشارات"""
    async with TelegramBot() as bot:
        await bot.send_signals(scan_result)


async def send_error(error: str):
    """إرسال خطأ"""
    async with TelegramBot() as bot:
        await bot.send_error(error)
