"""Individual chat widget — one per conversation (1-on-1 or groupchat)."""
from __future__ import annotations

import webbrowser

from PyQt6 import QtCore, QtWidgets

from jabbim.i18n import tr
from jabbim.include.avatars import avatar_data_uri, default_avatar_uri
from jabbim.ui.chat_view import ChatView
from jabbim.ui.chat_themes import ChatThemeFactory

_TYPING_DEBOUNCE_MS = 2000


class ChatWidget(QtWidgets.QWidget):
    """A single chat tab's content: header info + message view + input bar."""

    message_sent = QtCore.pyqtSignal(str, str)  # jid, body
    typing_changed = QtCore.pyqtSignal(str, bool)  # jid, is_typing
    link_clicked = QtCore.pyqtSignal(str)

    def __init__(self, jid: str, display_name: str, theme: ChatThemeFactory,
                 is_muc: bool = False, parent=None):
        super().__init__(parent)
        self.jid = jid
        self.display_name = display_name
        self.is_muc = is_muc
        self._show_avatars = True
        self._last_sender: str = ""
        self._build_ui(theme)

    def _build_ui(self, theme: ChatThemeFactory):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Contact info header
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(4, 2, 4, 2)
        self._name_label = QtWidgets.QLabel(self.display_name)
        self._name_label.setStyleSheet("font-weight: bold;")
        self._status_label = QtWidgets.QLabel("")
        self._status_label.setStyleSheet("color: gray; font-size: 11px;")
        header.addWidget(self._name_label)
        header.addWidget(self._status_label)
        header.addStretch()
        layout.addLayout(header)

        # Chat view
        self._view = ChatView(theme)
        self._view.link_clicked.connect(self._open_link)
        self._view.link_clicked.connect(self.link_clicked)
        layout.addWidget(self._view, stretch=1)

        # Input area
        input_row = QtWidgets.QHBoxLayout()
        input_row.setContentsMargins(4, 2, 4, 2)
        self._input = QtWidgets.QPlainTextEdit()
        self._input.setMaximumHeight(60)
        self._input.setPlaceholderText(tr("chat_send"))
        self._input.installEventFilter(self)
        self._input.textChanged.connect(self._on_input_changed)
        input_row.addWidget(self._input, stretch=1)

        self._send_btn = QtWidgets.QPushButton(tr("chat_send"))
        self._send_btn.clicked.connect(self._send)
        input_row.addWidget(self._send_btn)
        layout.addLayout(input_row)

        self._typing_timer = QtCore.QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.setInterval(_TYPING_DEBOUNCE_MS)
        self._typing_timer.timeout.connect(self._typing_paused)

    def _open_link(self, url: str):
        webbrowser.open(url)

    def _on_input_changed(self):
        if self.is_muc:
            return
        if self._input.toPlainText().strip():
            if not self._typing_timer.isActive():
                self.typing_changed.emit(self.jid, True)
            self._typing_timer.start()
        else:
            self._typing_timer.stop()
            self.typing_changed.emit(self.jid, False)

    def _typing_paused(self):
        self.typing_changed.emit(self.jid, False)

    def eventFilter(self, obj, event):
        if obj is self._input and event.type() == QtCore.QEvent.Type.KeyPress:
            if (event.key() == QtCore.Qt.Key.Key_Return
                    and not event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier):
                self._send()
                return True
        return super().eventFilter(obj, event)

    def _send(self):
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._typing_timer.stop()
        self.typing_changed.emit(self.jid, False)
        self.message_sent.emit(self.jid, text)
        self._input.clear()

    def add_message(self, sender: str, body: str, timestamp: str,
                    direction: str = "incoming", is_next: bool = False):
        self._view.add_message(sender=sender, body=body, timestamp=timestamp,
                               direction=direction, is_next=is_next,
                               user_icon_path=self._user_icon(direction))
        self._last_sender = sender

    def _user_icon(self, direction: str) -> str:
        """Return a PNG data-URI for the sender avatar."""
        if not self._show_avatars:
            return ""
        if direction == "outgoing":
            return default_avatar_uri()
        return avatar_data_uri(self.jid) or default_avatar_uri()

    def set_show_avatars(self, show: bool):
        self._show_avatars = show

    def reload_theme(self, variant: str = ""):
        self._view.load_theme(variant)

    def add_status(self, text: str, timestamp: str):
        self._view.add_status(text, timestamp)

    def set_typing(self, name: str, is_typing: bool):
        if is_typing:
            self._status_label.setText(tr("chat_is_typing", name=name))
        else:
            self._status_label.setText("")

    def set_status_text(self, text: str):
        """Override the header status label (e.g. MUC participant count)."""
        self._status_label.setText(text)

    def clear_messages(self):
        self._view.clear()

    def focus_input(self):
        self._input.setFocus()
