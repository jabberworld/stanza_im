"""Offscreen regression: a live outgoing row and its MAM copy render once."""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="stanza_chat_dedup_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(os.environ["XDG_DATA_HOME"], "config")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.include import constants
constants.set_webengine_enabled(False)
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

origin = "fe57d27cad174d749d9ad116155f1285"
live = {
    "direction": "outgoing", "sender": "Me", "body": "hello",
    "timestamp": "2026-11-16T10:57:23.799885Z",
    "archive_id": "", "stanza_id": "", "origin_id": origin,
    "message_id": origin, "reply_to": "", "reply_id": "",
}
mam = dict(live, timestamp="2026-11-16T10:57:23.858807Z",
           archive_id="1794826643858807", stanza_id="1794826643858807")

cw = ChatWidget("5997305839@tg.jabberworld.info", "R", ChatThemeFactory())
cw._messages = [live]
cw._history = [mam]
entries = cw._ordered_entries()

checks = [
    ("the live and MAM copies share the origin key",
     cw._entry_key(live) == cw._entry_key(mam)),
    ("the merged window contains one copy", len(entries) == 1),
    ("the stored MAM copy is the one rendered",
     entries and entries[0].get("stanza_id") == "1794826643858807"),
]
failures = []
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + ": " + name)
    if not ok:
        failures.append(name)
cw.detach()
if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print("All chat-dedup tests passed.")
