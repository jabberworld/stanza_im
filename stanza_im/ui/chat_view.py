"""QWebEngineView-based chat display with Python ↔ JS bridge via QWebChannel."""
from __future__ import annotations

import json
import html
import logging
from urllib.parse import quote

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    from PyQt6 import QtWebChannel
    from PyQt6 import QtWebEngineCore
    from PyQt6 import QtWebEngineWidgets
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False


def _register_custom_url_schemes() -> None:
    """Register ``stanza``/``mam`` as application-handled URL schemes.

    Must run before the first QWebEngineProfile is used. Knowing the scheme
    stops Chromium from attempting (and erroring on) a real navigation when
    an anchor is clicked; the actual routing still happens in
    ``acceptNavigationRequest``.
    """
    try:
        from PyQt6.QtWebEngineCore import QWebEngineUrlScheme
        for name in (b"stanza", b"mam"):
            scheme = QWebEngineUrlScheme(name)
            scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
            scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme)
            QWebEngineUrlScheme.registerScheme(scheme)
        logger.info("Registered custom URL schemes stanza/mam")
    except Exception as exc:  # pragma: no cover - optional capability
        logger.warning("Could not register custom URL schemes: %s", exc)


logger = logging.getLogger(__name__)

from stanza_im.i18n import tr
from stanza_im.ui.chat_themes import ChatThemeFactory


if HAS_WEBENGINE:
    _register_custom_url_schemes()

TYPING_MARKER = "\u200bStanzaTyping\u200b"


