#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚛️ SigmaRadar v4.0 — Flask
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
+ endpoints تشخيصية للتوكن وتيليجرام
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import threading
import asyncio
import requests
from datetime import datetime
from flask import Flask, jsonify, render_template_string

from storage import storage
from main import run_scan as main_scan, Config

app = Flask(__name__)
_scan_lock = threading.Lock()
_is_scanning = False


def run_scan_background():
    global _is_scanning
    with _scan_lock:
        if _is_scanning:
            return False
        _is_scanning = True
    
    def _run():
        global _is_scanning
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main_scan())
            loop.close()
        except Exception as e:
            print(f"❌ {e}")
        finally:
            with _scan_lock:
                _is_scanning = False
    
    threading.Thread(target=_run, daemon=True).start()
    return True


# ═══════════════════════════════════
# 🌐 Routes الأساسية
# ═══════════════════════════════════

@app.route('/')
def home():
    return "⚛️ SigmaRadar v4.0 — يعمل", 200


@app.route('/health')
def health():
    return "OK", 200


@app.route('/scan')
def scan():
    if run_scan_background():
        return jsonify({"status": "started"}), 200
    return jsonify({"status": "already_running"}), 200


@app.route('/cron')
def cron():
    return scan()


@app.route('/stats')
def stats():
    return jsonify(storage.get_stats())


@app.route('/trades')
def trades():
    return jsonify(storage.get_closed_trades(limit=100))


@app.route('/active')
def active():
    return jsonify(storage.get_active_trades())


@app.route('/candidates')
def candidates():
    return jsonify(storage.get_pending_candidates())


@app.route('/blacklist')
def blacklist():
    return jsonify(storage.get_blacklist())


# ═══════════════════════════════════
# 🧪 Endpoints تشخيصية
# ═══════════════════════════════════

@app.route('/env-check')
def env_check():
    """فحص المتغيرات البيئية والـ Config"""
    env_token = os.environ.get("TELEGRAM_TOKEN", "")
    env_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    
    return jsonify({
        "config_token": {
            "exists": bool(Config.TELEGRAM_TOKEN),
            "length": len(Config.TELEGRAM_TOKEN),
            "preview": Config.TELEGRAM_TOKEN[:25] + "..." if Config.TELEGRAM_TOKEN else "MISSING",
        },
        "config_chat": {
            "exists": bool(Config.TELEGRAM_CHAT_ID),
            "value": Config.TELEGRAM_CHAT_ID,
        },
        "env_token": {
            "exists": bool(env_token),
            "preview": env_token[:25] + "..." if env_token else "MISSING",
        },
        "env_chat": {
            "exists": bool(env_chat),
            "value": env_chat or "MISSING",
        },
    })


@app.route('/test-telegram')
def test_telegram():
    """اختبار إرسال رسالة على تيليجرام"""
    token = Config.TELEGRAM_TOKEN
    chat = Config.TELEGRAM_CHAT_ID
    
    if not token:
        return jsonify({
            "ok": False,
            "error": "TELEGRAM_TOKEN غير موجود في Config",
            "solution": "أضفه في main.py"
        }), 400
    
    if not chat:
        return jsonify({
            "ok": False,
            "error": "TELEGRAM_CHAT_ID غير موجود في Config",
            "solution": "أضفه في main.py"
        }), 400
    
    # 1. اختبار getMe
    try:
        me_response = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10
        )
        me_data = me_response.json()
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"فشل الاتصال بـ Telegram API: {e}"
        }), 500
    
    if not me_data.get('ok'):
        return jsonify({
            "ok": False,
            "error": "التوكن غير صحيح",
            "telegram_response": me_data,
            "solution": "جدّد التوكن من BotFather"
        }), 400
    
    # 2. إرسال رسالة اختبار
    try:
        msg_response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat,
                "text": f"🧪 <b>SigmaRadar Test</b>\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n✅ الإرسال يعمل",
                "parse_mode": "HTML"
            },
            timeout=10
        )
        msg_data = msg_response.json()
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"فشل إرسال الرسالة: {e}"
        }), 500
    
    return jsonify({
        "ok": msg_data.get('ok', False),
        "bot_info": {
            "id": me_data['result'].get('id'),
            "username": me_data['result'].get('username'),
            "first_name": me_data['result'].get('first_name'),
        },
        "send_result": msg_data,
        "message": "إذا وصلتك رسالة على تيليجرام → كل شيء يعمل ✅" if msg_data.get('ok') else "لم تصل رسالة — راجع send_result"
    })


