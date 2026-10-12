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
    """Subscribe to unread/event changes (idempotent across login)."""
    state = _ensure_state(app)
    for key, attr in (("slot", "unread_changed"),
                      ("event_slot", "events_changed")):
        signal = getattr(app, attr, None)
        if state.get(key) is None and signal is not None:
            slot = lambda: _refresh(app)  # noqa: E731
            signal.connect(slot)
            state[key] = slot
    _refresh(app)


def deactivate(app) -> None:
    state = getattr(app, _STATE, None)
    for key, attr in (("slot", "unread_changed"),
                      ("event_slot", "events_changed")):
        slot = (state or {}).get(key)
        signal = getattr(app, attr, None)
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


def _stats(app) -> tuple[int, int, int, int, int]:
    """``(messages, contacts, mentions, conferences, events)`` from the state.

    Contacts are 1:1 chats and MUC private messages (any key that is not a
    conference); conferences are counted only by their unread **mentions**;
    events is the Events-tab unread count.
    """
    chats = getattr(app, "_unread_chats", None) or {}
    conferences = set(getattr(app, "_conference_roster", None) or ())
    conferences |= set(getattr(app, "_muc_self_nicks", None) or {})
    # A room with restored unread is not joined yet at login, so it is only
    # recognisable from the persisted registry (`_known_conferences`).
    conferences |= set(getattr(app, "_known_conferences", None) or ())
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
    events = int(getattr(app, "_event_unread", 0) or 0)
    return messages, contacts, mentions, confs, events


def _refresh(app) -> None:
    """Recompute and show/update/dismiss the sticky digest notification."""
    osd = getattr(app, "_osd", None)
    if osd is None:
        return
    # Only surface notifications for the account actually logged in: the
    # restored unread counters exist before login (they still drive the roster
    # badges) but must not pop a digest on the login screen.
    if getattr(app, "_client", None) is None:
        osd.dismiss_sticky(_STICKY_KEY)
        return
    state = _ensure_state(app)
    messages, contacts, mentions, confs, events = _stats(app)
    total = messages + mentions + events
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
    if events > 0:
        lines.append(tr("digest_events", n=events))
    osd.show_sticky(_STICKY_KEY, _icon(), tr("digest_title"),
                    "\n".join(lines),
                    on_click=lambda: _open_top_unread(app),
                    on_close=lambda: _on_closed(app))


def _on_closed(app) -> None:
    """Remember the current total so it stays hidden until it grows."""
    state = _ensure_state(app)
    messages, _contacts, mentions, _confs, events = _stats(app)
    state["closed_at"] = messages + mentions + events


def _open_top_unread(app) -> None:
    """Open the Events tab when there are unread events, else a chat."""
    if int(getattr(app, "_event_unread", 0) or 0) > 0:
        handler = getattr(app, "_show_events_tab", None)
        if callable(handler):
            handler()
            return
    handler = getattr(app, "_on_tray_cycle_unread", None)
    if callable(handler):
        handler()


def _icon():
    from PyQt6 import QtGui
    from stanza_im.include.constants import find_icon
    return QtGui.QIcon(find_icon(PLUGIN_ICON))
