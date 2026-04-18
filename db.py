"""Local SQLite for push subscriptions (ephemeral — survives restarts but not redeploys)."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "./push_subscriptions.db")


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _db():
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT UNIQUE NOT NULL,
                keys_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )


def save_subscription(subscription: dict):
    now = datetime.now(timezone.utc).isoformat()
    endpoint = subscription["endpoint"]
    keys_json = json.dumps(subscription.get("keys", {}))
    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO push_subscriptions (endpoint, keys_json, created_at) VALUES (?, ?, ?)",
            (endpoint, keys_json, now),
        )


def delete_subscription(endpoint: str):
    with _db() as conn:
        conn.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
        )


def get_all_subscriptions() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT endpoint, keys_json FROM push_subscriptions"
        ).fetchall()
    return [
        {"endpoint": r["endpoint"], "keys": json.loads(r["keys_json"])} for r in rows
    ]
