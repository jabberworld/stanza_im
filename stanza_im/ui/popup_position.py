"""Pure geometry for anchoring a popup next to a button.

Shared by the XEP-0444 reaction picker and the unicode-smiley picker (both
open a ``Qt.Popup`` anchored to a chat button).  Kept dependency-light so the
placement math is unit-testable without building a chat window.
"""
from __future__ import annotations

from PyQt6 import QtCore


def popup_position(anchor: QtCore.QRect, size: QtCore.QSize,
                   area: QtCore.QRect) -> QtCore.QPoint:
    """Return the top-left for a popup anchored to *anchor* (a button).

    The popup is placed **above** the button (its bottom edge on the button's
    top edge); when it does not fit there it goes **below** the button's bottom
    edge, so the button is never covered.  Horizontally it stays attached to
    the button — the left edges are aligned, and when that would overflow the
    right edge of *area* the right edges are aligned instead — then the result
    is clamped to *area*.
    """
    w = max(1, int(size.width()))
    h = max(1, int(size.height()))
    ax, ay = int(anchor.x()), int(anchor.y())
    aw, ah = int(anchor.width()), int(anchor.height())
    px = ax
    py = ay - h
    if area.isValid():
        if py < area.top():
            py = ay + ah
        if px + w > area.right() + 1:
            px = ax + aw - w
        px = max(area.left(), min(px, area.right() + 1 - w))
        py = max(area.top(), min(py, area.bottom() + 1 - h))
    return QtCore.QPoint(int(px), int(py))
