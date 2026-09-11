"""Per-JID chat history stored in SQLite databases.

One ``<safe_bare_jid>.sqlite3`` file per contact under
``$XDG_DATA_HOME/stanza-im/history/``.  Connections are pooled so only the
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

from stanza_im.include.constants import HISTORY_DIR

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
    archive_id TEXT,
    origin_id TEXT,
    reply_to TEXT,
    reply_id TEXT,
    message_id TEXT,
    edited INTEGER NOT NULL DEFAULT 0
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


def _migrate_dedup(conn: sqlite3.Connection) -> None:
    """One-time maintenance: drop duplicate rows and add unique indexes.

    Existing databases may hold rows that are identical except for the
    autoincrement ``id`` (e.g. the same MAM/archived message stored twice).
    Keep the oldest row of each group and create partial unique indexes so the
    duplicates cannot come back.  Tracked via ``PRAGMA user_version``.
    """
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    except (sqlite3.Error, TypeError):
        version = 0
    if version >= 1:
        return
    no_ids = ("(archive_id IS NULL OR archive_id = '') "
              "AND (origin_id IS NULL OR origin_id = '') "
              "AND (message_id IS NULL OR message_id = '')")
    try:
        conn.execute(
            "DELETE FROM messages WHERE archive_id IS NOT NULL "
            "AND archive_id <> '' AND id NOT IN ("
            "SELECT MIN(id) FROM messages WHERE archive_id IS NOT NULL "
            "AND archive_id <> '' GROUP BY archive_id)")
        conn.execute(
            "DELETE FROM messages WHERE " + no_ids + " AND id NOT IN ("
            "SELECT MIN(id) FROM messages WHERE " + no_ids + " "
            "GROUP BY direction, sender, body, timestamp)")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_archive_unique "
            "ON messages(archive_id) WHERE archive_id IS NOT NULL "
            "AND archive_id <> ''")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_content_unique "
            "ON messages(direction, sender, body, timestamp) WHERE " + no_ids)
    except sqlite3.Error as exc:
        logger.warning("History dedup migration failed: %s", exc)
    try:
        conn.execute("PRAGMA user_version = 1")
    except sqlite3.Error:
        pass


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
        for col in ("origin_id", "reply_to", "reply_id"):
            if col not in columns:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {col} TEXT")
        for col in ("message_id",):
            if col not in columns:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {col} TEXT")
        if "edited" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN edited "
                         "INTEGER NOT NULL DEFAULT 0")
        _migrate_dedup(conn)
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
    _id, direction, sender, body, timestamp, archive_id, origin_id, \
        reply_to, reply_id, message_id, edited = row
    return {
        "id": _id,
        "direction": direction,
        "sender": sender,
        "body": body,
        "timestamp": timestamp,
        "archive_id": archive_id or "",
        "origin_id": origin_id or "",
        "reply_to": reply_to or "",
        "reply_id": reply_id or "",
        "message_id": message_id or "",
        "edited": bool(edited),
    }


def _entry_key(entry: dict) -> tuple:
    """Stable identity for a stored entry (stable ids preferred over content)."""
    if entry.get("archive_id"):
        return ("archive", entry["archive_id"])
    if entry.get("origin_id"):
        return ("origin", entry["origin_id"])
    if entry.get("message_id"):
        return ("message", entry["message_id"])
    return ("content", entry.get("direction", ""), entry.get("sender", ""),
            entry.get("body", ""), entry.get("timestamp", ""))


def _dedup(entries: list[dict]) -> list[dict]:
    """Drop entries that share the same identity (defensive read-side guard)."""
    seen: set = set()
    out: list[dict] = []
    for entry in entries:
        key = _entry_key(entry)
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def store_message(jid: str, direction: str, body: str,
                  timestamp: str | None = None, sender: str = "",
                  skip_existing: bool = True, archive_id: str = "",
                  origin_id: str = "", reply_to: str = "",
                  reply_id: str = "", message_id: str = "",
                  edited: bool = False) -> bool:
    """Append a message to *jid*'s history.

    By default (``skip_existing``) an already stored message is not duplicated.
    A row counts as the same when it shares any non-empty stable id
    (``archive_id``/``origin_id``/``message_id``) or, for rows that carry no
    ids at all, when direction/sender/body/timestamp match.  The content match
    only ever compares against id-less rows, so two distinct archived messages
    are never collapsed into one.  Pass ``skip_existing=False`` for an
    unconditional insert.
    """
    try:
        conn = _connection(jid)
        ts = timestamp or time.strftime("%Y-%m-%dT%H:%M:%S")
        if skip_existing:
            clauses: list[str] = []
            params: list = []
            if archive_id:
                clauses.append("archive_id = ?")
                params.append(archive_id)
            if origin_id:
                clauses.append("origin_id = ?")
                params.append(origin_id)
            if message_id:
                clauses.append("message_id = ?")
                params.append(message_id)
            clauses.append(
                "((archive_id IS NULL OR archive_id = '') "
                "AND (origin_id IS NULL OR origin_id = '') "
                "AND (message_id IS NULL OR message_id = '') "
                "AND direction = ? AND sender = ? AND body = ? "
                "AND timestamp = ?)")
            params.extend([direction, sender, body, ts])
            row = conn.execute(
                "SELECT id FROM messages WHERE (" + " OR ".join(clauses)
                + ") LIMIT 1", params).fetchone()
            if row:
                return False
        conn.execute(
            "INSERT INTO messages "
            "(direction, sender, body, timestamp, archive_id, "
            "origin_id, reply_to, reply_id, message_id, edited) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (direction, sender, body, ts, archive_id or None,
             origin_id or None, reply_to or None, reply_id or None,
             message_id or None, 1 if edited else 0),
        )
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.warning("Could not save history for %s: %s", jid, exc)
        return False


def replace_message(jid: str, ref_id: str, new_body: str) -> bool:
    """Replace the body of a stored message referenced by *ref_id* and mark
    it as edited (XEP-0308 corrections).  Matches by ``message_id`` or
    ``origin_id``."""
    if not ref_id:
        return False
    try:
        conn = _connection(jid)
        cur = conn.execute(
            "UPDATE messages SET body = ?, edited = 1 "
            "WHERE message_id = ? OR origin_id = ?",
            (new_body, ref_id, ref_id))
        conn.commit()
        return cur.rowcount > 0
    except sqlite3.Error as exc:
        logger.warning("Could not replace history for %s: %s", jid, exc)
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
            f"SELECT id, direction, sender, body, timestamp, archive_id,"
            f" origin_id, reply_to, reply_id, message_id, edited FROM messages"
            f"{clause} ORDER BY timestamp DESC, id DESC LIMIT ?) "
            f"ORDER BY timestamp ASC, id ASC",
            params)
        return _dedup([_row_to_entry(r) for r in cur.fetchall()])
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
            "SELECT id, direction, sender, body, timestamp, archive_id,"
            " origin_id, reply_to, reply_id, message_id, edited FROM messages "
            "WHERE id < ? ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
            (str(int(before_id)), str(int(limit))))
        return _dedup([_row_to_entry(r) for r in cur.fetchall()])
    except sqlite3.Error as exc:
        logger.warning("Could not load older history for %s: %s", jid, exc)
        return []


def load_older_timestamp(jid: str, before: str, limit: int = 200) -> list[dict]:
    """Load messages older than timestamp *before*, chronologically."""
    try:
        conn = _connection(jid)
        cur = conn.execute(
            "SELECT * FROM (SELECT id, direction, sender, body, timestamp, archive_id,"
            " origin_id, reply_to, reply_id, message_id, edited "
            "FROM messages WHERE timestamp < ? "
            "ORDER BY timestamp DESC, id DESC LIMIT ?) "
            "ORDER BY timestamp ASC, id ASC", (before, int(limit)))
        return _dedup([_row_to_entry(r) for r in cur.fetchall()])
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


def has_history(jid: str) -> bool:
    """True when *jid* has a history store (SQLite db or legacy JSONL)."""
    return os.path.isfile(_path(jid)) or _jsonl_exists(jid)


def _jsonl_exists(jid: str) -> bool:
    try:
        from stanza_im.core.storage import history_path
        return os.path.isfile(history_path(jid))
    except ImportError:
        return False


def list_history_jids() -> set[str]:
    """Return the set of JIDs that have a local history store.

    JIDs are recovered from ``.sqlite3`` filenames; safely recoverable ones
    (those containing a ``@``) are returned as-is, ambiguous slugs are kept
    verbatim.  The slash character in ``room/nick`` is stored as ``_`` so such
    legacy files can only be recovered against the known-contacts registry.
    """
    jids: set[str] = set()
    try:
        files = os.listdir(HISTORY_DIR)
    except OSError:
        return jids
    for name in files:
        if not name.endswith(".sqlite3"):
            continue
        slug = name[:-len(".sqlite3")]
        if "@" in slug:
            jids.add(slug)
    return jids


def dates(jid: str) -> list[str]:
    """Return the sorted list of ``YYYY-MM-DD`` dates that have messages."""
    try:
        conn = _connection(jid)
        rows = conn.execute(
            "SELECT DISTINCT substr(timestamp, 1, 10) AS d "
            "FROM messages WHERE d != '' ORDER BY d").fetchall()
        return [row[0] for row in rows if row[0]]
    except sqlite3.Error as exc:
        logger.warning("Could not read history dates for %s: %s", jid, exc)
        return []


def load_day(jid: str, date: str) -> list[dict]:
    """Read every message stored on *date* (``YYYY-MM-DD``), oldest first."""
    try:
        conn = _connection(jid)
        cur = conn.execute(
            "SELECT id, direction, sender, body, timestamp, archive_id,"
            " origin_id, reply_to, reply_id, message_id, edited "
            "FROM messages "
            "WHERE substr(timestamp, 1, 10) = ? "
            "ORDER BY timestamp ASC, id ASC", (date,))
        return _dedup([_row_to_entry(r) for r in cur.fetchall()])
    except sqlite3.Error as exc:
        logger.warning("Could not read history day %s for %s: %s",
                       date, jid, exc)
        return []


def search_dates(jid: str, query: str) -> list[tuple[str, int]]:
    """Return ``[(date, count)]`` of days containing a case-insensitive
    substring match of *query* in the message body, newest first."""
    try:
        conn = _connection(jid)
        cur = conn.execute(
            "SELECT substr(timestamp, 1, 10) AS d, COUNT(*) "
            "FROM messages WHERE body LIKE ? ESCAPE '\\' GROUP BY d "
            "ORDER BY d DESC", (f"%{_like_escape(query)}%",))
        return [(row[0], int(row[1])) for row in cur.fetchall() if row[0]]
    except sqlite3.Error as exc:
        logger.warning("Could not search history for %s: %s", jid, exc)
        return []


def _like_escape(query: str) -> str:
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
        from stanza_im.core.storage import history_path
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
