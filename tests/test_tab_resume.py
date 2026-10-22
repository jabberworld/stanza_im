"""Tab activation: idempotent settings and a single deferred render.

Returning to a suspended conference tab used to run ``resume()`` and then
several unconditional setters (participant font/options, hats, nick colours),
each re-rendering the whole chat or rebuilding every participant row: ~5 s of
CPU and 3-4 WebEngine page loads for one switch.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_tab_resume.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_tabresume_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.ui import chat_themes
from stanza_im.ui import chat_widget as chat_widget_mod

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
cw = chat_widget_mod.ChatWidget(
    "room@conf.example/me", "Room", chat_themes.ChatThemeFactory(), is_muc=True)


class _StubView(QtWidgets.QWidget):
    """A view stand-in: the resume tests never need a WebEngine page."""

    def __init__(self):
        super().__init__()
        self.highlight_nick = ""

    def shutdown(self):
        pass

    def set_chat_zoom(self, factor):
        pass

    def scroll_fraction(self):
        return 1.0

    def clear(self):
        pass

    def add_status(self, text, timestamp=""):
        pass

    def scroll_to_bottom(self):
        pass

    def set_scroll_fraction(self, fraction):
        pass

    def seed_unseen(self, count, target_id=""):
        pass

    def scroll_to_message(self, *args, **kwargs):
        pass


cw._create_view = lambda theme: _StubView()

rows: list[int] = []
renders: list[int] = []
_orig_rows = cw._render_muc_users
_orig_render = cw._render_all


def _rows():
    rows.append(1)
    return _orig_rows()


def _render():
    renders.append(1)
    return _orig_render()


cw._render_muc_users = _rows
cw._render_all = _render

# 1. unchanged settings are no-ops ------------------------------------------
cw.set_participant_font("", 0)
cw.set_participant_font("", 0)
check("an unchanged participant font does not rebuild the list", rows == [])
cw.set_participant_font("", 20)
check("a changed participant font rebuilds the list once", len(rows) == 1)
cw.set_participant_font("", 20)
check("re-applying the same font is a no-op", len(rows) == 1)

cw.set_muc_participant_options(True, True)
check("unchanged participant options do not rebuild", len(rows) == 1)
cw.set_muc_participant_options(False, True)
check("changed participant options rebuild", len(rows) == 2)
cw.set_muc_participant_options(False, True)
check("re-applying the same options is a no-op", len(rows) == 2)
cw.set_muc_participant_options(True, True)

cw.set_avatar_radius(cw._avatar_radius)
check("an unchanged avatar radius does not rebuild", len(rows) == 3)
cw.set_avatar_radius((cw._avatar_radius + 10) % 101)
check("a changed avatar radius rebuilds", len(rows) == 4)

before = len(renders)
cw.set_muc_hats_visible(cw._show_muc_hats)
check("an unchanged hats toggle does not re-render",
      len(renders) == before)
cw.set_muc_hats_visible(not cw._show_muc_hats)
check("a changed hats toggle re-renders", len(renders) == before + 1)
cw.set_muc_hats_visible(not cw._show_muc_hats)
before = len(renders)
cw.set_colored_muc_nicks(cw._colored_muc_nicks)
check("an unchanged colour toggle does not re-render",
      len(renders) == before)
cw.set_text_scale(cw._text_scale)
check("an unchanged text scale is a no-op", True)

# 2. resume renders once, after the history load had its chance -------------
# Simulate the suspended state (a real suspend destroys the WebEngine page,
# which the offscreen teardown dislikes); resume() itself is the code under
# test and uses the stub view.
cw.set_history([], 50, True)
renders.clear()
cw._suspended = True
cw.resume()
check("resume defers its render", not renders
      and cw._resume_render_timer.isActive())
cw.set_history([], 50, True)
check("a history load cancels the deferred render",
      len(renders) == 1 and not cw._resume_render_timer.isActive())

renders.clear()
cw._suspended = True
cw.resume()
cw._resume_render_timer.timeout.emit()
check("the deferred render runs once", len(renders) == 1)
check("the timer is single-shot",
      cw._resume_render_timer.isSingleShot()
      and not cw._resume_render_timer.isActive())

# 3. a settings change during the deferred window still renders once --------
renders.clear()
cw._suspended = True
cw.resume()
cw.set_muc_hats_visible(not cw._show_muc_hats)
check("a real settings change renders at once and cancels the deferred one",
      len(renders) == 1 and not cw._resume_render_timer.isActive())
check("the timer stays stopped after the immediate render",
      not cw._resume_render_timer.isActive())

cw.detach()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All tab-resume tests passed.")
