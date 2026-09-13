"""Roster style — QPainter-based rendering of roster items.

This is the pluggable rendering strategy for the roster widget.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.ui import icons as icons_mod


@dataclass
class GroupItem:
    """A roster group (expandable section)."""
    name: str
    expanded: bool = True
    online_count: int = 0
    total_count: int = 0
    single_count: bool = False
    height: int = 24


@dataclass
class UserItem:
    """A single contact in the roster."""
    jid: str
    name: str
    group: str
    status: str = "offline"
    status_message: str = ""
    icon_key: str = "offline"
    avatar_path: str | None = None
    is_hidden: bool = False
    unread_count: int = 0
    mood: str = ""
    meta_parent_jid: str | None = None
    meta_children: list | None = None

    def __post_init__(self):
        if self.meta_children is None:
            self.meta_children = []


class RosterStyle:
    """Default QPainter roster renderer.

    Draws group headers and user items with avatar, name, status icon and
    status message.  The height of user items is dynamic: taller when a
    status message is present.

    Background colors are configurable via :meth:`set_colors`; unset values
    fall back to the previous behavior (white widget fill, palette ``Window``
    group stripe).
    """

    GROUP_HEIGHT = 26
    USER_HEIGHT_SHORT = 32
    USER_HEIGHT_TALL = 52
    ICON_SIZE = 16
    STATUS_ICON_DRAW = 24        # rendered status icon size (source 32x32)
    AVATAR_SIZE = 24
    MARGIN_LEFT = 6
    STATUS_MSG_MAX_WIDTH = 180

    def __init__(self, bg_color: str = "", group_bg_color: str = ""):
        self._bg_color: QtGui.QColor | None = None
        self._group_bg_color: QtGui.QColor | None = None
        self.set_colors(bg_color, group_bg_color)

    @staticmethod
    def _parse(value) -> QtGui.QColor | None:
        color = QtGui.QColor(str(value or ""))
        return color if color.isValid() else None

    def set_colors(self, bg_color: str = "", group_bg_color: str = "") -> None:
        """Configure the roster background and group-stripe colors."""
        self._bg_color = self._parse(bg_color)
        self._group_bg_color = self._parse(group_bg_color)

    def bg_color(self) -> QtGui.QColor | None:
        """The roster background color (None = keep the previous white)."""
        return self._bg_color

    def group_bg_color(self) -> QtGui.QColor | None:
        """The group-stripe color (None = keep the palette ``Window``)."""
        return self._group_bg_color

    def _palette(self) -> QtGui.QPalette:
        """Return the application default palette (available without a widget)."""
        return QtWidgets.QApplication.palette()

    def user_height(self, item: UserItem) -> int:
        if item.status_message:
            return self.USER_HEIGHT_TALL
        return self.USER_HEIGHT_SHORT

    def group_height(self) -> int:
        return self.GROUP_HEIGHT

    def paint_group(self, painter: QtGui.QPainter, item: GroupItem,
                    rect: QtCore.QRect, is_selected: bool) -> None:
        """Draw a group header stripe."""
        painter.save()

        pal = self._palette()

        # Background stripe
        bg = self._group_bg_color or pal.color(QtGui.QPalette.ColorRole.Window)
        painter.fillRect(rect, bg)

        # Expand/collapse arrow
        arrow_x = rect.left() + 4
        arrow_y = rect.top() + rect.height() // 2
        if item.expanded:
            points = [
                QtCore.QPoint(arrow_x, arrow_y - 3),
                QtCore.QPoint(arrow_x + 5, arrow_y - 3),
                QtCore.QPoint(arrow_x + 2, arrow_y + 2),
            ]
        else:
            points = [
                QtCore.QPoint(arrow_x, arrow_y - 3),
                QtCore.QPoint(arrow_x + 5, arrow_y),
                QtCore.QPoint(arrow_x, arrow_y + 3),
            ]
        painter.setBrush(pal.color(QtGui.QPalette.ColorRole.Text))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawPolygon(QtGui.QPolygon(points))

        # Group name
        font = painter.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() - 1)
        painter.setFont(font)
        painter.setPen(pal.color(QtGui.QPalette.ColorRole.Text))
        text_rect = QtCore.QRect(rect.left() + 16, rect.top(),
                                 rect.width() - 16, rect.height())
        painter.drawText(text_rect,
                         QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
                         item.name)

        # Online/total count "(3/7)" on the right
        count_text = (str(item.total_count) if item.single_count
                      else f"({item.online_count}/{item.total_count})")
        painter.setPen(pal.color(QtGui.QPalette.ColorRole.Mid))
        count_rect = QtCore.QRect(rect.right() - 60, rect.top(),
                                  56, rect.height())
        painter.drawText(count_rect,
                         QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight,
                         count_text)

        painter.restore()

    def paint_user(self, painter: QtGui.QPainter, item: UserItem,
                   rect: QtCore.QRect, is_selected: bool) -> None:
        """Draw a contact row: status icon (left), name, status message and,
        when available, the vCard avatar (right)."""
        painter.save()

        pal = self._palette()

        # Selection highlight
        if is_selected:
            sel_bg = pal.color(QtGui.QPalette.ColorRole.Highlight)
            painter.fillRect(rect, sel_bg)
            text_color = pal.color(QtGui.QPalette.ColorRole.HighlightedText)
        else:
            text_color = pal.color(QtGui.QPalette.ColorRole.Text)

        x = rect.left() + self.MARGIN_LEFT
        y = rect.top()
        icon_y = y + (rect.height() - self.STATUS_ICON_DRAW) // 2

        # Status icon (always, left-aligned).  Source is 32x32, drawn at
        # STATUS_ICON_DRAW px.
        icons = icons_mod.icons
        if icons:
            status_pixmap = icons.get_status_icon(item.icon_key, "32x32")
            if not status_pixmap.isNull():
                scaled = status_pixmap.scaled(
                    self.STATUS_ICON_DRAW, self.STATUS_ICON_DRAW,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation)
                painter.drawPixmap(x, icon_y, scaled)

        # Text block (name + status message) between status icon and avatar.
        name_x = x + self.STATUS_ICON_DRAW + 8
        avail_right = rect.right() - 8
        if item.avatar_path and icons:
            ipix = icons.get(item.avatar_path)
            if not ipix.isNull():
                scaled = ipix.scaled(self.AVATAR_SIZE, self.AVATAR_SIZE,
                                     QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                     QtCore.Qt.TransformationMode.SmoothTransformation)
                ax = avail_right - self.AVATAR_SIZE
                ay = y + (rect.height() - self.AVATAR_SIZE) // 2
                painter.drawPixmap(ax, ay, scaled)
                avail_right -= self.AVATAR_SIZE + 6

        if item.unread_count > 0:
            badge_text = str(item.unread_count)
            badge_font = painter.font()
            badge_font.setBold(True)
            badge_font.setPointSize(8)
            painter.setFont(badge_font)
            badge_w = max(16, painter.fontMetrics().horizontalAdvance(badge_text) + 8)
            badge_rect = QtCore.QRect(avail_right - badge_w - 4,
                                      y + (rect.height() - 14) // 2,
                                      badge_w, 14)
            painter.setPen(QtCore.Qt.GlobalColor.white)
            painter.setBrush(QtGui.QColor(220, 50, 50))
            painter.drawRoundedRect(badge_rect, 7, 7)
            painter.drawText(badge_rect, QtCore.Qt.AlignmentFlag.AlignCenter, badge_text)
            avail_right -= badge_w + 6

        name_rect = QtCore.QRect(name_x, y + 2, avail_right - name_x, 16)
        painter.setPen(text_color)
        display_name = item.name if item.name else item.jid
        painter.drawText(name_rect,
                         QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
                         display_name)

        # Status message (if present): first line only, aligned to the bottom
        # edge of the status icon.
        first_line = (item.status_message.splitlines() or [""])[0]
        if first_line:
            painter.setPen(pal.color(QtGui.QPalette.ColorRole.Mid))
            sm_font = painter.font()
            sm_font.setItalic(True)
            sm_font.setPointSize(max(sm_font.pointSize() - 1, 7))
            painter.setFont(sm_font)
            fm = painter.fontMetrics()
            sm_top = icon_y + self.STATUS_ICON_DRAW - fm.height()
            sm_rect = QtCore.QRect(
                name_x, sm_top,
                min(self.STATUS_MSG_MAX_WIDTH, avail_right - name_x),
                fm.height())
            clipped = first_line[:40] + ("…" if len(first_line) > 40 else "")
            painter.drawText(sm_rect,
                             QtCore.Qt.AlignmentFlag.AlignTop
                             | QtCore.Qt.AlignmentFlag.AlignLeft,
                             clipped)

        painter.restore()
