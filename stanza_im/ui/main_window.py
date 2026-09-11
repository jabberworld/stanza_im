"""Main application window.

Manages the three-page stacked widget (login / splash / roster) and the
optional embedded chat window.  Wires the XMPP client, tray, roster and
chat together.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import os
import time
import uuid

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr, load as load_i18n
from stanza_im.include.avatars import save_avatar
from stanza_im.include.enumerators import populate_translations, show_to_icon_key
from stanza_im.include.constants import (APP_NAME, VERSION,
                                      ACTIONS_DIR_16, CATEGORIES_DIR_16,
                                      STATUS_DIR_32,
                                      PLACES_DIR_22)
from stanza_im.core.storage import Config
from stanza_im.ui.icons import init_icons
from stanza_im.ui.login_widget import LoginWidget
from stanza_im.ui.roster_widget import RosterWidget, UserItem
from stanza_im.ui.chat_window import ChatWindow
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.subject_dialog import SubjectDialog
from stanza_im.ui.tray import TrayIcon
from stanza_im.ui.osd import OsdManager

logger = logging.getLogger(__name__)
_HISTORY_BATCH_LIMIT = 60


def _current_timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")

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
        self._file_uploads: dict[str, tuple] = {}      # jid -> (dlg, paths)
        self._file_upload_states: dict[tuple, tuple] = {}  # (jid, path) -> (dlg, i)

        from stanza_im.ui.tray import build_app_icon
        app.setWindowIcon(build_app_icon())
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(280, 500)
        self._restore_window_geometry()

        # ── Theme factory (shared by all chat views) ──────────────
        self._theme_factory = ChatThemeFactory()
        self._muc_theme_factory = ChatThemeFactory()
        self._theme_factory.set_variant(
            self._config.appearance.chat_theme or self._config.chat.theme)
        self._muc_theme_factory.set_variant(self._config.appearance.muc_theme)
        self._theme_factory.set_emoticon_skin(self._config.appearance.emoticon_theme)
        self._muc_theme_factory.set_emoticon_skin(self._config.appearance.emoticon_theme)
        self._theme_factory.set_message_styling(self._config.chat.message_styling)
        self._muc_theme_factory.set_message_styling(self._config.chat.message_styling)

        # ── Chat window (standalone) ─────────────────────────────
        self._chat_window = ChatWindow(self._theme_factory, self._muc_theme_factory)
        self._chat_window.set_tab_title_length(
            self._config.chat.tab_title_length)
        self._chat_window.set_chat_options(self._config.chat)
        self._chat_window.message_to_send.connect(self._on_message_send)
        self._chat_window.groupchat_message_to_send.connect(self._on_groupchat_send)
        self._chat_window.message_reply_to_send.connect(self._on_message_reply_send)
        self._chat_window.groupchat_message_reply_to_send.connect(
            self._on_groupchat_reply_send)
        self._chat_window.message_edit_to_send.connect(self._on_message_edit_send)
        self._chat_window.groupchat_message_edit_to_send.connect(
            self._on_groupchat_edit_send)
        self._chat_window.vcard_requested.connect(self._on_chat_vcard)
        self._chat_window.files_upload_requested.connect(
            lambda jid, paths, method: self._on_chat_files_upload(
                jid, paths, method, self._chat_window))
        self._chat_window.input_height_changed.connect(
            self._on_input_height_changed)
        self._chat_window.text_scale_changed.connect(
            self._on_text_scale_changed)
        self._chat_window.window_closed.connect(self._on_chat_window_closed)
        self._chat_window.restore_geometry(self._config.chat_window)
        self._chat_window.tab_focused.connect(self._on_tab_focused)
        self._chat_window.tab_closed.connect(self._on_chat_closed)
        self._chat_window.muc_leave_requested.connect(self._on_muc_leave)
        self._chat_window.set_muc_leave_confirm(self._confirm_muc_leave)
        self._chat_window.clear_history_requested.connect(self._on_clear_history)
        self._chat_window.server_history_requested.connect(self._on_server_history)
        self._chat_window.bookmark_toggled.connect(self._toggle_bookmark)
        self._chat_window.set_subject_requested.connect(self._on_set_subject)
        self._chat_window.nick_change_requested.connect(self._on_nick_change)
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

        # ── OSD notifications ─────────────────────────────────────
        self._osd = OsdManager(self._config, self._icons)
        self._osd_status_seen: set[str] = set()

        # ── UI ───────────────────────────────────────────────────
        self._build_ui()

        # ── XMPP client (created on connect) ─────────────────────
        self._client = None

        # ── State ────────────────────────────────────────────────
        self._visible = True
        self._shutting_down = False
        self._unread_total = 0
        self._muc_users: dict[str, dict[str, dict]] = {}
        self._muc_self_nicks: dict[str, str] = {}
        self._muc_names: dict[str, str] = {}
        self._muc_avatar_paths: dict[str, str] = {}
        self._muc_join_tries: dict[str, int] = {}
        self._muc_base_nicks: dict[str, str] = {}
        self._muc_user_nick_change_from: dict[str, str] = {}
        self._conference_roster: set[str] = set()
        self._bookmarks: dict[str, dict] = {}
        self._vcard_requested: set[str] = set()
        self._pending_profile: set[str] = set()
        self._vcard_dialogs: dict[str, object] = {}
        self._history_manager: object | None = None
        self._last_activity = time.monotonic()
        self._auto_status_applied = False
        self.app.installEventFilter(self)
        self._idle_timer = QtCore.QTimer(self)
        self._idle_timer.timeout.connect(self._check_auto_status)
        self._idle_timer.start(30_000)

        self._chat_window.typing_changed.connect(self._on_typing_local)
        self._chat_window.activity_changed.connect(self._on_chat_activity)

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
        self._roster.set_tooltip_provider(self._roster_tooltip)
        self._show_offline_action.toggled.connect(self._roster.set_show_offline)
        self._roster.contact_double_clicked.connect(self._on_contact_open)
        self._roster.contact_context_menu.connect(self._on_contact_context)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._roster)
        viewport = scroll.viewport()
        viewport.setAutoFillBackground(True)
        pal = viewport.palette()
        pal.setColor(QtGui.QPalette.ColorRole.Window,
                     QtCore.Qt.GlobalColor.white)
        viewport.setPalette(pal)
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

    @staticmethod
    def _menu_icon(filename: str) -> QtGui.QIcon:
        """Load an action/category/status icon for menus from resources."""
        for directory in (ACTIONS_DIR_16, CATEGORIES_DIR_16, STATUS_DIR_32,
                          PLACES_DIR_22):
            pix = QtGui.QPixmap(os.path.join(directory, filename))
            if not pix.isNull():
                return QtGui.QIcon(pix)
        return QtGui.QIcon()

    def _build_menu(self):
        """Build the roster menu bar."""
        menubar = self.menuBar()

        actions_menu = menubar.addMenu(tr("menu_actions"))
        join_room = actions_menu.addAction(self._menu_icon("muc.png"),
                                           tr("menu_join_groupchat"))
        join_room.triggered.connect(self._on_join_groupchat_dialog)
        add_contact = actions_menu.addAction(self._menu_icon("add-user.png"),
                                             tr("menu_add_contact"))
        add_contact.triggered.connect(self._on_add_contact)
        service_discovery = actions_menu.addAction(
            self._menu_icon("service-discovery.png"), tr("menu_service_discovery"))
        service_discovery.triggered.connect(self._on_service_browser)
        my_vcard = actions_menu.addAction(self._menu_icon("v-card.png"),
                                          tr("menu_edit_my_vcard"))
        my_vcard.triggered.connect(self._edit_my_vcard)
        history_act = actions_menu.addAction(self._menu_icon("history.png"),
                                             tr("menu_history"))
        history_act.triggered.connect(self._on_history_manager)
        actions_menu.addSeparator()
        plugins_menu = actions_menu.addMenu(self._menu_icon("exec.png"),
                                            tr("menu_plugins"))
        plugins_menu.setEnabled(False)
        plugins_menu.addAction(tr("menu_plugins_empty")).setEnabled(False)
        actions_menu.addSeparator()
        prefs = actions_menu.addAction(self._menu_icon("gtk-preferences.png"),
                                       tr("menu_preferences"))
        prefs.triggered.connect(self._on_preferences)
        profiles = actions_menu.addAction(tr("menu_profiles"))
        profiles.setEnabled(False)
        actions_menu.addSeparator()
        quit_act = actions_menu.addAction(self._menu_icon("gtk-quit.png"),
                                          tr("menu_quit"))
        quit_act.triggered.connect(self._quit)

        view_menu = menubar.addMenu(tr("menu_view"))
        show_offline = view_menu.addAction(self._menu_icon("aim-offline.png"),
                                           tr("menu_show_offline"))
        show_offline.setCheckable(True)
        show_offline.setChecked(True)
        self._show_offline_action = show_offline
        show_transports = view_menu.addAction(self._menu_icon("transports.png"),
                                              tr("menu_show_transports"))
        show_transports.setCheckable(True)
        show_transports.setEnabled(False)

        self._bookmarks_menu = menubar.addMenu(tr("menu_bookmarks"))
        self._bookmarks_menu.aboutToShow.connect(self._refresh_bookmarks_menu)

        help_menu = menubar.addMenu(tr("menu_help"))
        about = help_menu.addAction(self._menu_icon("about.png"),
                                    tr("menu_about"))
        about.triggered.connect(self._on_about)

    # ── Menu actions ─────────────────────────────────────────────

    def _on_add_contact(self):
        if not self._client:
            return
        from stanza_im.ui.add_contact_dialog import AddContactDialog
        groups = sorted({user.group for user in self._roster._users
                         if user.group not in (tr("roster_group_conferences"),
                                               tr("roster_group_transports"),
                                               tr("roster_group_ungrouped"))},
                        key=str.casefold)
        dlg = AddContactDialog(groups, self._client, self)
        if not dlg.exec():
            return
        data = dlg.collect()
        self._client.add_contact(data["jid"], data["name"],
                                 [data["group"]] if data["group"] else [],
                                 data["message"], data["subscribe"])
        self._client.request_roster()

    def _on_service_browser(self):
        if not self._client:
            return
        from stanza_im.ui.service_browser import ServiceBrowserDialog
        servers = list(self._config.connection.service_servers or [])
        domain = self._client.jid_str.split("@", 1)[-1]
        if domain not in servers:
            servers.insert(0, domain)
        dlg = ServiceBrowserDialog(self._client, servers, self)
        dlg.conference_requested.connect(self._on_service_conference)
        dlg.vcard_requested.connect(self._show_profile)
        dlg.servers_updated.connect(self._on_service_servers)
        dlg.open()

    def _on_service_servers(self, servers: list[str]):
        self._config.connection.service_servers = list(servers)
        self._config.save()

    def _on_service_conference(self, jid: str):
        from stanza_im.ui.conference_dialog import JoinConferenceDialog
        room, sep, server = jid.partition("@")
        if not sep:
            room, server = "", jid
        dlg = JoinConferenceDialog(self._client, [server],
                                   list(self._bookmarks.values()), self,
                                   room=room)
        dlg.vcard_requested.connect(self._show_profile)

        def finished(result: int):
            if result != QtWidgets.QDialog.DialogCode.Accepted:
                return
            data = dlg.collect()
            if data["server"] and data["server"] not in (
                    self._config.connection.conference_servers or []):
                stored = list(self._config.connection.conference_servers or [])
                stored.append(data["server"])
                self._config.connection.conference_servers = stored
                self._config.save()
            self._join_muc(data["room"], data["nick"], data["password"],
                           save_bookmark=data["save"],
                           bookmark_name=data["name"],
                           autojoin=data["autojoin"])
        dlg.finished.connect(finished)
        dlg.open()

    def _on_join_groupchat_dialog(self):
        if not self._client:
            return
        self._start_task(self._open_join_conference_dialog())

    async def _open_join_conference_dialog(self):
        from stanza_im.ui.conference_dialog import JoinConferenceDialog
        servers = list(self._config.connection.conference_servers or [])
        if not servers:
            try:
                default_server = await self._client.discover_conference_service()
            except Exception:
                default_server = ""
            if default_server:
                servers.append(default_server)
        dlg = JoinConferenceDialog(self._client, servers,
                                   list(self._bookmarks.values()), self)
        dlg.vcard_requested.connect(self._show_profile)
        def finished(result: int):
            if result != QtWidgets.QDialog.DialogCode.Accepted:
                return
            data = dlg.collect()
            if data["server"] and data["server"] not in servers:
                servers.append(data["server"])
                self._config.connection.conference_servers = servers
                self._config.save()
            self._join_muc(data["room"], data["nick"], data["password"],
                           save_bookmark=data["save"],
                           bookmark_name=data["name"],
                           autojoin=data["autojoin"])
        dlg.finished.connect(finished)
        dlg.open()

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
            name = bookmark.get("name") or ""
            if not name or name == room:
                name = room.split("@", 1)[0]
            label = name
            submenu = self._bookmarks_menu.addMenu(self._menu_icon("muc.png"),
                                                   label)
            join = submenu.addAction(self._menu_icon("muc.png"),
                                     tr("bookmark_join"))
            join.triggered.connect(
                lambda checked=False, item=bookmark: self._join_bookmark(item))
            auto = submenu.addAction(tr("bookmark_autojoin"))
            auto.setCheckable(True)
            auto.setChecked(bool(bookmark.get("autojoin")))
            auto.toggled.connect(
                lambda value, item=bookmark: self._set_bookmark_autojoin(item, value))
            remove = submenu.addAction(self._menu_icon("process-stop.png"),
                                       tr("bookmark_remove"))
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
            bookmark.get("password", ""), autojoin=autojoin,
            name=bookmark.get("name", "")))

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

    def _on_set_subject(self, room: str):
        if not self._client:
            return
        dialog = SubjectDialog(room, self._client.get_muc_subjects(room),
                               self._chat_window)
        if not dialog.exec():
            return
        result = dialog.result_subjects()
        default = next((text for lang, text in result if not lang), "")
        langs = [(lang, text) for lang, text in result if lang]
        self._client.set_muc_subject(room, default, langs=langs)

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
            name=self._muc_display_name(room),
            group=tr("roster_group_conferences"),
            status=status,
            status_message=status_message,
            icon_key=status if status in ("online", "chat", "away", "xa", "dnd", "offline")
            else "online",
            avatar_path=(self._muc_avatar_paths.get(room)
                         or getattr(contact, "avatar_path", None)),
        ))
        self._conference_roster.add(room)
        self._roster._groups[tr("roster_group_conferences")].single_count = True
        self._remember_contact(room, name=self._muc_display_name(room),
                               groups=[tr("roster_group_conferences")],
                               is_conference=True)
        self._recount_groups()
        self._roster.sort_and_update()

    def _sync_all_conference_roster(self):
        for room in self._muc_self_nicks:
            self._sync_conference_roster(room)

    def _join_muc(self, room: str, nick: str, password: str = "",
                  save_bookmark: bool = False, bookmark_name: str = "",
                  autojoin: bool = False):
        if not self._client:
            return
        display_name = self._muc_display_name(room)
        is_new = not self._chat_window.has_chat(room)
        if is_new:
            self._chat_window.open_groupchat(room, nick, display_name)
        self._muc_self_nicks[room] = nick
        self._muc_base_nicks[room] = nick
        self._muc_join_tries[room] = 0
        self._muc_users.setdefault(room, {})[nick] = {
            "nick": nick, "show": "online", "status": "",
            "role": "", "affiliation": "",
        }
        self._client.join_muc(room, nick, password=password, save_bookmark=False)
        if save_bookmark:
            self._start_task(self._client.save_bookmark(
                room, nick, password, autojoin=autojoin, name=bookmark_name))
        chat = self._chat_window.get_chat(room)
        if chat:
            if is_new:
                self._load_history(room)
            chat.set_self_nick(nick)
            chat.update_muc_users(list(self._muc_users[room].values()),
                                  self_nick=nick)
            from stanza_im.include.utils import format_time
            chat.add_status(f"Joined as {nick}", format_time())
            chat.set_bookmarked(room in self._bookmarks)
        self._request_vcard(room, force=True)
        self._client.get_muc_info(room)
        self._sync_conference_roster(room)

    def _on_muc_leave(self, room: str):
        if self._client:
            self._client.leave_muc(room)
        self._muc_users.pop(room, None)
        self._muc_self_nicks.pop(room, None)
        self._muc_names.pop(room, None)
        self._muc_avatar_paths.pop(room, None)
        self._muc_join_tries.pop(room, None)
        self._muc_base_nicks.pop(room, None)
        if room in self._conference_roster:
            self._roster.remove_user(room)
            self._conference_roster.discard(room)
            self._recount_groups()
            self._roster.sort_and_update()
        from stanza_im.core import history
        history.close(room)

    def _on_leave_conference(self, room: str):
        if not self._confirm_muc_leave(room):
            return
        self._on_muc_leave(room)
        self._chat_window.close_chat(room)

    def _confirm_muc_leave(self, room: str) -> bool:
        """Ask before leaving a MUC when the preference is enabled."""
        if self._shutting_down or not self._config.chat.muc_confirm_leave:
            return True
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Icon.Question)
        box.setWindowTitle(tr("muc_leave"))
        box.setText(tr("muc_leave_confirm",
                       room=self._muc_display_name(room)))
        ok = box.addButton(tr("dialog_ok"),
                           QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("dialog_cancel"),
                      QtWidgets.QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(ok)
        box.exec()
        return box.clickedButton() is ok

    def _should_minimize_muc(self, room: str) -> bool:
        """Auto-joined MUCs stay out of the chat window on startup."""
        client = self._client
        if not client or not self._config.chat.muc_minimize_startup:
            return False
        return room in getattr(client, "autojoin_rooms", set())

    def _on_muc_joined(self, room: str, subject: str, occupants):
        self._muc_join_tries.pop(room, None)
        self._muc_user_nick_change_from.pop(room, None)
        if room not in self._muc_self_nicks:
            info = self._client.groupchats.get(room) if self._client else None
            nick = info.nick if info else (
                self._client.jid_str.split("@", 1)[0]
                if self._client else "")
            self._muc_self_nicks[room] = nick
        minimized = self._should_minimize_muc(room)
        chat = self._chat_window.get_chat(room)
        if not chat and not minimized:
            chat = self._chat_window.open_groupchat(
                room, self._muc_self_nicks[room],
                self._muc_display_name(room))
            self._load_history(room)
            self._request_vcard(room, force=True)
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
        if chat:
            self_nick = self._muc_self_nicks.get(room, "")
            chat.set_self_nick(self_nick)
            chat.update_muc_users(list(users.values()), self_nick=self_nick)
            subjects = (self._client.get_muc_subjects(room)
                        if self._client else [])
            if not subjects and subject:
                subjects = [("", subject)]
            chat.set_subject(subjects)
            self._chat_window.set_chat_title(
                room, self._muc_display_name(room))
            chat.set_bookmarked(room in self._bookmarks)
        if self._client:
            for nick, info in users.items():
                real_jid = info.get("real_jid")
                self._client.get_vcard(real_jid or f"{room}/{nick}")
            self._client.get_muc_info(room)
        self._sync_conference_roster(room)

    def _on_muc_subject_changed(self, room: str, subjects):
        if self._client:
            gi = self._client.groupchats.get(room)
            if gi:
                default = next((t for lang, t in subjects if not lang), "")
                if not default:
                    default = subjects[0][1] if subjects else ""
                if default:
                    gi.subject = default
        chat = self._chat_window.get_chat(room)
        if chat:
            chat.set_subject(subjects)

    def _schedule_muc_nick_retry(self, room: str) -> bool:
        """Re-join a busy nick with more underscores; False when exhausted."""
        client = self._client
        if not client:
            return False
        tries = self._muc_join_tries.get(room, 0)
        if tries >= 2:
            return False
        if room not in self._muc_base_nicks:
            gi = client.groupchats.get(room)
            base = gi.nick if gi else ""
            self._muc_base_nicks[room] = base or client.jid_str.split("@", 1)[0]
        base = self._muc_base_nicks.get(room, "")
        if not base:
            return False
        tries += 1
        self._muc_join_tries[room] = tries
        new_nick = base + "_" * tries
        gi = client.groupchats.get(room)
        password = gi.password if gi else ""
        client.join_muc(room, new_nick, password=password)
        self._update_muc_self_nick(room, new_nick)
        return True

    def _update_muc_self_nick(self, room: str, nick: str,
                              status_key: str = "muc_nick_retrying") -> None:
        old = self._muc_self_nicks.get(room, "")
        self._muc_self_nicks[room] = nick
        users = self._muc_users.setdefault(room, {})
        if old and old != nick and old in users:
            entry = users.pop(old)
            entry["nick"] = nick
            users[nick] = entry
        chat = self._chat_window.get_chat(room)
        if not chat:
            return
        chat.set_self_nick(nick)
        chat.update_muc_users(list(users.values()), self_nick=nick)
        from stanza_im.include.utils import format_time
        chat.add_status(tr(status_key, nick=nick), format_time())

    def _on_nick_change(self, room: str, nick: str):
        """Handle the /nick command in a conference (rejoin with new nick)."""
        client = self._client
        chat = self._chat_window.get_chat(room)
        if not client:
            return
        from stanza_im.include.utils import format_time
        now = format_time()
        if room not in self._muc_self_nicks:
            if chat:
                chat.add_status(tr("muc_nick_not_in_room"), now)
            return
        new_nick = (nick or "").strip()
        # XEP-0045 §17.1: a room nickname is a resourcepart — it must be
        # non-empty (not invisible), may contain "@", "\" and spaces, but no
        # control characters, no "/" (the resource separator) and no more
        # than 1023 UTF-8 bytes (RFC 7622).
        if (not new_nick
                or any(not c.isprintable() for c in new_nick)
                or "/" in new_nick
                or len(new_nick.encode("utf-8")) > 1023):
            if chat:
                chat.add_status(tr("muc_nick_invalid"), now)
            return
        current = self._muc_self_nicks.get(room, "")
        if new_nick == current:
            if chat:
                chat.add_status(tr("muc_nick_same", nick=new_nick), now)
            return
        if room in self._muc_user_nick_change_from:
            return
        self._muc_user_nick_change_from[room] = current
        gi = client.groupchats.get(room)
        password = gi.password if gi else ""
        client.join_muc(room, new_nick, password=password)
        self._update_muc_self_nick(room, new_nick, status_key="muc_nick_changed")

    def _on_muc_join_error(self, room: str, condition: str, code: str):
        if condition == "conflict" and room in self._muc_user_nick_change_from:
            old = self._muc_user_nick_change_from.pop(room)
            self._update_muc_self_nick(room, old, status_key="muc_nick_busy")
            return
        if condition == "conflict" and self._config.chat.muc_auto_nick:
            if self._schedule_muc_nick_retry(room):
                return
            self._muc_join_tries.pop(room, None)
            self._muc_base_nicks.pop(room, None)
            chat = self._chat_window.get_chat(room)
            if chat:
                from stanza_im.include.utils import format_time
                chat.add_status(tr("muc_nick_conflict_give_up"),
                                format_time())
            return
        chat = self._chat_window.get_chat(room)
        if not chat:
            return
        from stanza_im.include.utils import format_time
        message = (tr("muc_join_waiting") if condition == "timeout"
                   else tr("muc_join_failed", reason=condition or code))
        chat.add_status(message, format_time())

    def _on_muc_info_received(self, room: str, name: str):
        if room in self._muc_self_nicks and name:
            self._muc_names[room] = name
            self._chat_window.set_chat_title(room, name)
            self._sync_conference_roster(room)

    def _muc_display_name(self, room: str, preferred: str = "") -> str:
        if preferred:
            return preferred
        if room in self._muc_names:
            return self._muc_names[room]
        if self._client:
            contact = self._client.get_contact(room)
            card = getattr(contact, "vcard", None) or {}
            name = card.get("fn") or card.get("nickname") or ""
            if name:
                return name
        return room.split("@", 1)[0]

    def _roster_tooltip(self, jid: str) -> tuple[str, str | None]:
        """Build the roster contact/conference tooltip (html, avatar path)."""
        from stanza_im.include.utils import escape_html
        if not self._client:
            return "", None
        is_conf = (jid in self._conference_roster or jid in self._muc_self_nicks)
        if is_conf:
            avatar = self._muc_avatar_paths.get(jid)
            if not avatar:
                contact = self._client.get_contact(jid)
                avatar = getattr(contact, "avatar_path", None)
            name = self._muc_display_name(jid)
            html = (f"<b>{escape_html(name)}</b><br>"
                    f"{tr('tooltip_jid')}: {escape_html(jid)}")
            return html, avatar
        contact = self._client.get_contact(jid)
        name = self._roster_name(jid) or jid.split("@", 1)[0]
        lines = [f"<b>{escape_html(name)}</b>",
                 f"{tr('tooltip_jid')}: {escape_html(jid)}"]
        resources = sorted(
            contact.resources.items(),
            key=lambda item: (-item[1].get("priority", 0),
                              item[0].casefold()))
        for resource, info in resources:
            parts = [f"<b>{escape_html(resource or '*')}</b>"]
            client = info.get("client", "") or ""
            if client:
                parts.append(tr("tooltip_client") + ": "
                             + escape_html(client))
            lines.append("&nbsp;&nbsp;&middot;&nbsp; " + " &mdash; ".join(parts))
        if contact.status:
            lines.append("<i>"
                         + escape_html(contact.status).replace("\n", "<br>")
                         + "</i>")
        return "<br>".join(lines), contact.avatar_path

    def _on_preferences(self):
        dlg = getattr(self, "_prefs_dialog", None)
        if dlg is not None and dlg.isVisible():
            dlg.raise_()
            dlg.activateWindow()
            return
        from stanza_im.ui.preferences import PreferencesDialog
        dlg = PreferencesDialog(self._config, self._theme_factory,
                                osd_manager=self._osd, parent=self)
        dlg.settings_applied.connect(self._on_settings_applied)
        dlg.finished.connect(self._on_prefs_finished)
        self._prefs_dialog = dlg
        # Non-modal so the OSD preview stays interactive while it is open.
        dlg.show()

    def _on_prefs_finished(self, _result=None):
        dlg = getattr(self, "_prefs_dialog", None)
        if dlg is not None:
            dlg.finished.disconnect(self._on_prefs_finished)
        self._prefs_dialog = None

    def _on_settings_applied(self):
        """Apply saved settings to live widgets."""
        variant = self._config.appearance.chat_theme or self._config.chat.theme
        muc_variant = self._config.appearance.muc_theme
        if (variant, muc_variant) != getattr(self, "_applied_chat_themes", ("", "")):
            self._chat_window.reload_themes(variant, muc_variant)
            self._applied_chat_themes = (variant, muc_variant)
        emoticon_skin = self._config.appearance.emoticon_theme
        if emoticon_skin != getattr(self, "_applied_emoticon_skin", "default/smileys.cfg"):
            self._chat_window.reload_emoticons(emoticon_skin)
            self._applied_emoticon_skin = emoticon_skin
        styling = bool(self._config.chat.message_styling)
        if styling != getattr(self, "_applied_message_styling", None):
            self._theme_factory.set_message_styling(styling)
            self._muc_theme_factory.set_message_styling(styling)
            self._applied_message_styling = styling
        self._chat_window.set_chat_options(self._config.chat)
        if self._client:
            self._client.send_typing_notifications = self._config.privacy.send_typing_notifications
            self._client.send_activity_notifications = self._config.privacy.send_activity_notifications
            self._client.send_chatstates = (
                self._client.send_typing_notifications
                or self._client.send_activity_notifications)
            plugin = self._client.xmpp.plugin.get("xep_0092", None)
            if plugin is not None:
                plugin.software_name = (APP_NAME if self._config.privacy.send_software
                                        else "")
                if self._config.privacy.send_software:
                    from stanza_im.include.constants import VERSION
                    import platform
                    plugin.version = VERSION
                    plugin.os = f"Python {platform.python_version()}"
                else:
                    plugin.version = ""
                    plugin.os = ""
        self._chat_window.set_tab_title_length(
            self._config.chat.tab_title_length)
        self._set_tray_status_icon(self._config.last_status)

    def _on_about(self):
        from stanza_im.ui.about_dialog import AboutDialog
        AboutDialog(self).exec()

    # ── Login / Connect ───────────────────────────────────────────

    def _on_login(self, jid: str, password: str, show: str):
        """Handle login form submission."""
        self._stack.setCurrentIndex(_PAGE_SPLASH)
        self._splash_label.setText(tr("login_connecting"))

        from stanza_im.core.client import JabberClient
        connection = self._config.connection
        self._client = JabberClient(
            jid, password,
            resource=connection.resource or "jabbim",
            host=connection.host if connection.override_host else "",
            port=connection.port if connection.override_host else 0,
            auto_join_conferences=connection.auto_join_conferences,
            send_typing_notifications=self._config.privacy.send_typing_notifications,
            send_activity_notifications=self._config.privacy.send_activity_notifications,
            send_software=self._config.privacy.send_software,
            message_carbons=connection.message_carbons,
            message_displayed_sync=self._config.chat.message_displayed_sync,
            allow_incoming_edits=self._config.chat.allow_incoming_edits,
        )
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
        c.on("message_carbon_sent", self._on_message_carbon_sent)
        c.on("mds_displayed", self._on_mds_displayed)
        c.on("message_corrected", self._on_message_corrected)
        c.on("groupchat_message_corrected", self._on_groupchat_message_corrected)
        c.on("file_upload_progress", self._on_file_upload_progress)
        c.on("muc_private_message", self._on_muc_private_message)
        c.on("groupchat_message", self._on_groupchat_message)
        c.on("groupchat_presence", self._on_groupchat_presence)
        c.on("groupchat_presence_details", self._on_groupchat_presence_details)
        c.on("auth_failed", self._on_auth_failed)
        c.on("disconnected", self._on_disconnected)
        c.on("subscribed", self._on_subscribed)
        c.on("vcard_received", self._on_vcard_received)
        c.on("typing", self._on_typing)
        c.on("chatstate_received", self._on_chatstate_received)
        c.on("receipt_delivered", self._on_receipt_delivered)
        c.on("muc_joined", self._on_muc_joined)
        c.on("muc_subject_changed", self._on_muc_subject_changed)
        c.on("muc_info_received", self._on_muc_info_received)
        c.on("entity_info_received", self._on_entity_info_received)
        c.on("muc_join_error", self._on_muc_join_error)
        c.on("mam_unavailable", self._on_mam_unavailable)
        c.on("mam_parse_error", self._on_mam_parse_error)
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
        # Prefetch bookmarks so MUC bookmark buttons are correct before the
        # Bookmarks menu is ever opened.
        self._start_task(self._load_bookmarks())

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
        self._remember_contact(jid, name=name, groups=groups,
                               is_conference=False)
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

    def _request_vcard(self, jid: str, force: bool = False):
        """Request a cached or fresh vCard; the client enforces the TTL."""
        if not self._client:
            return
        self._vcard_requested.add(jid)
        self._client.get_vcard(jid, force=force)

    def _on_vcard_received(self, jid: str, card: dict):
        bare_jid = jid.split("/", 1)[0]
        room_jid = (jid if jid in self._conference_roster
                    or jid in self._muc_self_nicks else "")
        path = card.get("avatar_path") or ""
        raw = card.get("photo")
        if raw:
            try:
                path = save_avatar(jid, raw)
            except Exception:
                path = ""
        if path:
            if room_jid:
                self._muc_avatar_paths[room_jid] = path
            contact = (self._client.get_contact(room_jid or bare_jid)
                       if self._client and "/" not in jid else None)
            if contact:
                contact.avatar_path = path
            if room_jid or "/" not in jid:
                self._roster.update_user(room_jid or bare_jid,
                                         avatar_path=path)
        if room_jid:
            self._sync_conference_roster(room_jid)
        if room_jid:
            title = card.get("fn") or card.get("nickname") or ""
            if title:
                self._chat_window.set_chat_title(room_jid, title)
        for room, users in self._muc_users.items():
            changed_nicks: list[tuple[str, str]] = []
            for nick, info in users.items():
                virtual_jid = f"{room}/{nick}"
                if (info.get("real_jid", "").split("/", 1)[0] == jid
                        or info.get("avatar_jid", "") == jid
                        or virtual_jid == jid):
                    info["avatar_jid"] = jid
                    info["avatar_path"] = path
                    changed_nicks.append((nick, jid))
            if changed_nicks:
                chat = self._chat_window.get_chat(room)
                if chat:
                    chat.update_muc_users(
                        list(users.values()),
                        self_nick=self._muc_self_nicks.get(room, ""))
                    for nick, avatar_jid in changed_nicks:
                        chat.refresh_avatar_for_sender(nick, avatar_jid)
        if jid in self._pending_profile:
            self._pending_profile.discard(jid)
            self._open_vcard_info(jid, card)

    def _open_vcard_info(self, jid: str, card: dict):
        from stanza_im.ui.vcard_dialog import VCardInfoDialog
        status = {
            "jid": card.get("jid") or jid,
            "presence": "",
            "status_message": "",
            "resource": "",
            "status_updated": "",
            "client_time": card.get("client_time", ""),
            "vcard_updated": card.get("fetched_at", ""),
        }
        if self._client:
            bare = jid.split("/", 1)[0]
            contact = self._client.get_contact(bare)
            status["presence"] = getattr(contact, "show", "")
            status["status_message"] = getattr(contact, "status", "")
            status["resource"] = jid.split("/", 1)[1] if "/" in jid else ""
        for room, users in self._muc_users.items():
            for nick, info in users.items():
                if (info.get("real_jid", "") == jid
                        or info.get("avatar_jid", "") == jid
                        or f"{room}/{nick}" == jid):
                    status["presence"] = info.get("show", "")
                    status["status_message"] = info.get("status", "")
                    status["resource"] = nick
                    status["status_updated"] = info.get("status_updated", "")
        dlg = VCardInfoDialog(jid, card, status=status)
        self._vcard_dialogs[jid] = dlg
        dlg.finished.connect(lambda _result, key=jid:
                             self._vcard_dialogs.pop(key, None))
        if self._client:
            self._client.probe_entity(jid)
        dlg.open()

    def _on_entity_info_received(self, jid: str, info: dict):
        dialog = self._vcard_dialogs.get(jid)
        if dialog is not None:
            dialog.update_status(info)

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
        from stanza_im.include.vcard import parse_vcard
        from stanza_im.ui.vcard_dialog import VCardEditDialog
        my = self._client.jid_str
        card = {}
        try:
            iq = await self._client.xmpp.plugin["xep_0054"].get_vcard(my)
            card = parse_vcard(iq)
        except Exception:
            pass
        if isinstance(card, dict) and "jid" in card:
            card["jid"] = my
        dlg = VCardEditDialog(card or {"jid": my}, self)
        if not dlg.exec():
            return
        if await self._client.set_own_vcard(dlg.collect()):
            QtWidgets.QMessageBox.information(self, APP_NAME,
                                              tr("vcard_saved"))
        else:
            QtWidgets.QMessageBox.warning(self, APP_NAME,
                                          tr("vcard_save_error"))

    def _recount_groups(self):
        """Recount online/total per group after presence changes."""
        for group in self._roster._groups.values():
            group.online_count = 0
            group.total_count = 0
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
        old_show = next((user.status for user in self._roster._users
                         if user.jid == bare_jid), "offline")
        self._roster.update_user(bare_jid, status=show, status_message=status,
                                 icon_key=show_to_icon_key(show))
        chat = self._chat_window.get_chat(bare_jid)
        if chat and self._config.chat.show_status and old_show != show:
            chat.add_status(tr("status_changed", status=tr(f"status_{show}")),
                            time.strftime("%H:%M:%S"))
        self._recount_groups()
        self._roster.sort_and_update()
        self._maybe_osd_status(bare_jid, show, old_show)

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

    def _seed_muc_chat(self, room: str, chat, *, title: str = "",
                       is_new: bool = False) -> None:
        """Push the current MUC occupant state into an open tab."""
        self_nick = self._muc_self_nicks.get(room, "")
        users = self._muc_users.get(room, {})
        chat.set_self_nick(self_nick)
        chat.update_muc_users(list(users.values()), self_nick=self_nick)
        chat_title = title or self._muc_display_name(room)
        if self._client:
            chat.set_subject(self._client.get_muc_subjects(room))
        self._chat_window.set_chat_title(room, chat_title)
        chat.set_bookmarked(room in self._bookmarks)
        if is_new:
            self._load_history(room)
            self._request_vcard(room, force=True)

    def _on_contact_open(self, jid: str):
        display_name = self._roster_name(jid) or jid.split("@")[0]
        if jid in self._muc_self_nicks:
            is_new = not self._chat_window.has_chat(jid)
            chat = self._chat_window.open_groupchat(
                jid, self._muc_self_nicks[jid], display_name)
            self._seed_muc_chat(jid, chat, title=display_name, is_new=is_new)
            return
        is_new = not self._chat_window.has_chat(jid)
        self._chat_window.open_chat(jid, display_name)
        if is_new:
            self._load_history(jid)
        self._reset_unread(jid)
        self._request_vcard(jid)

    def _load_history(self, jid: str):
        """Feed previously saved messages from the SQLite history into chat."""
        from stanza_im.core import history
        chat = self._chat_window.get_chat(jid)
        if not chat:
            return
        if not os.path.isfile(history._path(jid)):
            history.migrate_from_jsonl(jid)
        try:
            limit = int(self._config.chat.history_limit)
        except (TypeError, ValueError):
            limit = _HISTORY_BATCH_LIMIT
        limit = min(limit, _HISTORY_BATCH_LIMIT)
        entries = history.load_history(jid, limit=limit)
        exhausted = bool(entries) and not history.older_available_timestamp(
            jid, entries[0].get("timestamp", ""))
        chat.set_history(entries, limit, exhausted)

    def _on_contact_context(self, jid: str, pos):
        menu = QtWidgets.QMenu(self)
        def defer(callback):
            menu.close()
            QtCore.QTimer.singleShot(0, callback)

        is_conf = (jid in self._conference_roster or jid in self._muc_self_nicks)
        menu.addAction(self._menu_icon("message.png"), tr("ctx_open_chat"),
                       lambda: self._on_contact_open(jid))
        menu.addAction(self._menu_icon("v-card.png"), tr("ctx_view_profile"),
                       lambda checked=False: defer(lambda: self._show_profile(jid)))
        if self._client:
            send_menu = menu.addMenu(self._menu_icon("upload.png"),
                                     tr("ctx_send_file"))
            send_menu.addAction(
                tr("ft_p2p"),
                lambda checked=False: defer(lambda: self._pick_and_send_file(jid, "p2p")))
            send_menu.addAction(
                tr("ft_http_upload"),
                lambda checked=False: defer(lambda: self._pick_and_send_file(jid, "http")))
        menu.addAction(self._menu_icon("history.png"), tr("ctx_show_history"),
                       lambda checked=False: defer(lambda: self._on_history_contact(jid)))
        if not is_conf:
            menu.addSeparator()
            menu.addAction(self._menu_icon("edit.png"), tr("ctx_rename"),
                           lambda checked=False: defer(lambda: self._rename_contact(jid)))
            group_menu = menu.addMenu(self._menu_icon("system-users.png"),
                                      tr("ctx_group"))
            current_groups = {user.group for user in self._roster._users
                              if user.jid == jid}
            current_groups.discard(tr("roster_group_ungrouped"))
            no_group = group_menu.addAction(tr("ctx_no_group"))
            no_group.setCheckable(True)
            no_group.setChecked(not current_groups)
            no_group.triggered.connect(lambda: self._set_contact_groups(jid, []))
            group_menu.addSeparator()
            groups = sorted({user.group for user in self._roster._users
                             if user.group not in (tr("roster_group_conferences"),
                                                   tr("roster_group_transports"),
                                                   tr("roster_group_ungrouped"))},
                            key=str.casefold)
            for group in groups:
                action = group_menu.addAction(group)
                action.setCheckable(True)
                action.setChecked(group in current_groups)
                action.triggered.connect(
                    lambda checked, group=group: self._set_contact_groups(jid, [group]))
            group_menu.addSeparator()
            group_menu.addAction(
                tr("ctx_create_group"),
                lambda checked=False: defer(lambda: self._create_contact_group(jid)))
            if self._client:
                menu.addAction(self._menu_icon("reload.png"), tr("ctx_resend_auth"),
                               lambda: self._client.resend_subscription(jid))
        menu.addSeparator()
        menu.addAction(self._menu_icon("process-stop.png"),
                       tr("ctx_clear_history"), lambda: self._on_clear_history(jid))
        if is_conf:
            menu.addAction(self._menu_icon("process-stop.png"),
                           tr("ctx_leave_conference"),
                           lambda: defer(lambda: self._on_leave_conference(jid)))
        else:
            menu.addAction(self._menu_icon("process-stop.png"),
                           tr("ctx_remove_contact"), lambda: self._on_remove_contact(jid))
        menu.exec(pos)

    def _pick_and_send_file(self, jid: str, method: str):
        paths, _filter = QtWidgets.QFileDialog.getOpenFileNames(self)
        paths = [p for p in (paths or []) if p]
        if paths:
            self._on_chat_files_upload(jid, paths, method, self)

    def _rename_contact(self, jid: str):
        current = self._roster_name(jid) or jid.split("@")[0]
        name, ok = QtWidgets.QInputDialog.getText(
            self, tr("ctx_rename"), tr("ctx_rename_prompt"), text=current)
        if not ok:
            return
        name = name.strip()
        self._client.update_contact(jid, name=name)
        self._roster.update_user(jid, name=name)
        self._remember_contact(jid, name=name)

    def _move_to_group(self, jid: str):
        if not self._client:
            return
        group, ok = QtWidgets.QInputDialog.getText(
            self, tr("ctx_move_group"), tr("ctx_move_group_prompt"))
        if not ok:
            return
        groups = [g.strip() for g in group.strip().split(",") if g.strip()]
        self._client.update_contact(jid, groups=groups)

    def _set_contact_groups(self, jid: str, groups: list[str]):
        if self._client:
            self._client.update_contact(jid, groups=groups)
        self._remember_contact(jid, groups=groups)

    def _create_contact_group(self, jid: str):
        name, ok = QtWidgets.QInputDialog.getText(
            self, tr("ctx_create_group"), tr("ctx_group_name"))
        if ok and name.strip():
            self._set_contact_groups(jid, [name.strip()])

    def _on_clear_history(self, jid: str):
        from stanza_im.core import history
        history.clear(jid)
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.history_cleared()

    # ── History manager ───────────────────────────────────────────

    def _remember_contact(self, jid: str, name: str = "",
                          groups: list[str] | None = None,
                          is_conference: bool | None = None):
        """Persist JID → name/groups/conference so removed contacts and
        inactive rooms keep their names in the history manager."""
        if not jid:
            return
        from stanza_im.core import known_contacts
        entry = known_contacts.get(jid)
        if is_conference is None:
            is_conference = entry.get("is_conference", False)
        known_contacts.update(
            jid,
            name=name or entry.get("name", ""),
            groups=list(groups) if groups is not None else None,
            is_conference=is_conference)

    def _history_catalog(self) -> list[dict]:
        """Build the contact catalog for the history manager.

        Merges the live roster (names/groups take precedence), the persisted
        known-contacts registry (removed contacts / inactive rooms) and the
        history files themselves (unrecognised JIDs).  Each entry carries
        ``{"jid", "name", "groups": [...], "is_conference": bool}``.
        """
        from stanza_im.core import history, known_contacts
        entries: dict[str, dict] = {}
        for user in self._roster._users:
            entry = entries.setdefault(user.jid, {
                "jid": user.jid,
                "name": user.name or user.jid,
                "groups": [],
                "is_conference": user.jid in self._conference_roster,
            })
            if user.name:
                entry["name"] = user.name or entry["name"]
            if user.group not in entry["groups"]:
                entry["groups"].append(user.group)
        for jid, data in known_contacts.all().items():
            entry = entries.setdefault(jid, {
                "jid": jid,
                "name": data.get("name") or jid.split("@", 1)[0],
                "groups": [],
                "is_conference": bool(data.get("is_conference")),
            })
            if jid in self._conference_roster:
                entry["is_conference"] = True
            if not entry["groups"]:
                entry["groups"] = list(data.get("groups", []))
            if entry["is_conference"] and tr("roster_group_conferences") \
                    not in entry["groups"]:
                entry["groups"].insert(0, tr("roster_group_conferences"))
        for jid in history.list_history_jids():
            contacts = {u.jid for u in self._roster._users}
            if jid not in entries and jid not in contacts:
                entries[jid] = {
                    "jid": jid,
                    "name": jid.split("@", 1)[0],
                    "groups": [],
                    "is_conference": False,
                }
        for entry in entries.values():
            if not entry["groups"]:
                entry["groups"] = [tr("category_personal")]
        return list(entries.values())

    def _on_history_manager(self):
        self._open_history_manager("")

    def _on_history_contact(self, jid: str):
        self._open_history_manager(jid)

    def _open_history_manager(self, jid: str):
        from stanza_im.ui.history_manager import HistoryManagerDialog
        if self._history_manager is None:
            self._history_manager = HistoryManagerDialog(
                self._history_catalog, parent=self)
        self._history_manager.open_for(jid)
        self._history_manager.show()
        self._history_manager.raise_()
        self._history_manager.activateWindow()

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
            limit = _HISTORY_BATCH_LIMIT
        limit = min(limit, _HISTORY_BATCH_LIMIT)
        try:
            stored = await client.fetch_history_mam(jid, since, limit)
        except Exception:
            stored = None
        chat = self._chat_window.get_chat(jid)
        if stored is None:
            logger.info("MAM request for %s skipped: another request is active",
                        jid)
            return
        if chat:
            logger.info("MAM history for %s stored %d messages", jid, stored or 0)
            chat.set_history_status(
                tr("history_server_loaded", n=stored or 0)
                if stored else tr("history_server_empty"))
            chat.server_fetch_done(stored or 0)

    def _on_mam_parse_error(self, jid: str, results: int,
                            parsed: int, skipped: int):
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.set_history_status(tr("history_server_parse_error"))

    def _on_mam_unavailable(self, jid: str):
        chat = self._chat_window.get_chat(jid)
        if not chat:
            return
        from stanza_im.include.utils import format_time
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
        if self._client:
            self._client.mds_mark_displayed(jid)

    def _on_message_received(self, frm: str, body: str, ts,
                             unstyled: bool = False,
                             reply_able_id: str = "", reply_author: str = "",
                             reply_to: str = "", reply_id: str = "",
                             carbon: bool = False):
        bare_jid = frm.split("/")[0]
        sender_name = self._roster_name(bare_jid) or bare_jid.split("@")[0]
        self._remember_contact(bare_jid, name=sender_name,
                               is_conference=False)

        if not self._chat_window.has_chat(bare_jid):
            self._chat_window.open_chat(bare_jid, sender_name, focus=False)

        chat = self._chat_window.get_chat(bare_jid)
        if chat:
            chat.add_message(sender=sender_name, body=body,
                             timestamp=ts or _current_timestamp(),
                             direction="incoming", unstyled=unstyled,
                             reply_able_id=reply_able_id,
                             reply_author=reply_author or frm,
                             reply_to=reply_to, reply_id=reply_id)

        from stanza_im.core import history
        history.store_message(bare_jid, "incoming", body,
                              timestamp=ts or _current_timestamp(),
                              sender=sender_name,
                              origin_id=reply_able_id,
                              reply_to=reply_to, reply_id=reply_id)

        # Unread badge + tray blink (skip when conversation is on screen)
        active = (self._chat_window.isVisible()
                  and self._chat_window.current_jid() == bare_jid)
        if not active:
            self._bump_unread(bare_jid)
            self._unread_total += 1
            if self._config.notifications.tray_blink:
                self._tray.start_blinking()
        if active and self._client:
            self._client.mds_mark_displayed(bare_jid)
        if self._config.notifications.popups and not active:
            popup_body = (f"* {sender_name} {body[4:]}"
                          if isinstance(body, str) and body.startswith("/me ")
                          else body)
            self._tray.show_message(sender_name, popup_body)
        self._maybe_osd_message(sender_name, body, bare_jid)
        if not carbon:
            self._request_vcard(bare_jid)

    def _on_message_carbon_sent(self, jid: str, body: str, ts,
                                stable_id: str = "", reply_to: str = "",
                                reply_id: str = ""):
        """A message sent from another of our resources (XEP-0280 carbon).

        Shown as our own outgoing message in the target chat and stored in
        history, so every device keeps the same conversation view.
        """
        if not isinstance(jid, str) or not jid.strip():
            return
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.add_message(
                sender="Me", body=body,
                timestamp=ts or _current_timestamp(), direction="outgoing",
                message_id=stable_id,
                reply_able_id=stable_id, reply_author=jid,
                reply_to=reply_to, reply_id=reply_id)
        self._remember_contact(jid)
        from stanza_im.core import history
        history.store_message(
            jid, "outgoing", body,
            timestamp=ts or _current_timestamp(), sender="Me",
            origin_id=stable_id, reply_to=reply_to, reply_id=reply_id)

    def _on_mds_displayed(self, chat_jid: str):
        """Another of our devices flagged *chat_jid* as displayed (XEP-0490)."""
        bare = chat_jid.split("/")[0]
        self._reset_unread(bare)
        chat = self._chat_window.get_chat(bare)
        if chat:
            chat.add_status(tr("mds_displayed_elsewhere"),
                            time.strftime("%H:%M:%S"))

    def _on_muc_private_message(self, room: str, nick: str,
                                 body: str, ts, unstyled: bool = False,
                                 reply_able_id: str = "", reply_author: str = "",
                                 reply_to: str = "", reply_id: str = ""):
        info = self._participant_info(room, nick)
        real_jid = info.get("real_jid")
        target = real_jid.strip() if isinstance(real_jid, str) else ""
        if not target or target.lower() == "none":
            target = f"{room}/{nick}"
        self._remember_contact(target, name=nick, is_conference=True)
        chat = self._chat_window.open_chat(target, nick)
        chat.add_message(sender=nick, body=body,
                         timestamp=ts or _current_timestamp(), direction="incoming",
                         unstyled=unstyled,
                         sender_jid=info.get("avatar_jid", "") or target,
                         reply_able_id=reply_able_id,
                         reply_author=reply_author or f"{room}/{nick}",
                         reply_to=reply_to, reply_id=reply_id)
        from stanza_im.core import history
        history.store_message(target, "incoming", body,
                              timestamp=ts or _current_timestamp(), sender=nick,
                              origin_id=reply_able_id,
                              reply_to=reply_to, reply_id=reply_id)
        self._maybe_osd_message(nick, body, target)
        if (self._client and self._chat_window.isVisible()
                and self._chat_window.current_jid() == target):
            self._client.mds_mark_displayed(target)

    def _on_message_send(self, jid: str, body: str):
        if self._client and isinstance(jid, str) and jid.strip():
            jid = jid.strip()
            message_id = self._client.send_message(jid, body)
            chat = self._chat_window.get_chat(jid)
            if chat:
                chat.add_message(sender="Me", body=body,
                                 timestamp=_current_timestamp(), direction="outgoing",
                                 message_id=message_id,
                                 reply_able_id=message_id,
                                 reply_author=jid)
            from stanza_im.core import history
            history.store_message(
                jid, "outgoing", body,
                timestamp=_current_timestamp(), sender="Me",
                origin_id=message_id)
            self._remember_contact(jid)

    # ── Groupchat ─────────────────────────────────────────────────

    def _on_groupchat_message(self, room: str, nick: str, body: str,
                              ts, archived: bool = False,
                              archive_id: str = "", unstyled: bool = False,
                              reply_able_id: str = "", reply_author: str = "",
                              reply_to: str = "", reply_id: str = ""):
        if archived:
            from stanza_im.core import history
            history.store_message(room, "incoming", body,
                                  timestamp=ts or _current_timestamp(),
                                  sender=nick, archive_id=archive_id,
                                  origin_id=reply_able_id,
                                  reply_to=reply_to, reply_id=reply_id)
            return
        logger.debug("Live groupchat message: room=%s nick=%s archive_id=%s",
                     room, nick, archive_id or "none")
        reply_ref_id = reply_able_id or archive_id
        chat = self._chat_window.get_chat(room)
        logger.debug("Groupchat live: room=%s nick=%s chat_present=%s",
                     room, nick, chat is not None)
        if chat:
            user = self._muc_users.get(room, {}).get(nick, {})
            chat.add_message(sender=nick, body=body,
                             timestamp=ts or _current_timestamp(),
                             direction="incoming",
                             unstyled=unstyled,
                             sender_jid=(user.get("avatar_jid", "")
                                         or user.get("real_jid", "")),
                             archive_id=archive_id,
                             reply_able_id=reply_ref_id,
                             reply_author=reply_author or f"{room}/{nick}",
                             reply_to=reply_to, reply_id=reply_id)
        from stanza_im.core import history
        history.store_message(room, "incoming", body,
                              timestamp=ts or _current_timestamp(), sender=nick,
                              origin_id=reply_ref_id,
                              reply_to=reply_to, reply_id=reply_id)
        self._maybe_osd_groupchat(room, nick, body)
        if (self._client and self._chat_window.isVisible()
                and self._chat_window.current_jid() == room):
            self._client.mds_mark_displayed(room)
        self._remember_contact(room, name=self._muc_display_name(room),
                               groups=[tr("roster_group_conferences")],
                               is_conference=True)

    def _on_groupchat_presence(self, room: str, nick: str, show: str,
                               status: str, role: str = "",
                               affiliation: str = "", real_jid: str = ""):
        users = self._muc_users.setdefault(room, {})
        was_present = nick in users
        previous_show = users.get(nick, {}).get("show", "")
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
                "client": previous.get("client", ""),
                "status_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            if self._client:
                request_jid = (real_jid if isinstance(real_jid, str)
                               and real_jid.lower() != "none" else "")
                self._client.get_vcard(request_jid or f"{room}/{nick}")
        chat = self._chat_window.get_chat(room)
        if chat:
            self_nick = self._muc_self_nicks.get(room, "")
            chat.update_muc_users(list(users.values()), self_nick=self_nick)
            if self._config.chat.muc_show_presence and show == "unavailable":
                chat.add_status(tr("muc_user_left", nick=nick), time.strftime("%H:%M:%S"))
            elif self._config.chat.muc_show_presence and not was_present:
                chat.add_status(tr("muc_user_joined", nick=nick), time.strftime("%H:%M:%S"))
            elif (self._config.chat.muc_show_status and was_present
                  and previous_show != show):
                from stanza_im.include.utils import escape_html
                msg = tr("muc_status_changed",
                         nick=escape_html(nick),
                         status=tr(f"status_{show}"))
                if self._config.chat.muc_show_status_text and status.strip():
                    msg += f" ({escape_html(status.strip())})"
                chat.add_status(msg, time.strftime("%H:%M:%S"))
        if nick == self._muc_self_nicks.get(room):
            self._sync_conference_roster(room)

    def _on_groupchat_presence_details(self, room: str, nick: str):
        """A participant's client (XEP-0092) arrived later — refresh tooltips."""
        if not self._client:
            return
        gi = self._client.groupchats.get(room)
        client = gi.users.get(nick, {}).get("client", "") if gi else ""
        if not client:
            return
        users = self._muc_users.setdefault(room, {})
        if nick in users:
            users[nick]["client"] = client
        chat = self._chat_window.get_chat(room)
        if chat:
            chat.update_muc_users(list(users.values()),
                                  self_nick=self._muc_self_nicks.get(room, ""))

    def _on_groupchat_send(self, room: str, body: str):
        if self._client:
            self._client.send_muc_message(room, body)

    # ── XEP-0461 reply sends ──────────────────────────────────────

    def _on_message_reply_send(self, jid: str, body: str, reply_to: str,
                               reply_id: str, ref_sender: str,
                               ref_body: str):
        if not (self._client and isinstance(jid, str) and jid.strip()):
            return
        jid = jid.strip()
        message_id = self._client.send_message(
            jid, body, reply_to=reply_to, reply_id=reply_id,
            reply_ref_sender=ref_sender, reply_ref_body=ref_body)
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.add_message(
                sender="Me", body=body,
                timestamp=_current_timestamp(), direction="outgoing",
                message_id=message_id,
                reply_able_id=message_id, reply_author=jid,
                reply_to=reply_to, reply_id=reply_id)
        from stanza_im.core import history
        history.store_message(
            jid, "outgoing", body,
            timestamp=_current_timestamp(), sender="Me",
            origin_id=message_id, reply_to=reply_to, reply_id=reply_id)
        self._remember_contact(jid)

    def _on_groupchat_reply_send(self, room: str, body: str, reply_to: str,
                                 reply_id: str, ref_sender: str,
                                 ref_body: str):
        if self._client:
            self._client.send_muc_message(
                room, body, reply_to=reply_to, reply_id=reply_id,
                reply_ref_sender=ref_sender, reply_ref_body=ref_body)

    def _on_message_edit_send(self, jid: str, body: str, edit_id: str):
        """Send a XEP-0308 correction (1:1) and replace it locally."""
        if not (self._client and isinstance(jid, str) and jid.strip()):
            return
        jid = jid.strip()
        self._client.edit_message(jid, body, edit_id)
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.edit_message_by_ref(edit_id, body)
        from stanza_im.core import history
        history.replace_message(jid, edit_id, body)
        self._remember_contact(jid)

    def _on_groupchat_edit_send(self, room: str, body: str, edit_id: str):
        if self._client:
            self._client.edit_message(room, body, edit_id, mtype="groupchat")
        self._remember_contact(room, name=self._muc_display_name(room),
                               groups=[tr("roster_group_conferences")],
                               is_conference=True)

    def _on_chat_vcard(self, jid: str):
        if jid in self._muc_self_nicks:
            self._show_muc_room_info(jid)
        else:
            self._show_profile(jid)

    def _on_input_height_changed(self, jid: str, height: int):
        self._config.chat.input_height = max(40, min(240, int(height)))
        self._config.save()

    def _on_text_scale_changed(self, jid: str, factor: float):
        try:
            factor = max(0.5, min(3.0, float(factor)))
        except (TypeError, ValueError):
            factor = 1.0
        self._config.chat.text_scale = factor
        self._config.save()

    def _on_chat_window_closed(self):
        self._chat_window.save_geometry(self._config.chat_window)
        self._config.save()

    @staticmethod
    def _place_dialog_over(dlg, window) -> None:
        """Center *dlg* over *window* so it appears above the source window
        (some WM/style combinations do not center child dialogs on show)."""
        if window is None:
            return
        dlg.adjustSize()
        geo = window.geometry()
        dlg.move(geo.center() - dlg.rect().center())

    def _on_chat_files_upload(self, jid: str, paths: list, method: str,
                              parent=None):
        if not self._client:
            return
        paths = [str(p) for p in (paths or []) if p]
        if not paths:
            return
        from stanza_im.ui.upload_dialog import FileTransferDialog
        parent = parent or self
        dlg = FileTransferDialog(paths, parent)
        self._place_dialog_over(dlg, parent)
        dlg.upload_started.connect(
            lambda caption: self._launch_file_uploads(jid, paths, method,
                                                      caption, dlg))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _launch_file_uploads(self, jid: str, paths: list, method: str,
                             caption: str, dlg):
        """Start per-file transfers and update the dialog rows."""

        def _relay_p2p(index: int, path: str):
            # P2P is still a placeholder; mark the row as failed immediately.
            self._client.send_file(jid, str(path))
            dlg.set_row_failed(index, tr("ft_p2p_unavailable"))
            self._file_upload_states.pop((jid, str(path)), None)
            self._check_uploads_finished(jid)

        tasks = []
        self._file_uploads[jid] = (dlg, list(paths))
        for index, path in enumerate(paths):
            path = str(path)
            self._file_upload_states[(jid, path)] = (dlg, index)
            if method == "p2p":
                _relay_p2p(index, path)
            else:
                tasks.append(
                    self._start_task(self._client.upload_http(jid, path)))
        if caption and tasks:
            self._start_task(self._send_caption_after(jid, caption, tasks))

    def _display_local_outgoing(self, jid: str, body: str, message_id: str):
        """Show our own 1:1 message locally (no carbons echo reaches the
        sending resource, so the client renders the stanza itself)."""
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.add_message(
                sender="Me", body=body,
                timestamp=_current_timestamp(), direction="outgoing",
                message_id=message_id,
                reply_able_id=message_id, reply_author=jid)
        from stanza_im.core import history
        history.store_message(
            jid, "outgoing", body,
            timestamp=_current_timestamp(), sender="Me",
            origin_id=message_id)
        self._remember_contact(jid)

    async def _send_caption_after(self, jid: str, caption: str, tasks):
        """Send the shared caption once, after the batch finished uploading."""
        await asyncio.gather(*tasks, return_exceptions=True)
        target = jid.split("/")[0] if "/" in jid else jid
        if self._client.groupchats.get(target):
            self._client.send_muc_message(target, caption)
        else:
            message_id = self._client.send_message(target, caption)
            self._display_local_outgoing(target, caption, message_id)

    def _check_uploads_finished(self, jid: str):
        batch = self._file_uploads.get(jid)
        if not batch:
            return
        dlg, paths = batch
        if any((jid, path) in self._file_upload_states for path in paths):
            return
        self._file_uploads.pop(jid, None)
        dlg.close()

    def _on_file_upload_progress(self, jid: str, phase: str, detail: str = "",
                                 path: str = ""):
        bare = jid.split("/")[0]
        chat = self._chat_window.get_chat(bare) or self._chat_window.get_chat(jid)
        state = self._file_upload_states.get((jid, path), (None, -1))
        dlg, index = state if state else (None, -1)
        if phase == "progress":
            if dlg is not None:
                dlg.set_progress(index, int(detail or 0))
            return
        if phase == "start":
            if chat:
                chat.add_status(tr("ft_upload_started",
                                   file=os.path.basename(path or detail)),
                                time.strftime("%H:%M:%S"))
            return
        self._file_upload_states.pop((jid, path), None)
        if phase == "done":
            if dlg is not None:
                dlg.set_progress(index, 100)
                dlg.set_row_done(index)
            # Show the file URL as a real outgoing message (clickable link)
            # instead of a plain-text status line. In MUC the room echo
            # already renders it, so only do this for 1:1.
            target = jid.split("/")[0] if "/" in jid else jid
            if not (self._client and self._client.groupchats.get(target)):
                self._display_local_outgoing(target, detail, uuid.uuid4().hex)
        elif phase == "error":
            if dlg is not None:
                dlg.set_row_failed(index, detail or "")
            if chat:
                chat.add_status(tr("ft_upload_failed", error=detail or ""),
                                time.strftime("%H:%M:%S"))
        self._check_uploads_finished(jid)

    def _show_muc_room_info(self, room: str):
        member = self._muc_users.get(room, {}).get(
            self._muc_self_nicks.get(room, ""), {})
        self._show_profile(member.get("real_jid") or room)

    def _on_message_corrected(self, frm: str, ref_id: str, body: str, ts,
                              unstyled: bool = False,
                              stable_id: str = "", reply_to: str = "",
                              reply_id: str = ""):
        """A contact corrected a message they sent (XEP-0308)."""
        bare = frm.split("/")[0]
        chat = self._chat_window.get_chat(bare) or self._chat_window.get_chat(frm)
        if chat:
            chat.edit_message_by_ref(ref_id, body)
        from stanza_im.core import history
        history.replace_message(bare, ref_id, body)

    def _on_groupchat_message_corrected(self, room: str, ref_id: str,
                                        body: str, ts, unstyled: bool = False,
                                        stable_id: str = "", frm: str = "",
                                        reply_to: str = "",
                                        reply_id: str = ""):
        """A participant corrected their MUC message (XEP-0308)."""
        chat = self._chat_window.get_chat(room)
        if chat:
            chat.edit_message_by_ref(ref_id, body)
        from stanza_im.core import history
        history.replace_message(room, ref_id, body)

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
        profile = menu.addAction(self._menu_icon("v-card.png"),
                                 tr("muc_user_view_vcard"))
        profile.triggered.connect(
            lambda: self._show_muc_participant_profile(room, nick, real_jid))
        command = menu.addAction(self._menu_icon("exec.png"),
                                 tr("muc_user_execute_command"))
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
            from stanza_im.include.utils import format_time
            chat.add_status(tr("muc_user_command_unavailable"), format_time())

    def _change_muc_role(self, room: str, nick: str, role: str):
        if not self._client:
            return
        self._client.set_muc_role(room, nick, role)

    # ── Status ────────────────────────────────────────────────────

    def _on_typing(self, jid: str, is_typing: bool):
        """A contact started/stopped composing (XEP-0085)."""
        if not self._config.privacy.send_typing_notifications:
            return
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.set_typing(self._roster_name(jid) or jid.split("@")[0], is_typing)
        if is_typing:
            self._maybe_osd_typing(jid)

    def _on_typing_local(self, jid: str, is_typing: bool):
        if self._client:
            self._client.send_chat_state(jid, "composing" if is_typing else "paused")

    def _on_chat_activity(self, jid: str, state: str):
        if self._client:
            self._client.send_chat_state(jid, state)

    def _on_chatstate_received(self, jid: str, state: str):
        if self._config.privacy.send_typing_notifications:
            chat = self._chat_window.get_chat(jid)
            if chat:
                chat.set_typing(self._roster_name(jid) or jid.split("@")[0],
                                state == "composing")
        if state in ("active", "inactive", "gone"):
            self._chat_window.set_remote_activity(jid, state)
        logger.debug("Chat state from %s: %s", jid, state)

    def _on_receipt_delivered(self, jid: str, message_id: str = ""):
        if not self._config.chat.show_receipts:
            return
        from stanza_im.include.utils import format_time
        chat = self._chat_window.get_chat(jid)
        if chat:
            chat.mark_delivered(message_id)

    # ── OSD helpers ─────────────────────────────────────────────

    @staticmethod
    def _osd_body(text, limit: int = 180) -> str:
        text = " ".join((text or "").split())
        if len(text) > limit:
            text = text[:limit] + "…"
        return text

    def _osd_for(self, jid) -> bool:
        """True when the app is not focused on *jid*'s chat.

        The chat window may stay visible while the roster (or another app)
        is active, so gate on the actual active window, not mere visibility.
        """
        return not (self._chat_window.isActiveWindow()
                    and self._chat_window.current_jid() == jid)

    def _osd_click(self, jid, nick: str = ""):
        self._chat_window.show()
        self._chat_window.raise_()
        self._chat_window.activateWindow()
        self._on_contact_open(jid)

    def _maybe_osd_message(self, title: str, body: str, jid: str):
        cfg = self._config.notifications
        if not cfg.osd_enabled or not cfg.osd_message or not self._osd_for(jid):
            return
        self._osd.show(QtGui.QIcon(), title, self._osd_body(body),
                       on_click=lambda: self._osd_click(jid))

    def _maybe_osd_typing(self, jid: str):
        cfg = self._config.notifications
        if not cfg.osd_enabled or not cfg.osd_typing or not self._osd_for(jid):
            return
        name = self._roster_name(jid) or jid.split("@")[0]
        self._osd.show(QtGui.QIcon(), tr("osd_typing_title"),
                       tr("osd_typing", name=name),
                       on_click=lambda: self._osd_click(jid))

    def _maybe_osd_status(self, jid: str, new_show: str, old_show: str):
        cfg = self._config.notifications
        mode = getattr(cfg, "osd_status", "available")
        if not cfg.osd_enabled or mode == "never" or old_show == new_show:
            return
        if jid not in self._osd_status_seen:
            self._osd_status_seen.add(jid)
            return

        def _available(show: str) -> bool:
            return show in ("online", "chat")

        if mode == "available" and _available(new_show) == _available(old_show):
            return
        name = self._roster_name(jid) or jid.split("@")[0]
        icon = QtGui.QIcon(self._icons.get_status_icon(new_show))
        self._osd.show(
            icon, name,
            tr("status_changed", status=tr(f"status_{new_show}")),
            on_click=lambda: self._osd_click(jid))

    def _maybe_osd_groupchat(self, room: str, nick: str, body: str):
        cfg = self._config.notifications
        mode = getattr(cfg, "osd_conference", "mention")
        if not cfg.osd_enabled or mode == "never" or not self._osd_for(room):
            return
        if mode == "mention":
            me = self._muc_self_nicks.get(room, "")
            if not me or me.lower() not in (body or "").lower():
                return
        title = nick or room
        if mode == "mention":
            title = self._muc_display_name(room) or room
            body = tr("osd_conference_mention", nick=nick, body=self._osd_body(body))
        self._osd.show(QtGui.QIcon(), title, self._osd_body(body),
                       on_click=lambda: self._osd_click(room, nick))

    def _notify_osd_file(self, sender: str, filename: str):
        """Entry point for incoming file-transfer notifications (used by the
        p2p file-transfer code once it is wired to incoming files)."""
        cfg = self._config.notifications
        if not cfg.osd_enabled or not cfg.osd_file:
            return
        self._osd.show(QtGui.QIcon(), sender or tr("osd_file"),
                       tr("osd_file", filename=filename or ""))

    def _on_status_change(self, index: int):
        show = self._status_combo.currentData()
        if not show:
            return
        self._config.last_status = show
        if self._client:
            self._client.send_presence(show=show)
        self._set_tray_status_icon(show)
        self._last_activity = time.monotonic()
        self._auto_status_applied = False

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.Type.MouseMove,
                            QtCore.QEvent.Type.MouseButtonPress,
                            QtCore.QEvent.Type.KeyPress,
                            QtCore.QEvent.Type.Wheel):
            self._last_activity = time.monotonic()
            if self._auto_status_applied and self._client:
                self._client.send_presence(show=self._config.last_status)
                self._set_tray_status_icon(self._config.last_status)
                self._auto_status_applied = False
        return super().eventFilter(obj, event)

    def _check_auto_status(self):
        if not self._client:
            return
        idle_minutes = (time.monotonic() - self._last_activity) / 60
        status = ""
        if self._config.status.auto_xa and idle_minutes >= self._config.status.xa_minutes:
            status = "xa"
        elif self._config.status.auto_away and idle_minutes >= self._config.status.away_minutes:
            status = "away"
        if status and not self._auto_status_applied:
            self._client.send_presence(show=status)
            self._set_tray_status_icon(status)
            self._auto_status_applied = True

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
        from stanza_im.core import history
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
        if self._shutting_down:
            return
        self._shutting_down = True
        self._tray.hide()
        self.hide()
        self._chat_window.close()
        self._start_task(self._shutdown_async())

    async def _shutdown_async(self):
        try:
            if self._client is not None and hasattr(self._client, "disconnect"):
                try:
                    await asyncio.wait_for(self._client.disconnect(), timeout=3.0)
                except Exception:
                    logger.debug("XMPP disconnect did not finish cleanly",
                                 exc_info=True)
        finally:
            current = asyncio.current_task()
            pending = [task for task in asyncio.all_tasks()
                       if task is not current and not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*pending, return_exceptions=True),
                        timeout=1.0)
                except asyncio.TimeoutError:
                    logger.debug("Some background tasks did not cancel in time")
            self.app.quit()

    def closeEvent(self, event):
        if self._shutting_down:
            event.accept()
            return
        self._save_window_geometry()
        if self._config.ui.close_to_tray:
            self.hide()
            self._visible = False
            event.ignore()
        else:
            self._quit()
            event.accept()
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
