"""Jingle Encrypted Transports (XEP-0391) with OMEMO keys (XEP-0396).

A Jingle transport — in practice a file transfer — is encrypted with a
symmetric key that travels in a ``<security/>`` element as an OMEMO
KeyTransportMessage (an OMEMO message with encrypted keys and no payload).
The data stream is one AES-128-GCM stream whose 16-byte authentication tag is
appended at the end, which is what Conversations and Dino implement.

Only the legacy OMEMO profile (``eu.siacs.conversations.axolotl``) is
supported: Conversations and Dino speak nothing else, and the OMEMO 2 variant
of the envelope is a Psi extension that is not part of XEP-0396.
"""
from __future__ import annotations

import base64
import hmac
from dataclasses import dataclass
from xml.etree import ElementTree as ET

NS_JET = "urn:xmpp:jingle:jet:0"
NS_JET_OMEMO = "urn:xmpp:jingle:jet-omemo:0"
NS_LEGACY_OMEMO = "eu.siacs.conversations.axolotl"

#: The cipher as Conversations/Dino write it (XEP-0396 names ``…:0``).
CIPHER_AES_128_GCM = "urn:xmpp:ciphers:aes-128-gcm-nopadding"
_CIPHERS = (CIPHER_AES_128_GCM, CIPHER_AES_128_GCM + ":0")

KEY_SIZE = 16
IV_SIZE = 12
TAG_SIZE = 16

#: The transfer encryption policy (``files.encryption``).
MODES = ("off", "prefer", "require", "strict")

SECURITY_NONE = "none"
SECURITY_OK = "ok"
SECURITY_UNSUPPORTED = "unsupported"

OUT_ENCRYPT = "encrypt"
OUT_PLAIN = "plain"
OUT_REFUSE = "refuse"
IN_DECRYPT = "decrypt"
IN_PLAIN = "plain"
IN_REJECT = "reject"


class JetError(Exception):
    """The encrypted stream is broken, truncated or not authentic."""


@dataclass(frozen=True)
class TransportSecret:
    """The AES-128 key and IV that protect one transfer."""

    key: bytes
    iv: bytes


def _q(ns: str, tag: str) -> str:
    return "{%s}%s" % (ns, tag)


def build_security(content_name: str,
                   encrypted: ET.Element) -> ET.Element:
    """The ``<security/>`` element carrying an OMEMO key transport envelope."""
    el = ET.Element(_q(NS_JET, "security"))
    el.set("name", str(content_name))
    el.set("cipher", CIPHER_AES_128_GCM)
    el.set("type", NS_LEGACY_OMEMO)
    el.append(encrypted)
    return el


def parse_security(content: ET.Element) -> tuple[str, ET.Element | None]:
    """Classify a content's ``<security/>`` element.

    Returns ``(SECURITY_NONE, None)`` when the offer is not encrypted,
    ``(SECURITY_OK, <encrypted/>)`` when it can be decrypted here and
    ``(SECURITY_UNSUPPORTED, None)`` when the peer wants encryption we cannot
    provide (an offer must never be treated as plain in that case).
    """
    el = content.find(_q(NS_JET, "security"))
    if el is None:
        return SECURITY_NONE, None
    cipher = (el.get("cipher") or "").strip()
    kind = (el.get("type") or "").strip()
    encrypted = el.find(_q(kind, "encrypted")) if kind else None
    if cipher not in _CIPHERS or kind != NS_LEGACY_OMEMO or encrypted is None:
        return SECURITY_UNSUPPORTED, None
    return SECURITY_OK, encrypted


# ── Policy ────────────────────────────────────────────────────────

def normalize_mode(mode: str) -> str:
    return mode if mode in MODES else "prefer"


def outgoing_decision(mode: str, *, peer_supports: bool,
                      omemo_ready: bool) -> str:
    """What to do with a transfer we start (see the ``OUT_*`` constants)."""
    mode = normalize_mode(mode)
    if mode == "off":
        return OUT_PLAIN
    if peer_supports and omemo_ready:
        return OUT_ENCRYPT
    return OUT_PLAIN if mode == "prefer" else OUT_REFUSE


def incoming_decision(mode: str, *, offer_encrypted: bool) -> str:
    """What to do with a transfer a peer starts (see the ``IN_*`` constants)."""
    mode = normalize_mode(mode)
    if offer_encrypted:
        return IN_DECRYPT
    return IN_REJECT if mode == "strict" else IN_PLAIN


# ── Stream cipher ─────────────────────────────────────────────────

def _crypto():
    # ``cryptography`` ships with the optional OMEMO stack, so it is imported
    # only when a transfer is actually encrypted.
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    return Cipher, algorithms, modes


