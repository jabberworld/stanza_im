"""Runtime detection of the OMEMO stack.

The OMEMO feature is optional: it needs the ``slixmpp-omemo`` plugin plus the
``python-omemo`` core and at least one backend (``oldmemo`` for legacy OMEMO
0.3, ``twomemo`` for ``urn:xmpp:omemo:2``).  Everything here degrades to a
disabled feature with a human-readable reason instead of raising, so a partial
or missing install never breaks the client.
"""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger("stanza_im.omemo")

#: Legacy OMEMO 0.3 namespace backend (``oldmemo``).
BACKEND_LEGACY = "legacy"
#: OMEMO 2 (``urn:xmpp:omemo:2``) backend (``twomemo``).
BACKEND_OMEMO2 = "omemo2"

LEGACY_NAMESPACE = "eu.siacs.conversations.axolotl"
OMEMO2_NAMESPACE = "urn:xmpp:omemo:2"


#: ``(import module, friendly name, Debian/Ubuntu package)`` of every component
#: the OMEMO stack needs.  ``xmlschema`` is a transitive dependency of
#: ``oldmemo``/``twomemo`` (their ElementTree helpers) that some distributions
#: do not pull in.
_REQUIRED = (
    ("slixmpp_omemo", "slixmpp-omemo", "python3-slixmpp-omemo"),
    ("omemo", "python-omemo", "python3-omemo"),
    ("oldmemo", "python-oldmemo", "python3-oldmemo"),
    ("twomemo", "python-twomemo", "python3-twomemo"),
    ("xmlschema", "python-xmlschema", "python3-xmlschema"),
    ("cryptography", "python-cryptography", "python3-cryptography"),
)

_BY_MODULE = {module: (name, deb) for module, name, deb in _REQUIRED}


def _probe(module: str) -> tuple[bool, str]:
    """Import *module*; return ``(ok, root_cause_module)``.

    A real import (not ``find_spec``) is used so a module that is present but
    whose transitive import is missing is detected — for example ``oldmemo``
    raising ``ModuleNotFoundError: xmlschema``.  The returned root cause is the
    name of the missing dependency (``exc.name``) so the message can point at
    the real package instead of the top-level one.
    """
    try:
        importlib.import_module(module)
        return True, ""
    except ImportError as exc:
        # A package may re-raise a wrapped ImportError for a missing
        # dependency (``oldmemo`` -> ``xmlschema``); walk the chain to find the
        # real root cause.
        cause: BaseException | None = exc
        while cause is not None:
            if isinstance(cause, ModuleNotFoundError) and cause.name:
                return False, str(cause.name)
            cause = cause.__cause__ or cause.__context__
        return False, module
    except Exception:  # noqa: BLE001 - any import-time failure disables it
        return False, module


def _compute_missing(probe) -> list[str]:
    """Deduplicated root-cause module names of the components *probe* rejects."""
    causes: list[str] = []
    for module, _name, _deb in _REQUIRED:
        ok, cause = probe(module)
        if not ok:
            causes.append(cause or module)
    return sorted(set(causes))


def _available(module: str) -> bool:
    return _probe(module)[0]


_PLUGIN = _available("slixmpp_omemo")
_CORE = _available("omemo")
_OLD = _available("oldmemo")
_NEW = _available("twomemo")
_CRYPTO = _available("cryptography")

#: Available protocol backends (``BACKEND_LEGACY``/``BACKEND_OMEMO2``).
BACKENDS: frozenset[str] = frozenset(
    backend for backend, ok in (
        (BACKEND_LEGACY, _OLD), (BACKEND_OMEMO2, _NEW)) if ok
)

#: Import names of the missing components (root cause) — for diagnostics.
MISSING_MODULES: list[str] = _compute_missing(_probe)

#: Friendly names of the required packages that are not importable.
MISSING: list[str] = [
    _BY_MODULE.get(module, (module, module))[0] for module in MISSING_MODULES
]

#: Debian/Ubuntu packages of the missing components.
MISSING_DEBIAN: list[str] = [
    _BY_MODULE.get(module, (module, module))[1] for module in MISSING_MODULES
]

#: True when the whole feature can be used.
AVAILABLE: bool = _PLUGIN and _CORE and _CRYPTO and bool(BACKENDS)

#: Human-readable reason shown when the feature is disabled.
WARNING: str = (
    "" if AVAILABLE
    else "OMEMO disabled: missing " + ", ".join(MISSING)
)


def install_hint() -> str:
    """A copy-paste install command for the missing components."""
    if not MISSING_DEBIAN:
        return ""
    return "sudo apt install " + " ".join(MISSING_DEBIAN)


def detail() -> str:
    """Multi-line explanation of the OMEMO availability (log/tooltip)."""
    if AVAILABLE:
        return ("OMEMO is available (backends: %s)."
                % (", ".join(sorted(BACKENDS)) or "none"))
    lines = [
        "OMEMO is unavailable: missing Python modules %s."
        % ", ".join(MISSING_MODULES),
        "OMEMO needs slixmpp-omemo (plugin), python-omemo (core), "
        "python-oldmemo (OMEMO 0.3), python-twomemo (OMEMO 2), "
        "python-xmlschema and python-cryptography.",
    ]
    hint = install_hint()
    if hint:
        lines.append("Install: " + hint)
    return "\n".join(lines)

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
        logger.warning("OMEMO unavailable: missing %s (install: %s)",
                       ", ".join(MISSING_MODULES),
                       install_hint() or "n/a")
        for line in detail().splitlines():
            logger.warning("  %s", line)


def summary() -> str:
    """Short status line for the About dialog / preferences."""
    if AVAILABLE:
        return "available (" + ", ".join(sorted(BACKENDS)) + ")"
    return "unavailable (missing " + ", ".join(MISSING) + ")"
