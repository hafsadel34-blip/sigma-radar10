"""
⚛️ SigmaRadar v4.0 — Flask Web Server
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يوفر endpoints:
- /              — Home
- /health        — Health check
- /scan          — تشغيل فحص
- /cron          — cron trigger
- /stats         — إحصائيات JSON
- /trades        — الصفقات
- /candidates    — المرشحات
- /backtest      — تشغيل backtest
- /dashboard     — لوحة تحكم HTML
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import threading
import asyncio
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

from storage import storage


app = Flask(__name__)

# ═══════════════════════════════════
# 🔒 Lock للفحص
# ═══════════════════════════════════
_scan_lock = threading.Lock()
_is_scanning = False


def run_scan_background():
    """تشغيل الفحص في thread منفصل"""
    global _is_scanning
    
    with _scan_lock:
        if _is_scanning:
            return False
        _is_scanning = True
    
    def _run():
        global _is_scanning
        try:
            from main import run_scan
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_scan())
            loop.close()
        except Exception as e:
            print(f"❌ scan error: {e}")
        finally:
            with _scan_lock:
                _is_scanning = False
    
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return True


# ═══════════════════════════════════
# 🌐 Routes
# ═══════════════════════════════════

@app.route('/')
def home():
    return "⚛️ SigmaRadar v4.0 — يعمل", 200


@app.route('/health')
def health():
    return "OK", 200


@app.route('/scan')
def scan():
    """تشغيل فحص"""
    if run_scan_background():
        return jsonify({"status": "started"}), 200
    return jsonify({"status": "already_running"}), 200


@app.route('/cron')
def cron():
    """Cron trigger (same as scan)"""
    return scan()


@app.route('/stats')
def stats():
    """إحصائيات JSON"""
    return jsonify(storage.get_stats())


@app.route('/trades')
def trades():
    """الصفقات"""
    limit = int(request.args.get('limit', 100))
    trades = storage.get_closed_trades(limit=limit)
    return jsonify(trades)


@app.route('/active')
def active():
    """الصفقات النشطة"""
    return jsonify(storage.get_active_trades())


@app.route('/candidates')
def candidates():
    """المرشحات المعلقة"""
    return jsonify(storage.get_pending_candidates())


@app.route('/blacklist')
def blacklist():
    """Blacklist"""
    return jsonify(storage.get_blacklist())


@app.route('/backtest', methods=['GET', 'POST'])
def backtest_route():
    """تشغيل backtest"""
    from main import run_backtest
    
    def _run():
        run_backtest()
    
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return jsonify({"status": "backtest_started"}), 200


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
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            padding: 20px;
            margin: 0;
        }
        h1 { color: #4ade80; }
        h2 { color: #60a5fa; margin-top: 30px; }
        .card {
            background: #1a1a1a;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
        }
        .stat {
            background: #222;
            padding: 15px;
            border-radius: 6px;
        }
        .stat-label { color: #888; font-size: 12px; }
        .stat-value { font-size: 24px; font-weight: bold; margin-top: 5px; }
        .green { color: #4ade80; }
        .red { color: #ef4444; }
        .yellow { color: #facc15; }
        table {
            width: 100%;
            border-collapse: collapse;
            background: #1a1a1a;
            border-radius: 8px;
            overflow: hidden;
        }
        th {
            background: #222;
            padding: 12px;
            text-align: left;
            color: #60a5fa;
        }
        td { padding: 10px; border-top: 1px solid #2a2a2a; }
        tr:hover { background: #222; }
        .badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
        }
        .badge-green { background: #14532d; color: #4ade80; }
        .badge-red { background: #7f1d1d; color: #fca5a5; }
        .badge-gray { background: #333; color: #aaa; }
    </style>
</head>
<body>
    <h1>⚛️ SigmaRadar v4.0</h1>
    <p style="color:#888">آخر تحديث: {{ now }}</p>
    
    <div class="card">
        <h2 style="margin-top:0">📊 الإحصائيات</h2>
        <div class="stats">
            <div class="stat">
                <div class="stat-label">إجمالي الصفقات</div>
                <div class="stat-value">{{ stats.total }}</div>
            </div>
            <div class="stat">
                <div class="stat-label">رابحة</div>
                <div class="stat-value green">{{ stats.wins }}</div>
            </div>
            <div class="stat">
                <div class="stat-label">خاسرة</div>
                <div class="stat-value red">{{ stats.losses }}</div>
            </div>
            <div class="stat">
                <div class="stat-label">Win Rate</div>
                <div class="stat-value {{ 'green' if stats.wr > 0.55 else 'yellow' if stats.wr > 0.45 else 'red' }}">
                    {{ "%.1f"|format(stats.wr * 100) }}%
                </div>
            </div>
        </div>
    </div>
    
    {% if stats.by_regime %}
    <div class="card">
        <h2 style="margin-top:0">📈 حسب السوق (Regime)</h2>
        <table>
            <tr><th>Regime</th><th>صفقات</th><th>رابحة</th><th>WR</th></tr>
            {% for regime, data in stats.by_regime.items() %}
            <tr>
                <td><b>{{ regime }}</b></td>
                <td>{{ data.total }}</td>
                <td class="green">{{ data.wins }}</td>
                <td class="{{ 'green' if data.wr > 0.55 else 'red' if data.wr < 0.4 else 'yellow' }}">
                    {{ "%.1f"|format(data.wr * 100) }}%
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
    {% endif %}
    
    <div class="card">
        <h2 style="margin-top:0">📋 آخر الصفقات</h2>
        <table>
            <tr>
                <th>ID</th><th>العملة</th><th>Regime</th><th>Score</th>
                <th>النتيجة</th><th>P&L</th><th>المدة</th>
            </tr>
            {% for t in trades[:20] %}
            <tr>
                <td>{{ t.id }}</td>
                <td><b>{{ t.symbol }}</b></td>
                <td>{{ t.regime }}</td>
                <td>{{ t.score }}</td>
                <td>
                    <span class="badge {{ 'badge-green' if t.result in ['TP1','TP2'] else 'badge-red' if t.result == 'SL' else 'badge-gray' }}">
                        {{ t.result }}
                    </span>
                </td>
                <td class="{{ 'green' if t.pnl_pct and t.pnl_pct > 0 else 'red' }}">
                    {{ "%+.2f"|format(t.pnl_pct or 0) }}%
                </td>
                <td>{{ "%.1f"|format(t.duration_h or 0) }}h</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="card">
        <h2 style="margin-top:0">🚫 Blacklist ({{ blacklist|length }})</h2>
        <p>{{ blacklist|map(attribute='symbol')|join(', ') }}</p>
    </div>
    
    <p style="text-align:center;color:#666;margin-top:40px">
        SigmaRadar v4.0 — Paper Trading
    </p>
</body>
</html>
"""


@app.route('/dashboard')
def dashboard():
    """لوحة تحكم"""
    stats = storage.get_stats()
    trades = storage.get_closed_trades(limit=20)
    blacklist = storage.get_blacklist()
    
    return render_template_string(
        DASHBOARD_HTML,
        stats=stats,
        trades=trades,
        blacklist=blacklist,
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )


# ═══════════════════════════════════
# 🚀 Run
# ═══════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