class StreamEncryptor:
    """One AES-128-GCM stream; :meth:`finish` returns the authentication tag."""

    def __init__(self, secret: TransportSecret) -> None:
        Cipher, algorithms, modes = _crypto()
        self._enc = Cipher(algorithms.AES(secret.key),
                           modes.GCM(secret.iv)).encryptor()

    def update(self, data: bytes) -> bytes:
        return self._enc.update(data) if data else b""

    def finish(self) -> bytes:
        tail = self._enc.finalize()
        return tail + self._enc.tag


class StreamDecryptor:
    """Decrypt an AES-128-GCM stream whose tag is appended at the end.

    GCM's own decryptor needs the tag up front, so the data is decrypted with
    the equivalent CTR keystream (counter block ``IV‖2``, as in GCM) and the
    tag is verified by encrypting the recovered plaintext again with GCM —
    the same approach Psi uses.  The last 16 bytes are held back until the
    stream ends.
    """

    def __init__(self, secret: TransportSecret) -> None:
        Cipher, algorithms, modes = _crypto()
        counter = bytes(secret.iv) + b"\x00\x00\x00\x02"
        self._dec = Cipher(algorithms.AES(secret.key),
                           modes.CTR(counter)).decryptor()
        self._verify = Cipher(algorithms.AES(secret.key),
                              modes.GCM(secret.iv)).encryptor()
        self._pending = b""

    def update(self, data: bytes) -> bytes:
        """Feed ciphertext; returns the plaintext that is safe to store."""
        if data:
            self._pending += data
        if len(self._pending) <= TAG_SIZE:
            return b""
        head = self._pending[:-TAG_SIZE]
        self._pending = self._pending[-TAG_SIZE:]
        plain = self._dec.update(head)
        self._verify.update(plain)
        return plain

    def finish(self) -> bytes:
        """Consume the tag; raises :class:`JetError` on truncation/mismatch."""
        if len(self._pending) != TAG_SIZE:
            raise JetError("the encrypted stream is truncated")
        tag, self._pending = self._pending, b""
        self._verify.finalize()
        expected = self._verify.tag
        if not hmac.compare_digest(expected, tag):
            raise JetError("the encrypted stream failed authentication")
        return b""


# ── OMEMO key transport ───────────────────────────────────────────

async def encrypt_key_transport(sm, own_bare: str, peer: str,
                                legacy_ns: str):
    """Build a legacy OMEMO KeyTransportMessage carrying a JET key.

    Returns ``(TransportSecret, <encrypted/>)`` or ``None`` when the peer has
    no device reachable through the legacy profile (the envelope would be
    useless to it).
    """
    import oldmemo.etree

    bare = str(peer).split("/", 1)[0]
    devices = await sm.get_device_information(bare)
    peer_ids = {device.device_id for device in devices
                if legacy_ns in device.namespaces}
    if not peer_ids:
        return None
    messages, _errors = await sm.encrypt(
        frozenset({bare}), {legacy_ns: b""},
        backend_priority_order=[legacy_ns], identifier=bare)
    for message, material in (messages or {}).items():
        if message.namespace != legacy_ns:
            continue
        covered = {key.device_id for key, _exchange in message.keys}
        if not covered & peer_ids:
            continue
        secret = TransportSecret(
            bytes(material.key),
            bytes(message.content.initialization_vector))
        return secret, oldmemo.etree.serialize_message(message)
    return None


async def decrypt_key_transport(sm, own_bare: str, encrypted: ET.Element,
                                sender_bare: str):
    """Recover ``(TransportSecret, device)`` from a key transport envelope."""
    import oldmemo.etree

    message = await oldmemo.etree.parse_message(
        encrypted, str(sender_bare), str(own_bare), sm)
    if message is None:
        return None
    plaintext, device, material = (await sm.decrypt(message))[:3]
    if plaintext is not None or material is None:
        return None
    # The library replaces the content of a payload-less message with a fresh
    # empty one (and a random IV), so read the transmitted IV from the wire.
    legacy_ns = (encrypted.tag[1:].split("}", 1)[0]
                 if encrypted.tag.startswith("{") else "")
    header = encrypted.find(_q(legacy_ns, "header")) if legacy_ns else None
    iv_el = header.find(_q(legacy_ns, "iv")) if header is not None else None
    if iv_el is None or not (iv_el.text or "").strip():
        return None
    try:
        iv = base64.b64decode(iv_el.text.strip())
    except Exception:  # noqa: BLE001
        return None
    if len(iv) != IV_SIZE:
        return None
    return TransportSecret(bytes(material.key), iv), device
