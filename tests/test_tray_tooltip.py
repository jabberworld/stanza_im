"""Tray tooltip: active account and unread summary.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_tray_tooltip.py
"""
import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.i18n import load as i18n_load, tr  # noqa: E402
from stanza_im.include.constants import APP_NAME  # noqa: E402
from stanza_im.ui.main_window import MainWindow  # noqa: E402

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Tray:
    def __init__(self):
        self.tooltips = []

    def set_tooltip(self, text):
        self.tooltips.append(str(text))


def _probe(client=True):
    return SimpleNamespace(
        _tray=_Tray(),
        _client=(SimpleNamespace(jid_str="me@example.com/walkbook")
                 if client else None),
        _unread_chats={},
        _event_unread=0,
        _roster=SimpleNamespace(
            _users=[SimpleNamespace(jid="alice@example.com")]),
        _conference_roster=set(),
        _muc_self_nicks={},
        _known_conferences=set(),
        _bookmarks={},
        _config=SimpleNamespace(
            connection=SimpleNamespace(conference_servers=[])),
    )


def _tip(probe):
    MainWindow._update_tray_tooltip(probe)
    return probe._tray.tooltips[-1]


# 1. logged in, nothing unread ------------------------------------------------
p = _probe()
tip = _tip(p)
lines = tip.splitlines()
check("the tooltip starts with the app name", lines[0] == APP_NAME)
check("the active account is shown",
      tr("tray_tooltip_account", jid="me@example.com/walkbook") in tip)
check("no unread lines when everything is read", len(lines) == 2)

# 2. visible unread + events --------------------------------------------------
p._unread_chats = {
    "alice@example.com": {"unread": 5, "mentions": 0},
    "old@example.com": {"unread": 3, "mentions": 0},
}
p._event_unread = 2
tip = _tip(p)
check("visible contact messages are counted",
      tr("digest_contacts", n=5, m=1) in tip)
check("an invisible key is not counted", "8" not in tip)
check("unread events are listed", tr("digest_events", n=2) in tip)

# 3. logged out ---------------------------------------------------------------
p2 = _probe(client=False)
p2._unread_chats = {"alice@example.com": {"unread": 5}}
tip = _tip(p2)
check("the logged-out tooltip has no account or unread", tip == APP_NAME)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All tray-tooltip tests passed.")
