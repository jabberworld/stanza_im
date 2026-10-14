"""Offscreen tests for the history-manager text export.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_history_export.py
"""
import asyncio
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_histexp_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core import history
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.history_manager import HistoryManagerDialog, _stamp

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

JID = "bob@example.com"
history.store_message(JID, "incoming", "hello there",
                      "2026-10-13T00:10:00Z", sender="Bob")
history.store_message(JID, "outgoing", "hi\nsecond line",
                      "2026-10-13T00:11:05Z")
history.store_message(JID, "incoming", "bye", "2026-10-14T09:00:00Z",
                      sender="Bob")

check("stamp formats an ISO timestamp",
      _stamp("2026-10-13T00:10:00Z") == "2026-10-13 00:10:00")
check("stamp tolerates an empty value", _stamp("") == "")

dlg = HistoryManagerDialog(lambda: [], "")
dlg._jid = JID

out = os.path.join(_SCRATCH, "bob.txt")
asyncio.run(dlg._export_async(out))
with open(out, encoding="utf-8") as handle:
    text = handle.read()

lines = text.splitlines()
check("one line per message", len(lines) == 3)
check("incoming line formatted",
      lines[0] == "[2026-10-13 00:10:00] Bob: hello there")
check("own message shows as Me",
      lines[1] == "[2026-10-13 00:11:05] Me: hi second line")
check("second day line present",
      lines[2] == "[2026-10-14 09:00:00] Bob: bye")
check("newlines collapsed to one line", "\n" not in lines[1])

# Empty conversation -> friendly status, no file written.
empty_jid = "nobody@example.com"
empty_path = os.path.join(_SCRATCH, "nobody.txt")
dlg._jid = empty_jid
asyncio.run(dlg._export_async(empty_path))
check("empty history writes no file", not os.path.exists(empty_path))

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All history-export tests passed.")
