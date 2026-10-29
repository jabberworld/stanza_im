"""The tray blink must follow the unread total, including zeroing paths.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_tray_blink.py
"""
import os
import sys
import tempfile
from types import MethodType, SimpleNamespace

_SCRATCH = tempfile.mkdtemp(prefix="stanza_tray_blink_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core import unread_state  # noqa: E402
from stanza_im.ui.main_window import MainWindow  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Signal:
    def __init__(self):
        self.count = 0

    def emit(self):
        self.count += 1


class _Tray:
    def __init__(self):
        self._blink_active = False
        self.starts = 0
        self.stops = 0

    def start_blinking(self):
        self.starts += 1
        self._blink_active = True

    def stop_blinking(self):
        self.stops += 1
        self._blink_active = False


class _Chat:
    def __init__(self, remaining=0, mentions=0):
        self.remaining = remaining
        self.mentions = mentions

    def mark_visible_unread(self):
        return self.remaining

    def mark_visible_mentions(self):
        return self.mentions

    def seen_anchor(self):
        return {}


def _probe():
    probe = SimpleNamespace(
        _unread_chats={},
        _unread_jids=set(),
        _unread_total=0,
        _tray_blink_allowed=True,
        _tray=_Tray(),
        _config=SimpleNamespace(
            notifications=SimpleNamespace(tray_blink=True,
                                            tray_conference="mention")),
        _conference_roster=set(),
        _muc_self_nicks={},
        _known_conferences=set(),
        unread_changed=_Signal(),
    )
    probe._sync_tray_blink = MethodType(MainWindow._sync_tray_blink, probe)
    probe._recount_unread = MethodType(MainWindow._recount_unread, probe)
    probe._notification_unread_count = MethodType(
        MainWindow._notification_unread_count, probe)
    probe._notification_unread_total = MethodType(
        MainWindow._notification_unread_total, probe)
    probe._conference_chat_keys = MethodType(
        MainWindow._conference_chat_keys, probe)
    return probe


# 1. a derived total starts the blink -----------------------------------------
p = _probe()
p._unread_chats = {
    "a@example.com": {"unread": 2, "mentions": 0},
    "b@example.com": {"unread": 1, "mentions": 0},
}
MainWindow._recount_unread(p)
check("recount derives the total", p._unread_total == 3)
check("recount starts the tray blink", p._tray._blink_active)
check("the start is idempotent", p._tray.starts == 1)
check("recount emits the unread signal", p.unread_changed.count == 1)

# 2. clearing the last unread stops it ----------------------------------------
p._unread_chats = {}
MainWindow._recount_unread(p)
check("clearing the records zeroes the total", p._unread_total == 0)
check("clearing the records stops the blink", not p._tray._blink_active)

# 3. the preference is applied live -------------------------------------------
p._unread_chats = {"a@example.com": {"unread": 1, "mentions": 0}}
MainWindow._recount_unread(p)
check("unread starts the blink again", p._tray._blink_active)
p._config.notifications.tray_blink = False
MainWindow._sync_tray_blink(p)
check("disabling the preference stops the blink", not p._tray._blink_active)
p._config.notifications.tray_blink = True
MainWindow._sync_tray_blink(p)
check("enabling the preference restores it", p._tray._blink_active)

# 4. storing a read state recomputes the tray ---------------------------------
read_record = unread_state.blank()
read_record["read_ts"] = "2026-10-27T19:00:00Z"
MainWindow._store_read_state(p, "a@example.com", read_record)
check("the last unread record is dropped", p._unread_total == 0)
check("storing a read state stops the blink", not p._tray._blink_active)

# 5. an unchanged visible count still heals a stale total ---------------------
p = _probe()
p._unread_chats = {"a@example.com": {"unread": 0, "mentions": 0}}
p._unread_total = 4
p._chat_area_visible = lambda: True
p._chat_window = SimpleNamespace(
    get_chat=lambda jid: _Chat(0, 0), current_jid=lambda: "a@example.com")
MainWindow._apply_visible_unread(p, "a@example.com")
check("a stale total is healed by the visible reconciliation",
      p._unread_total == 0)
check("the healed total stops the blink", not p._tray._blink_active)

# 6. loading unread before the tray exists is safe ----------------------------
p = _probe()
del p._tray
p._unread_chats = {"a@example.com": {"unread": 1, "mentions": 0}}
MainWindow._recount_unread(p)
check("recount before the tray exists is safe", p._unread_total == 1)

# 7. conference messages follow the tray_conference policy -------------------
p = _probe()
p._conference_roster = {"room@conf.example"}
p._unread_chats = {"room@conf.example": {"unread": 2, "mentions": 0}}
MainWindow._recount_unread(p)
check("a conference without a mention does not blink",
      not p._tray._blink_active)
p._unread_chats = {"room@conf.example": {"unread": 2, "mentions": 1}}
MainWindow._recount_unread(p)
check("a conference mention starts the blink", p._tray._blink_active)
p._config.notifications.tray_conference = "never"
MainWindow._recount_unread(p)
check("tray_conference=never hides a mention", not p._tray._blink_active)
p._config.notifications.tray_conference = "all"
MainWindow._recount_unread(p)
check("tray_conference=all counts ordinary conference messages",
      p._tray._blink_active)
p._unread_chats = {"room@conf.example": {"unread": 2, "mentions": 0}}
MainWindow._recount_unread(p)
check("tray_conference=all blinks without a mention", p._tray._blink_active)

# 8. middle-click cycles exactly the notifications the blink represents -----
p = _probe()
p._conference_roster = {"room@conf.example"}
p._roster = SimpleNamespace(_users=[
    SimpleNamespace(jid="bob@example.com", unread_count=1,
                    unread_mentions=0),
    SimpleNamespace(jid="room@conf.example", unread_count=2,
                    unread_mentions=0),
])
p._unread_chats = {
    "bob@example.com": {"unread": 1, "mentions": 0},
    "room@conf.example": {"unread": 2, "mentions": 0},
}
opened = []
p._osd_click = lambda jid, nick="": opened.append(jid)
p._on_tray_cycle_unread = MethodType(MainWindow._on_tray_cycle_unread, p)
p._on_tray_cycle_unread()
check("middle-click opens the 1:1 chat, not an ordinary conference",
      opened == ["bob@example.com"])
opened.clear()
p._unread_chats["bob@example.com"]["unread"] = 0
p._on_tray_cycle_unread()
check("an ordinary conference message is not cycled", opened == [])
p._unread_chats["room@conf.example"]["mentions"] = 1
p._on_tray_cycle_unread()
check("a conference mention is cycled", opened == ["room@conf.example"])
p._config.notifications.tray_conference = "all"
p._unread_chats["room@conf.example"]["mentions"] = 0
p._on_tray_cycle_unread()
check("tray_conference=all cycles ordinary conference messages",
      opened == ["room@conf.example", "room@conf.example"])

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All tests passed")
