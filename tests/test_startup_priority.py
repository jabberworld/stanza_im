"""Tests for the startup priority/cache changes (no network).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_startup_priority.py
"""
import logging
import os
import sys
import tempfile
import time

_SCRATCH = tempfile.mkdtemp(prefix="stanza_priority_")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.app import _XmlRedactFilter  # noqa: E402
from stanza_im.core import vcard_cache  # noqa: E402
from stanza_im.core.vcard_cache import VCardCache  # noqa: E402
from stanza_im.include import avatars  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. vCard TTL is three days and deferred writes coalesce --------------------
check("vCard TTL is three days", vcard_cache.MAX_AGE == 3 * 24 * 60 * 60)
vc = VCardCache(os.path.join(_SCRATCH, "vcard.json"))
vc.put("bob@example.com", {"fn": "Bob"}, defer=True)
check("deferred write is visible in memory",
      vc.get("bob@example.com", max_age=10**9)["fn"] == "Bob")
check("deferred write waits for the flush",
      not os.path.isfile(vc.path))
vc.flush()
check("flush writes the deferred batch", os.path.isfile(vc.path))
check("the flushed card can be reloaded",
      VCardCache(vc.path).get("bob@example.com", max_age=10**9)["fn"] == "Bob")

# 2. identical avatar bytes are not rewritten --------------------------------
raw = b"\x89PNG\r\n\x1a\nsame-avatar"
path = avatars.save_avatar("bob@example.com", raw)
stamp = os.stat(path).st_mtime_ns
time.sleep(0.02)
path2 = avatars.save_avatar("bob@example.com", raw)
check("same avatar path is returned", path == path2)
check("identical avatar bytes are not rewritten",
      os.stat(path).st_mtime_ns == stamp)

# 3. minimized replay keeps unread rows and trims only old ones --------------
from stanza_im.ui.main_window import MainWindow  # noqa: E402

win = MainWindow.__new__(MainWindow)
win._chat_window = type("CW", (), {
    "get_chat": lambda self, key: None,
})()
win._should_minimize_muc = lambda room: True
win._read_state = lambda room: {"unread": 2, "read_ts": "2026-10-21T11:00:00Z",
                                "seen_ts": ""}
rows = [
    {"timestamp": "2026-10-21T10:00:00Z"},
    {"timestamp": "2026-10-21T11:30:00Z"},
    {"timestamp": "2026-10-21T12:00:00Z"},
]
kept = MainWindow._replay_rows_to_store(win, "room@conf.example", rows)
check("minimized replay drops rows older than the read anchor",
      kept == rows[1:])

win._read_state = lambda room: {"unread": 0, "read_ts": "",
                                "seen_ts": ""}
kept = MainWindow._replay_rows_to_store(
    win, "room@conf.example", [{"timestamp": f"t{i}"} for i in range(60)])
check("a read minimized room keeps a bounded tail", len(kept) == 50)

win._chat_window = type("CW", (), {
    "get_chat": lambda self, key: object(),
})()
kept = MainWindow._replay_rows_to_store(win, "room@conf.example", rows)
check("an open room keeps the full replay", kept == rows)

# 4. Qt application/cache names are unified --------------------------------
import inspect
from stanza_im import app as app_module
main_src = inspect.getsource(app_module.run)
check("Qt uses the same stanza-im directory as the XDG stores",
      'setApplicationName("stanza-im")' in main_src)
check("the human-readable app name stays the display name",
      "setApplicationDisplayName(APP_NAME)" in main_src)

# 5. diagnostic XML logging does not retain base64 PHOTO payloads -------------
record = logging.LogRecord(
    "slixmpp.xmlstream.xmlstream", logging.DEBUG, __file__, 1,
    "SEND: <vCard><PHOTO><BINVAL>%s</BINVAL></PHOTO></vCard>",
    ("A" * 5000,), None)
_XmlRedactFilter().filter(record)
check("BINVAL is omitted from the diagnostic log",
      "<BINVAL>[omitted]</BINVAL>" in record.getMessage()
      and "AAAA" not in record.getMessage())

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All startup-priority tests passed.")
