"""QWebEngineView-based chat display with Python ↔ JS bridge via QWebChannel."""
from __future__ import annotations

import json
import html

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    from PyQt6 import QtWebChannel
    from PyQt6 import QtWebEngineWidgets
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

from jabbim.ui.chat_themes import ChatThemeFactory


TYPING_MARKER = "\u200bJabbimTyping\u200b"


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
            self._bridge.near_top.connect(self._on_bridge_near_top)
            self._fraction = 1.0
            self._near_top_hit = False
            self._bridge.scroll_fraction.connect(self._set_fraction)

            channel = QtWebChannel.QWebChannel()
            channel.registerObject("bridge", self._bridge)
            self.page().setWebChannel(channel)

            # Messages added before the (async) page load completes would see
            # no #chat node; buffer them until the load has finished.
            self._pending: list[str] = []
            self._ready = False
            self.loadFinished.connect(self._on_load_finished)

            self._scroll_poll = QtCore.QTimer(self)
            self._scroll_poll.setInterval(250)
            self._scroll_poll.timeout.connect(self._poll_scroll_position)

            # Load the empty page
            self._load_empty()

        def _on_load_finished(self, ok: bool):
            self._ready = ok
            if ok:
                self._install_scroll_js()
                self._scroll_poll.start()
            else:
                self._scroll_poll.stop()
            if ok and self._pending:
                pending, self._pending = self._pending, []
                for chunk in pending:
                    self._append_chunk(chunk)

        _SCROLL_JS = """
        (function installJabbimScroll() {
            if (window.__jabbimScrollInstalled) return;
            if (!window.bridge) {
                if (window.QWebChannel && window.qt && qt.webChannelTransport) {
                    new QWebChannel(qt.webChannelTransport, function (channel) {
                        window.bridge = channel.objects.bridge;
                        installJabbimScroll();
                    });
                    return;
                }
                window.setTimeout(installJabbimScroll, 50);
                return;
            }
            window.__jabbimScrollInstalled = true;
            var last = 0;
            window.addEventListener('scroll', function () {
                var now = Date.now();
                if (now - last < 120) return;
                last = now;
                var st = window.scrollY || 0;
                var sh = document.body.scrollHeight;
                var ih = window.innerHeight;
                var max = Math.max(1, sh - ih);
                window.bridge.on_scroll_fraction(Math.min(1, st / max));
                if (st <= ih) window.bridge.on_near_top();
            });
        })();
        """

        def _install_scroll_js(self):
            self.page().runJavaScript(self._SCROLL_JS)

        def _poll_scroll_position(self):
            if not self._ready:
                return
            self.page().runJavaScript(
                "[window.scrollY || document.documentElement.scrollTop || "
                "document.body.scrollTop || 0, window.innerHeight || 0]",
                self._on_scroll_position,
            )

        def _on_bridge_near_top(self):
            if self._near_top_hit:
                return
            self._near_top_hit = True
            self.near_top.emit()

        def _on_scroll_position(self, value):
            if not isinstance(value, list) or len(value) < 2:
                return
            try:
                offset = float(value[0])
                viewport = float(value[1])
            except (TypeError, ValueError):
                return
            near_top = offset <= max(24.0, viewport)
            if near_top:
                if not self._near_top_hit:
                    self._near_top_hit = True
                    self.near_top.emit()
            else:
                self._near_top_hit = False

        def _set_fraction(self, fraction: float):
            self._fraction = float(fraction) if fraction == fraction else 1.0

        def _append_chunk(self, html: str) -> None:
            safe = json.dumps(html)
            js = f"""
            var chat = document.getElementById('chat');
            if (chat) {{
                var div = document.createElement('div');
                div.innerHTML = {safe};
                var slot = document.getElementById('jabbim-typing-slot');
                if (slot) {{ chat.insertBefore(div, slot); }}
                else {{ chat.appendChild(div); }}
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
                        user_icon_path: str = "", message_id: str = ""):
            """Add a message to the chat view."""
            html = self._theme.render_message(
                sender=sender, body=body, timestamp=timestamp,
                direction=direction, is_next=is_next,
                sender_color=sender_color, user_icon_path=user_icon_path,
            )
            html = self._mark_message(html, sender, message_id)
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

        def prepend_messages(self, messages: list[dict]) -> None:
            """Insert older messages before the current document."""
            if not messages:
                return
            html = "".join(self._mark_message(self._theme.render_message(
                sender=entry.get("sender", "Me"),
                body=entry.get("body", ""),
                timestamp=entry.get("timestamp", ""),
                direction=entry.get("direction", "incoming"),
                is_next=entry.get("is_next", False),
                sender_color="#000000",
                user_icon_path=entry.get("user_icon_path", ""),
            ), entry.get("sender", "Me")) for entry in messages)
            if not self._ready:
                self._pending.insert(0, html)
                return
            safe = json.dumps(html)
            self.page().runJavaScript(f"""
            (function() {{
                var chat = document.getElementById('chat');
                if (!chat) return;
                var anchor = document.elementFromPoint(
                    Math.max(4, window.innerWidth / 2),
                    Math.max(4, window.innerHeight / 2));
                var anchorTop = anchor ? anchor.getBoundingClientRect().top : 0;
                chat.insertAdjacentHTML('afterbegin', {safe});
                function restoreAnchor() {{
                    if (!anchor) return;
                    var delta = anchor.getBoundingClientRect().top - anchorTop;
                    if (Math.abs(delta) > 0.1) window.scrollBy(0, delta);
                }}
                // Images and WebEngine layout can change height after the
                // insertion; correct against the same visible node again.
                requestAnimationFrame(function() {{
                    restoreAnchor();
                    requestAnimationFrame(restoreAnchor);
                }});
                [50, 150, 300].forEach(function (delay) {{
                    window.setTimeout(restoreAnchor, delay);
                }});
            }})();
            """)

        @staticmethod
        def _mark_message(content: str, sender: str, message_id: str = "") -> str:
            marker = (' data-jabbim-id="' + html.escape(message_id, quote=True) + '"'
                      if message_id else "")
            return ('<div class="jabbim-message"' + marker + ' data-jabbim-sender="'
                    + html.escape(sender or "Me", quote=True) + '">'
                    + content + '</div>')

        def mark_message_delivered(self, message_id: str) -> None:
            safe = json.dumps(message_id)
            self.page().runJavaScript(f"""
            var node = document.querySelector('[data-jabbim-id=' + JSON.stringify({safe}) + ']');
            var stamp = node && node.querySelector('.time_initial');
            if (stamp && !stamp.querySelector('.delivery')) {{
                var mark = document.createElement('span');
                mark.className = 'delivery'; mark.textContent = '✓'; stamp.appendChild(mark);
            }}
            """)

        def set_typing_indicator(self, text: str):
            safe = json.dumps(text or "")
            self.page().runJavaScript(f"""
            var slot = document.getElementById('jabbim-typing-slot');
            if (slot) slot.textContent = {safe};
            """)

        def update_sender_avatar(self, sender: str, avatar_uri: str) -> None:
            safe_sender = json.dumps(sender or "Me")
            safe_uri = json.dumps(avatar_uri or "")
            self.page().runJavaScript(f"""
            var sender = {safe_sender};
            document.querySelectorAll(
                '[data-jabbim-sender=' + JSON.stringify(sender) + '] img.avatar'
            ).forEach(function(img) {{ img.src = {safe_uri}; }});
            """)

        def clear(self):
            """Clear all messages."""
            self._pending.clear()
            self._load_empty()

        def evaluate_js(self, code: str):
            self.page().runJavaScript(code)

        def scroll_to_bottom(self):
            self._near_top_hit = False
            self.evaluate_js("window.scrollTo(0, document.body.scrollHeight);")

        def scroll_fraction(self) -> float:
            return self._fraction

        def set_scroll_fraction(self, fraction: float):
            fraction = max(0.0, min(1.0, float(fraction)))
            self._near_top_hit = fraction <= 0.0
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

        def _typing_block_start(self) -> int:
            """Position of the paragraph with our typing marker, if any."""
            block = self.document().begin()
            while block.isValid():
                if block.text().startswith(TYPING_MARKER):
                    return block.position()
                block = block.next()
            return -1

        def _append_before_typing(self, html: str) -> None:
            pos = self._typing_block_start()
            if pos < 0:
                self.append(html)
                return
            cursor = QtGui.QTextCursor(self.document())
            cursor.setPosition(pos)
            cursor.insertHtml(html)
            cursor.insertBlock()

        def add_message(self, sender: str, body: str, timestamp: str,
                        direction: str, is_next: bool = False,
                        sender_color: str = "#000000",
                        user_icon_path: str = "", message_id: str = ""):
            if direction == "incoming":
                self._append_before_typing(
                    f"<b>{sender}</b> <i>({timestamp})</i>: {body}")
            else:
                self._append_before_typing(
                    f"<b style='color:#0066cc'>{sender}</b> <i>({timestamp})</i>: {body}")

        def add_status(self, text: str, timestamp: str):
            self._append_before_typing(f"<i>({timestamp}) {text}</i>")

        def prepend_messages(self, messages: list[dict]) -> None:
            """Insert older messages while keeping the visible content fixed."""
            if not messages:
                return
            bar = self.verticalScrollBar()
            old_max = bar.maximum()
            old_value = bar.value()
            cursor = self.textCursor()
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.Start)
            self.setTextCursor(cursor)
            html = "".join(
                f"<b>{entry.get('sender', 'Me')}</b> "
                f"<i>({entry.get('timestamp', '')})</i>: "
                f"{entry.get('body', '')}"
                for entry in messages
            )
            cursor.insertHtml(html)
            QtCore.QCoreApplication.processEvents()
            bar.setValue(old_value + bar.maximum() - old_max)

        def update_sender_avatar(self, sender: str, avatar_uri: str) -> None:
            pass

        def mark_message_delivered(self, message_id: str) -> None:
            pass

        def set_typing_indicator(self, text: str):
            pos = self._typing_block_start()
            if pos >= 0:
                cursor = QtGui.QTextCursor(self.document())
                cursor.setPosition(pos)
                cursor.select(QtGui.QTextCursor.SelectionType.BlockUnderCursor)
                cursor.removeSelectedText()
            if text:
                self.append(f"<i id='jabbim-typing'>{TYPING_MARKER}_{html.escape(text)}</i>")

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
