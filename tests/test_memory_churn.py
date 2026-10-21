"""Tests for the UI-side memory churn fixes (scroll poll, pixmap caches).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_memory_churn.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_churn_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_view, icons as icons_mod, roster_style

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. the chat scroll poll pauses while the application is inactive ----------
_Active = QtCore.Qt.ApplicationState.ApplicationActive
_Inactive = QtCore.Qt.ApplicationState.ApplicationInactive
_Suspended = QtCore.Qt.ApplicationState.ApplicationSuspended
check("the poll runs while the application is active",
      chat_view.poll_allowed(_Active))
check("the poll pauses while the application is inactive",
      not chat_view.poll_allowed(_Inactive)
      and not chat_view.poll_allowed(_Suspended))
check("only the active state runs the poll",
      not chat_view.poll_allowed(object()))

_source = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "stanza_im", "ui", "chat_view.py"),
    encoding="utf-8").read()
_poll = _source.split("def _poll_scroll_position", 1)[1][:500]
check("the scroll poll checks the application state",
      "poll_allowed(" in _poll and "applicationState()" in _poll)


# 2. the roster renderer caches its scaled/rounded pixmaps ------------------
style = roster_style.RosterStyle()
_base = QtGui.QPixmap(64, 64)
_base.fill(QtGui.QColor("#3366cc"))

calls = {"n": 0}
_orig_rounded = roster_style.rounded_avatar


def _counting_rounded(pix, size, radius):
    calls["n"] += 1
    return _orig_rounded(pix, size, radius)


roster_style.rounded_avatar = _counting_rounded
try:
    first = style._scaled(("avatar", "a.png"), _base, 24, 20)
    second = style._scaled(("avatar", "a.png"), _base, 24, 20)
    check("a scaled avatar is cached",
          calls["n"] == 1 and first is second)
    style._scaled(("avatar", "a.png"), _base, 24, 50)
    check("a different radius bypasses the cache", calls["n"] == 2)
    style.clear_pixmaps()
    style._scaled(("avatar", "a.png"), _base, 24, 50)
    check("clear_pixmaps drops the cached avatars", calls["n"] == 3)
finally:
    roster_style.rounded_avatar = _orig_rounded

_status_a = style._scaled(("status", "online"), _base, 24)
_status_b = style._scaled(("status", "online"), _base, 24)
check("a scaled status icon is cached", _status_a is _status_b)
check("different icon keys do not share a pixmap",
      style._scaled(("status", "away"), _base, 24) is not _status_a)


# 3. the icon cache is bigger and does not expire icons by time -------------
cache = icons_mod.IconCache()
check("the icon cache holds at least 512 files", cache._max_size >= 512)
check("the icon cache has no TTL by default", cache._stale_ttl <= 0)

_icon_path = os.path.join(_SCRATCH, "icon.png")
_base.save(_icon_path, "PNG")
_first = cache.get(_icon_path)
check("a cached icon is returned unchanged",
      not _first.isNull() and cache.get(_icon_path) is _first)
cache._evict_stale()
check("the stale check keeps entries with the TTL off",
      cache.get(_icon_path) is _first)
cache.forget(_icon_path)
check("forget drops a single entry", _icon_path not in cache._cache)
check("the entry is reloaded after forget",
      not cache.get(_icon_path).isNull())


# 4. an avatar update invalidates both caches ------------------------------
_main = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "stanza_im", "ui", "main_window.py"),
    encoding="utf-8").read()
_refresh = _main.split("def _refresh_avatar", 1)[1][:800]
check("an avatar update forgets the cached file",
      "icons_mod.icons.forget(path)" in _refresh)
check("an avatar update clears the roster pixmaps",
      "clear_pixmaps()" in _refresh)


# 5. the roster forwards the invalidation to its renderer ------------------
from stanza_im.ui.roster_widget import RosterWidget

roster = RosterWidget()
_roster_style = roster._style
_roster_style._pixmaps[("avatar", "x")] = _base
roster.clear_pixmaps()
check("the roster clears the renderer's pixmap cache",
      not _roster_style._pixmaps)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All memory-churn tests passed.")
