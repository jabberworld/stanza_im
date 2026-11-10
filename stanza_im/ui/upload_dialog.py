"""File transfer dialog (HTTP Upload / P2P).

The dialog is a reusable list of transfer cards.  Each card is laid out
vertically: the file name, a full-width progress bar with a cancel button, and
the transfer statistics/status.  A new transfer is inserted at the top of the
list.  The bottom controls are only shown for a new outgoing batch.
"""
from __future__ import annotations

import math
import os
import time

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon
from stanza_im.include.utils import format_size

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
               ".svg", ".svgz", ".tif", ".tiff", ".ico"}
_ICON_SIZE = 22


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def format_speed(bps: float) -> str:
    """Human-readable transfer speed, e.g. ``1.5 KB/s`` ("" when unknown)."""
    if not bps or bps <= 0 or math.isinf(bps):
        return ""
    if bps < 1:
        return "<1 B/s"
    return format_size(int(bps)) + "/s"


def format_eta(seconds: float) -> str:
    """Estimated time remaining, e.g. ``12s``, ``2:05``, ``1:02:03``.

    A remaining time above one day is abbreviated instead of growing the
    statistics line (and the dialog's horizontal scroll range) without bound.
    """
    if seconds is None or seconds <= 0 or math.isinf(seconds):
        return ""
    if seconds > 86400:
        return tr("ft_eta_over_day")
    total = int(math.ceil(seconds))
    if total < 60:
        return f"{total}s"
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _preview_pixmap(path: str, widget: QtWidgets.QWidget) -> QtGui.QPixmap:
    """Thumbnail for images, otherwise the standard generic file icon."""
    ext = os.path.splitext(str(path))[1].lower()
    if ext in _IMAGE_EXTS:
        pix = QtGui.QPixmap(str(path))
        if not pix.isNull():
            return pix.scaled(
                _ICON_SIZE, _ICON_SIZE,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
    icon = widget.style().standardIcon(
        QtWidgets.QStyle.StandardPixmap.SP_FileIcon)
    return icon.pixmap(_ICON_SIZE, _ICON_SIZE)


class _ElidedLabel(QtWidgets.QLabel):
    """A single-line label that uses all available width and elides the rest."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = str(text or "")
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                           QtWidgets.QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setWordWrap(False)
        self.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setToolTip(self._full_text)
        self._refresh()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self._refresh()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event):  # noqa: N802 - Qt API
        self._refresh()
        super().resizeEvent(event)

    def _refresh(self) -> None:
        width = max(0, self.width())
        shown = self.fontMetrics().elidedText(
            self._full_text, QtCore.Qt.TextElideMode.ElideMiddle, width)
        QtWidgets.QLabel.setText(self, shown)


class _FileRow(QtWidgets.QWidget):
    """One file transfer card (name / progress / stats)."""

    cancel_requested = QtCore.pyqtSignal(object)
    state_changed = QtCore.pyqtSignal()

    def __init__(self, path: str = "", parent=None, *, name: str = "",
                 total: int | None = None, direction: str = "out",
                 status: str = "", transfer_id: str = "",
                 offer_id: str = "", jid: str = "",
                 cancelable: bool = True):
        super().__init__(parent)
        self._path = str(path or "")
        self._name = str(name or os.path.basename(self._path) or "file")
        self._total = int(total if total is not None else _file_size(self._path))
        self._direction = str(direction or "out")
        self._transfer_id = str(transfer_id or "")
        self._offer_id = str(offer_id or "")
        self._jid = str(jid or "")
        self._speed = 0.0
        self._start_time: float | None = None
        self._last_time: float | None = None
        self._last_bytes = 0
        self._samples: list[tuple[float, int]] = []
        self._last_progress_time: float | None = None
        self._status_text = str(status or "")
        self._cancelable = bool(cancelable)
        self._finished = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 5, 4, 5)
        layout.setSpacing(4)

        name_row = QtWidgets.QHBoxLayout()
        name_row.setSpacing(6)
        self._icon = QtWidgets.QLabel(self)
        self._icon.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        self._icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        if self._path:
            self._icon.setPixmap(_preview_pixmap(self._path, self))
        name_row.addWidget(self._icon, 0,
                           QtCore.Qt.AlignmentFlag.AlignVCenter)
        self._name_label = _ElidedLabel(self._name, self)
        name_row.addWidget(self._name_label, 1)
        layout.addLayout(name_row)

        progress_row = QtWidgets.QHBoxLayout()
        progress_row.setSpacing(0)
        self._bar = QtWidgets.QProgressBar(self)
        # 0.1% resolution: a 4 KiB block is visible even on a 37.5 MB file.
        self._bar.setRange(0, 1000)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                QtWidgets.QSizePolicy.Policy.Fixed)
        self._bar.setMinimumWidth(0)
        progress_row.addWidget(self._bar, 1)
        self._cancel_btn = QtWidgets.QToolButton(self)
        icon = find_icon("process-stop.png") or find_icon("cancel.svg")
        if icon:
            self._cancel_btn.setIcon(QtGui.QIcon(icon))
        self._cancel_btn.setAutoRaise(True)
        self._cancel_btn.setFixedSize(24, 24)
        self._cancel_btn.setToolTip(tr("ft_cancel_transfer"))
        self._cancel_btn.setVisible(self._cancelable)
        self._cancel_btn.clicked.connect(
            lambda: self.cancel_requested.emit(self))
        # Put the cancel button in the name row; the progress bar below spans
        # the full card width and never needs to be re-laid out when the
        # button disappears after completion.
        name_row.addWidget(self._cancel_btn, 0,
                           QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(progress_row)

        stats_row = QtWidgets.QHBoxLayout()
        stats_row.setSpacing(6)
        self._stats_label = QtWidgets.QLabel("\u2014", self)
        self._stats_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred)
        self._stats_label.setMinimumWidth(0)
        self._status_label = QtWidgets.QLabel(self._status_text, self)
        self._status_label.setStyleSheet("color: gray; font-size: 11px;")
        self._lock = QtWidgets.QLabel(self)
        lock_icon = find_icon("lock.svg")
        if lock_icon:
            self._lock.setPixmap(QtGui.QIcon(lock_icon).pixmap(14, 14))
        self._lock.setToolTip(tr("ft_encrypted"))
        self._lock.setVisible(False)
        stats_row.addWidget(self._stats_label, 1)
        stats_row.addWidget(self._status_label, 0)
        stats_row.addWidget(self._lock, 0)
        layout.addLayout(stats_row)

        self.setToolTip(self._path or self._name)
        self._update_stats(0)

    def set_cancelable(self, cancelable: bool) -> None:
        self._cancelable = bool(cancelable)
        self._cancel_btn.setVisible(self._cancelable)

    def is_finished(self) -> bool:
        return self._finished

    def mark_finished(self) -> None:
        """Mark the card as done/failed/cancelled (not active any more)."""
        if self._finished:
            return
        self._finished = True
        self.set_cancelable(False)
        self.state_changed.emit()

    def set_encrypted(self, encrypted: bool) -> None:
        """Mark the row as an end-to-end encrypted transfer."""
        self._lock.setVisible(bool(encrypted))

    def set_status(self, status: str) -> None:
        self._status_text = str(status or "")
        self._status_label.setText(self._status_text)
        self._status_label.setToolTip(self._status_text)

    def set_progress(self, pct: float, now: float | None = None) -> None:
        """Update from a percentage (HTTP Upload)."""
        pct = max(0.0, min(100.0, float(pct)))
        current = int(self._total * pct / 100) if self._total else 0
        self._advance(current, now, bar_pct=pct)

    def set_progress_bytes(self, current: int,
                           now: float | None = None) -> None:
        """Update from the number of acknowledged bytes (Jingle)."""
        current = max(0, int(current))
        if self._total:
            current = min(current, self._total)
        self._advance(current, now)

    def _advance(self, current: int, now: float | None = None,
                 bar_pct: float | None = None) -> None:
        if self._finished:
            return
        if bar_pct is not None:
            self._bar.setValue(int(round(max(0.0, min(100.0, bar_pct)) * 10)))
        elif self._total:
            self._bar.setValue(int(round(current * 1000 / self._total)))
        else:
            self._bar.setValue(0)
        if not self._total:
            return
        now = time.monotonic() if now is None else now
        if self._last_time is None:
            self._start_time = now
            self._last_time = now
            self._last_bytes = current
            self._last_progress_time = now
            self._samples = [(now, current)]
            self._update_stats(current)
            return
        if current > self._last_bytes:
            self._last_progress_time = now
            self._last_bytes = current
        self._samples.append((now, current))
        cutoff = now - 5.0
        while len(self._samples) > 2 and self._samples[0][0] < cutoff:
            self._samples.pop(0)
        elapsed = now - self._last_time
        if elapsed >= 0.3:
            if len(self._samples) >= 2:
                t0, c0 = self._samples[0]
                t1, c1 = self._samples[-1]
                if t1 > t0:
                    self._speed = max(0.0, (c1 - c0) / (t1 - t0))
            stalled = (self._last_progress_time is not None
                       and now - self._last_progress_time > 5.0)
            if stalled:
                self._speed = 0.0
            self._last_time = now
            self._update_stats(current)

    def _update_stats(self, current: int) -> None:
        parts = []
        if self._total:
            parts.append(f"{format_size(current)} / "
                         f"{format_size(self._total)}")
        if self._speed > 0:
            parts.append(format_speed(self._speed))
            remaining = self._total - current
            if remaining > 0:
                parts.append(tr("ft_eta", eta=format_eta(
                    remaining / self._speed)))
        self._stats_label.setText(" \u00b7 ".join(parts) or "\u2014")

    def finish(self, now: float | None = None) -> None:
        self._bar.setValue(self._bar.maximum())
        self.set_status(tr("ft_status_done"))
        self.mark_finished()
        if not self._total or self._start_time is None:
            return
        now = time.monotonic() if now is None else now
        elapsed = now - self._start_time
        average = self._total / elapsed if elapsed > 0 else 0.0
        text = f"{format_size(self._total)} / {format_size(self._total)}"
        if average > 0:
            text += " \u00b7 " + format_speed(average)
        self._stats_label.setText(text)

    def fail(self, message: str) -> None:
        reason = str(message or tr("ft_status_failed"))
        self._bar.setStyleSheet(
            "QProgressBar::chunk { background: #d9534f; }")
        self._bar.setFormat(tr("ft_status_failed"))
        self._bar.setToolTip(reason)
        self._stats_label.setText("")
        self.set_status(reason)
        self.mark_finished()


class FileTransferDialog(QtWidgets.QDialog):
    """Reusable list of file-transfer cards plus the send-batch controls."""

    upload_started = QtCore.pyqtSignal(str)  # shared caption ("" if none)
    transfer_cancel_requested = QtCore.pyqtSignal(object)  # _FileRow

    def __init__(self, paths=None, parent=None, targets=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ft_upload_title"))
        self.setMinimumWidth(480)
        self._rows: list[_FileRow] = []
        self._rows_by_path: dict[str, _FileRow] = {}
        self._rows_by_key: dict[str, _FileRow] = {}
        self._pending_paths: list[str] = []
        self._targets = list(targets or [])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._list_host = QtWidgets.QWidget(self)
        self._rows_layout = QtWidgets.QVBoxLayout(self._list_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        self._rows_layout.addStretch(1)
        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._list_host)
        self._scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self._scroll, 1)

        self._target_label = QtWidgets.QLabel(tr("ft_target_label"), self)
        self._target_combo = QtWidgets.QComboBox(self)
        self._target_row = QtWidgets.QHBoxLayout()
        self._target_row.addWidget(self._target_label)
        self._target_row.addWidget(self._target_combo, 1)
        layout.addLayout(self._target_row)
        self._rebuild_targets(self._targets)

        self._caption_label = QtWidgets.QLabel(tr("ft_upload_caption"), self)
        layout.addWidget(self._caption_label)
        self._caption = QtWidgets.QLineEdit(self)
        self._caption.setPlaceholderText(tr("ft_upload_caption_placeholder"))
        self._caption.returnPressed.connect(self._on_ok)
        layout.addWidget(self._caption)

        buttons = QtWidgets.QHBoxLayout()
        self._clear_btn = QtWidgets.QPushButton(tr("ft_clear_completed"), self)
        self._clear_btn.clicked.connect(self.clear_completed)
        buttons.addWidget(self._clear_btn)
        buttons.addStretch(1)
        self._ok_btn = QtWidgets.QPushButton(tr("dialog_ok"), self)
        self._cancel_btn = QtWidgets.QPushButton(tr("dialog_cancel"), self)
        self._ok_btn.setDefault(True)
        buttons.addWidget(self._ok_btn)
        buttons.addWidget(self._cancel_btn)
        layout.addLayout(buttons)

        self._ok_btn.clicked.connect(self._on_ok)
        self._cancel_btn.clicked.connect(self.reject)
        self.add_paths(paths or [], pending=True)
        self._update_clear_button()
        self._caption.setFocus()

    def showEvent(self, event):  # noqa: N802 - Qt API
        super().showEvent(event)
        self._schedule_fit()
        if self._ok_btn.isVisible() and self._ok_btn.isEnabled():
            self._caption.setFocus()

    def _schedule_fit(self) -> None:
        QtCore.QTimer.singleShot(0, self._fit_height)

    def _fit_height(self) -> None:
        """Grow to fit a few cards, but scroll once they exceed the screen."""
        rows = self._rows_layout.sizeHint().height()
        screen = self.screen() or QtWidgets.QApplication.primaryScreen()
        max_list = 600
        if screen is not None:
            max_list = max(180, int(screen.availableGeometry().height() * 0.65))
        self._scroll.setMinimumHeight(min(max(0, rows + 4), max_list))
        self.adjustSize()
        if screen is not None:
            max_height = int(screen.availableGeometry().height() * 0.9)
            if self.height() > max_height:
                self.resize(self.width(), max_height)

    def _update_clear_button(self) -> None:
        finished = any(row.is_finished() for row in self._rows)
        self._clear_btn.setVisible(finished)
        self._clear_btn.setEnabled(finished)

    def clear_completed(self) -> None:
        """Remove every finished card (done, failed or cancelled)."""
        for row in list(self._rows):
            if row.is_finished():
                self.remove_row(row)
        self._update_clear_button()
        self._schedule_fit()

    # ── target selector / send controls ──────────────────────────

    def _rebuild_targets(self, targets) -> None:
        self._targets = list(targets or [])
        self._target_combo.clear()
        if len(self._targets) <= 1:
            self._target_label.setVisible(False)
            self._target_combo.setVisible(False)
            return
        self._target_label.setVisible(True)
        self._target_combo.setVisible(True)
        self._target_combo.addItem(tr("ft_target_all"), "")
        for full_jid, label in self._targets:
            self._target_combo.addItem(label, full_jid)
            self._target_combo.setItemData(
                self._target_combo.count() - 1, full_jid,
                QtCore.Qt.ItemDataRole.ToolTipRole)

    def set_incoming_mode(self, incoming: bool) -> None:
        """Make the send controls reflect an incoming-only window.

        The dialog is shared with outgoing batches.  Disable OK only when no
        outgoing batch is waiting to start, so an incoming offer cannot block
        a send the user has already prepared.
        """
        if incoming:
            if not self._pending_paths:
                self._ok_btn.setEnabled(False)
            return
        self._ok_btn.setEnabled(True)
        self._ok_btn.setText(tr("dialog_ok"))

    def prepare_send(self, paths, targets=None) -> None:
        """Add a new outgoing batch and re-enable the send controls."""
        self.set_incoming_mode(False)
        if targets is not None:
            self._rebuild_targets(targets)
        self.add_paths(paths or [], pending=True)
        self._caption.clear()
        self._ok_btn.setEnabled(True)
        self._ok_btn.setText(tr("dialog_ok"))
        self._cancel_btn.setText(tr("dialog_cancel"))
        self._caption.setFocus()

    def take_pending_paths(self) -> list[str]:
        paths = list(self._pending_paths)
        self._pending_paths = []
        return paths

    def selected_target(self) -> str:
        """The chosen full JID, or ``""`` for all recipients' clients."""
        return (str(self._target_combo.currentData() or "")
                if self._target_combo.count() > 1 else "")

    # ── rows ─────────────────────────────────────────────────────

    def _connect_row(self, row: _FileRow) -> None:
        row.cancel_requested.connect(self.transfer_cancel_requested.emit)
        row.state_changed.connect(self._on_row_state_changed)

    def _on_row_state_changed(self) -> None:
        self._update_clear_button()
        self._schedule_fit()

    def add_path(self, path: str, *, direction: str = "out",
                 total: int | None = None, status: str = "",
                 cancelable: bool = True) -> _FileRow:
        path = str(path)
        # A new send always gets a new card.  The previous card for the same
        # path may still be visible as history until "Clear completed".
        row = _FileRow(path, self, direction=direction, total=total,
                       status=status, cancelable=cancelable)
        self._rows.insert(0, row)
        self._rows_layout.insertWidget(0, row)
        self._rows_by_path[path] = row
        self._connect_row(row)
        self._update_clear_button()
        self._schedule_fit()
        return row

    def add_paths(self, paths, *, pending: bool = False) -> list[_FileRow]:
        paths = [str(path) for path in (paths or []) if path]
        rows = []
        for path in reversed(paths):
            rows.append(self.add_path(path))
        if pending:
            self._pending_paths = list(paths)
        return list(reversed(rows))

    def add_transfer(self, key: str, *, path: str = "", name: str = "",
                     total: int = 0, direction: str = "out",
                     status: str = "", transfer_id: str = "",
                     offer_id: str = "", jid: str = "",
                     cancelable: bool = True) -> _FileRow:
        row = _FileRow(path, self, name=name, total=total,
                       direction=direction, status=status,
                       transfer_id=transfer_id, offer_id=offer_id, jid=jid,
                       cancelable=cancelable)
        self._rows.insert(0, row)
        self._rows_layout.insertWidget(0, row)
        if key:
            self._rows_by_key[str(key)] = row
        if path:
            self._rows_by_path[str(path)] = row
        self._connect_row(row)
        self._update_clear_button()
        self._schedule_fit()
        return row

    def row_for_path(self, path: str) -> _FileRow | None:
        return self._rows_by_path.get(str(path))

    def row_for_key(self, key: str) -> _FileRow | None:
        return self._rows_by_key.get(str(key))

    def remove_row(self, row: _FileRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        for path, item in list(self._rows_by_path.items()):
            if item is row:
                self._rows_by_path.pop(path, None)
        for key, item in list(self._rows_by_key.items()):
            if item is row:
                self._rows_by_key.pop(key, None)
        self._update_clear_button()
        self._schedule_fit()

    # ── compatibility helpers used by the transfer flows/tests ───

    @property
    def paths(self) -> list[str]:
        return [row._path for row in self._rows]

    def caption(self) -> str:
        return self._caption.text().strip()

    def row_count(self) -> int:
        return len(self._rows)

    def set_encrypted(self, index: int, encrypted: bool = True) -> None:
        if 0 <= index < len(self._rows):
            self._rows[index].set_encrypted(encrypted)

    def set_progress(self, index: int, pct: int,
                     now: float | None = None) -> None:
        if 0 <= index < len(self._rows):
            self._rows[index].set_progress(pct, now=now)

    def set_row_done(self, index: int) -> None:
        if 0 <= index < len(self._rows):
            self._rows[index].finish()

    def set_row_failed(self, index: int, message: str = "") -> None:
        if 0 <= index < len(self._rows):
            self._rows[index].fail(message)

    def _on_ok(self):
        self._ok_btn.setEnabled(False)
        self._ok_btn.setText(tr("ft_upload_in_progress"))
        self._cancel_btn.setText(tr("dialog_close"))
        self.upload_started.emit(self.caption())
