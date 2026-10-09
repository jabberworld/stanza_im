"""High-level OMEMO operations used by the client and the UI.

Wraps the ``slixmpp-omemo`` plugin/session manager and adds the pieces the
plugin does not provide:

* a SCE (XEP-0420) implementation for ``urn:xmpp:omemo:2`` content, which
  slixmpp-omemo 2.2.0 lacks (it only encrypts/decrypts legacy OMEMO 0.3);
* per-chat encryption modes stored next to the OMEMO state;
* fingerprint formatting and trust helpers for the UI.

All heavy imports happen lazily so a missing stack never breaks the client.
"""
from __future__ import annotations

import logging
from copy import copy
from typing import FrozenSet, Iterable, Optional

from stanza_im.xmpp.omemo import sce

logger = logging.getLogger("stanza_im.omemo")

MODE_OFF = "off"
MODE_OMEMO = "omemo"


def _namespaces():
    import oldmemo
    import oldmemo.etree
    import twomemo
    import twomemo.etree
    return oldmemo.oldmemo.NAMESPACE, twomemo.twomemo.NAMESPACE


class NullOmemo:
    """No-op stand-in used when the OMEMO stack is unavailable."""

    available = False
    warning = ""

    def __init__(self, client) -> None:
        self._client = client

    def is_encrypted(self, stanza) -> set[str]:
        return set()

    def chat_mode(self, jid: str) -> str:
        return MODE_OFF

    def set_chat_mode(self, jid: str, mode: str) -> None:
        pass

    def fingerprint(self, identity_key: bytes) -> str:
        return ""

    def trust_level_name(self, device) -> str:
        return ""

    def on_client_ready(self) -> None:
        pass


