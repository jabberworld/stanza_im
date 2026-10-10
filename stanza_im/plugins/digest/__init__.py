"""Notifications Digest plugin (category: Notifications).

Keeps a single persistent OSD notification on screen while there are unread
messages from contacts (1:1 chats and MUC private messages) or mentions
(highlights) in conferences, and updates it as the counters change.  The
notification can be dismissed with its close button; it reappears once the
number of unread messages/mentions grows again.  Clicking it opens the topmost
unread conversation.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PLUGIN_ID = "digest"
PLUGIN_NAME = "plugin_digest_name"
PLUGIN_CATEGORY = "plugin_category_notifications"
PLUGIN_DESCRIPTION = "plugin_digest_desc"
PLUGIN_ICON = "attention.svg"

# One sticky OSD for the whole plugin.
_STICKY_KEY = "digest"
# Plugin runtime state lives on the application object under this name.
_STATE = "_digest_state"


def _ensure_state(app) -> dict:
    state = getattr(app, _STATE, None)
    if state is None:
        state = {"slot": None, "closed_at": None}
        setattr(app, _STATE, state)
    return state


def activate(app) -> None:
    _ensure_state(app)
    on_client_ready(app)
    _refresh(app)


def on_client_ready(app) -> None:
    """Subscribe to unread changes (idempotent across login/activation)."""
    state = _ensure_state(app)
    signal = getattr(app, "unread_changed", None)
    if state.get("slot") is None and signal is not None:
        slot = lambda: _refresh(app)  # noqa: E731
        signal.connect(slot)
        state["slot"] = slot
    _refresh(app)


def deactivate(app) -> None:
    state = getattr(app, _STATE, None)
    slot = (state or {}).get("slot")
    signal = getattr(app, "unread_changed", None)
    if slot is not None and signal is not None:
        try:
            signal.disconnect(slot)
        except (TypeError, RuntimeError):
            pass
    setattr(app, _STATE, None)
    osd = getattr(app, "_osd", None)
    if osd is not None:
        osd.dismiss_sticky(_STICKY_KEY)


# ── Statistics ────────────────────────────────────────────────────


def _stats(app) -> tuple[int, int, int, int]:
    """``(messages, contacts, mentions, conferences)`` from the unread state.

    Contacts are 1:1 chats and MUC private messages (any key that is not a
    conference); conferences are counted only by their unread **mentions**.
    """
    chats = getattr(app, "_unread_chats", None) or {}
    conferences = set(getattr(app, "_conference_roster", None) or ())
    conferences |= set(getattr(app, "_muc_self_nicks", None) or {})
    messages = contacts = mentions = confs = 0
    for key, entry in chats.items():
        if key in conferences:
            count = int(entry.get("mentions", 0) or 0)
            if count > 0:
                mentions += count
                confs += 1
        else:
            count = int(entry.get("unread", 0) or 0)
            if count > 0:
                messages += count
                contacts += 1
    return messages, contacts, mentions, confs


def _refresh(app) -> None:
    """Recompute and show/update/dismiss the sticky digest notification."""
    osd = getattr(app, "_osd", None)
    if osd is None:
        return
    state = _ensure_state(app)
    messages, contacts, mentions, confs = _stats(app)
    total = messages + mentions
    if total <= 0:
        osd.dismiss_sticky(_STICKY_KEY)
        state["closed_at"] = None
        return
    # Respect a manual dismissal: stay hidden until the counters grow again.
    closed_at = state.get("closed_at")
    if closed_at is not None and total <= closed_at:
        return
    state["closed_at"] = None
    from stanza_im.i18n import tr
    lines = []
    if messages > 0:
        lines.append(tr("digest_contacts", n=messages, m=contacts))
    if mentions > 0:
        lines.append(tr("digest_mentions", n=mentions, m=confs))
    osd.show_sticky(_STICKY_KEY, _icon(), tr("digest_title"),
                    "\n".join(lines),
                    on_click=lambda: _open_top_unread(app),
                    on_close=lambda: _on_closed(app))


def _on_closed(app) -> None:
    """Remember the current total so it stays hidden until it grows."""
    state = _ensure_state(app)
    messages, _contacts, mentions, _confs = _stats(app)
    state["closed_at"] = messages + mentions


def _open_top_unread(app) -> None:
    """Open the topmost conversation with unread messages (tray behaviour)."""
    handler = getattr(app, "_on_tray_cycle_unread", None)
    if callable(handler):
        handler()


def _icon():
    from PyQt6 import QtGui
    from stanza_im.include.constants import find_icon
    return QtGui.QIcon(find_icon(PLUGIN_ICON))
