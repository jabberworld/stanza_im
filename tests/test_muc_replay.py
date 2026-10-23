"""Join-time MUC history replay on servers without MAM.

An old conference server replays its last messages with only a XEP-0203
``<delay/>`` (no ``<archived/>``).  That is history, not a live message: it
must be stored quietly (no sound/OSD/unread) and merged into the open window —
even when it is older than the local tail.  A room whose disco has no MAM is
not queried again and again.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_replay.py
"""
import inspect
import os
import sys
import tempfile
from types import SimpleNamespace
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_replay_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp
from PyQt6 import QtWidgets

from stanza_im.core.client import JabberClient, _delay_stamp
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.main_window import MainWindow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


def message(body, stamp="", archived=False):
    msg = slixmpp.Message()
    msg["from"] = "room@conf.example/Alice"
    msg["type"] = "groupchat"
    msg["body"] = body
    if stamp:
        delay = ET.SubElement(msg.xml, "{urn:xmpp:delay}delay")
        delay.set("stamp", stamp)
    if archived:
        ET.SubElement(msg.xml, "{urn:xmpp:mam:tmp}archived")
    return msg


def client():
    c = JabberClient.__new__(JabberClient)
    c._callbacks = {}
    c.groupchats = {}
    c._mam_inflight = set()
    c._muc_subjects = {}
    c._mark_muc_activity = lambda room: None
    c._is_omemo_encrypted = lambda msg: False
    c._omemo_flag = lambda msg: False
    c._mds_track = lambda *a, **k: None
    return c


# 1. a delayed delivery is history -----------------------------------------
c = client()
events = []
c.on("groupchat_message", lambda *a, **k: events.append((a, k)))

c._on_groupchat_message(message("old one", "2026-10-23T18:26:48Z"))
args, kwargs = events[-1]
check("a delay-only replay is classified as history", args[4] is True)
check("its original timestamp is used",
      args[3] == "2026-10-23T18:26:48.000000Z")
check("it carries no archive id (the room has no MAM)",
      args[5] == "")

c._on_groupchat_message(message("live now"))
args, kwargs = events[-1]
check("a live message stays live", args[4] is False and args[3] is None)

c._on_groupchat_message(message("mam row", "2026-10-23T19:00:00Z",
                                archived=True))
args, kwargs = events[-1]
check("a MAM archived row is history too", args[4] is True)

check("the delay stamp is read from the XML, not slixmpp's delay interface",
      _delay_stamp(message("x", "2026-10-23T20:00:00.500Z"))
      == "2026-10-23T20:00:00.500000Z")

# A 1:1 delayed message (offline storage) also keeps its original stamp.
fields = JabberClient._message_fields(message("one", "2026-10-23T21:00:00Z"))
check("a delayed 1:1 message keeps its original timestamp",
      fields[1] == "2026-10-23T21:00:00.000000Z")

# 2. the replay is merged with a forced window reload ----------------------
src = inspect.getsource(MainWindow._on_groupchat_message)
check("a delay-only replay forces the window merge",
      "schedule_tail_refresh(force=not archive_id)" in src)
check("a user-scrolled-up tab is not force-refreshed",
      'getattr(chat, "_user_scrolled_up", False)' in src)

# 3. no MAM query for a room that does not advertise an archive ------------
started = []


class _FakeChat:
    def __init__(self):
        self.exhausted = False
        self.status = ""

    def mark_server_exhausted(self):
        self.exhausted = True

    def set_history_status(self, text):
        self.status = text


class _FakeChatWindow:
    def __init__(self, chat):
        self.chat = chat

    def get_chat(self, jid):
        return self.chat


win = MainWindow.__new__(MainWindow)
win._client = SimpleNamespace()
win._chat_window = _FakeChatWindow(_FakeChat())
win._muc_self_nicks = {"room@conf.example": "me"}
win._mam_unsupported = set()
win._muc_room_features = {"room@conf.example": {"urn:xmpp:muc"}}
win._start_task = lambda coro: started.append(coro)

win._on_server_history("room@conf.example")
check("a known non-MAM room is not queried",
      started == [] and win._chat_window.chat.exhausted)
check("the room is remembered as archive-less",
      "room@conf.example" in win._mam_unsupported)

win._muc_room_features["mam@conf.example"] = {
    "urn:xmpp:mam:2", "urn:xmpp:muc"}
win._on_server_history("mam@conf.example")
check("a MAM room is queried", len(started) == 1)
for coro in started:
    coro.close()

win._on_mam_unavailable("other@conf.example")
check("a failed MAM query is remembered",
      "other@conf.example" in win._mam_unsupported)
history_src = inspect.getsource(MainWindow._on_server_history)
check("the history request consults the archive-less set",
      "self._mam_unsupported" in history_src)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All MUC replay tests passed.")
