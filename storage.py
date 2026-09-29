"""
⚛️ SigmaRadar v4.0 — التخزين الدائم
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SQLite — لا يضيع مع Render.
كل صفقة، كل مرشحة، كل blacklist في مكان دائم.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
import threading

from config import DB_PATH, DATA_DIR, PERMANENT_BLACKLIST


class Storage:
    """التخزين الدائم — يستخدم SQLite"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        os.makedirs(DATA_DIR, exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
        self._init_blacklist()
        self._initialized = True
    
    def _init_tables(self):
        """إنشاء كل الجداول"""
        with self._lock:
            # جدول الصفقات
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    score INTEGER,
                    entry REAL NOT NULL,
                    tp1 REAL NOT NULL,
                    tp2 REAL NOT NULL,
                    sl REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT,
                    exit_price REAL,
                    result TEXT,
                    pnl_pct REAL,
                    duration_h REAL,
                    features TEXT,
                    notes TEXT
                )
            """)
            
            # جدول المرشحات (Shadow)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    accepted INTEGER NOT NULL,
                    reject_reason TEXT,
                    regime TEXT,
                    entry REAL,
                    tp1 REAL,
                    tp2 REAL,
                    sl REAL,
                    entry_time TEXT NOT NULL,
                    result TEXT DEFAULT 'pending',
                    exit_time TEXT,
                    pnl_pct REAL,
                    features TEXT
                )
            """)
            
            # جدول Blacklist
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS blacklist (
                    symbol TEXT PRIMARY KEY,
                    reason TEXT,
                    added_at TEXT NOT NULL,
                    permanent INTEGER DEFAULT 1
                )
            """)
            
            # جدول Scan Logs
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    regime TEXT,
                    btc_change REAL,
                    candidates_count INTEGER,
                    accepted_count INTEGER,
                    duration_sec REAL
                )
            """)
            
            # جدول Backtest Results
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS backtest_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    logic_name TEXT,
                    total_trades INTEGER,
                    wr REAL,
                    rr REAL,
                    sharpe REAL,
                    max_dd REAL,
                    profit_factor REAL,
                    trimmed_wr REAL,
                    notes TEXT
                )
            """)
            
            # Indexes
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_regime ON trades(regime)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_symbol ON candidates(symbol)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_result ON candidates(result)")
            
            self.conn.commit()
    
    def _init_blacklist(self):
        """إضافة Blacklist الدائم"""
        with self._lock:
            for symbol, reason in PERMANENT_BLACKLIST.items():
                self.conn.execute("""
                    INSERT OR IGNORE INTO blacklist (symbol, reason, added_at, permanent)
                    VALUES (?, ?, ?, 1)
                """, (symbol, reason, datetime.now().isoformat()))
            self.conn.commit()
    
    # ═══════════════════════════════════
    # Trades
    # ═══════════════════════════════════
    
    def save_trade(self, trade: Dict[str, Any]) -> int:
        """حفظ صفقة جديدة"""
        with self._lock:
            cur = self.conn.execute("""
                INSERT INTO trades 
                (symbol, regime, score, entry, tp1, tp2, sl, entry_time, features)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade['symbol'],
                trade['regime'],
                trade.get('score', 0),
                trade['entry'],
                trade['tp1'],
                trade['tp2'],
                trade['sl'],
                datetime.now().isoformat(),
                json.dumps(trade.get('features', {}), ensure_ascii=False)
            ))
            self.conn.commit()
            return cur.lastrowid
    
    def close_trade(self, trade_id: int, result: str, exit_price: float, pnl_pct: float):
        """إغلاق صفقة"""
        with self._lock:
            # جلب وقت الدخول لحساب المدة
            row = self.conn.execute(
                "SELECT entry_time FROM trades WHERE id = ?", (trade_id,)
            ).fetchone()
            
            entry_time = datetime.fromisoformat(row['entry_time'])
            duration_h = (datetime.now() - entry_time).total_seconds() / 3600
            
            self.conn.execute("""
                UPDATE trades 
                SET exit_time = ?, exit_price = ?, result = ?, 
                    pnl_pct = ?, duration_h = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                exit_price,
                result,
                pnl_pct,
                round(duration_h, 2),
                trade_id
            ))
            self.conn.commit()
    
    def get_active_trades(self) -> List[Dict]:
        """الصفقات النشطة"""
        rows = self.conn.execute("""
            SELECT * FROM trades WHERE result IS NULL
        """).fetchall()
        return [dict(r) for r in rows]
    
    def get_closed_trades(self, limit: Optional[int] = None) -> List[Dict]:
        """الصفقات المغلقة"""
        query = "SELECT * FROM trades WHERE result IS NOT NULL ORDER BY id DESC"
        if limit:
            query += f" LIMIT {limit}"
        rows = self.conn.execute(query).fetchall()
        return [dict(r) for r in rows]
    
    # ═══════════════════════════════════
    # Candidates (Shadow)
    # ═══════════════════════════════════
    
    def save_candidate(self, candidate: Dict[str, Any]) -> int:
        """حفظ مرشحة"""
        with self._lock:
            cur = self.conn.execute("""
                INSERT INTO candidates
                (symbol, score, accepted, reject_reason, regime,
                 entry, tp1, tp2, sl, entry_time, features)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                candidate['symbol'],
                candidate['score'],
                1 if candidate['accepted'] else 0,
                candidate.get('reject_reason'),
                candidate.get('regime', 'UNKNOWN'),
                candidate.get('entry'),
                candidate.get('tp1'),
                candidate.get('tp2'),
                candidate.get('sl'),
                datetime.now().isoformat(),
                json.dumps(candidate.get('features', {}), ensure_ascii=False)
            ))
            self.conn.commit()
            return cur.lastrowid
    
    def get_pending_candidates(self) -> List[Dict]:
        """المرشحات المعلقة"""
        rows = self.conn.execute("""
            SELECT * FROM candidates WHERE result = 'pending'
        """).fetchall()
        return [dict(r) for r in rows]
    
    def update_candidate_result(self, candidate_id: int, result: str, 
                                 exit_price: float, pnl_pct: float):
        """تحديث نتيجة مرشحة"""
        with self._lock:
            self.conn.execute("""
                UPDATE candidates 
                SET result = ?, exit_time = ?, pnl_pct = ?
                WHERE id = ?
            """, (
                result,
                datetime.now().isoformat(),
                pnl_pct,
                candidate_id
            ))
            self.conn.commit()
    
    # ═══════════════════════════════════
    # Blacklist
    # ═══════════════════════════════════
    
    def is_blacklisted(self, symbol: str) -> bool:
        """فحص Blacklist"""
        row = self.conn.execute(
            "SELECT 1 FROM blacklist WHERE symbol = ?", (symbol,)
        ).fetchone()
        return row is not None
    
    def add_to_blacklist(self, symbol: str, reason: str, permanent: bool = False):
        """إضافة للـ Blacklist"""
        with self._lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO blacklist (symbol, reason, added_at, permanent)
                VALUES (?, ?, ?, ?)
            """, (
                symbol, reason, datetime.now().isoformat(),
                1 if permanent else 0
            ))
            self.conn.commit()
    
    def get_blacklist(self) -> List[Dict]:
        """كل الـ Blacklist"""
        rows = self.conn.execute("SELECT * FROM blacklist").fetchall()
        return [dict(r) for r in rows]
    
    # ═══════════════════════════════════
    # Scan Logs
    # ═══════════════════════════════════
    
    def log_scan(self, regime: str, btc_change: float, 
                 candidates: int, accepted: int, duration: float):
        """تسجيل فحص"""
        with self._lock:
            self.conn.execute("""
                INSERT INTO scan_logs
                (timestamp, regime, btc_change, candidates_count, accepted_count, duration_sec)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                regime, btc_change, candidates, accepted, round(duration, 2)
            ))
            self.conn.commit()
    
    # ═══════════════════════════════════
    # Stats
    # ═══════════════════════════════════
    
    def get_stats(self) -> Dict:
        """إحصاءات شاملة"""
        # إجمالي
        total = self.conn.execute(
            "SELECT COUNT(*) as c FROM trades WHERE result IS NOT NULL"
        ).fetchone()['c']
        
        if total == 0:
            return {"total": 0}
        
        wins = self.conn.execute("""
            SELECT COUNT(*) as c FROM trades 
            WHERE result IN ('TP1', 'TP2')
        """).fetchone()['c']
        
        losses = self.conn.execute("""
            SELECT COUNT(*) as c FROM trades WHERE result = 'SL'
        """).fetchone()['c']
        
        # حسب Regime
        by_regime = {}
        for regime in ['NEUTRAL', 'BULL', 'BEAR', 'STRONG_BEAR', 'STRONG_BULL']:
            r = self.conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN result IN ('TP1', 'TP2') THEN 1 ELSE 0 END) as wins
                FROM trades 
                WHERE result IS NOT NULL AND regime = ?
            """, (regime,)).fetchone()
            
            if r['total'] > 0:
                by_regime[regime] = {
                    'total': r['total'],
                    'wins': r['wins'],
                    'wr': r['wins'] / r['total']
                }
        
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "wr": wins / total if total > 0 else 0,
            "by_regime": by_regime
        }
    
    def close(self):
        """إغلاق الاتصال"""
        self.conn.close()


# Singleton
storage = Storage()
