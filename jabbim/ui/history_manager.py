"""History manager dialog.

Left pane: roster-style contact list grouped by roster groups (with per-group
contact counts) and a calendar whose bold dates mark days that have messages.
Right pane: a search row, an all-time search results list, a message browser
and day-navigation buttons.
"""
from __future__ import annotations

import datetime
import os

from PyQt6 import QtCore, QtGui, QtWidgets

from jabbim.core import history
from jabbim.include.constants import ACTIONS_DIR_16, CATEGORIES_DIR_16, \
    STATUS_DIR_32
from jabbim.include.utils import escape_html
from jabbim.i18n import tr


def _utc_today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _time_of(ts: str) -> str:
    """Return ``HH:MM:SS`` from a stored timestamp string."""
    if not ts:
        return ""
    if len(ts) >= 19 and ts[10] == "T":
        return ts[11:19]
    return ts


def _icon(filename: str) -> QtGui.QIcon:
    for directory in (ACTIONS_DIR_16, CATEGORIES_DIR_16, STATUS_DIR_32):
        pix = QtGui.QPixmap(os.path.join(directory, filename))
        if not pix.isNull():
            return QtGui.QIcon(pix)
    return QtGui.QIcon()


class HistoryManagerDialog(QtWidgets.QDialog):
    """Browser over locally stored per-contact chat history."""

    def __init__(self, catalog_provider, initial_jid: str = "",
                 parent=None):
        super().__init__(parent)
        self._catalog_provider = catalog_provider
        self._catalog: list[dict] = []
        self._jid: str = ""
        self._name: str = ""
        self._dates: list[str] = []
        self._entries: list[dict] = []
        self._date: str = ""
        self._query: str = ""
        self._matches: list[int] = []
        self._match_index = -1
        self._message_blocks: list[int] = []

        self.setWindowTitle(tr("history_manager"))
        self.resize(920, 620)
        self._build_ui()
        self._refresh()
        if initial_jid:
            self._select_jid(initial_jid)

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

        # ── Right pane: search + messages + navigation ────────────
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

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
        self._btn_all_time = QtWidgets.QPushButton(tr("history_all_time"))
        self._btn_all_time.setCheckable(True)
        self._btn_all_time.toggled.connect(self._on_mode_toggled)
        search_row.addWidget(self._btn_all_time)
        right_layout.addLayout(search_row)

        self._results = QtWidgets.QListWidget()
        self._results.setMaximumHeight(140)
        self._results.itemActivated.connect(self._on_result_picked)
        self._results.hide()
        right_layout.addWidget(self._results)

        self._status = QtWidgets.QLabel()
        self._status.setWordWrap(True)
        right_layout.addWidget(self._status)

        self._messages = QtWidgets.QTextBrowser()
        self._messages.setOpenExternalLinks(True)
        right_layout.addWidget(self._messages, 1)

        nav_row = QtWidgets.QHBoxLayout()
        self._btn_refresh = QtWidgets.QToolButton()
        self._btn_refresh.setIcon(_icon("reload.png"))
        self._btn_refresh.setToolTip(tr("history_refresh"))
        self._btn_refresh.clicked.connect(self._refresh)
        nav_row.addWidget(self._btn_refresh)
        nav_row.addStretch(1)
        self._btn_first = QtWidgets.QPushButton(tr("history_first_day"))
        self._btn_first.clicked.connect(lambda: self._jump_day(first=True))
        self._btn_first.setEnabled(False)
        nav_row.addWidget(self._btn_first)
        self._btn_prev_day = QtWidgets.QPushButton(tr("history_prev_day"))
        self._btn_prev_day.clicked.connect(lambda: self._jump_day(-1))
        self._btn_prev_day.setEnabled(False)
        nav_row.addWidget(self._btn_prev_day)
        self._btn_next_day = QtWidgets.QPushButton(tr("history_next_day"))
        self._btn_next_day.clicked.connect(lambda: self._jump_day(1))
        self._btn_next_day.setEnabled(False)
        nav_row.addWidget(self._btn_next_day)
        self._btn_last = QtWidgets.QPushButton(tr("history_last_day"))
        self._btn_last.clicked.connect(lambda: self._jump_day(last=True))
        self._btn_last.setEnabled(False)
        nav_row.addWidget(self._btn_last)
        nav_row.addStretch(1)
        close_btn = QtWidgets.QPushButton(tr("dialog_close"))
        close_btn.clicked.connect(self.accept)
        nav_row.addWidget(close_btn)
        right_layout.addLayout(nav_row)

        splitter.addWidget(right)
        splitter.setSizes([280, 640])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    # ── Catalog / contacts ───────────────────────────────────────

    def open_for(self, jid: str = "") -> None:
        """Refresh the catalog and show *jid* (or keep the current one)."""
        self._refresh()
        if jid:
            self._select_jid(jid)

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
        self._tree.clear()
        groups: dict[str, list[dict]] = {}
        for contact in self._catalog:
            for group in contact["groups"]:
                groups.setdefault(group, []).append(contact)
        for group in sorted(groups, key=str.casefold):
            contacts = sorted(groups[group],
                              key=lambda c: c["name"].casefold())
            header = QtWidgets.QTreeWidgetItem(
                [f"{group} ({len(contacts)})"])
            header.setData(0, QtCore.Qt.ItemDataRole.UserRole, None)
            header.setExpanded(True)
            for contact in contacts:
                item = QtWidgets.QTreeWidgetItem([contact["name"]])
                item.setData(0, QtCore.Qt.ItemDataRole.UserRole,
                             contact["jid"])
                item.setToolTip(0, contact["jid"])
                header.addChild(item)
            self._tree.addTopLevelItem(header)
        self._tree.blockSignals(False)
        has_contacts = bool(self._catalog)
        self._tree.setVisible(has_contacts)
        self._empty_label.setVisible(not has_contacts)
        self._calendar.setEnabled(has_contacts)

    def _on_tree_selection_changed(self) -> None:
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
        if jid != self._jid and not os.path.isfile(history._path(jid)):
            history.migrate_from_jsonl(jid)
        self._set_contact(jid, contact["name"])
        self._sync_tree_selection(jid)

    def _sync_tree_selection(self, jid: str) -> None:
        self._tree.blockSignals(True)
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

    def _set_contact(self, jid: str, name: str) -> None:
        self._jid = jid
        self._name = name
        self._clear_search_state()
        self._results.hide()
        if not jid:
            self._dates = []
            self._select_date("")
            return
        if history.has_history(jid):
            self._dates = history.dates(jid)
        else:
            self._dates = []
        self._mark_calendar_dates()
        if self._dates:
            today = _utc_today()
            date = today if today in self._dates else self._dates[-1]
            self._select_date(date)
        else:
            self._select_date("")

    # ── Calendar ─────────────────────────────────────────────────

    def _mark_calendar_dates(self) -> None:
        fmt = QtGui.QTextCharFormat()
        self._calendar.setDateTextFormat(QtCore.QDate(), fmt)
        bold = QtGui.QTextCharFormat()
        font = bold.font()
        font.setBold(True)
        bold.setFont(font)
        bold.setForeground(QtGui.QBrush(QtGui.QColor(0x1a, 0x5f, 0x9e)))
        for date in self._dates:
            try:
                y, m, d = (int(p) for p in date.split("-"))
            except ValueError:
                continue
            self._calendar.setDateTextFormat(
                QtCore.QDate(y, m, d), bold)

    def _on_calendar_clicked(self) -> None:
        value = self._calendar.selectedDate().toString("yyyy-MM-dd")
        if value in self._dates:
            self._select_date(value)
        else:
            self._show_empty_day(value)

    def _select_date(self, date: str) -> None:
        if date == self._date and date in self._dates:
            return
        self._date = date
        self._clear_search_state()
        if date:
            try:
                y, m, d = (int(p) for p in date.split("-"))
                self._calendar.setSelectedDate(QtCore.QDate(y, m, d))
            except ValueError:
                pass
        self._load_date(date)
        self._update_nav_state()
        if not self._btn_all_time.isChecked():
            self._results.hide()

    def _show_empty_day(self, value: str) -> None:
        self._date = value
        self._clear_search_state()
        self._entries = []
        self._message_blocks = []
        self._messages.clear()
        self._status.setText(tr("history_no_messages"))
        if not self._btn_all_time.isChecked():
            self._results.hide()

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

    def _load_date(self, date: str) -> None:
        self._entries = []
        self._message_blocks = []
        if not date or not self._jid:
            self._messages.clear()
            self._status.setText(
                tr("history_no_history") if self._jid else "")
            return
        self._entries = history.load_day(self._jid, date)
        self._render_messages()
        if not self._entries:
            self._status.setText(tr("history_no_messages"))
        else:
            self._status.setText(f"{self._name or self._jid} — {date}")

    def _render_messages(self) -> None:
        parts = ["<html><body>"]
        for entry in self._entries:
            ts = entry.get("timestamp", "")
            date = ts[:10] if len(ts) >= 10 else ""
            time_s = _time_of(ts)
            sender = entry.get("sender", "") or (
                "Me" if entry.get("direction") == "outgoing" else "")
            if not sender.strip():
                sender = self._jid.split("@", 1)[0]
            body = escape_html(entry.get("body", ""))
            arrow = "→" if entry.get("direction") == "outgoing" else "←"
            parts.append(
                f'<p><span style="color:#808080">{escape_html(date)}'
                f'{(" " + escape_html(time_s)) if time_s else ""}</span> '
                f'<b>{escape_html(arrow)} {escape_html(sender)}:</b> '
                f'{body}</p>')
        parts.append("</body></html>")
        self._messages.setHtml("\n".join(parts))

        doc = self._messages.document()
        block = doc.begin()
        self._message_blocks = []
        entry_index = 0
        while block.isValid() and entry_index < len(self._entries):
            if block.text().strip():
                self._message_blocks.append(block.position())
                entry_index += 1
            block = block.next()

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
        if not self._query or not self._jid:
            self._clear_search_state()
            return
        if self._btn_all_time.isChecked():
            self._run_all_time_search()
        else:
            self._run_day_search()

    def _run_day_search(self) -> None:
        self._find_day_matches()
        self._results.hide()
        self._match_index = 0 if self._matches else -1
        self._update_match_buttons()
        if self._matches:
            self._jump_to_match(0)
        else:
            self._status.setText(tr("history_no_results"))

    def _run_all_time_search(self) -> None:
        results = history.search_dates(self._jid, self._query)
        self._results.clear()
        for date, count in results:
            item = QtWidgets.QListWidgetItem(f"{date} · {count}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, date)
            self._results.addItem(item)
        self._update_match_buttons()
        if results:
            self._results.show()
            self._results.setCurrentRow(0)
            first = results[0][0]
            if first in self._dates and first != self._date:
                self._select_date(first)
                self._jump_to_first_match()
            elif first == self._date:
                self._jump_to_first_match()
        else:
            self._results.hide()
            self._status.setText(tr("history_no_results"))

    def _on_result_picked(self, item: QtWidgets.QListWidgetItem) -> None:
        date = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if date in self._dates:
            if date != self._date:
                self._select_date(date)
            self._jump_to_first_match()
            self._results.show()

    def _on_match_prev(self) -> None:
        if self._btn_all_time.isChecked():
            self._step_results(-1)
            return
        if not self._matches:
            return
        self._match_index = (self._match_index - 1) % len(self._matches)
        self._jump_to_match(self._match_index)

    def _on_match_next(self) -> None:
        if self._btn_all_time.isChecked():
            self._step_results(1)
            return
        if not self._matches:
            return
        self._match_index = (self._match_index + 1) % len(self._matches)
        self._jump_to_match(self._match_index)

    def _step_results(self, delta: int) -> None:
        if self._results.count() == 0:
            return
        row = (self._results.currentRow() + delta) % self._results.count()
        self._results.setCurrentRow(row)
        item = self._results.item(row)
        date = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if date in self._dates:
            if date != self._date:
                self._select_date(date)
            self._jump_to_first_match()
            self._results.show()

    def _update_match_buttons(self) -> None:
        if self._btn_all_time.isChecked():
            enabled = self._results.count() > 0
        else:
            enabled = len(self._matches) >= 2
        self._btn_prev_match.setEnabled(enabled)
        self._btn_next_match.setEnabled(enabled)

    def _find_day_matches(self) -> None:
        casefold = self._query.casefold()
        self._matches = [i for i, entry in enumerate(self._entries)
                         if casefold in entry.get("body", "").casefold()]

    def _jump_to_first_match(self) -> None:
        self._find_day_matches()
        self._match_index = 0 if self._matches else -1
        self._update_match_buttons()
        if self._matches:
            self._jump_to_match(0)

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
        if found.isNull():
            anchor = QtGui.QTextCursor(doc)
            anchor.setPosition(self._message_blocks[entry_index])
            self._messages.setTextCursor(anchor)
            self._messages.ensureCursorVisible()
            self._messages.setExtraSelections([])
            return
        selection = QtWidgets.QTextEdit.ExtraSelection()
        selection.cursor = found
        selection.format.setBackground(QtGui.QColor("#fff59d"))
        self._messages.setExtraSelections([selection])
        self._messages.setTextCursor(found)
        self._messages.ensureCursorVisible()

    def _on_mode_toggled(self, checked: bool) -> None:
        self._clear_search_state()
        self._results.hide()