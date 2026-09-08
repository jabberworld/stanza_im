"""Per-JID chat history stored in SQLite databases.

One ``<safe_bare_jid>.sqlite3`` file per contact under
``$XDG_DATA_HOME/jabbim/history/``.  Connections are pooled so only the
databases of recently used conversations stay open (WAL mode, safe for
querying by time range and future MAM backfills).

The old JSON-lines history (``.jsonl``) is migrated lazily on first open.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from collections import OrderedDict

from jabbim.include.constants import HISTORY_DIR

logger = logging.getLogger(__name__)

_MAX_CONNECTIONS = 32
_CONN_TTL = 300.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL,
    sender TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL,
    archive_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
"""

# jid -> (connection, last_use_monotonic)
_pool: OrderedDict[str, tuple[sqlite3.Connection, float]] = OrderedDict()


def _path(jid: str) -> str:
    safe = jid.lower().replace("/", "_")
    return os.path.join(HISTORY_DIR, f"{safe}.sqlite3")


def _evict_expired(now: float) -> None:
    stale = [jid for jid, (_, t) in _pool.items() if now - t > _CONN_TTL]
    for jid in stale:
        close(jid)


def _connection(jid: str) -> sqlite3.Connection:
    now = time.monotonic()
    _evict_expired(now)
    entry = _pool.get(jid)
    if entry is not None:
        _pool.move_to_end(jid)
        _pool[jid] = (entry[0], now)
        return entry[0]

    os.makedirs(HISTORY_DIR, exist_ok=True)
    conn = sqlite3.connect(_path(jid), timeout=5)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(_SCHEMA)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        if "archive_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN archive_id TEXT")
        conn.commit()
    except sqlite3.Error:
        conn.close()
        raise
    _pool[jid] = (conn, now)

    while len(_pool) > _MAX_CONNECTIONS:
        oldest = next(iter(_pool))
        if oldest == jid:
            break
        close(oldest)
    return conn


def _row_to_entry(row) -> dict:
    _id, direction, sender, body, timestamp, archive_id = row
    return {
        "id": _id,
        "direction": direction,
        "sender": sender,
        "body": body,
        "timestamp": timestamp,
        "archive_id": archive_id or "",
    }


def store_message(jid: str, direction: str, body: str,
                  timestamp: str | None = None, sender: str = "",
                  skip_existing: bool = False, archive_id: str = "") -> bool:
    """Append a message to *jid*'s history.

    With ``skip_existing`` a row with the same (sender, body, timestamp)
    is treated as already stored and is not duplicated (used when a MAM
    query overlaps the locally cached range).
    """
    try:
        conn = _connection(jid)
        ts = timestamp or time.strftime("%Y-%m-%dT%H:%M:%S")
        if skip_existing:
            row = None
            if archive_id:
                row = conn.execute(
                    "SELECT id FROM messages WHERE archive_id = ? LIMIT 1",
                    (archive_id,)).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT id FROM messages WHERE sender = ? AND body = ? "
                    "AND timestamp = ? LIMIT 1", (sender, body, ts)).fetchone()
            if row:
                return False
        conn.execute(
            "INSERT INTO messages "
            "(direction, sender, body, timestamp, archive_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (direction, sender, body, ts, archive_id or None),
        )
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.warning("Could not save history for %s: %s", jid, exc)
        return False


def load_history(jid: str, limit: int = 200, since: str | None = None,
                 until: str | None = None) -> list[dict]:
    """Read the most recent history entries (oldest first), optionally
    filtered by a time range (inclusive; matches stored ``YYYY-MM-DD...``
    timestamps).  Limiting applies to the newest rows so ``load_history``
    always returns the tail of the conversation."""
    try:
        conn = _connection(jid)
        where = []
        params: list[str] = []
        if since:
            where.append("timestamp >= ?")
            params.append(since)
        if until:
            where.append("timestamp <= ?")
            params.append(until)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        params.append(str(int(limit)))
        cur = conn.execute(
            f"SELECT * FROM ("
            f"SELECT id, direction, sender, body, timestamp, archive_id FROM messages"
            f"{clause} ORDER BY timestamp DESC, id DESC LIMIT ?) "
            f"ORDER BY timestamp ASC, id ASC",
            params)
        return [_row_to_entry(r) for r in cur.fetchall()]
    except sqlite3.Error as exc:
        logger.warning("Could not read history for %s: %s", jid, exc)
        return []


