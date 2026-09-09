"""QWebEngineView-based chat display with Python ↔ JS bridge via QWebChannel."""
from __future__ import annotations

import json
import html
import logging

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    from PyQt6 import QtWebChannel
    from PyQt6 import QtWebEngineWidgets
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

from stanza_im.i18n import tr
from stanza_im.ui.chat_themes import ChatThemeFactory


logger = logging.getLogger(__name__)

TYPING_MARKER = "\u200bStanzaTyping\u200b"


class _JumpButtonMixin:
    """Floating 'jump to bottom' button for either chat backend."""

    def _create_jump_button(self):
        button = QtWidgets.QToolButton(self)
        button.setText("\u25bc")
        button.setAutoRaise(True)
        button.setToolTip(tr("chat_scroll_to_bottom"))
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(34, 34)
        button.setStyleSheet(
            "QToolButton {"
            "  background: rgba(60, 60, 60, 0.85);"
            "  color: white; border: none; border-radius: 17px;"
            "  font-size: 18px;"
            "}"
            "QToolButton:hover { background: rgba(40, 40, 40, 0.95); }")
        button.clicked.connect(self.scroll_to_bottom)
        button.hide()
        self._jump_button = button

    def _position_jump_button(self):
        button = getattr(self, "_jump_button", None)
        if button is None:
            return
        button.move(
            (self.width() - button.width()) // 2,
            self.height() - button.height() - 16)

    def _update_jump_button(self):
        at_bottom = self.scroll_fraction() >= 0.999
        show = (not at_bottom) and getattr(self, "_overflow", False)
        self._set_jump_visible(show)

    def _set_jump_visible(self, show: bool):
        button = getattr(self, "_jump_button", None)
        if button is None:
            return
        if button.isVisible() != show:
            button.setVisible(show)
        self._position_jump_button()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_jump_button()


