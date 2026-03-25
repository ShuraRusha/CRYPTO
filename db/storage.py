"""
SQLite storage for score history and previous results.
"""
import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, db_path: str = "data/bot.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS score_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    coin TEXT NOT NULL,
                    composite_score REAL NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_score_coin_date 
                ON score_history(coin, created_at)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    coin TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def save_result(self, result: dict):
        """Save a coin analysis result."""
        now = datetime.now(timezone.utc).isoformat()
        # Remove non-serializable pandas objects
        clean = _clean_for_json(result)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO score_history (coin, composite_score, result_json, created_at) VALUES (?, ?, ?, ?)",
                (result["coin"], result["composite_score"], json.dumps(clean), now),
            )
            conn.commit()

    def get_previous_result(self, coin: str) -> Optional[dict]:
        """Get the most recent previous result for a coin."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT result_json FROM score_history WHERE coin = ? ORDER BY created_at DESC LIMIT 1",
                (coin,),
            ).fetchone()
            if row:
                return json.loads(row[0])
        return None

    def get_all_previous_results(self) -> dict:
        """Get the most recent result for each coin. Returns {coin: result_dict}."""
        results = {}
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT coin, result_json FROM score_history 
                WHERE id IN (
                    SELECT MAX(id) FROM score_history GROUP BY coin
                )
            """).fetchall()
            for coin, rjson in rows:
                results[coin] = json.loads(rjson)
        return results

    def log_alert(self, coin: str, alert_type: str, message: str):
        """Log an alert to history."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO alerts_log (coin, alert_type, message, created_at) VALUES (?, ?, ?, ?)",
                (coin, alert_type, message, now),
            )
            conn.commit()

    def cleanup_old(self, days: int = 30):
        """Remove entries older than N days."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"DELETE FROM score_history WHERE created_at < datetime('now', '-{days} days')"
            )
            conn.execute(
                f"DELETE FROM alerts_log WHERE created_at < datetime('now', '-{days} days')"
            )
            conn.commit()
            logger.info(f"Cleaned up records older than {days} days")


def _clean_for_json(result: dict) -> dict:
    """Remove non-serializable objects (pandas Series/DataFrames) from result."""
    skip_keys = {"rsi_series", "macd_df", "bb_df", "close_series"}
    clean = {}
    for k, v in result.items():
        if k in skip_keys:
            continue
        if isinstance(v, dict):
            clean[k] = _clean_for_json(v)
        else:
            try:
                json.dumps(v)
                clean[k] = v
            except (TypeError, ValueError):
                clean[k] = str(v)
    return clean
