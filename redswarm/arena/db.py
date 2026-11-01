from __future__ import annotations

import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS bounties (
    id INTEGER PRIMARY KEY, target_url TEXT NOT NULL, token TEXT NOT NULL,
    poster_key TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0,
    label TEXT NOT NULL DEFAULT '', initial TEXT NOT NULL DEFAULT '0');
CREATE TABLE IF NOT EXISTS attackers (account TEXT PRIMARY KEY, api_key TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, bounty_id INTEGER NOT NULL, attacker TEXT NOT NULL,
    channel TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL, reply TEXT,
    status TEXT NOT NULL, outcome TEXT NOT NULL, payout TEXT NOT NULL DEFAULT '0',
    created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS leads (
    lead_id INTEGER PRIMARY KEY, bounty_id INTEGER NOT NULL, author TEXT NOT NULL, content TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lead_sales (
    lead_id INTEGER NOT NULL, buyer TEXT NOT NULL, PRIMARY KEY (lead_id, buyer));
CREATE TABLE IF NOT EXISTS pending_fees (
    id INTEGER PRIMARY KEY AUTOINCREMENT, bounty_id INTEGER NOT NULL, attacker TEXT NOT NULL,
    amount TEXT NOT NULL, flushed INTEGER NOT NULL DEFAULT 0);
"""


class Db:
    """Thin sqlite wrapper. One connection guarded by a lock; the arena is single process."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.executescript(SCHEMA)

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.lastrowid

    def one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()
