"""Notes tab (Notes plugin).

Reads/writes tagged text notes from the server's XEP-0049 private storage.
The tab mirrors the bookmarks tab: a search box, a tag filter, the note titles
and a bottom toolbar (Open / New / Edit / Delete).  Notes are fetched anew
every time the tab is shown (`reload()`), and every save re-sends the whole set
in one IQ and rebuilds the list.
"""
from __future__ import annotations

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon
from stanza_im.ui.notes_dialog import NoteDialog

logger = logging.getLogger(__name__)

_ALL_TAGS = "__all__"


def _split_tags(value: str) -> list[str]:
    return [tag.strip() for tag in str(value or "").split(",") if tag.strip()]


class NotesWidget(QtWidgets.QWidget):
    """Server-backed note list with a tag filter."""

    def __init__(self, get_client, run_task, parent=None):
        super().__init__(parent)
        self._get_client = get_client
        self._run_task = run_task
        self._notes: list[dict] = []
        self._loading = False
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText(tr("notes_search_placeholder"))
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        self._tag_filter = QtWidgets.QComboBox()
        self._tag_filter.currentIndexChanged.connect(self._apply_filter)
        layout.addWidget(self._tag_filter)

        self._list = QtWidgets.QListWidget()
        self._list.itemDoubleClicked.connect(self._on_activated)
        self._list.itemSelectionChanged.connect(self._update_actions)
        layout.addWidget(self._list, stretch=1)

        bar = QtWidgets.QWidget()
        bar.setFixedHeight(24)
        actions = QtWidgets.QHBoxLayout(bar)
        actions.setContentsMargins(0, 0, 0, 0)
        self._open_btn = self._button("ok.png", tr("notes_open"),
                                      self._on_open_clicked)
        self._new_btn = self._button("about.png", tr("notes_new"),
                                     self._on_new_clicked)
        self._edit_btn = self._button("edit.png", tr("notes_edit"),
                                      self._on_edit_clicked)
        self._del_btn = self._button("process-stop.png", tr("notes_remove"),
                                     self._on_delete_clicked)
        for button in (self._open_btn, self._new_btn, self._edit_btn,
                       self._del_btn):
            actions.addWidget(button, stretch=1)
        layout.addWidget(bar)
        self._update_actions()

    @staticmethod
    def _button(icon_name: str, tooltip: str, slot) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setIcon(QtGui.QIcon(find_icon(icon_name)))
        button.setIconSize(QtCore.QSize(16, 16))
        button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                             QtWidgets.QSizePolicy.Policy.Fixed)
        button.setFixedHeight(24)
        button.setMinimumWidth(32)
        button.clicked.connect(slot)
        return button

    # ── Server I/O ────────────────────────────────────────────────

    def reload(self) -> None:
        """Fetch the notes from the server (called when the tab is shown)."""
        client = self._get_client()
        if client is None:
            self._notes = []
            self._rebuild()
            self._show_status(tr("notes_offline"))
            return
        if self._loading:
            return
        self._loading = True
        self._show_status(tr("notes_loading"))
        self._run_task(self._load_async())

    async def _load_async(self) -> None:
        client = self._get_client()
        try:
            notes = await client.get_notes()
        except Exception:  # noqa: BLE001
            logger.debug("Could not fetch notes", exc_info=True)
            notes = None
        self._loading = False
        if notes is None:
            self._notes = []
            self._rebuild()
            self._show_status(tr("notes_no_private_storage"))
            return
        self._notes = notes
        self._rebuild()
        self._show_status("")

    def _save(self) -> None:
        """Persist the whole note set on the server."""
        client = self._get_client()
        if client is None:
            return
        self._run_task(self._save_async())

    async def _save_async(self) -> None:
        client = self._get_client()
        try:
            await client.set_notes(self._notes)
        except Exception:  # noqa: BLE001
            logger.debug("Could not store notes", exc_info=True)
            self._show_status(tr("notes_save_failed"))
            return
        self._rebuild()
        self._show_status("")

    # ── List / filter ─────────────────────────────────────────────

    def _rebuild(self) -> None:
        icon = QtGui.QIcon(find_icon("draw-brush.png"))
        self._list.clear()
        for note in self._notes:
            item = QtWidgets.QListWidgetItem(
                icon, note.get("title") or tr("notes_untitled"))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, dict(note))
            item.setToolTip(", ".join(_split_tags(note.get("tags", ""))))
            self._list.addItem(item)
        self._rebuild_tags()
        self._apply_filter()
        self._update_actions()

    def _rebuild_tags(self) -> None:
        current = self._tag_filter.currentData()
        self._tag_filter.blockSignals(True)
        self._tag_filter.clear()
        self._tag_filter.addItem(tr("notes_all_tags"), _ALL_TAGS)
        tags = sorted({tag for note in self._notes
                       for tag in _split_tags(note.get("tags", ""))},
                      key=str.casefold)
        for tag in tags:
            self._tag_filter.addItem(tag, tag)
        index = self._tag_filter.findData(current)
        self._tag_filter.setCurrentIndex(index if index >= 0 else 0)
        self._tag_filter.blockSignals(False)

    def _apply_filter(self) -> None:
        needle = self._search.text().strip().casefold()
        tag = self._tag_filter.currentData()
        for i in range(self._list.count()):
            item = self._list.item(i)
            note = item.data(QtCore.Qt.ItemDataRole.UserRole) or {}
            title = str(note.get("title") or "").casefold()
            text = str(note.get("text") or "").casefold()
            tags = _split_tags(note.get("tags", ""))
            ok = needle in f"{title} {text}" if needle else True
            if ok and tag and tag != _ALL_TAGS:
                ok = tag in tags
            item.setHidden(not ok)

    def _update_actions(self) -> None:
        has = self._selected_note() is not None
        for button in (self._open_btn, self._edit_btn, self._del_btn):
            button.setEnabled(has)

    def _selected_note(self) -> dict | None:
        items = self._list.selectedItems()
        if not items:
            return None
        return items[0].data(QtCore.Qt.ItemDataRole.UserRole) or None

    def _selected_index(self) -> int:
        items = self._list.selectedItems()
        if not items:
            return -1
        return self._list.row(items[0])

    def _show_status(self, text: str) -> None:
        # Status is surfaced on the window title bar via the tab tooltip to
        # avoid an extra label above the list.
        self.setToolTip(text or "")

    # ── Actions ───────────────────────────────────────────────────

    def _on_activated(self, item: QtWidgets.QListWidgetItem) -> None:
        note = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if note:
            self._edit_note(self._list.row(item), note)

    def _on_open_clicked(self) -> None:
        index = self._selected_index()
        if index >= 0:
            self._edit_note(index, self._notes[index])

    def _on_edit_clicked(self) -> None:
        self._on_open_clicked()

    def _on_new_clicked(self) -> None:
        dialog = NoteDialog(parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self._notes.append(dialog.collect())
        self._save()

    def _edit_note(self, index: int, note: dict) -> None:
        dialog = NoteDialog(note, parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        if 0 <= index < len(self._notes):
            self._notes[index] = dialog.collect()
        self._save()

    def _on_delete_clicked(self) -> None:
        index = self._selected_index()
        if index < 0:
            return
        note = self._notes[index]
        title = note.get("title") or tr("notes_untitled")
        answer = QtWidgets.QMessageBox.question(
            self, tr("notes_remove"), tr("notes_remove_confirm", title=title))
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        del self._notes[index]
        self._save()
