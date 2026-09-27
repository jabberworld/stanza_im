"""Offscreen tests for presence subscription requests (authorization).

Covers the client handlers (incoming subscribe/unsubscribe/unsubscribed) and the
Events-tab row with Approve/Reject buttons.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_subscriptions.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_subs_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xml.etree import ElementTree as ET

from PyQt6 import QtWidgets
import slixmpp

from stanza_im.core.client import JabberClient
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.main_window import MainWindow, _SubscriptionRequestRow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. Client: incoming subscribe ----------------------------------------------
c = JabberClient.__new__(JabberClient)
c.xmpp = slixmpp.ClientXMPP("me@example.com/r", "pw")
c.jid_str = "me@example.com"
c._full_jid = "me@example.com/r"
c.emitted = []
c.emit = lambda ev, *a: c.emitted.append((ev, a))
c.subscribed = []


def _sub(jid, ptype="subscribe", nick=None):
    m = slixmpp.Presence()
    m["from"] = jid
    m["to"] = "me@example.com"
    m["type"] = ptype
    if nick:
        ET.SubElement(m.xml, "nick").text = nick
    return m


_sent = []
c.xmpp.send_presence_subscription = (
    lambda pto, pfrom=None, ptype="", **k: _sent.append((pto, ptype)))

c.subscription = lambda bare: "none"
c.get_contact = lambda bare: None
c._on_subscription_request(_sub("rss@transport/rss", nick="News"))
req = [a for ev, a in c.emitted if ev == "subscription_requested"]
check("incoming subscribe emits subscription_requested",
      req == [("rss@transport", "News", "", [])])

# Already subscribed (to/both) -> auto-approve, no event.
c.emitted.clear()
c.subscription = lambda bare: "both"
c._on_subscription_request(_sub("rss@transport/rss"))
check("duplicate subscribe auto-approves",
      ("rss@transport", "subscribed") in _sent
      and not [e for e, _ in c.emitted if e == "subscription_requested"])

# 2. approve/reject wire format ----------------------------------------------
_sent.clear()
c.approved_seen = []
c.subscription = lambda bare: "to"
JabberClient.approve_subscription(c, "rss@transport")
check("approve sends subscribed", ("rss@transport", "subscribed") in _sent)

_sent.clear()
c.subscription = lambda bare: "none"
JabberClient.approve_subscription(c, "new@example")
check("approve also sends subscribe when 'to' is missing",
      ("new@example", "subscribed") in _sent
      and ("new@example", "subscribe") in _sent)

_sent.clear()
JabberClient.reject_subscription(c, "spam@example")
check("reject sends unsubscribed",
      ("spam@example", "unsubscribed") in _sent)

# 3. incoming unsubscribe -> auto unsubscribed + info event ------------------
_sent.clear()
c.emitted.clear()
c._on_unsubscribe_request(_sub("bob@example", "unsubscribe"))
check("incoming unsubscribe auto-answers unsubscribed",
      ("bob@example", "unsubscribed") in _sent)
check("incoming unsubscribe emits subscription_cancelled",
      ("subscription_cancelled", ("bob@example",)) in c.emitted)

# 4. incoming unsubscribed -> cancellation event -----------------------------
c.emitted.clear()
c._on_unsubscribed(_sub("bob@example/r", "unsubscribed"))
check("incoming unsubscribed emits subscription_cancelled",
      ("subscription_cancelled", ("bob@example",)) in c.emitted)

# 5. Events tab row -----------------------------------------------------------
win = MainWindow(app)
win._client = None


class _StubClient:
    csi = True

    def __init__(self):
        self.approved = []
        self.rejected = []

    def approve_subscription(self, jid):
        self.approved.append(jid)

    def reject_subscription(self, jid):
        self.rejected.append(jid)

    def set_client_active(self, active):
        pass

    def get_contact(self, jid):
        return None

    def __getattr__(self, name):
        return lambda *a, **k: None


win._client = _StubClient()
win.show()
app.processEvents()
win._roster_tabs.setCurrentIndex(win._tab_index("events"))
app.processEvents()

win._on_subscription_request("rss@transport", nick="News", name="News Feed",
                             groups=["Feeds"])
app.processEvents()
check("subscription request becomes an event row",
      win._events_list.count() == 1
      and isinstance(win._events_list.itemWidget(win._events_list.item(0)),
                     _SubscriptionRequestRow))
row = win._events_list.itemWidget(win._events_list.item(0))
check("row shows the name", "News Feed" in row.findChildren(
    QtWidgets.QLabel)[0].text())
buttons = row.findChildren(QtWidgets.QPushButton)
check("row has Approve and Reject buttons",
      any(b.text() == "Approve" for b in buttons)
      and any(b.text() == "Reject" for b in buttons))

approve = next(b for b in buttons if b.text() == "Approve")
approve.click()
app.processEvents()
check("Approve calls the client",
      win._client.approved == ["rss@transport"])
check("the row is removed and the placeholder returns",
      win._events_list.count() == 1
      and win._events_list.itemWidget(win._events_list.item(0)) is None)

win._on_subscription_request("spam@example")
app.processEvents()
row = win._events_list.itemWidget(win._events_list.item(0))
reject = next(b for b in row.findChildren(QtWidgets.QPushButton)
              if b.text() == "Reject")
reject.click()
app.processEvents()
check("Reject calls the client",
      win._client.rejected == ["spam@example"])

win._on_subscription_cancelled("bob@example")
app.processEvents()
check("unsubscribed shows an info event",
      "bob@example" in win._events_list.item(0).text())
win.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All subscription tests passed.")
