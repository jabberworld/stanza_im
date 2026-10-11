"""Runtime detection of the OMEMO stack.

The OMEMO feature is optional: it needs the ``slixmpp-omemo`` plugin plus the
``python-omemo`` core and at least one backend (``oldmemo`` for legacy OMEMO
0.3, ``twomemo`` for ``urn:xmpp:omemo:2``).  Everything here degrades to a
disabled feature with a human-readable reason instead of raising, so a partial
or missing install never breaks the client.

Detection is **cheap by default**: the module only checks that the packages are
importable (``find_spec``) so merely importing this module never pulls in the
heavy ``oldmemo``/``twomemo``/``xmlschema``/``slixmpp_omemo`` stack.  A real
import (:func:`verify`) is done later — when the OMEMO plugin is actually
registered (login) or, in the "load at startup" mode, from the startup probe —
and it also catches a package that is present but whose *transitive* dependency
is missing (for example ``oldmemo`` raising ``ModuleNotFoundError: xmlschema``).
"""
from __future__ import annotations

import importlib
import importlib.util
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

#: Top-level components that must all be present for the feature to work.
_CORE_MODULES = ("slixmpp_omemo", "omemo", "cryptography")


def _has_spec(module: str) -> bool:
    """Cheap availability check that never imports the module."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _real_import_ok(module: str) -> tuple[bool, str]:
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


def _apply_state(ok_map: dict[str, bool]) -> None:
    """Recompute the module-level availability globals from *ok_map*."""
    global AVAILABLE, BACKENDS, MISSING_MODULES, MISSING, MISSING_DEBIAN
    global WARNING, OMEMO2_CONTENT
    missing = sorted({module for module, ok in ok_map.items() if not ok})
    backends = frozenset(
        backend for backend, module in (
            (BACKEND_LEGACY, "oldmemo"), (BACKEND_OMEMO2, "twomemo"))
        if ok_map.get(module))
    MISSING_MODULES = missing
    MISSING = [_BY_MODULE.get(module, (module, module))[0] for module in missing]
    MISSING_DEBIAN = [_BY_MODULE.get(module, (module, module))[1]
                      for module in missing]
    BACKENDS = backends
    AVAILABLE = all(ok_map.get(module) for module in _CORE_MODULES) and bool(backends)
    WARNING = ("" if AVAILABLE
               else "OMEMO disabled: missing " + ", ".join(MISSING))
    OMEMO2_CONTENT = AVAILABLE and BACKEND_OMEMO2 in BACKENDS


def _compute_missing(probe) -> list[str]:
    """Deduplicated root-cause module names of the components *probe* rejects."""
    causes: list[str] = []
    for module, _name, _deb in _REQUIRED:
        ok, cause = probe(module)
        if not ok:
            causes.append(cause or module)
    return sorted(set(causes))


# ── Initial (cheap, spec-based) state ─────────────────────────────
_apply_state({module: _has_spec(module) for module, _n, _d in _REQUIRED})

#: True once the real import probe (:func:`verify`) has run.
_verified = False


def verify() -> bool:
    """Run the real import probe (once) and return the true availability.

    Called when the OMEMO plugin is about to be registered (login) and, in the
    "load at startup" mode, from the startup probe.  Idempotent: the heavy
    import happens at most once per process.
    """
    global _verified
    if _verified:
        return AVAILABLE
    _verified = True
    ok_map: dict[str, bool] = {}
    for module, _name, _deb in _REQUIRED:
        ok, cause = _real_import_ok(module)
        ok_map[module] = ok
        if not ok and cause:
            # Surface the real root cause (e.g. a missing transitive
            # dependency) instead of / in addition to the top-level module.
            ok_map.setdefault(cause, False)
    _apply_state(ok_map)
    return AVAILABLE


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
