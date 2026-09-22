"""Offscreen tests for XEP-0158 CAPTCHA Forms (responder side).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_captcha.py
"""
import asyncio
import base64
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
    _field_media, fit_dialog_to_content

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _field(form_el, var, value="", ftype=None, label=None, media=None,
           required=False):
    field = ET.SubElement(form_el, f"{{{NS_DATA}}}field")
    field.set("var", var)
    if ftype:
        field.set("type", ftype)
    if label:
        field.set("label", label)
    if value is not None:
        val = ET.SubElement(field, f"{{{NS_DATA}}}value")
        val.text = value
    if required:
        ET.SubElement(field, f"{{{NS_DATA}}}required")
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

# 6. XEP-0231 Bits of Binary captcha media ----------------------------------
NS_BOB = "urn:xmpp:bob"
_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAACXBIWXMAAA7"
            "EAAAOxAGVKw4bAAAAFklEQVQImWP8z8DAwMDAxMDAwMDAAAANHQEDDMfniQAAAABJ"
            "RU5ErkJggg==")

bob_form = _form_element()
_field(bob_form, "ocr", "", label="Enter the text",
       media=("image/png", "cid:sha1+abc@bob.xmpp.org"))
bob_msg = _challenge(bob_form)
bob_data = ET.SubElement(bob_msg.xml, f"{{{NS_BOB}}}data")
bob_data.set("cid", "sha1+abc@bob.xmpp.org")
bob_data.set("type", "image/png")
bob_data.text = _PNG_B64

bob_form_parsed = c._captcha_form(bob_msg)
bob_uri = (bob_form_parsed.xml.find(f".//{{{NS_MEDIA}}}uri")
           if bob_form_parsed is not None else None)
check("BOB captcha URI resolved to a data URI",
      bob_uri is not None
      and str(bob_uri.text or "").startswith("data:image/png;base64,"))

bob_media = (_field_media(bob_form_parsed.get_fields()["ocr"])
             if bob_form_parsed is not None else None)
check("resolved BOB media is an image",
      bob_media is not None and bob_media["kind"] == "image"
      and bob_media["url"].startswith("data:image/png;base64,"))

bob_widget = DataFormWidget(bob_form_parsed)
bob_labels = bob_widget.findChildren(QtWidgets.QLabel)
check("BOB image is rendered inline",
      any(lbl.pixmap() is not None and not lbl.pixmap().isNull()
          for lbl in bob_labels))


# 7. clickable URL fields and image sizing ----------------------------------
url_form = _form_element()
_field(url_form, "url", "http://server.example/captcha.jpg", "text-single",
       label="Captcha URL")
url_widget = DataFormWidget(c._captcha_form(_challenge(url_form)))
url_links = [lbl for lbl in url_widget.findChildren(QtWidgets.QLabel)
             if "<a href=" in lbl.text()]
check("a URL text field gets a clickable link",
      len(url_links) == 1 and url_links[0].openExternalLinks() is True)
check("the URL link uses the field label as its text",
      ">Captcha URL</a>" in url_links[0].text())
check("the URL link keeps the URL as a tooltip",
      url_links[0].toolTip() == "http://server.example/captcha.jpg")
check("the URL field has no editable input",
      "url" not in url_widget._fields and "url" in url_widget._link_fields)
check("the URL link spans the whole row",
      url_widget._form_layout.getItemPosition(
          url_widget._form_layout.indexOf(url_links[0]))[1]
      == QtWidgets.QFormLayout.ItemRole.SpanningRole)

req_form = _form_element()
_field(req_form, "url", "http://server.example/x", "text-single",
       label="Captcha URL", required=True)
req_widget = DataFormWidget(c._captcha_form(_challenge(req_form)))
check("a required read-only URL link still validates",
      req_widget.validate() is None)

fixed_form = _form_element()
_field(fixed_form, "note", "http://server.example/help", "fixed")
fixed_widget = DataFormWidget(c._captcha_form(_challenge(fixed_form)))
fixed_links = [lbl for lbl in fixed_widget.findChildren(QtWidgets.QLabel)
               if "<a href=" in lbl.text()]
check("a fixed URL value becomes a clickable link", len(fixed_links) == 1)

plain_form = _form_element()
plain_field = ET.SubElement(plain_form, f"{{{NS_DATA}}}field")
plain_field.set("type", "fixed")
plain_value = ET.SubElement(plain_field, f"{{{NS_DATA}}}value")
plain_value.text = "If you cannot see the image, open the link."
plain_widget = DataFormWidget(c._captcha_form(_challenge(plain_form)))
plain_lbl = next(lbl for lbl in plain_widget.findChildren(QtWidgets.QLabel)
                 if lbl.text() == plain_value.text)
check("an unlabeled fixed field spans both columns",
      plain_widget._form_layout.getItemPosition(
          plain_widget._form_layout.indexOf(plain_lbl))[1]
      == QtWidgets.QFormLayout.ItemRole.SpanningRole)

bob_img = next(lbl for lbl in bob_labels
               if lbl.pixmap() is not None and not lbl.pixmap().isNull())
check("an inline image label is sized to the pixmap",
      bob_img.minimumSize() == bob_img.pixmap().size()
      and bob_img.maximumSize() == bob_img.pixmap().size())

ready = []
bob_widget.media_ready.connect(lambda: ready.append(True))
bob_widget._set_media_pixmap(bob_img, base64.b64decode(_PNG_B64))
check("setting a pixmap emits media_ready", ready == [True])

fit_dlg = QtWidgets.QDialog()
fit_form = DataFormWidget(bob_form_parsed)
fit_scroll = QtWidgets.QScrollArea()
fit_scroll.setWidgetResizable(True)
fit_scroll.setWidget(fit_form)
QtWidgets.QVBoxLayout(fit_dlg).addWidget(fit_scroll)
fit_dlg._form_scroll = fit_scroll
fit_dialog_to_content(fit_dlg)
check("fit_dialog_to_content runs offscreen", fit_dlg.width() > 0)
check("the fitted dialog covers the whole form (no scrolling needed)",
      fit_dlg.width() >= fit_form.sizeHint().width()
      and fit_dlg.height() >= fit_form.sizeHint().height())


# 8. static wiring ----------------------------------------------------------
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
