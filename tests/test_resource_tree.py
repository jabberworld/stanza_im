"""Offscreen tests for the shared per-resource client tree.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_resource_tree.py
"""
import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.i18n import tr
from stanza_im.ui.resource_tree import resource_tree_html

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

_STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

b1 = {"resource": "laptop", "show": "online", "status": "Working",
      "client": "Gajim", "version": "2.6.0", "os": "Linux", "tzo": "+03:00",
      "caps_node": ""}
b2 = {"resource": "phone", "show": "away", "status": "",
      "client": "Conversations", "version": "2.20.1", "os": "", "tzo": "",
      "caps_node": ""}

tree = resource_tree_html([b1, b2])
check("one table for all resources",
      tree.count("<table") == 1 and tree.count("</table>") == 1)
check("no separator between resources",
      tree.count("<tr>") == 6)  # 3 rows (name/time/client) + 2 rows (name/client)
check("both resources present", "<b>laptop</b>" in tree and "<b>phone</b>" in tree)
check("status icon before the name", "jabber-online.png" in tree)
check("clock icon on its own row",
      tree.index("<b>laptop</b>") < tree.index("clock.svg"))
check("local time formatted", bool(_STAMP.search(tree)))
check("client version and OS shown", "Gajim 2.6.0 / Linux" in tree)
check("client without an OS has no separator",
      "Conversations 2.20.1</td>" in tree)
check("status label present", tr("tooltip_status") in tree)
check("no empty resource rows", "<td></td><td></td>" not in tree)
check("empty tree renders nothing", resource_tree_html([]) == "")

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All resource-tree tests passed.")
