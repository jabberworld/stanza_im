"""QWebEngineView-based chat display with Python ↔ JS bridge via QWebChannel."""
from __future__ import annotations

import json
import html
import logging
from urllib.parse import quote, unquote

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    from PyQt6 import QtWebChannel
    from PyQt6 import QtWebEngineCore
    from PyQt6 import QtWebEngineWidgets
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False


def _register_custom_url_schemes() -> None:
    """Register ``stanza``/``mam``/``xmpp`` as application-handled URL schemes.

    Must run before the first QWebEngineProfile is used. Knowing the scheme
    stops Chromium from attempting (and erroring on) a real navigation when
    an anchor is clicked; the actual routing still happens in
    ``acceptNavigationRequest``.  The schemes use the ``Path`` syntax (Qt's
    default): everything after ``scheme:`` is preserved verbatim, so Chromium
    keeps the opaque ``stanza:view:…``/``xmpp:…`` anchors intact — the media
    context menu reads that raw link back through ``linkUrl()``.
    """
    try:
        from PyQt6.QtWebEngineCore import QWebEngineUrlScheme
        for name in (b"stanza", b"mam", b"xmpp"):
            scheme = QWebEngineUrlScheme(name)
            scheme.setSyntax(QWebEngineUrlScheme.Syntax.Path)
            scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme)
            QWebEngineUrlScheme.registerScheme(scheme)
        logger.info("Registered custom URL schemes stanza/mam/xmpp")
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


def clamp_zoom(factor: float) -> float:
    """Clamp a text-scale factor to the allowed 50-300 % range."""
    try:
        return max(0.5, min(3.0, float(factor)))
    except (TypeError, ValueError):
        return 1.0


def share_payload(link_url: str, media_url: str, media_kind: str,
                  selected_text: str) -> str:
    """The content a chat context menu should offer to share, or "".

    Priority: a media URL, then a link URL, then the selected text.  Only
    ``http(s)`` URLs are shareable — internal ``stanza:``/``data:`` links are
    not.
    """
    def _web(url: str) -> bool:
        return (url or "").lower().startswith(("http://", "https://"))

    if media_kind and _web(media_url):
        return media_url
    if _web(link_url):
        return link_url
    return (selected_text or "").strip()


def _media_type_name(media_type) -> str:
    """Map QWebEngineContextMenuRequest.MediaType to image/audio/video.

    PyQt6 exposes the members prefixed (``MediaTypeImage``); the unprefixed
    spellings are tried too for other bindings.
    """
    if not HAS_WEBENGINE or media_type is None:
        return ""
    from PyQt6 import QtWebEngineCore
    enum = getattr(QtWebEngineCore.QWebEngineContextMenuRequest,
                   "MediaType", None)
    if enum is None:
        return ""
    for member, label in (("MediaTypeImage", "image"),
                          ("MediaTypeAudio", "audio"),
                          ("MediaTypeVideo", "video"),
                          ("Image", "image"), ("Audio", "audio"),
                          ("Video", "video")):
        try:
            if media_type == getattr(enum, member):
                return label
        except Exception:
            pass
    return ""


def _stanza_media_link(link_url: str):
    """``"stanza:view:<kind>/<urlencoded>"`` -> ``(kind, url)`` or ``None``.

    The chat's previews wrap media in such a link and the original URL lives in
    its href; the DOM ``src`` of an image is only a data-URI thumbnail.
    """
    if not link_url.startswith("stanza:view:"):
        return None
    kind, sep, encoded = link_url[len("stanza:view:"):].partition("/")
    if not sep or kind not in ("image", "audio", "video"):
        return None
    return kind, unquote(encoded)


