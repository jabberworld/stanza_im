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
        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(self._label)
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

    def _fit_image(self) -> None:
        if self._pixmap.isNull():
            return
        target = self._scroll.viewport().size()
        if target.width() < 32 or target.height() < 32:
            return
        scaled = self._pixmap.scaled(
            target, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation)
        self._label.setPixmap(scaled)

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
