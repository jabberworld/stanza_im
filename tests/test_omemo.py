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
_cw.set_omemo_mode("off")
check("OMEMO shield hidden when off", _cw._omemo_shield_btn.isHidden())
_cw.detach()

from stanza_im.include.constants import find_icon
check("the QR icon resolves", bool(find_icon("qr.svg")))
check("the shield icon resolves", bool(find_icon("shield.svg")))

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

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All OMEMO tests passed.")
