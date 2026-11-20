"""Regression checks for returning composer focus after a chat link click.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_link_focus.py
"""
import inspect
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.ui.chat_widget import ChatWidget  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


open_src = inspect.getsource(ChatWidget._open_link)
handle_src = inspect.getsource(ChatWidget._handle_link)
restore_src = inspect.getsource(ChatWidget._restore_input_focus)
check("every link click schedules a focus restore",
      "_focus_input_after_link()" in open_src)
check("an external link focuses the composer before the browser",
      "inp.setFocus()" in handle_src
      and "webbrowser.open(url)" in handle_src)
check("a link-created dialog keeps its focus",
      "activeModalWidget" in restore_src
      and "QDialog" in restore_src)
check("returning from the browser reuses the pending focus flag",
      "_pending_link_focus" in restore_src)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All link-focus tests passed.")
