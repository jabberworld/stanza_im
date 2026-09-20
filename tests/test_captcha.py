"""Offscreen tests for XEP-0158 CAPTCHA Forms (responder side).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_captcha.py
"""
import asyncio
import hashlib
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_captcha_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

import slixmpp

from stanza_im.core.client import (
    JabberClient, NS_CAPTCHA, NS_DATA, NS_MEDIA,
    _is_captcha_message,
)
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.data_form_widget import DataFormWidget, _HashcashSolver, \
    _field_media

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _field(form_el, var, value="", ftype=None, label=None, media=None):
    field = ET.SubElement(form_el, f"{{{NS_DATA}}}field")
    field.set("var", var)
    if ftype:
        field.set("type", ftype)
    if label:
        field.set("label", label)
    if value is not None:
        val = ET.SubElement(field, f"{{{NS_DATA}}}value")
        val.text = value
    if media:
        mime, url = media
        media_el = ET.SubElement(field, f"{{{NS_MEDIA}}}media")
        media_el.set("height", "80")
        uri = ET.SubElement(media_el, f"{{{NS_MEDIA}}}uri")
        uri.set("type", mime)
        uri.text = url
    return field


def _challenge(form_el):
    m = slixmpp.Message()
    m["from"] = "room@conf.example"
    m["to"] = "me@example.com/r"
    m["type"] = "normal"
    m["body"] = "Solve the challenge"
    captcha = ET.SubElement(m.xml, f"{{{NS_CAPTCHA}}}captcha")
    form_el.set("type", "form")
    captcha.append(form_el)
    return m


def _form_element():
    return ET.Element(f"{{{NS_DATA}}}x")


# 1. parsing ---------------------------------------------------------------
form_el = _form_element()
_field(form_el, "FORM_TYPE", "urn:xmpp:captcha", "hidden")
_field(form_el, "from", "room@conf.example", "hidden")
_field(form_el, "challenge", "ch-1", "hidden")
_field(form_el, "sid", "sid-1", "hidden")
_field(form_el, "ocr", "", label="Enter the text you see",
       media=("image/jpeg", "http://server.example/captcha.jpg"))
msg = _challenge(form_el)

check("captcha message detected", _is_captcha_message(msg) is True)

c = JabberClient("me@example.com/r", "pw")
form = c._captcha_form(msg)
check("captcha form parsed", form is not None)
fields = form.get_fields() if form is not None else {}
check("captcha fields parsed",
      {"FORM_TYPE", "from", "challenge", "sid", "ocr"} <= set(fields))

# 2. the challenge never renders as a chat message ------------------------
received, challenges = [], []
c.on("message_received", lambda *a: received.append(a))
c.on("captcha_challenge", lambda *a: challenges.append(a))
c._on_message(msg)
check("captcha is not a chat message", received == [])
asyncio.new_event_loop().run_until_complete(c._on_captcha_stanza(msg))
check("captcha challenge emitted",
      len(challenges) == 1 and challenges[0][0] == "room@conf.example"
      and challenges[0][1] is not None)

# 3. media extraction ------------------------------------------------------
media = _field_media(fields["ocr"])
check("media uri parsed",
      media == {"kind": "image", "url": "http://server.example/captcha.jpg",
                "mime": "image/jpeg", "alt": ""})

# 4. response stanza -------------------------------------------------------
fields["ocr"]["value"] = "7nHL3"
iq = c._build_captcha_response("room@conf.example", form)
captcha = iq.xml.find(f"{{{NS_CAPTCHA}}}captcha")
check("response wraps a captcha element", captcha is not None)
x = captcha.find(f"{{{NS_DATA}}}x") if captcha is not None else None
check("response is a submit form",
      x is not None and x.get("type") == "submit")
values = {}
for field in x.iter(f"{{{NS_DATA}}}field"):
    value = field.find(f"{{{NS_DATA}}}value")
    values[str(field.get("var"))] = value.text if value is not None else None
check("response carries FORM_TYPE",
      values.get("FORM_TYPE") == "urn:xmpp:captcha")
check("response carries the answer", values.get("ocr") == "7nHL3")
check("response carries challenge/sid",
      values.get("challenge") == "ch-1" and values.get("sid") == "sid-1")

# 5. data form widget renders the media field -------------------------------
widget = DataFormWidget(form)
check("media field keeps its text input",
      isinstance(widget._fields.get("ocr"), QtWidgets.QLineEdit))
labels = [lbl.text() for lbl in widget.findChildren(QtWidgets.QLabel)]
check("media field shows a loading placeholder",
      any(t == "Loading…" for t in labels))

# 6. SHA-256 hashcash solver ------------------------------------------------
solved = []
solver = _HashcashSolver()
solver.solved.connect(solved.append)
solver.failed.connect(lambda msg: solved.append(""))
solver._run("victim@example.com", "0")
check("hashcash solved", bool(solved) and solved[0] != "")
if solved and solved[0]:
    digest = hashlib.sha256(solved[0].encode("utf-8")).digest()
    check("hashcash answer matches the label",
          int.from_bytes(digest, "big") & 0xF == 0)
    check("hashcash answer starts with the JID",
          solved[0].startswith("victim@example.com"))

# 7. static wiring ----------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    return open(os.path.join(_root, *parts), encoding="utf-8").read()


_client_src = _src("stanza_im", "core", "client.py")
check("client parses and answers captchas",
      "def answer_captcha" in _client_src
      and "def _captcha_form" in _client_src
      and 'NS_CAPTCHA = "urn:xmpp:captcha"' in _client_src)
check("captcha challenge matcher registered",
      'MatchXPath("%s/{%s}captcha"' in _client_src)
check("XEPs.md lists XEP-0158 and XEP-0221",
      "XEP-0158" in _src("XEPs.md") and "XEP-0221" in _src("XEPs.md"))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All captcha tests passed.")
