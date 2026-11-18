"""Already loaded tabs must not reload history on focus.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_tab_focus_speed.py
"""
import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.ui.main_window import MainWindow

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Chat:
    def __init__(self, history=True, suspended=False):
        self._history = [{"body": "one"}] if history else []
        self._messages = []
        self._initial_load_done = bool(history)
        self.suspended = suspended
        self.restore_anchor = None
        self.anchor_requests = 0
        self.tail_refreshes = 0
        self.resumes = 0

    def set_restore_anchor(self, anchor):
        self.restore_anchor = anchor

    def request_anchor_update(self):
        self.anchor_requests += 1

    def schedule_tail_refresh(self, _delay=0):
        self.tail_refreshes += 1

    def resume(self):
        self.resumes += 1
        self.suspended = False


class _Window:
    def __init__(self, chat):
        self._chat = chat

    def current_jid(self):
        return "bob@example.com"

    def get_chat(self, _jid):
        return self._chat


def make_window(chat, anchor):
    win = MainWindow.__new__(MainWindow)
    win._chat_window = _Window(chat)
    win._restore_anchor_for = lambda _jid: dict(anchor)
    win._push_unread_to_chat = lambda _jid: None
    win._push_reaction_pending = lambda _jid: None
    win._apply_visible_unread = lambda _jid: None
    win._chat_area_available = lambda: False
    win._load_history_calls = []
    win._load_history = lambda jid, anchor=None, **kwargs: \
        win._load_history_calls.append((jid, anchor))
    win._schedule_mds_reconcile_calls = []
    win._schedule_mds_reconcile = lambda jid, **kwargs: \
        win._schedule_mds_reconcile_calls.append(jid)
    return win


anchor = {"ref": "m-1", "ts": "2026-11-01T10:00:00Z", "sid": "sid-1"}
loaded = _Chat(history=True)
win = make_window(loaded, anchor)
win._focus_chat("bob@example.com", loaded)
check("a loaded unread tab is not reloaded on focus",
      win._load_history_calls == [])
check("a loaded tab keeps its rendered window",
      loaded.anchor_requests == 1 and loaded.tail_refreshes == 1)
check("a loaded tab does not run a per-chat MDS reconcile",
      win._schedule_mds_reconcile_calls == [])

empty = _Chat(history=False)
win2 = make_window(empty, anchor)
win2._focus_chat("bob@example.com", empty)
check("a tab without a window loads its archive with the anchor",
      win2._load_history_calls == [("bob@example.com", anchor)])
check("the first open still schedules the MDS gap pass",
      win2._schedule_mds_reconcile_calls == ["bob@example.com"])

suspended = _Chat(history=True, suspended=True)
win3 = make_window(suspended, anchor)
win3._focus_chat("bob@example.com", suspended)
check("a suspended tab resumes instead of reloading",
      suspended.resumes == 1 and win3._load_history_calls == [])
check("a suspended unread tab receives its restore anchor",
      suspended.restore_anchor == anchor)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All tab-focus tests passed.")
