"""Attention plugin (XEP-0224, category: Communication).

Lets a 1:1 contact "nudge" us with a bodyless ``<attention/>`` message and
surfaces incoming nudges (sound, OSD, an Events entry).  Activation installs a
contact-menu entry ("Привлечь внимание") next to "Send contact…" and enables the
bell button on 1:1 tabs; both stay disabled for peers that do not advertise
``urn:xmpp:attention:0``.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

PLUGIN_ID = "attention"
PLUGIN_NAME = "plugin_attention_name"
PLUGIN_CATEGORY = "plugin_category_communication"
PLUGIN_DESCRIPTION = "plugin_attention_desc"
PLUGIN_ICON = "attention.svg"
PLUGIN_HAS_SETTINGS = True

# XEP-0224 namespace.  Defined locally (mirrors ``core/client.py``) so that
# merely importing this plugin — done by ``plugins.discover()`` at startup for
# every plugin — never pulls in ``core.client`` (and, transitively, aiortc).
NS_ATTENTION = "urn:xmpp:attention:0"

_SOUND = "effects/door_bell.wav"

# Plugin runtime state is kept on the application object under these names.
_STATE = "_attention_state"


def _settings(config) -> dict:
    """Return the plugin's settings with defaults applied."""
    from stanza_im.plugins import settings_section
    section = settings_section(config, PLUGIN_ID)
    if "cooldown" not in section:
        section.cooldown = 60
    if "allow_dnd" not in section:
        section.allow_dnd = True
    if "play_sound" not in section:
        section.play_sound = True
    if "show_events" not in section:
        section.show_events = True
    return section


def open_settings(config, parent=None) -> None:
    """Open the Attention settings dialog."""
    from stanza_im.ui.attention_settings_dialog import AttentionSettingsDialog
    dialog = AttentionSettingsDialog(config, parent)
    dialog.exec()


# ── Activation ────────────────────────────────────────────────────


def _ensure_state(app) -> dict:
    state = getattr(app, _STATE, None)
    if state is None:
        state = {"last": {}, "hooks": [], "seen": set()}
        setattr(app, _STATE, state)
    state.setdefault("seen", set())
    app._attention_seen = state["seen"]
    return state


def activate(app) -> None:
    state = _ensure_state(app)
    app._attention_feature = NS_ATTENTION
    app._attention_seen = state["seen"]

    menuhook = _make_menu_hook(app)
    app.add_contact_menu_hook(menuhook)
    state["hooks"].append(menuhook)

    on_client_ready(app)


def on_client_ready(app) -> None:
    """Bind to the now-existing client (called after login / activation)."""
    state = _ensure_state(app)
    client = getattr(app, "_client", None)
    if client is not None and not state.get("subscribed"):
        client.on("attention_received", lambda frm: _on_attention(app, frm))
        state["subscribed"] = True
    # Show/enable the bell on already-open 1:1 tabs.
    for jid in list(getattr(app, "_chat_window", None).tabs()
                    if getattr(app, "_chat_window", None) else []):
        app.apply_attention_support(jid)


def deactivate(app) -> None:
    state = getattr(app, _STATE, {})
    for hook in state.get("hooks", []):
        app.remove_contact_menu_hook(hook)
    setattr(app, _STATE, None)
    app._attention_feature = ""
    app._attention_seen = set()
    # Hide the bell on open 1:1 tabs (plugin is no longer active).
    for jid in list(getattr(app, "_chat_window", None).tabs()
                    if getattr(app, "_chat_window", None) else []):
        app.apply_attention_support(jid)


# ── Menu entry ────────────────────────────────────────────────────


def _make_menu_hook(app):
    """Return the contact-menu hook adding "Привлечь внимание" for *app*."""
    from stanza_im.i18n import tr
    from stanza_im.include.constants import find_icon

    def hook(menu, jid, is_conf) -> None:
        if is_conf:
            return
        bare = jid.split("/", 1)[0]
        client = getattr(app, "_client", None)
        # Enabled when the peer advertises the feature or has ever sent us an
        # attention request (Psi+ often sends it without announcing it).
        supported = (bare in getattr(app, "_attention_seen", set())
                     or bool(client
                             and client.supports_feature(bare, NS_ATTENTION)))
        action = menu.addAction(
            _menu_icon(), tr("attention_menu"),
            lambda checked=False: _send(app, bare))
        action.setEnabled(supported)

    return hook


def _menu_icon():
    from PyQt6 import QtGui
    from stanza_im.include.constants import find_icon
    return QtGui.QIcon(find_icon("attention.svg"))


def _send(app, bare: str) -> None:
    client = getattr(app, "_client", None)
    if client is not None:
        client.send_attention(bare)


def _on_attention(app, frm: str) -> None:
    """Handle an incoming XEP-0224 request (sound / OSD / Events)."""
    client = getattr(app, "_client", None)
    if client is None or not frm:
        return
    bare = frm.split("/", 1)[0]
    config = app._config
    settings = _settings(config)
    state = _ensure_state(app)

    # The peer proved it supports attention by sending one — unlock the bell /
    # menu for it even if it does not advertise the feature in its caps.
    if bare not in state["seen"]:
        state["seen"].add(bare)
        app.apply_attention_support(bare)

    # Our "do not disturb" status suppresses the notification unless allowed.
    our_show = str(getattr(config, "last_status", "") or "")
    if our_show == "dnd" and not bool(settings.allow_dnd):
        logger.debug("ATTENTION from %s ignored (dnd)", bare)
        return

    # Per-contact throttle: at most one nudge per ``cooldown`` seconds.
    now = time.monotonic()
    cooldown = max(1, min(99, int(settings.cooldown or 60)))
    last = state["last"].get(bare, 0.0)
    if now - last < cooldown:
        logger.debug("ATTENTION from %s throttled", bare)
        return
    state["last"][bare] = now

    name = app._roster_name(bare) or bare.split("@")[0]
    if bool(settings.play_sound):
        _play_bell(app)
    cfg = config.notifications
    if cfg.osd_enabled:
        from stanza_im.i18n import tr
        app._osd.show(
            _attention_icon(), tr("attention_osd_title"),
            tr("attention_osd_body", name=name),
            on_click=lambda: app._osd_click(bare))
    if bool(settings.show_events):
        from stanza_im.i18n import tr
        app._push_system_event(tr("attention_event", name=name))


def _attention_icon():
    from PyQt6 import QtGui
    from stanza_im.include.constants import find_icon
    icon = QtGui.QIcon(find_icon("attention.svg"))
    return icon


def _play_bell(app) -> None:
    from stanza_im.include.constants import SOUNDS_DIR
    import os
    player = getattr(app, "_sounds", None)
    if player is None:
        return
    path = os.path.join(SOUNDS_DIR, _SOUND)
    if os.path.isfile(path):
        player.play_file(path)
