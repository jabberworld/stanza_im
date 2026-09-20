"""Standalone media viewer: fit-to-window images and video with fullscreen.

Images are shown from the on-disk original cache (downloaded on demand).
Videos use an embedded HTML5 ``<video>`` inside a dedicated QWebEngineView
window; ``F11`` toggles window fullscreen.  Without QWebEngine only images
are viewable (video falls back to a short notice).
"""
from __future__ import annotations

import html
import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr

try:
    from PyQt6 import QtWebEngineWidgets
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False

logger = logging.getLogger(__name__)


class _ImageScroll(QtWidgets.QScrollArea):
    """Scroll area that turns Ctrl+wheel into a zoom request."""

    zoom_step = QtCore.pyqtSignal(int)  # +1 zoom in, -1 zoom out

    def wheelEvent(self, event):
        if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoom_step.emit(1 if delta > 0 else -1)
                event.accept()
                return
        super().wheelEvent(event)


class MediaViewer(QtWidgets.QMainWindow):
    """Non-modal viewer window for an image or video URL."""

    closed = QtCore.pyqtSignal()

    def __init__(self, url: str, kind: str, service, parent=None,
                 geometry_cfg=None):
        super().__init__(parent)
        self._url = url
        self._kind = "video" if str(kind).startswith("video") else "image"
        self._service = service
        self._geometry_cfg = geometry_cfg
        self._pixmap = QtGui.QPixmap()
        self._fullscreen_hint = str(kind) == "video_fs"
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle(tr("media_viewer_title"))
        # Esc closes the viewer from anywhere, including the embedded video
        # page (its QWebEngineView owns the keyboard focus otherwise).
        esc = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape),
                              self)
        esc.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        esc.activated.connect(self.close)
        self.restore_geometry()
        if self._kind == "video":
            self._build_video()
        else:
            self._build_image()
        if self._fullscreen_hint:
            QtCore.QTimer.singleShot(0, self.showFullScreen)

    # ── Image ─────────────────────────────────────────────────────

    def _build_image(self) -> None:
        self._label = QtWidgets.QLabel()
        self._label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(1, 1)
        self._label.installEventFilter(self)
        self._zoom = 1.0
        self._pan_origin = None
        self._pan_scroll = (0, 0)
        scroll = _ImageScroll(self)
        # Keep the widget at the pixmap size so a zoomed-in image gets
        # scrollbars instead of being clipped to the viewport.
        scroll.setWidgetResizable(False)
        scroll.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(self._label)
        scroll.zoom_step.connect(self._on_zoom_step)
        self._scroll = scroll
        self.setCentralWidget(scroll)
        self._load_image()

    def _load_image(self) -> None:
        def _ready(path):
            self._pixmap = QtGui.QPixmap(path)
            # The window is usually not laid out yet when a cached original is
            # returned synchronously; defer the fit until after the event loop
            # has processed the show/layout (otherwise the viewport is degenerate
            # and the image only appears on the next resize).
            QtCore.QTimer.singleShot(0, self._fit_image)

        def _error(exc):
            self._label.setText(str(exc))

        self._service.ensure_original_async(self._url, _ready, _error)

    def _on_zoom_step(self, step: int) -> None:
        factor = 1.1 if step > 0 else (1.0 / 1.1)
        self._set_zoom(self._zoom * factor)

    def _set_zoom(self, zoom: float) -> None:
        zoom = max(0.1, min(8.0, float(zoom)))
        if abs(zoom - self._zoom) < 1e-6:
            return
        self._zoom = zoom
        self._fit_image()

    def _reset_zoom(self) -> None:
        self._set_zoom(1.0)

    def _fit_image(self) -> None:
        if self._pixmap.isNull():
            return
        target = self._scroll.viewport().size()
        if target.width() < 32 or target.height() < 32:
            return
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if pw <= 0 or ph <= 0:
            return
        fit = min(target.width() / pw, target.height() / ph)
        scale = max(0.001, fit * self._zoom)
        width = max(1, int(round(pw * scale)))
        height = max(1, int(round(ph * scale)))
        mode = (QtCore.Qt.TransformationMode.SmoothTransformation
                if scale < 1.0
                else QtCore.Qt.TransformationMode.FastTransformation)
        scaled = self._pixmap.scaled(
            width, height, QtCore.Qt.AspectRatioMode.KeepAspectRatio, mode)
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())
        if self._pan_origin is None:
            if (scaled.width() > target.width()
                    or scaled.height() > target.height()):
                self._label.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            else:
                self._label.unsetCursor()

    # ── Drag to pan ───────────────────────────────────────────────

    def _pannable(self) -> bool:
        """True when the scaled image overflows the viewport."""
        scroll = getattr(self, "_scroll", None)
        if scroll is None:
            return False
        return (scroll.horizontalScrollBar().maximum() > 0
                or scroll.verticalScrollBar().maximum() > 0)

    def _begin_pan(self, global_pos: QtCore.QPoint) -> None:
        if not self._pannable():
            self._pan_origin = None
            return
        self._pan_origin = global_pos
        self._pan_scroll = (
            self._scroll.horizontalScrollBar().value(),
            self._scroll.verticalScrollBar().value())
        self._label.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)

    def _pan_to(self, global_pos: QtCore.QPoint) -> None:
        if self._pan_origin is None:
            return
        delta = global_pos - self._pan_origin
        self._scroll.horizontalScrollBar().setValue(
            self._pan_scroll[0] - delta.x())
        self._scroll.verticalScrollBar().setValue(
            self._pan_scroll[1] - delta.y())

    def _end_pan(self) -> None:
        if self._pan_origin is None:
            return
        self._pan_origin = None
        if self._pannable():
            self._label.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        else:
            self._label.unsetCursor()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_label", None):
            etype = event.type()
            if etype == QtCore.QEvent.Type.MouseButtonDblClick:
                self._reset_zoom()
                return True
            if (etype == QtCore.QEvent.Type.MouseButtonPress
                    and event.button() == QtCore.Qt.MouseButton.LeftButton):
                self._begin_pan(event.globalPosition().toPoint())
                if self._pan_origin is not None:
                    return True
            elif (etype == QtCore.QEvent.Type.MouseMove
                    and self._pan_origin is not None):
                self._pan_to(event.globalPosition().toPoint())
                return True
            elif (etype == QtCore.QEvent.Type.MouseButtonRelease
                    and event.button() == QtCore.Qt.MouseButton.LeftButton
                    and self._pan_origin is not None):
                self._end_pan()
                return True
        return super().eventFilter(obj, event)

    # ── Geometry persistence ──────────────────────────────────────

    def restore_geometry(self) -> None:
        """Apply persisted window geometry/position (if any)."""
        cfg = self._geometry_cfg
        width, height, x, y, maximized = 900, 680, 0, 0, False
        if cfg:
            try:
                width = int(cfg.get("width", width) or width)
                height = int(cfg.get("height", height) or height)
                x = int(cfg.get("x", 0) or 0)
                y = int(cfg.get("y", 0) or 0)
            except (TypeError, ValueError):
                width, height, x, y = 900, 680, 0, 0
            maximized = bool(cfg.get("maximized"))
        self.resize(max(320, width), max(240, height))
        if x or y:
            self.move(x, y)
        if maximized:
            self.setWindowState(
                self.windowState()
                | QtCore.Qt.WindowState.WindowMaximized)

    def save_geometry(self) -> None:
        """Persist the current window geometry into the config section."""
        cfg = self._geometry_cfg
        if not cfg:
            return
        geo = (self.normalGeometry()
               if (self.isFullScreen() or self.isMaximized())
               else self.geometry())
        cfg["x"] = geo.x()
        cfg["y"] = geo.y()
        cfg["width"] = geo.width()
        cfg["height"] = geo.height()
        cfg["maximized"] = self.isMaximized()

    # ── Video ─────────────────────────────────────────────────────

    def _build_video(self) -> None:
        if not _HAS_WEBENGINE:
            label = QtWidgets.QLabel(tr("media_viewer_unsupported"))
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            self.setCentralWidget(label)
            return
        view = QtWebEngineWidgets.QWebEngineView(self)
        page = (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<style>html,body{margin:0;height:100%;background:#000;}'
            'video{width:100%;height:100%;}</style></head><body>'
            f'<video src="{html.escape(self._url, quote=True)}" '
            'controls autoplay></video></body></html>')
        view.setHtml(page, QtCore.QUrl("about:blank"))
        self.setCentralWidget(view)

    # ── Fullscreen ────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_F11:
            self._toggle_fullscreen()
            return
        if (event.key() == QtCore.Qt.Key.Key_0
                and event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            self._reset_zoom()
            return
        super().keyPressEvent(event)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._kind != "video":
            self._fit_image()

    def showEvent(self, event):
        super().showEvent(event)
        if self._kind != "video":
            QtCore.QTimer.singleShot(0, self._fit_image)

    def closeEvent(self, event):
        self.save_geometry()
        self.closed.emit()
        event.accept()
