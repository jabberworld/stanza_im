"""Individual chat widget — one per conversation (1-on-1 or groupchat).

Renders a local history window (SQLite tail + live messages) inside the
chat view, grows it backwards on scroll-to-top or viewport growth, shows a
""load from server"" marker after the local history was cleared, and lists
MUC participants in a side panel.
"""
from __future__ import annotations

import time
import webbrowser
import logging
import uuid

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.avatars import (
    avatar_data_uri, avatar_file_data_uri, default_avatar, default_avatar_uri,
)
from stanza_im.ui.chat_view import ChatView
from stanza_im.ui.chat_themes import ChatThemeFactory
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
    typing_changed = QtCore.pyqtSignal(str, bool)  # jid, is_typing
    link_clicked = QtCore.pyqtSignal(str)
    clear_history_requested = QtCore.pyqtSignal(str)       # jid
    server_history_requested = QtCore.pyqtSignal(str, str)  # jid, since_ts
    bookmark_toggled = QtCore.pyqtSignal(str)              # MUC room
    set_subject_requested = QtCore.pyqtSignal(str)         # MUC room
    participant_clicked = QtCore.pyqtSignal(str, str)      # room, nick
    participant_context_requested = QtCore.pyqtSignal(
        str, str, QtCore.QPoint)                            # room, nick, global pos

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
        self._bookmarked = False
        self._bookmark_action = None
        self._subjects: list[tuple[str, str]] = []
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
        self._name_label.setVisible(not self.is_muc)
        self._status_label = QtWidgets.QLabel("")
        self._status_label.setStyleSheet("color: gray; font-size: 11px;")
        self._status_label.setVisible(not self.is_muc)
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

        self._history_btn = QtWidgets.QToolButton(self)
        self._history_btn.setText("\u2026")
        self._history_btn.setToolTip(tr("history_menu_tooltip"))
        self._history_btn.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self._history_btn.setMenu(self._history_menu)
        header.addWidget(self._history_btn)
        layout.addLayout(header)

        # Chat view + resizable MUC participant sidebar
        chat_col = QtWidgets.QVBoxLayout()
        chat_col.setContentsMargins(0, 0, 0, 0)
        chat_col.setSpacing(0)
        self._view = ChatView(theme)
        self._view.link_clicked.connect(self._open_link)
        self._view.link_clicked.connect(self.link_clicked)
        chat_col.addWidget(self._view, stretch=1)

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
        chat_col.addLayout(input_row)
        chat_panel = QtWidgets.QWidget(self)
        chat_panel.setLayout(chat_col)

        self._users_list = QtWidgets.QListWidget()
        self._users_list.setMinimumWidth(120)
        self._users_list.setMaximumWidth(420)
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
        if url == "mam://load":
            self.load_more_from_server()
            return
        low = url.lower()
        if low.startswith(("http://", "https://", "mailto:")):
            webbrowser.open(url)
            return
        self.link_clicked.emit(url)

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
        return super().eventFilter(obj, event)

    def _send(self):
        text = self._input.toPlainText()
        if not text:
            return
        self._typing_timer.stop()
        self.typing_changed.emit(self.jid, False)
        self.message_sent.emit(self.jid, text)
        self._input.clear()

    # ── Message rendering ─────────────────────────────────────────

    def add_message(self, sender: str, body: str, timestamp: str,
                    direction: str = "incoming", is_next: bool = False,
                    sender_jid: str = "", archive_id: str = "",
                    message_id: str = "", unstyled: bool = False):
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
                  "message_id": message_id or (uuid.uuid4().hex if direction == "outgoing" else ""),
                  "delivered": False, "unstyled": unstyled}
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

    def _render_entry(self, entry: dict):
        from stanza_im.include.utils import ts_to_time
        self._view.add_message(sender=entry["sender"], body=entry["body"],
                               timestamp=ts_to_time(entry.get("timestamp", "")),
                                direction=entry.get("direction", "incoming"),
                                is_next=entry.get("is_next", False),
                                message_id=entry.get("message_id", ""),
                                unstyled=entry.get("unstyled", False),
                                raw_timestamp=entry.get("timestamp", ""),
                                 user_icon_path=self._user_icon(
                                     entry.get("direction", "incoming"),
                                     entry.get("sender_jid", ""),
                                     entry.get("sender", "")))

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
             "raw_timestamp": entry.get("timestamp", "")}
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
        from stanza_im.core import history

        self._server_fetching = False
        if stored < 0:
            self._hist_loading = False
            return
        if stored > 0:
            self._server_exhausted = False
            before = self.oldest_ts()
            if before:
                rows = history.load_older_timestamp(
                    self.jid, before, self._window_size)
                # These rows belong to the MAM page just stored. Do not
                # expose the same SQLite rows through a second paging path;
                # the next page is controlled by the MAM archive cursor.
                self.prepend_history(rows, True)
                self._db_exhausted = True
            else:
                self._history = history.load_history(
                    self.jid, limit=self._window_size)
                self._merge_live_history()
                self._db_exhausted = True
                self._anchor_bottom = True
                self._render_all()
        else:
            self._hist_loading = False
            self._server_exhausted = True

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
        from stanza_im.core import history
        size = size or self._window_size * 2
        entries = history.load_history(self.jid, limit=size)
        self._preserve_fraction = self._view.scroll_fraction()
        self._hist_loading = False
        self._cleared = False
        self._server_fetching = False
        self._history = entries
        self._db_exhausted = (not entries
                              or not history.older_available_timestamp(
                                  self.jid, self.oldest_ts()))
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
        from stanza_im.core import history
        self._hist_loading = True
        before_ts = self.oldest_ts()
        if before_ts and history.older_available_timestamp(self.jid, before_ts):
            rows = history.load_older_timestamp(
                self.jid, before_ts, self._batch_size())
            exhausted = not rows
            if rows:
                next_before = rows[0].get("timestamp", "")
                exhausted = not (next_before and
                                 history.older_available_timestamp(
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
        self._render_muc_users()

    def set_self_nick(self, nick: str):
        self._self_nick = nick or self._self_nick
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

    def set_chat_options(self, options):
        self._send_ctrl_enter = bool(options.get("send_ctrl_enter", False))
        self._send_typing_notifications = bool(options.get("send_typing_notifications", True))
        self._send_activity_notifications = bool(options.get("send_activity_notifications", True))
        self._show_status = bool(options.get("show_status", True))
        self._status_label.setVisible(self._show_status and not self.is_muc)
        self.set_show_avatars(bool(options.get("show_avatars", True)))

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
        """Re-render messages after a participant avatar was cached."""
        self._preserve_fraction = self._view.scroll_fraction()
        self._anchor_bottom = False
        self._render_all()

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

    def focus_input(self):
        self._input.setFocus()
