"""Chat theme engine — generates HTML from Adium-style chat skin templates."""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import quote

from PyQt6 import QtCore

from stanza_im.include.constants import CHATSKINS_DIR
from stanza_im.include.emoticons import smile_to_html
from stanza_im.include.utils import escape_html, restore_url_tokens
from stanza_im.i18n import tr

_logger = logging.getLogger(__name__)


def _qwebchannel_js() -> str:
    """Return the ``qwebchannel.js`` glue ($undefined if unavailable).

    Prefers Qt's bundled resource (``:/qtwebchannel/qwebchannel.js``) and
    falls back to the copy shipped in ``resources/qwebchannel.js`` so the
    ``window.bridge`` channel works even when the resource is missing.
    """
    try:
        fh = QtCore.QFile(":/qtwebchannel/qwebchannel.js")
        if fh.open(QtCore.QIODevice.OpenModeFlag.ReadOnly):
            try:
                js = bytes(fh.readAll()).decode("utf-8", "replace")
                if js.strip():
                    return js
            finally:
                fh.close()
    except ImportError:
        pass
    bundled = os.path.join(CHATSKINS_DIR, os.pardir, "qwebchannel.js")
    if os.path.isfile(bundled):
        with open(bundled, "r", encoding="utf-8") as fh:
            js = fh.read()
            if js.strip():
                return js
    _logger.warning("qwebchannel.js not found (Qt resource or bundled copy)")
    return ""


def _webchannel_script() -> str:
    """Inline QWebChannel glue so Python↔JS bridge works across pages.

    Reads Qt's bundled ``qwebchannel.js`` (or the packaged copy in
    ``resources/``) and installs ``window.bridge`` plus a global click
    handler that routes link clicks and XEP-0461 reply buttons through
    ``stanzaSend``.  ``stanzaSend`` calls the QWebChannel bridge and always
    mirrors the payload over ``console.log`` so the C++ side receives it
    even when the WebChannel transport is unavailable (Python dedupes).
    Returns '' only when the script itself is unavailable.
    """
    js = _qwebchannel_js()
    if not js:
        return ""
    return f"""<script>
{js}
window.__stanzaSeq = 0;
window.stanzaSend = function (uri) {{
    var sid = 's' + (++window.__stanzaSeq) + '-' + Date.now();
    var payload = sid + '|' + uri;
    try {{
        if (window.bridge && window.bridge.on_link_clicked) {{
            window.bridge.on_link_clicked(payload);
        }}
    }} catch (err) {{ /* fall through to the console channel */ }}
    try {{
        console.log('stanza-click|' + payload);
    }} catch (err) {{}}
}};
document.addEventListener('DOMContentLoaded', function () {{
    new QWebChannel(qt.webChannelTransport, function (channel) {{
        window.bridge = channel.objects.bridge;
        if (window.__stanzaScrollInstalled) return;
        window.__stanzaScrollInstalled = true;
        var last = 0;
        function onScroll() {{
            var now = Date.now();
            if (now - last < 120) return;
            last = now;
            var st = window.scrollY || 0;
            var sh = document.body.scrollHeight;
            var ih = window.innerHeight;
            var max = Math.max(1, sh - ih);
            window.bridge.on_scroll_fraction(Math.min(1, st / max));
            if (st <= ih) window.bridge.on_near_top();
        }}
        window.addEventListener('scroll', onScroll);
    }});
}});
document.addEventListener('click', function (e) {{
    var el = e.target && e.target.closest ? e.target.closest('a') : null;
    if (el && el.getAttribute('href')) {{
        e.preventDefault();
        // Use the raw attribute, not el.href: the browser resolves/normalises
        // custom schemes (stanza:…) and the resolved property breaks routing.
        window.stanzaSend(el.getAttribute('href'));
        return;
    }}
    var reply = e.target && e.target.closest
        ? e.target.closest('.message_actions button[data-action="reply"]')
        : null;
    if (reply) {{
        e.preventDefault();
        var wrap = reply.closest('.stanza-message');
        var replyId = wrap ? (wrap.getAttribute('data-reply-id')
                              || wrap.getAttribute('data-stanza-id') || '') : '';
        var bodyNode = wrap ? wrap.querySelector(
            '.message, .message_incoming, .message_outgoing, .next_message')
            : null;
        var body = bodyNode
            ? (bodyNode.innerText || bodyNode.textContent).trim() : '';
        var sender = wrap ? (wrap.getAttribute('data-stanza-sender') || '') : '';
        var author = wrap ? (wrap.getAttribute('data-reply-author') || '') : '';
        window.stanzaSend('stanza:reply:' + encodeURIComponent(replyId) + '/'
            + encodeURIComponent(author) + '/' + encodeURIComponent(sender)
            + '/' + encodeURIComponent(body));
    }}
}});
</script>
"""


