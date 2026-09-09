"""Chat window — hosts all conversation tabs.

Supports two modes:
- Standalone mode (separate QMainWindow, default)
- Embedded mode (QWidget placed inside MainWindow's splitter)
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.include.constants import APP_NAME
from stanza_im.i18n import tr
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.chat_themes import ChatThemeFactory


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

    def __init__(self, theme_factory: ChatThemeFactory,
                 muc_theme_factory: ChatThemeFactory | None = None, parent=None):
        super().__init__(parent)
        self._theme = theme_factory
        self._muc_theme = muc_theme_factory or theme_factory
        self._tabs: dict[str, ChatWidget] = {}  # jid -> widget
        self._tab_order: list[str] = []         # ordered jid list
        self._tab_title_length = 30
        self._active_jid: str | None = None
        self._remote_activity: dict[str, str] = {}
        self._chat_options = {}
        self._muc_leave_confirm: Callable[[str], bool] | None = None

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
        QtGui.QShortcut(QtGui.QKeySequence("Esc"), self,
                        activated=self._on_escape)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+PgUp"), self,
                        activated=lambda: self._cycle_tab(-1))
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+PgDown"), self,
                        activated=lambda: self._cycle_tab(1))

    def _cycle_tab(self, step: int):
        count = self._tab_widget.count()
        if count > 1:
            self._tab_widget.setCurrentIndex(
                (self._tab_widget.currentIndex() + step) % count)

    def _goto_tab(self, index: int):
        if 0 <= index < self._tab_widget.count():
            self._tab_widget.setCurrentIndex(index)

    def _close_current_tab(self):
        idx = self._tab_widget.currentIndex()
        if idx >= 0:
            self._close_tab(idx)

    def _on_escape(self):
        widget = self._tab_widget.currentWidget()
        if isinstance(widget, ChatWidget) and widget.is_muc:
            self.hide()
            return
        self._close_current_tab()

    # ── Public API ────────────────────────────────────────────────

    def open_chat(self, jid: str, display_name: str,
                  focus: bool = True) -> ChatWidget:
        """Open (or focus) a 1-on-1 chat tab for *jid*."""
        if not isinstance(jid, str) or not jid.strip():
            raise ValueError("A chat target JID is required")
        jid = jid.strip()
        if jid in self._tabs:
            if focus:
                self._focus_tab(jid)
            return self._tabs[jid]

        widget = ChatWidget(jid, display_name, self._theme)
        widget.set_chat_options(self._chat_options)
        widget.message_sent.connect(self._on_message_sent)
        widget.typing_changed.connect(self.typing_changed)
        widget.clear_history_requested.connect(self.clear_history_requested)
        widget.server_history_requested.connect(self.server_history_requested)
        widget.bookmark_toggled.connect(self.bookmark_toggled)
        widget.set_subject_requested.connect(self.set_subject_requested)
        widget.participant_clicked.connect(self.participant_clicked)
        widget.participant_context_requested.connect(
            self.participant_context_requested)
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

        widget = ChatWidget(room, display_name, self._muc_theme, is_muc=True)
        widget.set_chat_options(self._chat_options)
        widget.message_sent.connect(self._on_groupchat_message_sent)
        widget.typing_changed.connect(self.typing_changed)
        widget.clear_history_requested.connect(self.clear_history_requested)
        widget.server_history_requested.connect(self.server_history_requested)
        widget.bookmark_toggled.connect(self.bookmark_toggled)
        widget.set_subject_requested.connect(self.set_subject_requested)
        widget.participant_clicked.connect(self.participant_clicked)
        widget.participant_context_requested.connect(
            self.participant_context_requested)
        idx = self._tab_widget.addTab(widget, self._tab_caption(widget))
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
        self._remote_activity.pop(jid, None)
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

    def reload_themes(self, variant: str = "", muc_variant: str | None = None):
        """Re-apply the chat theme variant to all open tabs."""
        self._theme.set_variant(variant)
        self._muc_theme.set_variant(muc_variant if muc_variant is not None else variant)
        for widget in self._tabs.values():
            if widget.is_muc and muc_variant is not None:
                widget.reload_theme(muc_variant)
            elif not widget.is_muc:
                widget.reload_theme(variant)

    def reload_emoticons(self, skin: str):
        self._theme.set_emoticon_skin(skin)
        self._muc_theme.set_emoticon_skin(skin)
        for widget in self._tabs.values():
            widget.reload_theme()

    def set_show_avatars(self, show: bool):
        for widget in self._tabs.values():
            widget.set_show_avatars(show)

    def set_chat_options(self, options):
        self._chat_options = dict(options)
        for widget in self._tabs.values():
            widget.set_chat_options(options)

    def set_tab_title_length(self, length: int):
        self._tab_title_length = max(10, int(length))
        for index in range(self._tab_widget.count()):
            widget = self._tab_widget.widget(index)
            if isinstance(widget, ChatWidget):
                self._tab_widget.setTabText(index, self._tab_caption(widget))

    def set_chat_title(self, jid: str, title: str):
        widget = self._tabs.get(jid)
        if not widget:
            return
        widget.display_name = title
        widget._name_label.setText(title)
        index = self._tab_widget.indexOf(widget)
        if index >= 0:
            self._tab_widget.setTabText(index, self._tab_caption(widget))
        self._update_title()

    def _tab_caption(self, widget: ChatWidget) -> str:
        title = widget.display_name
        prefix = "🔒 " if widget.is_muc else ""
        available = max(1, self._tab_title_length - len(prefix))
        if len(title) > available:
            title = title[:max(1, available - 1)] + "…"
        return prefix + title

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
            state = "" if w.is_muc else self._remote_activity.get(w.jid, "")
            suffix = "" if not state else f" ({state})"
            self.setWindowTitle(w.display_name + suffix)
        else:
            self.setWindowTitle(APP_NAME)

    def set_remote_activity(self, jid: str, state: str):
        widget = self._tabs.get(jid)
        if widget is not None and widget.is_muc:
            return
        if state in ("active", "inactive", "gone", "composing", "paused"):
            labels = {
                "active": tr("chat_activity_active"),
                "inactive": tr("chat_activity_inactive"),
                "composing": tr("chat_is_typing", name="").strip(),
                "paused": tr("chat_activity_inactive"),
                "gone": tr("chat_activity_gone"),
            }
            self._remote_activity[jid] = labels.get(state, state)
        if widget is not None:
            widget.set_status_text(tr("chat_activity_gone") if state == "gone" else "")
        self._update_title()

    # ── Signals ───────────────────────────────────────────────────

    message_to_send = QtCore.pyqtSignal(str, str)       # jid, body
    groupchat_message_to_send = QtCore.pyqtSignal(str, str)  # room, body
    tab_focused = QtCore.pyqtSignal(str)                # jid became current
    activity_changed = QtCore.pyqtSignal(str, str)      # jid, state
    tab_closed = QtCore.pyqtSignal(str)                 # a 1-on-1 tab closed
    muc_leave_requested = QtCore.pyqtSignal(str)        # room closed → leave
    typing_changed = QtCore.pyqtSignal(str, bool)       # jid, is_typing
    clear_history_requested = QtCore.pyqtSignal(str)    # jid
    server_history_requested = QtCore.pyqtSignal(str, str)  # jid, since
    bookmark_toggled = QtCore.pyqtSignal(str)               # MUC room
    set_subject_requested = QtCore.pyqtSignal(str)           # MUC room
    participant_clicked = QtCore.pyqtSignal(str, str)       # room, nick
    participant_context_requested = QtCore.pyqtSignal(
        str, str, QtCore.QPoint)

    # ── Internal ──────────────────────────────────────────────────

    def _close_tab(self, index: int):
        widget = self._tab_widget.widget(index)
        if isinstance(widget, ChatWidget):
            if widget.is_muc:
                if self._muc_leave_confirm and not self._muc_leave_confirm(
                        widget.jid):
                    return
                self.muc_leave_requested.emit(widget.jid)
            else:
                self.activity_changed.emit(widget.jid, "gone")
                self.tab_closed.emit(widget.jid)
            self.close_chat(widget.jid)

    def set_muc_leave_confirm(self, callback) -> None:
        """Let the owner veto closing a MUC tab (``callback(room) -> bool``)."""
        self._muc_leave_confirm = callback

    def _on_tab_changed(self, index: int):
        previous = self._active_jid
        current = None
        widget = self._tab_widget.currentWidget()
        if isinstance(widget, ChatWidget):
            current = widget.jid
            widget.focus_input()
            self.tab_focused.emit(widget.jid)
        previous_widget = self._tabs.get(previous) if previous else None
        current_widget = self._tabs.get(current) if current else None
        if (previous and previous != current and previous_widget
                and not previous_widget.is_muc):
            self.activity_changed.emit(previous, "inactive")
        if (current and current != previous and current_widget
                and not current_widget.is_muc):
            self.activity_changed.emit(current, "active")
        self._active_jid = current
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
