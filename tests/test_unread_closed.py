"""Offscreen test: explicit mark-read for a closed chat stores an anchor."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.ui.main_window import MainWindow

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


win = MainWindow.__new__(MainWindow)
win._chat_window = None
win._client = None
captured = {}


def _capture(jid, anchor=None):
    captured["jid"] = jid
    captured["anchor"] = dict(anchor or {})


win._reset_unread = _capture
MainWindow._mark_chat_read(win, "rss@example.org", whole=True)
anchor = captured.get("anchor") or {}
check("the explicit action clears the closed chat",
      captured.get("jid") == "rss@example.org")
check("the explicit action stores a read timestamp",
      bool(anchor.get("ts")))
check("the read anchor has no fabricated message id",
      anchor.get("ref") == "")

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All closed-chat mark-read tests passed")
