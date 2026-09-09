"""vCard avatar helpers: parse PHOTO data, cache to disk, default placeholder.

Avatars are stored as PNG files in ``$XDG_CACHE_HOME/stanza-im/avatars/``.
QPixmap objects are never held here — the roster paints from file paths and
the chat theme inlines a small PNG as a data-URI.
"""
from __future__ import annotations

import base64
import os
import re

from PyQt6 import QtCore, QtGui

from stanza_im.include.constants import AVATARS_DIR

PLACEHOLDER_FILENAME = "_default.png"

_VCARD_NS = "vcard-temp"
_SAFE_RE = re.compile(r"[^A-Za-z0-9_.@-]")
_URI_CACHE: dict[str, str | None] = {}
_MISSING = object()


def _safe_name(jid: str) -> str:
    value = str(jid)
    bare, separator, resource = value.partition("/")
    key = value if separator and "@" in bare else bare
    return _SAFE_RE.sub("_", key)


def ensure_dirs() -> None:
    os.makedirs(AVATARS_DIR, exist_ok=True)


def avatar_path(jid: str) -> str:
    """Return the cache path for *jid*'s avatar (bare JID)."""
    return os.path.join(AVATARS_DIR, _safe_name(jid) + ".png")


def has_avatar(jid: str) -> bool:
    return os.path.exists(avatar_path(jid))


def save_avatar(jid: str, raw: bytes) -> str:
    """Persist avatar bytes for *jid* and return the cache path."""
    ensure_dirs()
    path = avatar_path(jid)
    with open(path, "wb") as fh:
        fh.write(raw)
    value = str(jid)
    bare, separator, resource = value.partition("/")
    key = value if separator and "@" in bare else bare
    _URI_CACHE.pop(key, None)
    return path


def default_avatar() -> str:
    """Return the neutral placeholder avatar, generating it on first use."""
    path = os.path.join(AVATARS_DIR, PLACEHOLDER_FILENAME)
    if not os.path.exists(path):
        ensure_dirs()
        pix = QtGui.QPixmap(64, 64)
        pix.fill(QtGui.QColor(178, 178, 178))
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QColor(255, 255, 255))
        font = painter.font()
        font.setPixelSize(30)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pix.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "?")
        painter.end()
        pix.save(path)
    return path


def default_avatar_uri() -> str:
    """Return a PNG data-URI for the neutral placeholder avatar."""
    uri = _URI_CACHE.get("__default__")
    if uri is None:
        path = default_avatar()
        with open(path, "rb") as fh:
            uri = png_data_uri(fh.read())
        _URI_CACHE["__default__"] = uri
    return uri or ""


def avatar_data_uri(jid: str) -> str | None:
    """Return a PNG data-URI for *jid*'s cached avatar, or ``None``."""
    jid = str(jid)
    bare, separator, resource = jid.partition("/")
    jid = jid if separator and "@" in bare else bare
    uri = _URI_CACHE.get(jid, _MISSING)
    if uri is not _MISSING:
        return uri
    path = avatar_path(jid)
    uri = None
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            uri = png_data_uri(fh.read())
    _URI_CACHE[jid] = uri
    return uri


def avatar_file_data_uri(path: str) -> str | None:
    """Return a data URI for an already resolved avatar cache path."""
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as fh:
            return png_data_uri(fh.read())
    except OSError:
        return None


_VCARD_NS = "vcard-temp"


def parse_vcard_photo(vcard_iq) -> bytes | None:
    """Extract the base64 PHOTO data from a vCard IQ (XEP-0054).

    Works directly on the XML payload so it does not depend on slixmpp's
    interface registration.  Returns ``None`` when the card has no photo.
    """
    try:
        payload = vcard_iq.get_payload()
    except Exception:
        return None
    if not payload:
        return None
    if not isinstance(payload, list):
        payload = [payload]
    for root in payload:
        for photo in root.iter(f"{{{_VCARD_NS}}}PHOTO"):
            binval = photo.findtext(f"{{{_VCARD_NS}}}BINVAL")
            if binval:
                try:
                    raw = base64.b64decode(binval)
                except (ValueError, TypeError):
                    continue
                if raw:
                    return bytes(raw)
    return None


def png_data_uri(raw: bytes) -> str | None:
    """Return an image data URI for common vCard photo formats."""
    if not raw:
        return None
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif raw[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif raw[:6] in (b"GIF87a", b"GIF89a"):
        mime = "image/gif"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        return None
    return "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")
