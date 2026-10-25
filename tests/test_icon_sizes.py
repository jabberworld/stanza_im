"""Icon source selection: SVG first, then the nearest raster size for DPR.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_icon_sizes.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_icons_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.include.constants import (  # noqa: E402
    find_icon, find_icon_sized)
from stanza_im.ui.icons import IconCache  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


check("a 1x 16 px icon uses the 16 px source",
      find_icon_sized("system-users.png", 16, 1).endswith(
          "16x16/categories/system-users.png"))
check("a 2x 16 px icon uses the 32 px source",
      find_icon_sized("system-users.png", 16, 2).endswith(
          "32x32/categories/system-users.png"))
check("a 24 px target picks the 32 px source",
      find_icon_sized("system-users.png", 24, 1).endswith(
          "32x32/categories/system-users.png"))
check("SVG wins at any DPR",
      find_icon_sized("info.svg", 16, 2).endswith(
          "scalable/actions/info.svg"))
check("a 32 px action source is used on a 2x screen",
      find_icon_sized("clear.png", 16, 2).endswith(
          "32x32/actions/clear.png"))
check("a 1x action keeps its 16 px source",
      find_icon_sized("clear.png", 16, 1).endswith(
          "16x16/actions/clear.png"))
check("legacy find_icon prefers the larger action source",
      find_icon("clear.png").endswith("32x32/actions/clear.png"))
check("an unknown icon resolves to an empty path",
      find_icon_sized("does-not-exist.png", 16) == "")

cache = IconCache()
check("a 32 px category icon is rendered at 32 px",
      cache.get_category_icon("system-users.png", 32).width() == 32)
check("a scalable icon is rendered at the requested size",
      cache.get_category_icon("info.svg", 20).width() == 20)
check("get_icon returns a valid icon",
      not cache.get_icon("clear.png", 16).isNull())
check("get_icon_pixmap returns a valid pixmap",
      not cache.get_icon_pixmap("clear.png", 16).isNull())

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All icon-size tests passed.")
