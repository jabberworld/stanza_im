"""Chat theme engine — generates HTML from Adium-style chat skin templates."""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import quote

from PyQt6 import QtCore, QtGui

from stanza_im.include.constants import CHATSKINS_DIR
from stanza_im.include.emoticons import smile_to_html
from stanza_im.include.utils import escape_html, restore_url_tokens
from stanza_im.include import hats as hats_mod
from stanza_im.i18n import tr

_logger = logging.getLogger(__name__)

_HIGHLIGHT_COLOR = "#e53935"

_MEDIA_CSS = """
.stanza-media { display: inline-block; margin: 3px 0; vertical-align: top; }
.stanza-media-thumb { border-radius: 6px; max-width: 100%; height: auto;
                      cursor: pointer; background: rgba(0,0,0,.06); display: block; }
.stanza-media-loading .stanza-media-thumb { min-width: 80px; min-height: 60px; }
.stanza-media audio { max-width: 340px; }
.stanza-media video { max-width: 100%; border-radius: 6px; background: #000;
                      display: block; }
.stanza-media-open { display: inline-block; margin-top: 2px; font-size: 11px;
                     color: #1a73e8; }
"""

_HATS_CSS = """
.stanza-hat { display: inline-block; margin-left: 4px; padding: 0 5px;
              border-radius: 7px; font-size: 9px; font-weight: normal;
              line-height: 14px; vertical-align: middle; white-space: nowrap;
              background: rgba(0,0,0,.08); }
"""