class OmemoManager:
    """Facade over the OMEMO plugin for one account (one profile)."""

    available = True

    def __init__(self, client) -> None:
        self._client = client
        self._plugin = client.xmpp["xep_0384"]
        self._own_bare = client.jid_str
        #: Cached plaintexts of outgoing MUC messages, keyed by stanza id.
        self._reflection_cache: dict[str, dict[str, bytes]] = {}
        # UI hooks (set by MainWindow); called with (devices, identifier).
        self._plugin.on_blindly_trusted = self._on_blindly_trusted
        self._plugin.on_manual_trust = self._on_manual_trust
        self.on_devices_changed = None
        self.on_trust_warning = None
        #: Mirror device names to the account's private PEP node (opt-in).
        self.alias_sync = False
        #: Learned ``"jid/id" -> display label`` (resource + client name).
        self._device_resources: dict[str, str] = {}

    # ── callbacks from the plugin ───────────────────────────────

    async def _on_blindly_trusted(self, devices, identifier) -> None:
        if self.on_trust_warning is not None:
            self.on_trust_warning("blindly_trusted", devices, identifier)
        if self.on_devices_changed is not None:
            self.on_devices_changed()

    async def _on_manual_trust(self, devices, identifier) -> None:
        if self.on_trust_warning is not None:
            self.on_trust_warning("distrusted", devices, identifier)
        if self.on_devices_changed is not None:
            self.on_devices_changed()

    def on_client_ready(self) -> None:
        """Called when a session starts.

        The plugin already builds the session manager on ``session_bind``; this
        hook is a no-op placeholder kept for symmetry with the plugin API.
        """
        return None

    def set_btbv(self, enabled: bool) -> None:
        self._plugin.set_btbv(enabled)

    # ── low-level access ────────────────────────────────────────

    async def session_manager(self):
        return await self._plugin.get_session_manager()

    def is_encrypted(self, stanza) -> set[str]:
        try:
            return self._plugin.is_encrypted(stanza)
        except Exception:  # noqa: BLE001
            return set()

    async def own_device(self):
        sm = await self.session_manager()
        return (await sm.get_own_device_information())[0]

    async def devices(self, bare_jid: str):
        sm = await self.session_manager()
        return await sm.get_device_information(bare_jid)

    async def refresh_device_lists(self, jids: Iterable[str],
                                   force: bool = False) -> None:
        from slixmpp import JID
        await self._plugin.refresh_device_lists(
            {JID(j) for j in jids}, force_download=force)

    async def set_trust(self, bare_jid: str, identity_key: bytes,
                        level_name: str) -> None:
        sm = await self.session_manager()
        await sm.set_trust(bare_jid, identity_key, level_name)

    async def set_own_label(self, label: Optional[str]) -> None:
        sm = await self.session_manager()
        await sm.set_own_label(label)

    async def ensure_own_label(self, resource: str) -> None:
        """Give our own device a readable label if it has none yet."""
        try:
            device = await self.own_device()
        except Exception:  # noqa: BLE001
            return
        if getattr(device, "label", None):
            return
        from stanza_im.include.constants import APP_NAME
        label = f"{APP_NAME} · {resource}".strip(" ·")
        if label:
            await self.set_own_label(label[:53])

    # ── pure helpers ────────────────────────────────────────────

    def fingerprint(self, identity_key: bytes) -> str:
        """Human-readable fingerprint (groups of hex) for an identity key."""
        if not identity_key:
            return ""
        from omemo.session_manager import SessionManager
        return " ".join(SessionManager.format_identity_key(identity_key))

    def trust_level_name(self, device) -> str:
        return str(getattr(device, "trust_level_name", "") or "")

    def is_trusted(self, device) -> bool:
        return self.trust_level_name(device) in ("TRUSTED", "BLINDLY_TRUSTED")

    # ── per-chat mode ───────────────────────────────────────────

    def _modes(self) -> dict:
        data = self._plugin.storage.get_app("chat_modes", {})
        return data if isinstance(data, dict) else {}

    def chat_mode(self, jid: str) -> str:
        mode = self._modes().get(jid, MODE_OFF)
        return MODE_OMEMO if mode == MODE_OMEMO else MODE_OFF

    def set_chat_mode(self, jid: str, mode: str) -> None:
        modes = self._modes()
        if mode == MODE_OMEMO:
            modes[jid] = MODE_OMEMO
        else:
            modes.pop(jid, None)
        self._plugin.storage.set_app("chat_modes", modes)

    # ── device names / aliases / last-seen ──────────────────────

    def _aliases(self) -> dict:
        data = self._plugin.storage.get_app("device_aliases", {})
        return data if isinstance(data, dict) else {}

    def device_alias(self, jid: str, device_id: int) -> str:
        return str(self._aliases().get(f"{jid}/{device_id}", "") or "")

    def set_device_alias(self, jid: str, device_id: int, name: str) -> None:
        aliases = self._aliases()
        key = f"{jid}/{device_id}"
        if name:
            aliases[key] = name
        else:
            aliases.pop(key, None)
        self._plugin.storage.set_app("device_aliases", aliases)
        if self.alias_sync:
            self._schedule_alias_publish()

    def device_name(self, jid: str, device_id: int, label: str = "") -> str:
        """Best display name: user alias, learned name, label, else the id."""
        return (self.device_alias(jid, device_id)
                or self._device_resources.get(f"{jid}/{device_id}", "")
                or (label or "")
                or f"Device {device_id}")

    def note_device_resource(self, jid: str, device_id: int,
                             label: str) -> None:
        """Remember a device's resource/client name (auto-naming fallback)."""
        if label:
            self._device_resources[f"{jid}/{device_id}"] = label

    # ── server-side alias sync ──────────────────────────────────

    def _alias_entries(self) -> list[dict]:
        aliases = self._aliases()
        seen = self._seen_map()
        entries: list[dict] = []
        for key, alias in aliases.items():
            jid, _, device_id = key.rpartition("/")
            if not jid or not device_id:
                continue
            entries.append({"jid": jid, "id": device_id, "alias": alias,
                            "last_seen": seen.get(key, "")})
        return entries

    def _schedule_alias_publish(self) -> None:
        import asyncio
        try:
            asyncio.ensure_future(self._publish_aliases())
        except RuntimeError:
            pass

    async def _publish_aliases(self) -> None:
        try:
            await self._client.set_omemo_aliases(self._alias_entries())
        except Exception:  # noqa: BLE001
            logger.debug("OMEMO alias publish failed", exc_info=True)

    async def sync_aliases(self) -> None:
        """Merge the server-side aliases into the local store (local wins)."""
        try:
            entries = await self._client.get_omemo_aliases()
        except Exception:  # noqa: BLE001
            return
        if not entries:
            return
        aliases = self._aliases()
        seen = self._seen_map()
        changed = False
        for entry in entries:
            key = f"{entry.get('jid', '')}/{entry.get('id', '')}"
            if not entry.get("jid") or not entry.get("id"):
                continue
            if entry.get("alias") and key not in aliases:
                aliases[key] = entry["alias"]
                changed = True
            if entry.get("last_seen"):
                try:
                    if float(entry["last_seen"]) > float(seen.get(key, 0)):
                        seen[key] = entry["last_seen"]
                        changed = True
                except (TypeError, ValueError):
                    pass
        if changed:
            self._plugin.storage.set_app("device_aliases", aliases)
            self._plugin.storage.set_app("device_last_seen", seen)

    def _seen_map(self) -> dict:
        data = self._plugin.storage.get_app("device_last_seen", {})
        return data if isinstance(data, dict) else {}

    def note_device_seen(self, jid: str, device_id: int) -> None:
        import time
        seen = self._seen_map()
        seen[f"{jid}/{device_id}"] = time.time()
        self._plugin.storage.set_app("device_last_seen", seen)

    def device_last_seen(self, jid: str, device_id: int) -> float:
        try:
            return float(self._seen_map().get(f"{jid}/{device_id}", 0.0))
        except (TypeError, ValueError):
            return 0.0

    def muc_recipients(self, room: str) -> set[str]:
        """Bare real JIDs of a room's members (for OMEMO group chat)."""
        recipients: set[str] = set()
        users = getattr(self._client, "_muc_users", {}).get(room, {})
        for info in users.values():
            real = info.get("real_jid")
            if real and str(real).lower() not in ("", "none"):
                recipients.add(str(real).split("/")[0])
        # Include ourselves so our other devices can read the room too.
        recipients.add(self._own_bare)
        return recipients

    async def purge_device(self, device) -> None:
        """Remove one of our own devices from the published device lists."""
        legacy_ns, omemo2_ns = _namespaces()
        sm = await self.session_manager()
        own, others = await sm.get_own_device_information()
        target = int(device.device_id)
        keep = [own] + [d for d in others if int(d.device_id) != target]
        device_list = {int(d.device_id): None for d in keep}
        for namespace in (omemo2_ns, legacy_ns):
            await sm.update_device_list(namespace, self._own_bare, device_list)
        self.set_device_alias(self._own_bare, target, "")

    # ── encryption / decryption ─────────────────────────────────

    async def encrypt(self, stanza, recipients: Iterable[str],
                      identifier: Optional[str] = None):
        """Encrypt *stanza* for *recipients* (bare JIDs).

        Returns ``(encrypted_stanza | None, errors)``.  Builds both the legacy
        (oldmemo) and the SCE (twomemo) plaintexts and lets the session manager
        pick the version per recipient device.
        """
        import oldmemo
        import oldmemo.etree
        import twomemo
        import twomemo.etree
        from slixmpp import JID

        legacy_ns, omemo2_ns = _namespaces()
        bare = frozenset(JID(j).bare for j in recipients)
        if not bare:
            raise ValueError("OMEMO: no recipients")

        await self.refresh_device_lists(bare)

        plaintexts: dict[str, bytes] = {}
        body = stanza.get("body", None)
        if body is not None:
            plaintexts[legacy_ns] = body.encode("utf-8")

        content = sce.collect_content(stanza.xml)
        to_jid = next(iter(bare)) if len(bare) == 1 else ""
        envelope = sce.build_envelope(content, self._own_bare, to_jid=to_jid)
        plaintexts[omemo2_ns] = sce.serialize(envelope)

        sm = await self.session_manager()
        messages, errors = await sm.encrypt(
            bare, plaintexts,
            backend_priority_order=[omemo2_ns, legacy_ns],
            identifier=identifier,
        )

        encrypted = copy(stanza)
        encrypted.clear()
        encrypted["body"] = self._plugin.fallback_message
        encrypted.enable("store")

        namespaces: set[str] = set()
        for message in messages:
            namespace = message.namespace
            namespaces.add(namespace)
            if namespace == omemo2_ns:
                element = twomemo.etree.serialize_message(message)
            elif namespace == legacy_ns:
                element = oldmemo.etree.serialize_message(message)
            else:
                raise ValueError(f"OMEMO: unknown namespace {namespace}")
            encrypted.append(element)

        # XEP-0380: advertise the encryption method.
        if namespaces:
            primary = omemo2_ns if omemo2_ns in namespaces else legacy_ns
            try:
                encrypted["eme"]["namespace"] = primary
                encrypted["eme"]["name"] = "OMEMO"
            except (KeyError, AttributeError):
                logger.debug("OMEMO: could not set EME element")

        if stanza.get_type() == "groupchat" and encrypted["id"]:
            self._reflection_cache[encrypted["id"]] = plaintexts

        return encrypted, errors

    async def decrypt(self, stanza):
        """Decrypt an OMEMO stanza.

        Returns ``(decrypted_stanza, device_information)``.  Raises the library
        exceptions on failure (the caller reports them to the user).
        """
        import oldmemo
        import oldmemo.etree
        import twomemo
        import twomemo.etree

        legacy_ns, omemo2_ns = _namespaces()
        from_jid = stanza.get_from()
        sender_bare = from_jid.bare
        if stanza.get_type() == "groupchat":
            xep_0045 = self._client.xmpp["xep_0045"]
            real = xep_0045.get_jid_property(from_jid.bare, from_jid.resource,
                                             "jid")
            if real:
                sender_bare = str(real).split("/")[0]

        tw_elts = stanza.xml.findall(f"{{{omemo2_ns}}}encrypted")
        old_elts = stanza.xml.findall(f"{{{legacy_ns}}}encrypted")

        message = None
        if tw_elts:
            message = twomemo.etree.parse_message(tw_elts[0], sender_bare)
        elif old_elts:
            sm = await self.session_manager()
            message = await oldmemo.etree.parse_message(
                old_elts[0], sender_bare, self._own_bare, sm)
        if message is None:
            raise ValueError("OMEMO: no supported encrypted content")

        sm = await self.session_manager()
        from omemo.session_manager import MessageNotForUs
        try:
            plaintext, device_information = (await sm.decrypt(message))[:2]
        except MessageNotForUs:
            if stanza.get_type() != "groupchat":
                raise
            cached = self._reflection_cache.pop(stanza["id"], None)
            if cached is None:
                raise
            plaintext = cached.get(message.namespace)
            device_information = (await sm.get_own_device_information())[0]

        decrypted = copy(stanza)
        try:
            del decrypted["body"]
        except (KeyError, AttributeError):
            pass
        for elt in list(decrypted.xml):
            if elt.tag in (f"{{{omemo2_ns}}}encrypted",
                           f"{{{legacy_ns}}}encrypted"):
                decrypted.xml.remove(elt)

        if message.namespace == omemo2_ns:
            if plaintext is None:
                raise ValueError("OMEMO: empty SCE payload")
            envelope = sce.parse(plaintext)
            self._verify_affixes(envelope, sender_bare, stanza)
            for child in sce.extract_content(envelope):
                decrypted.xml.append(child)
        else:
            if plaintext is not None:
                decrypted["body"] = plaintext.decode("utf-8")

        return decrypted, device_information

    def _verify_affixes(self, envelope, sender_bare: str, stanza) -> None:
        from_elt = sce.affix(envelope, "from")
        if from_elt is not None and from_elt.get("jid") != sender_bare:
            raise ValueError("OMEMO: SCE 'from' affix mismatch")
        to_elt = sce.affix(envelope, "to")
        if to_elt is not None:
            expected = (stanza.get_to().bare
                        if stanza.get_type() == "groupchat"
                        else self._own_bare)
            if to_elt.get("jid") not in (expected, self._own_bare):
                raise ValueError("OMEMO: SCE 'to' affix mismatch")
