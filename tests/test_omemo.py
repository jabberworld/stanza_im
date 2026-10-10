"""Offscreen tests for the OMEMO core helpers (availability/storage/SCE).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_omemo.py
"""
import asyncio
import os
import stat
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_omemo_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.xmpp.omemo import availability
from stanza_im.xmpp.omemo import sce
from stanza_im.xmpp.omemo.storage import OmemoStorage, storage_path

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. availability ------------------------------------------------------------
check("OMEMO stack detected as available", availability.AVAILABLE)
check("both backends detected",
      availability.BACKEND_LEGACY in availability.BACKENDS
      and availability.BACKEND_OMEMO2 in availability.BACKENDS)
check("no missing packages", availability.MISSING == [])
check("summary mentions both backends",
      "legacy" in availability.summary()
      and "omemo2" in availability.summary())


# 2. storage -----------------------------------------------------------------
store = OmemoStorage(storage_path(os.path.join(_SCRATCH, "profile")))


async def _storage_roundtrip():
    from omemo.storage import Just, Nothing
    empty = await store._load("missing")
    ok_empty = isinstance(empty, Nothing)
    await store._store("k", {"a": 1, "b": [1, 2, 3]})
    loaded = await store._load("k")
    ok_just = isinstance(loaded, Just) and loaded.from_just() == {
        "a": 1, "b": [1, 2, 3]}
    await store._delete("k")
    gone = await store._load("k")
    return ok_empty, ok_just, isinstance(gone, Nothing)


ok_empty, ok_just, ok_gone = asyncio.run(_storage_roundtrip())
check("storage returns Nothing for a missing key", ok_empty)
check("storage round-trips a JSON value", ok_just)
check("storage deletes a key", ok_gone)
check("OMEMO store file is 0600",
      stat.S_IMODE(os.stat(store._path).st_mode) == 0o600)

store.set_app("chat_modes", {"bob@example.com": "omemo"})
check("app-level key round-trips",
      store.get_app("chat_modes") == {"bob@example.com": "omemo"})
reopened = OmemoStorage(store._path)
check("app-level key persists across reopen",
      reopened.get_app("chat_modes") == {"bob@example.com": "omemo"})


# 3. SCE envelope ------------------------------------------------------------
body = ET.Element("{jabber:client}body")
body.text = "Hello World!"
reply = ET.Element("{urn:xmpp:reply:0}reply")
reply.set("id", "m1")
hints = ET.Element("{urn:xmpp:hints}store")
eme = ET.Element("{urn:xmpp:eme:0}encryption")
message = ET.Element("{jabber:client}message")
for elt in (body, reply, hints, eme):
    message.append(elt)

content = sce.collect_content(message)
check("collect_content keeps body and reply, drops hints/eme",
      body in content and reply in content
      and hints not in content and eme not in content)

envelope = sce.build_envelope(content, "romeo@montague.lit")
payload = sce.serialize(envelope)
parsed = sce.parse(payload)
check("envelope round-trips through serialize/parse",
      parsed.tag == "{urn:xmpp:sce:1}envelope")
check("envelope carries a from affix",
      sce.affix(parsed, "from") is not None
      and sce.affix(parsed, "from").get("jid") == "romeo@montague.lit")
check("envelope carries an rpad affix",
      sce.affix(parsed, "rpad") is not None
      and len(sce.affix(parsed, "rpad").text or "") >= 100)
check("no to affix for a 1:1 envelope", sce.affix(parsed, "to") is None)

extracted = sce.extract_content(parsed)
tags = [e.tag for e in extracted]
check("extract_content returns body and reply",
      "{jabber:client}body" in tags and "{urn:xmpp:reply:0}reply" in tags)
check("extracted body text survives",
      next(e for e in extracted if e.tag == "{jabber:client}body").text
      == "Hello World!")

muc_env = sce.build_envelope(content, "romeo@montague.lit",
                             "room@conference.montague.lit")
check("MUC envelope carries a to affix",
      sce.affix(muc_env, "to").get("jid") == "room@conference.montague.lit")

try:
    sce.parse(b"not xml")
    check("malformed payload is rejected", False)
except ValueError:
    check("malformed payload is rejected", True)

try:
    sce.parse(b"<nope/>")
    check("non-envelope root is rejected", False)
except ValueError:
    check("non-envelope root is rejected", True)


# 4. config section ----------------------------------------------------------
from stanza_im.core.storage import Config

