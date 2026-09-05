"""Chat window — hosts all conversation tabs.

Supports two modes:
- Standalone mode (separate QMainWindow, default)
- Embedded mode (QWidget placed inside MainWindow's splitter)
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from jabbim.include.constants import APP_NAME
from jabbim.ui.chat_widget import ChatWidget
from jabbim.ui.chat_themes import ChatThemeFactory


class _TabBar(QtWidgets.QTabBar):
    """Custom tab bar with middle-click close and mouse-wheel tab cycling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setExpanding(False)
        self.setTabsClosable(True)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            idx = self.tabAt(event.position().toPoint())
            if idx >= 0:
                self.tabCloseRequested.emit(idx)
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        idx = self.currentIndex()
        count = self.count()
        if count == 0:
            return
        if delta > 0:
            self.setCurrentIndex((idx - 1) % count)
        else:
            self.setCurrentIndex((idx + 1) % count)


class ChatWindow(QtWidgets.QMainWindow):
    """Window containing all chat tabs.

    In standalone mode this is a separate window.  In embedded mode it
    would be a plain QWidget (subclassed here for compatibility).
    """

    def __init__(self, theme_factory: ChatThemeFactory, parent=None):
        super().__init__(parent)
        self._theme = theme_factory
        self._tabs: dict[str, ChatWidget] = {}  # jid -> widget
        self._tab_order: list[str] = []         # ordered jid list

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(500, 400)

        # Central widget with tab widget
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tab_widget = QtWidgets.QTabWidget()
        self._tab_widget.setTabBar(_TabBar())
        self._tab_widget.setTabsClosable(True)
        self._tab_widget.tabCloseRequested.connect(self._close_tab)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tab_widget)

        self._install_shortcuts()

    def _install_shortcuts(self):
        """Ctrl+1..9 jump to a tab, Ctrl+W closes the current tab."""
        for i in range(1, 10):
            QtGui.QShortcut(QtGui.QKeySequence(f"Ctrl+{i}"), self,
                            activated=lambda i=i: self._goto_tab(i - 1))
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+W"), self,
                        activated=self._close_current_tab)

    def _goto_tab(self, index: int):
        if 0 <= index < self._tab_widget.count():
            self._tab_widget.setCurrentIndex(index)

    def _close_current_tab(self):
        idx = self._tab_widget.currentIndex()
        if idx >= 0:
            self._close_tab(idx)

    # ── Public API ────────────────────────────────────────────────

    def open_chat(self, jid: str, display_name: str,
                  focus: bool = True) -> ChatWidget:
        """Open (or focus) a 1-on-1 chat tab for *jid*."""
        if jid in self._tabs:
            if focus:
                self._focus_tab(jid)
            return self._tabs[jid]

        widget = ChatWidget(jid, display_name, self._theme)
        widget.message_sent.connect(self._on_message_sent)
        widget.typing_changed.connect(self.typing_changed)
        idx = self._tab_widget.addTab(widget, display_name)
        self._tab_widget.setTabToolTip(idx, jid)
        self._tabs[jid] = widget
        self._tab_order.append(jid)
        if focus:
            self._tab_widget.setCurrentIndex(idx)
            self.show()
            self.raise_()
            self.activateWindow()
            self._update_title()
            widget.focus_input()
        return widget

    def open_groupchat(self, room: str, nick: str, display_name: str) -> ChatWidget:
        """Open (or focus) a MUC chat tab."""
        if room in self._tabs:
            self._focus_tab(room)
            return self._tabs[room]

        widget = ChatWidget(room, display_name, self._theme, is_muc=True)
        widget.message_sent.connect(self._on_groupchat_message_sent)
        widget.typing_changed.connect(self.typing_changed)
        idx = self._tab_widget.addTab(widget, f"🔒 {display_name}")
        self._tab_widget.setTabToolTip(idx, room)
        self._tabs[room] = widget
        self._tab_order.append(room)
        self._tab_widget.setCurrentIndex(idx)
        self.show()
        self.raise_()
        self.activateWindow()
        self._update_title()
        widget.focus_input()
        return widget

    def get_chat(self, jid: str) -> ChatWidget | None:
        return self._tabs.get(jid)

    def close_chat(self, jid: str) -> None:
        if jid in self._tabs:
            idx = self._tab_widget.indexOf(self._tabs[jid])
            if idx >= 0:
                self._tab_widget.removeTab(idx)
            del self._tabs[jid]
            self._tab_order = [j for j in self._tab_order if j != jid]
        if not self._tabs:
            self.hide()
        self._update_title()

    def has_chat(self, jid: str) -> bool:
        return jid in self._tabs

    def reload_themes(self, variant: str = ""):
        """Re-apply the chat theme variant to all open tabs."""
        for widget in self._tabs.values():
            widget.reload_theme(variant)

    def set_show_avatars(self, show: bool):
        for widget in self._tabs.values():
            widget.set_show_avatars(show)

    def tab_count(self) -> int:
        return len(self._tabs)

    def current_jid(self) -> str | None:
        w = self._tab_widget.currentWidget()
        if isinstance(w, ChatWidget):
            return w.jid
        return None

    def _update_title(self):
        """Title reflects the currently active chat."""
        w = self._tab_widget.currentWidget()
        if isinstance(w, ChatWidget) and w.display_name:
            self.setWindowTitle(w.display_name)
        else:
            self.setWindowTitle(APP_NAME)

    # ── Signals ───────────────────────────────────────────────────

    message_to_send = QtCore.pyqtSignal(str, str)       # jid, body
    groupchat_message_to_send = QtCore.pyqtSignal(str, str)  # room, body
    tab_focused = QtCore.pyqtSignal(str)                # jid became current
    tab_closed = QtCore.pyqtSignal(str)                 # a 1-on-1 tab closed
    muc_leave_requested = QtCore.pyqtSignal(str)        # room closed → leave
    typing_changed = QtCore.pyqtSignal(str, bool)       # jid, is_typing

    # ── Internal ──────────────────────────────────────────────────

    def _close_tab(self, index: int):
        widget = self._tab_widget.widget(index)
        if isinstance(widget, ChatWidget):
            if widget.is_muc:
                self.muc_leave_requested.emit(widget.jid)
            else:
                self.tab_closed.emit(widget.jid)
            self.close_chat(widget.jid)

    def _on_tab_changed(self, index: int):
        widget = self._tab_widget.currentWidget()
        if isinstance(widget, ChatWidget):
            widget.focus_input()
            self.tab_focused.emit(widget.jid)
        self._update_title()

    def _focus_tab(self, jid: str):
        widget = self._tabs.get(jid)
        if widget:
            idx = self._tab_widget.indexOf(widget)
            if idx >= 0:
                self._tab_widget.setCurrentIndex(idx)
            self.show()
            self.raise_()

    def _on_message_sent(self, jid: str, body: str):
        self.message_to_send.emit(jid, body)

    def _on_groupchat_message_sent(self, room: str, body: str):
        self.groupchat_message_to_send.emit(room, body)
