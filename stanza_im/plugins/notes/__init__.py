"""Notes plugin (category: Tools).

Stores tagged text notes on the server in XEP-0049 private XML storage using
the Miranda ``http://miranda-im.org/storage#notes`` payload.  Activating the
plugin appends a "Notes" tab to the roster window (after the built-in tabs);
deactivating it removes the tab again.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PLUGIN_ID = "notes"
PLUGIN_NAME = "plugin_notes_name"
PLUGIN_CATEGORY = "plugin_category_tools"
PLUGIN_DESCRIPTION = "plugin_notes_desc"
PLUGIN_ICON = "draw-brush.png"

_TAB_KEY = "plugin:notes"


def activate(app) -> None:
    """Add the Notes tab to the roster tab bar."""
    app._notes_feature = True
    app._notes_page = getattr(app, "_notes_page", None)
    if getattr(app, "_notes_page", None) is not None:
        return
    from stanza_im.i18n import tr
    from stanza_im.ui.notes_widget import NotesWidget
    page = NotesWidget(lambda: app._client, app._start_task)
    app._notes_page = page
    app._add_roster_tab(
        _TAB_KEY, app._tab_icon(PLUGIN_ICON), tr(PLUGIN_NAME), page)


def on_client_ready(app) -> None:
    """Preload the notes once the client exists."""
    page = getattr(app, "_notes_page", None)
    if page is not None and getattr(app, "_client", None) is not None:
        page.reload()


def deactivate(app) -> None:
    """Remove the Notes tab from the roster tab bar."""
    app._remove_roster_tab(_TAB_KEY)
    app._notes_page = None
    app._notes_feature = False
