"""Main application window.

Manages the three-page stacked widget (login / splash / roster) and the
optional embedded chat window.  Wires the XMPP client, tray, roster and
chat together.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

from PyQt6 import QtCore, QtGui, QtWidgets

from jabbim.i18n import tr, load as load_i18n
from jabbim.include.avatars import save_avatar
from jabbim.include.enumerators import populate_translations, show_to_icon_key
from jabbim.include.constants import APP_NAME, VERSION
from jabbim.core.storage import Config
from jabbim.ui.icons import init_icons
from jabbim.ui.login_widget import LoginWidget
from jabbim.ui.roster_widget import RosterWidget, UserItem
from jabbim.ui.chat_window import ChatWindow
from jabbim.ui.chat_themes import ChatThemeFactory
from jabbim.ui.tray import TrayIcon

logger = logging.getLogger(__name__)

_PAGE_LOGIN = 0
_PAGE_SPLASH = 1
_PAGE_ROSTER = 2


class MainWindow(QtWidgets.QMainWindow):
    """Top-level window that owns the roster, chat window, tray and XMPP client."""

    def __init__(self, app: QtWidgets.QApplication):
        super().__init__()
        self.app = app

        # ── Initialise subsystems ─────────────────────────────────
        load_i18n()
        populate_translations(tr)
        self._icons = init_icons()
        self._config = Config()

        from jabbim.ui.tray import build_app_icon
        app.setWindowIcon(build_app_icon())
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(280, 500)
        self._restore_window_geometry()

        # ── Theme factory (shared by all chat views) ──────────────
        self._theme_factory = ChatThemeFactory()

        # ── Chat window (standalone) ─────────────────────────────
        self._chat_window = ChatWindow(self._theme_factory)
        self._chat_window.set_tab_title_length(
            self._config.chat.tab_title_length)
        self._chat_window.message_to_send.connect(self._on_message_send)
        self._chat_window.groupchat_message_to_send.connect(self._on_groupchat_send)
        self._chat_window.tab_focused.connect(self._on_tab_focused)
        self._chat_window.tab_closed.connect(self._on_chat_closed)
        self._chat_window.muc_leave_requested.connect(self._on_muc_leave)
        self._chat_window.clear_history_requested.connect(self._on_clear_history)
        self._chat_window.server_history_requested.connect(self._on_server_history)
        self._chat_window.bookmark_toggled.connect(self._toggle_bookmark)
        self._chat_window.participant_clicked.connect(
            self._on_muc_participant_clicked)
        self._chat_window.participant_context_requested.connect(
            self._on_muc_participant_context)
        self._chat_window.hide()

        # ── Tray ─────────────────────────────────────────────────
        self._tray = TrayIcon(self)
        self._tray.show_requested.connect(self._toggle_visibility)
        self._tray.quit_requested.connect(self._quit)
        self._set_tray_status_icon(self._config.last_status)
        self._tray.show()

        # ── UI ───────────────────────────────────────────────────
        self._build_ui()

        # ── XMPP client (created on connect) ─────────────────────
        self._client = None

        # ── State ────────────────────────────────────────────────
        self._visible = True
        self._unread_total = 0
        self._muc_users: dict[str, dict[str, dict]] = {}
        self._muc_self_nicks: dict[str, str] = {}
        self._conference_roster: set[str] = set()
        self._bookmarks: dict[str, dict] = {}
        self._vcard_requested: set[str] = set()
        self._pending_profile: set[str] = set()

        self._chat_window.typing_changed.connect(self._on_typing_local)

        # ── Auto-connect (if configured) delayed until loop runs ──
        QtCore.QTimer.singleShot(100, self.try_auto_connect)

    # ── UI construction ───────────────────────────────────────────

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self._build_menu()

        self._stack = QtWidgets.QStackedWidget()
        main_layout.addWidget(self._stack)

        # Page 0: Login
        self._login = LoginWidget()
        self._login.login_requested.connect(self._on_login)
        self._stack.addWidget(self._login)

        # Page 1: Splash / connecting
        splash = QtWidgets.QWidget()
        splash_layout = QtWidgets.QVBoxLayout(splash)
        splash_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._splash_label = QtWidgets.QLabel("")
        self._splash_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        splash_layout.addWidget(self._splash_label)
        self._splash_progress = QtWidgets.QProgressBar()
        self._splash_progress.setRange(0, 0)  # indeterminate
        splash_layout.addWidget(self._splash_progress)
        self._splash_cancel = QtWidgets.QPushButton("Cancel")
        self._splash_cancel.clicked.connect(self._on_connect_cancel)
        splash_layout.addWidget(self._splash_cancel, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(splash)

        # Page 2: Roster
        roster_page = QtWidgets.QWidget()
        roster_layout = QtWidgets.QVBoxLayout(roster_page)
        roster_layout.setContentsMargins(0, 0, 0, 0)

        # Search bar
        search_bar = QtWidgets.QHBoxLayout()
        self._search_input = QtWidgets.QLineEdit()
        self._search_input.setPlaceholderText(tr("roster_search_placeholder"))
        self._search_input.textChanged.connect(self._on_search)
        search_bar.addWidget(self._search_input)
        roster_layout.addLayout(search_bar)

        # Roster widget
        self._roster = RosterWidget()
        self._roster.contact_double_clicked.connect(self._on_contact_open)
        self._roster.contact_context_menu.connect(self._on_contact_context)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._roster)
        roster_layout.addWidget(scroll, stretch=1)

        # Status bar at bottom
        status_bar = QtWidgets.QHBoxLayout()
        self._status_combo = QtWidgets.QComboBox()
        for key in ("online", "chat", "away", "xa", "dnd", "offline"):
            icon = QtGui.QIcon(self._icons.get_status_icon(key))
            self._status_combo.addItem(icon, tr(f"status_{key}"), key)
        self._status_combo.currentIndexChanged.connect(self._on_status_change)
        status_bar.addWidget(self._status_combo, stretch=1)
        roster_layout.addLayout(status_bar)

        self._stack.addWidget(roster_page)

        # Start on login page
        self._stack.setCurrentIndex(_PAGE_LOGIN)

    def _build_menu(self):
        """Application menu bar: file actions, bookmarks and help."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu(tr("menu_file"))
        add_contact = file_menu.addAction(tr("menu_add_contact"))
        add_contact.triggered.connect(self._on_add_contact)
        join_room = file_menu.addAction(tr("menu_join_groupchat"))
        join_room.triggered.connect(self._on_join_groupchat_dialog)
        my_vcard = file_menu.addAction(tr("menu_edit_my_vcard"))
        my_vcard.triggered.connect(self._edit_my_vcard)
        file_menu.addSeparator()
        prefs = file_menu.addAction(tr("menu_preferences"))
        prefs.triggered.connect(self._on_preferences)
        file_menu.addSeparator()
        quit_act = file_menu.addAction(tr("menu_quit"))
        quit_act.triggered.connect(self._quit)

        self._bookmarks_menu = menubar.addMenu(tr("menu_bookmarks"))
        self._bookmarks_menu.aboutToShow.connect(self._refresh_bookmarks_menu)

        help_menu = menubar.addMenu(tr("menu_help"))
        about = help_menu.addAction(tr("menu_about"))
        about.triggered.connect(self._on_about)

    # ── Menu actions ─────────────────────────────────────────────

    def _on_add_contact(self):
        if not self._client:
            return
        jid, ok = QtWidgets.QInputDialog.getText(self, tr("menu_add_contact"),
                                                 tr("login_title"))
        if not ok or not jid.strip():
            return
        name, ok = QtWidgets.QInputDialog.getText(self, tr("menu_add_contact"),
                                                  "Name:")
        name = name.strip() if ok else ""
        self._client.add_contact(jid.strip(), name)
        self._client.request_roster()

    def _on_join_groupchat_dialog(self):
        if not self._client:
            return
        room, ok = QtWidgets.QInputDialog.getText(self, tr("menu_join_groupchat"),
                                                  "Room JID:")
        if not ok or not room.strip():
            return
        nick = self._client.jid_str.split("@")[0]
        nick, ok = QtWidgets.QInputDialog.getText(self, tr("menu_join_groupchat"),
                                                  "Nickname:", text=nick)
        if not ok or not nick.strip():
            return
        self._join_muc(room.strip(), nick.strip())

    def _refresh_bookmarks_menu(self):
        """Refresh the server-side conference bookmarks before displaying it."""
        self._bookmarks_menu.clear()
        if not self._client:
            action = self._bookmarks_menu.addAction(tr("menu_bookmarks_empty"))
            action.setEnabled(False)
            return
        loading = self._bookmarks_menu.addAction(tr("bookmarks_loading"))
        loading.setEnabled(False)
        self._start_task(self._load_bookmarks())

    async def _load_bookmarks(self):
        bookmarks = await self._client.list_bookmarks()
        self._bookmarks = {item["jid"]: item for item in bookmarks}
        self._rebuild_bookmarks_menu()
        for room in self._muc_self_nicks:
            chat = self._chat_window.get_chat(room)
            if chat:
                chat.set_bookmarked(room in self._bookmarks)

    def _rebuild_bookmarks_menu(self):
        self._bookmarks_menu.clear()
        if not self._bookmarks:
            action = self._bookmarks_menu.addAction(tr("menu_bookmarks_empty"))
            action.setEnabled(False)
            return
        for room, bookmark in sorted(self._bookmarks.items()):
            label = room.split("@", 1)[0]
            submenu = self._bookmarks_menu.addMenu(label)
            join = submenu.addAction(tr("bookmark_join"))
            join.triggered.connect(
                lambda checked=False, item=bookmark: self._join_bookmark(item))
            auto = submenu.addAction(tr("bookmark_autojoin"))
            auto.setCheckable(True)
            auto.setChecked(bool(bookmark.get("autojoin")))
            auto.toggled.connect(
                lambda value, item=bookmark: self._set_bookmark_autojoin(item, value))
            remove = submenu.addAction(tr("bookmark_remove"))
            remove.triggered.connect(
                lambda checked=False, jid=room: self._remove_bookmark(jid))

    def _join_bookmark(self, bookmark: dict):
        room = bookmark.get("jid", "")
        if not room:
            return
        nick = bookmark.get("nick", "") or self._client.jid_str.split("@", 1)[0]
        self._join_muc(room, nick, bookmark.get("password", ""))

    def _set_bookmark_autojoin(self, bookmark: dict, autojoin: bool):
        if not self._client:
            return
        bookmark["autojoin"] = bool(autojoin)
        self._start_task(self._client.save_bookmark(
            bookmark["jid"], bookmark.get("nick", ""),
            bookmark.get("password", ""), autojoin=autojoin))

    def _remove_bookmark(self, room: str):
        if not self._client:
            return
        self._bookmarks.pop(room, None)
        chat = self._chat_window.get_chat(room)
        if chat:
            chat.set_bookmarked(False)
        self._start_task(self._client.remove_bookmark(room))
        self._rebuild_bookmarks_menu()

    def _toggle_bookmark(self, room: str):
        if not self._client:
            return
        if room in self._bookmarks:
            self._remove_bookmark(room)
            return
        nick = self._muc_self_nicks.get(room, self._client.jid_str.split("@", 1)[0])
        bookmark = {"jid": room, "nick": nick, "password": "", "autojoin": False}
        self._bookmarks[room] = bookmark
        chat = self._chat_window.get_chat(room)
        if chat:
            chat.set_bookmarked(True)
        self._start_task(self._client.save_bookmark(
            room, nick, "", autojoin=False))

    def _sync_conference_roster(self, room: str):
        """Represent an active MUC using the normal roster row renderer."""
        if not self._client or room not in self._muc_self_nicks:
            return
        nick = self._muc_self_nicks[room]
        info = self._muc_users.get(room, {}).get(nick, {})
        contact = self._client.get_contact(room)
        status = info.get("show", "online") or "online"
        status_message = info.get("status", "")
        self._roster.remove_user(room)
        self._roster.add_user(UserItem(
            jid=room,
            name=room.split("@", 1)[0],
            group=tr("roster_group_conferences"),
            status=status,
            status_message=status_message,
            icon_key=status if status in ("online", "chat", "away", "xa", "dnd", "offline")
            else "online",
            avatar_path=getattr(contact, "avatar_path", None),
        ))
        self._conference_roster.add(room)
        self._recount_groups()
        self._roster.sort_and_update()

    def _sync_all_conference_roster(self):
        for room in self._muc_self_nicks:
            self._sync_conference_roster(room)

    def _join_muc(self, room: str, nick: str, password: str = ""):
        if not self._client:
            return
        display_name = self._muc_display_name(room)
        is_new = not self._chat_window.has_chat(room)
        if is_new:
            self._chat_window.open_groupchat(room, nick, display_name)
        self._muc_self_nicks[room] = nick
        self._muc_users.setdefault(room, {})[nick] = {
            "nick": nick, "show": "online", "status": "",
            "role": "", "affiliation": "",
        }
        self._client.join_muc(room, nick, password=password, save_bookmark=False)
        chat = self._chat_window.get_chat(room)
        if chat:
            if is_new:
                self._load_history(room)
            chat.set_self_nick(nick)
            chat.update_muc_users(list(self._muc_users[room].values()),
                                  self_nick=nick)
            from jabbim.include.utils import format_time
            chat.add_status(f"Joined as {nick}", format_time())
            chat.set_bookmarked(room in self._bookmarks)
        self._request_vcard(room)
        self._client.get_muc_info(room)
        self._sync_conference_roster(room)

    def _on_muc_leave(self, room: str):
        if self._client:
            self._client.leave_muc(room)
        self._muc_users.pop(room, None)
        self._muc_self_nicks.pop(room, None)
        if room in self._conference_roster:
            self._roster.remove_user(room)
            self._conference_roster.discard(room)
            self._recount_groups()
            self._roster.sort_and_update()
        from jabbim.core import history
        history.close(room)

    def _on_muc_joined(self, room: str, subject: str, occupants):
        chat = self._chat_window.get_chat(room)
        if not chat:
            info = self._client.groupchats.get(room) if self._client else None
            nick = info.nick if info else self._client.jid_str.split("@", 1)[0]
            self._muc_self_nicks[room] = nick
            chat = self._chat_window.open_groupchat(
                room, nick, self._muc_display_name(room, subject))
            self._load_history(room)
            self._request_vcard(room)
        users = self._muc_users.setdefault(room, {})
        for occ in occupants or []:
            if isinstance(occ, str):
                nick = occ
            elif isinstance(occ, (tuple, list)) and occ:
                nick = occ[0]
            else:
                nick = str(occ)
            users.setdefault(nick, {
                "nick": nick, "show": "online", "status": "",
                "role": "", "affiliation": "",
            })
        self_nick = self._muc_self_nicks.get(room, "")
        chat.set_self_nick(self_nick)
        chat.update_muc_users(list(users.values()), self_nick=self_nick)
        title = subject or ""
        title += (" · " if title else "") + tr("muc_participants_count",
                                               n=len(users))
        chat.set_status_text(title)
        self._chat_window.set_chat_title(
            room, self._muc_display_name(room, subject))
        chat.refresh_history()
        chat.set_bookmarked(room in self._bookmarks)
        self._sync_conference_roster(room)

    def _on_muc_join_error(self, room: str, condition: str, code: str):
        chat = self._chat_window.get_chat(room)
        if not chat:
            return
        from jabbim.include.utils import format_time
        message = (tr("muc_join_waiting") if condition == "timeout"
                   else tr("muc_join_failed", reason=condition or code))
        chat.add_status(message, format_time())

    def _on_muc_info_received(self, room: str, name: str):
        if room in self._muc_self_nicks and name:
            self._chat_window.set_chat_title(room, name)

    def _muc_display_name(self, room: str, preferred: str = "") -> str:
        if preferred:
            return preferred
        if self._client:
            contact = self._client.get_contact(room)
            card = getattr(contact, "vcard", None) or {}
            name = card.get("fn") or card.get("nickname") or ""
            if name:
                return name
        return room.split("@", 1)[0]

    def _on_preferences(self):
        from jabbim.ui.preferences import PreferencesDialog
        dlg = PreferencesDialog(self._config, self._theme_factory, self)
        dlg.settings_applied.connect(self._on_settings_applied)
        dlg.exec()

    def _on_settings_applied(self):
        """Apply saved settings to live widgets."""
        variant = self._config.chat.theme
        self._chat_window.reload_themes(variant)
        self._chat_window.set_show_avatars(self._config.chat.show_avatars)
        self._chat_window.set_tab_title_length(
            self._config.chat.tab_title_length)
        self._set_tray_status_icon(self._config.last_status)

    def _on_about(self):
        QtWidgets.QMessageBox.about(self, tr("about_title"),
                                    f"{APP_NAME} {VERSION}")

    # ── Login / Connect ───────────────────────────────────────────

    def _on_login(self, jid: str, password: str, show: str):
        """Handle login form submission."""
        self._stack.setCurrentIndex(_PAGE_SPLASH)
        self._splash_label.setText(tr("login_connecting"))

        from jabbim.core.client import JabberClient
        self._client = JabberClient(jid, password)
        self._connect_client_signals()

        self._start_task(self._connect_async(jid, show))

    def _start_task(self, coro):
        """Schedule a coroutine on the shared asyncio loop."""
        loop = asyncio.get_event_loop()
        return loop.create_task(coro)

    def try_auto_connect(self):
        """Start automatically when the saved config requests it."""
        if self._login.should_auto_connect():
            jid, pw, show = self._login.get_credentials()
            self._on_login(jid, pw, show)

    async def _connect_async(self, jid: str, show: str):
        try:
            await self._client.connect_async()
            self._client.send_presence(show=show)
            self._splash_label.setText(tr("login_connected"))
            self._splash_progress.setRange(0, 100)
            self._splash_progress.setValue(100)
            # Switch to roster page after a brief delay
            QtCore.QTimer.singleShot(500, lambda: self._stack.setCurrentIndex(_PAGE_ROSTER))
        except Exception as e:
            logger.exception("Connection failed")
            self._login.set_error(tr("login_connection_error", error=str(e)))
            self._stack.setCurrentIndex(_PAGE_LOGIN)

    def _on_connect_cancel(self):
        if self._client:
            self._start_task(self._client.disconnect())
        self._stack.setCurrentIndex(_PAGE_LOGIN)
        self._login.set_status_text("")

    # ── XMPP event wiring ────────────────────────────────────────

    def _connect_client_signals(self):
        c = self._client
        c.on("session_started", self._on_session_started)
        c.on("roster_received", self._on_roster_received)
        c.on("roster_item_added", self._on_roster_item_added)
        c.on("roster_item_removed", self._on_roster_item_removed)
        c.on("presence_changed", self._on_presence_changed)
        c.on("message_received", self._on_message_received)
        c.on("groupchat_message", self._on_groupchat_message)
        c.on("groupchat_presence", self._on_groupchat_presence)
        c.on("auth_failed", self._on_auth_failed)
        c.on("disconnected", self._on_disconnected)
        c.on("subscribed", self._on_subscribed)
        c.on("vcard_received", self._on_vcard_received)
        c.on("typing", self._on_typing)
        c.on("receipt_delivered", self._on_receipt_delivered)
        c.on("muc_joined", self._on_muc_joined)
        c.on("muc_info_received", self._on_muc_info_received)
        c.on("muc_join_error", self._on_muc_join_error)
        c.on("mam_unavailable", self._on_mam_unavailable)
        # roster removals are delivered via roster_item_removed (from client)

    def _on_session_started(self):
        logger.info("Session started, roster arriving...")
        self._set_tray_status_icon(self._config.last_status)

    def _on_auth_failed(self):
        self._login.set_error(tr("login_auth_failed"))
        self._stack.setCurrentIndex(_PAGE_LOGIN)

    def _on_disconnected(self):
        self._tray.show_message(APP_NAME, "Disconnected from server")
        self._tray.set_icon(QtGui.QIcon(self._icons.get_status_icon("offline")))

    def _set_tray_status_icon(self, show: str):
        """Use the presence status icon in the tray (right away)."""
        key = show if show in ("online", "chat", "away", "xa", "dnd", "offline") \
            else "offline"
        self._tray.set_icon(QtGui.QIcon(self._icons.get_status_icon(key)))

    # ── Roster management ─────────────────────────────────────────

    def _on_roster_received(self, items):
        """Full roster arrived (initial load or server refresh)."""
        self._rebuild_roster(items)
        self._sync_all_conference_roster()
        self._recount_groups()
        self._roster.sort_and_update()

    def _on_roster_item_added(self, item):
        self._add_roster_item(item)
        self._roster.sort_and_update()

    def _on_roster_item_removed(self, jid: str):
        self._roster.remove_user(jid)
        self._roster.sort_and_update()

    def _rebuild_roster(self, items):
        self._roster.clear()
        for item in items:
            self._add_roster_item(item)

    def _add_roster_item(self, item: dict):
        jid = item["jid"]
        name = item["name"] or jid.split("@")[0]
        groups = item["groups"]
        if not groups:
            groups = [tr("roster_group_ungrouped")]
        contact = self._client.get_contact(jid) if self._client else None
        show = contact.show if contact else "offline"
        status = contact.status if contact else ""
        for group in groups:
            user = UserItem(
                jid=jid,
                name=name,
                group=group,
                status=show,
                status_message=status,
                icon_key=show_to_icon_key(show),
            )
            self._roster.add_user(user)
        self._request_vcard(jid)

    def _request_vcard(self, jid: str):
        """Request a cached or fresh vCard; the client enforces the TTL."""
        if not self._client:
            return
        self._vcard_requested.add(jid)
        self._client.get_vcard(jid)

    def _on_vcard_received(self, jid: str, card: dict):
        path = card.get("avatar_path") or ""
        raw = card.get("photo")
        if raw:
            try:
                path = save_avatar(jid, raw)
            except Exception:
                path = ""
        if path:
            contact = self._client.get_contact(jid) if self._client else None
            if contact:
                contact.avatar_path = path
            self._roster.update_user(jid, avatar_path=path)
        if jid in self._conference_roster:
            self._sync_conference_roster(jid)
        if jid in self._muc_self_nicks:
            title = card.get("fn") or card.get("nickname") or ""
            if title:
                self._chat_window.set_chat_title(jid, title)
        for room, users in self._muc_users.items():
            changed = False
            for nick, info in users.items():
                virtual_jid = f"{room}/{nick}"
                if (info.get("real_jid", "").split("/", 1)[0] == jid
                        or info.get("avatar_jid", "") == jid
                        or virtual_jid == jid):
                    info["avatar_jid"] = jid
                    info["avatar_path"] = path
                    changed = True
            if changed:
                chat = self._chat_window.get_chat(room)
                if chat:
                    chat.update_muc_users(
                        list(users.values()),
                        self_nick=self._muc_self_nicks.get(room, ""))
                    chat.refresh_avatars()
        if jid in self._pending_profile:
            self._pending_profile.discard(jid)
            self._open_vcard_info(jid, card)

    def _open_vcard_info(self, jid: str, card: dict):
        from jabbim.ui.vcard_dialog import VCardInfoDialog
        dlg = VCardInfoDialog(jid, card)
        dlg.exec()

    def _show_profile(self, jid: str):
        """Show the contact's vCard (fetching it if not yet known)."""
        if not self._client:
            return
        if "/" in jid:
            self._pending_profile.add(jid)
            self._request_vcard(jid)
            return
        contact = self._client.get_contact(jid) if self._client else None
        card = getattr(contact, "vcard", None) if contact else None
        if isinstance(card, dict) and (card.get("fn") or card.get("nickname") or card.get("email")):
            self._open_vcard_info(jid, card)
        else:
            self._pending_profile.add(jid)
            self._request_vcard(jid)

    def _edit_my_vcard(self):
        if not self._client:
            return
        self._start_task(self._fetch_and_edit_my_vcard())

    async def _fetch_and_edit_my_vcard(self):
        from jabbim.include.vcard import parse_vcard
        from jabbim.ui.vcard_dialog import VCardEditDialog
        my = self._client.jid_str
        card = {}
        try:
            iq = await self._client.xmpp.plugin["xep_0054"].get_vcard(my)
            card = parse_vcard(iq)
        except Exception:
            pass
        if isinstance(card, dict) and "jid" in card:
            card["jid"] = my
        dlg = VCardEditDialog(card or {"jid": my})
        if not dlg.exec():
            return
        await self._client.set_own_vcard(dlg.collect())
        QtWidgets.QMessageBox.information(self, APP_NAME,
                                          tr("vcard_saved"))

    def _recount_groups(self):
        """Recount online/total per group after presence changes."""
        counts: dict[str, list[int]] = {}
        for user in self._roster._users:
            entry = counts.setdefault(user.group, [0, 0])
            entry[1] += 1
            if user.status != "offline":
                entry[0] += 1
        for name, (online, total) in counts.items():
            self._roster._groups[name].online_count = online
            self._roster._groups[name].total_count = total

    def _on_presence_changed(self, bare_jid: str, show: str, status: str):
        show = show or "offline"
        self._roster.update_user(bare_jid, status=show, status_message=status,
                                 icon_key=show_to_icon_key(show))
        self._recount_groups()
        self._roster.sort_and_update()

    def _on_subscribed(self, jid: str):
        """A new contact was added (our subscribe was accepted)."""
        self._client.request_roster()

    # ── Chat ──────────────────────────────────────────────────────

    def _roster_name(self, jid: str) -> str:
        """Return the display name for *jid* from the roster, or ''."""
        for user in self._roster._users:
            if user.jid == jid:
                return user.name or user.jid
        return ""

    def _on_contact_open(self, jid: str):
        display_name = self._roster_name(jid) or jid.split("@")[0]
        if jid in self._muc_self_nicks:
            self._chat_window.open_groupchat(
                jid, self._muc_self_nicks[jid], display_name)
            return
        is_new = not self._chat_window.has_chat(jid)
        self._chat_window.open_chat(jid, display_name)
        if is_new:
            self._load_history(jid)
        self._reset_unread(jid)
        self._request_vcard(jid)

    def _load_history(self, jid: str):
        """Feed previously saved messages from the SQLite history into chat."""
        from jabbim.core import history
        chat = self._chat_window.get_chat(jid)
        if not chat:
            return
        if not os.path.isfile(history._path(jid)):
            history.migrate_from_jsonl(jid)
        try:
            limit = int(self._config.chat.history_limit)
        except (TypeError, ValueError):
            limit = 200
        entries = history.load_history(jid, limit=limit)
        exhausted = bool(entries) and bool(entries[0].get("id")) \
            and not history.older_available(jid, entries[0]["id"])
        chat.set_history(entries, limit, exhausted)

    def _on_contact_context(self, jid: str, pos):
        menu = QtWidgets.QMenu(self)
        menu.addAction(tr("ctx_open_chat"), lambda: self._on_contact_open(jid))
        menu.addAction(tr("ctx_view_profile"), lambda: self._show_profile(jid))
        menu.addSeparator()
        menu.addAction(tr("ctx_rename"), lambda: self._rename_contact(jid))
        menu.addAction(tr("ctx_move_group"), lambda: self._move_to_group(jid))
        if self._client:
            menu.addAction(tr("ctx_resend_auth"),
                           lambda: self._client.resend_subscription(jid))
        menu.addSeparator()
        menu.addAction(tr("ctx_clear_history"), lambda: self._on_clear_history(jid))
        menu.addAction(tr("ctx_remove_contact"), lambda: self._on_remove_contact(jid))
        menu.exec(pos)

    def _rename_contact(self, jid: str):
        if not self._client:
            return
        current = self._roster_name(jid) or jid.split("@")[0]
        name, ok = QtWidgets.QInputDialog.getText(
            self, tr("ctx_rename"), tr("ctx_rename_prompt"), text=current)
        if not ok:
            return
        name = name.strip()
        self._client.update_contact(jid, name=name)
        self._roster.update_user(jid, name=name)

    def _move_to_group(self, jid: str):
        if not self._client:
            return
        group, ok = QtWidgets.QInputDialog.getText(
            self, tr("ctx_move_group"), tr("ctx_move_group_prompt"))
        if not ok:
            return
        groups = [g.strip() for g in group.strip().split(",") if g.strip()]
        self._client.update_contact(jid, groups=groups)

    def _on_clear_history(self, jid: str):
        from jabbim.core import history
        history.clear(jid)
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.history_cleared()

    def _on_server_history(self, jid: str, since: str = ""):
        """Load the whole server-side conversation into the chat window."""
        if not self._client:
            return
        logger.info("Requesting MAM history for %s before %s", jid, since or "now")
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.set_history_status(tr("history_server_fetching"))
        self._start_task(self._fetch_server_history(jid, since or None))

    async def _fetch_server_history(self, jid: str, since):
        client = self._client
        if not client:
            return
        try:
            limit = int(self._config.chat.history_limit)
        except (TypeError, ValueError):
            limit = 200
        try:
            stored = await client.fetch_history_mam(jid, since, limit)
        except Exception:
            stored = None
        chat = self._chat_window.get_chat(jid)
        if chat:
            logger.info("MAM history for %s stored %d messages", jid, stored or 0)
            chat.set_history_status(
                tr("history_server_loaded", n=stored or 0)
                if stored else tr("history_server_empty"))
            chat.server_fetch_done(stored or 0)

    def _on_mam_unavailable(self, jid: str):
        chat = self._chat_window.get_chat(jid)
        if not chat:
            return
        from jabbim.include.utils import format_time
        chat.mark_server_exhausted()
        chat.set_history_status(tr("history_server_unavailable"))

    def _on_remove_contact(self, jid: str):
        if self._client:
            self._client.remove_contact(jid)
            self._roster.remove_user(jid)

    def _bump_unread(self, jid: str):
        """Increment the unread counter for a roster contact."""
        for user in self._roster._users:
            if user.jid == jid:
                self._roster.update_user(jid, unread_count=user.unread_count + 1)
                return

    def _reset_unread(self, jid: str):
        """Clear the unread counter for *jid* and refresh totals."""
        found = False
        for user in self._roster._users:
            if user.jid == jid and user.unread_count:
                self._unread_total = max(0, self._unread_total - user.unread_count)
                self._roster.update_user(jid, unread_count=0)
                found = True
                break
        if not found:
            # Message came from a contact not in the roster — decrement the
            # running total so blinking always stops once everything is read.
            self._unread_total = max(0, self._unread_total - 1)
        if self._unread_total == 0:
            self._tray.stop_blinking()

    def _on_tab_focused(self, jid: str):
        self._reset_unread(jid)

    def _on_message_received(self, frm: str, body: str, ts):
        from jabbim.include.utils import ts_to_time
        bare_jid = frm.split("/")[0]
        timestamp = ts_to_time(ts)
        sender_name = self._roster_name(bare_jid) or bare_jid.split("@")[0]

        if not self._chat_window.has_chat(bare_jid):
            self._chat_window.open_chat(bare_jid, sender_name, focus=False)

        chat = self._chat_window.get_chat(bare_jid)
        if chat:
            chat.add_message(sender=sender_name, body=body,
                             timestamp=timestamp, direction="incoming")

        from jabbim.core import history
        history.store_message(bare_jid, "incoming", body, sender=sender_name)

        # Unread badge + tray blink (skip when conversation is on screen)
        active = (self._chat_window.isVisible()
                  and self._chat_window.current_jid() == bare_jid)
        if not active:
            self._bump_unread(bare_jid)
            self._unread_total += 1
            if self._config.notifications.tray_blink:
                self._tray.start_blinking()
        if self._config.notifications.popups and not active:
            self._tray.show_message(sender_name, body)
        self._request_vcard(bare_jid)

    def _on_message_send(self, jid: str, body: str):
        if self._client and isinstance(jid, str) and jid.strip():
            jid = jid.strip()
            self._client.send_message(jid, body)
            chat = self._chat_window.get_chat(jid)
            if chat:
                from jabbim.include.utils import format_time
                chat.add_message(sender="Me", body=body,
                                 timestamp=format_time(), direction="outgoing")
            from jabbim.core import history
            history.store_message(jid, "outgoing", body, sender="Me")

    # ── Groupchat ─────────────────────────────────────────────────

    def _on_groupchat_message(self, room: str, nick: str, body: str, ts):
        from jabbim.include.utils import ts_to_time
        timestamp = ts_to_time(ts)
        chat = self._chat_window.get_chat(room)
        if chat:
            user = self._muc_users.get(room, {}).get(nick, {})
            chat.add_message(sender=nick, body=body,
                             timestamp=timestamp, direction="incoming",
                             sender_jid=(user.get("avatar_jid", "")
                                         or user.get("real_jid", "")))

    def _on_groupchat_presence(self, room: str, nick: str, show: str,
                               status: str, role: str = "",
                               affiliation: str = "", real_jid: str = ""):
        users = self._muc_users.setdefault(room, {})
        if show == "unavailable":
            users.pop(nick, None)
        else:
            previous = users.get(nick, {})
            users[nick] = {
                "nick": nick, "show": show, "status": status,
                "role": role, "affiliation": affiliation,
                "real_jid": real_jid or previous.get("real_jid", ""),
                "avatar_jid": previous.get("avatar_jid", ""),
                "avatar_path": previous.get("avatar_path", ""),
            }
            if self._client:
                self._client.get_vcard(real_jid or f"{room}/{nick}")
        chat = self._chat_window.get_chat(room)
        if chat:
            self_nick = self._muc_self_nicks.get(room, "")
            chat.update_muc_users(list(users.values()), self_nick=self_nick)
            chat.set_status_text(f"{tr('muc_participants')}: {len(users)}")
        if nick == self._muc_self_nicks.get(room):
            self._sync_conference_roster(room)

    def _on_groupchat_send(self, room: str, body: str):
        if self._client:
            self._client.send_muc_message(room, body)

    def _participant_info(self, room: str, nick: str) -> dict:
        return self._muc_users.get(room, {}).get(nick, {})

    def _on_muc_participant_clicked(self, room: str, nick: str):
        info = self._participant_info(room, nick)
        real_jid = info.get("real_jid")
        target = real_jid.strip() if isinstance(real_jid, str) else ""
        if not target or target.lower() == "none":
            target = f"{room}/{nick}"
        chat = self._chat_window.open_chat(target, nick)
        if not chat._history:
            self._load_history(target)

    def _on_muc_participant_context(self, room: str, nick: str, pos):
        info = self._participant_info(room, nick)
        raw_real_jid = info.get("real_jid")
        real_jid = (raw_real_jid.split("/", 1)[0]
                    if isinstance(raw_real_jid, str) else "")
        own = self._participant_info(room, self._muc_self_nicks.get(room, ""))
        can_manage = (own.get("role") == "moderator"
                      or own.get("affiliation") in ("admin", "owner"))

        menu = QtWidgets.QMenu(self)
        profile = menu.addAction(tr("muc_user_view_vcard"))
        profile.triggered.connect(
            lambda: self._show_muc_participant_profile(room, nick, real_jid))
        command = menu.addAction(tr("muc_user_execute_command"))
        command.triggered.connect(
            lambda: self._muc_user_command(room, nick))
        menu.addSeparator()
        roles = menu.addMenu(tr("muc_user_change_role"))
        for role in ("visitor", "participant", "moderator"):
            action = roles.addAction(tr(f"muc_role_{role}"))
            action.setEnabled(can_manage)
            action.triggered.connect(
                lambda checked=False, value=role:
                self._change_muc_role(room, nick, value))
        menu.exec(pos)

    def _show_muc_participant_profile(self, room: str, nick: str,
                                      real_jid: str):
        self._show_profile(real_jid or f"{room}/{nick}")

    def _muc_user_command(self, room: str, nick: str):
        chat = self._chat_window.get_chat(room)
        if chat:
            from jabbim.include.utils import format_time
            chat.add_status(tr("muc_user_command_unavailable"), format_time())

    def _change_muc_role(self, room: str, nick: str, role: str):
        if not self._client:
            return
        self._client.set_muc_role(room, nick, role)

    # ── Status ────────────────────────────────────────────────────

    def _on_typing(self, jid: str, is_typing: bool):
        """A contact started/stopped composing (XEP-0085)."""
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.set_typing(self._roster_name(jid) or jid.split("@")[0], is_typing)

    def _on_typing_local(self, jid: str, is_typing: bool):
        if self._client:
            self._client.send_chat_state(jid, "composing" if is_typing else "paused")

    def _on_receipt_delivered(self, jid: str):
        from jabbim.include.utils import format_time
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.add_status(tr("msg_delivered"), format_time())

    def _on_status_change(self, index: int):
        show = self._status_combo.currentData()
        if not show:
            return
        self._config.last_status = show
        if self._client:
            self._client.send_presence(show=show)
        self._set_tray_status_icon(show)

    def _on_search(self, text: str):
        self._roster.set_search_filter(text.lower())

    # ── Window management ─────────────────────────────────────────

    def _restore_window_geometry(self):
        """Restore window position/size from config (if any)."""
        win = self._config.window
        width = int(win.width or 300)
        height = int(win.height or 600)
        x, y = int(win.x or 0), int(win.y or 0)
        self.resize(max(width, 280), max(height, 500))
        if x or y:
            self.move(x, y)

    def _save_window_geometry(self):
        """Persist window geometry into config."""
        geo = self.geometry()
        self._config.window.x = geo.x()
        self._config.window.y = geo.y()
        self._config.window.width = geo.width()
        self._config.window.height = geo.height()
        self._config.window.maximized = self.isMaximized()
        self._config.save()

    def _on_chat_closed(self, jid: str):
        """A chat tab was closed — release its history DB connection."""
        from jabbim.core import history
        history.close(jid)

    def _toggle_visibility(self):
        if self._visible:
            self._visible = False
            self.hide()
        else:
            state = self.windowState()
            state &= ~QtCore.Qt.WindowState.WindowMinimized
            state |= QtCore.Qt.WindowState.WindowActive
            self.setWindowState(state)
            self.show()
            self.raise_()
            self.activateWindow()
            self._visible = True

    def _quit(self):
        if self._client is not None and hasattr(self._client, "disconnect"):
            asyncio.ensure_future(self._client.disconnect())
        self._tray.hide()
        self.app.quit()

    def closeEvent(self, event):
        self._save_window_geometry()
        if self._config.ui.close_to_tray:
            self.hide()
            self._visible = False
            event.ignore()
        else:
            self._quit()
            event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self._visible = True

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            if self.isMinimized() and not self.isHidden():
                self._visible = False
                self._save_window_geometry()
                QtCore.QTimer.singleShot(0, self.hide)