def context_menu_values(data) -> tuple[str, str, str, str]:
    """``(media_url, media_kind, link_url, selected_text)``.

    *data* is the ``QWebEngineContextMenuRequest`` from
    ``QWebEngineView.lastContextMenuRequest()`` (or ``None``); the helper also
    works with a plain test double exposing the same methods.
    """
    if data is None:
        return "", "", "", ""
    media_url = ""
    media = data.mediaUrl()
    if media is not None and not media.isEmpty():
        media_url = media.toString()
    kind = _media_type_name(data.mediaType())
    link_url = data.linkUrl().toString() if data.linkUrl() else ""
    selected = data.selectedText() or ""
    stanza_media = _stanza_media_link(link_url)
    if stanza_media is not None:
        link_kind, original = stanza_media
        kind = kind or link_kind
        if not media_url.lower().startswith(("http://", "https://")):
            # An embedded image reports its data-URI thumbnail as the media
            # URL; the shareable original is in the stanza:view: link.
            media_url = original
    return media_url, kind, link_url, selected


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
        button.clicked.connect(self._on_jump_clicked)
        button.hide()
        self._jump_button = button
        self._init_jump_state()

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

    # ── New-message counter + two-step jump ───────────────────────

    def _init_jump_state(self):
        self._new_count = 0
        self._first_unread_id = ""
        self._jumped_once = False
        self._update_jump_label()

    def is_scrolled_up(self) -> bool:
        """True while the view overflows and is not at the very bottom."""
        return (bool(getattr(self, "_overflow", False))
                and self.scroll_fraction() < 0.999)

    def note_new_message(self, target_id: str = "") -> None:
        """Count a message that arrived while the user was scrolled up."""
        self._new_count += 1
        if not self._first_unread_id and target_id:
            self._first_unread_id = target_id
        self._update_jump_label()

    def _reset_unread_indicator(self) -> None:
        if not (getattr(self, "_new_count", 0)
                or getattr(self, "_first_unread_id", "")
                or getattr(self, "_jumped_once", False)):
            return
        self._new_count = 0
        self._first_unread_id = ""
        self._jumped_once = False
        self._update_jump_label()

    @staticmethod
    def _jump_label(count: int) -> str:
        if count <= 0:
            return "\u25bc"
        return "\u25bc " + ("99+" if count > 99 else str(count))

    def _on_jump_clicked(self) -> None:
        if (self._new_count > 0 and self._first_unread_id
                and not self._jumped_once and self._jump_has_target()):
            self._jumped_once = True
            self.scroll_to_message(self._first_unread_id, highlight=False)
        else:
            self._reset_unread_indicator()
            self.scroll_to_bottom()

    def _jump_has_target(self) -> bool:
        """Whether the backend can scroll to a specific message."""
        return False

    def _update_jump_label(self):
        button = getattr(self, "_jump_button", None)
        if button is None:
            return
        text = self._jump_label(getattr(self, "_new_count", 0))
        if button.text() != text:
            button.setText(text)
            button.setFixedSize(max(34, button.sizeHint().width() + 8), 34)
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
        zoom_changed = QtCore.pyqtSignal(float)
        media_save_requested = QtCore.pyqtSignal(str)       # url
        media_copy_requested = QtCore.pyqtSignal(str)       # url
        media_open_requested = QtCore.pyqtSignal(str, str)  # url, kind
        share_requested = QtCore.pyqtSignal(str)            # shared content

        _LOAD_RETRY_LIMIT = 5
        _MAX_DOM_MESSAGES = 500   # oldest message nodes trimmed past this

        def __init__(self, theme: ChatThemeFactory, parent=None):
            super().__init__(parent)
            self._theme = theme
            self.mention_senders = False
            self.highlight_nick = ""
            self._zoom = 1.0
            self._last_edit_ref = ""
            self._last_reply_ref = ""
            self._last_mention_ref = ""
            self._last_xmpp_ref = ""
            self._last_jump_ref = ""
            self._bridge = _ChatBridge()
            self._bridge.link_clicked.connect(self.link_clicked)
            self._bridge.near_top.connect(self._on_bridge_near_top)
            self._fraction = 1.0
            self._overflow = False
            self._near_top_hit = False
            self._bridge.scroll_fraction.connect(self._set_fraction)
            self._bridge.jump_clicked.connect(self._on_jump_clicked)
            self._bridge.reply_requested.connect(self.reply_requested)

            self._page = _StanzaPage(self, parent=self)
            self.setPage(self._page)
            self._init_jump_state()

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
            self._load_failures = 0
            self._loading = False
            self.loadFinished.connect(self._on_load_finished)
            self.loadStarted.connect(self._on_load_started)
            # Chromium handles Ctrl+wheel itself once the page owns focus, so
            # our wheelEvent is never called; the scroll poll below also
            # relays scroll/pinch zoom by comparing QWebEngineView.zoomFactor()
            # against the tracked value (Qt 6 has no zoomFactorChanged signal).

            self._scroll_poll = QtCore.QTimer(self)
            self._scroll_poll.setInterval(250)
            self._scroll_poll.timeout.connect(self._poll_scroll_position)

            # Load the empty page
            self._load_empty()

        def shutdown(self) -> None:
            """Stop the scroll poll and drop buffers on tab teardown.

            Called from ``ChatWidget.detach`` right before the tab widget is
            ``deleteLater``-ed; the page itself is freed with the view.
            """
            try:
                self._scroll_poll.stop()
            except RuntimeError:
                pass
            self._ready = False
            self._pending.clear()

        def wheelEvent(self, event):
            """Ctrl+wheel resizes the chat text instead of scrolling."""
            if (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier
                    and event.angleDelta().y()):
                step = 0.1 if event.angleDelta().y() > 0 else -0.1
                self.set_chat_zoom(clamp_zoom(self._zoom + step))
                self.zoom_changed.emit(self._zoom)
                event.accept()
                return
            super().wheelEvent(event)

        def _on_load_started(self):
            self._loading = True

        def set_chat_zoom(self, factor: float):
            """Set a persisted text-scale factor (applied to the whole page)."""
            self._zoom = clamp_zoom(factor)
            self.setZoomFactor(self._zoom)

        def set_media_thumbnail(self, url: str, data_uri: str) -> None:
            """Swap a loading placeholder for the ready thumbnail data-URI."""
            if not self._ready or not url:
                return
            safe_url = json.dumps(url)
            safe_uri = json.dumps(data_uri or "")
            self.page().runJavaScript(f"""
            (function() {{
                var target = {safe_url};
                document.querySelectorAll('img.stanza-media-thumb').forEach(
                    function (img) {{
                        if (img.getAttribute('data-media-url') !== target) return;
                        img.src = {safe_uri};
                        var parent = img.parentNode;
                        if (parent && parent.classList) {{
                            parent.classList.remove('stanza-media-loading');
                        }}
                    }});
            }})();
            """)

        def contextMenuEvent(self, event):
            """Show our own chat context menu (never the engine's)."""
            data = None
            try:
                data = self.lastContextMenuRequest()
            except Exception:
                logger.debug("lastContextMenuRequest failed", exc_info=True)
            media_url, kind, link_url, selected = context_menu_values(data)
            content = share_payload(link_url, media_url, kind, selected)
            if media_url and kind:
                self._show_media_menu(event, media_url, kind, content)
                return
            self._show_context_menu(event, link_url, selected, content)

        def _show_media_menu(self, event, url: str, kind: str,
                             share_content: str = "") -> None:
            menu = QtWidgets.QMenu(self)
            menu.addAction(tr("media_copy_link"),
                           lambda: self.media_copy_requested.emit(url))
            menu.addAction(tr("media_save"),
                           lambda: self.media_save_requested.emit(url))
            if share_content:
                menu.addAction(
                    tr("ctx_share"),
                    lambda c=share_content: self.share_requested.emit(c))
            if kind in ("audio", "video"):
                menu.addSeparator()
                menu.addAction(
                    tr("media_open_viewer"),
                    lambda u=url, k=kind: self.media_open_requested.emit(u, k))
                if kind == "video":
                    menu.addAction(
                        tr("media_fullscreen"),
                        lambda u=url: self.media_open_requested.emit(
                            u, "video_fs"))
            menu.exec(event.globalPos())

        def _show_context_menu(self, event, link_url: str, selected: str,
                               share_content: str) -> None:
            """The standard chat menu: share / copy link / open / select all."""
            menu = QtWidgets.QMenu(self)
            web_link = link_url.lower().startswith(("http://", "https://"))
            if share_content:
                menu.addAction(
                    tr("ctx_share"),
                    lambda c=share_content: self.share_requested.emit(c))
            if web_link:
                menu.addAction(
                    tr("media_copy_link"),
                    lambda u=link_url: QtWidgets.QApplication.clipboard().setText(u))
                menu.addAction(
                    tr("ctx_open_link"),
                    lambda u=link_url: QtGui.QDesktopServices.openUrl(
                        QtCore.QUrl(u)))
            elif selected:
                menu.addAction(
                    tr("ctx_copy"),
                    lambda t=selected: QtWidgets.QApplication.clipboard().setText(t))
            menu.addSeparator()
            menu.addAction(tr("ctx_select_all"), self._select_all)
            menu.exec(event.globalPos())

        def _select_all(self) -> None:
            try:
                self.triggerPageAction(
                    QtWebEngineCore.QWebEnginePage.WebAction.SelectAll)
            except Exception:
                logger.debug("select all failed", exc_info=True)

        def _accept_navigation(self, url) -> bool:
            """Route a page navigation; return True to allow the load.

            Clicking an anchor (link/mention/MAM) requests a navigation to its
            ``href``; we forward the URL to ``link_clicked`` and deny the load
            inside the chat.  ``about:``/``data:`` are the mechanism
            ``setHtml`` uses to render the page itself (the initial load and
            reloads, with an ``about:blank`` base), so both must stay allowed —
            denying ``data:`` would wedge the page in a reload loop.
            """
            scheme = str(url.scheme()).lower()
            if scheme in ("stanza", "mam", "xmpp", "http", "https", "mailto"):
                self._schedule_content_probe()
                self.link_clicked.emit(url.toString())
                return False
            return scheme in ("about", "data", "") or not url.isValid()

        def _schedule_content_probe(self) -> None:
            """Schedule a check that the conversation survived the click.

            A denied/blocked link can, in rare cases, end with the page being
            reloaded to an empty document that still contains ``#chat``, which
            the loadFinished probe would miss.  If messages vanished, restore
            through ``document_lost``.
            """
            self._pre_click_messages = None  # unknown until measured
            def _count(result):
                if result is None:
                    return
                try:
                    self._pre_click_messages = int(result)
                except (TypeError, ValueError):
                    self._pre_click_messages = None
            try:
                self._page.runJavaScript(
                    "document.querySelectorAll('#chat .stanza-message').length",
                    _count)
            except RuntimeError:
                return
            QtCore.QTimer.singleShot(
                400, self._verify_after_click)

        def _verify_after_click(self) -> None:
            def _check(result):
                try:
                    after = int(result) if result is not None else 0
                except (TypeError, ValueError):
                    return
                pre = getattr(self, "_pre_click_messages", None)
                if after == 0 and (pre is None or pre > 0):
                    logger.warning(
                        "chat contents vanished after a click; restoring")
                    self.document_lost.emit()
            try:
                self._page.runJavaScript(
                    "document.querySelectorAll('#chat .stanza-message').length",
                    _check)
            except RuntimeError:
                pass

        def _on_load_finished(self, ok: bool):
            self._loading = False
            if ok:
                self._load_failures = 0
                self._ready = True
                self.setZoomFactor(self._zoom)
                self._install_scroll_js()
                self._install_jump_js()
                self._install_action_js()
                self._scroll_poll.start()
            else:
                self._load_failures += 1
                logger.warning("chat page load finished with error: %s",
                               self.url().toString())
                if self._load_failures >= self._LOAD_RETRY_LIMIT:
                    logger.error(
                        "chat page failed to load %d times in a row; "
                        "stopping reload attempts", self._load_failures)
                    self._ready = False
                    self._pending.clear()
                    return
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
                elif self._load_failures >= self._LOAD_RETRY_LIMIT:
                    logger.error("chat document repeatedly lost (%d); "
                                 "stopping reload attempts",
                                 self._load_failures)
                    self._pending.clear()
                else:
                    logger.warning("chat document lost; reloading empty page")
                    self._load_empty()
                    self.document_lost.emit()
            try:
                self._page.runJavaScript(
                    "var n = document.getElementById('chat');"
                    " n ? 'ok' : 'missing'", _handle)
            except RuntimeError:
                if self._load_failures >= self._LOAD_RETRY_LIMIT:
                    logger.error("chat page unavailable; stopping reloads")
                    self._pending.clear()
                else:
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
                    window.__stanzaJumpPress = 1;
                    if (window.bridge && window.bridge.on_jump_clicked) {
                        window.bridge.on_jump_clicked();
                        window.__stanzaJumpPress = 0;
                    }
                });
            d.textContent = '\\u25bc';
            window.__stanzaJumpPress = 0;
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
            var FORWARD_LABEL = %FORWARD_LABEL%;
            var menu = null;

            function closeMenu() {
                if (menu && menu.parentNode) menu.parentNode.removeChild(menu);
                menu = null;
            }
            window.stanzaCloseMenu = closeMenu;
            window.__stanzaReplyRef = '';
            window.__stanzaMediaRef = '';
