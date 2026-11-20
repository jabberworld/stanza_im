"""Persistent prepared chat-render cache.

Only the *base* message HTML is stored: the unread separator, delivery checks
and read eyes are applied when the tab is opened, so a cached window can never
change the read state.  Payloads are zlib-compressed and kept on disk; the
in-memory footprint is limited to the chat currently being opened.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import zlib

from stanza_im.include.constants import CACHE_DIR

logger = logging.getLogger(__name__)

MAX_CHATS = 100
MAX_BYTES = 64 * 1024 * 1024
_DB_NAME = "chat-render.sqlite3"
_LOCK = threading.RLock()


def path() -> str:
    return os.path.join(CACHE_DIR, _DB_NAME)


def _connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    conn = sqlite3.connect(path(), timeout=10)
    try:
        os.chmod(path(), 0o600)
    except OSError:
        pass
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS render_cache ("
        "account TEXT NOT NULL, jid TEXT NOT NULL, settings_hash TEXT NOT NULL,"
        "last_ref TEXT, window_size INTEGER NOT NULL DEFAULT 0,"
        "payload BLOB NOT NULL, created_at REAL NOT NULL,"
        "accessed_at REAL NOT NULL,"
        "PRIMARY KEY (account, jid))")
    conn.commit()
    return conn


def get(account: str, jid: str, settings_hash: str,
        refs: list[str]) -> list[str] | None:
    """Return prepared HTML fragments when *refs* and the settings match."""
    if not account or not jid or not refs:
        return None
    try:
        with _LOCK:
            conn = _connection()
            try:
                row = conn.execute(
                    "SELECT settings_hash, last_ref, payload FROM render_cache "
                    "WHERE account=? AND jid=?", (account, jid)).fetchone()
                if row is None or row[0] != settings_hash:
                    return None
                data = json.loads(zlib.decompress(row[2]).decode("utf-8"))
                if list(data.get("refs") or []) != list(refs):
                    return None
                html = [str(item) for item in (data.get("html") or [])]
                if len(html) != len(refs):
                    return None
                conn.execute(
                    "UPDATE render_cache SET accessed_at=? "
                    "WHERE account=? AND jid=?",
                    (time.time(), account, jid))
                conn.commit()
                return html
            finally:
                conn.close()
    except (sqlite3.Error, ValueError, zlib.error) as exc:
        logger.debug("chat render cache read failed for %s: %s", jid, exc)
        return None


def put(account: str, jid: str, settings_hash: str, refs: list[str],
        html: list[str], window_size: int = 0) -> None:
    """Store a prepared window and enforce the count/byte LRU limits."""
    if not account or not jid or not refs or len(refs) != len(html):
        return
    payload = zlib.compress(json.dumps(
        {"refs": list(refs), "html": list(html)},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)
    now = time.time()
    try:
        with _LOCK:
            conn = _connection()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO render_cache "
                    "(account, jid, settings_hash, last_ref, window_size,"
                    " payload, created_at, accessed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (account, jid, settings_hash, refs[-1],
                     int(window_size or 0), payload, now, now))
                conn.commit()
                _evict_locked(conn)
            finally:
                conn.close()
    except sqlite3.Error as exc:
        logger.debug("chat render cache write failed for %s: %s", jid, exc)


def _evict_locked(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT account, jid, length(payload) FROM render_cache "
        "ORDER BY accessed_at ASC").fetchall()
    total = sum(int(row[2] or 0) for row in rows)
    count = len(rows)
    remove = []
    for account, jid, size in rows:
        if count <= MAX_CHATS and total <= MAX_BYTES:
            break
        remove.append((account, jid))
        total -= int(size or 0)
        count -= 1
    for account, jid in remove:
        conn.execute("DELETE FROM render_cache WHERE account=? AND jid=?",
                     (account, jid))
    if remove:
        conn.commit()


def invalidate(account: str, jid: str = "") -> None:
    if not account:
        return
    try:
        with _LOCK:
            conn = _connection()
            try:
                if jid:
                    conn.execute(
                        "DELETE FROM render_cache WHERE account=? AND jid=?",
                        (account, jid))
                else:
                    conn.execute("DELETE FROM render_cache WHERE account=?",
                                 (account,))
                conn.commit()
            finally:
                conn.close()
    except sqlite3.Error:
        pass


def clear() -> None:
    """Remove every prepared chat window (used by Help → Cache)."""
    try:
        with _LOCK:
            conn = _connection()
            try:
                conn.execute("DELETE FROM render_cache")
                conn.commit()
                conn.execute("VACUUM")
            finally:
                conn.close()
    except sqlite3.Error:
        pass


def total_bytes() -> int:
    try:
        with _LOCK:
            conn = _connection()
            try:
                row = conn.execute(
                    "SELECT COALESCE(SUM(length(payload)), 0) "
                    "FROM render_cache").fetchone()
                return int(row[0] or 0)
            finally:
                conn.close()
    except sqlite3.Error:
        return 0


def count() -> int:
    try:
        with _LOCK:
            conn = _connection()
            try:
                return int(conn.execute(
                    "SELECT COUNT(*) FROM render_cache").fetchone()[0] or 0)
            finally:
                conn.close()
    except sqlite3.Error:
        return 0
