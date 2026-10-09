"""Tests for XEP-0394 Message Markup parsing/rendering.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_message_markup.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_markup_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.xmpp import message_markup as mm
from stanza_im.xmpp.message_markup import parse_message, render

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def frag(raw):
    return mm.escape_html(raw)


def markup(xml):
    return parse_message(ET.fromstring(xml))


_M = '<message xmlns="jabber:client">%s</message>'
_MK = '<markup xmlns="urn:xmpp:markup:0">%s</markup>'

# 1. inline emphasis (XEP example 1) -----------------------------------------
body = "There is really no reason to worry."
mk = markup(_M % (_MK % '<span start="9" end="15"><emphasis/></span>'))
html = render(body, mk, frag)
check("inline emphasis renders <em>", "<em>really</em>" in html)
check("inline emphasis keeps the rest plain",
      html.startswith("There is ") and html.endswith(" no reason to worry."))

# 2. code block (XEP example 2) ----------------------------------------------
body = "Just run this command:\n$ cowsay XMPP is awesome."
mk = markup(_M % (_MK % '<bcode start="23" end="48" language="bash"/>'))
html = render(body, mk, frag)
check("bcode renders a <pre> block", "<pre" in html and "</pre>" in html)
check("bcode keeps the command text",
      "$ cowsay XMPP is awesome." in html)

# 3. itemized list (XEP example 3) -------------------------------------------
body = ("This XEP supports many things:\n* inline markup\n* code blocks\n"
        "* lists\n* and possibly more!")
mk = markup(_M % (_MK % '<list start="31" end="89" ordered="false">'
                        '<li start="31"/><li start="47"/><li start="61"/>'
                        '<li start="69"/></list>'))
html = render(body, mk, frag)
check("list renders <ul>/<li>", "<ul" in html and html.count("<li>") == 4)
check("list strips the leading bullet markers", "* inline markup" not in html)
check("list keeps the item text",
      "<li>inline markup</li>" in html
      and "<li>and possibly more!</li>" in html)

# 3b. ordered list -----------------------------------------------------------
mk = markup(_M % (_MK % '<list start="31" end="49" ordered="true">'
                        '<li start="31"/><li start="47"/></list>'))
html = render(body, mk, frag)
check("ordered list renders <ol>", "<ol" in html)

# 4. blockquote (XEP example 4) ----------------------------------------------
body = "He said:\n> Thou shalt not pass!\nand raised his hand."
mk = markup(_M % (_MK % '<bquote start="9" end="32"/>'))
html = render(body, mk, frag)
check("bquote renders <blockquote>", "<blockquote" in html)
check("bquote strips the leading '>' marker",
      "> Thou shalt not pass!" not in html
      and "Thou shalt not pass!" in html)
check("bquote keeps the surrounding text",
      html.startswith("He said:") and "and raised his hand." in html)

# 5. nested blockquote (XEP example 5) ---------------------------------------
body = ("> He said:\n>> Thou shalt not pass!\n> and raised his hand.\n\n"
        "Isn't this from some famous movie?")
mk = markup(_M % (_MK % '<bquote start="0" end="57"/>'
                        '<bquote start="11" end="34"/>'))
html = render(body, mk, frag)
check("nested bquote renders two levels", html.count("<blockquote") == 2)
check("nested bquote strips one marker per level",
      "Thou shalt not pass!" in html and ">>" not in html
      and "> He said:" not in html)

# 6. span types + containment ------------------------------------------------
body = "hello world foo"
mk = markup(_M % (_MK % '<span start="0" end="5"><strong/></span>'
                        '<span start="6" end="11"><deleted/></span>'
                        '<span start="12" end="15"><code/></span>'))
html = render(body, mk, frag)
check("strong span", "<strong>hello</strong>" in html)
check("deleted span", "line-through" in html and "world" in html)
check("code span", "<code" in html and "foo" in html)

# 7. unknown elements are ignored; bad ranges dropped at render --------------
mk = markup(_M % (_MK % '<span start="0" end="3"><emphasis/></span>'
                        '<frobnicate start="0" end="3"/>'
                        '<span start="9" end="4"><strong/></span>'))
check("unknown markup element ignored", mk is not None
      and len(mk["spans"]) == 2)
check("an inverted range is dropped at render",
      render("abcdef", mk, frag).count("<em>") == 1
      and "<strong>" not in render("abcdef", mk, frag))
check("markup without usable children is None",
      parse_message(ET.fromstring(_M % (_MK % '<unknown/>'))) is None)
check("message without markup is None",
      parse_message(ET.fromstring(_M % "<body>hi</body>")) is None)

# 8. clamping beyond the body length -----------------------------------------
mk = markup(_M % (_MK % '<span start="0" end="999"><emphasis/></span>'))
html = render("abc", mk, frag)
check("out-of-range end is clamped", "<em>abc</em>" in html)

# 9. client helper + history round-trip --------------------------------------
import types

from stanza_im.core.client import message_markup as client_markup

_msg = types.SimpleNamespace(xml=ET.fromstring(
    _M % ("<body>There is really no reason to worry.</body>"
          + (_MK % '<span start="9" end="15"><emphasis/></span>'))))
check("client.message_markup parses the stanza",
      client_markup(_msg) is not None
      and client_markup(_msg)["spans"][0]["start"] == 9)
check("client.message_markup without markup is None",
      client_markup(types.SimpleNamespace(
          xml=ET.fromstring(_M % "<body>x</body>"))) is None)

from stanza_im.core import history

history.store_message(
    "markup@example.com", "incoming", "There is really no reason to worry.",
    sender="bob", origin_id="m1", markup=client_markup(_msg))
_entries = history.load_history("markup@example.com")
check("markup is persisted and reloaded",
      _entries and _entries[-1].get("markup", {}).get("spans"))
_entry = history.entry_by_ref("markup@example.com", "m1")
check("entry_by_ref returns the markup",
      _entry is not None and _entry.get("markup", {}).get("blocks") == [])
history.replace_message("markup@example.com", "m1", "edited", markup=None)
_entry = history.entry_by_ref("markup@example.com", "m1")
check("replace_message clears the markup", _entry.get("markup") is None)

# 10. theme integration + XEP-0393 precedence --------------------------------
from PyQt6 import QtWidgets

from stanza_im.ui.chat_themes import ChatThemeFactory

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
theme = ChatThemeFactory()
theme.set_message_styling(True)
theme.set_chat_font("", 0)
html = theme.render_message(
    sender="bob", body="There is really no reason to worry.",
    timestamp="12:00", direction="incoming",
    markup=client_markup(_msg))
check("theme renders the XEP-0394 markup", "<em>really</em>" in html)
# With markup present the XEP-0393 parser must not run on the body: the
# asterisks stay literal because the span only covers "bold".
html2 = theme.render_message(
    sender="bob", body="*bold* text", timestamp="12:00",
    direction="incoming",
    markup={"spans": [{"start": 1, "end": 5, "types": ["strong"]}],
            "blocks": []})
check("XEP-0394 takes precedence over XEP-0393",
      "*<strong>bold</strong>* text" in html2)
# With styling disabled neither runs.
theme.set_message_styling(False)
html3 = theme.render_message(
    sender="bob", body="There is really no reason to worry.",
    timestamp="12:00", direction="incoming", markup=client_markup(_msg))
check("markup ignored when styling is disabled", "<em>" not in html3)
theme.set_message_styling(True)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All message-markup tests passed.")
