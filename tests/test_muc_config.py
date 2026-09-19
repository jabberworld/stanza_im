"""Offscreen tests for the MUC room-management dialog (P-manager feature).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_config.py
"""
import asyncio
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_muccfg_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.muc_config_dialog import MucConfigDialog, can_change_affiliation

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _FakeForm(dict):
    pass


class _FakeClient:
    def __init__(self):
        self.affiliation_calls = []
        self.config_calls = []
        self.form = _FakeForm(title="", instructions=[], fields=[])
        self.groupchats = {}

    async def muc_get_affiliations(self, room):
        return {
            "owner": [{"jid": "owner@x", "nick": "", "reason": "boss"}],
            "admin": [{"jid": "admin@x", "nick": "", "reason": ""}],
            "member": [{"jid": "m1@x", "nick": "", "reason": "note1"},
                       {"jid": "m2@x", "nick": "", "reason": ""}],
            "outcast": [{"jid": "bad@x", "nick": "", "reason": "spam"}],
        }

    async def muc_get_config(self, room):
        return self.form

    async def muc_set_affiliation(self, room, jid, affiliation, reason=""):
        self.affiliation_calls.append((room, jid, affiliation, reason))

    async def muc_set_config(self, room, values):
        self.config_calls.append((room, values))

    async def room_supports_hats(self, room):
        return True

    async def hats_list(self, room):
        return [{"uri": "urn:xmpp:hats:abc", "title": "Host", "hue": 10.0}]

    async def hats_list_assigned(self, room):
        return [{"uri": "urn:xmpp:hats:abc", "title": "Host",
                 "hue": 10.0, "jid": "m1@x"}]


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# 1. the gear button (MUC only, gated, emits) --------------------------------
muc = ChatWidget("room@conf.example/me", "Room", ChatThemeFactory(),
                 is_muc=True)
check("gear hidden for 1:1", ChatWidget(
    "u@x", "U", ChatThemeFactory())._config_btn.isHidden())
check("gear visible for MUC", not muc._config_btn.isHidden())
check("gear disabled without rights", not muc._config_btn.isEnabled())
captured = []
muc.muc_config_requested.connect(lambda r: captured.append(r))
muc.set_muc_admin(True)
check("gear enabled with rights", muc._config_btn.isEnabled())
muc._config_btn.click()
check("gear emits the room", captured == ["room@conf.example/me"])

# 2. the dialog: participants + settings gating ------------------------------
async def scenario(can_configure):
    client = _FakeClient()
    dlg = MucConfigDialog(client, "room@conf.example",
                          can_configure=can_configure,
                          actor_affiliation="owner" if can_configure
                          else "member")
    for _ in range(8):
        await asyncio.sleep(0)
    return client, dlg


