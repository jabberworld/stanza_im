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
from stanza_im.include.constants import find_icon

try:
    from PyQt6 import QtWebChannel
    from PyQt6 import QtWebEngineCore
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


if _HAS_WEBENGINE:
    from stanza_im.ui import url_schemes
    url_schemes.ensure_registered()

    class _VideoBridge(QtCore.QObject):
        """Bridge for the video page: fullscreen + the overlay action buttons."""

        fullscreen_requested = QtCore.pyqtSignal()
        save_requested = QtCore.pyqtSignal()
        copy_requested = QtCore.pyqtSignal()
        share_requested = QtCore.pyqtSignal()

        @QtCore.pyqtSlot()
        def toggle_fullscreen(self):
            self.fullscreen_requested.emit()

        @QtCore.pyqtSlot()
        def save(self):
            self.save_requested.emit()

        @QtCore.pyqtSlot()
        def copy(self):
            self.copy_requested.emit()

        @QtCore.pyqtSlot()
        def share(self):
            self.share_requested.emit()

    class _VideoPage(QtWebEngineCore.QWebEnginePage):
        """Video page that turns a ``stanza:viewer-fs`` navigation into a
        fullscreen toggle (a fallback for the JS double-click handler)."""

        def __init__(self, view, on_fullscreen, parent=None):
            super().__init__(parent)
            self._view = view
            self._on_fullscreen = on_fullscreen

        def acceptNavigationRequest(self, url, _type, is_main_frame):
            # The scheme uses Qt's ``Path`` syntax, so ``path()`` may be empty
            # for ``stanza://viewer-fs``; check the whole string instead.
            text = url.toString()
            if str(url.scheme()) == "stanza" and "viewer-fs" in text:
                self._on_fullscreen()
                return False
            return super().acceptNavigationRequest(url, _type, is_main_frame)


