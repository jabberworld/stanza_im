"""Branding: the scalable app logo is used by login/About, no old logo assets.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_branding.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_branding_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtGui, QtWidgets  # noqa: E402

from stanza_im.include.constants import (  # noqa: E402
    APP_ICON_SVG, PROJECT_ROOT)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


check("the scalable app logo exists", os.path.isfile(APP_ICON_SVG))
for size in (72, 96):
    pixmap = QtGui.QIcon(APP_ICON_SVG).pixmap(size, size)
    check(f"the logo renders at {size}px",
          not pixmap.isNull() and pixmap.width() == size)

root = os.path.join(PROJECT_ROOT, "stanza_im")
for rel in ("include/constants.py", "ui/login_widget.py",
            "ui/about_dialog.py"):
    with open(os.path.join(root, rel), encoding="utf-8") as handle:
        text = handle.read()
    check(f"{rel} uses APP_ICON_SVG", "APP_ICON_SVG" in text)
    check(f"{rel} has no LOGO_PNG/LOGO_SVG", "LOGO_PNG" not in text
          and "LOGO_SVG" not in text)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All branding tests passed.")
