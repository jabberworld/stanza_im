"""Render a prepared chat window without creating a WebEngine tab.

The live chat widget owns much more state than message HTML, but the rendering
methods themselves only need a small, explicit context.  This module builds a
read-only ChatWidget shell, reuses its ``_entry_view_kwargs`` and the theme, and
returns the same marked HTML nodes that ``ChatView.add_message`` would produce.
"""
from __future__ import annotations

import logging

from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.nick_colors import NickColorAllocator
from stanza_im.ui import theme as theme_mod

logger = logging.getLogger(__name__)


class _PreparedView:
    """The tiny part of ChatView used by ``render_message_html``."""

    def __init__(self, theme: ChatThemeFactory, mention: bool, nick: str):
        self._theme = theme
        self.mention_senders = bool(mention)
        self.highlight_nick = nick
        from stanza_im.ui.chat_view import ChatView
        self._action_phrase = ChatView._action_phrase
        self._mark_message = ChatView._mark_message

    def render_message_html(self, *args, **kwargs) -> str:
        from stanza_im.ui.chat_view import ChatView
        return ChatView.render_message_html(self, *args, **kwargs)


def render_prepared(entries: list[dict], *, display_name: str = "",
                    is_muc: bool = False, own_jid: str = "",
                    own_avatar: str = "", peer_avatar: str = "",
                    users: list[dict] | None = None, self_nick: str = "",
                    theme: ChatThemeFactory | None = None,
                    avatar_radius: int = 20, colored_nicks: bool = True,
                    show_hats: bool = True, show_avatars: bool = True,
                    moderation: bool = False,
                    text_scale: float = 1.0) -> tuple[str, list[str], list[str]] | None:
    """Return ``(settings_hash, refs, html)`` for *entries* or ``None``.

    Must run on the GUI thread because avatar rounding uses QPixmap.
    """
    if not entries or theme is None:
        return None
    try:
        from stanza_im.ui import chat_view as chat_view_mod
        if not getattr(chat_view_mod, "HAS_WEBENGINE", False):
            return None
        w = ChatWidget.__new__(ChatWidget)
        w.jid = "prepared"
        w.display_name = display_name
        w.is_muc = bool(is_muc)
        w._own_jid = str(own_jid or "")
        w._own_avatar = str(own_avatar or "")
        w._peer_avatar = str(peer_avatar or "")
        w._show_avatars = bool(show_avatars)
        w._users = list(users or [])
        w._self_nick = str(self_nick or "")
        w._theme = theme
        w._avatar_radius = max(0, min(100, int(avatar_radius or 0)))
        w._rounded_avatar_cache = {}
        w._colored_muc_nicks = bool(colored_nicks)
        w._show_muc_hats = bool(show_hats)
        w._text_scale = float(text_scale or 1.0)
        w._moderation_enabled = bool(moderation)
        w._history = list(entries)
        w._messages = []
        w._quick_response_used_refs = set()
        w._quick_response_refs = w._compute_quick_response_refs(entries)
        w._nick_colors = NickColorAllocator(dark=theme_mod.is_dark())
        # Allocate participant colors in the same participant order the live
        # sidebar uses, so prepared and live HTML agree.
        for user in w._users:
            if user.get("nick"):
                w._nick_colors.color_for(w._user_color_key(user))
        if w._self_nick:
            from stanza_im.ui.nick_colors import normalize_nick
            w._nick_colors.color_for(normalize_nick(w._self_nick))
        w._view = _PreparedView(theme, w.is_muc, w._self_nick)
        refs = [w._render_ref(entry) for entry in entries]
        html = [w._view.render_message_html(
                    **w._entry_view_kwargs(entry, False))
                for entry in entries]
        if not all(html):
            return None
        return w._render_settings_hash(), refs, html
    except Exception:  # noqa: BLE001 - preparation is best-effort
        logger.debug("PREP[render] failed", exc_info=True)
        return None
