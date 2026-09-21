"""File transfer dialog (XEP-0363 HTTP Upload / P2P placeholder).

Lists the files about to be sent with a thumbnail (images) or a generic
file icon, a per-file progress bar and one shared caption message. Non-modal:
pressing OK starts the transfers while the dialog stays open and shows live
progress; it is closed by the caller once every file reached a terminal state.
"""
from __future__ import annotations

import math
import os
import time

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.utils import format_size

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
               ".svg", ".svgz", ".tif", ".tiff", ".ico"}
_THUMB_SIZE = 56


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def format_speed(bps: float) -> str:
    """Human-readable transfer speed, e.g. ``1.5 KB/s`` ("" when unknown)."""
    if not bps or bps <= 0 or math.isinf(bps):
        return ""
    return format_size(int(bps)) + "/s"


def format_eta(seconds: float) -> str:
    """Estimated time remaining, e.g. ``12s``, ``2:05`` or ``1:02:03``."""
    if seconds is None or seconds <= 0 or math.isinf(seconds):
        return ""
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
                _THUMB_SIZE, _THUMB_SIZE,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
    icon = widget.style().standardIcon(
        QtWidgets.QStyle.StandardPixmap.SP_FileIcon)
    return icon.pixmap(_THUMB_SIZE, _THUMB_SIZE)


class _FileRow(QtWidgets.QWidget):
    """One file: preview/icon, name + size, a progress bar and live stats
    (transferred / total, speed, ETA)."""

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = str(path)
        self._total = _file_size(self._path)
        self._speed = 0.0
        self._start_time: float | None = None
        self._last_time: float | None = None
        self._last_bytes = 0
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        self._icon = QtWidgets.QLabel(self)
        self._icon.setFixedSize(_THUMB_SIZE + 8, _THUMB_SIZE + 8)
        self._icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._icon.setPixmap(_preview_pixmap(self._path, self))
        layout.addWidget(self._icon, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        text = QtWidgets.QVBoxLayout()
        text.setSpacing(2)
        name = QtWidgets.QLabel(os.path.basename(self._path), self)
        name.setWordWrap(True)
        name.setStyleSheet("font-weight: bold;")
        size_label = QtWidgets.QLabel(format_size(self._total), self)
        size_label.setStyleSheet("color: gray; font-size: 11px;")
        self._stats_label = QtWidgets.QLabel("\u2014", self)
        self._stats_label.setStyleSheet("color: gray; font-size: 11px;")
        text.addWidget(name)
        text.addWidget(size_label)
        text.addWidget(self._stats_label)
        layout.addLayout(text, 1)

        self._bar = QtWidgets.QProgressBar(self)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedWidth(160)
        layout.addWidget(self._bar, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

        self.setToolTip(self._path)

    def set_progress(self, pct: int, now: float | None = None) -> None:
        pct = max(0, min(100, int(pct)))
        self._bar.setValue(pct)
        if not self._total:
            return
        now = time.monotonic() if now is None else now
        current = int(self._total * pct / 100)
        if self._last_time is None:
            self._start_time = now
            self._last_time = now
            self._last_bytes = current
            self._update_stats(current)
            return
        elapsed = now - self._last_time
        if elapsed >= 0.3:
            instant = (current - self._last_bytes) / elapsed
            self._speed = (instant if self._speed <= 0
                           else 0.6 * self._speed + 0.4 * instant)
            self._last_time = now
            self._last_bytes = current
            self._update_stats(current)

    def _update_stats(self, current: int) -> None:
        parts = [f"{format_size(current)} / {format_size(self._total)}"]
        if self._speed > 0:
            parts.append(format_speed(self._speed))
            remaining = self._total - current
            if remaining > 0:
                parts.append(tr("ft_eta", eta=format_eta(
                    remaining / self._speed)))
        self._stats_label.setText(" \u00b7 ".join(parts))

    def finish(self, now: float | None = None) -> None:
        self._bar.setValue(100)
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
        self._bar.setStyleSheet(
            "QProgressBar::chunk { background: #d9534f; }")
        self._bar.setFormat((message or tr("ft_upload_error_row"))
                            .replace("%", "%%"))
        self._stats_label.setText("")


class FileTransferDialog(QtWidgets.QDialog):
    """Dialog that previews files and reports per-file upload progress."""

    upload_started = QtCore.pyqtSignal(str)  # shared caption ("" if none)

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ft_upload_title"))
        self.setMinimumWidth(480)
        self._rows = [_FileRow(path, self) for path in (paths or [])]

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        list_host = QtWidgets.QWidget(self)
        rows = QtWidgets.QVBoxLayout(list_host)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(4)
        for row in self._rows:
            rows.addWidget(row)
        rows.addStretch(1)
        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(list_host)
        if self._rows:
            scroll.setFixedHeight(
                min(48 + len(self._rows) * (_THUMB_SIZE + 16), 320))
        layout.addWidget(scroll, 1)

        layout.addWidget(QtWidgets.QLabel(tr("ft_upload_caption"), self))
        self._caption = QtWidgets.QLineEdit(self)
        self._caption.setPlaceholderText(tr("ft_upload_caption_placeholder"))
        layout.addWidget(self._caption)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._ok_btn = QtWidgets.QPushButton(tr("dialog_ok"), self)
        self._cancel_btn = QtWidgets.QPushButton(tr("dialog_cancel"), self)
        self._ok_btn.setDefault(True)
        buttons.addWidget(self._ok_btn)
        buttons.addWidget(self._cancel_btn)
        layout.addLayout(buttons)

        self._ok_btn.clicked.connect(self._on_ok)
        self._cancel_btn.clicked.connect(self.reject)

    @property
    def paths(self) -> list[str]:
        return [row._path for row in self._rows]

    def caption(self) -> str:
        return self._caption.text().strip()

    def row_count(self) -> int:
        return len(self._rows)

    def set_progress(self, index: int, pct: int, now: float | None = None) -> None:
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