"""OMEMO (XEP-0384) support: optional, detected at runtime.

Importing this package is safe even without the OMEMO stack; the heavy modules
(``plugin``/``manager``) must only be imported when
:data:`stanza_im.xmpp.omemo.availability.AVAILABLE` is true.
"""
from __future__ import annotations

from stanza_im.xmpp.omemo import availability

__all__ = ["availability"]
