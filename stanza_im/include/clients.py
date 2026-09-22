"""XEP-0115 caps node → Jabber client name/icon mapping.

The data lives in ``resources/clients/clients.txt`` (generated from the bundled
``index.html`` by ``resources/clients/build_clients.py``)::

    caps-prefix <TAB> client name <TAB> icon file

Icons are shipped in ``resources/clients/{16x16,22x22,32x32,64x64}/``.
"""
from __future__ import annotations

import os
from functools import lru_cache

from stanza_im.include.constants import CLIENTS_DIR, CLIENTS_FILE

SIZES = ("16x16", "22x22", "32x32", "64x64")


@lru_cache(maxsize=1)
def load_clients() -> tuple[tuple[str, str, str], ...]:
    """Return ``[(caps_prefix, name, icon), …]`` from ``clients.txt``."""
    entries: list[tuple[str, str, str]] = []
    try:
        with open(CLIENTS_FILE, encoding="utf-8") as handle:
            for line in handle:
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                caps, name, icon = (part.strip() for part in parts[:3])
                if caps:
                    entries.append((caps, name or caps, icon))
    except OSError:
        return ()
    return tuple(entries)


@lru_cache(maxsize=1)
def _by_length() -> tuple[tuple[str, str, str], ...]:
    return tuple(sorted(load_clients(),
                        key=lambda entry: len(entry[0]), reverse=True))


def find_client(node: str) -> tuple[str, str] | None:
    """Return ``(name, icon)`` for a caps *node* (longest prefix wins)."""
    node = str(node or "")
    if not node:
        return None
    for caps, name, icon in _by_length():
        if node == caps or node.startswith(caps):
            return name, icon
    return None


@lru_cache(maxsize=512)
def icon_path(icon: str, size: int = 16) -> str:
    """Absolute path to *icon* in the *size* folder (falling back in size)."""
    if not icon:
        return ""
    preferred = f"{size}x{size}"
    order = [preferred] + [folder for folder in SIZES if folder != preferred]
    for folder in order:
        path = os.path.join(CLIENTS_DIR, folder, icon)
        if os.path.exists(path):
            return path
    return ""


def client_icon_for(node: str, size: int = 16) -> str:
    """Convenience: caps node → icon path (``""`` when unknown)."""
    found = find_client(node)
    return icon_path(found[1], size) if found else ""