def _compose_reply_target(reply_id: str, author: str, sender: str,
                          body: str) -> str:
    """Percent-encode a ``stanza:reply:id/author/sender/body`` target.

    Fields are URL-encoded (slashes too) and joined with literal ``/`` so
    ``ChatWidget._handle_reply_uri`` can split them back out.
    """
    def _q(value: str) -> str:
        return quote(value or "", safe="")

    return "/".join(_q(part)
                    for part in (reply_id, author, sender, body))


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
            "  background: #ececec;"
            "  color: #555; border: none; border-radius: 17px;"
            "  font-size: 18px;"
            "}"
            "QToolButton:hover { background: #d9d9d9; }")
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
        reply_requested = QtCore.pyqtSignal(str, str, str, str)  # reply_id, author, sender, snippet

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

        @QtCore.pyqtSlot(str, str, str, str)
        def on_reply(self, reply_id: str, author: str, sender: str, snippet: str):
            self.reply_requested.emit(reply_id, author, sender, snippet)

    class _StanzaPage(QtWebEngineCore.QWebEnginePage):
        """QWebEnginePage that routes clicks to Python via navigation.

        Anchors (links, mentions, reply, MAM) navigate to their ``href``;
        this page intercepts those requests and hands them to the view's
        ``link_clicked`` signal instead of loading them inside the chat.
        """

        def __init__(self, view, parent=None):
            super().__init__(parent)
            self._view = view

        def acceptNavigationRequest(self, url, _type, is_main_frame):
            return self._view._accept_navigation(url)

    class ChatView(_JumpButtonMixin, QtWebEngineWidgets.QWebEngineView):
        """Chat display widget backed by QWebEngineView."""

        link_clicked = QtCore.pyqtSignal(str)
        near_top = QtCore.pyqtSignal()
        reply_requested = QtCore.pyqtSignal(str, str, str, str)
        document_lost = QtCore.pyqtSignal()

        def __init__(self, theme: ChatThemeFactory, parent=None):
            super().__init__(parent)
            self._theme = theme
            self.mention_senders = False
            self._bridge = _ChatBridge()
            self._bridge.link_clicked.connect(self.link_clicked)
            self._bridge.near_top.connect(self._on_bridge_near_top)
            self._fraction = 1.0
            self._overflow = False
            self._near_top_hit = False
            self._bridge.scroll_fraction.connect(self._set_fraction)
            self._bridge.jump_clicked.connect(self.scroll_to_bottom)
            self._bridge.reply_requested.connect(self.reply_requested)

            self._page = _StanzaPage(self, parent=self)
            self.setPage(self._page)

            channel = QtWebChannel.QWebChannel()
            channel.registerObject("bridge", self._bridge)
            self._page.setWebChannel(channel)

            try:
                self._page.javaScriptConsoleMessage.connect(
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

        def _accept_navigation(self, url) -> bool:
            """Route a page navigation; return True to allow the load.

            Clicking an anchor (link/mention/reply/MAM) requests a navigation
            to its ``href``; we forward the URL to ``link_clicked`` and deny
            the load inside the chat.  Everything else (initial ``setHtml``,
            ``about:``/``data:``) is allowed so the page itself renders.
            """
            scheme = str(url.scheme()).lower()
            if scheme in ("stanza", "mam", "http", "https", "mailto"):
                self.link_clicked.emit(url.toString())
                return False
            return scheme in ("about", "data", "") or not url.isValid()

        def _on_load_finished(self, ok: bool):
            if ok:
                self._ready = True
                self._install_scroll_js()
                self._install_jump_js()
                self._install_action_js()
                self._scroll_poll.start()
            else:
                logger.warning("chat page load finished with error: %s",
                               self.url().toString())
                # A denied/blocked navigation (stanza:/mam:/mailto:) can emit
                # a spurious loadFinished(false) even though the current
                # document (#chat) is still alive. Probe the DOM instead of
                # wedging _ready=False forever.
                self._ready = False
                self._probe_chat_alive()
                return
            if self._pending:
                pending, self._pending = self._pending, []
                for chunk in pending:
                    self._append_chunk(chunk)

        def _probe_chat_alive(self):
            """Check whether the ``#chat`` node survived a rejected load."""
            def _handle(result):
                if result == "ok":
                    self._ready = True
                    if self._pending:
                        pending, self._pending = self._pending, []
                        for chunk in pending:
                            self._append_chunk(chunk)
                else:
                    logger.warning("chat document lost; reloading empty page")
                    self._load_empty()
                    self.document_lost.emit()
            try:
                self._page.runJavaScript(
                    "var n = document.getElementById('chat');"
                    " n ? 'ok' : 'missing'", _handle)
            except RuntimeError:
                self._load_empty()
                self.document_lost.emit()

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
                'border-radius:17px;background:#ececec;' +
                'color:#555;font-size:18px;cursor:pointer;z-index:9999;' +
                'display:none;user-select:none;';
            d.addEventListener('mouseenter', function () {
                d.style.background = '#d9d9d9';
            });
            d.addEventListener('mouseleave', function () {
                d.style.background = '#ececec';
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

        _ACTION_JS = """
        (function installStanzaActions() {
            if (window.__stanzaActionsInstalled) return;
            window.__stanzaActionsInstalled = true;

            var MENU_CLASS = 'stanza-menu';
            var EDIT_LABEL = %EDIT_LABEL%;
            var menu = null;

            function closeMenu() {
                if (menu && menu.parentNode) menu.parentNode.removeChild(menu);
                menu = null;
            }
            window.stanzaCloseMenu = closeMenu;

            function pad(n) { return (n < 10 ? '0' : '') + n; }

            function fmtCopyTime(raw) {
                var full = (raw || '').trim();
                var m = /^(\\d{4})-(\\d{2})-(\\d{2})T(\\d{2}):(\\d{2}):(\\d{2})/
                    .exec(full);
                if (m) return m[1] + '-' + m[2] + '-' + m[3] + ' '
                    + m[4] + ':' + m[5] + ':' + m[6];
                if (full && full.indexOf('-') < 0) {
                    var now = new Date();
                    return now.getFullYear() + '-' + pad(now.getMonth() + 1)
                        + '-' + pad(now.getDate()) + ' ' + full;
                }
                return full;
            }

            function composeCopyText(sender, timeRaw, body) {
                var t = fmtCopyTime(timeRaw);
                if (!t) {
                    var now = new Date();
                    t = now.getFullYear() + '-' + pad(now.getMonth() + 1)
                        + '-' + pad(now.getDate()) + ' '
                        + pad(now.getHours()) + ':' + pad(now.getMinutes())
                        + ':' + pad(now.getSeconds());
                }
                return '[' + t + '] ' + (sender || '') + ': ' + (body || '');
            }

            function copyText(text) {
                var ta = document.createElement('textarea');
                ta.value = text;
                ta.setAttribute('readonly', '');
                ta.style.position = 'fixed';
                ta.style.left = '-9999px';
                document.body.appendChild(ta);
                ta.select();
                var ok = false;
                try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
                document.body.removeChild(ta);
                return ok;
            }

            function openMenu(btn, x, y) {
                closeMenu();
                var wrap = btn.closest('.stanza-message');
                if (!wrap) return;
                var timeNode = wrap.querySelector('.time_initial, .timestamp');
                var bodyNode = wrap.querySelector(
                    '.message, .message_incoming, .message_outgoing, .next_message');
                var timeRaw = wrap.getAttribute('data-stanza-time')
                    || (timeNode ? timeNode.textContent.trim() : '');
                var body = bodyNode
                    ? (bodyNode.innerText || bodyNode.textContent).trim() : '';
                var sender = wrap.getAttribute('data-stanza-sender') || '';

                menu = document.createElement('div');
                menu.className = MENU_CLASS;
                menu.style.position = 'fixed';
                menu.style.top = (y + 2) + 'px';
                menu.style.left = (x + 2) + 'px';
                if (wrap.getAttribute('data-stanza-outgoing') === '1') {
                    var edit = document.createElement('button');
                    edit.type = 'button';
                    edit.textContent = EDIT_LABEL || 'Edit';
                    edit.addEventListener('click', function (ev) {
                        ev.stopPropagation();
                        var ref = wrap.getAttribute('data-stanza-id');
                        if (ref) {
                            window.location.href = 'stanza:edit:' + encodeURIComponent(ref);
                        }
                        closeMenu();
                    });
                    menu.appendChild(edit);
                }
                var item = document.createElement('button');
                item.type = 'button';
                item.textContent = btn.getAttribute('data-copy-label') || 'Copy';
                item.addEventListener('click', function (ev) {
                    ev.stopPropagation();
                    copyText(composeCopyText(sender, timeRaw, body));
                    closeMenu();
                });
                menu.appendChild(item);
                document.body.appendChild(menu);
                var rect = menu.getBoundingClientRect();
                var M = 4;
                if (rect.right > window.innerWidth - M) {
                    menu.style.left =
                        Math.max(M, window.innerWidth - rect.width - M) + 'px';
                }
                if (rect.bottom > window.innerHeight - M) {
                    menu.style.top = Math.max(M, y - rect.height - 2) + 'px';
                }
            }

            document.addEventListener('click', function (e) {
                var t = e.target;
                if (t && t.closest && t.closest('.' + MENU_CLASS)) return;
                closeMenu();
                var btn = t && t.closest
                    ? t.closest('.message_actions button') : null;
                if (!btn) return;
                e.preventDefault();
                if ((btn.getAttribute('data-action') || 'menu') === 'menu') {
                    openMenu(btn, e.clientX, e.clientY);
                }
            });
            document.addEventListener('keydown', function (e) {
                if (e.key === 'Escape') closeMenu();
            });
            window.addEventListener('scroll', function () { closeMenu(); }, true);
        })();
        """

        def _install_action_js(self):
            code = self._ACTION_JS.replace(
                "%EDIT_LABEL%", json.dumps(tr("chat_edit")))
            self.page().runJavaScript(code)

        def _close_stanza_menu(self):
            """Close the in-page message menu (e.g. focus leaves the view)."""
            try:
                self.evaluate_js(
                    "if (window.stanzaCloseMenu) window.stanzaCloseMenu();")
            except RuntimeError:
                pass

        def focusOutEvent(self, event):
            self._close_stanza_menu()
            super().focusOutEvent(event)

        def hideEvent(self, event):
            self._close_stanza_menu()
            super().hideEvent(event)

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

        def render_message_html(self, sender: str, body: str, timestamp: str,
                                direction: str, is_next: bool = False,
                                sender_color: str = "#000000",
                                user_icon_path: str = "", message_id: str = "",
                                unstyled: bool = False, raw_timestamp: str = "",
                                reply_able_id: str = "", reply_author: str = "",
                                reply_quote=None, outgoing: bool = False,
                                edited: bool = False) -> str:
            """Render (and mark) a single message's full HTML node."""
            phrase = self._action_phrase(body)
            if phrase is not None:
                html = self._theme.render_action(sender, phrase, timestamp)
            else:
                html = self._theme.render_message(
                    sender=sender, body=body, timestamp=timestamp,
                    direction=direction, is_next=is_next,
                    sender_color=sender_color, user_icon_path=user_icon_path,
                    unstyled=unstyled, mention=self.mention_senders,
                )
            if reply_quote is not None:
                ref_sender, ref_snippet = reply_quote
                html = self._theme.render_reply(ref_sender, ref_snippet) + html
            return self._mark_message(html, sender, message_id, raw_timestamp,
                                      reply_able_id, reply_author,
                                      reply_body=body, outgoing=outgoing,
                                      edited=edited)

        def add_message(self, sender: str, body: str, timestamp: str,
                        direction: str, is_next: bool = False,
                        sender_color: str = "#000000",
                        user_icon_path: str = "", message_id: str = "",
                        unstyled: bool = False, raw_timestamp: str = "",
                        reply_able_id: str = "", reply_author: str = "",
                        reply_quote=None, outgoing: bool = False,
                        edited: bool = False):
            """Add a message to the chat view.

            *reply_quote* is an optional ``(ref_sender, ref_snippet)`` shown
            as a XEP-0461 reply bar above the message.
            """
            html = self.render_message_html(
                sender, body, timestamp, direction, is_next,
                sender_color, user_icon_path, message_id, unstyled,
                raw_timestamp, reply_able_id, reply_author, reply_quote,
                outgoing, edited)
            if not self._ready:
                logger.debug("chat add_message buffered (page not ready, "
                             "pending=%d)", len(self._pending))
                self._pending.append(html)
                return
            self._append_chunk(html)

        def replace_message_ref(self, ref_id: str, html_node: str) -> None:
            """Replace an existing message node identified by *ref_id*."""
            try:
                self.page().runJavaScript(
                    "var ref = " + json.dumps(str(ref_id)) + ";"
                    "var n = document.querySelector('[data-stanza-id=' +"
                    " JSON.stringify(ref) + ']');"
                    "if (n) n.outerHTML = " + json.dumps(html_node) + ";")
            except RuntimeError:
                pass

        @staticmethod
        def _action_phrase(body: str):
            """Return the phrase for a XEP-0245 /me body, else None."""
            if isinstance(body, str) and body.startswith("/me "):
                return body[4:]
            return None

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

            def entry_html(entry: dict) -> str:
                body = entry.get("body", "")
                phrase = self._action_phrase(body)
                if phrase is not None:
                    html_msg = self._theme.render_action(
                        entry.get("sender", "Me"), phrase,
                        entry.get("timestamp", ""))
                else:
                    html_msg = self._theme.render_message(
                        sender=entry.get("sender", "Me"),
                        body=body,
                        timestamp=entry.get("timestamp", ""),
                        direction=entry.get("direction", "incoming"),
                        is_next=entry.get("is_next", False),
                        sender_color=entry.get("sender_color", "#000000"),
                        user_icon_path=entry.get("user_icon_path", ""),
                        unstyled=entry.get("unstyled", False),
                        mention=self.mention_senders,
                    )
                reply_quote = entry.get("reply_quote")
                if reply_quote is not None:
                    ref_sender, ref_snippet = reply_quote
                    html_msg = (self._theme.render_reply(ref_sender, ref_snippet)
                                + html_msg)
                return html_msg

            html = "".join(self._mark_message(
                entry_html(entry), entry.get("sender", "Me"),
                entry.get("message_id", ""),
                entry.get("raw_timestamp", ""),
                entry.get("origin_id", ""), entry.get("reply_author", ""),
                reply_body=entry.get("body", ""),
                outgoing=entry.get("outgoing", False),
                edited=entry.get("edited", False))
                for entry in messages)
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
        def _mark_message(content: str, sender: str, message_id: str = "",
                          raw_timestamp: str = "", reply_able_id: str = "",
                          reply_author: str = "", reply_body: str = "",
                          outgoing: bool = False, edited: bool = False) -> str:
            if edited:
                tag = ('<span class="stanza-edited" style="color:#999;'
                       'font-size:10px;vertical-align:super;cursor:help;'
                       'margin-right:2px;" title="%s">\u270e</span>'
                       % html.escape(tr("msg_edited_tooltip"), quote=True))
                content = tag + content
            if "%REPLY_TARGET%" in content:
                content = content.replace(
                    "%REPLY_TARGET%",
                    _compose_reply_target(reply_able_id, reply_author,
                                          sender, reply_body))
            node_id = message_id or reply_able_id
            marker = (' data-stanza-id="' + html.escape(node_id, quote=True) + '"'
                      if node_id else "")
            stamp = (' data-stanza-time="' + html.escape(raw_timestamp, quote=True) + '"'
                     if raw_timestamp else "")
            rid = ' data-reply-id="' + html.escape(reply_able_id, quote=True) + '"'
            rauthor = ' data-reply-author="' + html.escape(reply_author, quote=True) + '"'
            outward = ' data-stanza-outgoing="1"' if outgoing else ""
            edited_attr = ' data-edited="1"' if edited else ""
            return ('<div class="stanza-message"' + marker + stamp
                    + ' data-stanza-sender="'
                    + html.escape(sender or "Me", quote=True) + '"'
                    + rid + rauthor + outward + edited_attr
                    + '>' + content + '</div>')

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
        reply_requested = QtCore.pyqtSignal(str, str, str, str)
        document_lost = QtCore.pyqtSignal()

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
                        unstyled: bool = False, raw_timestamp: str = "",
                        reply_able_id: str = "", reply_author: str = "",
                        reply_quote=None, outgoing: bool = False,
                        edited: bool = False):
            edited_suffix = " " + tr("msg_edited_tooltip") if edited else ""
            reply_line = ""
            if reply_quote is not None:
                ref_sender, ref_snippet = reply_quote
                label = tr("reply_in_reply_to", sender=ref_sender or "…")
                if ref_snippet:
                    label += f": {html.escape(ref_snippet)}"
                reply_line = (f'<div class="stanza-reply" style="color:#888;'
                              f'font-size:11px">\u21b0 {html.escape(label)}</div>')
            phrase = (body[4:]
                      if isinstance(body, str) and body.startswith("/me ")
                      else None)
            if phrase is not None:
                self._append_before_typing(
                    reply_line +
                    f"<i>({timestamp}) * {sender or 'Me'} "
                    f"{phrase}{edited_suffix}</i>")
            elif direction == "incoming":
                self._append_before_typing(
                    reply_line +
                    f"<b>{sender}</b> <i>({timestamp})</i>: {body}{edited_suffix}")
            else:
                self._append_before_typing(
                    reply_line +
                    f"<b style='color:#0066cc'>{sender}</b> "
                    f"<i>({timestamp})</i>: {body}{edited_suffix}")

        def render_message_html(self, *args, **kwargs) -> str:
            return ""

        def replace_message_ref(self, ref_id: str, html_node: str) -> None:
            return

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

            def entry_html(entry: dict) -> str:
                body = entry.get("body", "")
                reply_line = ""
                reply_quote = entry.get("reply_quote")
                if reply_quote is not None:
                    ref_sender, ref_snippet = reply_quote
                    label = tr("reply_in_reply_to", sender=ref_sender or "…")
                    if ref_snippet:
                        label += f": {html.escape(ref_snippet)}"
                    reply_line = (
                        f'<div class="stanza-reply" style="color:#888;'
                        f'font-size:11px">\u21b0 {html.escape(label)}</div>')
                phrase = (body[4:]
                          if isinstance(body, str) and body.startswith("/me ")
                          else None)
                if phrase is not None:
                    return (reply_line +
                            f"<i>({entry.get('timestamp', '')}) * "
                            f"{entry.get('sender', 'Me')} {phrase}</i>")
                return (reply_line +
                        f"<b>{entry.get('sender', 'Me')}</b> "
                        f"<i>({entry.get('timestamp', '')})</i>: {body}")

            html = "".join(entry_html(entry) for entry in messages)
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
