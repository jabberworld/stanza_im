"""Offscreen test for rendering prepared chat HTML without a tab.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_chat_render_prepare.py
"""
import os
import sys
import tempfile

os.environ["XDG_CACHE_HOME"] = os.path.join(tempfile.mkdtemp(), "cache")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tempfile.mkdtemp(), "config")
os.environ["XDG_DATA_HOME"] = os.path.join(tempfile.mkdtemp(), "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402
from stanza_im.ui.chat_render_prepare import render_prepared  # noqa: E402

i18n_load("en")
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


entries = [
    {"sender": "Bob", "body": "hello", "direction": "incoming",
     "timestamp": "2026-10-21T11:00:00Z", "origin_id": "m1"},
    {"sender": "Me", "body": "hi", "direction": "outgoing",
     "timestamp": "2026-10-21T11:01:00Z", "origin_id": "m2"},
]
result = render_prepared(entries, display_name="Bob", own_jid="me@example.com",
                         theme=ChatThemeFactory())
check("a prepared window is rendered", result is not None)
if result:
    settings, refs, html = result
    check("the settings hash is present", bool(settings))
    check("one ref per row", len(refs) == 2)
    check("one marked HTML node per row", len(html) == 2
          and all('class="stanza-message"' in item for item in html))
    check("the unread divider is not baked in",
          all("stanza-unread" not in item for item in html))
    check("sender/body are rendered", "hello" in html[0] and "Bob" in html[0])

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All prepared-chat tests passed.")
