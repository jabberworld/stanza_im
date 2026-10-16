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

    The popup is placed on the side of the button with **more room** (above the
    button's top edge, or below its bottom edge), so it stays adjacent to the
    button and does not cover it.  When the chosen side cannot fit the popup
    fully, the other side is used if it avoids the button; otherwise the popup
    is pushed to the far screen edge.  Horizontally it stays attached to the
    button — the left edges are aligned, and when that overflows the right edge
    of *area* the right edges are aligned instead — then clamped to *area*.
    """
    w = max(1, int(size.width()))
    h = max(1, int(size.height()))
    ax, ay = int(anchor.x()), int(anchor.y())
    aw, ah = int(anchor.width()), int(anchor.height())
    px = ax
    if not area.isValid():
        return QtCore.QPoint(px, ay - h)

    def _clamp_y(py: int) -> int:
        return max(area.top(), min(py, area.bottom() + 1 - h))

    above_py = _clamp_y(ay - h)
    below_py = _clamp_y(ay + ah)

    def _covers(py: int) -> bool:
        return py < ay + ah and py + h > ay

    room_above = ay - area.top()
    room_below = area.bottom() + 1 - (ay + ah)
    if room_above >= room_below:
        py = above_py
        if _covers(py) and not _covers(below_py):
            py = below_py
    else:
        py = below_py
        if _covers(py) and not _covers(above_py):
            py = above_py

    # Horizontal: align left edges; if it overflows, align right edges.
    if px + w > area.right() + 1:
        px = ax + aw - w
    px = max(area.left(), min(px, area.right() + 1 - w))
    return QtCore.QPoint(int(px), int(py))
