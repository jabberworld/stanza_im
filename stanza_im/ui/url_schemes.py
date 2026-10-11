"""Registration of the app-handled QWebEngine URL schemes.

The ``stanza``/``mam``/``xmpp`` schemes must be registered before the first
``QWebEngineProfile`` is used.  Registration is kept out of the WebEngine
importers so the schemes are set up no matter which WebEngine view is created
first (chat or media viewer); the helper is idempotent.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_registered = False
_profile_configured = False


def ensure_registered() -> None:
    """Register ``stanza``/``mam``/``xmpp`` as application-handled schemes.

    Must run before the first QWebEngineProfile is used.  Knowing the scheme
    stops Chromium from attempting (and erroring on) a real navigation when an
    anchor is clicked; the actual routing still happens in
    ``acceptNavigationRequest``.  The schemes use the ``Path`` syntax (Qt's
    default): everything after ``scheme:`` is preserved verbatim, so Chromium
    keeps the opaque ``stanza:view:…``/``xmpp:…`` anchors intact — the media
    context menu reads that raw link back through ``linkUrl()``.
    """
    global _registered
    if not _registered:
        _registered = True
        try:
            from PyQt6.QtWebEngineCore import QWebEngineUrlScheme
            for name in (b"stanza", b"mam", b"xmpp"):
                scheme = QWebEngineUrlScheme(name)
                scheme.setSyntax(QWebEngineUrlScheme.Syntax.Path)
                scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme)
                QWebEngineUrlScheme.registerScheme(scheme)
            logger.info("Registered custom URL schemes stanza/mam/xmpp")
        except Exception as exc:  # pragma: no cover - optional capability
            logger.warning("Could not register custom URL schemes: %s", exc)
    configure_default_profile()


def configure_default_profile() -> None:
    """Tune the shared ``QWebEngineProfile`` (memory / privacy).

    Runs once, before the first page is created (both WebEngine importers call
    :func:`ensure_registered` at import time).  The HTTP cache size comes from
    ``performance.webengine_cache_mb``; cookies are kept in memory only.  A
    ``QWebEngineProfile`` needs a live ``QApplication``, so this is a no-op (and
    retried on the next call) when none exists yet.
    """
    global _profile_configured
    if _profile_configured:
        return
    try:
        from PyQt6.QtWidgets import QApplication
        if QApplication.instance() is None:
            return
    except Exception:  # pragma: no cover - PyQt6 unavailable
        return
    _profile_configured = True
    try:
        from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
    except Exception:  # pragma: no cover - WebEngine unavailable
        return
    try:
        cache_mb = 50
        try:
            from stanza_im.core.storage import Config
            perf = getattr(Config(), "performance", None)
            cache_mb = int(getattr(perf, "webengine_cache_mb", 50) or 0)
        except Exception:  # noqa: BLE001 - fall back to the default
            pass
        profile = QWebEngineProfile.defaultProfile()
        if cache_mb > 0:
            profile.setHttpCacheMaximumSize(cache_mb * 1024 * 1024)
        try:
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        except Exception:  # noqa: BLE001
            pass
        settings = profile.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        logger.info("Configured default WebEngine profile (cache %d MB)",
                    cache_mb)
    except Exception as exc:  # pragma: no cover - optional capability
        logger.warning("Could not configure the WebEngine profile: %s", exc)