# XEP-0424: the inline delete button lives in every template, but only our
# own messages (data-stanza-outgoing) may be retracted.
_DELETE_CSS = """
.stanza-message:not([data-stanza-outgoing="1"]) .message_actions a.action-delete
    { display: none; }
"""


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
    ``resources/``) and installs ``window.bridge`` plus a scroll reporter.
    Click routing does NOT live here: anchors (links, mentions, replies, MAM)
    navigate to their ``href`` and are intercepted on the C++ side via
    ``QWebEnginePage.acceptNavigationRequest`` (``ChatView._accept_navigation``).
    Returns '' only when the script itself is unavailable.
    """
    js = _qwebchannel_js()
    if not js:
        return ""
    return f"""<script>
{js}
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
            if (window.bridge && window.bridge.on_scroll_fraction) {{
                window.bridge.on_scroll_fraction(Math.min(1, st / max));
            }}
            if (st <= ih && window.bridge && window.bridge.on_near_top) {{
                window.bridge.on_near_top();
            }}
        }}
        window.addEventListener('scroll', onScroll);
    }});
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
        self._highlight_mode = "both"
        self._media = None
        self._media_mode = "none"
        self._media_size = 200
        self._font_family = ""
        self._font_size_pt = 0
        self._nick_font_family = ""
        self._nick_font_size_pt = 0
        self._chat_bg_color = ""
        self._highlight_color = _HIGHLIGHT_COLOR
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

    def set_highlight_mode(self, mode: str) -> None:
        """Set the MUC mention highlight style: "bold" | "color" | "both"."""
        self._highlight_mode = mode or "both"

    def set_media_preview(self, service, mode: str = "none",
                          size: int = 200) -> None:
        """Attach a :class:`MediaPreviewService` and its policy.

        The factory is the single source of truth for the preview policy: the
        mode/size are pushed into the service too, so it never keeps a stale
        default that would silently drop audio/video embeds.
        """
        self._media = service
        self._media_mode = mode or "none"
        try:
            self._media_size = int(size or 200)
        except (TypeError, ValueError):
            self._media_size = 200
        if service is not None:
            service.set_mode(self._media_mode)
            service.set_size(self._media_size)

    def set_chat_font(self, family: str = "", size: int = 0) -> None:
        """Set the chat base-font override (*family*, point size).

        An empty family / zero size keeps the skin's defaults.  The override
        is appended to the page CSS (last style block, ``!important``), so it
        wins over themes that hard-code their own font on the message text.
        Avatars and media are unaffected — only text.  Applies to the HTML
        (WebEngine) rendering; the QTextBrowser fallback keeps its document
        font scaled by the zoom factor only.
        """
        self._font_family = family or ""
        try:
            self._font_size_pt = int(size or 0)
        except (TypeError, ValueError):
            self._font_size_pt = 0

    def chat_font(self) -> tuple[str, int]:
        """Return the current (family, size-in-points) font override."""
        return self._font_family, self._font_size_pt

    def set_nick_font(self, family: str = "", size: int = 0) -> None:
        """Set the chat nickname font override (*family*, point size).

        Applies to the message sender label only: ``.sender`` in the generated
        CSS, which is injected into the theme's own ``%sender%`` position when
        the skin packs no ``class="sender"`` on its sender element.  An empty
        family / zero size makes nicknames simply inherit the chat font.
        """
        self._nick_font_family = family or ""
        try:
            self._nick_font_size_pt = int(size or 0)
        except (TypeError, ValueError):
            self._nick_font_size_pt = 0

    def nick_font(self) -> tuple[str, int]:
        """Return the current (family, size-in-points) nickname override."""
        return self._nick_font_family, self._nick_font_size_pt

    def set_chat_bg_color(self, color: str = "") -> None:
        """Set the chat background override (hex ``#rrggbb``).

        Empty/invalid values keep the skin's own body background.  The color
        is injected as a ``body`` CSS rule that also clears the skin's
        ``background-image`` so the chosen shade actually shows (e.g. the
        ``minimal-mod`` tiled image would otherwise still paint on top).
        """
        if color and QtGui.QColor(str(color)).isValid():
            self._chat_bg_color = QtGui.QColor(str(color)).name()
        else:
            self._chat_bg_color = ""

    def set_highlight_color(self, color: str = "") -> None:
        """Set the MUC mention highlight color (hex ``#rrggbb``)."""
        if color and QtGui.QColor(str(color)).isValid():
            self._highlight_color = QtGui.QColor(str(color)).name()
        else:
            self._highlight_color = _HIGHLIGHT_COLOR

    def _font_override_css(self) -> str:
        """CSS that forces the configured family/size on the chat text."""
        css = ""
        if self._font_family or self._font_size_pt:
            family = self._font_family or "sans-serif"
            size = self._font_size_pt or 13
            safe_family = family.replace("\\", "\\\\").replace("'", "\\'")
            css += (
                f"body {{ font-family: '{safe_family}' !important; "
                f"font-size: {size}pt !important; }}"
                "\n.sender, .fromstatus, .next_label, .time_initial, "
                "#chat .stanza-action, #chat .stanza-reply "
                "{ font-family: inherit !important; }")
        if self._nick_font_family or self._nick_font_size_pt:
            family = self._nick_font_family or self._font_family or "sans-serif"
            size = (self._nick_font_size_pt or self._font_size_pt or 13)
            safe_family = family.replace("\\", "\\\\").replace("'", "\\'")
            css += (f"\n.sender {{ font-family: '{safe_family}' !important; "
                    f"font-size: {size}pt !important; }}")
        if self._chat_bg_color:
            css += (f"\nbody {{ background-color: {self._chat_bg_color} "
                    f"!important; background-image: none !important; }}")
        return css

    def _transform_body(self, body: str, styled: bool = True,
                        highlight_nick: str = "", geo_ref: str = "") -> str:
        """Turn a plain-text body into message HTML.

        With styling enabled the XEP-0393 parser runs first and delegates
        plain-text regions to :meth:`_body_fragment`, so URLs/emoticons still
        apply inside styled spans but never inside ``<code>``/``<pre>``.
        *geo_ref* is the message id used by XEP-0308 corrections, embedded in
        the ``stanza:geo:`` link so an open map window can follow the fixes.
        """
        if self._message_styling and styled:
            from stanza_im.xmpp import message_styling
            try:
                return message_styling.render(
                    body,
                    lambda raw: self._body_fragment(raw, highlight_nick,
                                                    geo_ref))
            except Exception:
                pass
        return self._body_fragment(body, highlight_nick, geo_ref)

    def _body_fragment(self, raw: str, highlight_nick: str = "",
                       geo_ref: str = "") -> str:
        """Escape plain text, then add clickable links and emoticons.

        Order matters: URLs are replaced with tokens first so emoticon codes
        (e.g. ``:/`` inside ``https://``) can't corrupt them, emoticons are
        substituted in the remaining text, then the <a> links are restored.
        """
        escaped = escape_html(raw)
        escaped = escaped.replace("\r\n", "\n").replace("\r", "\n")
        escaped = escaped.replace("\n", "<br>")
        tokenised, anchors = self._tokenize_urls(escaped, geo_ref)
        emotified = smile_to_html(tokenised, self._emoticon_skin)
        if highlight_nick and self._highlight_mode != "none":
            emotified = self._apply_highlight(emotified, highlight_nick)
        return restore_url_tokens(emotified, anchors)

    def _apply_highlight(self, text: str, nick: str) -> str:
        """Wrap case-insensitive *nick* mentions in styled <span> tags.

        A mention is bounded on both sides by a non-letter/non-digit (Unicode
        aware), so punctuation stays allowed ("rain:", "rain?") while
        substrings of longer words ("brain", "Ukraine") never match.
        """
        style = ""
        if self._highlight_mode in ("bold", "both"):
            style += "font-weight:bold;"
        if self._highlight_mode in ("color", "both"):
            style += "color:%s;" % self._highlight_color
        pattern = re.compile(r"(?<![^\W_])(%s)(?![^\W_])"
                             % re.escape(nick), re.IGNORECASE)
        return pattern.sub('<span style="%s">\\1</span>' % style.rstrip(";"),
                           text)

    def _tokenize_urls(self, text: str, geo_ref: str = ""
                       ) -> tuple[str, list[str]]:
        from stanza_im.include.utils import tokenize_urls
        render = None
        if self._media is not None and self._media_mode != "none":
            render = self._media.markup

        def geo_render(uri: str) -> str:
            if not geo_ref:
                return f'<a href="{uri}">{uri}</a>'
            from urllib.parse import quote
            href = "stanza:geo:%s/%s" % (quote(str(geo_ref), safe=""),
                                         quote(uri, safe=""))
            return f'<a class="stanza-geo" href="{href}">{uri}</a>'

        return tokenize_urls(text, render, geo_render)

    def render_message(self, sender: str, body: str, timestamp: str,
                       direction: str, is_next: bool = False,
                       sender_color: str = "#000000",
                       user_icon_path: str = "", unstyled: bool = False,
                       mention: bool = False, edited: bool = False,
                       highlight_nick: str = "", geo_ref: str = "",
                       hats: list | None = None,
                       retracted: bool = False,
                       retract_marker: bool = False) -> str:
        """Render a single message to HTML using the skin template.

        With *mention* the incoming sender name is wrapped in a clickable
        ``stanza:mention:`` link (MUC nickname mentions).  With *edited* a
        bold «✎» marker is appended right after the message phrase.  With
        *highlight_nick* case-insensitive mentions of that nick in the body
        are wrapped in a styled <span> (see :meth:`_apply_highlight`).  With
        *geo_ref* geo: URIs in the body become ``stanza:geo:`` links carrying
        the message id (used to live-update the map window on corrections).
        *hats* (XEP-0317) are rendered as coloured chips right of the nick.
        """
        key = direction
        if is_next:
            key += "_next"
        template = self._templates.get(key, self._templates.get(direction, "{body}"))
        body_html = self._transform_body(body, styled=not unstyled,
                                         highlight_nick=highlight_nick,
                                         geo_ref=geo_ref)
        if retracted:
            body_html = ('<span class="stanza-retracted-text" '
                         'style="color:#888;font-style:italic;">%s</span>'
                         % escape_html(tr("msg_retracted")))
        else:
            if edited:
                body_html += ('<span class="stanza-edited" style="color:#777;'
                              'font-size:16px;font-weight:bold;margin-left:4px;'
                              'cursor:help;" title="%s">\u270e</span>'
                              % escape_html(tr("msg_edited_tooltip")))
            if retract_marker:
                body_html += ('<span class="stanza-retracted" style="color:#777;'
                              'font-size:16px;font-weight:bold;margin-left:4px;'
                              'cursor:help;" title="%s">\u2715</span>'
                              % escape_html(tr("msg_retract_marker_tooltip")))

        sender_html = escape_html(sender)
        if mention and direction == "incoming" and sender:
            dst = "stanza:mention:" + quote(sender, safe="")
            sender_html = (f'<a class="mention" href="{dst}" '
                           f'title="{escape_html(tr("muc_mention_sender"))}">'
                           f'{sender_html}</a>')
        if (self._nick_font_family or self._nick_font_size_pt) \
                and 'class="sender' not in template:
            sender_html = f'<span class="sender">{sender_html}</span>'
        sender_html += self._render_hats(hats)

        html = template.replace("%sender%", sender_html) \
                       .replace("%message%", body_html) \
                       .replace("%time%", timestamp) \
                       .replace("%senderColor%", sender_color) \
                       .replace("%userIconPath%", user_icon_path) \
                       .replace("%reply_title%", tr("chat_reply")) \
                       .replace("%copy_label%", tr("chat_copy")) \
                       .replace("%delete_title%", tr("chat_delete"))
        if "{body}" in html:
            html = html.replace("{body}", body_html)
        return html

    @staticmethod
    def _render_hats(hats: list | None) -> str:
        """Render XEP-0317 hats as coloured chips right of the sender nick."""
        if not hats:
            return ""
        parts = []
        for hat in hats:
            title = str((hat or {}).get("title") or (hat or {}).get("uri") or "")
            if not title:
                continue
            hue = (hat or {}).get("hue")
            fg = hats_mod.hue_to_color(hue, 90.0, 32.0) if hue is not None else ""
            bg = hats_mod.hue_to_color(hue, 70.0, 88.0) if hue is not None else ""
            border = (hats_mod.hue_to_color(hue, 80.0, 72.0)
                      if hue is not None else "")
            style = ""
            if fg:
                style += f"color:{fg};"
            if bg:
                style += f"background:{bg};"
            if border:
                style += f"border:1px solid {border};"
            title_html = escape_html(title)
            parts.append(
                f'<span class="stanza-hat" style="{style}" '
                f'title="{title_html}">{title_html}</span>')
        return "".join(parts)

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

    def render_reply(self, sender: str, snippet: str = "",
                     target_id: str = "") -> str:
        """Render a XEP-0461 reply-bar above the message body.

        With *target_id* the bar becomes a ``stanza:jump:`` link that the chat
        page turns into a scroll-to-message action (never a navigation).
        """
        label = tr("reply_in_reply_to", sender=sender or "…")
        esc_quote = escape_html(snippet or "")
        inner = (f'<span class="reply-arrow">\u21b0</span> '
                 f'<span class="reply-label">{escape_html(label)}</span>'
                 + (f' <span class="reply-quote">{esc_quote}</span>'
                    if snippet else ''))
        if target_id:
            href = "stanza:jump:" + quote(target_id, safe="")
            inner = (f'<a class="stanza-reply-jump" href="{href}" '
                     f'title="{escape_html(tr("reply_jump_tooltip"))}">'
                     f'{inner}</a>')
        return f'<div class="stanza-reply">{inner}</div>'

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
                    hats=msg.get("hats"),
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
.stanza-reply a.stanza-reply-jump {{ display: block; color: inherit;
                 text-decoration: none; cursor: pointer; }}
.stanza-reply a.stanza-reply-jump:hover .reply-label {{ text-decoration: underline; }}
.stanza-jump-highlight {{ animation: stanza-jump-flash 1.6s ease-out; }}
@keyframes stanza-jump-flash {{ 0% {{ background: rgba(255,214,0,.45); }}
                 100% {{ background: transparent; }} }}
{_MEDIA_CSS}
{_HATS_CSS}
{_DELETE_CSS}
{self._font_override_css()}
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
.stanza-reply a.stanza-reply-jump {{ display: block; color: inherit;
                 text-decoration: none; cursor: pointer; }}
.stanza-reply a.stanza-reply-jump:hover .reply-label {{ text-decoration: underline; }}
.stanza-jump-highlight {{ animation: stanza-jump-flash 1.6s ease-out; }}
@keyframes stanza-jump-flash {{ 0% {{ background: rgba(255,214,0,.45); }}
                 100% {{ background: transparent; }} }}
{_MEDIA_CSS}
{_HATS_CSS}
{_DELETE_CSS}
{self._font_override_css()}
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
