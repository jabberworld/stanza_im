"""Cache overview and cleanup dialog (Help -> Cache).

Shows the disk usage of every cache the client keeps (media previews,
avatars, map tiles, vCard/discovery metadata, the roster cache, the Chromium
HTTP cache and the local chat history) with a per-cache "Clear" action and a
total.  The dialog only measures and calls callbacks; the owner (MainWindow)
performs the clear and the UI refresh, so this module stays testable.
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import Callable

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon
from stanza_im.include.media import human_size


def dir_size(path: str) -> int:
    """Total size of the regular files under *path* (0 when unavailable)."""
    if not path:
        return 0
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    except OSError:
        return 0
    return total


def file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def webengine_cache_path() -> str:
    """The Chromium HTTP cache directory ('' when it cannot be determined).

    The QtWebEngine module is imported lazily by the chat views; asking the
    profile is only possible once it is loaded.  Otherwise the standard cache
    location is used without initialising Chromium just for this dialog.
    """
    if "PyQt6.QtWebEngineCore" in sys.modules:
        try:
            from PyQt6.QtWebEngineCore import QWebEngineProfile
            return QWebEngineProfile.defaultProfile().cachePath() or ""
        except Exception:  # noqa: BLE001 - optional dependency
            return ""
    try:
        from PyQt6.QtCore import QStandardPaths
        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation)
    except Exception:  # noqa: BLE001
        return ""
    return os.path.join(base, "QtWebEngine", "Default") if base else ""


def clear_webengine_cache() -> None:
    """Clear the Chromium HTTP cache (or its directory when not running)."""
    if "PyQt6.QtWebEngineCore" in sys.modules:
        try:
            from PyQt6.QtWebEngineCore import QWebEngineProfile
            QWebEngineProfile.defaultProfile().clearHttpCache()
            return
        except Exception:  # noqa: BLE001
            pass
    path = webengine_cache_path()
    if path and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


@dataclass
class CacheEntry:
    """One cache row: title/hint, a size probe and a clear callback."""

    key: str
    title: str
    hint: str
    warning: str
    size: Callable[[], int | None]
    clear: Callable[[], object]


class CacheDialog(QtWidgets.QDialog):
    """Non-modal cache overview with per-cache clearing."""

    def __init__(self, entries: list[CacheEntry], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("cache_dialog_title"))
        self.setModal(False)
        self.setSizeGripEnabled(True)
        self._entries = list(entries)
        self._sizes: dict[str, int | None] = {}
        self._buttons: dict[str, QtWidgets.QPushButton] = {}

        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(tr("cache_intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._table = QtWidgets.QTableWidget(0, 4, self)
        self._table.setHorizontalHeaderLabels([
            tr("cache_column_cache"), tr("cache_column_hint"),
            tr("cache_column_size"), ""])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        # One line per cache: a long hint elides (the tooltip keeps it whole)
        # instead of wrapping the whole row.
        self._table.setWordWrap(False)
        self._table.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self._table.verticalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(
            3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        self._total_label = QtWidgets.QLabel()
        self._total_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._total_label)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._refresh_btn = QtWidgets.QPushButton(tr("cache_refresh"))
        self._refresh_btn.clicked.connect(self.refresh)
        buttons.addWidget(self._refresh_btn)
        close_btn = QtWidgets.QPushButton(tr("cache_close"))
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self.resize(760, 520)
        self.refresh()

    # ── Data ──────────────────────────────────────────────────────

    @property
    def sizes(self) -> dict[str, int | None]:
        """The last measured size per cache key."""
        return dict(self._sizes)

    @property
    def total_size(self) -> int:
        return sum(size for size in self._sizes.values()
                   if size is not None)

    def _measure(self, entry: CacheEntry) -> int | None:
        try:
            size = entry.size()
        except Exception:  # noqa: BLE001 - a cache probe must not break the UI
            return None
        return None if size is None else int(size)

    def refresh(self) -> None:
        """Measure every cache and rebuild the table."""
        self._sizes = {}
        self._buttons = {}
        self._table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            size = self._measure(entry)
            self._sizes[entry.key] = size
            name = QtWidgets.QTableWidgetItem(entry.title)
            name.setToolTip(entry.hint)
            hint = QtWidgets.QTableWidgetItem(entry.hint)
            hint.setToolTip(entry.hint)
            size_text = (tr("cache_size_unavailable") if size is None
                         else (human_size(size) or "0 B"))
            size_item = QtWidgets.QTableWidgetItem(size_text)
            size_item.setToolTip(tr("cache_size_tooltip", bytes=size or 0))
            self._table.setItem(row, 0, name)
            self._table.setItem(row, 1, hint)
            self._table.setItem(row, 2, size_item)
            button = QtWidgets.QToolButton()
            icon = QtGui.QIcon(find_icon("process-stop.png"))
            if not icon.isNull():
                button.setIcon(icon)
            button.setIconSize(QtCore.QSize(16, 16))
            button.setFixedSize(24, 24)
            button.setAutoRaise(True)
            button.setToolTip(entry.warning)
            button.clicked.connect(
                lambda _checked=False, e=entry: self.clear_entry(e))
            holder = QtWidgets.QWidget(self._table)
            cell = QtWidgets.QHBoxLayout(holder)
            cell.setContentsMargins(0, 0, 0, 0)
            cell.addStretch(1)
            cell.addWidget(button)
            cell.addStretch(1)
            self._table.setCellWidget(row, 3, holder)
            self._buttons[entry.key] = button
        self._total_label.setText(
            tr("cache_total", size=human_size(self.total_size) or "0 B"))

    def showEvent(self, event):  # noqa: N802 - Qt override
        super().showEvent(event)
        # ``refresh`` runs before the first layout: the hint column is still
        # narrow there, so the rows would be measured against wrapped text.
        # Re-fit them once the real widths are in place.
        QtCore.QTimer.singleShot(0, self._table.resizeRowsToContents)

    def clear_entry(self, entry: CacheEntry) -> bool:
        """Confirm and clear one cache; returns whether it was cleared."""
        answer = QtWidgets.QMessageBox.question(
            self, tr("cache_clear_title"), entry.warning,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return False
        try:
            entry.clear()
        except Exception:  # noqa: BLE001 - report and keep the dialog usable
            import logging
            logging.getLogger(__name__).exception(
                "Could not clear the %s cache", entry.key)
        self.refresh()
        return True