def load_older(jid: str, before_id: int, limit: int = 200) -> list[dict]:
    """Load rows stored strictly before ``before_id`` (oldest first).

    Used to extend the on-screen history window backwards when the user
    scrolls towards the top of the conversation."""
    try:
        conn = _connection(jid)
        cur = conn.execute(
            "SELECT * FROM ("
            "SELECT id, direction, sender, body, timestamp, archive_id FROM messages "
            "WHERE id < ? ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
            (str(int(before_id)), str(int(limit))))
        return [_row_to_entry(r) for r in cur.fetchall()]
    except sqlite3.Error as exc:
        logger.warning("Could not load older history for %s: %s", jid, exc)
        return []


def load_older_timestamp(jid: str, before: str, limit: int = 200) -> list[dict]:
    """Load messages older than timestamp *before*, chronologically."""
    try:
        conn = _connection(jid)
        cur = conn.execute(
            "SELECT * FROM (SELECT id, direction, sender, body, timestamp, archive_id "
            "FROM messages WHERE timestamp < ? "
            "ORDER BY timestamp DESC, id DESC LIMIT ?) "
            "ORDER BY timestamp ASC, id ASC", (before, int(limit)))
        return [_row_to_entry(r) for r in cur.fetchall()]
    except sqlite3.Error as exc:
        logger.warning("Could not load older timestamp history for %s: %s",
                       jid, exc)
        return []


def older_available_timestamp(jid: str, before: str) -> bool:
    try:
        conn = _connection(jid)
        row = conn.execute(
            "SELECT 1 FROM messages WHERE timestamp < ? LIMIT 1",
            (before,)).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


def count_messages(jid: str) -> int:
    try:
        conn = _connection(jid)
        row = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0


def first_id(jid: str) -> int | None:
    """Return the smallest stored message id for *jid*, or ``None``."""
    try:
        conn = _connection(jid)
        row = conn.execute("SELECT MIN(id) FROM messages").fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except sqlite3.Error:
        return None


def last_id(jid: str) -> int | None:
    """Return the largest stored message id for *jid*, or ``None``."""
    try:
        conn = _connection(jid)
        row = conn.execute("SELECT MAX(id) FROM messages").fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except sqlite3.Error:
        return None


def older_available(jid: str, before_id: int) -> bool:
    """True when rows exist that were stored before ``before_id``."""
    fid = first_id(jid)
    return fid is not None and fid < int(before_id)


def clear(jid: str) -> None:
    """Delete all locally stored history for *jid*."""
    try:
        conn = _connection(jid)
        conn.execute("DELETE FROM messages")
        conn.commit()
    except sqlite3.Error as exc:
        logger.warning("Could not clear history for %s: %s", jid, exc)


def close(jid: str) -> None:
    """Close and drop *jid*'s pooled connection (call on tab close)."""
    entry = _pool.pop(jid, None)
    if entry is not None:
        try:
            entry[0].close()
        except sqlite3.Error:
            pass


def close_all() -> None:
    jids = list(_pool)
    for jid in jids:
        close(jid)


def migrate_from_jsonl(jid: str) -> bool:
    """Import a legacy ``.jsonl`` history file if a fresh SQLite DB exists.

    Returns True when an import happened (call once per JID)."""
    path = _path(jid)
    if os.path.isfile(path):
        return False
    try:
        from jabbim.core.storage import history_path
        jsonl = history_path(jid)
    except ImportError:
        return False
    if not os.path.isfile(jsonl):
        return False
    imported = 0
    try:
        conn = _connection(jid)
        with open(jsonl, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    import json
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                conn.execute(
                    "INSERT INTO messages (direction, sender, body, timestamp) "
                    "VALUES (?, ?, ?, ?)",
                    (entry.get("direction", "incoming"),
                     entry.get("sender", ""),
                     entry.get("body", ""),
                     entry.get("timestamp", "")),
                )
                imported += 1
        conn.commit()
        if imported:
            logger.info("Migrated %d entries from %s", imported, jsonl)
        return True
    except (OSError, sqlite3.Error) as exc:
        logger.warning("JSONL migration failed for %s: %s", jid, exc)
        return False
