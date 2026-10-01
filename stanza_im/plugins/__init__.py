"""Plugin registry.

Plugins are self-contained sub-packages of ``stanza_im.plugins``.  Each
sub-package exposes a small manifest through module-level attributes and
optional lifecycle hooks::

    PLUGIN_ID = "notes"              # unique, stable key (config / menu)
    PLUGIN_NAME = "plugin_notes_name"  # i18n key shown in the manager
    PLUGIN_CATEGORY = "tools"        # i18n key of the category
    PLUGIN_DESCRIPTION = "…_desc"    # i18n key
    PLUGIN_ICON = "draw-brush.png"   # icon filename (find_icon dirs)

    def activate(app): ...           # called when enabled
    def deactivate(app): ...         # called when disabled
    def on_client_ready(app): ...    # called once the XMPP client exists

    PLUGIN_HAS_SETTINGS = True       # optional: announce a settings dialog
    def open_settings(config, parent=None): ...  # opens the plugin's own dialog

A plugin with settings persists them in the shared config under
``[plugin_settings.<id>]`` (see :func:`settings_section`); the enable flag stays
``[plugins].<id> = true``.

``discover()`` scans the directory (no external loading), so enabling a plugin
is a pure in-process call and a plugin that disappeared between sessions is a
plain missing entry the caller can warn about.
"""
from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

# Preferred category order; unknown categories sort after these, by name.
CATEGORY_ORDER = ("tools", "communication", "appearance", "other")


@dataclass(frozen=True)
class Plugin:
    """A discovered plugin's manifest plus its lifecycle hooks."""

    id: str
    name: str
    category: str
    description: str = ""
    icon: str = ""
    module: object = None
    has_settings: bool = False

    def activate(self, app) -> None:
        hook = getattr(self.module, "activate", None)
        if callable(hook):
            hook(app)

    def deactivate(self, app) -> None:
        hook = getattr(self.module, "deactivate", None)
        if callable(hook):
            hook(app)

    def client_ready(self, app) -> None:
        """Called once the XMPP client exists (event subscriptions etc.)."""
        hook = getattr(self.module, "on_client_ready", None)
        if callable(hook):
            hook(app)

    def open_settings(self, config, parent=None) -> bool:
        """Open the plugin's settings dialog; True when it was offered."""
        if not self.has_settings:
            return False
        hook = getattr(self.module, "open_settings", None)
        if not callable(hook):
            return False
        hook(config, parent)
        return True


def _package_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def discover() -> list[Plugin]:
    """Return every plugin found under ``stanza_im.plugins`` (sorted)."""
    found: list[Plugin] = []
    base = _package_dir()
    for entry in sorted(os.listdir(base)):
        path = os.path.join(base, entry)
        if not os.path.isdir(path) or entry.startswith(("_", ".")):
            continue
        if not os.path.isfile(os.path.join(path, "__init__.py")):
            continue
        try:
            module = importlib.import_module(f"{__name__}.{entry}")
        except Exception:  # noqa: BLE001 - a broken plugin must not kill us
            logger.warning("Could not import plugin %s", entry, exc_info=True)
            continue
        plugin_id = str(getattr(module, "PLUGIN_ID", "") or entry)
        name = str(getattr(module, "PLUGIN_NAME", "") or plugin_id)
        category = str(getattr(module, "PLUGIN_CATEGORY", "") or "other")
        has_settings = bool(getattr(module, "PLUGIN_HAS_SETTINGS", False)) \
            and callable(getattr(module, "open_settings", None))
        found.append(Plugin(
            id=plugin_id,
            name=name,
            category=category,
            description=str(getattr(module, "PLUGIN_DESCRIPTION", "") or ""),
            icon=str(getattr(module, "PLUGIN_ICON", "") or ""),
            module=module,
            has_settings=has_settings,
        ))
    return sorted(found, key=_sort_key)


def _sort_key(plugin: Plugin) -> tuple:
    try:
        order = CATEGORY_ORDER.index(plugin.category)
    except ValueError:
        order = len(CATEGORY_ORDER)
    return (order, plugin.category.casefold(), plugin.name.casefold(),
            plugin.id)


def get(plugin_id: str) -> Plugin | None:
    """Return the plugin with *plugin_id* (or ``None``)."""
    for plugin in discover():
        if plugin.id == plugin_id:
            return plugin
    return None


def _plugins_section(config) -> dict:
    """Return the mutable ``[plugins]`` mapping from *config*."""
    section = getattr(config, "plugins", None)
    if section is None:
        from stanza_im.core.storage import AttrDict
        section = AttrDict()
        setattr(config, "plugins", section)
    return section


def enabled_ids(config, known: Iterable[Plugin] | None = None) -> list[str]:
    """Return the ids enabled in *config* (optionally filtered to *known*)."""
    section = _plugins_section(config)
    known_ids = {p.id for p in known} if known is not None else None
    out = []
    for pid, value in dict(section).items():
        if not value:
            continue
        if known_ids is not None and pid not in known_ids:
            continue
        out.append(pid)
    return out


def stored_enabled_ids(config) -> list[str]:
    """Like :func:`enabled_ids` but without filtering (includes missing ones)."""
    return enabled_ids(config, known=None)


def set_enabled(config, plugin_id: str, enabled: bool) -> None:
    """Persist the enabled/disabled state of *plugin_id*."""
    _plugins_section(config)[plugin_id] = bool(enabled)


def settings_section(config, plugin_id: str):
    """Return (creating if needed) the plugin's settings AttrDict.

    Settings live in the shared config under ``[plugin_settings.<id>]`` so they
    never collide with the boolean enable flag in ``[plugins].<id>``.
    """
    from stanza_im.core.storage import AttrDict
    root = getattr(config, "plugin_settings", None)
    if root is None:
        root = AttrDict()
        setattr(config, "plugin_settings", root)
    section = root.get(plugin_id)
    if not isinstance(section, AttrDict):
        section = AttrDict(section or {})
        root[plugin_id] = section
    return section


def missing_enabled(config, known: Iterable[Plugin] | None = None) -> list[str]:
    """Return saved-enabled ids that are not among the discovered plugins."""
    plugins = list(known) if known is not None else discover()
    known_ids = {p.id for p in plugins}
    return [pid for pid in stored_enabled_ids(config) if pid not in known_ids]
