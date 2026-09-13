"""Individual chat widget — one per conversation (1-on-1 or groupchat).

Renders a local history window (SQLite tail + live messages) inside the
chat view, grows it backwards on scroll-to-top or viewport growth, shows a
""load from server"" marker after the local history was cleared, and lists
MUC participants in a side panel.
"""
from __future__ import annotations

import asyncio
import tempfile
import time
import webbrowser
import logging
import os
import uuid
from urllib.parse import unquote

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import (
    ACTIONS_DIR_16, ACTIONS_DIR_22, CATEGORIES_DIR_16, STATUS_DIR_32,
    PLACES_DIR_22,
)
from stanza_im.include.avatars import (
    avatar_data_uri, avatar_file_data_uri, default_avatar, default_avatar_uri,
)
from stanza_im.ui.chat_view import ChatView
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.nick_colors import NickColorAllocator, normalize_nick
from stanza_im.ui import tooltip as tooltip_mod

logger = logging.getLogger(__name__)

_TYPING_DEBOUNCE_MS = 2000

_MUC_BADGES: dict[str, str] = {
    "owner": "~",
    "admin": "@",
    "member": "+",
}
_MUC_RANK: dict[str, int] = {
    "owner": 0,
    "admin": 1,
    "member": 2,
    "participant": 3,
    "visitor": 4,
    "none": 5,
    "": 5,
}
_SHOW_RANK: dict[str, int] = {
    "online": 0,
    "chat": 1,
    "dnd": 2,
    "away": 3,
    "xa": 4,
    "offline": 5,
    "unavailable": 5,
    "": 5,
}


def _ts_from_entry(entry: dict) -> str:
    """Extract a displayable HH:MM:SS from a stored ``YYYY-MM-DD...`` ts."""
    ts = entry.get("timestamp", "") or ""
    if isinstance(ts, str) and len(ts) >= 19 and ts[10] == "T":
        return ts[11:19]
    return ts


