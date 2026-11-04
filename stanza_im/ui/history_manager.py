"""History manager dialog.

Left pane: roster-style contact list grouped by roster groups (with per-group
contact counts) and a calendar whose bold dates mark days that have messages.
Right pane: a search row, an all-time search results list, a message browser
and day-navigation buttons.
"""
from __future__ import annotations

import asyncio
import logging
import os

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.core import history
from stanza_im.include.constants import ACTIONS_DIR_16, APP_ICON_16, \
    CATEGORIES_DIR_16, STATUS_DIR_32, find_icon
from stanza_im.include.utils import escape_html
from stanza_im.i18n import tr
from stanza_im.ui.resize_handle import VerticalResizeHandle
from stanza_im.ui.history_media import HistoryMediaView
from stanza_im.ui.media_meta import MediaMetadataService
from stanza_im.include.media import media_items_from_entry

logger = logging.getLogger(__name__)


def _time_of(ts: str) -> str:
    """Return ``HH:MM:SS`` from a stored timestamp string."""
    if not ts:
        return ""
    if len(ts) >= 19 and ts[10] == "T":
        return ts[11:19]
    return ts


def _stamp(ts: str) -> str:
    """Return ``YYYY-MM-DD HH:MM:SS`` from a stored timestamp string."""
    if not ts:
        return ""
    if len(ts) >= 19 and ts[10] == "T":
        return ts[:10] + " " + ts[11:19]
    return ts


def _icon(filename: str) -> QtGui.QIcon:
    path = find_icon(filename)
    if path:
        return QtGui.QIcon(path)
    for directory in (ACTIONS_DIR_16, CATEGORIES_DIR_16, STATUS_DIR_32,
                      APP_ICON_16):
        pix = QtGui.QPixmap(os.path.join(directory, filename))
        if not pix.isNull():
            return QtGui.QIcon(pix)
    return QtGui.QIcon()


