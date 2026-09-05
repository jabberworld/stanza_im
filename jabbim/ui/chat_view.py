"""QWebEngineView-based chat display with Python ↔ JS bridge via QWebChannel."""
from __future__ import annotations

import json

from PyQt6 import QtCore, QtWidgets

try:
    from PyQt6 import QtWebChannel
    from PyQt6 import QtWebEngineWidgets
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

from jabbim.ui.chat_themes import ChatThemeFactory


if HAS_WEBENGINE:

    class _ChatBridge(QtCore.QObject):
        """Bridge exposed to JavaScript via QWebChannel."""

        link_clicked = QtCore.pyqtSignal(str)
        file_transfer_accept = QtCore.pyqtSignal(str)
        file_transfer_reject = QtCore.pyqtSignal(str)
        near_top = QtCore.pyqtSignal()
        scroll_fraction = QtCore.pyqtSignal(float)

        @QtCore.pyqtSlot(str)
        def on_link_clicked(self, url: str):
            self.link_clicked.emit(url)

        @QtCore.pyqtSlot(str)
        def on_ft_accept(self, sid: str):
            self.file_transfer_accept.emit(sid)

        @QtCore.pyqtSlot(str)
        def on_ft_reject(self, sid: str):
            self.file_transfer_reject.emit(sid)

        @QtCore.pyqtSlot()
        def on_near_top(self):
            self.near_top.emit()

        @QtCore.pyqtSlot(float)
        def on_scroll_fraction(self, fraction: float):
            self.scroll_fraction.emit(fraction)

    class ChatView(QtWebEngineWidgets.QWebEngineView):
        """Chat display widget backed by QWebEngineView."""

        link_clicked = QtCore.pyqtSignal(str)
        near_top = QtCore.pyqtSignal()

        def __init__(self, theme: ChatThemeFactory, parent=None):
            super().__init__(parent)
            self._theme = theme
            self._bridge = _ChatBridge()
            self._bridge.link_clicked.connect(self.link_clicked)
            self._bridge.near_top.connect(self.near_top)
            self._fraction = 1.0
            self._bridge.scroll_fraction.connect(self._set_fraction)

            channel = QtWebChannel.QWebChannel()
            channel.registerObject("bridge", self._bridge)
            self.page().setWebChannel(channel)

            # Messages added before the (async) page load completes would see
            # no #chat node; buffer them until the load has finished.
            self._pending: list[str] = []
            self._ready = False
            self.loadFinished.connect(self._on_load_finished)

            # Load the empty page
            self._load_empty()

        def _on_load_finished(self, ok: bool):
            self._ready = ok
            if ok and self._pending:
                pending, self._pending = self._pending, []
                for chunk in pending:
                    self._append_chunk(chunk)

        def _set_fraction(self, fraction: float):
            self._fraction = float(fraction) if fraction == fraction else 1.0

        def _append_chunk(self, html: str) -> None:
            safe = json.dumps(html)
            js = f"""
            var chat = document.getElementById('chat');
            if (chat) {{
                var div = document.createElement('div');
                div.innerHTML = {safe};
                chat.appendChild(div);
            }}
            window.scrollTo(0, document.body.scrollHeight);
            """
            self.page().runJavaScript(js)

        def _load_empty(self):
            self._pending.clear()
            self._ready = False
            html = self._theme.generate_empty_page()
            self.setHtml(html, QtCore.QUrl("about:blank"))

        def load_theme(self, variant: str = ""):
            if variant:
                self._theme.set_variant(variant)
            self._load_empty()

        def add_message(self, sender: str, body: str, timestamp: str,
                        direction: str, is_next: bool = False,
                        sender_color: str = "#000000",
                        user_icon_path: str = ""):
            """Add a message to the chat view."""
            html = self._theme.render_message(
                sender=sender, body=body, timestamp=timestamp,
                direction=direction, is_next=is_next,
                sender_color=sender_color, user_icon_path=user_icon_path,
            )
            if not self._ready:
                self._pending.append(html)
                return
            self._append_chunk(html)

        def add_status(self, text: str, timestamp: str):
            """Add a status/system message."""
            html = self._theme.render_status(text, timestamp)
            if not self._ready:
                self._pending.append(html)
                return
            self._append_chunk(html)

        def clear(self):
            """Clear all messages."""
            self._pending.clear()
            self._load_empty()

        def evaluate_js(self, code: str):
            self.page().runJavaScript(code)

        def scroll_to_bottom(self):
            self.evaluate_js("window.scrollTo(0, document.body.scrollHeight);")

        def scroll_fraction(self) -> float:
            return self._fraction

        def set_scroll_fraction(self, fraction: float):
            fraction = max(0.0, min(1.0, float(fraction)))
            js = (
                "requestAnimationFrame(function(){"
                "  document.body.scrollTop;"
                "  window.scrollTo(0, %r * Math.max(0, "
                "    document.body.scrollHeight - window.innerHeight));"
                "});" % fraction
            )
            self.evaluate_js(js)

else:
    # Fallback: QTextBrowser when QWebEngine is not available
    class ChatView(QtWidgets.QTextBrowser):
        """Fallback chat display using QTextBrowser (no CSS themes)."""

        link_clicked = QtCore.pyqtSignal(str)
        near_top = QtCore.pyqtSignal()

        def __init__(self, theme: ChatThemeFactory = None, parent=None):
            super().__init__(parent)
            self._theme = theme
            self.setOpenExternalLinks(False)
            self.anchorClicked.connect(
                lambda url: self.link_clicked.emit(url.toString()))
            self._near_top_hit = False
            self._fraction = 1.0

        def scrollContentsBy(self, dx: int, dy: int) -> None:
            super().scrollContentsBy(dx, dy)
            self._check_scroll()

        def _check_scroll(self):
            vbar = self.verticalScrollBar()
            span = max(1, vbar.maximum() - vbar.minimum())
            self._fraction = (vbar.value() - vbar.minimum()) / span
            offset = vbar.value() - vbar.minimum()
            if offset <= vbar.pageStep():
                if not self._near_top_hit:
                    self._near_top_hit = True
                    self.near_top.emit()
            else:
                self._near_top_hit = False

        def add_message(self, sender: str, body: str, timestamp: str,
                        direction: str, is_next: bool = False,
                        sender_color: str = "#000000",
                        user_icon_path: str = ""):
            if direction == "incoming":
                self.append(f"<b>{sender}</b> <i>({timestamp})</i>: {body}")
            else:
                self.append(f"<b style='color:#0066cc'>{sender}</b> <i>({timestamp})</i>: {body}")

        def add_status(self, text: str, timestamp: str):
            self.append(f"<i>({timestamp}) {text}</i>")

        def clear(self):
            super().clear()
            self._near_top_hit = False
            self._fraction = 1.0

        def evaluate_js(self, code: str):
            pass

        def load_theme(self, variant: str = ""):
            pass

        def scroll_to_bottom(self):
            vbar = self.verticalScrollBar()
            vbar.setValue(vbar.maximum())

        def scroll_fraction(self) -> float:
            return self._fraction

        def set_scroll_fraction(self, fraction: float):
            fraction = max(0.0, min(1.0, float(fraction)))
            vbar = self.verticalScrollBar()
            vbar.setValue(int(vbar.minimum()
                              + fraction * (vbar.maximum() - vbar.minimum())))