# ═══════════════════════════════════
# 📊 Dashboard
# ═══════════════════════════════════

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>SigmaRadar v4.0</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { font-family: -apple-system, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; margin: 0; }
        h1 { color: #4ade80; }
        h2 { color: #60a5fa; margin-top: 30px; }
        .card { background: #1a1a1a; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; }
        .stat { background: #222; padding: 15px; border-radius: 6px; }
        .stat-label { color: #888; font-size: 12px; }
        .stat-value { font-size: 24px; font-weight: bold; margin-top: 5px; }
        .green { color: #4ade80; }
        .red { color: #ef4444; }
        .yellow { color: #facc15; }
        table { width: 100%; border-collapse: collapse; background: #1a1a1a; border-radius: 8px; overflow: hidden; }
        th { background: #222; padding: 12px; text-align: left; color: #60a5fa; }
        td { padding: 10px; border-top: 1px solid #2a2a2a; }
        tr:hover { background: #222; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 11px; }
        .badge-green { background: #14532d; color: #4ade80; }
        .badge-red { background: #7f1d1d; color: #fca5a5; }
        .badge-gray { background: #333; color: #aaa; }
        .btn { display: inline-block; padding: 10px 20px; background: #4ade80; color: #000; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 5px; }
        .btn:hover { background: #22c55e; }
        .btn-red { background: #ef4444; color: #fff; }
        .btn-blue { background: #60a5fa; color: #000; }
    </style>
</head>
<body>
    <h1>⚛️ SigmaRadar v4.0</h1>
    <p style="color:#888">آخر تحديث: {{ now }}</p>
    
    <div class="card">
        <h2 style="margin-top:0">🧪 أدوات التشخيص</h2>
        <a href="/env-check" class="btn btn-blue" target="_blank">فحص المتغيرات</a>
        <a href="/test-telegram" class="btn" target="_blank">اختبار تيليجرام</a>
        <a href="/cron" class="btn btn-red" target="_blank">تشغيل /cron</a>
    </div>
    
    <div class="card">
        <h2 style="margin-top:0">📊 الإحصائيات</h2>
        <div class="stats">
            <div class="stat"><div class="stat-label">إجمالي</div><div class="stat-value">{{ stats.total }}</div></div>
            <div class="stat"><div class="stat-label">رابحة</div><div class="stat-value green">{{ stats.wins }}</div></div>
            <div class="stat"><div class="stat-label">خاسرة</div><div class="stat-value red">{{ stats.losses }}</div></div>
            <div class="stat"><div class="stat-label">WR</div><div class="stat-value">{{ "%.1f"|format(stats.wr * 100) }}%</div></div>
        </div>
    </div>
    
    <div class="card">
        <h2 style="margin-top:0">📋 آخر الصفقات</h2>
        <table>
            <tr><th>ID</th><th>العملة</th><th>Regime</th><th>Score</th><th>النتيجة</th><th>P&L</th><th>المدة</th></tr>
            {% for t in trades %}
            <tr>
                <td>SIG-{{ "%04d"|format(t.id) }}</td>
                <td><b>{{ t.symbol }}</b></td>
                <td>{{ t.regime }}</td>
                <td>{{ t.score }}</td>
                <td>
                    <span class="badge {{ 'badge-green' if t.result in ['TP1','TP2'] else 'badge-red' if t.result == 'SL' else 'badge-gray' }}">
                        {{ t.result or 'active' }}
                    </span>
                </td>
                <td class="{{ 'green' if t.pnl_pct and t.pnl_pct > 0 else 'red' }}">{{ "%+.2f"|format(t.pnl_pct or 0) }}%</td>
                <td>{{ "%.1f"|format(t.duration_h or 0) }}h</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="card">
        <h2 style="margin-top:0">🚫 Blacklist ({{ blacklist|length }})</h2>
        <p>{{ blacklist|map(attribute='symbol')|join(', ') }}</p>
    </div>
</body>
</html>
"""


@app.route('/dashboard')
def dashboard():
    return render_template_string(
        DASHBOARD_HTML,
        stats=storage.get_stats(),
        trades=storage.get_closed_trades(limit=20),
        blacklist=storage.get_blacklist(),
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