class ChatThemeFactory:
    """Loads Adium-style chat skin templates and generates HTML for messages."""

    def __init__(self, skin_dir: str | None = None,
                 emoticon_skin: str = "default/smileys.cfg"):
        self._skin_dir = skin_dir or os.path.join(CHATSKINS_DIR, "minimal-mod")
        self._templates: dict[str, str] = {}
        self._css: str = ""
        self._header: str = ""
        self._footer: str = ""
        self._status_template: str = ""
        self._variants: dict[str, str] = {}
        self._current_variant_css: str = ""
        self._emoticon_skin = emoticon_skin
        self._message_styling = True
        self._load_templates()

    def _load_templates(self) -> None:
        base = self._skin_dir

        def _read(rel):
            path = os.path.join(base, rel)
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            return ""

        self._templates["incoming"] = _read("Incoming/Content.html")
        self._templates["incoming_next"] = _read("Incoming/NextContent.html")
        self._templates["outgoing"] = _read("Outgoing/Content.html")
        self._templates["outgoing_next"] = _read("Outgoing/NextContent.html")
        self._css = _read("main.css")
        self._header = _read("Header.html")
        self._footer = _read("Footer.html")
        self._status_template = _read("Status.html")

        # Load CSS variants
        variants_dir = os.path.join(base, "Variants")
        if os.path.isdir(variants_dir):
            for fn in os.listdir(variants_dir):
                if fn.endswith(".css"):
                    name = fn[:-4]
                    with open(os.path.join(variants_dir, fn), "r", encoding="utf-8") as f:
                        self._variants[name] = f.read()

    def variant_names(self) -> list[str]:
        return sorted(self._variants.keys())

    def set_variant(self, name: str) -> None:
        self._current_variant_css = self._variants.get(name, "")

    def set_emoticon_skin(self, skin: str) -> None:
        self._emoticon_skin = skin

    def set_message_styling(self, enabled: bool) -> None:
        """Enable/disable XEP-0393 message styling in rendered bodies."""
        self._message_styling = bool(enabled)

    def _transform_body(self, body: str, styled: bool = True) -> str:
        """Turn a plain-text body into message HTML.

        With styling enabled the XEP-0393 parser runs first and delegates
        plain-text regions to :meth:`_body_fragment`, so URLs/emoticons still
        apply inside styled spans but never inside ``<code>``/``<pre>``.
        """
        if self._message_styling and styled:
            from stanza_im.xmpp import message_styling
            try:
                return message_styling.render(body, self._body_fragment)
            except Exception:
                pass
        return self._body_fragment(body)

    def _body_fragment(self, raw: str) -> str:
        """Escape plain text, then add clickable links and emoticons.

        Order matters: URLs are replaced with tokens first so emoticon codes
        (e.g. ``:/`` inside ``https://``) can't corrupt them, emoticons are
        substituted in the remaining text, then the <a> links are restored.
        """
        escaped = escape_html(raw)
        escaped = escaped.replace("\r\n", "\n").replace("\r", "\n")
        escaped = escaped.replace("\n", "<br>")
        tokenised, anchors = self._tokenize_urls(escaped)
        emotified = smile_to_html(tokenised, self._emoticon_skin)
        return restore_url_tokens(emotified, anchors)

    @staticmethod
    def _tokenize_urls(text: str) -> tuple[str, list[str]]:
        from stanza_im.include.utils import tokenize_urls
        return tokenize_urls(text)

    def render_message(self, sender: str, body: str, timestamp: str,
                       direction: str, is_next: bool = False,
                       sender_color: str = "#000000",
                       user_icon_path: str = "", unstyled: bool = False,
                       mention: bool = False) -> str:
        """Render a single message to HTML using the skin template.

        With *mention* the incoming sender name is wrapped in a clickable
        ``stanza:mention:`` link (MUC nickname mentions).
        """
        key = direction
        if is_next:
            key += "_next"
        template = self._templates.get(key, self._templates.get(direction, "{body}"))
        body_html = self._transform_body(body, styled=not unstyled)

        sender_html = escape_html(sender)
        if mention and direction == "incoming" and sender:
            dst = "stanza:mention:" + quote(sender, safe="")
            sender_html = (f'<a class="mention" href="{dst}" '
                           f'title="{escape_html(tr("muc_mention_sender"))}">'
                           f'{sender_html}</a>')

        html = template.replace("%sender%", sender_html) \
                       .replace("%message%", body_html) \
                       .replace("%time%", timestamp) \
                       .replace("%senderColor%", sender_color) \
                       .replace("%userIconPath%", user_icon_path) \
                       .replace("%reply_title%", tr("chat_reply")) \
                       .replace("%copy_label%", tr("chat_copy"))
        if "{body}" in html:
            html = html.replace("{body}", body_html)
        return html

    def render_status(self, text: str, timestamp: str) -> str:
        """Render a status/system message."""
        if self._status_template:
            return self._status_template.replace("%message%", text) \
                                         .replace("%time%", timestamp)
        return f'<div class="status"><span class="time">{timestamp}</span> {text}</div>'

    def render_action(self, sender: str, body: str, timestamp: str) -> str:
        """Render a XEP-0245 ``/me`` action: "* <sender> <phrase>" in italics.

        The ``*`` and the sender name are plain text (never styled), while the
        phrase still passes through the standard fragment pipeline so links and
        emoticons inside it stay clickable.
        """
        phrase_html = self._body_fragment(body)
        return (f'<div class="stanza-action">'
                f'<span class="time">{timestamp}</span>'
                f' <span class="action">* {escape_html(sender)} {phrase_html}</span>'
                f'</div>')

    # XEP-0461 Message Replies ──────────────────────────────────────

    def render_reply(self, sender: str, quote: str = "") -> str:
        """Render a XEP-0461 reply-bar above the message body."""
        label = tr("reply_in_reply_to", sender=sender or "…")
        esc_quote = escape_html(quote or "")
        return (f'<div class="stanza-reply">'
                f'<span class="reply-arrow">\u21b0</span> '
                f'<span class="reply-label">{escape_html(label)}</span>'
                + (f' <span class="reply-quote">{esc_quote}</span>'
                   if quote else '')
                + '</div>')

    def generate_page(self, messages: list[dict], base_url: str = "") -> str:
        """Generate a complete HTML page containing the given messages.

        Each message dict has keys: sender, body, time, direction, is_next.
        """
        css = self._css
        if self._current_variant_css:
            css += "\n" + self._current_variant_css

        body_parts = []
        for msg in messages:
            if msg.get("type") == "status":
                body_parts.append(self.render_status(msg["body"], msg["time"]))
            elif msg.get("type") == "action":
                body_parts.append(self.render_action(
                    msg.get("sender", ""), msg.get("body", ""),
                    msg.get("time", "")))
            else:
                body_parts.append(self.render_message(
                    sender=msg.get("sender", ""),
                    body=msg.get("body", ""),
                    timestamp=msg.get("time", ""),
                    direction=msg.get("direction", "incoming"),
                    is_next=msg.get("is_next", False),
                    sender_color=msg.get("sender_color", "#000000"),
                    user_icon_path=msg.get("user_icon_path", ""),
                ))

        messages_html = "\n".join(body_parts)

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{css}</style>
<style>
body {{ margin: 0; padding: 4px; font-family: sans-serif; font-size: 13px; }}
#chat {{ display: flex; flex-direction: column; }}
.stanza-action {{ padding: 2px 8px; font-style: italic; color: #666; }}
.stanza-action .time {{ font-style: normal; font-size: 10px; color: #999; margin-right: 6px; }}
.stanza-action .action {{ font-style: italic; }}
.stanza-reply {{ padding: 3px 8px; font-size: 11px; color: #666;
                 border-left: 3px solid #bbb; background: rgba(0,0,0,.04); margin-bottom: 1px; }}
.stanza-reply .reply-label {{ font-weight: bold; }}
.stanza-reply .reply-quote {{ font-style: italic; color: #888; }}
</style>
</head>
<body>
<div id="chat">
{self._header}
{messages_html}
{self._footer}
<div id="stanza-typing-slot" class="typing-indicator"></div>
</div>
{_webchannel_script()}
</body>
</html>"""

    def generate_empty_page(self, base_url: str = "") -> str:
        """Generate an empty chat page."""
        css = self._css
        if self._current_variant_css:
            css += "\n" + self._current_variant_css
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{css}</style>
<style>
body {{ margin: 0; padding: 4px; font-family: sans-serif; font-size: 13px; }}
#chat {{ display: flex; flex-direction: column; }}
.stanza-action {{ padding: 2px 8px; font-style: italic; color: #666; }}
.stanza-action .time {{ font-style: normal; font-size: 10px; color: #999; margin-right: 6px; }}
.stanza-action .action {{ font-style: italic; }}
.stanza-reply {{ padding: 3px 8px; font-size: 11px; color: #666;
                 border-left: 3px solid #bbb; background: rgba(0,0,0,.04); margin-bottom: 1px; }}
.stanza-reply .reply-label {{ font-weight: bold; }}
.stanza-reply .reply-quote {{ font-style: italic; color: #888; }}
</style>
</head>
<body>
<div id="chat">
{self._header}
{self._footer}
<div id="stanza-typing-slot" class="typing-indicator"></div>
</div>
{_webchannel_script()}
</body>
</html>"""
