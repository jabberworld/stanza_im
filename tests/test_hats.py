"""Offscreen tests for XEP-0317 Hats and XEP-0392 colour generation.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_hats.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_hats_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets
import slixmpp

from stanza_im.core.client import JabberClient
from stanza_im.i18n import load as i18n_load
from stanza_im.include import hats as hats_mod
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.main_window import MainWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. hat URI ------------------------------------------------------------------
uri_a = hats_mod.hat_uri("room@conf.example", "Host")
check("URI is deterministic", uri_a == hats_mod.hat_uri("room@conf.example", "Host"))
check("URI depends on the room",
      uri_a != hats_mod.hat_uri("other@conf.example", "Host"))
check("URI depends on the title",
      uri_a != hats_mod.hat_uri("room@conf.example", "Other"))
check("URI carries the hats prefix", uri_a.startswith("urn:xmpp:hats:"))

# 2. hue <-> colour (XEP-0392 test vectors) -----------------------------------
vectors = [
    ("Romeo", 327.255249, (0.865, 0.000, 0.686)),
    ("juliet@capulet.lit", 209.410400, (0.000, 0.515, 0.573)),
    ("council", 359.994507, (0.918, 0.000, 0.394)),
    ("Board", 171.430664, (0.000, 0.527, 0.457)),
]
import hashlib


def angle_of(text):
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "little") / 65536.0 * 360.0


for text, want_angle, want_rgb in vectors:
    got = hats_mod.hsluv_to_rgb(angle_of(text), 100.0, 50.0)
    ok = (abs(angle_of(text) - want_angle) < 0.01
          and max(abs(a - b) for a, b in zip(got, want_rgb)) < 0.01)
    check("XEP-0392 vector %s" % text, ok)
check("hue_to_color returns hex", hats_mod.hue_to_color(200.0).startswith("#"))
check("hue_to_color without hue is empty", hats_mod.hue_to_color(None) == "")
check("parse_hue normalises", hats_mod.parse_hue("370") == 10.0)
check("parse_hue rejects garbage", hats_mod.parse_hue("x") is None)

# 3. parsing <hats/> from presence --------------------------------------------
pres = slixmpp.Presence()
pres["from"] = "room@conf.example/Bob"
pres["type"] = "available"
muc = ET.SubElement(pres.xml, "{http://jabber.org/protocol/muc#user}x")
muc.set("affiliation", "member")
muc.set("role", "participant")
ET.SubElement(muc, "{http://jabber.org/protocol/muc#user}item")
hats_el = ET.SubElement(pres.xml, "{urn:xmpp:hats:0}hats")
hat_el = ET.SubElement(hats_el, "{urn:xmpp:hats:0}hat")
hat_el.set("title", "Host")
hat_el.set("uri", "urn:xmpp:hats:abc")
hat_el.set("hue", "327.255249")
parsed = hats_mod.parse_hats(pres)
check("parse_hats extracts the hat",
      len(parsed) == 1 and parsed[0]["title"] == "Host"
      and parsed[0]["uri"] == "urn:xmpp:hats:abc")
check("parse_hats keeps the hue", abs(parsed[0]["hue"] - 327.255249) < 0.001)
check("parse_hats on a bare presence is empty", hats_mod.parse_hats(
    slixmpp.Presence()) == [])

# 4. result-form parsing + submit building ------------------------------------
root = ET.Element("iq")
cmd = ET.SubElement(root, "{http://jabber.org/protocol/commands}command")
x = ET.SubElement(cmd, "{jabber:x:data}x")
x.set("type", "result")
reported = ET.SubElement(x, "{jabber:x:data}reported")
for var in ("hats#title", "hats#uri", "hats#hue"):
    f = ET.SubElement(reported, "{jabber:x:data}field")
    f.set("var", var)
item = ET.SubElement(x, "{jabber:x:data}item")
for var, val in (("hats#title", "Host"), ("hats#uri", "urn:xmpp:hats:abc"),
                 ("hats#hue", "10")):
    f = ET.SubElement(item, "{jabber:x:data}field")
    f.set("var", var)
    v = ET.SubElement(f, "{jabber:x:data}value")
    v.text = val
rows = hats_mod.parse_result_form(root)
check("parse_result_form reads items",
      rows == [{"hats#title": "Host", "hats#uri": "urn:xmpp:hats:abc",
                "hats#hue": "10"}])
check("command_session reads sessionid",
      hats_mod.command_session(ET.Element("iq")) == ("", ""))

submit = hats_mod.build_command(hats_mod.CMD_CREATE,
                                {"hats#title": "Host",
                                 "hats#uri": "urn:xmpp:hats:abc"},
                                sessionid="s1")
check("built command node/action",
      submit.get("node") == hats_mod.CMD_CREATE
      and submit.get("action") == "execute" and submit.get("sessionid") == "s1")
form = submit.find("{jabber:x:data}x")
check("built form is a submit", form is not None and form.get("type") == "submit")
vars_ = [f.get("var") for f in form.findall("{jabber:x:data}field")]
check("submit carries FORM_TYPE + fields",
      vars_ == ["FORM_TYPE", "hats#title", "hats#uri"])
check("plain execute has no form",
      hats_mod.build_command(hats_mod.CMD_LIST).find("{jabber:x:data}x") is None)

# 5. client wrappers ----------------------------------------------------------
c = JabberClient("me@example.com/res", "pw")
iq = c._hats_command("room@conf.example", hats_mod.CMD_ASSIGN,
                     {"hats#jid": "bob@example.com", "hats#uri": "u"})
check("client builds a hats IQ",
      iq["type"] == "set" and str(iq["to"]) == "room@conf.example"
      and iq.xml.find("{http://jabber.org/protocol/commands}command") is not None)
rows2 = JabberClient._hats_rows(root)
check("client maps result rows",
      rows2 and rows2[0]["title"] == "Host"
      and rows2[0]["uri"] == "urn:xmpp:hats:abc"
      and abs(rows2[0]["hue"] - 10.0) < 0.001)

events = []
c.on("groupchat_presence", lambda *a: events.append(a))
c._on_groupchat_presence(pres)
check("presence hats stored on the occupant",
      c.groupchats["room@conf.example"].users["Bob"]["hats"][0]["title"]
      == "Host")
check("presence event carries hats",
      events and events[-1][-1] and events[-1][-1][0]["title"] == "Host")

# 6. MainWindow stores hats and offers the context submenu --------------------
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
win._on_groupchat_presence("room@conf.example", "Bob", "online", "",
                           "participant", "member", "", parsed)
check("MainWindow stores the participant hats",
      win._muc_users["room@conf.example"]["Bob"]["hats"][0]["title"] == "Host")
win._on_groupchat_presence("room@conf.example", "Bob", "online", "",
                           "participant", "member", "")
check("MainWindow keeps hats when a presence omits them",
      win._muc_users["room@conf.example"]["Bob"]["hats"])

# 7. chat rendering + tooltip -------------------------------------------------
theme = ChatThemeFactory()
html = theme.render_message("Bob", "hi", "12:00", "incoming",
                            hats=[{"title": "Host", "uri": "u",
                                   "hue": 327.255249}])
check("message renders a hat chip", "stanza-hat" in html and "Host" in html)
check("hat chip carries a colour", "color:#" in html)
check("message without hats has no chip",
      "stanza-hat" not in theme.render_message("Bob", "hi", "12:00", "incoming"))

widget = ChatWidget("room@conf.example/me", "Room", ChatThemeFactory(),
                    is_muc=True)
widget._users = [{"nick": "Bob", "real_jid": "bob@example.com",
                  "hats": [{"title": "Host", "uri": "u", "hue": 10.0}]}]
check("tooltip lists hats", "Hats" in widget._participant_tooltip(
    widget._users[0]) and "Host" in widget._participant_tooltip(widget._users[0]))
check("_user_hats resolves by nick",
      widget._user_hats({"sender": "Bob"})[0]["title"] == "Host")
check("entry kwargs carry hats",
      widget._entry_view_kwargs({"sender": "Bob"})["hats"][0]["title"] == "Host")
check("1:1 chats never carry hats",
      ChatWidget("u@x", "U", ChatThemeFactory())._user_hats(
          {"sender": "Bob"}) == [])

# 8. static wiring ------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    return open(os.path.join(_root, *parts), encoding="utf-8").read()


_client_src = _src("stanza_im", "core", "client.py")
check("client exposes the hats API",
      all(k in _client_src for k in (
          "hats_list", "hats_list_assigned", "hats_create", "hats_update",
          "hats_destroy", "hats_assign", "hats_unassign", "room_supports_hats")))
check("presence parse stores hats", "hats_mod.parse_hats(pres)" in _client_src)
_mw_src = _src("stanza_im", "ui", "main_window.py")
check("context menu offers the hats submenu",
      '"muc_user_hats"' in _mw_src and "def _show_hat_assign" in _mw_src
      and "def _show_hat_unassign" in _mw_src)
_muc_src = _src("stanza_im", "ui", "muc_config_dialog.py")
check("room dialog embeds the hats tab", "HatsTab(" in _muc_src)
_xeps = _src("XEPs.md")
check("XEPs.md lists XEP-0317", "XEP-0317" in _xeps)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All hats tests passed.")
