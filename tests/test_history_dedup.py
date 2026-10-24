"""Dedup tests for the SQLite chat history (no Qt required).

Run with:
    python3 tests/test_history_dedup.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_hist_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core import history

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. same archive_id is not duplicated ---------------------------------------
jid = "dedup-archive@example.com"
first = history.store_message(jid, "incoming", "hello",
                              timestamp="2026-01-01T10:00:00.000000Z",
                              sender="Bob", archive_id="arch-1")
second = history.store_message(jid, "incoming", "hello",
                               timestamp="2026-01-01T10:00:00.000000Z",
                               sender="Bob", archive_id="arch-1")
check("archive dup: first stored", first is True)
check("archive dup: second skipped", second is False)
check("archive dup: count==1", history.count_messages(jid) == 1)

# 1b. a stale archive timestamp is repaired without touching the body -------
jid1b = "dedup-archive-repair@example.com"
history.store_message(jid1b, "incoming", "fixed", sender="Bob",
                      timestamp="2026-10-21T15:14:13.000000Z",
                      archive_id="arch-repair")
repaired = history.store_message(jid1b, "incoming", "fixed", sender="Bob",
                                 timestamp="2026-10-22T13:09:08.000000Z",
                                 archive_id="arch-repair")
rows = history.load_history(jid1b, 10)
check("archive repair updates the timestamp", repaired is True
      and len(rows) == 1
      and rows[0]["timestamp"] == "2026-10-22T13:09:08.000000Z")
rewritten = history.store_message(jid1b, "incoming", "changed", sender="Bob",
                                  timestamp="2026-10-22T13:09:08.000000Z",
                                  archive_id="arch-repair")
rows = history.load_history(jid1b, 10)
check("archive repair never rewrites the body",
      rewritten is False and rows[0]["body"] == "fixed")

# 2. id-less identical content is not duplicated -----------------------------
jid2 = "dedup-content@example.com"
history.store_message(jid2, "incoming", "same", sender="Ann",
                      timestamp="2026-01-01T10:00:00")
dup = history.store_message(jid2, "incoming", "same", sender="Ann",
                            timestamp="2026-01-01T10:00:00")
check("content dup skipped", dup is False and history.count_messages(jid2) == 1)

# 3. identical text with a different timestamp is stored ---------------------
history.store_message(jid2, "incoming", "same", sender="Ann",
                      timestamp="2026-01-01T10:00:05")
check("different timestamp kept", history.count_messages(jid2) == 2)

# 4. live (no ids) then MAM row (archive_id) -> no duplicate -----------------
jid3 = "dedup-live-mam@example.com"
history.store_message(jid3, "incoming", "msg", sender="Cid",
                      timestamp="2026-01-01T11:00:00.000000Z")
history.store_message(jid3, "incoming", "msg", sender="Cid",
                      timestamp="2026-01-01T11:00:00.000000Z",
                      archive_id="arch-9")
check("live+mam deduped", history.count_messages(jid3) == 1)

# 4b. a delayed replay adopts the older live copy (receive time) -----------
jid4 = "dedup-replay-legacy@example.com"
history.store_message(jid4, "incoming", "replayed", sender="Dan",
                      timestamp="2026-01-01T12:05:00.000000Z")
adopted = history.store_message(
    jid4, "incoming", "replayed", sender="Dan",
    timestamp="2026-01-01T11:00:00.000000Z",
    origin_id="orig-1", archived=True)
rows = history.load_history(jid4, 10)
check("an archived replay adopts the live copy", adopted is True
      and len(rows) == 1
      and rows[0]["timestamp"] == "2026-01-01T11:00:00.000000Z"
      and rows[0].get("origin_id") == "orig-1")

# 4c. a live row never adopts an id-less one --------------------------------
jid5 = "dedup-live-no-adopt@example.com"
history.store_message(jid5, "incoming", "live same", sender="Eve",
                      timestamp="2026-01-01T12:05:00.000000Z")
history.store_message(jid5, "incoming", "live same", sender="Eve",
                      timestamp="2026-01-01T12:05:10.000000Z",
                      origin_id="orig-2")
check("two live copies are kept", history.count_messages(jid5) == 2)

# 4d. the same replay re-stored with a stable id is not duplicated ---------
jid6 = "dedup-replay-repeat@example.com"
history.store_message(jid6, "incoming", "again", sender="Fay",
                      timestamp="2026-01-01T13:00:00.000000Z",
                      origin_id="orig-3")
history.store_message(jid6, "incoming", "again", sender="Fay",
                      timestamp="2026-01-01T13:00:05.000000Z",
                      origin_id="orig-3")
rows = history.load_history(jid6, 10)
check("a stable-id replay dedups across the wrong timestamp",
      len(rows) == 1
      and rows[0]["timestamp"] == "2026-01-01T13:00:05.000000Z")

# 5. distinct archived rows with same text/time are kept --------------------
jid4 = "dedup-distinct-archive@example.com"
history.store_message(jid4, "incoming", "ping", sender="Dan",
                      timestamp="2026-01-01T12:00:00.000000Z",
                      archive_id="arch-a")
history.store_message(jid4, "incoming", "ping", sender="Dan",
                      timestamp="2026-01-01T12:00:00.000000Z",
                      archive_id="arch-b")
check("distinct archives kept", history.count_messages(jid4) == 2)

# 6. migration cleans a pre-existing duplicate DB ---------------------------
import sqlite3
jid5 = "dedup-migrate@example.com"
path = history._path(jid5)
os.makedirs(os.path.dirname(path), exist_ok=True)
raw = sqlite3.connect(path)
raw.execute(
    "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "direction TEXT NOT NULL, sender TEXT NOT NULL DEFAULT '', "
    "body TEXT NOT NULL DEFAULT '', timestamp TEXT NOT NULL, "
    "archive_id TEXT, origin_id TEXT, reply_to TEXT, reply_id TEXT, "
    "message_id TEXT, edited INTEGER NOT NULL DEFAULT 0)")
for _ in range(3):
    raw.execute(
        "INSERT INTO messages (direction, sender, body, timestamp, "
        "archive_id, origin_id) VALUES "
        "('incoming','Eve','dup','2026-01-01T13:00:00.000000Z','m1','m1')")
raw.commit()
raw.close()

entries = history.load_history(jid5)  # triggers _connection migration
check("migration collapsed dups", len(entries) == 1
      and history.count_messages(jid5) == 1)
conn = history._connection(jid5)
indexes = {row[1] for row in conn.execute("PRAGMA index_list(messages)")}
check("archive unique index created",
      "idx_messages_archive_unique" in indexes)
check("content unique index created",
      "idx_messages_content_unique" in indexes)
check("user_version bumped",
      conn.execute("PRAGMA user_version").fetchone()[0] == 1)

# 7. load_day returns no duplicates ------------------------------------------
day = history.load_day(jid5, "2026-01-01")
check("load_day deduped", len(day) == 1)

history.close_all()
print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
