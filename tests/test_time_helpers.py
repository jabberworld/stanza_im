"""Tests for the local-time/status-icon helpers (no Qt needed).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_time_helpers.py
"""
import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.include.utils import (
    format_local_datetime, local_time_from_tzo, status_icon_html)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

# format_local_datetime: unix and ISO inputs -> local YYYY-MM-DD HH:MM:SS ----
check("unix epoch formats as a stamp", bool(_STAMP.match(format_local_datetime(0))))
check("iso utc formats as a stamp",
      bool(_STAMP.match(format_local_datetime("2026-10-13T00:10:00Z"))))
check("digit string is treated as unix",
      bool(_STAMP.match(format_local_datetime("1700000000"))))
check("empty value returns empty", format_local_datetime("") == "")
check("None returns empty", format_local_datetime(None) == "")
check("garbage returns unchanged", format_local_datetime("nope") == "nope")

# local_time_from_tzo: live local time of an entity from its offset ----------
check("positive offset from epoch",
      local_time_from_tzo("+03:00", now=0) == "1970-01-01 03:00:00")
check("negative half-hour offset from epoch",
      local_time_from_tzo("-05:30", now=0) == "1969-12-31 18:30:00")
check("compact offset accepted",
      local_time_from_tzo("+0200", now=0) == "1970-01-01 02:00:00")
check("missing tzo returns empty", local_time_from_tzo("") == "")
check("malformed tzo returns empty", local_time_from_tzo("Z") == "")

# status_icon_html: presence show -> jabber-<key>.png ------------------------
check("online icon", "jabber-online.png" in status_icon_html("online"))
check("chat icon", "jabber-chat.png" in status_icon_html("chat"))
check("dnd icon", "jabber-dnd.png" in status_icon_html("dnd"))
check("empty show falls back to offline",
      "jabber-offline.png" in status_icon_html(""))

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All time-helper tests passed.")
