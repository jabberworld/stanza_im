"""Runtime detection of the OMEMO stack.

The OMEMO feature is optional: it needs the ``slixmpp-omemo`` plugin plus the
``python-omemo`` core and at least one backend (``oldmemo`` for legacy OMEMO
0.3, ``twomemo`` for ``urn:xmpp:omemo:2``).  Everything here degrades to a
disabled feature with a human-readable reason instead of raising, so a partial
or missing install never breaks the client.
"""
from __future__ import annotations

import importlib.util
import logging

logger = logging.getLogger("stanza_im.omemo")

#: Legacy OMEMO 0.3 namespace backend (``oldmemo``).
BACKEND_LEGACY = "legacy"
#: OMEMO 2 (``urn:xmpp:omemo:2``) backend (``twomemo``).
BACKEND_OMEMO2 = "omemo2"

LEGACY_NAMESPACE = "eu.siacs.conversations.axolotl"
OMEMO2_NAMESPACE = "urn:xmpp:omemo:2"


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


_PLUGIN = _module_available("slixmpp_omemo")
_CORE = _module_available("omemo")
_OLD = _module_available("oldmemo")
_NEW = _module_available("twomemo")
_CRYPTO = _module_available("cryptography")

#: Available protocol backends (``BACKEND_LEGACY``/``BACKEND_OMEMO2``).
BACKENDS: frozenset[str] = frozenset(
    backend for backend, ok in (
        (BACKEND_LEGACY, _OLD), (BACKEND_OMEMO2, _NEW)) if ok
)

#: Packages that are required but not importable (for the UI warning).
MISSING: list[str] = []
if not _PLUGIN:
    MISSING.append("slixmpp-omemo")
if not _CORE:
    MISSING.append("python-omemo")
if not _OLD:
    MISSING.append("python-oldmemo")
if not _NEW:
    MISSING.append("python-twomemo")
if not _CRYPTO:
    MISSING.append("python-cryptography")

#: True when the whole feature can be used.
AVAILABLE: bool = _PLUGIN and _CORE and _CRYPTO and bool(BACKENDS)

#: Human-readable reason shown when the feature is disabled.
WARNING: str = (
    "" if AVAILABLE
    else "OMEMO disabled: missing " + ", ".join(MISSING)
)

#: Whether the OMEMO 2 (twomemo) content can be handled.  slixmpp-omemo does
#: not implement Stanza Content Encryption (XEP-0420) yet, so the manager ships
#: its own SCE implementation; that only needs the twomemo backend.
OMEMO2_CONTENT: bool = AVAILABLE and BACKEND_OMEMO2 in BACKENDS

_logged = False


def log_availability() -> None:
    """Log the OMEMO availability once (mirrors the audio-codec warning)."""
    global _logged
    if _logged:
        return
    _logged = True
    if AVAILABLE:
        logger.info("OMEMO available (backends: %s)",
                    ", ".join(sorted(BACKENDS)) or "none")
    else:
        logger.warning("OMEMO unavailable: missing %s", ", ".join(MISSING))


def summary() -> str:
    """Short status line for the About dialog / preferences."""
    if AVAILABLE:
        return "available (" + ", ".join(sorted(BACKENDS)) + ")"
    return "unavailable (missing " + ", ".join(MISSING) + ")"