class MediaViewer(QtWidgets.QMainWindow):
    """Non-modal viewer window for an image or video URL."""

    closed = QtCore.pyqtSignal()
    save_requested = QtCore.pyqtSignal(str)   # url
    copy_requested = QtCore.pyqtSignal(str)   # url
    share_requested = QtCore.pyqtSignal(str)  # url

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
        self._overlay = None
        if self._kind == "video":
            self._build_video()
        else:
            self._build_image()
        if self._fullscreen_hint:
            QtCore.QTimer.singleShot(0, self.showFullScreen)

    # ── Floating action overlay ───────────────────────────────────

    def _build_image_overlay(self) -> None:
        """Floating download/copy/share buttons over the image (no panel)."""
        overlay = QtWidgets.QFrame(self._scroll)
        overlay.setObjectName("viewer-overlay")
        overlay.setStyleSheet(
            "#viewer-overlay { background: rgba(20, 20, 20, 150); "
            "border-radius: 6px; }")
        row = QtWidgets.QHBoxLayout(overlay)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(2)
        for icon_name, label, signal in (
                ("arrow-down.svg", tr("media_save"), self.save_requested),
                ("copy.svg", tr("media_copy_link"), self.copy_requested),
                ("send-arrow.svg", tr("ctx_share"), self.share_requested)):
            btn = QtWidgets.QToolButton(overlay)
            btn.setIcon(QtGui.QIcon(find_icon(icon_name)))
            btn.setIconSize(QtCore.QSize(16, 16))
            btn.setAutoRaise(True)
            btn.setToolTip(label)
            btn.clicked.connect(
                lambda _checked=False, sig=signal: sig.emit(self._url))
            row.addWidget(btn)
        self._overlay = overlay
        self._place_overlay()

    def _place_overlay(self) -> None:
        overlay = getattr(self, "_overlay", None)
        scroll = getattr(self, "_scroll", None)
        if overlay is None or scroll is None:
            return
        overlay.adjustSize()
        margin = 10
        x = max(margin, scroll.width() - overlay.width() - margin)
        overlay.move(x, margin)
        overlay.raise_()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._place_overlay()

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
        self._build_image_overlay()
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
        if self._url.startswith("aesgcm://"):
            # Encrypted media must be decrypted to a local file first (the
            # browser cannot read the aesgcm: scheme).
            self._service.ensure_original_async(
                self._url,
                lambda path: self._render_video(
                    QtCore.QUrl.fromLocalFile(path).toString()),
                lambda _exc: self._render_video_unsupported())
            return
        self._render_video(self._url)

    def _render_video_unsupported(self) -> None:
        label = QtWidgets.QLabel(tr("media_viewer_unsupported"))
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.setCentralWidget(label)

    @staticmethod
    def _svg_data_uri(name: str) -> str:
        """Inline an action SVG as a data URI (for the video HTML overlay)."""
        path = find_icon(name)
        if not path:
            return ""
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            return ""
        import base64
        return ("data:image/svg+xml;base64,"
                + base64.b64encode(data).decode("ascii"))

    def _render_video(self, src: str) -> None:
        view = QtWebEngineWidgets.QWebEngineView(self)
        view.setPage(_VideoPage(view, self._toggle_fullscreen, parent=view))
        # The double-click asks Python for fullscreen through the WebChannel
        # (reliable); ``stanza:viewer-fs`` navigation stays a harmless fallback.
        bridge = _VideoBridge(self)
        bridge.fullscreen_requested.connect(self._toggle_fullscreen)
        bridge.save_requested.connect(
            lambda: self.save_requested.emit(self._url))
        bridge.copy_requested.connect(
            lambda: self.copy_requested.emit(self._url))
        bridge.share_requested.connect(
            lambda: self.share_requested.emit(self._url))
        channel = QtWebChannel.QWebChannel(self)
        channel.registerObject("bridge", bridge)
        view.page().setWebChannel(channel)
        from stanza_im.ui.chat_themes import _qwebchannel_js
        glue = _qwebchannel_js()
        save_icon = self._svg_data_uri("arrow-down.svg")
        copy_icon = self._svg_data_uri("copy.svg")
        share_icon = self._svg_data_uri("send-arrow.svg")
        acts = (
            '<div id="acts">'
            f'<button title="{html.escape(tr("media_save"), quote=True)}" '
            f'onclick="act(\'save\')"><img src="{save_icon}"></button>'
            f'<button title="{html.escape(tr("media_copy_link"), quote=True)}" '
            f'onclick="act(\'copy\')"><img src="{copy_icon}"></button>'
            f'<button title="{html.escape(tr("ctx_share"), quote=True)}" '
            f'onclick="act(\'share\')"><img src="{share_icon}"></button>'
            '</div>')
        page = (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<style>html,body{margin:0;height:100%;background:#000;}'
            'video{width:100%;height:100%;}'
            '#acts{position:absolute;top:10px;right:10px;display:flex;gap:2px;'
            'background:rgba(20,20,20,0.6);border-radius:6px;padding:4px;}'
            '#acts button{background:transparent;border:0;cursor:pointer;'
            'padding:2px;line-height:0;}'
            '#acts img{width:18px;height:18px;filter:invert(1);}'
            '</style></head><body>'
            f'<video src="{html.escape(src, quote=True)}" '
            'controls autoplay></video>'
            + acts +
            f'<script>{glue}</script>'
            '<script>'
            'function act(a){if(window.bridge&&window.bridge[a])'
            '{window.bridge[a]();}}'
            'var clickTimer=null;'
            'var clk=function(e){clearTimeout(clickTimer);'
            'clickTimer=setTimeout(function(){'
            'if(v.paused){v.play();}else{v.pause();}},250);};'
            'var dbl=function(e){e.preventDefault();clearTimeout(clickTimer);'
            'if(window.bridge&&window.bridge.toggle_fullscreen)'
            '{window.bridge.toggle_fullscreen();}'
            'else{var u=document.createElement("a");'
            'u.href="stanza:viewer-fs";u.click();}};'
            'var v=document.querySelector("video");'
            'if(v){v.addEventListener("click",clk);'
            'v.addEventListener("dblclick",dbl);}'
            'if(window.QWebChannel&&window.qt&&window.qt.webChannelTransport)'
            '{new QWebChannel(qt.webChannelTransport,function(ch){'
            'window.bridge=ch.objects.bridge;});}'
            '</script></body></html>')
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