if HAS_WEBENGINE:

    class _ChatBridge(QtCore.QObject):
        """Bridge exposed to JavaScript via QWebChannel."""

        link_clicked = QtCore.pyqtSignal(str)
        file_transfer_accept = QtCore.pyqtSignal(str)
        file_transfer_reject = QtCore.pyqtSignal(str)
        near_top = QtCore.pyqtSignal()
        scroll_fraction = QtCore.pyqtSignal(float)
        jump_clicked = QtCore.pyqtSignal()

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

        @QtCore.pyqtSlot()
        def on_jump_clicked(self):
            self.jump_clicked.emit()

    class ChatView(_JumpButtonMixin, QtWebEngineWidgets.QWebEngineView):
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
            self._overflow = False
            self._near_top_hit = False
            self._bridge.scroll_fraction.connect(self._set_fraction)
            self._bridge.jump_clicked.connect(self.scroll_to_bottom)

            channel = QtWebChannel.QWebChannel()
            channel.registerObject("bridge", self._bridge)
            self.page().setWebChannel(channel)

            try:
                self.page().javaScriptConsoleMessage.connect(
                    self._on_js_console)
            except (AttributeError, RuntimeError):
                pass

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
                self._install_jump_js()
                self._scroll_poll.start()
            else:
                self._scroll_poll.stop()
            if ok and self._pending:
                pending, self._pending = self._pending, []
                for chunk in pending:
                    self._append_chunk(chunk)

        def _on_js_console(self, level, message: str, line: int, source: str):
            logger.debug("chat JS [%s:%s] %s", source, line, message)

        _SCROLL_JS = """
        (function installStanzaScroll() {
            if (window.__stanzaScrollInstalled) return;
            if (!window.bridge) {
                if (window.QWebChannel && window.qt && qt.webChannelTransport) {
                    new QWebChannel(qt.webChannelTransport, function (channel) {
                        window.bridge = channel.objects.bridge;
                        installStanzaScroll();
                    });
                    return;
                }
                window.setTimeout(installStanzaScroll, 50);
                return;
            }
            window.__stanzaScrollInstalled = true;
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

        _JUMP_JS = """
        (function installStanzaJump() {
            if (document.getElementById('stanza-jump')) return;
            var d = document.createElement('div');
            d.id = 'stanza-jump';
            d.style.cssText =
                'position:fixed;bottom:16px;left:50%;transform:translateX(-50%);' +
                'width:34px;height:34px;line-height:34px;text-align:center;' +
                'border-radius:17px;background:rgba(60,60,60,0.85);' +
                'color:#fff;font-size:18px;cursor:pointer;z-index:9999;' +
                'display:none;user-select:none;';
            d.addEventListener('mouseenter', function () {
                d.style.background = 'rgba(40,40,40,0.95)';
            });
            d.addEventListener('mouseleave', function () {
                d.style.background = 'rgba(60,60,60,0.85)';
            });
            d.addEventListener('click', function () {
                window.scrollTo(0, document.body.scrollHeight);
                if (window.bridge && window.bridge.on_jump_clicked) {
                    window.bridge.on_jump_clicked();
                }
            });
            d.textContent = '\\u25bc';
            document.body.appendChild(d);
        })();
        """

        def _install_jump_js(self):
            self.page().runJavaScript(self._JUMP_JS)

        def _set_jump_visible(self, show: bool):
            self.evaluate_js(
                "var d = document.getElementById('stanza-jump');"
                "if (d) d.style.display = %s;"
                % ("'block'" if show else "'none'"))

        def _poll_scroll_position(self):
            if not self._ready:
                return
            self.page().runJavaScript(
                "var st = window.scrollY || document.documentElement.scrollTop "
                "|| document.body.scrollTop || 0; "
                "[st, window.innerHeight || 0, document.body.scrollHeight || 0]",
                self._on_scroll_position,
            )

        def _on_bridge_near_top(self):
            if self._near_top_hit:
                return
            self._near_top_hit = True
            self.near_top.emit()

        def _on_scroll_position(self, value):
            if not isinstance(value, list) or len(value) < 3:
                return
            try:
                offset = float(value[0])
                viewport = float(value[1])
                total = float(value[2])
            except (TypeError, ValueError):
                return
            self._overflow = total > viewport
            if self._overflow:
                span = max(1.0, total - viewport)
                self._fraction = min(1.0, offset / span)
            else:
                self._fraction = 1.0
            near_top = offset <= max(24.0, viewport)
            if near_top:
                if not self._near_top_hit:
                    self._near_top_hit = True
                    self.near_top.emit()
            else:
                self._near_top_hit = False
            self._update_jump_button()

        def _set_fraction(self, fraction: float):
            self._fraction = float(fraction) if fraction == fraction else 1.0
            self._update_jump_button()

        def _append_chunk(self, html: str) -> None:
            safe = json.dumps(html)
            do_scroll = 1 if self._fraction >= 0.999 else 0
            js = f"""
            var chat = document.getElementById('chat');
            if (chat) {{
                var div = document.createElement('div');
                div.innerHTML = {safe};
                var slot = document.getElementById('stanza-typing-slot');
                if (slot) {{ chat.insertBefore(div, slot); }}
                else {{ chat.appendChild(div); }}
            }}
            if ({do_scroll}) window.scrollTo(0, document.body.scrollHeight);
            """
            self.page().runJavaScript(js)

        def _load_empty(self):
            self._pending.clear()
            self._ready = False
            self._fraction = 1.0
            self._overflow = False
            self._update_jump_button()
            html = self._theme.generate_empty_page()
            self.setHtml(html, QtCore.QUrl("about:blank"))

        def load_theme(self, variant: str = ""):
            if variant:
                self._theme.set_variant(variant)
            self._load_empty()

        def add_message(self, sender: str, body: str, timestamp: str,
                        direction: str, is_next: bool = False,
                        sender_color: str = "#000000",
                        user_icon_path: str = "", message_id: str = "",
                        unstyled: bool = False):
            """Add a message to the chat view."""
            html = self._theme.render_message(
                sender=sender, body=body, timestamp=timestamp,
                direction=direction, is_next=is_next,
                sender_color=sender_color, user_icon_path=user_icon_path,
                unstyled=unstyled,
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
                unstyled=entry.get("unstyled", False),
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
            marker = (' data-stanza-id="' + html.escape(message_id, quote=True) + '"'
                      if message_id else "")
            return ('<div class="stanza-message"' + marker + ' data-stanza-sender="'
                    + html.escape(sender or "Me", quote=True) + '">'
                    + content + '</div>')

        def mark_message_delivered(self, message_id: str) -> None:
            safe = json.dumps(message_id)
            self.page().runJavaScript(f"""
            var node = document.querySelector('[data-stanza-id=' + JSON.stringify({safe}) + ']');
            var stamp = node && node.querySelector('.time_initial');
            if (stamp && !stamp.querySelector('.delivery')) {{
                var mark = document.createElement('span');
                mark.className = 'delivery'; mark.textContent = '✓'; stamp.appendChild(mark);
            }}
            """)

        def set_typing_indicator(self, text: str):
            safe = json.dumps(text or "")
            self.page().runJavaScript(f"""
            var slot = document.getElementById('stanza-typing-slot');
            if (slot) slot.textContent = {safe};
            """)

        def update_sender_avatar(self, sender: str, avatar_uri: str) -> None:
            safe_sender = json.dumps(sender or "Me")
            safe_uri = json.dumps(avatar_uri or "")
            self.page().runJavaScript(f"""
            var sender = {safe_sender};
            document.querySelectorAll(
                '[data-stanza-sender=' + JSON.stringify(sender) + '] img.avatar'
            ).forEach(function(img) {{ img.src = {safe_uri}; }});
            """)

        def clear(self):
            """Clear all messages."""
            self._pending.clear()
            self._fraction = 1.0
            self._overflow = False
            self._update_jump_button()
            self._load_empty()

        def evaluate_js(self, code: str):
            self.page().runJavaScript(code)

        def scroll_to_bottom(self):
            self._near_top_hit = False
            self._fraction = 1.0
            self._update_jump_button()
            self.evaluate_js("window.scrollTo(0, document.body.scrollHeight);")

        def scroll_fraction(self) -> float:
            return self._fraction

        def set_scroll_fraction(self, fraction: float):
            fraction = max(0.0, min(1.0, float(fraction)))
            self._near_top_hit = fraction <= 0.0
            self._fraction = fraction
            js = (
                "requestAnimationFrame(function(){"
                "  document.body.scrollTop;"
                "  window.scrollTo(0, %r * Math.max(0, "
                "    document.body.scrollHeight - window.innerHeight));"
                "});" % fraction
            )
            self.evaluate_js(js)
            self._update_jump_button()

else:
    # Fallback: QTextBrowser when QWebEngine is not available
    class ChatView(_JumpButtonMixin, QtWidgets.QTextBrowser):
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
            self._overflow = False
            self._create_jump_button()

        def scrollContentsBy(self, dx: int, dy: int) -> None:
            super().scrollContentsBy(dx, dy)
            self._check_scroll()

        def _check_scroll(self):
            vbar = self.verticalScrollBar()
            span = vbar.maximum() - vbar.minimum()
            self._overflow = span > 0
            if self._overflow:
                self._fraction = (vbar.value() - vbar.minimum()) / span
            else:
                self._fraction = 1.0
            offset = vbar.value() - vbar.minimum()
            if offset <= vbar.pageStep():
                if not self._near_top_hit:
                    self._near_top_hit = True
                    self.near_top.emit()
            else:
                self._near_top_hit = False
            self._update_jump_button()

        def _typing_block_start(self) -> int:
            """Position of the paragraph with our typing marker, if any."""
            block = self.document().begin()
            while block.isValid():
                if block.text().startswith(TYPING_MARKER):
                    return block.position()
                block = block.next()
            return -1

        def _append_before_typing(self, html: str) -> None:
            vbar = self.verticalScrollBar()
            was_at_bottom = self._fraction >= 0.999
            old_value = vbar.value()
            pos = self._typing_block_start()
            if pos < 0:
                self.append(html)
            else:
                cursor = QtGui.QTextCursor(self.document())
                cursor.setPosition(pos)
                cursor.insertHtml(html)
                cursor.insertBlock()
            if was_at_bottom:
                self._fraction = 1.0
                vbar.setValue(vbar.maximum())
            else:
                vbar.setValue(old_value)
            self._check_scroll()

        def add_message(self, sender: str, body: str, timestamp: str,
                        direction: str, is_next: bool = False,
                        sender_color: str = "#000000",
                        user_icon_path: str = "", message_id: str = "",
                        unstyled: bool = False):
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
                self.append(f"<i id='stanza-typing'>{TYPING_MARKER}_{html.escape(text)}</i>")

        def clear(self):
            super().clear()
            self._near_top_hit = False
            self._fraction = 1.0
            self._overflow = False
            self._update_jump_button()

        def evaluate_js(self, code: str):
            pass

        def load_theme(self, variant: str = ""):
            pass

        def scroll_to_bottom(self):
            self._fraction = 1.0
            vbar = self.verticalScrollBar()
            vbar.setValue(vbar.maximum())
            self._update_jump_button()

        def scroll_fraction(self) -> float:
            return self._fraction

        def set_scroll_fraction(self, fraction: float):
            fraction = max(0.0, min(1.0, float(fraction)))
            vbar = self.verticalScrollBar()
            vbar.setValue(int(vbar.minimum()
                              + fraction * (vbar.maximum() - vbar.minimum())))
            self._update_jump_button()