loop = asyncio.new_event_loop()
try:
    client, dlg = loop.run_until_complete(scenario(True))
    check("three tabs", dlg._tabs.count() == 3)
    check("owner sees the settings tab", dlg._tabs.isTabEnabled(2))
    check("hats tab present", dlg._tabs.tabText(1) == "Hats")
    check("hats tree lists one category with one assignee",
          dlg._hats_tab._tree.topLevelItemCount() == 1
          and dlg._hats_tab._tree.topLevelItem(0).childCount() == 1)
    dlg._hats_tab._tree.setCurrentItem(
        dlg._hats_tab._tree.topLevelItem(0))
    check("edit/delete enabled on a hat",
          dlg._hats_tab._edit_btn.isEnabled()
          and dlg._hats_tab._delete_btn.isEnabled())
    dlg._hats_tab._tree.setCurrentItem(
        dlg._hats_tab._tree.topLevelItem(0).child(0))
    check("unassign enabled on a user, edit disabled",
          dlg._hats_tab._unassign_btn.isEnabled()
          and not dlg._hats_tab._edit_btn.isEnabled())
    check("participants grouped in four categories",
          dlg._tree.topLevelItemCount() == 4)
    counts = [dlg._tree.topLevelItem(i).childCount() for i in range(4)]
    check("category counts", counts == [1, 1, 2, 1])
    check("form widget built for owner", dlg._form_widget is not None)

    child = dlg._tree.topLevelItem(2).child(0)
    dlg._tree.setCurrentItem(child)
    check("edit/delete enabled on selection",
          dlg._edit_btn.isEnabled() and dlg._delete_btn.isEnabled())
    dlg._tree.setCurrentItem(None)
    check("edit/delete disabled without selection",
          not dlg._edit_btn.isEnabled() and not dlg._delete_btn.isEnabled())

    # Ok with no changes must send nothing at all
    dlg._changes = {}
    dlg._pending_values = None
    dlg._on_ok()
    check("no-change Ok sends nothing",
          client.affiliation_calls == [] and client.config_calls == [])

    # Ok with only affiliation changes must not submit the config form
    dlg._changes = {
        "m1@x": {"affiliation": "admin", "note": "promoted"},
        "bad@x": {"affiliation": "none", "note": ""},
    }
    dlg._pending_values = None
    loop.run_until_complete(dlg._apply())
    check("affiliation changes submitted",
          client.affiliation_calls == [
              ("room@conf.example", "m1@x", "admin", "promoted"),
              ("room@conf.example", "bad@x", "none", "")])
    check("no config sent for an affiliation-only edit",
          client.config_calls == [])

    # Ok with only settings changes must not send affiliations
    client.affiliation_calls.clear()
    dlg._changes = {}
    dlg._pending_values = {"muc#roomconfig_roomname": "New"}
    loop.run_until_complete(dlg._apply())
    check("room config submitted",
          client.config_calls == [
              ("room@conf.example", {"muc#roomconfig_roomname": "New"})])
    check("no affiliations sent for a settings-only edit",
          client.affiliation_calls == [])
    dlg.deleteLater()

    client2, dlg2 = loop.run_until_complete(scenario(False))
    check("admin cannot see the settings tab", not dlg2._tabs.isTabEnabled(2))
    check("no-rights note shown", bool(dlg2._settings_status.text()))
    check("no config fetch for admin", dlg2._form_widget is None)
    dlg2.deleteLater()
finally:
    loop.close()

# 2b. affiliation permission rules (XEP-0045) --------------------------------
check("owner can change anything",
      all(can_change_affiliation("owner", o, n)
          for o in ("owner", "admin", "member", "outcast", "none")
          for n in ("owner", "admin", "member", "outcast", "none")))
check("admin cannot touch owner",
      not can_change_affiliation("admin", "owner", "member"))
check("admin cannot touch admin",
      not can_change_affiliation("admin", "admin", "member"))
check("admin cannot grant admin",
      not can_change_affiliation("admin", "member", "admin"))
check("admin cannot grant owner",
      not can_change_affiliation("admin", "member", "owner"))
check("admin can manage members/outcasts",
      can_change_affiliation("admin", "member", "outcast")
      and can_change_affiliation("admin", "outcast", "member")
      and can_change_affiliation("admin", "none", "member"))
check("non-managers cannot change",
      not can_change_affiliation("member", "member", "outcast"))

# 2c. the stanza language follows the UI language ----------------------------
from stanza_im.i18n import load as _load, current_language as _current_language
_load("ru")
check("current_language reflects the loaded dict", _current_language() == "ru")
_load("en")
check("current_language switches", _current_language() == "en")

# 3. static wiring ------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_client_src = open(os.path.join(_root, "stanza_im", "core", "client.py"),
                   encoding="utf-8").read()
check("client exposes the MUC management wrappers",
      all(k in _client_src for k in ("muc_get_config", "muc_set_config",
                                     "muc_get_affiliations",
                                     "muc_set_affiliation")))
_cw_src = open(os.path.join(_root, "stanza_im", "ui", "chat_window.py"),
               encoding="utf-8").read()
check("ChatWindow forwards the signal and gates the button",
      "muc_config_requested" in _cw_src and "def set_muc_admin" in _cw_src)
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
check("MainWindow applies rights and opens the dialog",
      "def _apply_muc_admin" in _mw_src
      and "def _on_muc_config_requested" in _mw_src)
check("client advertises the UI language",
      "lang=_current_language()" in _client_src
      and "self.peer_default_lang = self.default_lang" in _client_src)
check("config submit builds a fresh form",
      'await muc.set_room_config(room, form)' in _client_src
      and 'form = Form()' in _client_src)
check("dialog sends only what changed",
      "current != self._initial_values" in open(
          os.path.join(_root, "stanza_im", "ui", "muc_config_dialog.py"),
          encoding="utf-8").read())

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All MUC-config tests passed.")
