"""Media calendar widgets for the History Manager.

The view is a scrollable grid grouped by months.  Item thumbnails come from
the shared media preview cache; video thumbnails and audio/video duration are
filled in by :class:`stanza_im.ui.media_meta.MediaMetadataService`.
"""
from __future__ import annotations

import base64

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.include.constants import find_icon
from stanza_im.include.media import media_item_tokens
from stanza_im.include.utils import format_duration, format_local_datetime
from stanza_im.i18n import tr

_CARD_WIDTH = 172
_THUMB_HEIGHT = 104
_PAGE_SIZE = 80


def _pixmap_from_uri(uri: str) -> QtGui.QPixmap:
    if not uri or not uri.startswith("data:image/"):
        return QtGui.QPixmap()
    try:
        raw = base64.b64decode(uri.split(",", 1)[1])
    except Exception:  # noqa: BLE001
        return QtGui.QPixmap()
    pix = QtGui.QPixmap()
    pix.loadFromData(raw)
    return pix


def _placeholder(name: str, size: int = 48) -> QtGui.QPixmap:
    path = find_icon(name)
    if not path:
        return QtGui.QPixmap()
    pix = QtGui.QPixmap(path)
    if pix.isNull():
        return pix
    return pix.scaled(
        size, size, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation)


class MediaCard(QtWidgets.QFrame):
    """One fixed-size media tile."""

    clicked = QtCore.pyqtSignal(dict)
    context_requested = QtCore.pyqtSignal(dict, QtCore.QPoint)

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self._item = item
        self._name = str(item.get("name") or "")
        self.setFixedSize(_CARD_WIDTH, 150)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "MediaCard { background: palette(base); border: 1px solid "
            "palette(mid); border-radius: 5px; }")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 4)
        layout.setSpacing(3)
        self._thumb = QtWidgets.QLabel(self)
        self._thumb.setFixedHeight(_THUMB_HEIGHT)
        self._thumb.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet(
            "background: palette(alternate-base); border-radius: 3px;")
        layout.addWidget(self._thumb)
        self._caption = QtWidgets.QLabel(self)
        self._caption.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Fixed)
        layout.addWidget(self._caption)
        self._play = QtWidgets.QLabel("▶", self._thumb)
        self._play.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._play.setStyleSheet(
            "color: white; background: rgba(0,0,0,120); border-radius: "
            "12px; font-size: 16px;")
        self._play.setFixedSize(24, 24)
        self._play.setVisible(item.get("kind") in ("video", "audio"))
        self._duration = QtWidgets.QLabel("", self._thumb)
        self._duration.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignBottom)
        self._duration.setStyleSheet(
            "color: white; background: rgba(0,0,0,130); padding: 1px 3px; "
            "border-radius: 3px;")
        self._duration.setVisible(False)
        for label in (self._play, self._duration):
            label.setAttribute(
                QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setToolTip(self._tooltip())
        self._update_caption()
        self._set_placeholder()
        duration = float(item.get("duration") or 0.0)
        if duration:
            self.set_duration(duration)
        self._place_overlays()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._place_overlays()

    def _place_overlays(self) -> None:
        thumb = self._thumb
        self._play.move(
            max(2, (thumb.width() - self._play.width()) // 2),
            max(2, (thumb.height() - self._play.height()) // 2))
        self._duration.adjustSize()
        self._duration.move(
            max(2, thumb.width() - self._duration.width() - 4),
            max(2, thumb.height() - self._duration.height() - 4))

    def _tooltip(self) -> str:
        parts = [self._name or self._item.get("url", "")]
        if self._item.get("jid"):
            parts.append(str(self._item["jid"]))
        if self._item.get("timestamp"):
            stamp = str(self._item["timestamp"])
            parts.append(format_local_datetime(stamp) or stamp)
        return "\n".join(parts)

    def _update_caption(self) -> None:
        metrics = self._caption.fontMetrics()
        width = _CARD_WIDTH - 12
        self._caption.setText(metrics.elidedText(
            self._name or self._item.get("url", ""),
            QtCore.Qt.TextElideMode.ElideMiddle, width))
        self._caption.setToolTip(self._name)

    def _set_placeholder(self) -> None:
        kind = self._item.get("kind")
        icon = {"image": "wb-image.svg", "video": "camera.svg",
                "audio": "sound.svg"}.get(kind, "wb-image.svg")
        self._thumb.setPixmap(_placeholder(icon))

    def set_thumb_uri(self, uri: str) -> None:
        pix = _pixmap_from_uri(uri)
        if not pix.isNull():
            self._thumb.setPixmap(pix.scaled(
                _CARD_WIDTH - 10, _THUMB_HEIGHT,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation))
            self._place_overlays()

    def set_duration(self, seconds: float) -> None:
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            return
        if seconds <= 0:
            return
        self._duration.setText(format_duration(seconds))
        self._duration.setVisible(True)
        self._place_overlays()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self._item)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802
        self.context_requested.emit(self._item, event.globalPos())
        event.accept()


class HistoryMediaView(QtWidgets.QWidget):
    """Scrollable month-grouped media grid for one media kind."""

    open_requested = QtCore.pyqtSignal(str, str)   # url, kind
    context_requested = QtCore.pyqtSignal(dict, QtCore.QPoint)
    load_more = QtCore.pyqtSignal()

    def __init__(self, kind: str, preview_service=None, meta_service=None,
                 parent=None):
        super().__init__(parent)
        self._kind = kind
        self._preview = preview_service
        self._meta = meta_service
        self._items: list[dict] = []
        self._filter = ""
        self._loading = False
        self._status_text = ""
        self._cards: dict[str, list[MediaCard]] = {}
        self._render_limit = _PAGE_SIZE
        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._body = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self._body)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(6)
        self._scroll.setWidget(self._body)
        self._context = QtWidgets.QLabel("", self)
        self._context.setStyleSheet("color: palette(mid); padding: 0 4px;")
        self._context.setVisible(False)
        self._status = QtWidgets.QLabel("", self)
        self._status.setWordWrap(True)
        self._status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._context)
        layout.addWidget(self._scroll, 1)
        layout.addWidget(self._status)
        self._scroll.verticalScrollBar().valueChanged.connect(
            self._on_scroll)
        self._columns = 0
        self._rendering = False
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)
        self._resize_timer.timeout.connect(self._reflow)
        self._pending_filter = ""
        self._filter_timer = QtCore.QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(400)
        self._filter_timer.timeout.connect(self._apply_filter)
        if self._preview is not None:
            self._preview.thumbnail_ready.connect(self._on_thumb)
        if self._meta is not None:
            self._meta.meta_ready.connect(self._on_meta)
        self._render()

    def set_items(self, items: list[dict]) -> None:
        self._items = [item for item in (items or [])
                       if item.get("kind") == self._kind]
        self._render_limit = _PAGE_SIZE
        self._render()

    def append_items(self, items: list[dict]) -> None:
        known: set[tuple] = set()
        for item in self._items:
            known.update(media_item_tokens(item))
        for item in items or []:
            if item.get("kind") != self._kind:
                continue
            tokens = media_item_tokens(item)
            if tokens & known:
                continue
            known.update(tokens)
            self._items.append(item)
        bar = self._scroll.verticalScrollBar()
        value = bar.value()
        self._render_limit = min(
            len(self._visible()), self._render_limit + _PAGE_SIZE)
        self._render()
        QtCore.QTimer.singleShot(
            0, lambda b=bar, v=value: b.setValue(min(v, b.maximum())))

    def set_filter(self, text: str) -> None:
        text = str(text or "").strip().casefold()
        self._pending_filter = text
        if not text:
            self._filter_timer.stop()
            if self._filter:
                self._filter = ""
                self._render_limit = _PAGE_SIZE
                self._render()
            return
        self._filter_timer.start()

    def _apply_filter(self) -> None:
        if self._pending_filter == self._filter:
            return
        self._filter = self._pending_filter
        self._render_limit = _PAGE_SIZE
        self._render()

    def set_context(self, text: str) -> None:
        self._context.setText(str(text or ""))
        self._context.setVisible(bool(text))

    def can_scroll(self) -> bool:
        """Whether the current card grid is taller than the viewport."""
        return self._scroll.verticalScrollBar().maximum() > 0

    def viewport_height(self) -> int:
        return max(1, self._scroll.viewport().height())

    def near_bottom(self, margin: int | None = None) -> bool:
        """Whether the scroll is within *margin* pixels of the bottom."""
        bar = self._scroll.verticalScrollBar()
        if bar.maximum() <= 0:
            return True
        if margin is None:
            margin = max(200, self.viewport_height())
        return bar.value() >= bar.maximum() - margin

    def set_loading(self, loading: bool, status: str = "") -> None:
        self._loading = bool(loading)
        if status:
            self._status_text = status
        elif not self._loading:
            self._status_text = ""
        self._update_status()

    def set_status(self, status: str) -> None:
        self._status_text = str(status or "")
        self._update_status()

    def clear(self) -> None:
        self._items = []
        self._render_limit = _PAGE_SIZE
        self._status_text = ""
        self._loading = False
        self._render()

    def _visible(self) -> list[dict]:
        if not self._filter:
            return list(self._items)
        return [item for item in self._items
                if self._filter in str(item.get("name", "")).casefold()
                or self._filter in str(item.get("url", "")).casefold()]

    def _clear_item(self, item) -> None:
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
            return
        child = item.layout()
        if child is not None:
            while child.count():
                self._clear_item(child.takeAt(0))
            child.deleteLater()

    def _clear_layout(self) -> None:
        while self._layout.count():
            self._clear_item(self._layout.takeAt(0))

    def _render(self) -> None:
        if self._rendering:
            return
        self._rendering = True
        try:
            self._render_now()
        finally:
            self._rendering = False

    def _render_now(self) -> None:
        self._clear_layout()
        self._cards = {}
        items = sorted(self._visible(),
                       key=lambda item: str(item.get("timestamp") or ""),
                       reverse=True)[:self._render_limit]
        if not items:
            self._update_status()
            self._layout.addStretch(1)
            return
        groups: dict[str, list[dict]] = {}
        for item in items:
            key = str(item.get("timestamp") or "")[:7] or "????-??"
            groups.setdefault(key, []).append(item)
        for key in sorted(groups, reverse=True):
            self._layout.addWidget(self._month_header(key))
            grid = QtWidgets.QGridLayout()
            grid.setContentsMargins(0, 0, 0, 4)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(8)
            grid.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignTop)
            columns = max(1, (self._scroll.viewport().width() - 12)
                          // (_CARD_WIDTH + 8))
            self._columns = columns
            for index, item in enumerate(groups[key]):
                card = MediaCard(item, self._body)
                card.clicked.connect(self._open_item)
                card.context_requested.connect(self.context_requested)
                grid.addWidget(card, index // columns, index % columns)
                self._cards.setdefault(str(item.get("url", "")), []).append(card)
                self._prepare_preview(card, item)
            # Send all spare width to an empty column at the right so the
            # fixed cards stay flush with the left edge.
            grid.setColumnStretch(columns, 1)
            self._layout.addLayout(grid)
        self._layout.addStretch(1)
        self._update_status()

    def _prepare_preview(self, card: MediaCard, item: dict) -> None:
        url = str(item.get("url") or "")
        duration = float(item.get("duration") or 0.0)
        if self._preview is not None:
            uri = self._preview.cached_thumb_uri(url)
            if uri:
                card.set_thumb_uri(uri)
            elif item.get("kind") == "image":
                self._preview.request(url)
        if self._meta is not None and item.get("kind") in ("video", "audio"):
            info = self._meta._cache.info(url)
            if info.get("duration"):
                duration = float(info.get("duration") or duration)
            if duration:
                card.set_duration(duration)
            if item.get("kind") == "video":
                uri = self._preview.cached_thumb_uri(url) \
                    if self._preview is not None else None
                if uri:
                    card.set_thumb_uri(uri)
                self._meta.request(url, item["kind"])
            elif not duration:
                self._meta.request(url, "audio")

    def _open_item(self, item: dict) -> None:
        self.open_requested.emit(
            str(item.get("url") or ""), str(item.get("kind") or ""))

    def _on_thumb(self, url: str, uri: str) -> None:
        for card in self._cards.get(url, ()):
            card.set_thumb_uri(uri)

    def _on_meta(self, url: str, duration: float, uri: str) -> None:
        for card in self._cards.get(url, ()):
            if duration:
                card.set_duration(duration)
            if uri:
                card.set_thumb_uri(uri)

    def _update_status(self) -> None:
        text = self._status_text
        if not text:
            if self._loading:
                text = tr("history_media_loading")
            elif not self._visible():
                text = tr("history_no_results") if self._filter \
                    else tr("history_media_empty")
        self._status.setText(text)
        self._status.setVisible(bool(text))

    def _on_scroll(self, value: int) -> None:
        if self._loading:
            return
        bar = self._scroll.verticalScrollBar()
        margin = max(200, self.viewport_height())
        near_bottom = bar.maximum() <= 0 or value >= bar.maximum() - margin
        if near_bottom and self._render_limit < len(self._visible()):
            # Render the next local page only once the user approaches the
            # current end; this keeps all-time catalogs from building hundreds
            # of QWidget cards on the UI thread at once.
            old_value = bar.value()
            self._render_limit = min(
                len(self._visible()), self._render_limit + _PAGE_SIZE)
            self._render()
            QtCore.QTimer.singleShot(
                0, lambda b=bar, v=old_value:
                    b.setValue(min(v, b.maximum())))
            # Server mode still needs its next MAM page; local mode has no
            # listener for this signal.
            self.load_more.emit()
            return
        if near_bottom:
            self.load_more.emit()

    @staticmethod
    def _month_label(key: str) -> str:
        try:
            year, month = key.split("-", 1)
            year_i, month_i = int(year), int(month)
        except (TypeError, ValueError):
            return key
        locale = QtCore.QLocale()
        # ``monthName`` is the genitive form in Russian ("октября"); the
        # standalone form is the month name users expect in a heading.
        name = locale.standaloneMonthName(
            month_i, QtCore.QLocale.FormatType.LongFormat)
        return f"{year_i} {name}"

    def _month_header(self, key: str) -> QtWidgets.QWidget:
        header = QtWidgets.QWidget(self._body)
        row = QtWidgets.QHBoxLayout(header)
        row.setContentsMargins(0, 6, 0, 2)
        row.setSpacing(8)
        left = QtWidgets.QFrame(header)
        left.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        left.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        label = QtWidgets.QLabel(self._month_label(key), header)
        label.setStyleSheet("font-weight: bold; padding: 0 6px;")
        right = QtWidgets.QFrame(header)
        right.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        right.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        row.addWidget(left, 1)
        row.addWidget(label)
        row.addWidget(right, 1)
        return header

    def _reflow(self) -> None:
        columns = max(1, (self._scroll.viewport().width() - 12)
                      // (_CARD_WIDTH + 8))
        if columns != self._columns:
            self._render()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # Rebuild after the user stops dragging: destroying cards on every
        # pixel produced visible stale widgets and flicker.
        self._resize_timer.start()
