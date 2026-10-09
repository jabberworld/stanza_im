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
    if _registered:
        return
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
