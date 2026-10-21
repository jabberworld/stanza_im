"""Offscreen tests for DataFormWidget (XEP-0004), incl. text-multi.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_data_form.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.data_form_widget import DataFormWidget

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _field(ftype, var, value, label="", required=False):
    return {"type": ftype, "var": var, "value": value, "label": label,
            "required": required, "options": []}


# text-multi is a list of lines (one <value> each) and must be edited in a
# multi-line widget — not a single-line QLineEdit with a fake hint.
form = {"title": "", "instructions": [], "type": "form", "fields": [
    _field("text-multi", "replyText", ["Первая строка", "Вторая строка"]),
    _field("text-single", "nick", "bob"),
]}

widget = DataFormWidget(form)
edit = widget._fields["replyText"]
check("text-multi renders a multi-line editor",
      isinstance(edit, QtWidgets.QPlainTextEdit))
check("text-multi shows every line",
      edit.toPlainText() == "Первая строка\nВторая строка")
check("text-multi submits a list of lines",
      widget.values()["replyText"] == ["Первая строка", "Вторая строка"])
check("text-multi has no fake placeholder",
      "line1" not in edit.placeholderText())
check("text-single still uses a one-line editor",
      isinstance(widget._fields["nick"], QtWidgets.QLineEdit)
      and widget.values()["nick"] == "bob")

# A single-line value for text-multi is accepted too.
form2 = {"title": "", "instructions": [], "type": "form", "fields": [
    _field("text-multi", "notes", "only line")]}
widget2 = DataFormWidget(form2)
check("a scalar text-multi value is shown as one line",
      widget2._fields["notes"].toPlainText() == "only line")
check("an empty text-multi yields no value lines",
      DataFormWidget({"title": "", "instructions": [], "type": "form",
                      "fields": [_field("text-multi", "x", "")]}
                     ).values()["x"] == [])

# jid-multi is a list of JIDs (one per line), normalized on submit.
form3 = {"title": "", "instructions": [], "type": "form", "fields": [
    _field("jid-multi", "muc#roomconfig_captcha_whitelist",
           ["a@example.com", "b@example.com"]),
    _field("jid-multi", "empty", ""),
]}
widget3 = DataFormWidget(form3)
_edit3 = widget3._fields["muc#roomconfig_captcha_whitelist"]
check("jid-multi renders a multi-line editor",
      isinstance(_edit3, QtWidgets.QPlainTextEdit))
check("jid-multi shows one JID per line",
      _edit3.toPlainText() == "a@example.com\nb@example.com")
check("jid-multi submits a list of JIDs",
      widget3.values()["muc#roomconfig_captcha_whitelist"]
      == ["a@example.com", "b@example.com"])
check("an empty jid-multi yields no values",
      widget3.values()["empty"] == [])
_edit3.setPlainText("xmpp:Alice@Example.COM/res, bob@example.com\n\n")
check("jid-multi normalises the JIDs (scheme, resource, commas)",
      widget3.values()["muc#roomconfig_captcha_whitelist"]
      == ["Alice@example.com", "bob@example.com"])

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All data-form tests passed.")