def _mode_button(icon_name: str, tooltip: str) -> QtWidgets.QToolButton:
    """A compact, checkable, icon-only history-mode button."""
    button = QtWidgets.QToolButton()
    button.setIcon(_icon(icon_name))
    button.setIconSize(QtCore.QSize(16, 16))
    button.setToolButtonStyle(
        QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setCheckable(True)
    button.setAutoRaise(True)
    button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    return button


class HistoryManagerDialog(QtWidgets.QDialog):
    """Browser over locally stored per-contact chat history."""

    media_open_requested = QtCore.pyqtSignal(str, str)  # url, kind

    def __init__(self, catalog_provider, initial_jid: str = "",
                 parent=None, server_search=None, server_supported=None,
                 server_media=None, server_media_supported=None,
                 media_service=None):
        super().__init__(parent)
        self._catalog_provider = catalog_provider
        self._server_search = server_search
        self._server_supported = server_supported
        self._server_media = server_media
        self._server_media_supported = server_media_supported
        self._media_service = media_service
        self._meta_service = None
        if media_service is not None and getattr(media_service, "cache", None):
            self._meta_service = MediaMetadataService(
                media_service.cache, downloader=media_service, parent=self)
        self._media_views: dict[str, HistoryMediaView] = {}
        self._media_filters: dict[str, QtWidgets.QLineEdit] = {}
        self._media_buttons: dict[str, dict] = {}
        self._media_items: list[dict] = []
        self._media_local_key = None
        self._media_mode = {"all_time": True, "all_contacts": False,
                            "server": False}
        self._media_server_jid = ""
        self._media_server_cursor = ""
        self._media_server_complete = True
        self._media_server_loading = False
        self._media_server_ok = False
        self._media_request_id = 0
        self._media_empty_pages = 0
        self._media_auto_pages = 0
        self._catalog: list[dict] = []
        self._jid: str = ""
        self._name: str = ""
        self._dates: list[str] = []
        self._entries: list[dict] = []
        self._date: str = ""
        self._query: str = ""
        self._matches: list[int] = []
        self._match_index = -1
        self._all_days: list[str] = []
        self._message_blocks: list[int] = []
        #: ``{jid: [(date, count)]}`` of the last global (all-contacts) search.
        self._global_days: dict[str, list[tuple[str, int]]] = {}
        #: When set, the left tree shows only these JIDs (global search).
        self._catalog_filter: set[str] | None = None
        #: A day to select once the contact's dates have loaded (global result).
        self._pending_date = ""
        #: Guards a programmatic calendar update from re-entering its handler.
        self._syncing_calendar = False
        #: Guards a programmatic tree update from re-entering its handler.
        self._syncing_tree = False
        #: The running "load this contact's dates" task (awaited by a global
        #: result open so the pinned day is applied deterministically).
        self._dates_task = None
        self._released = False
        #: XEP-0431 server search (selected contact only, first page + more).
        self._server_jid = ""
        self._server_query = ""
        self._server_cursor = ""
        self._server_complete = True
        self._server_rows: list[dict] = []
        self._server_days: dict[str, int] = {}

        self.setWindowTitle(tr("history_manager"))
        self.resize(920, 620)
        self._build_ui()
        self._refresh()
        if initial_jid:
            self._select_jid(initial_jid)
        self._search.setFocus()

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

    def done(self, result):
        self._released = True
        super().done(result)

    def showEvent(self, event):
        # Reused as a singleton by MainWindow: ``done()`` marks the dialog
        # released so pending async work stops, but the instance is shown
        # again later.  Revive it on every show or all async loads would bail
        # out immediately (empty dates and no messages).
        self._released = False
        super().showEvent(event)

    def _set_results_height(self, height: int) -> None:
        """Resize the search-results list (the messages take the rest)."""
        height = max(40, min(400, int(height)))
        if height != self._results_height:
            self._results_height = height
            self._results.setFixedHeight(height)

    def _set_results_visible(self, visible: bool) -> None:
        """Show/hide the results list together with its resize handle."""
        self._results.setVisible(visible)
        self._results_handle.setVisible(visible)

    def _build_ui(self) -> None:
        layout = QtWidgets.QHBoxLayout(self)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # ── Left pane: contacts + calendar ────────────────────────
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._tree = QtWidgets.QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.itemSelectionChanged.connect(
            self._on_tree_selection_changed)
        left_layout.addWidget(self._tree, 1)
        self._empty_label = QtWidgets.QLabel(tr("history_no_contacts"))
        self._empty_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.hide()
        left_layout.addWidget(self._empty_label)
        self._calendar = QtWidgets.QCalendarWidget()
        self._calendar.setGridVisible(True)
        self._calendar.selectionChanged.connect(self._on_calendar_clicked)
        left_layout.addWidget(self._calendar)
        splitter.addWidget(left)

        # ── Right pane: tabs with the text browser and media grids ─
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._tabs = QtWidgets.QTabWidget()
        right_layout.addWidget(self._tabs, 1)

        text_page = QtWidgets.QWidget()
        text_layout = QtWidgets.QVBoxLayout(text_page)
        text_layout.setContentsMargins(8, 8, 8, 8)

        search_row = QtWidgets.QHBoxLayout()
        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText(tr("history_search_placeholder"))
        self._search.returnPressed.connect(self._on_search_run)
        search_row.addWidget(self._search, 1)
        self._btn_prev_match = QtWidgets.QToolButton()
        self._btn_prev_match.setToolTip(tr("history_search_prev"))
        self._btn_prev_match.setIcon(self.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_ArrowUp))
        self._btn_prev_match.clicked.connect(self._on_match_prev)
        self._btn_prev_match.setEnabled(False)
        search_row.addWidget(self._btn_prev_match)
        self._btn_next_match = QtWidgets.QToolButton()
        self._btn_next_match.setToolTip(tr("history_search_next"))
        self._btn_next_match.setIcon(self.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_ArrowDown))
        self._btn_next_match.clicked.connect(self._on_match_next)
        self._btn_next_match.setEnabled(False)
        search_row.addWidget(self._btn_next_match)
        self._btn_all_time = _mode_button(
            "history.png", tr("history_all_time"))
        self._btn_all_time.toggled.connect(self._on_mode_toggled)
        search_row.addWidget(self._btn_all_time)
        self._btn_all_contacts = _mode_button(
            "system-users.png", tr("history_all_contacts_tip"))
        self._btn_all_contacts.toggled.connect(self._on_all_contacts_toggled)
        search_row.addWidget(self._btn_all_contacts)
        self._btn_server = _mode_button(
            "globe.svg", tr("history_search_server_tip"))
        self._btn_server.toggled.connect(self._on_server_toggled)
        self._btn_server.setEnabled(False)
        search_row.addWidget(self._btn_server)
        text_layout.addLayout(search_row)

        self._results = QtWidgets.QListWidget()
        self._results_height = 140
        self._results.setFixedHeight(self._results_height)
        self._results.itemActivated.connect(self._on_result_picked)
        text_layout.addWidget(self._results)

        # A thin bar under the results resizes them (and the messages below);
        # session-only, like the chat input's own handle.
        self._results_handle = VerticalResizeHandle(
            get_height=lambda: self._results_height, invert=True)
        self._results_handle.height_changed.connect(self._set_results_height)
        text_layout.addWidget(self._results_handle)
        self._btn_server_more = QtWidgets.QPushButton(
            tr("history_search_server_more"))
        self._btn_server_more.setAutoDefault(False)
        self._btn_server_more.setDefault(False)
        self._btn_server_more.setFocusPolicy(
            QtCore.Qt.FocusPolicy.NoFocus)
        self._btn_server_more.clicked.connect(
            lambda: self._run_server_search(more=True))
        self._btn_server_more.setVisible(False)
        text_layout.addWidget(self._btn_server_more)
        self._set_results_visible(False)

        self._status = QtWidgets.QLabel()
        self._status.setWordWrap(True)
        text_layout.addWidget(self._status)

        self._messages = QtWidgets.QTextBrowser()
        self._messages.setOpenExternalLinks(True)
        text_layout.addWidget(self._messages, 1)

        nav_row = QtWidgets.QHBoxLayout()
        self._btn_refresh = QtWidgets.QToolButton()
        self._btn_refresh.setIcon(_icon("reload.png"))
        self._btn_refresh.setToolTip(tr("history_refresh"))
        self._btn_refresh.clicked.connect(self._refresh)
        nav_row.addWidget(self._btn_refresh)
        self._btn_export = QtWidgets.QToolButton()
        self._btn_export.setIcon(QtGui.QIcon(find_icon("export.svg")))
        self._btn_export.setToolTip(tr("history_export"))
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._on_export)
        nav_row.addWidget(self._btn_export)
        nav_row.addStretch(1)
        self._btn_first = QtWidgets.QPushButton(tr("history_first_day"))
        self._btn_first.setAutoDefault(False)
        self._btn_first.setDefault(False)
        self._btn_first.clicked.connect(lambda: self._jump_day(first=True))
        self._btn_first.setEnabled(False)
        nav_row.addWidget(self._btn_first)
        self._btn_prev_day = QtWidgets.QPushButton(tr("history_prev_day"))
        self._btn_prev_day.setAutoDefault(False)
        self._btn_prev_day.setDefault(False)
        self._btn_prev_day.clicked.connect(lambda: self._jump_day(-1))
        self._btn_prev_day.setEnabled(False)
        nav_row.addWidget(self._btn_prev_day)
        self._btn_next_day = QtWidgets.QPushButton(tr("history_next_day"))
        self._btn_next_day.setAutoDefault(False)
        self._btn_next_day.setDefault(False)
        self._btn_next_day.clicked.connect(lambda: self._jump_day(1))
        self._btn_next_day.setEnabled(False)
        nav_row.addWidget(self._btn_next_day)
        self._btn_last = QtWidgets.QPushButton(tr("history_last_day"))
        self._btn_last.setAutoDefault(False)
        self._btn_last.setDefault(False)
        self._btn_last.clicked.connect(lambda: self._jump_day(last=True))
        self._btn_last.setEnabled(False)
        nav_row.addWidget(self._btn_last)
        nav_row.addStretch(1)
        close_btn = QtWidgets.QPushButton(tr("dialog_close"))
        close_btn.setAutoDefault(False)
        close_btn.setDefault(False)
        close_btn.clicked.connect(self.accept)
        nav_row.addWidget(close_btn)
        text_layout.addLayout(nav_row)

        self._tabs.addTab(text_page, tr("history_tab_text"))
        for kind, label in (("image", "history_tab_photos"),
                            ("video", "history_tab_videos"),
                            ("audio", "history_tab_audio")):
            self._tabs.addTab(self._build_media_tab(kind), tr(label))
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._sync_media_buttons()

        splitter.addWidget(right)
        splitter.setSizes([280, 640])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _build_media_tab(self, kind: str) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        row = QtWidgets.QHBoxLayout()
        filter_edit = QtWidgets.QLineEdit()
        filter_edit.setPlaceholderText(tr("history_media_filter"))
        filter_edit.textChanged.connect(
            lambda text, k=kind: self._on_media_filter_changed(k, text))
        row.addWidget(filter_edit, 1)
        buttons = {}
        specs = (
            ("all_time", "history.png", "history_all_time"),
            ("all_contacts", "system-users.png", "history_all_contacts_tip"),
            ("server", "globe.svg", "history_search_server_tip"),
        )
        for name, icon_name, tip_key in specs:
            button = _mode_button(icon_name, tr(tip_key))
            button.toggled.connect(
                lambda checked, n=name: self._on_media_mode_toggled(n, checked))
            row.addWidget(button)
            buttons[name] = button
        buttons["server"].setEnabled(False)
        layout.addLayout(row)
        view = HistoryMediaView(
            kind, self._media_service, self._meta_service, page)
        view.open_requested.connect(self.media_open_requested)
        view.load_more.connect(
            lambda k=kind: self._on_media_load_more(k))
        layout.addWidget(view, 1)
        self._media_views[kind] = view
        self._media_filters[kind] = filter_edit
        self._media_buttons[kind] = buttons
        return page

    # ── Catalog / contacts ───────────────────────────────────────

    def open_for(self, jid: str = "") -> None:
        """Refresh the catalog and show *jid* (or keep the current one)."""
        self._released = False
        self._refresh()
        if jid:
            self._select_jid(jid)
        self._search.setFocus()

    def _refresh(self) -> None:
        try:
            catalog = list(self._catalog_provider() or [])
        except Exception:
            catalog = []
        self._catalog = catalog
        self._rebuild_tree()
        wanted = self._jid
        self._set_contact("", "")
        if wanted and any(c["jid"] == wanted for c in catalog):
            self._select_jid(wanted)
        elif self._catalog:
            self._select_jid(self._catalog[0]["jid"])

    def _rebuild_tree(self) -> None:
        self._tree.blockSignals(True)
        self._syncing_tree = True
        self._tree.clear()
        app_icon = _icon("stanza-im.png")
        catalog = self._catalog
        if self._catalog_filter is not None:
            catalog = [c for c in catalog if c["jid"] in self._catalog_filter]
        groups: dict[str, list[dict]] = {}
        for contact in catalog:
            for group in contact["groups"]:
                groups.setdefault(group, []).append(contact)
        # In the global (all-contacts) search the whole tree is expanded so the
        # matching contacts are visible at a glance; otherwise only the working
        # contact matters and the groups stay collapsed.
        expand = self._catalog_filter is not None
        for group in sorted(groups, key=str.casefold):
            contacts = sorted(groups[group],
                              key=lambda c: c["name"].casefold())
            header = QtWidgets.QTreeWidgetItem(
                [f"{group} ({len(contacts)})"])
            header.setData(0, QtCore.Qt.ItemDataRole.UserRole, None)
            for contact in contacts:
                item = QtWidgets.QTreeWidgetItem([contact["name"]])
                item.setIcon(0, app_icon)
                item.setData(0, QtCore.Qt.ItemDataRole.UserRole,
                             contact["jid"])
                item.setToolTip(0, contact["jid"])
                header.addChild(item)
            self._tree.addTopLevelItem(header)
            if expand:
                header.setExpanded(True)
        self._tree.blockSignals(False)
        self._syncing_tree = False
        has_contacts = bool(catalog)
        self._tree.setVisible(has_contacts)
        self._empty_label.setVisible(not has_contacts)
        self._calendar.setEnabled(has_contacts)

    def _on_tree_selection_changed(self) -> None:
        if self._syncing_tree:
            return
        items = self._tree.selectedItems()
        if not items:
            return
        jid = items[0].data(0, QtCore.Qt.ItemDataRole.UserRole)
        if jid:
            self._select_jid(jid)

    def _select_jid(self, jid: str) -> None:
        contact = next((c for c in self._catalog if c["jid"] == jid), None)
        if contact is None:
            return
        self._start_task(self._select_jid_async(jid, contact["name"]))

    async def _select_jid_async(self, jid: str, name: str) -> None:
        if self._released:
            return
        # Record the target before awaiting: ``_set_contact`` (which sets
        # ``_jid``) runs further down, so a guard against ``self._jid`` below
        # would otherwise always abort the very first selection.
        previous = self._jid
        self._jid = jid
        if jid != previous and not os.path.isfile(history._path(jid)):
            await history.migrate_from_jsonl_async(jid)
        if self._released or jid != self._jid:
            return
        self._set_contact(jid, name)
        self._sync_tree_selection(jid)

    def _sync_tree_selection(self, jid: str) -> None:
        self._tree.blockSignals(True)
        self._syncing_tree = True
        found = None
        for i in range(self._tree.topLevelItemCount()):
            header = self._tree.topLevelItem(i)
            for j in range(header.childCount()):
                item = header.child(j)
                if item.data(0, QtCore.Qt.ItemDataRole.UserRole) == jid:
                    found = item
                    break
            if found:
                break
        if found is not None:
            self._tree.setCurrentItem(found)
        self._tree.blockSignals(False)
        self._syncing_tree = False

    def _set_contact(self, jid: str, name: str) -> None:
        self._jid = jid
        self._name = name
        self._btn_export.setEnabled(bool(jid))
        self._reset_server_search()
        self._update_server_button()
        self._update_media_server_buttons()
        self._reset_media_state()
        self._date = ""
        self._search.setText("")
        self._all_days = []
        self._clear_search_state()
        self._set_results_visible(False)
        if self._tabs.currentIndex() > 0:
            self._refresh_media()
        if not jid:
            self._dates = []
            self._show_empty_day("")
            return
        if history.has_history(jid):
            self._dates_task = self._start_task(self._set_contact_dates(jid))
        else:
            self._dates_task = None
            self._dates = []
            self._show_empty_day("")

    async def _set_contact_dates(self, jid: str) -> None:
        if self._released or jid != self._jid:
            return
        self._dates = await history.dates_async(jid)
        if self._released or jid != self._jid:
            return
        self._mark_calendar_dates()
        self._date = ""
        # A global-search result pins the day to open (not the newest one).
        target = self._pending_date or (self._dates[-1] if self._dates else "")
        self._pending_date = ""
        if target:
            await self._select_date_async(target)
        else:
            self._show_empty_day("")

    # ── Calendar ─────────────────────────────────────────────────

    def _mark_calendar_dates(self) -> None:
        fmt = QtGui.QTextCharFormat()
        self._calendar.setDateTextFormat(QtCore.QDate(), fmt)
        bold = QtGui.QTextCharFormat()
        font = bold.font()
        font.setBold(True)
        bold.setFont(font)
        bold.setForeground(QtGui.QBrush(QtGui.QColor(0x0d, 0x4f, 0x8b)))
        bold.setBackground(QtGui.QBrush(QtGui.QColor(0xd8, 0xe6, 0xf5)))
        for date in self._dates:
            try:
                y, m, d = (int(p) for p in date.split("-"))
            except ValueError:
                continue
            self._calendar.setDateTextFormat(
                QtCore.QDate(y, m, d), bold)

    def _on_calendar_clicked(self) -> None:
        if self._syncing_calendar:
            return
        value = self._calendar.selectedDate().toString("yyyy-MM-dd")
        if value in self._dates:
            self._select_date(value)
        else:
            # The day may have been added to SQLite by a MAM backfill after
            # this contact's dates were last read; re-check before declaring
            # it empty, then select it or show the empty notice.
            self._start_task(self._recheck_date_async(value))

    async def _recheck_date_async(self, value: str) -> None:
        if self._released:
            return
        jid = self._jid
        dates = await history.dates_async(jid)
        if self._released or jid != self._jid or value != \
                self._calendar.selectedDate().toString("yyyy-MM-dd"):
            return
        self._dates = dates
        self._mark_calendar_dates()
        if value in self._dates:
            self._select_date(value)
        else:
            self._show_empty_day(value)

    def _select_date(self, date: str) -> None:
        """Sync shim: navigation does not await the (async) day load."""
        self._start_task(self._select_date_async(date))

    async def _select_date_async(self, date: str) -> None:
        if self._released:
            return
        if date == self._date and date in self._dates:
            return
        self._date = date
        self._clear_search_state()
        if date:
            try:
                y, m, d = (int(p) for p in date.split("-"))
                # Set the calendar without re-entering _on_calendar_clicked
                # (which would re-check/reload the day and could loop).
                self._syncing_calendar = True
                try:
                    self._calendar.setSelectedDate(QtCore.QDate(y, m, d))
                finally:
                    self._syncing_calendar = False
            except ValueError:
                pass
        await self._load_date_async(date)
        if self._released or date != self._date:
            return
        self._update_nav_state()
        if not self._multi_mode():
            self._set_results_visible(False)
        if self._tabs.currentIndex() > 0:
            self._refresh_media()

    def _show_empty_day(self, value: str) -> None:
        self._date = value
        self._clear_search_state()
        self._entries = []
        self._message_blocks = []
        self._messages.clear()
        self._status.setText(tr("history_no_messages"))
        if not self._multi_mode():
            self._set_results_visible(False)
        if self._tabs.currentIndex() > 0:
            self._refresh_media()

    def _jump_day(self, delta: int = 0, first: bool = False,
                  last: bool = False) -> None:
        if not self._dates:
            return
        if first:
            idx = 0
        elif last:
            idx = len(self._dates) - 1
        else:
            idx = self._dates.index(self._date) if self._date in self._dates \
                else -1
            idx = max(0, min(len(self._dates) - 1, idx + delta))
        self._select_date(self._dates[idx])

    def _update_nav_state(self) -> None:
        has = bool(self._dates)
        idx = self._dates.index(self._date) if self._date in self._dates else -1
        self._btn_first.setEnabled(has and idx > 0)
        self._btn_prev_day.setEnabled(has and idx > 0)
        self._btn_next_day.setEnabled(has and 0 <= idx < len(self._dates) - 1)
        self._btn_last.setEnabled(has and idx < len(self._dates) - 1)

    # ── Messages ──────────────────────────────────────────────────

    async def _load_date_async(self, date: str) -> None:
        if self._released:
            return
        if not date or not self._jid:
            # No day to show: never leave the previous contact's messages on
            # screen while switching to a contact without history.
            self._entries = []
            self._message_blocks = []
            self._messages.clear()
            self._status.setText(
                tr("history_no_history") if self._jid else "")
            return
        entries = await history.load_day_async(self._jid, date)
        if self._released or date != self._date:
            return
        self._entries = entries
        self._render_messages()
        if not self._entries:
            self._status.setText(tr("history_no_messages"))
        else:
            self._status.setText(f"{self._name or self._jid} — {date}")

    def _sender_of(self, entry: dict) -> str:
        """Resolve a message's sender (own messages show as «Я»/«Me»)."""
        sender = entry.get("sender", "") or (
            tr("history_me") if entry.get("direction") == "outgoing" else "")
        if not sender.strip():
            sender = self._jid.split("@", 1)[0]
        return sender

    def _render_messages(self) -> None:
        parts = ["<html><body>"]
        for entry in self._entries:
            ts = entry.get("timestamp", "")
            date = ts[:10] if len(ts) >= 10 else ""
            time_s = _time_of(ts)
            sender = self._sender_of(entry)
            body = escape_html(entry.get("body", ""))
            body = body.replace("\r\n", "\n").replace("\r", "\n").replace(
                "\n", "<br>")
            arrow = "→" if entry.get("direction") == "outgoing" else "←"
            parts.append(
                f'<p><span style="color:#808080">{escape_html(date)}'
                f'{(" " + escape_html(time_s)) if time_s else ""}</span> '
                f'<b>{escape_html(arrow)} {escape_html(sender)}:</b> '
                f'{body}</p>')
        parts.append("</body></html>")
        self._messages.setHtml("\n".join(parts))
        scroll = self._messages.verticalScrollBar()
        cursor = QtGui.QTextCursor(self._messages.document())
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        self._messages.setTextCursor(cursor)
        self._messages.ensureCursorVisible()
        scroll.setValue(scroll.maximum())
        QtCore.QTimer.singleShot(0, self._snap_scroll_end)

        doc = self._messages.document()
        block = doc.begin()
        self._message_blocks = []
        entry_index = 0
        while block.isValid() and entry_index < len(self._entries):
            if block.text().strip():
                self._message_blocks.append(block.position())
                entry_index += 1
            block = block.next()

    # ── Media calendar ────────────────────────────────────────────

    def _current_media_kind(self) -> str:
        index = self._tabs.currentIndex() if hasattr(self, "_tabs") else 0
        return {1: "image", 2: "video", 3: "audio"}.get(index, "")

    def _on_tab_changed(self, index: int) -> None:
        if index <= 0:
            self._search.setFocus()
            return
        self._update_media_server_buttons()
        if self._media_mode["server"]:
            if self._media_server_jid != self._jid:
                self._start_server_media()
        else:
            self._refresh_media()
        kind = self._current_media_kind()
        filter_edit = self._media_filters.get(kind)
        if filter_edit is not None:
            filter_edit.setFocus()

    def _on_media_filter_changed(self, kind: str, text: str) -> None:
        view = self._media_views.get(kind)
        if view is not None:
            view.set_filter(text)

    def _on_media_mode_toggled(self, name: str, checked: bool) -> None:
        if name not in self._media_mode:
            return
        if checked and name == "server":
            self._media_mode["all_time"] = False
            self._media_mode["all_contacts"] = False
            self._media_server_jid = ""
        elif checked:
            self._media_mode["server"] = False
        self._media_mode[name] = bool(checked)
        self._sync_media_buttons()
        self._refresh_media()

    def _sync_media_buttons(self) -> None:
        server = bool(self._media_mode.get("server"))
        for buttons in self._media_buttons.values():
            for name, button in buttons.items():
                button.blockSignals(True)
                button.setChecked(bool(self._media_mode.get(name)))
                button.blockSignals(False)
            buttons["all_time"].setEnabled(not server)
            buttons["all_contacts"].setEnabled(not server)
            buttons["server"].setEnabled(bool(self._media_server_ok))

    def _update_media_server_buttons(self) -> None:
        supported = False
        if self._server_media_supported is not None and self._jid:
            try:
                supported = bool(self._server_media_supported(self._jid))
            except Exception:  # noqa: BLE001 - never break the browser
                supported = False
        elif self._server_media is not None and self._jid:
            supported = True
        self._media_server_ok = supported
        if not supported and self._media_mode.get("server"):
            self._media_mode["server"] = False
        for buttons in self._media_buttons.values():
            buttons["server"].setToolTip(
                tr("history_search_server_tip") if supported
                else tr("history_search_server_unavailable"))
        self._sync_media_buttons()

    def _reset_media_state(self) -> None:
        self._media_request_id += 1
        self._media_items = []
        self._media_local_key = None
        self._media_server_jid = ""
        self._media_server_cursor = ""
        self._media_server_complete = True
        self._media_server_loading = False
        self._media_empty_pages = 0
        self._media_auto_pages = 0
        for view in self._media_views.values():
            view.clear()
        self._update_media_context()

    def _update_media_context(self) -> None:
        if self._media_mode.get("all_time") or self._media_mode.get("server"):
            text = ""
        elif not self._date:
            text = ""
        elif (self._date == QtCore.QDate.currentDate().toString("yyyy-MM-dd")):
            text = tr("history_media_today")
        else:
            text = tr("history_media_for_day", date=self._date)
        for view in self._media_views.values():
            view.set_context(text)

    def _refresh_media(self) -> None:
        self._update_media_context()
        if self._media_mode.get("server"):
            if self._media_server_jid == self._jid:
                return
            self._start_server_media()
            return
        key = (self._jid, self._date if not self._media_mode.get("all_time")
               else "", bool(self._media_mode.get("all_time")),
               bool(self._media_mode.get("all_contacts")))
        if key == self._media_local_key:
            return
        self._media_local_key = key
        self._media_request_id += 1
        self._start_task(self._load_local_media(self._media_request_id))

    async def _load_local_media(self, request_id: int) -> None:
        if self._released:
            return
        for view in self._media_views.values():
            view.set_loading(True, tr("history_media_loading"))
        all_time = bool(self._media_mode.get("all_time"))
        all_contacts = bool(self._media_mode.get("all_contacts"))
        date = "" if all_time else self._date
        if not all_contacts and not self._jid:
            items: list[dict] = []
        elif not all_time and not date:
            items = []
        else:
            jids = ([self._jid] if not all_contacts
                    else await asyncio.to_thread(history.list_history_jids))
            names = {c["jid"]: c["name"] for c in self._catalog}
            items = []
            for jid in sorted(jids):
                if self._released or request_id != self._media_request_id:
                    return
                entries = await history.media_entries_async(jid, date)
                for entry in entries:
                    for item in media_items_from_entry(entry, jid=jid):
                        item["contact"] = names.get(jid, jid)
                        items.append(item)
        if (self._released or request_id != self._media_request_id
                or self._media_mode.get("server")):
            return
        self._media_items = items
        self._media_local_key = (
            self._jid, date, all_time, all_contacts)
        self._update_media_context()
        for view in self._media_views.values():
            view.set_loading(False)
            view.set_items(items)

    def _start_server_media(self) -> None:
        if self._server_media is None or not self._jid:
            for view in self._media_views.values():
                view.clear()
                view.set_status(tr("history_search_server_unavailable"))
            return
        self._media_server_jid = self._jid
        self._media_server_cursor = ""
        self._media_server_complete = False
        self._media_server_loading = False
        self._media_empty_pages = 0
        self._media_items = []
        self._media_local_key = None
        self._update_media_context()
        for view in self._media_views.values():
            view.clear()
            view.set_loading(True, tr("history_search_server_running"))
        self._start_task(self._load_server_media_page())

    async def _load_server_media_page(self) -> None:
        if (self._released or self._media_server_loading
                or not self._media_mode.get("server")
                or self._server_media is None
                or self._media_server_jid != self._jid):
            return
        self._media_server_loading = True
        if not self._media_items:
            for view in self._media_views.values():
                view.set_loading(True, tr("history_search_server_running"))
        jid = self._jid
        before = self._media_server_cursor
        try:
            result = await self._server_media(jid, before)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Server media search failed: %s", exc)
            result = None
        if (self._released or not self._media_mode.get("server")
                or self._media_server_jid != self._jid):
            self._media_server_loading = False
            return
        self._media_server_loading = False
        if result is None:
            for view in self._media_views.values():
                view.set_loading(False, tr("history_search_server_error"))
            return
        rows, complete, cursor = result
        items = []
        for row in rows or []:
            items.extend(media_items_from_entry(row, jid=jid))
        known = {(item.get("url", ""), item.get("timestamp", ""))
                 for item in self._media_items}
        fresh = [item for item in items
                 if (item.get("url", ""), item.get("timestamp", ""))
                 not in known]
        self._media_items.extend(fresh)
        self._media_server_cursor = str(cursor or "")
        self._media_server_complete = bool(complete)
        for view in self._media_views.values():
            if fresh:
                view.append_items(fresh)
            view.set_loading(False)
        if not fresh and not self._media_server_complete \
                and self._media_empty_pages < 20:
            self._media_empty_pages += 1
            QtCore.QTimer.singleShot(0, self._start_task_media_page)
            return
        self._media_empty_pages = 0 if fresh else self._media_empty_pages
        if self._media_server_complete and not self._media_items:
            for view in self._media_views.values():
                view.set_status(tr("history_media_empty"))
        if not self._media_server_complete:
            QtCore.QTimer.singleShot(50, self._continue_server_if_short)

    def _continue_server_if_short(self) -> None:
        """Load more pages while the active media grid has no scrollbar.

        A media-bearing archive page can hold one file among 100 messages;
        with a single card the grid cannot scroll, so the normal scroll
        trigger never asks for the next (older) page.
        """
        if (self._released or not self._media_mode.get("server")
                or self._media_server_loading or self._media_server_complete):
            return
        kind = self._current_media_kind()
        view = self._media_views.get(kind) if kind else None
        if view is None or view.can_scroll():
            return
        if self._media_auto_pages >= 20:
            return
        self._media_auto_pages += 1
        self._start_task(self._load_server_media_page())

    def _start_task_media_page(self) -> None:
        self._start_task(self._load_server_media_page())

    def _on_media_load_more(self, _kind: str) -> None:
        if (self._media_mode.get("server")
                and not self._media_server_complete):
            self._start_task(self._load_server_media_page())

    def media_error(self, _url: str = "") -> None:
        kind = self._current_media_kind()
        view = self._media_views.get(kind)
        if view is not None:
            view.set_status(tr("history_media_missing"))

    # ── Export ────────────────────────────────────────────────────

    def _on_export(self) -> None:
        if not self._jid:
            return
        default = os.path.join(
            os.path.expanduser("~"), f"{self._jid.split('@', 1)[0]}.txt")
        path, _selected = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("history_export_dialog"), default,
            "Text files (*.txt);;All files (*)")
        if not path:
            return
        self._start_task(self._export_async(path))

    async def _export_async(self, path: str) -> None:
        jid = self._jid

        def _collect() -> list[str]:
            lines: list[str] = []
            for date in history.dates(jid):
                for entry in history.load_day(jid, date):
                    body = (entry.get("body", "") or "").replace(
                        "\r\n", "\n").replace("\r", "\n")
                    body = body.replace("\n", " ")
                    lines.append(
                        f"[{_stamp(entry.get('timestamp', ''))}] "
                        f"{self._sender_of(entry)}: {body}")
            return lines

        def _write(lines: list[str]) -> None:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
                handle.write("\n")

        try:
            lines = await asyncio.to_thread(_collect)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("History export read failed for %s: %s", jid, exc)
            self._status.setText(tr("history_export_error"))
            return
        if not lines:
            self._status.setText(tr("history_export_empty"))
            return
        try:
            await asyncio.to_thread(_write, lines)
        except Exception as exc:
            logger.warning("History export write failed for %s: %s", path, exc)
            self._status.setText(tr("history_export_error"))
            return
        self._status.setText(
            tr("history_export_done", n=len(lines), path=path))

    # ── Search ────────────────────────────────────────────────────

    def _clear_search_state(self) -> None:
        self._query = ""
        self._matches = []
        self._match_index = -1
        self._btn_prev_match.setEnabled(False)
        self._btn_next_match.setEnabled(False)
        self._messages.setExtraSelections([])

    def _on_search_run(self) -> None:
        self._query = self._search.text().strip()
        if not self._query:
            self._clear_search_state()
            return
        if self._btn_server.isChecked():
            self._run_server_search()
            return
        if self._btn_all_contacts.isChecked():
            self._run_global_search()
            return
        if not self._jid:
            self._clear_search_state()
            return
        if self._btn_all_time.isChecked():
            self._run_all_time_search()
        else:
            self._run_day_search()

    def _run_global_search(self) -> None:
        self._start_task(self._run_global_search_async())

    async def _run_global_search_async(self) -> None:
        """Search every contact's history for *query* (all-contacts mode)."""
        if self._released:
            return
        query = self._query
        names = {c["jid"]: c["name"] for c in self._catalog}

        def _collect() -> dict[str, list[tuple[str, int]]]:
            found: dict[str, list[tuple[str, int]]] = {}
            for jid in history.list_history_jids():
                result = history.search_dates(jid, query)
                if result:
                    found[jid] = result
            return found

        try:
            found = await asyncio.to_thread(_collect)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Global history search failed: %s", exc)
            found = {}
        if self._released or query != self._search.text().strip():
            return
        self._global_days = found
        # The left tree keeps only the contacts that matched.
        self._catalog_filter = set(found)
        self._rebuild_tree()
        rows = [(date, jid, count)
                for jid, days in found.items() for date, count in days]
        rows.sort(key=lambda row: row[0], reverse=True)
        self._results.clear()
        for date, jid, count in rows:
            item = QtWidgets.QListWidgetItem(
                tr("history_global_result",
                   name=names.get(jid, jid), date=date, count=count))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, (jid, date))
            self._results.addItem(item)
        self._update_match_buttons()
        if not rows:
            self._set_results_visible(False)
            self._status.setText(tr("history_no_results"))
        else:
            self._set_results_visible(True)
        self._search.setFocus()

    def _run_day_search(self) -> None:
        self._start_task(self._run_day_search_async())

    async def _run_day_search_async(self) -> None:
        if self._released:
            return
        if self._date:
            await self._load_date_async(self._date)
            if self._released:
                return
        self._find_day_matches()
        self._set_results_visible(False)
        self._match_index = 0 if self._matches else -1
        self._update_match_buttons()
        if self._matches:
            self._jump_to_match(0)
        else:
            self._status.setText(tr("history_no_results"))
        self._search.setFocus()

    def _run_all_time_search(self) -> None:
        self._start_task(self._run_all_time_search_async())

    async def _run_all_time_search_async(self) -> None:
        if self._released:
            return
        results = await history.search_dates_async(self._jid, self._query)
        if self._released or self._query != self._search.text().strip():
            return
        ordered = list(reversed(results))
        self._all_days = [date for date, _ in ordered]
        self._results.clear()
        for date, count in ordered:
            item = QtWidgets.QListWidgetItem(f"{date} · {count}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, date)
            self._results.addItem(item)
        self._update_match_buttons()
        if not self._all_days:
            self._set_results_visible(False)
            self._status.setText(tr("history_no_results"))
            self._search.setFocus()
            return
        self._set_results_visible(True)
        self._results.setCurrentRow(0)
        self._go_to_day(0)
        self._search.setFocus()

    def _on_result_picked(self, item: QtWidgets.QListWidgetItem) -> None:
        data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple):
            jid, date = data
            self._start_task(self._open_global_result(jid, date))
            return
        date = data
        if date in self._all_days:
            self._go_to_day(self._all_days.index(date))
        if self._btn_all_time.isChecked() or self._btn_server.isChecked():
            self._set_results_visible(True)
        self._search.setFocus()

    async def _open_global_result(self, jid: str, date: str) -> None:
        """Open a matched contact's day from a global-search result."""
        query = self._search.text().strip()
        contact = next((c for c in self._catalog if c["jid"] == jid), None)
        name = contact["name"] if contact else jid
        # Pin the day so the contact's date-load opens it (not the newest one):
        # awaiting that task makes the selection deterministic.
        self._pending_date = date
        await self._select_jid_async(jid, name)
        task = self._dates_task
        if task is not None:
            try:
                await task
            except Exception:  # noqa: BLE001 - defensive
                pass
        if self._released or self._jid != jid:
            self._pending_date = ""
            return
        if self._date != date:
            await self._select_date_async(date)
        if self._released or self._date != date:
            return
        # Selecting a contact/day clears the search box; restore the query.
        self._search.setText(query)
        self._query = query
        self._find_day_matches()
        self._match_index = 0 if self._matches else -1
        self._update_match_buttons()
        if self._matches:
            self._jump_to_match(0)
        self._set_results_visible(True)
        self._search.setFocus()

    def _multi_mode(self) -> bool:
        """True when the results list drives the navigation."""
        return (self._btn_all_time.isChecked()
                or self._btn_all_contacts.isChecked()
                or self._btn_server.isChecked())

    def _on_match_prev(self) -> None:
        if (self._btn_all_contacts.isChecked()
                or self._btn_server.isChecked()):
            self._step_results(-1)
            return
        if self._btn_all_time.isChecked():
            self._step_all_time(-1)
            return
        if not self._matches:
            return
        self._match_index = (self._match_index - 1) % len(self._matches)
        self._jump_to_match(self._match_index)

    def _on_match_next(self) -> None:
        if (self._btn_all_contacts.isChecked()
                or self._btn_server.isChecked()):
            self._step_results(1)
            return
        if self._btn_all_time.isChecked():
            self._step_all_time(1)
            return
        if not self._matches:
            return
        self._match_index = (self._match_index + 1) % len(self._matches)
        self._jump_to_match(self._match_index)

    def _step_results(self, delta: int) -> None:
        """Step the global-search result list and open the selected row."""
        count = self._results.count()
        if count == 0:
            return
        row = (self._results.currentRow() + delta) % count
        self._results.setCurrentRow(row)
        self._on_result_picked(self._results.item(row))

    def _step_all_time(self, delta: int) -> None:
        if not self._all_days:
            return
        pos = self._all_days.index(self._date) \
            if self._date in self._all_days else 0
        n = len(self._all_days)
        if delta > 0:
            if self._match_index + 1 < len(self._matches):
                self._match_index += 1
                self._jump_to_match(self._match_index)
            else:
                self._go_to_day((pos + 1) % n)
        else:
            if self._match_index > 0:
                self._match_index -= 1
                self._jump_to_match(self._match_index)
            else:
                self._go_to_day((pos - 1) % n, last_match=True)
        self._search.setFocus()

    def _go_to_day(self, pos: int, last_match: bool = False) -> None:
        """Sync shim — day loads are async, so defer the match step."""
        if not (0 <= pos < len(self._all_days)):
            return
        if not self._query:
            return
        self._start_task(self._go_to_day_async(
            self._all_days[pos], self._query, pos, last_match))

    async def _go_to_day_async(self, day: str, query: str, pos: int,
                               last_match: bool) -> None:
        if self._released:
            return
        if day != self._date:
            await self._select_date_async(day)
            if self._released or day != self._date:
                return
        self._query = query
        self._find_day_matches()
        self._match_index = len(self._matches) - 1 if last_match else 0
        self._update_match_buttons()
        self._results.setCurrentRow(pos)
        if not self._multi_mode():
            self._set_results_visible(False)
        if self._matches:
            self._jump_to_match(self._match_index)

    def _update_match_buttons(self) -> None:
        if self._multi_mode():
            enabled = self._results.count() > 0
        else:
            enabled = len(self._matches) >= 2
        self._btn_prev_match.setEnabled(enabled)
        self._btn_next_match.setEnabled(enabled)

    def _find_day_matches(self) -> None:
        casefold = self._query.casefold()
        self._matches = [i for i, entry in enumerate(self._entries)
                         if casefold in entry.get("body", "").casefold()]

    def _snap_scroll_end(self) -> None:
        if self._matches:
            return
        scroll = self._messages.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    def _all_match_selections(self) -> list:
        """Yellow backgrounds for every occurrence of the search query."""
        if not self._query:
            return []
        doc = self._messages.document()
        selections = []
        cursor = QtGui.QTextCursor(doc)
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.Start)
        while True:
            found = doc.find(self._query, cursor)
            if found.isNull():
                break
            selection = QtWidgets.QTextEdit.ExtraSelection()
            selection.cursor = found
            selection.format.setBackground(QtGui.QColor("#fff59d"))
            selections.append(selection)
            end = found.selectionEnd()
            if end <= cursor.position():
                break
            cursor.setPosition(end)
        return selections

    def _jump_to_match(self, index: int) -> None:
        if not self._matches or not (0 <= index < len(self._matches)):
            return
        entry_index = self._matches[index]
        if entry_index >= len(self._message_blocks):
            return
        doc = self._messages.document()
        cursor = QtGui.QTextCursor(doc)
        cursor.setPosition(self._message_blocks[entry_index])
        found = doc.find(self._query, cursor)
        # Highlight every occurrence, not just the active entry.  The active
        # one keeps the normal text-cursor selection (blue), as before.
        self._messages.setExtraSelections(self._all_match_selections())
        if found.isNull():
            anchor = QtGui.QTextCursor(doc)
            anchor.setPosition(self._message_blocks[entry_index])
            self._messages.setTextCursor(anchor)
            self._messages.ensureCursorVisible()
            return
        self._messages.setTextCursor(found)
        self._messages.ensureCursorVisible()
        # ``setHtml`` defers the layout, so a match near the end of the day
        # cannot be scrolled to until the next event-loop turn (when the scroll
        # range is final) — re-reveal it then.
        QtCore.QTimer.singleShot(0, lambda c=found: self._reveal_cursor(c))

    def _reveal_cursor(self, cursor) -> None:
        try:
            self._messages.setTextCursor(cursor)
            self._messages.ensureCursorVisible()
        except RuntimeError:  # pragma: no cover - the widget was destroyed
            pass

    def _reset_server_search(self) -> None:
        self._server_jid = ""
        self._server_query = ""
        self._server_cursor = ""
        self._server_complete = True
        self._server_rows = []
        self._server_days = {}
        self._btn_server_more.setVisible(False)

    def _update_server_button(self) -> None:
        supported = False
        if (self._server_supported is not None and self._jid):
            try:
                supported = bool(self._server_supported(self._jid))
            except Exception:  # noqa: BLE001 - never break the browser
                supported = False
        self._btn_server.setEnabled(supported)
        if not supported and self._btn_server.isChecked():
            self._btn_server.setChecked(False)
        self._btn_server.setToolTip(
            tr("history_search_server_tip") if supported
            else tr("history_search_server_unavailable"))

    def _on_server_toggled(self, checked: bool) -> None:
        if checked:
            self._btn_all_contacts.setChecked(False)
            self._btn_all_contacts.setEnabled(False)
            self._btn_all_time.setChecked(False)
            self._btn_all_time.setEnabled(False)
        else:
            self._btn_all_contacts.setEnabled(True)
            self._btn_all_time.setEnabled(True)
            self._reset_server_search()
            self._clear_search_state()
            self._all_days = []
            self._set_results_visible(False)

    def _run_server_search(self, more: bool = False) -> None:
        self._start_task(self._run_server_search_async(more))

    async def _run_server_search_async(self, more: bool = False) -> None:
        if self._released or not self._jid or self._server_search is None:
            return
        query = self._search.text().strip()
        if not query:
            self._clear_search_state()
            return
        if not more:
            self._reset_server_search()
            self._server_jid = self._jid
            self._server_query = query
        elif self._server_jid != self._jid or self._server_query != query:
            return
        self._status.setText(tr("history_search_server_running"))
        after = self._server_cursor if more else ""
        try:
            result = await self._server_search(
                self._jid, query, after)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Server history search failed: %s", exc)
            result = None
        if self._released or self._jid != self._server_jid:
            return
        if result is None:
            self._status.setText(tr("history_search_server_error"))
            return
        rows, complete, cursor = result
        rows = list(rows or [])
        if more:
            known = {str(row.get("archive_id") or row.get("stanza_id") or "")
                     for row in self._server_rows}
            for row in rows:
                ref = str(row.get("archive_id") or row.get("stanza_id") or "")
                if not ref or ref not in known:
                    self._server_rows.append(row)
                    if ref:
                        known.add(ref)
        else:
            self._server_rows = rows
        self._server_days = {}
        for row in self._server_rows:
            day = str(row.get("timestamp") or "")[:10]
            if day:
                self._server_days[day] = self._server_days.get(day, 0) + 1
        self._server_cursor = cursor or ""
        self._server_complete = bool(complete)
        self._query = query
        self._all_days = sorted(self._server_days, reverse=True)
        self._dates = await history.dates_async(self._jid)
        if self._released or self._jid != self._server_jid:
            return
        self._mark_calendar_dates()
        self._results.clear()
        for day in self._all_days:
            item = QtWidgets.QListWidgetItem(
                f"{day} · {self._server_days[day]}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, day)
            self._results.addItem(item)
        self._set_results_visible(bool(self._all_days))
        self._btn_server_more.setVisible(
            bool(self._all_days) and not self._server_complete)
        if self._all_days:
            self._status.setText(tr(
                "history_search_server_results", n=len(self._server_rows)))
        else:
            self._status.setText(tr("history_search_server_no_results"))
        self._update_match_buttons()
        if self._all_days:
            self._results.setCurrentRow(0)
            self._go_to_day(0)
        self._search.setFocus()

    def _on_mode_toggled(self, checked: bool) -> None:
        self._clear_search_state()
        self._all_days = []
        self._set_results_visible(False)

    def _on_all_contacts_toggled(self, checked: bool) -> None:
        """Switch between the per-contact and the all-contacts search."""
        if checked and self._btn_server.isChecked():
            self._btn_server.setChecked(False)
        self._clear_search_state()
        self._global_days = {}
        self._all_days = []
        self._set_results_visible(False)
        self._catalog_filter = None
        self._rebuild_tree()