cfg = Config()
check("omemo config defaults",
      cfg.omemo.enabled is True and cfg.omemo.blind_trust is True
      and cfg.omemo.alias_sync is False)
cfg.omemo.blind_trust = False
cfg.save()
check("omemo config round-trips", Config().omemo.blind_trust is False)


# 5. history encryption flag + render ----------------------------------------
from stanza_im.core import history
from stanza_im.ui.chat_themes import ChatThemeFactory

history.store_message("omemo@example.com", "incoming", "secret",
                      origin_id="e1", encrypted=True, encryption="omemo")
entry = history.entry_by_ref("omemo@example.com", "e1")
check("history stores the encrypted flag", entry is not None
      and entry["encrypted"] is True and entry["encryption"] == "omemo")

html = ChatThemeFactory().render_message(
    sender="Bob", body="secret", timestamp="10:00", direction="incoming",
    encrypted=True)
check("encrypted messages render a lock", "stanza-lock" in html)
html_plain = ChatThemeFactory().render_message(
    sender="Bob", body="hi", timestamp="10:00", direction="incoming")
check("plain messages have no lock", "stanza-lock" not in html_plain)

# 6. QR encoder --------------------------------------------------------------
from stanza_im.xmpp.omemo import qr

matrix = qr.encode("HELLO")
check("QR size for a short string is version 1 (21x21)",
      len(matrix) == 21 and all(len(row) == 21 for row in matrix))
check("QR finder pattern is drawn",
      matrix[0][0] and matrix[0][6] and matrix[6][0] and matrix[6][6]
      and not matrix[1][1] and matrix[3][3] and not matrix[1][5])
check("QR timing pattern alternates",
      matrix[6][8] != matrix[6][9])

# The full codeword polynomial must vanish at the RS generator roots.
_cw = qr._codewords(b"HELLO", 1)
_deg = qr._ECC_CODEWORDS[1]
_ok = True
for i in range(_deg):
    x = 1
    for _ in range(i):
        x = qr._gf_mul(x, 0x02)
    acc = 0
    for coeff in _cw:
        acc = qr._gf_mul(acc, x) ^ coeff
    if acc != 0:
        _ok = False
check("QR Reed-Solomon codewords are valid", _ok)