class _ParticipantRow(QtWidgets.QWidget):
    """A MUC participant row that reports hover/press so ChatWidget can show
    the rich custom tooltip (Qt tooltips are plain-text only).

    Child labels ignore mouse move events, which then propagate to this row.
    """

    def __init__(self, parent=None, on_hover=None, on_leave=None,
                 on_press=None):
        super().__init__(parent)
        self._on_hover = on_hover
        self._on_leave = on_leave
        self._on_press = on_press
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._on_hover is not None:
            self._on_hover(event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._on_press is not None:
            self._on_press()
        super().mousePressEvent(event)

    def leaveEvent(self, event) -> None:
        if self._on_leave is not None:
            self._on_leave()
        super().leaveEvent(event)


class _InputHandle(QtWidgets.QFrame):
    """Thin draggable bar above the chat input that resizes it vertically.

    The bar sits on the input's top edge, right below the button toolbar;
    dragging up grows the field, dragging down shrinks it.
    """

    height_changed = QtCore.pyqtSignal(int)

    def __init__(self, parent=None, get_height=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self.setCursor(QtCore.Qt.CursorShape.SizeVerCursor)
        self.setStyleSheet("_InputHandle { background: rgba(0, 0, 0, 0.05); }")
        self._get_height = get_height or (lambda: 60)
        self._press_y: float | None = None
        self._press_h = 60
        self.setMouseTracking(True)

    def _resized_height(self, dy: float) -> int:
        """New input height for a vertical drag delta *dy*.

        The handle moves the input's top edge, so a downward drag shifts the
        edge down and shrinks the field (negative delta grows it).
        """
        return int(self._press_h - dy)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press_y = float(event.globalPosition().y())
            self._press_h = int(self._get_height())
            self.grabMouse()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._press_y is None:
            return
        dy = float(event.globalPosition().y()) - self._press_y
        self.height_changed.emit(self._resized_height(dy))
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._press_y is not None:
            self.releaseMouse()
        self._press_y = None


class _SubjectEdit(QtWidgets.QLineEdit):
    """Read-only MUC subject field with the app's rich tooltip.

    The native QToolTip renders as a black block over the WebEngine surface,
    so hover/leave are forwarded to the custom tooltip popup instead.
    """

    def __init__(self, text, parent=None, on_hover=None, on_leave=None):
        super().__init__(text, parent)
        self._on_hover = on_hover
        self._on_leave = on_leave
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._on_hover is not None:
            self._on_hover(event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._on_leave is not None:
            self._on_leave()
        super().mousePressEvent(event)

    def leaveEvent(self, event) -> None:
        if self._on_leave is not None:
            self._on_leave()
        super().leaveEvent(event)


class ChatWidget(QtWidgets.QWidget):
    """A single chat tab's content: header info + message view + input bar."""

    message_sent = QtCore.pyqtSignal(str, str)  # jid, body
    message_reply_sent = QtCore.pyqtSignal(str, str, str, str, str, str)
    #   jid, body, reply_to, reply_id, ref_sender, ref_body   (XEP-0461)
    message_edit_sent = QtCore.pyqtSignal(str, str, str)  # jid, body, edit_id
    typing_changed = QtCore.pyqtSignal(str, bool)  # jid, is_typing
    link_clicked = QtCore.pyqtSignal(str)
    clear_history_requested = QtCore.pyqtSignal(str)       # jid
    server_history_requested = QtCore.pyqtSignal(str, str)  # jid, since_ts
    bookmark_toggled = QtCore.pyqtSignal(str)              # MUC room
    set_subject_requested = QtCore.pyqtSignal(str)         # MUC room
    nick_change_requested = QtCore.pyqtSignal(str, str)    # MUC room, nick
    participant_clicked = QtCore.pyqtSignal(str, str)      # room, nick
    participant_context_requested = QtCore.pyqtSignal(
        str, str, QtCore.QPoint)                            # room, nick, global pos
    vcard_requested = QtCore.pyqtSignal(str)                # jid
    files_upload_requested = QtCore.pyqtSignal(str, list, str)  # jid, [paths], method
    input_height_changed = QtCore.pyqtSignal(str, int)   # jid, height
    text_scale_changed = QtCore.pyqtSignal(str, float)   # jid, scale factor
    media_view_requested = QtCore.pyqtSignal(str, str, bool)  # url, kind, fullscreen
    media_save_requested = QtCore.pyqtSignal(str)             # url
    media_copy_requested = QtCore.pyqtSignal(str)             # url

    def __init__(self, jid: str, display_name: str, theme: ChatThemeFactory,
                 is_muc: bool = False, parent=None):
        super().__init__(parent)
        self.jid = jid
        self.display_name = display_name
        self.is_muc = is_muc
        self._show_avatars = True
        self._send_ctrl_enter = False
        self._send_typing_notifications = True
        self._send_activity_notifications = True
        self._show_status = True
        self._last_sender: str = ""
        self._history: list[dict] = []
        self._status_lines: list[tuple[str, str]] = []
        self._messages: list[dict] = []
        self._window_size = 200
        self._hist_loading = False
        self._db_exhausted = False
        self._server_exhausted = False
        self._server_fetching = False
        self._cleared = False
        self._anchor_bottom = True
        self._preserve_fraction: float | None = None
        self._users: list[dict] = []
        self._self_nick: str = ""
        self._hovered_participant: str = ""
        self._nick_colors = NickColorAllocator()
        self._colored_muc_nicks: bool = True
        self._bookmarked = False
        self._bookmark_action = None
        self._subjects: list[tuple[str, str]] = []
        self._released = False
        self._last_view_h = 0
        self._build_ui(theme)
        self._view.near_top.connect(self._on_near_top)

    # ── UI construction ───────────────────────────────────────────

    def _build_ui(self, theme: ChatThemeFactory):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Contact info header
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(4, 2, 4, 2)
        header.setSpacing(6)
        self._name_label = QtWidgets.QLabel(self.display_name)
        self._name_label.setStyleSheet("font-weight: bold;")
        self._name_label.setVisible(False)
        self._status_label = QtWidgets.QLabel("")
        self._status_label.setStyleSheet("color: gray; font-size: 11px;")
        self._status_label.setVisible(False)
        header.addWidget(self._name_label)
        header.addWidget(self._status_label)

        self._subject_btn = QtWidgets.QToolButton(self)
        self._subject_btn.setText(tr("muc_subject_label"))
        self._subject_btn.setAutoRaise(True)
        self._subject_btn.setToolTip(tr("muc_set_subject_title"))
        self._subject_btn.setVisible(self.is_muc)
        self._subject_btn.clicked.connect(
            lambda: self.set_subject_requested.emit(self.jid))
        header.addWidget(self._subject_btn)

        self._subject_edit = _SubjectEdit(
            "", self,
            on_hover=self._subject_tooltip,
            on_leave=tooltip_mod.hide)
        self._subject_edit.setReadOnly(True)
        self._subject_edit.setStyleSheet(
            "border: none; background: transparent; padding-left: 2px;")
        self._subject_edit.setMinimumWidth(120)
        self._subject_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred)
        self._subject_edit.setVisible(self.is_muc)
        header.addWidget(self._subject_edit)

        self._history_menu = QtWidgets.QMenu(self)
        act_load = self._history_menu.addAction(tr("history_load_earlier"))
        act_load.triggered.connect(self._load_older_batch)
        act_server = self._history_menu.addAction(tr("history_load_from_server"))
        act_server.triggered.connect(self.load_more_from_server)
        act_clear = self._history_menu.addAction(tr("history_clear"))
        act_clear.triggered.connect(self._request_clear_history)
        if self.is_muc:
            self._history_menu.addSeparator()
            self._bookmark_action = self._history_menu.addAction(
                tr("bookmark_add"))
            self._bookmark_action.triggered.connect(
                lambda: self.bookmark_toggled.emit(self.jid))

        self._bookmark_btn = QtWidgets.QToolButton(self)
        self._bookmark_btn.setIcon(self._bookmark_icon())
        self._bookmark_btn.setCheckable(True)
        self._bookmark_btn.setToolTip(tr("bookmark_add"))
        self._bookmark_btn.setVisible(self.is_muc)
        self._bookmark_btn.setAutoRaise(True)
        self._bookmark_btn.clicked.connect(
            lambda: self.bookmark_toggled.emit(self.jid))
        header.addWidget(self._bookmark_btn)

        if self.is_muc:
            layout.addLayout(header)

        # Chat view + resizable MUC participant sidebar
        chat_col = QtWidgets.QVBoxLayout()
        chat_col.setContentsMargins(0, 0, 0, 0)
        chat_col.setSpacing(0)
        self._view = ChatView(theme)
        self._view.mention_senders = self.is_muc
        self._view.link_clicked.connect(self._open_link)
        self._view.link_clicked.connect(self.link_clicked)
        self._view.reply_requested.connect(self._on_reply_requested)
        self._view.document_lost.connect(self._restore_after_document_lost)
        self._view.zoom_changed.connect(
            lambda factor: self.text_scale_changed.emit(self.jid, factor))
        self._view.media_save_requested.connect(self.media_save_requested)
        self._view.media_copy_requested.connect(self.media_copy_requested)
        self._view.media_open_requested.connect(self._on_media_open_requested)
        chat_col.addWidget(self._view, stretch=1)

        # Reply context bar (XEP-0461): shown while composing a reply.
        self._reply_ctx = QtWidgets.QFrame(self)
        self._reply_ctx.setObjectName("reply-ctx")
        self._reply_ctx.setStyleSheet(
            "#reply-ctx { background: #f0f0f0; border-bottom: 1px solid #d8d8d8; }"
            "#reply-ctx QLabel { color: #444; font-size: 12px; }")
        _ctx = QtWidgets.QHBoxLayout(self._reply_ctx)
        _ctx.setContentsMargins(8, 3, 4, 3)
        _ctx.setSpacing(6)
        self._reply_label = QtWidgets.QLabel("")
        self._reply_label.setWordWrap(True)
        _ctx.addWidget(self._reply_label, stretch=1)
        self._reply_cancel = QtWidgets.QToolButton(self._reply_ctx)
        self._reply_cancel.setText("\u00d7")
        self._reply_cancel.setAutoRaise(True)
        self._reply_cancel.setToolTip(tr("reply_cancel"))
        self._reply_cancel.clicked.connect(self._cancel_reply)
        _ctx.addWidget(self._reply_cancel)
        self._reply_ctx.setVisible(False)
        chat_col.addWidget(self._reply_ctx)
        self._reply_id = ""
        self._reply_to = ""
        self._reply_ref_sender = ""
        self._reply_ref_body = ""
        self._reply_quote_range: tuple[int, int] | None = None
        self._reply_quote_text = ""

        # Editing banner + state (XEP-0308)
        self._edit_ctx = QtWidgets.QFrame(self)
        self._edit_ctx.setObjectName("edit-ctx")
        self._edit_ctx.setStyleSheet(
            "#edit-ctx { background: #fdeecc; border-bottom: 1px solid #e0c875; }"
            "#edit-ctx QLabel { color: #6b5b1f; font-size: 12px; }")
        _edit_layout = QtWidgets.QHBoxLayout(self._edit_ctx)
        _edit_layout.setContentsMargins(8, 3, 4, 3)
        _edit_layout.setSpacing(6)
        self._edit_label = QtWidgets.QLabel("")
        self._edit_label.setWordWrap(True)
        _edit_layout.addWidget(self._edit_label, stretch=1)
        self._edit_cancel = QtWidgets.QToolButton(self._edit_ctx)
        self._edit_cancel.setText("\u00d7")
        self._edit_cancel.setAutoRaise(True)
        self._edit_cancel.setToolTip(tr("edit_cancel"))
        self._edit_cancel.clicked.connect(self._cancel_edit)
        _edit_layout.addWidget(self._edit_cancel)
        self._edit_ctx.setVisible(False)
        chat_col.addWidget(self._edit_ctx)
        self._editing_id = ""
        self._editing_previous = ""

        # ── Input bar buttons ─────────────────────────────────────
        actions_row = QtWidgets.QHBoxLayout()
        actions_row.setContentsMargins(4, 2, 4, 0)
        actions_row.setSpacing(2)

        clear_btn = QtWidgets.QToolButton(self)
        clear_btn.setIcon(self._chat_icon("process-stop.png"))
        clear_btn.setToolTip(tr("chat_clear"))
        clear_btn.setAutoRaise(True)
        clear_btn.clicked.connect(lambda: self.clear_history_requested.emit(self.jid))
        actions_row.addWidget(clear_btn)

        self._history_btn = QtWidgets.QToolButton(self)
        self._history_btn.setIcon(self._chat_icon("history.png"))
        self._history_btn.setToolTip(tr("history_menu_tooltip"))
        self._history_btn.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self._history_btn.setMenu(self._history_menu)
        actions_row.addWidget(self._history_btn)

        vcard_btn = QtWidgets.QToolButton(self)
        vcard_btn.setIcon(self._chat_icon("v-card.png"))
        vcard_btn.setToolTip(tr("chat_vcard"))
        vcard_btn.setAutoRaise(True)
        vcard_btn.clicked.connect(lambda: self.vcard_requested.emit(self.jid))
        actions_row.addWidget(vcard_btn)

        send_menu = QtWidgets.QMenu(self)
        send_p2p = send_menu.addAction(tr("ft_p2p"))
        send_p2p.triggered.connect(lambda: self._choose_file_send("p2p"))
        send_http = send_menu.addAction(tr("ft_http_upload"))
        send_http.triggered.connect(lambda: self._choose_file_send("http"))
        self._send_file_btn = QtWidgets.QToolButton(self)
        self._send_file_btn.setIcon(self._chat_icon("upload.png"))
        self._send_file_btn.setToolTip(tr("chat_send_file"))
        self._send_file_btn.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self._send_file_btn.setMenu(send_menu)
        actions_row.addWidget(self._send_file_btn)
        actions_row.addStretch(1)
        chat_col.addLayout(actions_row)

        self._nick_complete_candidates: list[str] = []
        self._nick_complete_index = -1
        self._nick_complete_inserted = ""
        self._nick_complete_start = -1
        self._nick_complete_suffix = ""

        # Resize handle above the input, right below the toolbar
        self._input_handle = _InputHandle(
            self, get_height=lambda: self._input_height)
        self._input_handle.height_changed.connect(self._set_input_height)
        chat_col.addWidget(self._input_handle)

        # Input area
        input_row = QtWidgets.QHBoxLayout()
        input_row.setContentsMargins(4, 2, 4, 2)
        self._input = QtWidgets.QPlainTextEdit()
        self._input_height = 60
        self._input.setMinimumHeight(40)
        self._input.setMaximumHeight(240)
        self._input.setFixedHeight(self._input_height)
        self._input.setPlaceholderText(tr("chat_send"))
        self._input.installEventFilter(self)
        self._input.textChanged.connect(self._on_input_changed)
        input_row.addWidget(self._input, stretch=1)

        self._send_btn = QtWidgets.QPushButton(tr("chat_send"))
        self._send_btn.clicked.connect(self._send)
        input_row.addWidget(self._send_btn)
        chat_col.addLayout(input_row)

        chat_panel = QtWidgets.QWidget(self)
        chat_panel.setLayout(chat_col)
        self.setAcceptDrops(True)
        # Let drops fall through to this widget: the view and input would
        # otherwise swallow file drops (QTextBrowser/QWebEngineView and
        # QPlainTextEdit both accept drops by default).
        self._view.setAcceptDrops(False)
        self._input.setAcceptDrops(False)

        self._users_list = QtWidgets.QListWidget()
        self._users_list.setMinimumWidth(120)
        self._users_list.setMaximumWidth(420)
        self._users_list.setAcceptDrops(False)
        self._users_list.setVisible(self.is_muc)
        self._users_list.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._users_list.itemClicked.connect(self._on_muc_user_clicked)
        self._users_list.customContextMenuRequested.connect(
            self._on_muc_context_menu)

        self._content_splitter = QtWidgets.QSplitter(
            QtCore.Qt.Orientation.Horizontal, self)
        self._content_splitter.addWidget(chat_panel)
        self._content_splitter.addWidget(self._users_list)
        self._content_splitter.setStretchFactor(0, 1)
        self._content_splitter.setStretchFactor(1, 0)
        self._content_splitter.setSizes([self.width() - 180, 180])
        layout.addWidget(self._content_splitter, stretch=1)

        self._typing_timer = QtCore.QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.setInterval(_TYPING_DEBOUNCE_MS)
        self._typing_timer.timeout.connect(self._typing_paused)

    # ── Link / marker handling ────────────────────────────────────

    def _open_link(self, url: str):
        if url.startswith("stanza:reply:"):
            self._handle_reply_uri(url)
            return
        if url.startswith("stanza:mention:"):
            self._handle_mention_uri(url)
            return
        if url.startswith("stanza:edit:"):
            self._handle_edit_uri(url)
            return
        if url.startswith("stanza:view:"):
            self._handle_media_view_uri(url)
            return
        if url == "mam://load":
            self.load_more_from_server()
            return
        low = url.lower()
        if low.startswith(("http://", "https://", "mailto:")):
            webbrowser.open(url)
            return
        self.link_clicked.emit(url)

    def _handle_reply_uri(self, url: str) -> None:
        """Decode a ``stanza:reply:id/author/sender/body`` click and start a
        XEP-0461 reply (page JS routes the reply button here)."""
        parts = url[len("stanza:reply:"):].split("/", 3)
        reply_id = unquote(parts[0]) if len(parts) > 0 else ""
        author = unquote(parts[1]) if len(parts) > 1 else ""
        sender = unquote(parts[2]) if len(parts) > 2 else ""
        snippet = unquote(parts[3]) if len(parts) > 3 else ""
        self._on_reply_requested(reply_id, author, sender, snippet)

    def _handle_mention_uri(self, url: str) -> None:
        """Insert ``nick: `` from a ``stanza:mention:nick`` click (MUC only)."""
        if not self.is_muc:
            return
        nick = unquote(url[len("stanza:mention:"):])
        if not nick:
            return
        cursor = self._input.textCursor()
        before = self._input.toPlainText()[:cursor.position()]
        prefix = " " if before and not before[-1].isspace() else ""
        self._input.insertPlainText(prefix + nick + ": ")
        self._input.setFocus()

    def _handle_media_view_uri(self, url: str) -> None:
        """Open a ``stanza:view:<kind>/<url>`` target in the media viewer."""
        rest = url[len("stanza:view:"):]
        kind, _sep, encoded = rest.partition("/")
        target = unquote(encoded) if encoded else ""
        if target:
            self.media_view_requested.emit(target, kind or "image", False)

    def _on_media_open_requested(self, url: str, kind: str):
        """Route a context-menu viewer request, expanding ``video_fs``."""
        fullscreen = kind == "video_fs"
        self.media_view_requested.emit(
            url, "video" if fullscreen else kind, fullscreen)

    # ── Typing indicators ─────────────────────────────────────────

    def _on_input_changed(self):
        if self.is_muc:
            return
        if self._input.toPlainText().strip():
            if not self._typing_timer.isActive():
                if self._send_typing_notifications:
                    self.typing_changed.emit(self.jid, True)
            self._typing_timer.start()
        else:
            self._typing_timer.stop()
            if self._send_typing_notifications:
                self.typing_changed.emit(self.jid, False)

    def _typing_paused(self):
        if self._send_typing_notifications:
            self.typing_changed.emit(self.jid, False)

    def eventFilter(self, obj, event):
        if obj is self._input and event.type() == QtCore.QEvent.Type.KeyPress:
            modifiers = event.modifiers()
            has_ctrl = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)
            send_key = has_ctrl if self._send_ctrl_enter else not has_ctrl
            if (event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter)
                    and send_key
                    and not modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier):
                self._send()
                return True
            if event.key() in (QtCore.Qt.Key.Key_Tab,
                               QtCore.Qt.Key.Key_Backtab):
                backward = event.key() == QtCore.Qt.Key.Key_Backtab
                if self._tab_complete_nick(backward):
                    return True
            if (event.key() == QtCore.Qt.Key.Key_Up and has_ctrl
                    and not modifiers & QtCore.Qt.KeyboardModifier.AltModifier
                    and not modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier
                    and self._edit_last_sent()):
                return True
            if (event.key() == QtCore.Qt.Key.Key_V and has_ctrl
                    and self._handle_pasted_image()):
                return True
            if (event.key() in (QtCore.Qt.Key.Key_Escape,)
                    and self._editing_id):
                self._cancel_edit()
                return True
        return super().eventFilter(obj, event)

    def _tab_complete_nick(self, backward: bool = False) -> bool:
        """Complete the MUC nick before the cursor with Tab.

        With an empty input the nick is inserted as an address (``nick: ``),
        otherwise only the nick is completed.  Repeated Tab presses walk the
        candidate list (wrapping around) and replace the previously inserted
        token; any edit restarts the search.  Returns True when consumed.
        """
        if not self.is_muc:
            return False
        tc = self._input.textCursor()
        doc = self._input.document()
        pos = tc.position()

        continuing = False
        if (self._nick_complete_inserted
                and self._nick_complete_start >= 0
                and self._nick_complete_start
                + len(self._nick_complete_inserted) == pos):
            probe = QtGui.QTextCursor(doc)
            probe.setPosition(self._nick_complete_start)
            probe.setPosition(
                self._nick_complete_start + len(self._nick_complete_inserted),
                QtGui.QTextCursor.MoveMode.KeepAnchor)
            continuing = probe.selectedText() == self._nick_complete_inserted

        if continuing:
            candidates = self._nick_complete_candidates
            index = (self._nick_complete_index + (-1 if backward else 1)) \
                % len(candidates)
            suffix = self._nick_complete_suffix
            start = self._nick_complete_start
        else:
            block_text = tc.block().text()
            in_block = tc.positionInBlock()
            start_in_block = block_text.rfind(" ", 0, in_block) + 1
            current_word = block_text[start_in_block:in_block]
            pool = sorted(
                (u.get("nick", "") for u in self._users if u.get("nick")),
                key=str.lower)
            if current_word:
                pool = [n for n in pool
                        if n.lower().startswith(current_word.lower())]
            if not pool:
                self._nick_complete_inserted = ""
                return False
            candidates = pool
            index = len(pool) - 1 if backward else 0
            suffix = (": " if not block_text[:start_in_block].strip() else "")
            start = tc.block().position() + start_in_block

        new_text = candidates[index] + suffix
        end = start + len(self._nick_complete_inserted) if continuing else pos
        edit = QtGui.QTextCursor(doc)
        edit.setPosition(start)
        edit.setPosition(end, QtGui.QTextCursor.MoveMode.KeepAnchor)
        edit.insertText(new_text)
        self._input.setTextCursor(edit)

        self._nick_complete_candidates = candidates
        self._nick_complete_index = index
        self._nick_complete_inserted = new_text
        self._nick_complete_start = start
        self._nick_complete_suffix = suffix
        return True

    def _send(self):
        text = self._input.toPlainText()
        if not text:
            return
        self._typing_timer.stop()
        self.typing_changed.emit(self.jid, False)
        if text.startswith("/") and self._handle_slash_command(text):
            self._input.clear()
            return
        if self._editing_id:
            self.message_edit_sent.emit(self.jid, text, self._editing_id)
            self._clear_edit_state()
            self._input.clear()
            return
        if self._reply_id and text.lstrip().startswith("> "):
            self.message_reply_sent.emit(
                self.jid, text, self._reply_to, self._reply_id, "", "")
        else:
            self.message_sent.emit(self.jid, text)
        self._clear_reply_state()
        self._input.clear()

    def _handle_slash_command(self, text: str) -> bool:
        """Handle local slash commands; return True when consumed.

        XEP-0245 ``/me`` is intentionally NOT consumed: the body goes to the
        wire as-is ("/me laughs") and only the presentation changes.
        """
        if text.startswith("/nick "):
            nick = text[6:].strip()
            if self.is_muc:
                self.nick_change_requested.emit(self.jid, nick)
            else:
                self.add_status(tr("muc_nick_only_groupchat"),
                                time.strftime("%H:%M:%S"))
            return True
        return False

    # ── XEP-0461 replies ──────────────────────────────────────────

    @staticmethod
    def _split_reply_quote(body: str):
        """Split a reply body into (display_body, fallback_quote).

        XEP-0421 fallback bodies are prefixed with ``> Sender wrote: …``
        lines. Those become the *quote*; everything after the blank line is
        the real body.
        """
        if not body:
            return body, ""
        in_quote = True
        quote, rest = [], []
        for line in body.split("\n"):
            if in_quote and line.startswith("> "):
                quote.append(line[2:].strip())
            else:
                in_quote = False
                rest.append(line)
        while rest and not rest[0].strip():
            rest.pop(0)
        snippet = " ".join(item for item in quote if item)
        return "\n".join(rest), snippet

    def _find_message(self, stable_id: str):
        """Locate a stored message whose stable id matches the reply target."""
        if not stable_id:
            return None
        for entry in self._newest_first():
            if (entry.get("origin_id") == stable_id
                    or entry.get("message_id") == stable_id
                    or entry.get("archive_id") == stable_id):
                return entry
        return None

    def _newest_first(self):
        """Iterate the conversation newest-to-oldest (live then history)."""
        for entry in reversed(self._messages):
            yield entry
        for entry in reversed(self._history):
            yield entry

    @staticmethod
    def _reply_target_id(entry: dict) -> str:
        """Stable id a XEP-0461 ``<reply/>`` can reference for *entry*.

        Falls back through ``origin_id`` → ``archive_id`` → ``message_id`` so
        messages persisted before the reply feature (or without an
        ``origin-id``) still expose a replyable target when possible.
        """
        return (entry.get("origin_id") or entry.get("archive_id")
                or entry.get("message_id") or "")

    def _reply_quote_for(self, entry: dict):
        """Resolve a reply reference to (sender_name, body_quote)."""
        original = self._find_message(entry.get("reply_id", ""))
        if original:
            return (original.get("sender", ""), original.get("body", ""))
        return (self._author_display(entry.get("reply_to", "")), "")

    @staticmethod
    def _author_display(reply_to: str) -> str:
        """Human-friendly author name from a full JID or room/nick."""
        if not reply_to:
            return ""
        if "/" in reply_to:
            return reply_to.rsplit("/", 1)[1]
        return reply_to

    def _on_reply_requested(self, reply_id: str, author: str, sender: str,
                            snippet: str):
        """Start composing a XEP-0461 reply in this chat.

        The referenced message is inserted into the input as a XEP-0421
        style quote block with the cursor below it; the banner stays as an
        indicator and the reply reference is kept for the outgoing stanza.
        """
        self._clear_edit_state()
        self._reply_id = reply_id
        self._reply_to = author or sender or self.jid
        display = sender or self._author_display(author) or self._reply_to
        self._reply_ref_sender = ""
        self._reply_ref_body = ""
        quote = self._format_quote(display, snippet)
        self._input.insertPlainText(quote)
        cursor = self._input.textCursor()
        self._reply_quote_text = quote
        self._reply_quote_range = (
            max(0, cursor.position() - len(quote)), len(quote))
        label = tr("reply_in_reply_to", sender=display)
        hint = " ".join((snippet or "").split())
        if hint:
            if len(hint) > 90:
                hint = hint[:90] + "\u2026"
            label += f": {hint}"
        self._reply_label.setText(label)
        self._reply_ctx.setVisible(True)
        self._input.setFocus()

    @staticmethod
    def _format_quote(sender: str, snippet: str) -> str:
        """Build the XEP-0421 fallback quote block inserted into the input."""
        lines = ["> " + (sender or "") + " wrote:"]
        for line in (snippet or "").splitlines() or [""]:
            lines.append(("> " + line) if line else ">")
        return "\n".join(lines) + "\n\n"

    def _cancel_reply(self):
        self._remove_inserted_quote()
        self._clear_reply_state()
        self._input.setFocus()

    def _remove_inserted_quote(self) -> None:
        """Delete the quote block inserted when the reply started (if the
        user has not edited it since)."""
        if not self._reply_quote_range or not self._reply_quote_text:
            return
        start, length = self._reply_quote_range
        doc = self._input.document()
        if start < 0 or start + length > doc.characterCount() - 1:
            return
        probe = QtGui.QTextCursor(doc)
        probe.setPosition(start)
        probe.setPosition(start + length, QtGui.QTextCursor.MoveMode.KeepAnchor)
        selected = probe.selectedText().replace("\u2029", "\n")
        if selected != self._reply_quote_text:
            return
        probe.removeSelectedText()

    def _clear_reply_state(self):
        self._reply_id = ""
        self._reply_to = ""
        self._reply_ref_sender = ""
        self._reply_ref_body = ""
        self._reply_quote_range = None
        self._reply_quote_text = ""
        self._reply_ctx.setVisible(False)

    # ── XEP-0308 editing ─────────────────────────────────────────

    def _handle_edit_uri(self, url: str) -> None:
        ref = unquote(url[len("stanza:edit:"):])
        if not ref:
            return
        entry = self._find_editable(ref)
        if entry is not None:
            self._begin_edit(entry)

    def _find_editable(self, ref: str):
        """Locate a message editable via *ref* (must be our own message)."""
        if not ref:
            return None
        for entry in self._newest_first():
            if (str(entry.get("message_id") or "") == ref
                    or str(self._reply_target_id(entry) or "") == ref):
                if self._is_mine(entry):
                    return entry
        return None

    def _is_mine(self, entry: dict) -> bool:
        if entry.get("direction") == "outgoing":
            return True
        return bool(self.is_muc and self._self_nick
                    and entry.get("sender") == self._self_nick)

    def _edit_last_sent(self) -> bool:
        """Edit the newest message we sent (Ctrl+Up)."""
        for entry in self._newest_first():
            mine = (entry.get("direction") == "outgoing"
                    or (self.is_muc and self._self_nick
                        and entry.get("sender") == self._self_nick))
            ref = str(entry.get("message_id") or "") or self._reply_target_id(entry)
            if mine and ref:
                self._begin_edit(entry)
                return True
        return False

    def _begin_edit(self, entry: dict) -> None:
        ref = str(entry.get("message_id") or "") or self._reply_target_id(entry)
        if not ref:
            return
        self._cancel_reply()
        self._editing_id = ref
        self._editing_previous = self._input.toPlainText()
        body = entry.get("body", "") or ""
        if entry.get("reply_id"):
            body = self._split_reply_quote(body)[0]
        self._input.setPlainText(body)
        cursor = self._input.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        self._edit_label.setText(tr("edit_in_progress"))
        self._edit_ctx.setVisible(True)
        self._input.setFocus()

    def _cancel_edit(self):
        self._input.setPlainText(self._editing_previous)
        self._clear_edit_state()
        self._input.setFocus()

    def _clear_edit_state(self):
        self._editing_id = ""
        self._editing_previous = ""
        self._edit_ctx.setVisible(False)

    def edit_message_by_ref(self, ref_id: str, new_body: str) -> bool:
        """Replace the body of *ref_id*'s message and mark it edited."""
        for entry in list(self._messages) + list(self._history):
            if (str(entry.get("message_id") or "") == ref_id
                    or str(self._reply_target_id(entry) or "") == ref_id):
                entry["body"] = new_body
                entry["edited"] = True
                dom_ref = entry.get("message_id") or self._reply_target_id(entry) \
                    or ref_id
                html = self._view.render_message_html(
                    **self._entry_view_kwargs(entry))
                self._view.replace_message_ref(dom_ref, html)
                return True
        return False

    # ── Message rendering ─────────────────────────────────────────

    def add_message(self, sender: str, body: str, timestamp: str,
                    direction: str = "incoming", is_next: bool = False,
                    sender_jid: str = "", archive_id: str = "",
                    message_id: str = "", unstyled: bool = False,
                    reply_able_id: str = "", reply_author: str = "",
                    reply_to: str = "", reply_id: str = "",
                    edited: bool = False):
        if not isinstance(timestamp, str):
            timestamp = (timestamp.strftime("%H:%M:%S")
                         if hasattr(timestamp, "strftime")
                         else str(timestamp or ""))
        if not self._last_sender and sender in ("Me", self.display_name,
                                                self.jid.split("@")[0]):
            self._last_sender = sender
        if sender == self._last_sender and direction == "incoming":
            is_next = True
        timestamp = timestamp or time.strftime("%H:%M:%S")
        entry = {"sender": sender or "Me", "body": body or "",
                  "timestamp": timestamp, "direction": direction,
                  "is_next": is_next, "sender_jid": sender_jid,
                  "archive_id": archive_id,
                  "message_id": (message_id or reply_able_id
                              or (uuid.uuid4().hex if direction == "outgoing" else "")),
                  "delivered": False, "unstyled": unstyled,
                  "origin_id": reply_able_id, "reply_author": reply_author,
                  "reply_to": reply_to, "reply_id": reply_id,
                  "edited": edited}
        self._messages.append(entry)
        self._render_entry(entry)
        if direction == "incoming" or sender == "Me":
            self._last_sender = sender
        self._anchor_bottom = True
        self._view.scroll_to_bottom()
        self._maybe_unblock_after_clear()

    def add_status(self, text: str, timestamp: str):
        self._status_lines.append((text, timestamp))
        self._view.add_status(text, timestamp)

    def set_history_status(self, text: str):
        """Replace the transient server-history status without moving scroll."""
        fetching = tr("history_server_fetching")
        self._status_lines = [item for item in self._status_lines
                              if item[0] != fetching]
        if text:
            self._status_lines.append((text, time.strftime("%H:%M:%S")))

    def _entry_view_kwargs(self, entry: dict) -> dict:
        body = entry.get("body", "")
        reply_quote = None
        if entry.get("reply_id"):
            body, fb_quote = self._split_reply_quote(body)
            ref_sender, ref_body = self._reply_quote_for(entry)
            reply_quote = (ref_sender or entry.get("reply_author") or "",
                           ref_body or fb_quote)
        from stanza_im.include.utils import ts_to_time
        return {
            "sender": entry["sender"],
            "body": body,
            "timestamp": ts_to_time(entry.get("timestamp", "")),
            "direction": entry.get("direction", "incoming"),
            "is_next": entry.get("is_next", False),
            "message_id": entry.get("message_id", ""),
            "unstyled": entry.get("unstyled", False),
            "raw_timestamp": entry.get("timestamp", ""),
            "reply_able_id": self._reply_target_id(entry),
            "reply_author": entry.get("reply_author", ""),
            "reply_quote": reply_quote,
            "user_icon_path": self._user_icon(
                entry.get("direction", "incoming"),
                entry.get("sender_jid", ""),
                entry.get("sender", "")),
            "outgoing": self._is_mine(entry),
            "edited": bool(entry.get("edited")),
            "sender_color": self._sender_color(entry),
        }

    def _render_entry(self, entry: dict):
        self._view.add_message(**self._entry_view_kwargs(entry))

    def _user_icon(self, direction: str, sender_jid: str = "",
                   sender: str = "") -> str:
        """Return a PNG data-URI for the sender avatar."""
        if not self._show_avatars:
            return ""
        if direction == "outgoing":
            return default_avatar_uri()
        if self.is_muc:
            if not sender_jid and sender:
                participant = next(
                    (user for user in self._users
                     if self._same_nick(user.get("nick", ""), sender)), None)
                if participant:
                    direct_uri = avatar_file_data_uri(
                        participant.get("avatar_path", ""))
                    if direct_uri:
                        return direct_uri
                    sender_jid = (participant.get("avatar_jid", "")
                                  or participant.get("real_jid", ""))
                    if sender_jid:
                        logger.debug("Resolved historical avatar: room=%s nick=%s jid=%s",
                                     self.jid, sender, sender_jid)
            return avatar_data_uri(sender_jid) or default_avatar_uri()
        return avatar_data_uri(sender_jid or self.jid) or default_avatar_uri()

    @staticmethod
    def _same_nick(left: str, right: str) -> bool:
        import re
        import unicodedata
        normalize = lambda value: re.sub(
            r"\s+", " ", unicodedata.normalize("NFKC", value or "")
        ).strip().casefold()
        return normalize(left) == normalize(right)

    def _restore_after_document_lost(self):
        """The WebEngine document was wiped (blocked load); rebuild it from
        the local window instead of leaving a blank chat."""
        self._preserve_fraction = None
        self._anchor_bottom = True
        self._render_all()

    def _render_all(self):
        """Clear the view and re-render everything, restoring scroll."""
        keep = self._preserve_fraction if self._preserve_fraction is not None \
            else self._view.scroll_fraction()
        self._view.clear()
        if self._cleared:
            marker = (f'<a href="mam://load" '
                      f'style="color:#1a73e8;text-decoration:underline;">'
                      f'{tr("history_load_from_server")}</a>')
            self._view.add_status(marker, "")
        for text, timestamp in self._status_lines:
            self._view.add_status(text, timestamp)
        entries = []
        seen = set()
        for entry in self._history + self._messages:
            key = self._entry_key(entry)
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
        entries.sort(key=lambda entry: (
            entry.get("timestamp", "") or "", entry.get("id", 0) or 0))
        for entry in entries:
            self._render_entry(entry)
        self._preserve_fraction = None
        if self._anchor_bottom:
            self._view.scroll_to_bottom()
        else:
            self._view.set_scroll_fraction(keep)

    @staticmethod
    def _entry_key(entry: dict) -> tuple:
        if entry.get("archive_id"):
            return ("archive", entry["archive_id"])
        return (entry.get("direction", "incoming"),
                entry.get("sender", ""), entry.get("body", ""),
                entry.get("timestamp", ""))

    # ── History window management ─────────────────────────────────

    def _start_task(self, coro):
        """Schedule *coro* on the shared asyncio loop (best-effort)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return None
        return loop.create_task(coro)

    def detach(self):
        """Mark the widget as torn down: pending async history pages abort."""
        self._released = True

    def set_history(self, entries: list[dict], window_size: int,
                    exhausted: bool):
        """Initial window: replace history rows and re-render from bottom."""
        self._history = list(entries or [])
        self._window_size = max(50, int(window_size))
        self._db_exhausted = bool(exhausted)
        self._server_exhausted = False
        self._hist_loading = False
        self._server_fetching = False
        self._cleared = False
        self._anchor_bottom = True
        self._preserve_fraction = None
        self._render_all()
        if self.is_muc and not self._history:
            QtCore.QTimer.singleShot(0, self._on_near_top)

    def prepend_history(self, entries: list[dict], exhausted: bool):
        """Insert older rows at the top of the window, keeping position."""
        from stanza_im.include.utils import ts_to_time
        known = {self._entry_key(entry) for entry in self._history}
        unique = []
        for entry in entries:
            key = self._entry_key(entry)
            if key in known:
                continue
            known.add(key)
            unique.append(entry)
        if not unique:
            self._hist_loading = False
            self._db_exhausted = bool(exhausted)
            return
        self._preserve_fraction = self._view.scroll_fraction()
        self._history = unique + self._history
        self._db_exhausted = bool(exhausted)
        self._hist_loading = False
        self._view.prepend_messages([
             {**entry, "user_icon_path": self._user_icon(
                 entry.get("direction", "incoming"),
                 entry.get("sender_jid", ""), entry.get("sender", "")),
             "timestamp": ts_to_time(entry.get("timestamp", "")),
             "raw_timestamp": entry.get("timestamp", ""),
             "body": (entry.get("body", "") if not entry.get("reply_id")
                      else self._split_reply_quote(entry.get("body", ""))[0]),
             "origin_id": self._reply_target_id(entry),
             "reply_author": entry.get("reply_author", ""),
             "reply_quote": self._reply_quote_for(entry)
                            if entry.get("reply_id") else None,
             "outgoing": self._is_mine(entry),
             "edited": bool(entry.get("edited"))}
            for entry in unique
        ])

    def history_cleared(self):
        """Local history was wiped — reset buffers and show the marker."""
        self._history = []
        self._messages = []
        self._status_lines = []
        self._cleared = True
        self._db_exhausted = True
        self._server_exhausted = False
        self._hist_loading = False
        self._anchor_bottom = True
        self._render_all()

    def server_fetch_done(self, stored: int):
        """Add the newly fetched older messages to the current window."""
        self._server_fetching = False
        if stored < 0:
            self._hist_loading = False
            return
        if stored > 0:
            self._server_exhausted = False
            self._start_task(self._apply_server_page())
        else:
            self._hist_loading = False
            self._server_exhausted = True

    async def _apply_server_page(self):
        """Fold the SQLite rows of the fetched MAM page into the window."""
        if self._released:
            return
        from stanza_im.core import history
        before = self.oldest_ts()
        if before:
            rows = await history.load_older_timestamp_async(
                self.jid, before, self._window_size)
            if self._released:
                return
            # These rows belong to the MAM page just stored. Do not
            # expose the same SQLite rows through a second paging path;
            # the next page is controlled by the MAM archive cursor.
            self.prepend_history(rows, True)
            self._db_exhausted = True
        else:
            self._history = await history.load_history_async(
                self.jid, limit=self._window_size)
            if self._released:
                return
            self._merge_live_history()
            self._db_exhausted = True
            self._anchor_bottom = True
            self._render_all()

    def _merge_live_history(self):
        """Fold messages received during MAM loading into the DB window."""
        if not self._messages:
            return
        known = {self._entry_key(entry) for entry in self._history}
        for entry in self._messages:
            key = self._entry_key(entry)
            if key not in known:
                self._history.append(entry)
                known.add(key)
        self._history.sort(key=lambda entry: (
            entry.get("timestamp", "") or "", entry.get("id", 0) or 0))
        self._messages.clear()

    def mark_server_exhausted(self):
        """Server has no MAM archive or it errored out — stop retrying."""
        self._server_fetching = False
        self._hist_loading = False
        self._server_exhausted = True

    def refresh_history(self, size: int | None = None):
        """Re-read the conversation tail from the local DB."""
        size = size or self._window_size * 2
        self._start_task(self._refresh_history_async(size))

    async def _refresh_history_async(self, size):
        if self._released:
            return
        from stanza_im.core import history
        entries = await history.load_history_async(self.jid, limit=size)
        if self._released:
            return
        self._preserve_fraction = self._view.scroll_fraction()
        self._cleared = False
        self._server_fetching = False
        self._history = entries
        self._db_exhausted = bool(entries) and not await \
            history.older_available_timestamp_async(
                self.jid, self.oldest_ts())
        self._hist_loading = False
        self._render_all()

    def first_loaded_id(self):
        if self._history:
            return self._history[0].get("id")
        return None

    def oldest_ts(self):
        timestamps = [entry.get("timestamp", "") for entry in self._history
                      if entry.get("timestamp")]
        return min(timestamps) if timestamps else ""

    def _batch_size(self):
        return max(50, self._window_size // 2)

    def _fill_threshold(self):
        estimate = max(10, self._view.height() // 40)
        return max(self._window_size, 3 * estimate)

    def needs_more(self) -> bool:
        return (not self._hist_loading and not self._server_fetching
                and not self._cleared and not self._db_exhausted
                and len(self._history) < self._window_size)

    def _maybe_unblock_after_clear(self):
        if self._cleared and len(self._messages) >= self._fill_threshold():
            self._cleared = False
            self._render_all()

    def _load_older_batch(self):
        if self._hist_loading or self._server_fetching:
            return
        if self._cleared:
            self.load_more_from_server()
            return
        if self._db_exhausted:
            self.load_more_from_server()
            return
        self._hist_loading = True
        self._start_task(self._load_older_batch_async(self.oldest_ts()))

    async def _load_older_batch_async(self, before_ts):
        if self._released:
            return
        from stanza_im.core import history
        if before_ts and await history.older_available_timestamp_async(
                self.jid, before_ts):
            rows = await history.load_older_timestamp_async(
                self.jid, before_ts, self._batch_size())
            if self._released:
                return
            exhausted = not rows
            if rows:
                next_before = rows[0].get("timestamp", "")
                exhausted = not (next_before and
                                 await history.older_available_timestamp_async(
                                     self.jid, next_before))
            self.prepend_history(rows, exhausted)
        else:
            self._db_exhausted = True
            self._hist_loading = False
            self.load_more_from_server()

    def load_more_from_server(self):
        if self._server_fetching or self._server_exhausted:
            return
        self._server_fetching = True
        logger.info("Requesting server history from widget: jid=%s since=%s",
                    self.jid, self.oldest_ts() or "now")
        self.server_history_requested.emit(self.jid, self.oldest_ts() or None)

    def _request_clear_history(self):
        self.clear_history_requested.emit(self.jid)

    def _on_near_top(self):
        logger.info("History near-top: jid=%s local=%d db_exhausted=%s server_exhausted=%s fetching=%s",
                    self.jid, len(self._history), self._db_exhausted,
                    self._server_exhausted, self._server_fetching)
        if (self._cleared or self._server_exhausted or self._hist_loading
                or self._server_fetching):
            return
        self._load_older_batch()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = self._view.height()
        if h <= self._last_view_h:
            self._last_view_h = h
            return
        self._last_view_h = h
        if (not self._cleared and not self._server_exhausted
                and not self._hist_loading and not self._server_fetching
                and len(self._history) < self._fill_threshold()):
            self._load_older_batch()

    # ── MUC participant sidebar ───────────────────────────────────

    def update_muc_users(self, users: list[dict], self_nick: str = ""):
        """Replace the MUC participant list (dicts with nick/show/status/
        role/affiliation)."""
        self._users = list(users or [])
        if self_nick:
            self._self_nick = self_nick
        self._view.highlight_nick = self._self_nick
        self._refresh_nick_colors()
        self._render_muc_users()

    def set_self_nick(self, nick: str):
        self._self_nick = nick or self._self_nick
        self._view.highlight_nick = self._self_nick
        self._refresh_nick_colors()
        self._render_muc_users()

    def _render_muc_users(self):
        if not self.is_muc:
            return
        self._users_list.clear()
        sections = {
            "moderators": [],
            "participants": [],
            "guests": [],
        }
        for user in self._users:
            role = user.get("role", "")
            affiliation = user.get("affiliation", "")
            if role == "moderator" or affiliation in ("owner", "admin"):
                section = "moderators"
            elif role == "visitor":
                section = "guests"
            else:
                section = "participants"
            sections[section].append(user)

        for section, users in sections.items():
            if not users:
                continue
            header = QtWidgets.QListWidgetItem(
                f"{tr(f'muc_section_{section}')} ({len(users)})")
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            header.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self._users_list.addItem(header)
            for user in sorted(users, key=lambda u: u.get("nick", "").lower()):
                self._add_muc_user_row(user)

    def _add_muc_user_row(self, user: dict):
        nick = user.get("nick", "")
        badge = (_MUC_BADGES.get(user.get("affiliation", ""), "")
                 or _MUC_BADGES.get(user.get("role", ""), ""))
        label = f"{badge} {nick}" if badge else nick
        if self._self_nick and nick == self._self_nick:
            label = f"{label} ({tr('muc_you')})"

        row = _ParticipantRow(
            self._users_list,
            on_hover=lambda pos: self._muc_user_hover(nick, pos),
            on_leave=self._muc_user_leave,
            on_press=tooltip_mod.hide)
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(4)
        status = QtWidgets.QLabel(row)
        status.setMouseTracking(True)
        status.setPixmap(self._status_icon(user.get("show", "offline"))
                         .pixmap(16, 16))
        text = QtWidgets.QLabel(label, row)
        text.setMouseTracking(True)
        if self._colored_muc_nicks:
            color = self._nick_colors.color_for(
                self._user_color_key(user))
            if color:
                text.setStyleSheet(f"color: {color};")
        layout.addWidget(status)
        layout.addWidget(text, 1)
        avatar = QtWidgets.QLabel(row)
        avatar.setMouseTracking(True)
        avatar.setFixedSize(28, 28)
        path = user.get("avatar_path", "") or default_avatar()
        pix = QtGui.QPixmap(path)
        if not pix.isNull():
            avatar.setPixmap(pix.scaled(
                28, 28, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(avatar)
        item = QtWidgets.QListWidgetItem()
        item.setData(QtCore.Qt.ItemDataRole.UserRole, nick)
        item.setSizeHint(row.sizeHint())
        self._users_list.addItem(item)
        self._users_list.setItemWidget(item, row)

    def _participant_tooltip(self, user: dict) -> str:
        """Rich-text tooltip for a MUC participant row."""
        from stanza_im.include.utils import escape_html
        nick = user.get("nick", "")
        lines = [f"<b>{escape_html(nick)}</b>"]
        real_jid = user.get("real_jid", "")
        if real_jid:
            lines.append(f"{tr('tooltip_real_jid')}: {escape_html(real_jid)}")
        client = user.get("client", "")
        if client:
            lines.append(f"{tr('tooltip_client')}: {escape_html(client)}")
        role = user.get("role", "")
        if role:
            label = tr(f"muc_role_{role}")
            lines.append(f"{tr('tooltip_role')}: {escape_html(label)}")
        affiliation = user.get("affiliation", "")
        if affiliation:
            label = tr(f"muc_affiliation_{affiliation}")
            lines.append(f"{tr('tooltip_affiliation')}: {escape_html(label)}")
        status = user.get("status", "")
        if status:
            lines.append("<i>"
                         + escape_html(status).replace("\n", "<br>")
                         + "</i>")
        return "<br>".join(lines)

    def _muc_user_hover(self, nick: str, global_pos: QtCore.QPoint) -> None:
        """Show the rich tooltip once per participant (restart on change)."""
        if nick == self._hovered_participant:
            return
        self._hovered_participant = nick
        self._muc_user_tooltip(nick, global_pos)

    def _muc_user_tooltip(self, nick: str, global_pos: QtCore.QPoint) -> None:
        tooltip_mod.hide()
        user = next((u for u in self._users if u.get("nick", "") == nick),
                    None)
        if user is None:
            return
        html = self._participant_tooltip(user)
        avatar = user.get("avatar_path", "") or None
        if html:
            tooltip_mod.show(global_pos, html, avatar)

    def _muc_user_leave(self) -> None:
        tooltip_mod.hide()
        self._hovered_participant = ""

    def _on_muc_user_clicked(self, item: QtWidgets.QListWidgetItem):
        nick = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if nick:
            self.participant_clicked.emit(self.jid, str(nick))

    def _on_muc_context_menu(self, position: QtCore.QPoint):
        item = self._users_list.itemAt(position)
        if not item:
            return
        nick = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if nick:
            self.participant_context_requested.emit(
                self.jid, str(nick),
                self._users_list.viewport().mapToGlobal(position))

    @staticmethod
    def _status_icon(show: str):
        try:
            from stanza_im.ui.icons import icons
            if icons is not None:
                return QtGui.QIcon(icons.get_status_icon(show))
        except Exception:
            pass
        return QtGui.QIcon()

    @staticmethod
    def _chat_icon(filename: str) -> QtGui.QIcon:
        for directory in (ACTIONS_DIR_16, ACTIONS_DIR_22, CATEGORIES_DIR_16,
                          STATUS_DIR_32, PLACES_DIR_22):
            pix = QtGui.QPixmap(os.path.join(directory, filename))
            if not pix.isNull():
                return QtGui.QIcon(pix)
        return QtGui.QIcon()

    def _set_input_height(self, height: int):
        height = max(40, min(240, int(height)))
        if height != self._input_height:
            self._input_height = height
            self._input.setFixedHeight(height)
            self.input_height_changed.emit(self.jid, height)

    def _choose_file_send(self, method: str):
        from PyQt6.QtWidgets import QFileDialog
        paths, _filter = QFileDialog.getOpenFileNames(self,
                                                      tr("chat_send_file"))
        paths = [p for p in (paths or []) if p]
        if paths:
            self.files_upload_requested.emit(self.jid, paths, method)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()
                 if url.isLocalFile()]
        if paths:
            self.files_upload_requested.emit(self.jid, paths, "http")
        event.acceptProposedAction()

    def _handle_pasted_image(self) -> bool:
        """Ctrl+V in the input: if the clipboard holds an image, offer it as
        a chat file upload (same flow as drag-and-drop).  Returns True when
        the paste was consumed as an image."""
        clipboard = QtGui.QGuiApplication.clipboard()
        mime = clipboard.mimeData()
        if not mime or not mime.hasImage():
            return False
        image = clipboard.image()
        path = self._clipboard_image_to_tempfile(image)
        if not path:
            return False
        self.files_upload_requested.emit(self.jid, [path], "http")
        return True

    @staticmethod
    def _clipboard_image_to_tempfile(image: QtGui.QImage) -> str | None:
        """Save a clipboard image to a throwaway PNG for upload."""
        fd, path = tempfile.mkstemp(prefix="stanza-paste-", suffix=".png")
        os.close(fd)
        ok = False
        try:
            ok = bool(image.save(path, "PNG"))
        finally:
            if not ok:
                try:
                    os.remove(path)
                except OSError:
                    pass
        return path if ok else None

    @staticmethod
    def _bookmark_icon():
        try:
            from stanza_im.ui.icons import icons
            if icons is not None:
                return QtGui.QIcon(icons.get_category_icon("bookmarks"))
        except Exception:
            pass
        return QtGui.QIcon()

    # ── Misc API ──────────────────────────────────────────────────

    def set_show_avatars(self, show: bool):
        self._show_avatars = show

    def set_participant_font(self, family: str = "", size: int = 0):
        """Set the MUC participant sidebar font (empty = system default)."""
        base = QtGui.QFont(QtWidgets.QApplication.font())
        if family:
            base.setFamily(family)
        if size > 0:
            base.setPointSize(int(size))
        self._users_list.setFont(base)
        if self.is_muc:
            self._render_muc_users()

    def set_colored_muc_nicks(self, enabled: bool):
        """Toggle per-participant colorized nicknames in this MUC tab."""
        self._colored_muc_nicks = bool(enabled)
        if self.is_muc:
            self._refresh_nick_colors()
            self._render_muc_users()
            self._render_all()

    def _sender_color(self, entry: dict) -> str:
        """Return the color for the sender nick of a message (MUC only)."""
        if not (self.is_muc and self._colored_muc_nicks):
            return ""
        nick = entry.get("sender", "")
        for user in self._users:
            if self._same_nick(user.get("nick", ""), nick):
                return self._nick_colors.color_for(
                    self._user_color_key(user))
        return self._nick_colors.color_for(self._color_key(nick))

    def _color_key(self, nick: str, real_jid: str = "") -> str:
        key = normalize_nick(nick or "")
        if real_jid:
            key = f"{key}|{real_jid}"
        return key

    def _user_color_key(self, user: dict) -> str:
        return self._color_key(user.get("nick", ""),
                               user.get("real_jid", ""))

    def _refresh_nick_colors(self) -> None:
        """Rebuild the nick color map for currently present users."""
        active = set()
        for user in self._users:
            key = self._user_color_key(user)
            active.add(key)
            self._nick_colors.color_for(key)
        if self._self_nick:
            active.add(normalize_nick(self._self_nick))
            self._nick_colors.color_for(normalize_nick(self._self_nick))
        self._nick_colors.prune(active)

    def set_chat_options(self, options):
        self._send_ctrl_enter = bool(options.get("send_ctrl_enter", False))
        self._send_typing_notifications = bool(options.get("send_typing_notifications", True))
        self._send_activity_notifications = bool(options.get("send_activity_notifications", True))
        self._show_status = bool(options.get("show_status", True))
        self._status_label.setVisible(False)
        self.set_show_avatars(bool(options.get("show_avatars", True)))
        self._set_input_height(int(options.get("input_height", self._input_height) or 60))
        self.set_text_scale(float(options.get("text_scale", 1.0) or 1.0))

    def set_text_scale(self, factor: float):
        """Re-apply the text-scale factor (reopened tabs keep the zoom)."""
        self._view.set_chat_zoom(factor)

    def mark_delivered(self, message_id: str) -> None:
        if not message_id:
            return
        for entry in reversed(self._messages):
            if entry.get("message_id") == message_id:
                entry["delivered"] = True
                self._view.mark_message_delivered(message_id)
                return

    def refresh_avatar_for_sender(self, sender: str, sender_jid: str) -> None:
        """Refresh only messages belonging to a participant avatar update."""
        changed = False
        for entry in self._history + self._messages:
            if self._same_nick(entry.get("sender", ""), sender):
                if entry.get("sender_jid", "") != sender_jid:
                    entry["sender_jid"] = sender_jid
                    changed = True
        if changed:
            self._view.update_sender_avatar(
                sender, self._user_icon("incoming", sender_jid, sender))

    def refresh_avatars(self):
        """Update avatar images in place after a participant avatar cached.

        Drives the WebEngine ``img.avatar`` elements directly instead of
        clearing and reloading the whole chat document (which would wedge
        live rendering if the reload fails).
        """
        for entry in self._history + self._messages:
            sender = entry.get("sender", "")
            if entry.get("direction") != "incoming" or not sender:
                continue
            self._view.update_sender_avatar(
                sender,
                self._user_icon("incoming", entry.get("sender_jid", ""),
                                sender))

    def set_bookmarked(self, bookmarked: bool):
        self._bookmarked = bool(bookmarked)
        label = tr("bookmark_remove" if self._bookmarked else "bookmark_add")
        if self._bookmark_action is not None:
            self._bookmark_action.setText(label)
        if getattr(self, "_bookmark_btn", None) is not None:
            self._bookmark_btn.setChecked(self._bookmarked)
            self._bookmark_btn.setToolTip(label)

    def set_subject(self, subjects: list[tuple[str, str]] | None = None):
        """Display the MUC subject in the read-only header field.

        *subjects* is an ordered list of ``(lang, text)`` pairs; the default
        (empty ``lang``) variant wins, otherwise the first non-empty one.
        """
        self._subjects = list(subjects or [])
        text = ""
        for lang, candidate in self._subjects:
            if not lang and candidate:
                text = candidate
                break
        if not text:
            for lang, candidate in self._subjects:
                if candidate:
                    text = candidate
                    break
        self._subject_edit.setText(text)

    def _subject_tooltip(self, global_pos: QtCore.QPoint) -> None:
        """Show the MUC subject via the rich tooltip popup."""
        text = self._subject_edit.text().strip()
        if not text:
            tooltip_mod.hide()
            return
        from stanza_im.include.utils import escape_html
        tooltip_mod.show(global_pos, escape_html(text))

    def reload_theme(self, variant: str = ""):
        self._view.load_theme(variant)
        self._render_all()

    def set_typing(self, name: str, is_typing: bool):
        if not self._show_status:
            return
        self._view.set_typing_indicator(
            tr("chat_is_typing", name=name) if is_typing else "")

    def set_status_text(self, text: str):
        """Override the header status label (e.g. MUC participant count)."""
        self._status_label.setText(text)

    def clear_messages(self):
        self._view.clear()

    def rerender_messages(self):
        """Re-render history and messages (e.g. preview settings changed)."""
        self._render_all()

    def focus_input(self):
        self._input.setFocus()
