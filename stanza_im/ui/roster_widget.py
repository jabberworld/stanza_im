"""Custom-painted roster widget (QPainter-based, no QTreeView)."""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.ui import tooltip as tooltip_mod
from stanza_im.ui.roster_style import RosterStyle, GroupItem, UserItem


class RosterWidget(QtWidgets.QWidget):
    """A fully custom-painted contact list.

    Renders groups and contacts using QPainter.  Supports:
    - Expand/collapse groups
    - Click, double-click, context menu
    - Keyboard navigation
    - Drag-and-drop (planned)
    - Dynamic item heights
    """

    contact_clicked = QtCore.pyqtSignal(str)         # jid
    contact_double_clicked = QtCore.pyqtSignal(str)   # jid
    contact_context_menu = QtCore.pyqtSignal(str, QtCore.QPoint)  # jid, global_pos

    def __init__(self, parent=None):
        super().__init__(parent)
        self._style = RosterStyle()
        self._groups: dict[str, GroupItem] = {}
        self._users: list[UserItem] = []
        self._sorted_groups: list[str] = []
        self._sorted_users: dict[str, list[UserItem]] = {}
        self._trailing_groups: set[str] = set()
        self._selected_jid: str | None = None
        self._hover_jid: str | None = None
        self._search_text: str = ""
        self._filter: str = ""
        self._show_offline = True

        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._tooltip_provider = None

    # ── Public API ────────────────────────────────────────────────

    def set_style(self, style: RosterStyle) -> None:
        self._style = style
        self._recalc_heights()
        self.update()

    def set_tooltip_provider(self, provider) -> None:
        """Set a callable ``(jid) -> (html, avatar_path|None)`` used for
        contact tooltips (default: no tooltips)."""
        self._tooltip_provider = provider

    def _group_sort_key(self, name: str):
        """Sort contact groups alphabetically, trailing groups last."""
        return (name in self._trailing_groups, name.casefold())

    def set_trailing_groups(self, names) -> None:
        """Groups (e.g. conferences) that always sort after the rest."""
        self._trailing_groups = set(names or ())
        self._sorted_groups.sort(key=self._group_sort_key)
        self.update()

    def add_group(self, name: str) -> GroupItem:
        if name not in self._groups:
            item = GroupItem(name=name)
            self._groups[name] = item
            self._sorted_groups.append(name)
            self._sorted_groups.sort(key=self._group_sort_key)
        return self._groups[name]

    def add_user(self, user: UserItem) -> None:
        self._users.append(user)
        self.add_group(user.group)
        self._sorted_users.setdefault(user.group, []).append(user)
        self._recalc_heights()
        self.update()

    def update_user(self, jid: str, **kwargs) -> None:
        for user in self._users:
            if user.jid == jid:
                for k, v in kwargs.items():
                    if hasattr(user, k):
                        setattr(user, k, v)
                self._recalc_heights()
                self.update()
                return

    def remove_user(self, jid: str) -> None:
        self._users = [u for u in self._users if u.jid != jid]
        self._rebuild_sorted()
        self._recalc_heights()
        self.update()

    def clear(self) -> None:
        self._groups.clear()
        self._users.clear()
        self._sorted_groups.clear()
        self._sorted_users.clear()
        self._selected_jid = None
        self.update()

    def set_search_filter(self, text: str) -> None:
        self._filter = text.lower()
        self._recalc_heights()
        self.update()

    def set_show_offline(self, value: bool) -> None:
        """Show or hide contacts whose current presence is offline."""
        self._show_offline = value
        self._recalc_heights()
        self.update()

    def sort_and_update(self) -> None:
        self._rebuild_sorted()
        self._recalc_heights()
        self.update()

    # ── Geometry helpers ──────────────────────────────────────────

    def _rebuild_sorted(self) -> None:
        self._sorted_users.clear()
        for user in self._users:
            self._sorted_users.setdefault(user.group, []).append(user)
        for group in self._sorted_users:
            self._sorted_users[group].sort(key=lambda u: u.name.casefold())

    def _visible_items(self) -> list[tuple[str, GroupItem | UserItem]]:
        """Return the list of items currently visible (respecting group
        expansion and search filter)."""
        result: list[tuple[str, GroupItem | UserItem]] = []
        for group_name in self._sorted_groups:
            group = self._groups[group_name]
            users = self._sorted_users.get(group_name, [])

            if not self._show_offline:
                users = [u for u in users if u.status != "offline"]

            if self._filter:
                users = [u for u in users if self._filter in u.name.lower()
                         or self._filter in u.jid.lower()]
                if not users:
                    continue

            result.append(("group", group))
            if group.expanded:
                for user in users:
                    result.append(("user", user))
        return result

    def _total_height(self) -> int:
        h = 0
        for kind, item in self._visible_items():
            if kind == "group":
                h += self._style.group_height()
            else:
                h += self._style.user_height(item)
        return h

    def _item_rect(self, index: int) -> QtCore.QRect:
        y = 0
        for i, (kind, item) in enumerate(self._visible_items()):
            h = self._style.group_height() if kind == "group" else self._style.user_height(item)
            if i == index:
                return QtCore.QRect(0, y, self.width(), h)
            y += h
        return QtCore.QRect(0, y, self.width(), 0)

    def _item_at(self, y: int) -> tuple[str, GroupItem | UserItem] | None:
        cy = 0
        for kind, item in self._visible_items():
            h = self._style.group_height() if kind == "group" else self._style.user_height(item)
            if cy <= y < cy + h:
                return (kind, item)
            cy += h
        return None

    def _item_index_at(self, y: int) -> int:
        cy = 0
        for i, (kind, item) in enumerate(self._visible_items()):
            h = self._style.group_height() if kind == "group" else self._style.user_height(item)
            if cy <= y < cy + h:
                return i
            cy += h
        return -1

    def _recalc_heights(self) -> None:
        h = self._total_height()
        self.setMinimumHeight(h)
        self.setMaximumHeight(16777215)
        self.updateGeometry()

    def _visible_user_jids(self) -> list[str]:
        """JIDs of users currently visible (group expansion + search filter)."""
        jids: list[str] = []
        for group_name in self._sorted_groups:
            group = self._groups[group_name]
            if not group.expanded:
                continue
            users = self._sorted_users.get(group_name, [])
            if not self._show_offline:
                users = [u for u in users if u.status != "offline"]
            if self._filter:
                users = [u for u in users if self._filter in u.name.lower()
                         or self._filter in u.jid.lower()]
            for user in users:
                jids.append(user.jid)
        return jids

    def _select_jid(self, jid: str) -> None:
        self._selected_jid = jid
        self.update()
        self._scroll_to_jid(jid)

    def _scroll_to_jid(self, jid: str) -> None:
        """Best-effort: scroll the enclosing QScrollArea to reveal *jid*."""
        idx = next((i for i, (kind, item) in enumerate(self._visible_items())
                    if kind == "user" and item.jid == jid), -1)
        if idx < 0:
            return
        rect = self._item_rect(idx)
        scroll = self.parentWidget()
        while scroll is not None and not isinstance(scroll, QtWidgets.QScrollArea):
            scroll = scroll.parentWidget()
        if scroll is not None:
            scroll.verticalScrollBar().setValue(rect.y())

    # ── QWidget overrides ─────────────────────────────────────────

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(200, self._total_height())

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)

        dirty = event.rect()
        painter.fillRect(dirty, self._style.bg_color()
                         or QtGui.QColor(QtCore.Qt.GlobalColor.white))
        cy = 0
        for kind, item in self._visible_items():
            if kind == "group":
                h = self._style.group_height()
                rect = QtCore.QRect(0, cy, self.width(), h)
                if rect.intersects(dirty):
                    self._style.paint_group(painter, item, rect, False)
                cy += h
            else:
                h = self._style.user_height(item)
                rect = QtCore.QRect(0, cy, self.width(), h)
                if rect.intersects(dirty):
                    is_sel = (item.jid == self._selected_jid)
                    self._style.paint_user(painter, item, rect, is_sel)
                cy += h

        painter.end()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        tooltip_mod.hide()
        hit = self._item_at(int(event.position().y()))
        if hit is None:
            self._selected_jid = None
            self.update()
            return
        kind, item = hit
        if kind == "group":
            item.expanded = not item.expanded
            self._recalc_heights()
            self.update()
        elif kind == "user":
            self._selected_jid = item.jid
            self.update()
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                self.contact_clicked.emit(item.jid)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        tooltip_mod.hide()
        hit = self._item_at(int(event.position().y()))
        if hit and hit[0] == "user":
            self.contact_double_clicked.emit(hit[1].jid)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        hit = self._item_at(int(event.position().y()))
        if hit is not None and hit[0] == "user":
            jid = hit[1].jid
            if jid != self._hover_jid:
                self._hover_jid = jid
                tooltip_mod.hide()
                if self._tooltip_provider is not None:
                    html, avatar = self._tooltip_provider(jid)
                    if html:
                        tooltip_mod.show(event.globalPosition().toPoint(),
                                         html, avatar)
        elif self._hover_jid is not None:
            self._hover_jid = None
            tooltip_mod.hide()

    def leaveEvent(self, event) -> None:
        self._hover_jid = None
        tooltip_mod.hide()
        super().leaveEvent(event)

    def hideEvent(self, event) -> None:
        tooltip_mod.hide()
        super().hideEvent(event)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        hit = self._item_at(event.pos().y())
        if hit and hit[0] == "user":
            self.contact_context_menu.emit(hit[1].jid, event.globalPos())

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace) and self._selected_jid:
            self.contact_context_menu.emit(
                self._selected_jid, self.mapToGlobal(QtCore.QPoint(self.width() // 2, 0))
            )
        elif key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            if self._selected_jid:
                self.contact_double_clicked.emit(self._selected_jid)
        elif key in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down,
                     QtCore.Qt.Key.Key_Home, QtCore.Qt.Key.Key_End):
            self._move_selection(key)
        else:
            super().keyPressEvent(event)

    def _move_selection(self, key: QtCore.Qt.Key) -> None:
        jids = self._visible_user_jids()
        if not jids:
            return
        current = self._selected_jid
        idx = jids.index(current) if current in jids else -1
        if key == QtCore.Qt.Key.Key_Up:
            idx = idx - 1 if idx > 0 else 0
        elif key == QtCore.Qt.Key.Key_Down:
            idx = idx + 1 if 0 <= idx < len(jids) - 1 else (0 if idx < 0 else idx)
        elif key == QtCore.Qt.Key.Key_Home:
            idx = 0
        elif key == QtCore.Qt.Key.Key_End:
            idx = len(jids) - 1
        self._select_jid(jids[idx])