_fp = "aa bb cc dd ee ff 00 11 22 33 44 55 66 77 88 99"
_big = qr.encode(_fp)
check("QR of a fingerprint fits a small version",
      1 <= (len(_big) - 17) // 4 <= 5)

# 7. UI: chat OMEMO buttons + QR pixmap --------------------------------------
from PyQt6 import QtWidgets
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.qr_dialog import render_qr_pixmap

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
_cw = ChatWidget("bob@example.com", "Bob", ChatThemeFactory())
check("OMEMO lock hidden by default", _cw._omemo_btn.isHidden())
_cw.set_omemo_support(True, peer_supported=False)
check("OMEMO lock shown while OMEMO is available",
      not _cw._omemo_btn.isHidden())
check("OMEMO mode entry disabled for an unsupported peer",
      not _cw._omemo_on_action.isEnabled())
_cw.set_omemo_support(True, peer_supported=True)
check("OMEMO mode entry enabled for a supported peer",
      _cw._omemo_on_action.isEnabled())
_cw.set_omemo_mode("omemo")
check("OMEMO mode reflected", _cw.omemo_mode() == "omemo")
check("OMEMO shield shown in omemo mode", not _cw._omemo_shield_btn.isHidden())
_cw.set_omemo_mode("omemo")
check("lock menu checks the OMEMO entry",
      _cw._omemo_on_action.isChecked()
      and not _cw._omemo_off_action.isChecked())
_cw.set_omemo_mode("off")
check("OMEMO shield hidden when off", _cw._omemo_shield_btn.isHidden())
check("lock menu checks the off entry",
      _cw._omemo_off_action.isChecked()
      and not _cw._omemo_on_action.isChecked())
_cw.detach()

from stanza_im.include.constants import find_icon
check("the QR icon resolves", bool(find_icon("qr.svg")))
check("the shield icon resolves", bool(find_icon("shield.svg")))
for _name in ("shield-trusted.svg", "shield-blindly.svg",
              "shield-unknown.svg", "shield-distrusted.svg"):
    check("the %s icon resolves" % _name, bool(find_icon(_name)))

# Trust state -> coloured shield (state, not action).
from stanza_im.ui.omemo_devices_dialog import _trust_icon as _dlg_icon
from stanza_im.ui.omemo_popup import _trust_icon as _pop_icon
check("trusted uses the green shield",
      _dlg_icon("TRUSTED") == "shield-trusted.svg")
check("blindly-trusted uses the green outline shield",
      _dlg_icon("BLINDLY_TRUSTED") == "shield-blindly.svg")
check("undecided uses the yellow shield",
      _dlg_icon("UNDECIDED") == "shield-unknown.svg")
check("distrusted uses the red shield",
      _dlg_icon("DISTRUSTED") == "shield-distrusted.svg")
check("the popup mirrors the trust icons",
      _pop_icon("DISTRUSTED") == "shield-distrusted.svg")

# The popup anchors its bottom-left corner at the click point.
from PyQt6 import QtCore
from stanza_im.ui.omemo_popup import OmemoPopup


class _FakeOmemo:
    async def refresh_device_lists(self, jids, force=False):
        return None

    async def devices(self, jid):
        return []

    def device_name(self, jid, did, label=""):
        return f"Device {did}"

    def device_resource(self, jid, did):
        return ""

    def trust_level_name(self, device):
        return "UNDECIDED"

    def fingerprint(self, key):
        return ""

    def sorted_devices(self, jid, devices):
        return list(devices)


class _FakeClient:
    omemo = _FakeOmemo()


_orig_reload = OmemoPopup._reload
OmemoPopup._reload = lambda self: None
try:
    _pop = OmemoPopup(_FakeClient(), "bob@example.com", anchor=(500, 400))
    _pop.show()
    check("popup anchors its bottom-left at the click point",
          _pop.y() < 400 and _pop.y() + _pop.height() <= 401)
    check("popup left edge does not pass the click x", _pop.x() <= 500)
    _pop.close()
finally:
    OmemoPopup._reload = _orig_reload

# A long device list must scroll instead of spilling off the screen.
class _DevX:
    def __init__(self, did):
        self.device_id = did
        self.identity_key = b""
        self.label = ""


_orig_reload2 = OmemoPopup._reload
OmemoPopup._reload = lambda self: None
try:
    _pop2 = OmemoPopup(_FakeClient(), "bob@example.com", anchor=(500, 400))
    _pop2._devices = [_DevX(i) for i in range(1, 60)]
    _pop2._rebuild()
    _pop2.show()
    QtWidgets.QApplication.processEvents()
    _screen = (QtWidgets.QApplication.screenAt(QtCore.QPoint(500, 400))
               or QtWidgets.QApplication.primaryScreen())
    _area = _screen.availableGeometry()
    check("popup height is capped to the screen",
          _pop2.height() <= _area.height())
    check("a long device list scrolls",
          _pop2._scroll.widget().sizeHint().height()
          > _pop2._scroll.height()
          or _pop2._scroll.verticalScrollBar().maximum() > 0)
    _pop2.close()
finally:
    OmemoPopup._reload = _orig_reload2

# A moderate list fits without a scrollbar and stays clear of the button.
_orig_reload3 = OmemoPopup._reload
OmemoPopup._reload = lambda self: None
try:
    _pop3 = OmemoPopup(_FakeClient(), "bob@example.com", anchor=(500, 400))
    _pop3._devices = [_DevX(i) for i in range(1, 5)]
    _pop3._rebuild()
    _pop3.show()
    QtWidgets.QApplication.processEvents()
    check("a moderate device list does not scroll",
          _pop3._scroll.verticalScrollBar().maximum() == 0)
    check("the popup sits above the click, not over the button",
          _pop3.y() + _pop3.height() <= 400)
    _pop3.close()
finally:
    OmemoPopup._reload = _orig_reload3

# aesgcm:// URLs must be linkified so the media preview can embed them.
from stanza_im.include.utils import _URL_RE
check("aesgcm URLs are linkified",
      bool(_URL_RE.search("aesgcm://example.com/f.enc#abc")))

# The new-device warning carries the id, JID and fingerprint plus a control
# link to the device manager.
from stanza_im.i18n.en import STRINGS as _EN
check("new-device warning names the id and fingerprint",
      "{id}" in _EN["omemo_new_device_warning"]
      and "{fp}" in _EN["omemo_new_device_warning"])
check("own-device warning names the JID",
      "{jid}" in _EN["omemo_new_own_device_warning"])
check("the last-seen label exists", "omemo_last_seen" in _EN)
check("the alias-sync tip exists", "prefs_omemo_alias_sync_tip" in _EN)
import inspect
check("the stanza:omemo link is routed",
      "stanza:omemo:" in inspect.getsource(ChatWidget._open_link))
_view_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stanza_im", "ui", "chat_view.py")
_view_src = open(_view_path, encoding="utf-8").read()
check("the JS click handler relays stanza:omemo",
      'a[href^="stanza:omemo"]' in _view_src
      and "__stanzaOmemoRef" in _view_src)

_pm = render_qr_pixmap("abc")
check("QR pixmap renders", _pm is not None and not _pm.isNull())
check("QR pixmap is square and sized", _pm.width() == _pm.height()
      and _pm.width() > 21)

# 8. server-side aliases payload ---------------------------------------------
from stanza_im.core import omemo_aliases

_payload = omemo_aliases.build_payload([
    {"jid": "alice@example.com", "id": "1", "alias": "Laptop",
     "last_seen": "1700000000"},
    {"jid": "bob@example.com", "id": "2", "alias": "", "last_seen": ""},
])
_entries = omemo_aliases.parse_payload(_payload)
check("alias payload round-trips",
      _entries[0] == {"jid": "alice@example.com", "id": "1",
                      "alias": "Laptop", "last_seen": "1700000000"}
      and _entries[1]["alias"] == "" and _entries[1]["jid"] == "bob@example.com")
check("alias node namespace is private",
      omemo_aliases.NODE == "urn:xmpp:omemo:aliases:0")

# 9. XEP-0454 OMEMO file encryption ------------------------------------------
import io
from slixmpp.plugins.xep_0454 import XEP_0454
from stanza_im.include import media as media_mod

_data = b"hello omemo file" * 50
_payload, _frag = XEP_0454.encrypt(io.BytesIO(_data), None)
check("XEP-0454 file round-trips",
      XEP_0454.decrypt(io.BytesIO(_payload), _frag) == _data)
check("XEP-0454 fragment is 88 hex chars",
      len(_frag) == 88 and all(c in "0123456789abcdef" for c in _frag))
_url = XEP_0454.format_url("https://example.com/abc.bin", _frag)
check("aesgcm URL format",
      _url.startswith("aesgcm://example.com/abc.bin#") and _frag in _url)
check("aesgcm URL classifies by extension",
      media_mod.media_kind(
          "aesgcm://example.com/abc.jpg#" + _frag) == "image")

# 10. MUC recipients ---------------------------------------------------------
import types
from stanza_im.xmpp.omemo.manager import OmemoManager

_fake = types.SimpleNamespace(
    _client=types.SimpleNamespace(_muc_users={
        "room@conf": {"a": {"real_jid": "alice@example.com/x"},
                      "b": {"real_jid": "none"}}}),
    _own_bare="me@example.com")
_recips = OmemoManager.muc_recipients(_fake, "room@conf")
check("MUC recipients resolve real JIDs",
      _recips == {"alice@example.com", "me@example.com"})

# 11. aesgcm audio/video renders a viewer link (no native player) ------------
from stanza_im.ui.media_preview import MediaPreviewService
from stanza_im.include import media as media_mod

_cache = media_mod.MediaCache(os.path.join(_SCRATCH, "mediacache"))
_svc = MediaPreviewService(_cache)
_svc.set_mode("all")
_amarkup = _svc.markup("aesgcm://example.com/song.ogg#" + "a" * 88)
check("aesgcm audio renders a viewer link",
      _amarkup and "<audio" not in _amarkup
      and "stanza:view:audio/" in _amarkup)
_vmarkup = _svc.markup("aesgcm://example.com/clip.mp4#" + "a" * 88)
check("aesgcm video renders a viewer link",
      _vmarkup and "<video" not in _vmarkup
      and "stanza:view:video/" in _vmarkup)

# 12. availability detail / install hint / About + prefs ---------------------
check("xmlschema is a required component",
      availability._BY_MODULE.get("xmlschema")
      == ("python-xmlschema", "python3-xmlschema"))

# A package that wraps a missing transitive dependency (oldmemo -> xmlschema)
# must be reported by its root cause, not by the top-level module.
def _fake_probe(module):
    if module in ("slixmpp_omemo", "xmlschema"):
        return False, "xmlschema"
    return True, ""


check("a wrapped missing dependency is reported by its root cause",
      availability._compute_missing(_fake_probe) == ["xmlschema"])

_saved = (availability.AVAILABLE, availability.MISSING,
          availability.MISSING_MODULES, availability.MISSING_DEBIAN,
          availability.BACKENDS)
availability.AVAILABLE = False
availability.MISSING = ["python-xmlschema", "slixmpp-omemo"]
availability.MISSING_MODULES = ["xmlschema", "slixmpp_omemo"]
availability.MISSING_DEBIAN = ["python3-xmlschema", "python3-slixmpp-omemo"]
availability.BACKENDS = frozenset()
_hint = availability.install_hint()
check("install hint is an apt command",
      _hint.startswith("sudo apt install")
      and "python3-xmlschema" in _hint)
_detail = availability.detail()
check("detail lists the missing modules and the install hint",
      "xmlschema" in _detail and "sudo apt install" in _detail)
check("summary marks it unavailable",
      availability.summary().startswith("unavailable"))

from stanza_im.ui.about_dialog import AboutDialog
_about = AboutDialog()
_texts = [lb.text() for lb in _about.findChildren(QtWidgets.QLabel)]
check("About dialog shows the OMEMO row",
      any(availability.summary() in t for t in _texts))
_about.deleteLater()
availability.AVAILABLE, availability.MISSING = _saved[0], _saved[1]
availability.MISSING_MODULES, availability.MISSING_DEBIAN = _saved[2], _saved[3]
availability.BACKENDS = _saved[4]

_prefs_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stanza_im", "ui", "preferences.py"), encoding="utf-8").read()
check("the OMEMO preferences tab is never disabled",
      "setTabEnabled(1, False)" not in _prefs_src)
check("the OMEMO tab carries a detail tooltip",
      "tabs.setTabToolTip(1, availability.detail())" in _prefs_src)

_client_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stanza_im", "core", "client.py"), encoding="utf-8").read()
check("the OMEMO init failure is reported without a traceback",
      "OMEMO could not be initialised: %s" in _client_src
      and 'logger.debug("OMEMO import failed", exc_info=True)' in _client_src)

# 13. own label auto-naming --------------------------------------------------
class _FakeMgr:
    def __init__(self, label):
        self._label = label
        self.set_called = None

    async def own_device(self):
        return types.SimpleNamespace(label=self._label)

    async def set_own_label(self, label):
        self.set_called = label


_mgr = _FakeMgr("")
asyncio.run(OmemoManager.ensure_own_label(_mgr, "host"))
check("ensure_own_label sets a label when empty",
      _mgr.set_called and "host" in _mgr.set_called)
_mgr2 = _FakeMgr("Existing")
asyncio.run(OmemoManager.ensure_own_label(_mgr2, "host"))
check("ensure_own_label keeps an existing label", _mgr2.set_called is None)


# 14. static wiring: force refresh + menu placement --------------------------
_dlg_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stanza_im", "ui", "omemo_devices_dialog.py"), encoding="utf-8").read()
check("the device dialog force-downloads the list",
      "refresh_device_lists([self._jid], force=True)" in _dlg_src)
check("device actions are per-row icon buttons",
      "_device_row" in _dlg_src and "setItemWidget" in _dlg_src
      and "_trust_btn" not in _dlg_src)

_mw_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stanza_im", "ui", "main_window.py"), encoding="utf-8").read()
check("the OMEMO entry follows the subscription menu",
      _mw_src.index('self._menu_icon("shield.svg"), tr("omemo_manage")')
      > _mw_src.index("_build_subscription_menu(menu"))
check("peer OMEMO support falls back to the device list",
      "def _check_peer_omemo" in _mw_src
      and "refresh_device_lists([bare], force=True)" in _mw_src)
check("encrypted messages auto-enable OMEMO",
      "self._maybe_auto_enable_omemo(bare_jid)" in _mw_src)

# 15. auto-enable + config option -------------------------------------------
from stanza_im.core.storage import Config as _Config
check("omemo.auto_enable defaults on", _Config().omemo.auto_enable is True)

from stanza_im.ui.main_window import MainWindow


class _FakeOmemoMgr:
    def __init__(self):
        self.available = True
        self.mode = "off"
        self.set_calls = []

    def chat_mode(self, jid):
        return self.mode

    def set_chat_mode(self, jid, mode):
        self.mode = "omemo" if mode == "omemo" else "off"
        self.set_calls.append((jid, mode))


class _FakeChatWindow:
    def __init__(self):
        self.modes = []

    def set_omemo_mode(self, jid, mode):
        self.modes.append((jid, mode))

    def get_chat(self, jid):
        return None


def _fake_mw(auto_enable):
    return types.SimpleNamespace(
        _client=types.SimpleNamespace(omemo=_FakeOmemoMgr()),
        _config=types.SimpleNamespace(
            omemo=types.SimpleNamespace(auto_enable=auto_enable)),
        _apply_omemo_support=lambda jid: None,
        _chat_window=_FakeChatWindow(),
    )


_mw1 = _fake_mw(True)
MainWindow._maybe_auto_enable_omemo(_mw1, "bob@example.com")
check("an encrypted message auto-enables OMEMO",
      _mw1._client.omemo.mode == "omemo"
      and _mw1._chat_window.modes == [("bob@example.com", "omemo")])

_mw2 = _fake_mw(False)
MainWindow._maybe_auto_enable_omemo(_mw2, "bob@example.com")
check("auto-enable respects the option",
      _mw2._client.omemo.mode == "off" and _mw2._chat_window.modes == [])

# 16. device removal + popup anchoring --------------------------------------
# The popup must accept a QPoint anchor (MainWindow passes QCursor.pos()).
from PyQt6 import QtCore as _QtCore

_orig_reload = OmemoPopup._reload
OmemoPopup._reload = lambda self: None
try:
    _p = OmemoPopup(_FakeClient(), "bob@example.com",
                    anchor=_QtCore.QPoint(300, 250))
    _p.show()
    check("popup accepts a QPoint anchor", _p.y() < 250)
    _p.close()
finally:
    OmemoPopup._reload = _orig_reload

from stanza_im.xmpp.omemo.manager import OmemoManager


class _Dev:
    def __init__(self, did, active):
        self.device_id = did
        self.active = active


check("a device active in a namespace counts as active",
      OmemoManager._device_active(_Dev(1, frozenset({("ns", True)}))))
check("a device inactive everywhere is filtered",
      not OmemoManager._device_active(
          _Dev(2, frozenset({("ns", False), ("ns2", False)}))))
check("a device with no activity info is kept",
      OmemoManager._device_active(_Dev(3, frozenset())))


class _FakeSM:
    def __init__(self):
        self.uploaded = []
        self.updated = []

    async def _download_device_list(self, namespace, bare):
        return {111: None, 222: "label"}

    async def _upload_device_list(self, namespace, dl):
        self.uploaded.append((namespace, dict(dl)))

    async def update_device_list(self, namespace, bare, dl):
        self.updated.append((namespace, set(dl)))

    async def get_device_information(self, bare):
        return frozenset([_Dev(111, frozenset({("ns", True)})),
                          _Dev(222, frozenset({("ns", False)}))])


class _Mgr(OmemoManager):
    def __init__(self, sm):
        self._sm = sm
        self._own_bare = "me@example.com"
        self.alias_cleared = []

    async def session_manager(self):
        return self._sm

    def set_device_alias(self, jid, did, name):
        self.alias_cleared.append((jid, did, name))


async def _run_purge():
    sm = _FakeSM()
    mgr = _Mgr(sm)
    await mgr.purge_device(_Dev(222, frozenset()))
    return sm, mgr


_sm, _mgr = asyncio.run(_run_purge())
check("purge uploads a list without the removed device",
      len(_sm.uploaded) == 2
      and all(222 not in dl and 111 in dl for _ns, dl in _sm.uploaded))
check("purge clears the device alias",
      _mgr.alias_cleared == [("me@example.com", 222, "")])


async def _run_filter():
    return await _Mgr(_FakeSM()).devices("me@example.com")


_devs = asyncio.run(_run_filter())
check("devices() hides inactive devices",
      [int(d.device_id) for d in _devs] == [111])

# 17. device naming + last-seen ---------------------------------------------
from stanza_im.core.client import JabberClient as _JC


class _Contact:
    def __init__(self):
        self.resources = {}


class _ContactClient:
    def __init__(self):
        self.contacts = {}

    def get_contact(self, bare):
        return self.contacts.setdefault(bare, _Contact())


_cc = _ContactClient()
_cc.get_contact("bob@example.com").resources["gajim.abc"] = {
    "client": "Gajim", "caps_node": ""}
_cc.get_contact("bob@example.com").resources["res.caps"] = {
    "client": "", "caps_node": "https://gajim.org/"}
_cc.get_contact("bob@example.com").resources["res.bare"] = {
    "client": "", "caps_node": ""}
check("resource_client_name prefers XEP-0092 software",
      _JC.resource_client_name(_cc, "bob@example.com", "gajim.abc") == "Gajim")
_caps_name = _JC.resource_client_name(_cc, "bob@example.com", "res.caps")
check("resource_client_name falls back to caps", bool(_caps_name))
check("resource_client_name is empty without a hint",
      _JC.resource_client_name(_cc, "bob@example.com", "res.bare") == "")


class _Store:
    def __init__(self):
        self.data = {}

    def get_app(self, key, default=None):
        return self.data.get(key, default)

    def set_app(self, key, value):
        self.data[key] = value


class _Plugin:
    def __init__(self):
        self.storage = _Store()


class _MgrClient:
    def __init__(self):
        self.xmpp = {"xep_0384": _Plugin()}
        self.jid_str = "me@example.com"
        self._names = {}

    def resource_client_name(self, jid, resource):
        return self._names.get(resource, "")


def _make_manager():
    client = _MgrClient()
    return OmemoManager(client), client


_mgr2, _c2 = _make_manager()
check("an unknown device shows Device <id>",
      _mgr2.device_name("bob@example.com", 1) == "Device 1")
check("the peer label outranks a learned name",
      _mgr2.device_name("bob@example.com", 1, label="Bob's phone")
      == "Bob's phone")
_mgr2.note_device_resource("bob@example.com", 2, "gajim.abc")
_c2._names["gajim.abc"] = "Gajim"
check("a learned resource resolves to the client name",
      _mgr2.device_name("bob@example.com", 2) == "Gajim")
check("the peer label outranks the learned client name",
      _mgr2.device_name("bob@example.com", 2, label="Phone") == "Phone")
_mgr2.set_device_alias("bob@example.com", 2, "My Gajim")
check("a user alias outranks everything",
      _mgr2.device_name("bob@example.com", 2, label="Phone") == "My Gajim")
check("the learned resource is persisted",
      _c2.xmpp["xep_0384"].storage.get_app("device_names", {})
      == {"bob@example.com/2": "gajim.abc"})
# A fresh manager over the same store still knows the resource.
_mgr2b = OmemoManager(_c2)
check("a learned resource survives a restart",
      _mgr2b.device_resource("bob@example.com", 2) == "gajim.abc")

# Presence refresh: only mapped devices get their last-seen updated.
_mgr2.note_resource_seen("bob@example.com", "gajim.abc")
_seen = _c2.xmpp["xep_0384"].storage.get_app("device_last_seen", {})
check("presence refreshes last-seen for the mapped device",
      _seen.get("bob@example.com/2", 0) > 0)
_mgr2.note_resource_seen("bob@example.com", "unmapped.res")
check("presence leaves unmapped devices untouched",
      "bob@example.com/9" not in _seen)

# Device ordering: activity first (newest first), then named, then the rest.
class _D:
    def __init__(self, did, label=""):
        self.device_id = did
        self.label = label


_mgr3, _c3 = _make_manager()
_store3 = _c3.xmpp["xep_0384"].storage
_store3.set_app("device_last_seen", {"bob@example.com/1": 100.0,
                                     "bob@example.com/4": 200.0})
_store3.set_app("device_aliases", {"bob@example.com/2": "Named"})
_order = [int(d.device_id) for d in _mgr3.sorted_devices(
    "bob@example.com", [_D(3), _D(1), _D(2), _D(4)])]
check("devices sort by activity, then name, then the rest",
      _order == [4, 1, 2, 3])
# A named device without activity still outranks an unnamed one.
_order2 = [int(d.device_id) for d in _mgr3.sorted_devices(
    "bob@example.com", [_D(7), _D(2)])]
check("a named device without activity leads an unnamed one",
      _order2 == [2, 7])

# MUC guard: the device<->resource mapping is only learned for 1:1.
_client_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stanza_im", "core", "client.py"), encoding="utf-8").read()
check("resource learning is guarded to non-groupchat",
      'str(msg["type"]) != "groupchat"' in _client_src
      and "note_device_resource" in _client_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All OMEMO tests passed.")
