"""Tests for Jingle Encrypted Transports helpers (XEP-0391/0396).

Covers the ``<security/>`` element, the streaming AES-128-GCM cipher (chunked,
tampered and truncated input) and the transfer encryption policy.

Run with:
    python3 tests/test_jet.py
"""
import os
import sys
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.xmpp import jet

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _q(ns, tag):
    return "{%s}%s" % (ns, tag)


DATA = bytes(range(256)) * 300 + b"the tail of the file"
SECRET = jet.TransportSecret(b"k" * jet.KEY_SIZE, b"i" * jet.IV_SIZE)

# 1. the stream cipher -------------------------------------------------------
for chunk in (1, 7, 16, 61, 4096):
    enc = jet.StreamEncryptor(SECRET)
    blob = b"".join(enc.update(DATA[i:i + chunk])
                    for i in range(0, len(DATA), chunk)) + enc.finish()
    check("the ciphertext is the data plus one tag (%d-byte chunks)" % chunk,
          len(blob) == len(DATA) + jet.TAG_SIZE)
    dec = jet.StreamDecryptor(SECRET)
    out = b"".join(dec.update(blob[i:i + chunk])
                   for i in range(0, len(blob), chunk)) + dec.finish()
    check("decryption restores the data (%d-byte chunks)" % chunk, out == DATA)

# 2. tampered / truncated input ---------------------------------------------
def _decrypt_all(blob, chunk=1024):
    dec = jet.StreamDecryptor(SECRET)
    out = b""
    for i in range(0, len(blob), chunk):
        out += dec.update(blob[i:i + chunk])
    return out + dec.finish()


tampered = bytearray(blob)
tampered[len(tampered) // 2] ^= 0x01
try:
    _decrypt_all(bytes(tampered))
    rejected = False
except jet.JetError:
    rejected = True
check("a tampered stream is rejected", rejected)

try:
    _decrypt_all(blob[:-1])
    truncated = False
except jet.JetError:
    truncated = True
check("a truncated stream is rejected", truncated)

try:
    _decrypt_all(b"")
    empty = False
except jet.JetError:
    empty = True
check("an empty stream is rejected", empty)

# 3. the <security/> element -------------------------------------------------
content = ET.Element(_q(jet.NS_JET, "content"))
content.set("name", "file-1")
envelope = ET.SubElement(content, _q(jet.NS_LEGACY_OMEMO, "encrypted"))
security = jet.build_security("file-1", envelope)
content.append(security)
check("the security names the content and the cipher",
      security.get("name") == "file-1"
      and security.get("cipher") == jet.CIPHER_AES_128_GCM
      and security.get("type") == jet.NS_LEGACY_OMEMO)
status, parsed = jet.parse_security(content)
check("a JET-OMEMO security is recognised",
      status == jet.SECURITY_OK and parsed is envelope)

security.set("cipher", jet.CIPHER_AES_128_GCM + ":0")
status, _parsed = jet.parse_security(content)
check("the ':0' cipher spelling is accepted", status == jet.SECURITY_OK)

security.set("cipher", "urn:xmpp:ciphers:other")
status, parsed = jet.parse_security(content)
check("an unknown cipher is unsupported",
      status == jet.SECURITY_UNSUPPORTED and parsed is None)

security.set("cipher", jet.CIPHER_AES_128_GCM)
security.set("type", "urn:xmpp:omemo:2")
status, _parsed = jet.parse_security(content)
check("an unsupported envelope type is unsupported",
      status == jet.SECURITY_UNSUPPORTED)

plain = ET.Element(_q(jet.NS_JET, "content"))
status, parsed = jet.parse_security(plain)
check("a content without security is plain",
      status == jet.SECURITY_NONE and parsed is None)

# 4. the encryption policy ---------------------------------------------------
for mode, supports, omemo, want in (
        ("off", True, True, jet.OUT_PLAIN),
        ("prefer", True, True, jet.OUT_ENCRYPT),
        ("prefer", False, True, jet.OUT_PLAIN),
        ("prefer", True, False, jet.OUT_PLAIN),
        ("require", True, True, jet.OUT_ENCRYPT),
        ("require", False, True, jet.OUT_REFUSE),
        ("require", True, False, jet.OUT_REFUSE),
        ("strict", False, False, jet.OUT_REFUSE)):
    got = jet.outgoing_decision(mode, peer_supports=supports,
                                omemo_ready=omemo)
    check("outgoing %s (peer=%s omemo=%s) -> %s"
          % (mode, supports, omemo, want), got == want)

check("an incoming encrypted offer is decrypted",
      jet.incoming_decision("prefer", offer_encrypted=True) == jet.IN_DECRYPT)
check("incoming plain is accepted in require",
      jet.incoming_decision("require", offer_encrypted=False) == jet.IN_PLAIN)
check("incoming plain is rejected in strict",
      jet.incoming_decision("strict", offer_encrypted=False) == jet.IN_REJECT)
check("an unknown mode falls back to prefer",
      jet.normalize_mode("bogus") == "prefer"
      and jet.outgoing_decision("bogus", peer_supports=False,
                                omemo_ready=True) == jet.OUT_PLAIN)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All JET tests passed.")
