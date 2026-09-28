"""Offscreen tests for presence handling.

Regression: slixmpp folds a bare ``<show>`` value into the presence ``type``
(so a transport presence with ``<show>away</show>`` and no ``type`` arrives as
``presence_away``, not ``presence_available``).  ``JabberClient._on_presence``
is subscribed to the generic ``presence`` event and must treat show-based types
as available.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_presence_show.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_pres_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp

from stanza_im.core.client import JabberClient

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _presence(attrs: str, body: str = ""):
    p = slixmpp.Presence()
    p.xml = ET.fromstring(
        f"<presence xmlns='jabber:client' {attrs}>{body}</presence>")
    return p


class _Contact:
    def __init__(self):
        self.resources = {}
        self.show = "offline"
        self.status = ""


def _client():
    c = JabberClient.__new__(JabberClient)
    c.presences = {}
    c._known_rooms = set()
    c.emitted = []
    c.emit = lambda ev, *a: c.emitted.append((ev, a))
    c._contact = _Contact()
    c.get_contact = lambda bare: c._contact
    c._version_probed = set()
    c._start_task = lambda *a, **k: None
    c._ensure_pep_subscription = lambda *a, **k: None
    c._maybe_refresh_pep = lambda *a, **k: None
    return c


# 1. show-based type (transport/RSS presence) is treated as available --------
c = _client()
c._on_presence(_presence("from='feed@rss.jabberworld.info/rss' to='me@x/r'",
                         "<show>away</show><status>News</status>"))
check("show=away emits presence_changed with away",
      c.emitted == [("presence_changed",
                     ("feed@rss.jabberworld.info", "away", "News"))])

c = _client()
c._on_presence(_presence("from='feed@rss.jabberworld.info/rss' to='me@x/r'",
                         "<show>chat</show>"))
check("show=chat emits presence_changed with chat",
      c.emitted == [("presence_changed",
                     ("feed@rss.jabberworld.info", "chat", ""))])

c = _client()
c._on_presence(_presence("from='feed@rss.jabberworld.info/rss' to='me@x/r'",
                         "<show>xa</show>"))
check("show=xa emits presence_changed with xa",
      c.emitted[0][1][1] == "xa")

# 2. bare available (no <show>) -> online -------------------------------------
c = _client()
c._on_presence(_presence("from='bot@transport.example/rss' to='me@x/r'"))
check("bare presence emits online",
      c.emitted == [("presence_changed",
                     ("bot@transport.example", "online", ""))])

# 3. unavailable -> offline ---------------------------------------------------
c = _client()
c._on_presence(_presence("from='bot@transport.example/rss' to='me@x/r' "
                         "type='unavailable'"))
check("unavailable emits offline",
      c.emitted == [("presence_changed",
                     ("bot@transport.example", "offline", ""))])

# 4. service types are ignored by the generic handler -------------------------
for stype in ("subscribe", "subscribed", "unsubscribe", "unsubscribed",
              "probe", "error"):
    c = _client()
    c._on_presence(_presence(
        f"from='a@b' to='me@x/r' type='{stype}'"))
    check(f"type={stype} does not emit presence_changed", c.emitted == [])

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All presence-show tests passed.")