window.__stanzaMentionRef = '';
            window.__stanzaGeoRef = '';
            window.__stanzaForwardRef = '';
            window.__stanzaJumpRef = '';

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
                        // No navigation: leave the reference for the scroll
                        // poll, which delivers it to Python without touching
                        // the chat document.
                        window.__stanzaEditRef =
                            wrap.getAttribute('data-stanza-id') || '';
                        window.setTimeout(closeMenu, 0);
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
                var fwd = document.createElement('button');
                fwd.type = 'button';
                fwd.textContent = FORWARD_LABEL || 'Forward';
                fwd.addEventListener('click', function (ev) {
                    ev.stopPropagation();
                    // Never navigate: leave the whole message for the scroll
                    // poll, which delivers it to Python as a link_clicked.
                    var content = body;
                    if (!content) {
                        var media = wrap.querySelector(
                            'a.stanza-media, a.stanza-media-open');
                        if (media) {
                            content = media.getAttribute('data-media-url')
                                || media.getAttribute('href') || '';
                        }
                    }
                    if (content) {
                        window.__stanzaForwardRef = 'stanza:forward:'
                            + encodeURIComponent(
                                composeCopyText(sender, timeRaw, content));
                    }
                    window.setTimeout(closeMenu, 0);
                });
                menu.appendChild(fwd);
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
                // Reply-quote jump: never navigate. Scroll locally when the
                // target is already rendered; otherwise hand the stanza:jump:
                // target to the scroll poll so Python can load it from the
                // local archive and scroll afterwards.
                var jump = t && t.closest
                    ? t.closest('a.stanza-reply-jump') : null;
                if (jump) {
                    e.preventDefault();
                    var jhref = jump.getAttribute('href') || '';
                    var jid = jhref.indexOf('stanza:jump:') === 0
                        ? decodeURIComponent(jhref.slice('stanza:jump:'.length))
                        : '';
                    var jnodes = document.querySelectorAll('.stanza-message');
                    for (var k = 0; k < jnodes.length; k++) {
                        if (jnodes[k].getAttribute('data-stanza-id') === jid
                            || jnodes[k].getAttribute('data-reply-id') === jid) {
                            jnodes[k].scrollIntoView({block: 'center'});
                            jnodes[k].classList.remove('stanza-jump-highlight');
                            void jnodes[k].offsetWidth;
                            jnodes[k].classList.add('stanza-jump-highlight');
                            setTimeout((function (n) {
                                return function () {
                                    n.classList.remove('stanza-jump-highlight');
                                };
                            })(jnodes[k]), 1600);
                            return;
                        }
                    }
                    window.__stanzaJumpRef = jhref;
                    return;
                }
                // Media preview/player links must never navigate: a custom
                // stanza: navigation can otherwise replace the chat document
                // (and the image click would not reach Python).  Leave the
                // href for the always-running scroll poll, which delivers it
                // as a link_clicked (same relay as reply/edit).
                var media = t && t.closest
                    ? t.closest('a.stanza-media, a.stanza-media-open') : null;
                if (media) {
                    e.preventDefault();
                    window.__stanzaMediaRef =
                        media.getAttribute('href') || '';
                    return;
                }
                // Reply button: never navigate. Leave the stanza:reply target
                // for the always-running scroll poll, which delivers it to
                // Python (exactly like the edit reference), so the chat
                // document is never reset by the click.
                var rbtn = t && t.closest
                    ? t.closest('a.action-reply') : null;
                if (rbtn) {
                    e.preventDefault();
                    window.__stanzaReplyRef =
                        rbtn.getAttribute('href') || '';
                    return;
                }
                // MUC mention: never navigate. A stanza: navigation can
                // otherwise replace the chat document and blank the whole
                // conversation.  Leave the href for the always-running scroll
                // poll, which delivers it to Python like the reply/edit refs.
                var m = t && t.closest ? t.closest('a.mention') : null;
                if (m) {
                    e.preventDefault();
                    window.__stanzaMentionRef =
                        m.getAttribute('href') || '';
                    return;
                }
                var g = t && t.closest ? t.closest('a.stanza-geo') : null;
                if (g) {
                    // geo: link — hand the stanza:geo: target to the scroll
                    // poll exactly like reply/edit/mention, so the chat
                    // document is never reset by the click.
                    e.preventDefault();
                    window.__stanzaGeoRef =
                        g.getAttribute('href') || '';
                    return;
                }
                // xmpp: URI — never navigate. Leaving the href alone would
                // request a navigation that can replace the chat document and
                // blank the conversation (the same defence as geo/reply/edit).
                // Hand it to the scroll poll, which delivers it to Python as
                // a link_clicked without touching the document.
                var x = t && t.closest ? t.closest('a[href^="xmpp:"]') : null;
                if (x) {
                    e.preventDefault();
                    window.__stanzaXmppRef =
                        x.getAttribute('href') || '';
                    return;
                }
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
            code = (self._ACTION_JS
                    .replace("%EDIT_LABEL%", json.dumps(tr("chat_edit")))
                    .replace("%FORWARD_LABEL%", json.dumps(tr("chat_forward"))))
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

        def _jump_has_target(self) -> bool:
            return True

        def _update_jump_label(self):
            count = getattr(self, "_new_count", 0)
            text = json.dumps(self._jump_label(count))
            self.evaluate_js(
                "var d = document.getElementById('stanza-jump');"
                "if (d) { d.textContent = %s; d.style.width = %s;"
                " d.style.padding = %s; }"
                % (text, "'auto'" if count else "'34px'",
                   "'0 10px'" if count else "'0'"))

        def _poll_scroll_position(self):
            if not self._ready:
                return
            # Detect Chromium-initiated zoom (Ctrl+wheel, pinch, Ctrl+/-) that
            # bypasses our wheelEvent.  Qt 6 removed the zoomFactorChanged
            # signal, so poll the property instead.
            if not self._loading:
                zoom = clamp_zoom(self.zoomFactor())
                if abs(zoom - self._zoom) > 1e-9:
                    self._zoom = zoom
                    self.zoom_changed.emit(zoom)
            self.page().runJavaScript(
                "var st = window.scrollY || document.documentElement.scrollTop "
                "|| document.body.scrollTop || 0; "
                "[st, window.innerHeight || 0, document.body.scrollHeight || 0,"
                "window.__stanzaEditRef || '', window.__stanzaReplyRef || '',"
                " window.__stanzaMediaRef || '',"
                " window.__stanzaMentionRef || '', window.__stanzaGeoRef || '',"
                " window.__stanzaXmppRef || '', window.__stanzaForwardRef || '',"
                " window.__stanzaJumpRef || '', window.__stanzaJumpPress ? 1 : 0]",
                self._on_scroll_position,
            )

        def _clear_edit_request(self):
            try:
                self._page.runJavaScript("window.__stanzaEditRef = '';")
            except RuntimeError:
                pass

        def _clear_reply_request(self):
            try:
                self._page.runJavaScript("window.__stanzaReplyRef = '';")
            except RuntimeError:
                pass

        def _clear_media_request(self):
            try:
                self._page.runJavaScript("window.__stanzaMediaRef = '';")
            except RuntimeError:
                pass

        def _clear_mention_request(self):
            try:
                self._page.runJavaScript("window.__stanzaMentionRef = '';")
            except RuntimeError:
                pass

        def _clear_geo_request(self):
            try:
                self._page.runJavaScript("window.__stanzaGeoRef = '';")
            except RuntimeError:
                pass

        def _clear_xmpp_request(self):
            try:
                self._page.runJavaScript("window.__stanzaXmppRef = '';")
            except RuntimeError:
                pass

        def _clear_forward_request(self):
            try:
                self._page.runJavaScript("window.__stanzaForwardRef = '';")
            except RuntimeError:
                pass

        def _clear_jump_request(self):
            try:
                self._page.runJavaScript("window.__stanzaJumpRef = '';")
            except RuntimeError:
                pass

        def _on_bridge_near_top(self):
            if self._near_top_hit:
                return
            self._near_top_hit = True
            self.near_top.emit()

        def _on_scroll_position(self, value):
            if not isinstance(value, list) or len(value) < 3:
                return
            if len(value) > 3 and isinstance(value[3], str) and value[3]:
                self._clear_edit_request()
                requested = value[3]
                if requested != getattr(self, "_last_edit_ref", ""):
                    self._last_edit_ref = requested
                    self.link_clicked.emit("stanza:edit:" + requested)
            else:
                self._last_edit_ref = ""
            if len(value) > 4 and isinstance(value[4], str) and value[4]:
                self._clear_reply_request()
                requested = value[4]
                if requested != getattr(self, "_last_reply_ref", ""):
                    self._last_reply_ref = requested
                    self.link_clicked.emit(requested)
            else:
                self._last_reply_ref = ""
            if len(value) > 5 and isinstance(value[5], str) and value[5]:
                self._clear_media_request()
                requested = value[5]
                if requested != getattr(self, "_last_media_ref", ""):
                    self._last_media_ref = requested
                    self.link_clicked.emit(requested)
            else:
                self._last_media_ref = ""
            if len(value) > 6 and isinstance(value[6], str) and value[6]:
                self._clear_mention_request()
                requested = value[6]
                if requested != getattr(self, "_last_mention_ref", ""):
                    self._last_mention_ref = requested
                    self.link_clicked.emit(requested)
            else:
                self._last_mention_ref = ""
            if len(value) > 7 and isinstance(value[7], str) and value[7]:
                self._clear_geo_request()
                requested = value[7]
                if requested != getattr(self, "_last_geo_ref", ""):
                    self._last_geo_ref = requested
                    self.link_clicked.emit(requested)
            else:
                self._last_geo_ref = ""
            if len(value) > 8 and isinstance(value[8], str) and value[8]:
                self._clear_xmpp_request()
                requested = value[8]
                if requested != getattr(self, "_last_xmpp_ref", ""):
                    self._last_xmpp_ref = requested
                    self.link_clicked.emit(requested)
            else:
                self._last_xmpp_ref = ""
            if len(value) > 9 and isinstance(value[9], str) and value[9]:
                self._clear_forward_request()
                requested = value[9]
                if requested != getattr(self, "_last_forward_ref", ""):
                    self._last_forward_ref = requested
                    self.link_clicked.emit(requested)
            else:
                self._last_forward_ref = ""
            if len(value) > 10 and isinstance(value[10], str) and value[10]:
                self._clear_jump_request()
                requested = value[10]
                if requested != getattr(self, "_last_jump_ref", ""):
                    self._last_jump_ref = requested
                    self.link_clicked.emit(requested)
            else:
                self._last_jump_ref = ""
            if len(value) > 11 and value[11]:
                self.evaluate_js("window.__stanzaJumpPress = 0;")
                self._on_jump_clicked()
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
            if self._fraction >= 0.999:
                self._reset_unread_indicator()
            self._update_jump_button()

        def _set_fraction(self, fraction: float):
            self._fraction = float(fraction) if fraction == fraction else 1.0
            if self._fraction >= 0.999:
                self._reset_unread_indicator()
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
                var nodes = chat.querySelectorAll('.stanza-message');
                for (var i = 0; i < nodes.length - {self._MAX_DOM_MESSAGES}; i++) {{
                    var wrap = nodes[i];
                    while (wrap.parentNode && wrap.parentNode !== chat) {{
                        wrap = wrap.parentNode;
                    }}
                    if (wrap.parentNode === chat) {{ chat.removeChild(wrap); }}
                }}
            }}
            if ({do_scroll}) window.scrollTo(0, document.body.scrollHeight);
            """
            self.page().runJavaScript(js)

        def _load_empty(self):
            self._pending.clear()
            self._ready = False
            self._fraction = 1.0
            self._overflow = False
            self._reset_unread_indicator()
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
                                edited: bool = False, hats=None) -> str:
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
                    edited=edited, highlight_nick=self.highlight_nick,
                    geo_ref=reply_able_id or "", hats=hats)
            if reply_quote is not None:
                ref_sender, ref_snippet, ref_target = reply_quote
                html = self._theme.render_reply(
                    ref_sender, ref_snippet, ref_target) + html
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
                        edited: bool = False, hats=None):
            """Add a message to the chat view.

            *reply_quote* is an optional ``(ref_sender, ref_snippet)`` shown
            as a XEP-0461 reply bar above the message.
            """
            html = self.render_message_html(
                sender, body, timestamp, direction, is_next,
                sender_color, user_icon_path, message_id, unstyled,
                raw_timestamp, reply_able_id, reply_author, reply_quote,
                outgoing, edited, hats)
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

        def prepend_messages(self, messages: list[dict],
                             keep_position: bool = True) -> None:
            """Insert older messages before the current document.

            With *keep_position* the reading anchor is preserved (normal
            "load earlier" paging); a reply-quote jump passes ``False`` so the
            subsequent scroll to the target is not reverted.
            """
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
                        edited=entry.get("edited", False),
                        highlight_nick=self.highlight_nick,
                        hats=entry.get("hats"),
                    )
                reply_quote = entry.get("reply_quote")
                if reply_quote is not None:
                    ref_sender, ref_snippet, ref_target = reply_quote
                    html_msg = (self._theme.render_reply(
                        ref_sender, ref_snippet, ref_target) + html_msg)
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
            keep = 1 if keep_position else 0
            self.page().runJavaScript(f"""
            (function() {{
                var chat = document.getElementById('chat');
                if (!chat) return;
                var keep = {keep};
                var anchor = keep ? document.elementFromPoint(
                    Math.max(4, window.innerWidth / 2),
                    Math.max(4, window.innerHeight / 2)) : null;
                var anchorTop = anchor ? anchor.getBoundingClientRect().top : 0;
                chat.insertAdjacentHTML('afterbegin', {safe});
                if (!keep) return;
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

        def scroll_to_message(self, message_id: str,
                              highlight: bool = True) -> None:
            """Scroll the ``data-stanza-id`` node into view (and flash it)."""
            safe = json.dumps(message_id or "")
            flash = 1 if highlight else 0
            self.page().runJavaScript(f"""
            (function() {{
                var id = {safe};
                if (!id) return;
                var flash = {flash};
                var nodes = document.querySelectorAll('.stanza-message');
                for (var i = 0; i < nodes.length; i++) {{
                    if (nodes[i].getAttribute('data-stanza-id') === id
                        || nodes[i].getAttribute('data-reply-id') === id) {{
                        nodes[i].scrollIntoView({{block: 'center'}});
                        if (!flash) return;
                        nodes[i].classList.remove('stanza-jump-highlight');
                        void nodes[i].offsetWidth;
                        nodes[i].classList.add('stanza-jump-highlight');
                        setTimeout(function() {{
                            nodes[i].classList.remove('stanza-jump-highlight');
                        }}, 1600);
                        return;
                    }}
                }}
            }})();
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
            self._reset_unread_indicator()
            self._update_jump_button()
            self._load_empty()

        def evaluate_js(self, code: str):
            self.page().runJavaScript(code)

        def scroll_to_bottom(self):
            self._near_top_hit = False
            self._fraction = 1.0
            self._reset_unread_indicator()
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
        zoom_changed = QtCore.pyqtSignal(float)
        media_save_requested = QtCore.pyqtSignal(str)       # url
        media_copy_requested = QtCore.pyqtSignal(str)       # url
        media_open_requested = QtCore.pyqtSignal(str, str)  # url, kind
        share_requested = QtCore.pyqtSignal(str)            # shared content

        def __init__(self, theme: ChatThemeFactory = None, parent=None):
            super().__init__(parent)
            self._theme = theme
            self.highlight_nick = ""
            self._zoom = 1.0
            self.setOpenExternalLinks(False)
            self.anchorClicked.connect(
                lambda url: self.link_clicked.emit(url.toString()))
            self._near_top_hit = False
            self._fraction = 1.0
            self._overflow = False
            self._create_jump_button()

        def wheelEvent(self, event):
            """Ctrl+wheel resizes the chat text instead of scrolling."""
            if (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier
                    and event.angleDelta().y()):
                step = 0.1 if event.angleDelta().y() > 0 else -0.1
                self.set_chat_zoom(clamp_zoom(self._zoom + step))
                self.zoom_changed.emit(self._zoom)
                event.accept()
                return
            super().wheelEvent(event)

        def contextMenuEvent(self, event):
            """Standard menu plus a Share action for a link or selected text."""
            menu = self.createStandardContextMenu()
            pos = self.viewport().mapFromGlobal(event.globalPos())
            anchor = self.anchorAt(pos)
            selected = self.textCursor().selectedText().replace("\u2029", "\n")
            content = share_payload(anchor, "", "", selected)
            if content:
                action = QtGui.QAction(tr("ctx_share"), menu)
                action.triggered.connect(
                    lambda _checked=False, payload=content:
                    self.share_requested.emit(payload))
                actions = menu.actions()
                if actions:
                    menu.insertAction(actions[0], action)
                    menu.insertSeparator(actions[0])
                else:
                    menu.addAction(action)
            menu.exec(event.globalPos())

        def set_chat_zoom(self, factor: float):
            """Set a persisted text-scale factor as the document font size."""
            factor = clamp_zoom(factor)
            if factor != self._zoom:
                base = self.font().pointSizeF() or 10.0
                font = QtGui.QFont(self.font())
                font.setPointSizeF(base * factor)
                self.document().setDefaultFont(font)
                self._zoom = factor

        def set_media_thumbnail(self, url: str, data_uri: str) -> None:
            """No-op: media previews are disabled without QWebEngine."""
            return

        def scroll_to_message(self, message_id: str,
                              highlight: bool = True) -> None:
            """No-op: the QTextBrowser fallback has no per-message nodes."""
            return

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
            if self._fraction >= 0.999:
                self._reset_unread_indicator()
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
                        edited: bool = False, hats=None):
            edited_suffix = " " + tr("msg_edited_tooltip") if edited else ""
            hats_suffix = self._hats_text(hats)
            reply_line = ""
            if reply_quote is not None:
                ref_sender, ref_snippet = reply_quote[0], reply_quote[1]
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
                    f"<b>{sender}</b>{hats_suffix} <i>({timestamp})</i>: "
                    f"{self._escape_body_for_fallback(body)}{edited_suffix}")
            else:
                self._append_before_typing(
                    reply_line +
                    f"<b style='color:#0066cc'>{sender}</b>{hats_suffix} "
                    f"<i>({timestamp})</i>: "
                    f"{self._escape_body_for_fallback(body)}{edited_suffix}")

        @staticmethod
        def _hats_text(hats) -> str:
            titles = [str((h or {}).get("title") or (h or {}).get("uri") or "")
                      for h in (hats or [])]
            titles = [t for t in titles if t]
            return " [" + ", ".join(titles) + "]" if titles else ""

        @staticmethod
        def _escape_body_for_fallback(body) -> str:
            """Escape the fallback body and linkify geo: coordinates."""
            from stanza_im.include.geo import escape_body_with_geo
            return escape_body_with_geo(body)

        def render_message_html(self, *args, **kwargs) -> str:
            return ""

        def replace_message_ref(self, ref_id: str, html_node: str) -> None:
            return

        def add_status(self, text: str, timestamp: str):
            self._append_before_typing(f"<i>({timestamp}) {text}</i>")

        def prepend_messages(self, messages: list[dict],
                             keep_position: bool = True) -> None:
            """Insert older messages above the current document (fallback)."""
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
                    ref_sender, ref_snippet = reply_quote[0], reply_quote[1]
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
                        f"<b>{entry.get('sender', 'Me')}</b>"
                        f"{self._hats_text(entry.get('hats'))} "
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
            self._reset_unread_indicator()
            self._update_jump_button()

        def evaluate_js(self, code: str):
            pass

        def load_theme(self, variant: str = ""):
            pass

        def scroll_to_bottom(self):
            self._fraction = 1.0
            vbar = self.verticalScrollBar()
            vbar.setValue(vbar.maximum())
            self._reset_unread_indicator()
            self._update_jump_button()

        def scroll_fraction(self) -> float:
            return self._fraction

        def set_scroll_fraction(self, fraction: float):
            fraction = max(0.0, min(1.0, float(fraction)))
            vbar = self.verticalScrollBar()
            vbar.setValue(int(vbar.minimum()
                              + fraction * (vbar.maximum() - vbar.minimum())))
            self._update_jump_button()
