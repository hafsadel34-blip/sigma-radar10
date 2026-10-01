#!/usr/bin/env python3
"""⚛️ SigmaRadar v4.0 — Flask"""

import os
import threading
import asyncio
from datetime import datetime
from flask import Flask, jsonify, render_template_string

from storage import storage
from main import run_scan as main_scan

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


DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>SigmaRadar v4.0</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { font-family: -apple-system, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; margin: 0; }
        h1 { color: #4ade80; }
        .card { background: #1a1a1a; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; }
        .stat { background: #222; padding: 15px; border-radius: 6px; }
        .stat-label { color: #888; font-size: 12px; }
        .stat-value { font-size: 24px; font-weight: bold; margin-top: 5px; }
        .green { color: #4ade80; }
        .red { color: #ef4444; }
        table { width: 100%; border-collapse: collapse; background: #1a1a1a; border-radius: 8px; overflow: hidden; }
        th { background: #222; padding: 12px; text-align: left; color: #60a5fa; }
        td { padding: 10px; border-top: 1px solid #2a2a2a; }
    </style>
</head>
<body>
    <h1>⚛️ SigmaRadar v4.0</h1>
    <p style="color:#888">آخر تحديث: {{ now }}</p>
    
    <div class="card">
        <h2>📊 الإحصائيات</h2>
        <div class="stats">
            <div class="stat"><div class="stat-label">إجمالي</div><div class="stat-value">{{ stats.total }}</div></div>
            <div class="stat"><div class="stat-label">رابحة</div><div class="stat-value green">{{ stats.wins }}</div></div>
            <div class="stat"><div class="stat-label">خاسرة</div><div class="stat-value red">{{ stats.losses }}</div></div>
            <div class="stat"><div class="stat-label">WR</div><div class="stat-value">{{ "%.1f"|format(stats.wr * 100) }}%</div></div>
        </div>
    </div>
    
    <div class="card">
        <h2>📋 آخر الصفقات</h2>
        <table>
            <tr><th>ID</th><th>العملة</th><th>Regime</th><th>Score</th><th>النتيجة</th><th>P&L</th><th>المدة</th></tr>
            {% for t in trades %}
            <tr>
                <td>{{ t.id }}</td>
                <td><b>{{ t.symbol }}</b></td>
                <td>{{ t.regime }}</td>
                <td>{{ t.score }}</td>
                <td>{{ t.result or 'active' }}</td>
                <td class="{{ 'green' if t.pnl_pct and t.pnl_pct > 0 else 'red' }}">{{ "%+.2f"|format(t.pnl_pct or 0) }}%</td>
                <td>{{ "%.1f"|format(t.duration_h or 0) }}h</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="card">
        <h2>🚫 Blacklist ({{ blacklist|length }})</h2>
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
