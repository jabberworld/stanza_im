"""Offscreen tests for the XEP-0224 Attention plugin.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_attention.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_attention_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp
from PyQt6 import QtGui, QtWidgets

from stanza_im.core.client import NS_ATTENTION, JabberClient
from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.plugins import discover, get
from stanza_im.plugins import attention as A
from stanza_im.ui.attention_settings_dialog import AttentionSettingsDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _attention_msg(frm: str, mtype: str = "headline") -> slixmpp.Message:
    raw = (f"<message xmlns='jabber:client' type='{mtype}' from='{frm}' "
           f"to='me@x'><attention xmlns='{NS_ATTENTION}'/></message>")
    return slixmpp.Message(xml=ET.fromstring(raw))


# 1. Registry / manifest -----------------------------------------------------
plugins = discover()
check("the attention plugin is discovered",
      "attention" in [p.id for p in plugins])
att = get("attention")
check("the attention plugin announces settings", att.has_settings is True)
check("the attention plugin carries the bell icon",
      att.icon == "attention.svg")
check("the attention plugin lives in the Communication category",
      att.category == "plugin_category_communication")

# 2. The plugin registers the attention event handler ------------------------
check("the client subscribes to slixmpp's attention event",
      JabberClient._on_attention_event is not None)
check("NS_ATTENTION matches XEP-0224", NS_ATTENTION == "urn:xmpp:attention:0")

# 3. Defaults ----------------------------------------------------------------
cfg = Config()
settings = A._settings(cfg)
check("the cooldown default is 60 s", int(settings.cooldown) == 60)
check("allow_dnd defaults on", bool(settings.allow_dnd) is True)
check("play_sound defaults on", bool(settings.play_sound) is True)
check("show_events defaults on", bool(settings.show_events) is True)

# 4. Settings dialog ---------------------------------------------------------
from stanza_im.ui.sounds import SoundPlayer  # noqa: E402
dlg = AttentionSettingsDialog(cfg)
check("the cooldown selector is 1..99",
      dlg._cooldown.minimum() == 1 and dlg._cooldown.maximum() == 99)
dlg._cooldown.setValue(15)
dlg._allow_dnd.setChecked(False)
dlg._play_sound.setChecked(False)
dlg._show_events.setChecked(False)
dlg._accept()
stored = A._settings(cfg)
check("the settings dialog persists the cooldown",
      int(stored.cooldown) == 15)
check("the settings dialog persists allow_dnd",
      bool(stored.allow_dnd) is False)
check("the settings dialog persists play_sound",
      bool(stored.play_sound) is False)
check("the settings dialog persists show_events",
      bool(stored.show_events) is False)
check("settings live in config.plugin_settings.attention",
      "attention" in dict(cfg.plugin_settings))

# 5. Receive logic -----------------------------------------------------------
from stanza_im.ui.main_window import MainWindow  # noqa: E402

cfg2 = Config()
cfg2.plugins["attention"] = True
cfg2.save()
w = MainWindow(app)


class _StubClient:
    """Minimal client: the handler only needs a truthy object."""

    def __getattr__(self, _name):
        return lambda *a, **k: None


w._client = _StubClient()  # a client must exist for the handler to run
# The settings-dialog test above saved its values to the shared config; reset
# them so the receive-path assertions use the documented defaults.
from stanza_im.plugins import settings_section  # noqa: E402
_saved = settings_section(w._config, A.PLUGIN_ID)
_saved.cooldown = 60
_saved.allow_dnd = True
_saved.play_sound = False
_saved.show_events = True
check("activating the plugin installs the attention feature",
      getattr(w, "_attention_feature", "") == NS_ATTENTION)
check("activating the plugin installs a contact-menu hook",
      len(w._contact_menu_hooks) == 1)

pushed = []
w._push_system_event = lambda *a: pushed.append(a)
w._config.notifications.osd_enabled = False
A._on_attention(w, "rcpt@example.com/res")
check("an incoming attention pushes an Events entry", len(pushed) == 1)
state = getattr(w, A._STATE)
check("the sender is recorded for throttling",
      "rcpt@example.com" in state["last"])
check("the sender is unlocked for attention support",
      "rcpt@example.com" in getattr(w, "_attention_seen", set()))
pushed.clear()
A._on_attention(w, "rcpt@example.com/res")
check("a repeat within the cooldown is throttled", pushed == [])

s = A._settings(w._config)
s.allow_dnd = False
w._config.last_status = "dnd"
state["last"].clear()
pushed.clear()
A._on_attention(w, "carol@example.com/res")
check("dnd suppresses the notification when not allowed", pushed == [])
s.allow_dnd = True
state["last"].clear()
pushed.clear()
A._on_attention(w, "dave@example.com/res")
check("dnd still notifies when allowed", len(pushed) == 1)

# 6. Gating (bell + menu) ----------------------------------------------------
cw = w._chat_window.open_chat("bob@example.com", "Bob")
check("the 1:1 tab has a bell button",
      getattr(cw, "_attention_btn", None) is not None)
check("the bell tooltip is the plugin's translated label",
      cw._attention_btn.toolTip() == "Get attention")
check("the bell is hidden without peer caps",
      cw._attention_btn.isHidden())
muc = w._chat_window.open_groupchat("room@conf.example", "me", "Room")
check("a MUC tab hides the bell",
      muc._attention_btn.isHidden())


class _CapsClient:
    def __getattr__(self, _name):
        return lambda *a, **k: None

    def supports_feature(self, bare, feature):
        return True

    def supports_calls(self, *a, **k):
        return False

    def client_icon(self, *a, **k):
        return ""

    def send_attention(self, jid):
        self.sent = jid
        return True


caps = _CapsClient()
w._client = caps
w.apply_attention_support("bob@example.com")
check("the bell becomes visible and enabled on peer support",
      not cw._attention_btn.isHidden() and cw._attention_btn.isEnabled())
cw._attention_btn.click()
check("clicking the bell sends an attention", caps.sent == "bob@example.com")

# Deactivating the plugin hides the bell again.
A.deactivate(w)
check("deactivating the plugin hides the bell",
      cw._attention_btn.isHidden())
A.activate(w)
w.apply_attention_support("bob@example.com")
check("reactivating the plugin shows the bell again",
      not cw._attention_btn.isHidden())

# 6b. The plugin's ``attention`` event drives the receive path (XEP-0224) ----
# slixmpp's core ``message`` event only fires for a stanza with a ``<body>``,
# so a bodyless attention (Psi+) is delivered through slixmpp's ``attention``
# event instead (raised by its ``xep_0224`` plugin).
from stanza_im.core.client import JabberClient as _JC  # noqa: E402


class _EventClient(_JC):
    def __init__(self):
        self.events = []

    def emit(self, name, *a, **k):
        self.events.append((name, a))


ec = _EventClient()
ec._on_attention_event(
    _attention_msg("rain@jabberworld.info/walkbook"))
check("the attention event emits attention_received with the bare JID",
      ("attention_received", ("rain@jabberworld.info",)) in ec.events)

# 6c. Sending goes through slixmpp's xep_0224 plugin -------------------------
class _Xep:
    def __init__(self):
        self.sent = []

    def request_attention(self, to):
        self.sent.append(to)


class _SendClient(_JC):
    def __init__(self):
        self.xmpp = type("X", (), {"plugin": {"xep_0224": _Xep()}})()


sc = _SendClient()
check("send_attention returns True for a valid JID",
      sc.send_attention("rain@jabberworld.info") is True)
check("send_attention delegates to xep_0224.request_attention",
      sc.xmpp.plugin["xep_0224"].sent == ["rain@jabberworld.info"])
check("send_attention refuses an empty JID",
      sc.send_attention("") is False)


class _FakeMenu:
    def __init__(self):
        self.actions = []

    def addAction(self, *a):
        action = QtGui.QAction("x")
        self.actions.append(action)
        return action


menu = _FakeMenu()
for hook in w._contact_menu_hooks:
    hook(menu, "bob@example.com", False)
check("the contact menu gains an enabled attention action",
      len(menu.actions) == 1 and menu.actions[0].isEnabled())
muc_menu = _FakeMenu()
for hook in w._contact_menu_hooks:
    hook(muc_menu, "room@conf.example", True)
check("the attention action is skipped for conferences",
      muc_menu.actions == [])

# 7. i18n --------------------------------------------------------------------
from stanza_im import i18n  # noqa: E402
from stanza_im.plugins.attention.strings import en as att_en  # noqa: E402
from stanza_im.plugins.attention.strings import ru as att_ru  # noqa: E402

i18n_load("en")
merged_en = dict(i18n._current)
i18n_load("ru")
merged_ru = dict(i18n._current)
check("the merged en/ru dictionaries have the same keys",
      set(merged_en) == set(merged_ru))
check("the plugin's own strings are merged in",
      i18n.tr("attention_menu") == "Привлечь внимание")
check("the attention strings modules agree",
      set(att_en.STRINGS) == set(att_ru.STRINGS))

# 8. Deactivation ------------------------------------------------------------
A.deactivate(w)
check("deactivation removes the menu hook",
      w._contact_menu_hooks == [])
check("deactivation clears the attention feature",
      getattr(w, "_attention_feature", "") == "")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All attention tests passed.")
