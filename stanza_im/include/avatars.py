"""vCard avatar helpers: parse PHOTO data, cache to disk, default placeholder.

Avatars are stored as PNG files in ``$XDG_CACHE_HOME/stanza-im/avatars/``.
QPixmap objects are never held here — the roster paints from file paths and
the chat theme inlines a small PNG as a data-URI.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil

from PyQt6 import QtCore, QtGui

from stanza_im.include.constants import AVATARS_DIR

PLACEHOLDER_FILENAME = "_default.png"

_VCARD_NS = "vcard-temp"
_SAFE_RE = re.compile(r"[^A-Za-z0-9_.@-]")
_URI_CACHE: dict[str, str | None] = {}
_MISSING = object()
# A non-ASCII key (a conference nick, a Unicode localpart) is sanitised to
# underscores; the digest keeps two such keys from sharing one file.
_DIGEST_LEN = 10
_PREFIX_MAX = 180


def _key(jid: str) -> str:
    """The cache key: the full occupant JID, else the bare JID."""
    value = str(jid)
    bare, separator, resource = value.partition("/")
    return value if separator and "@" in bare else bare


def _safe_name(jid: str) -> str:
    key = _key(jid)
    safe = _SAFE_RE.sub("_", key)
    if safe != key:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:_DIGEST_LEN]
        safe = f"{safe[:_PREFIX_MAX]}-{digest}"
    return safe


def ensure_dirs() -> None:
    os.makedirs(AVATARS_DIR, exist_ok=True)


def avatar_path(jid: str) -> str:
    """Return the cache path for *jid*'s avatar (bare JID)."""
    return os.path.join(AVATARS_DIR, _safe_name(jid) + ".png")


def has_avatar(jid: str) -> bool:
    return os.path.exists(avatar_path(jid))


def clear_cache() -> int:
    """Delete every cached avatar (keeps the generated placeholder)."""
    _URI_CACHE.clear()
    removed = 0
    try:
        names = os.listdir(AVATARS_DIR)
    except OSError:
        return 0
    for name in names:
        if name == PLACEHOLDER_FILENAME:
            continue
        path = os.path.join(AVATARS_DIR, name)
        if not os.path.isfile(path):
            continue
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed


def save_avatar(jid: str, raw: bytes) -> str:
    """Persist avatar bytes for *jid* and return the cache path."""
    ensure_dirs()
    path = avatar_path(jid)
    with open(path, "wb") as fh:
        fh.write(raw)
    _URI_CACHE.pop(_key(jid), None)
    return path


def ensure_avatar(jid: str, path: str) -> str:
    """Return the canonical cache path, migrating an older-named file.

    The cache name gained a digest suffix for non-ASCII keys; a vCard cache
    may still hand out the old path.  The list paints that path directly while
    the chat resolves the avatar by JID, so the file is copied to the current
    canonical name (the old one is kept) and the data-URI cache is dropped.
    """
    canonical = avatar_path(jid)
    path = str(path or "")
    if path and os.path.isfile(path):
        if os.path.abspath(path) != os.path.abspath(canonical):
            if not os.path.isfile(canonical):
                try:
                    shutil.copyfile(path, canonical)
                except OSError:
                    return path
            _URI_CACHE.pop(_key(jid), None)
        return canonical
    return canonical if os.path.isfile(canonical) else ""


def rounded_avatar(pix: QtGui.QPixmap, size: int,
                   radius_pct: int) -> QtGui.QPixmap:
    """Return *pix* scaled to *size* and clipped to a rounded square.

    *radius_pct* is 0–100 % of the half-size: 0 keeps sharp corners, 100 gives
    a full circle.  Falls back to the plain scaled pixmap for an invalid one.
    """
    if pix.isNull():
        return pix
    scaled = pix.scaled(
        size, size, QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        QtCore.Qt.TransformationMode.SmoothTransformation)
    radius = max(0.0, min(1.0, float(radius_pct) / 100.0)) * (size / 2.0)
    if radius <= 0.0:
        # Sharp corners: centre-crop to the square so nothing shifts.
        out = QtGui.QPixmap(size, size)
        out.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(out)
        painter.drawPixmap((size - scaled.width()) // 2,
                           (size - scaled.height()) // 2, scaled)
        painter.end()
        return out
    out = QtGui.QPixmap(size, size)
    out.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(out)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    clip = QtGui.QPainterPath()
    clip.addRoundedRect(QtCore.QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(clip)
    painter.drawPixmap((size - scaled.width()) // 2,
                       (size - scaled.height()) // 2, scaled)
    painter.end()
    return out


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
    jid = _key(jid)
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
    mime = image_mime(raw)
    if mime == "application/octet-stream":
        return None
    return "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")


def image_mime(raw: bytes) -> str:
    """Sniff the MIME type of a raw avatar image."""
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def image_size(raw: bytes) -> tuple[int, int]:
    """Return the ``(width, height)`` of a raw avatar, or ``(0, 0)``."""
    if not raw:
        return (0, 0)
    try:
        image = QtGui.QImage()
        if image.loadFromData(raw):
            return (image.width(), image.height())
    except Exception:
        pass
    return (0, 0)
