"""In-process OMEMO crypto round-trips (no XMPP server needed).

Builds two ``omemo.SessionManager`` instances backed by an in-memory XMPP
interaction layer and verifies that

* a ``urn:xmpp:omemo:2`` message encrypted with our SCE envelope decrypts back
  to the original body (this is the path slixmpp-omemo 2.2.0 does not provide),
* a legacy ``eu.siacs.conversations.axolotl`` body round-trips as well.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_omemo_crypto.py
"""
import asyncio
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_omemo_crypto_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import oldmemo
import oldmemo.etree
import twomemo
import twomemo.etree
from omemo.session_manager import SessionManager
from omemo.storage import Just, Nothing, Storage
from omemo.types import TrustLevel

from stanza_im.xmpp.omemo import sce

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── in-memory XMPP interaction layer ────────────────────────────────────────

REGISTRY = {"bundles": {}, "devices": {}}
_OWN = [""]


class MemStorage(Storage):
    def __init__(self):
        super().__init__()
        self.data = {}

    async def _load(self, key):
        return Just(self.data[key]) if key in self.data else Nothing()

    async def _store(self, key, value):
        self.data[key] = value

    async def _delete(self, key):
        self.data.pop(key, None)


class TestSessionManager(SessionManager):
    @staticmethod
    async def _upload_bundle(bundle):
        REGISTRY["bundles"][
            (bundle.namespace, bundle.bare_jid, bundle.device_id)] = bundle

    @staticmethod
    async def _download_bundle(namespace, bare_jid, device_id):
        return REGISTRY["bundles"][(namespace, bare_jid, device_id)]

    @staticmethod
    async def _delete_bundle(namespace, device_id):
        pass

    @staticmethod
    async def _upload_device_list(namespace, device_list):
        REGISTRY["devices"].setdefault(namespace, {})[_OWN[0]] = device_list

    @staticmethod
    async def _download_device_list(namespace, bare_jid):
        return REGISTRY["devices"].get(namespace, {}).get(bare_jid, {})

    @staticmethod
    async def _send_message(message, bare_jid):
        pass

    async def _evaluate_custom_trust_level(self, device):
        return TrustLevel.TRUSTED

    async def _make_trust_decision(self, undecided, identifier):
        for device in undecided:
            await self.set_trust(device.bare_jid, device.identity_key,
                                 "TRUSTED")


async def _make(bare, storage):
    _OWN[0] = bare
    return await TestSessionManager.create(
        [twomemo.Twomemo(storage), oldmemo.Oldmemo(storage)],
        storage, bare, None, "UNDECIDED")


async def _roundtrips():
    alice = await _make("alice@example.com", MemStorage())
    bob = await _make("bob@example.com", MemStorage())
    await alice.refresh_device_lists("bob@example.com")
    results = {}

    # ── OMEMO 2 / SCE ───────────────────────────────────────────
    message_elt = ET.fromstring(
        "<message xmlns='jabber:client'><body>hi bob</body></message>")
    envelope = sce.build_envelope(
        sce.collect_content(message_elt), "alice@example.com",
        to_jid="bob@example.com")
    msgs, errors = await alice.encrypt(
        frozenset({"bob@example.com"}),
        {twomemo.twomemo.NAMESPACE: sce.serialize(envelope)},
        backend_priority_order=[twomemo.twomemo.NAMESPACE])
    results["omemo2_errors"] = errors
    results["omemo2_n"] = len(msgs)
    message = next(iter(msgs))
    element = twomemo.etree.serialize_message(message)
    parsed = twomemo.etree.parse_message(element, "alice@example.com")
    plaintext, device, _ = await bob.decrypt(parsed)
    results["omemo2_device"] = device.device_id
    decrypted = sce.parse(plaintext)
    content = sce.extract_content(decrypted)
    results["omemo2_body"] = next(
        c for c in content if c.tag == "{jabber:client}body").text
    results["omemo2_from"] = sce.affix(decrypted, "from").get("jid")

    # ── legacy OMEMO 0.3 ────────────────────────────────────────
    msgs2, _ = await alice.encrypt(
        frozenset({"bob@example.com"}),
        {oldmemo.oldmemo.NAMESPACE: b"legacy hi"},
        backend_priority_order=[oldmemo.oldmemo.NAMESPACE])
    element2 = oldmemo.etree.serialize_message(next(iter(msgs2)))
    parsed2 = await oldmemo.etree.parse_message(
        element2, "alice@example.com", "bob@example.com", bob)
    plaintext2, _, _ = await bob.decrypt(parsed2)
    results["legacy_body"] = plaintext2
    return results


res = asyncio.run(_roundtrips())

check("OMEMO 2 encryption reports no errors", not res["omemo2_errors"])
check("OMEMO 2 produces exactly one message", res["omemo2_n"] == 1)
check("OMEMO 2 SCE body round-trips", res["omemo2_body"] == "hi bob")
check("OMEMO 2 SCE from affix is the sender",
      res["omemo2_from"] == "alice@example.com")
check("OMEMO 2 decryption reports the sender device",
      res["omemo2_device"] > 0)
check("legacy OMEMO 0.3 body round-trips", res["legacy_body"] == b"legacy hi")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All OMEMO crypto tests passed.")
