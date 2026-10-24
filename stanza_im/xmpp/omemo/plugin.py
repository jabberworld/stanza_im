"""Custom ``slixmpp-omemo`` plugin: storage + BTBV/strict trust policy.

The stock ``slixmpp_omemo.XEP_0384`` is abstract: it needs a storage backend and
a trust policy.  We supply a per-profile :class:`OmemoStorage` and implement the
two policies the user asked for:

* **BTBV on** — new devices are blindly trusted (encrypted to) and the plugin's
  ``_devices_blindly_trusted`` hook lets the UI warn the user until they are
  verified.
* **BTBV off (strict)** — undecided devices are automatically distrusted (so
  only manually trusted devices receive messages); the hook still lets the UI
  tell the user which devices were excluded.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, FrozenSet, Optional

from slixmpp.plugins.base import register_plugin
from slixmpp_omemo import TrustLevel, XEP_0384
from omemo.storage import Storage
from omemo.types import DeviceInformation

from stanza_im.xmpp.omemo.storage import OmemoStorage

logger = logging.getLogger("stanza_im.omemo")


def _strip_device_labels(element) -> None:
    """Remove the optional label attributes from every ``<device/>``."""
    for node in element.iter():
        if str(node.tag).rsplit("}", 1)[-1] != "device":
            continue
        node.attrib.pop("label", None)
        node.attrib.pop("labelsig", None)


def _install_device_list_compat() -> None:
    """Tolerate ``label``/``labelsig`` in a peer's OMEMO device list.

    Legacy OMEMO 0.3 does not define those attributes (Conversations/Psi+ add
    them anyway) and older OMEMO 2 schemas predate the standard signed label;
    strict validation would drop the whole list, losing every device id.  The
    labels are display metadata only — the device ids/keys are what OMEMO uses
    — so a sanitised retry is safe.
    """
    import copy
    try:
        import oldmemo.etree as old_etree
    except Exception:  # noqa: BLE001 - optional backend
        old_etree = None
    try:
        import twomemo.etree as two_etree
    except Exception:  # noqa: BLE001 - optional backend
        two_etree = None

    if old_etree is not None and not getattr(
            old_etree.parse_device_list, "_stanza_patched", False):
        original_old = old_etree.parse_device_list

        def parse_old(element, _original=original_old):
            sanitised = copy.deepcopy(element)
            _strip_device_labels(sanitised)
            return _original(sanitised)

        parse_old._stanza_patched = True
        old_etree.parse_device_list = parse_old

    if two_etree is not None and not getattr(
            two_etree.parse_device_list, "_stanza_patched", False):
        original_two = two_etree.parse_device_list

        def parse_two(element, _original=original_two):
            try:
                return _original(element)
            except Exception:  # noqa: BLE001 - older schema without labels
                sanitised = copy.deepcopy(element)
                _strip_device_labels(sanitised)
                return _original(sanitised)

        parse_two._stanza_patched = True
        two_etree.parse_device_list = parse_two

    omemo_log = logging.getLogger("slixmpp_omemo.xep_0384")
    if not any(getattr(item, "_stanza_schema_filter", False)
               for item in omemo_log.filters):
        class _SchemaTracebackFilter(logging.Filter):
            _stanza_schema_filter = True

            def filter(self, record):
                exc = record.exc_info[1] if record.exc_info else None
                if (exc is not None
                        and type(exc).__name__ == "XMLSchemaValidationError"):
                    record.exc_info = None
                return True

        omemo_log.addFilter(_SchemaTracebackFilter())


_install_device_list_compat()

#: ``(devices, identifier)`` callback used to surface trust changes in the UI.
TrustCallback = Callable[[FrozenSet[DeviceInformation], Optional[str]], Any]


class OmemoPlugin(XEP_0384):  # noqa: N801 - mirrors the XEP class name
    """Concrete ``xep_0384`` implementation for Stanza IM."""

    default_config = {
        "fallback_message": "This message is OMEMO encrypted.",
        # Path of the per-profile JSON store.
        "storage_path": "",
        # Blind Trust Before Verification (True) vs. strict manual trust.
        "btbv": True,
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._omemo_storage: Optional[Storage] = None
        #: Notified about devices that were blindly trusted.
        self.on_blindly_trusted: Optional[TrustCallback] = None
        #: Notified about devices that had to be decided manually (strict).
        self.on_manual_trust: Optional[TrustCallback] = None

    def plugin_init(self) -> None:
        self._omemo_storage = OmemoStorage(self.storage_path)
        super().plugin_init()

    @property
    def storage(self) -> Storage:
        assert self._omemo_storage is not None
        return self._omemo_storage

    @property
    def _btbv_enabled(self) -> bool:
        # Read dynamically so toggling the setting takes effect immediately.
        return bool(self.btbv)

    def set_btbv(self, enabled: bool) -> None:
        self.btbv = bool(enabled)

    async def _devices_blindly_trusted(
        self,
        blindly_trusted: FrozenSet[DeviceInformation],
        identifier: Optional[str],
    ) -> None:
        if self.on_blindly_trusted is not None:
            await self.on_blindly_trusted(blindly_trusted, identifier)

    async def _prompt_manual_trust(
        self,
        manually_trusted: FrozenSet[DeviceInformation],
        identifier: Optional[str],
    ) -> None:
        # Strict mode: exclude every undecided device so encryption proceeds
        # only to devices the user explicitly trusted.  If none remain, the
        # library raises NoEligibleDevices, which the manager reports.
        session_manager = await self.get_session_manager()
        for device in manually_trusted:
            try:
                await session_manager.set_trust(
                    device.bare_jid,
                    device.identity_key,
                    TrustLevel.DISTRUSTED.name,
                )
            except Exception:  # noqa: BLE001
                logger.debug("OMEMO: could not distrust device %s",
                             device.device_id, exc_info=True)
        if self.on_manual_trust is not None:
            await self.on_manual_trust(manually_trusted, identifier)


register_plugin(OmemoPlugin)
