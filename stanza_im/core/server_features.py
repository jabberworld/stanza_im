"""Server capability report used by the "Server info" dialog.

The preset XEP list is evaluated against the account domain's ``disco#info``
features, the raw ``<stream:features>`` namespaces and the negotiated SASL
mechanism.  ``evaluate_server_xeps`` is pure so it can be tested without a
network connection.
"""
from __future__ import annotations

import logging
from typing import NamedTuple

from stanza_im.core.client import NS_DISCO_INFO
from stanza_im.include.utils import format_size

logger = logging.getLogger(__name__)


class ServerXep(NamedTuple):
    """One preset XEP entry of the server report."""

    xep: str
    name: str
    source: str            # "disco" or "stream"
    keys: tuple[str, ...]  # feature namespaces (a trailing "*" = prefix)


# Server-detectable extensions, ordered by XEP number.
SERVER_XEPS: tuple[ServerXep, ...] = (
    ServerXep("XEP-0045", "Multi-User Chat", "disco",
              ("http://jabber.org/protocol/muc",)),
    ServerXep("XEP-0050", "Ad-Hoc Commands", "disco",
              ("http://jabber.org/protocol/commands",)),
    ServerXep("XEP-0054", "vcard-temp", "disco", ("vcard-temp",)),
    ServerXep("XEP-0059", "Result Set Management", "disco",
              ("http://jabber.org/protocol/rsm",)),
    ServerXep("XEP-0060", "Publish-Subscribe", "disco",
              ("http://jabber.org/protocol/pubsub",)),
    ServerXep("XEP-0077", "In-Band Registration", "disco",
              ("jabber:iq:register",)),
    ServerXep("XEP-0092", "Software Version", "disco",
              ("jabber:iq:version",)),
    ServerXep("XEP-0163", "Personal Eventing Protocol", "disco",
              ("http://jabber.org/protocol/pubsub#pep",)),
    ServerXep("XEP-0191", "Blocking Command", "disco",
              ("urn:xmpp:blocking",)),
    ServerXep("XEP-0198", "Stream Management", "stream",
              ("urn:xmpp:sm:3", "urn:xmpp:sm:2")),
    ServerXep("XEP-0199", "XMPP Ping", "disco", ("urn:xmpp:ping",)),
    ServerXep("XEP-0202", "Entity Time", "disco", ("urn:xmpp:time",)),
    ServerXep("XEP-0215", "External Service Discovery", "disco",
              ("urn:xmpp:extdisco:2", "urn:xmpp:extdisco:1")),
    ServerXep("XEP-0237", "Roster Versioning", "stream",
              ("urn:xmpp:features:rosterver",)),
    ServerXep("XEP-0258", "Security Labels in XMPP", "disco",
              ("urn:xmpp:sec-label:0",)),
    ServerXep("XEP-0280", "Message Carbons", "disco",
              ("urn:xmpp:carbons:2",)),
    ServerXep("XEP-0313", "Message Archive Management", "disco",
              ("urn:xmpp:mam:2", "urn:xmpp:mam:1", "urn:xmpp:mam:0")),
    ServerXep("XEP-0352", "Client State Indication", "stream",
              ("urn:xmpp:csi:0",)),
    ServerXep("XEP-0359", "Unique and Stable Stanza IDs", "disco",
              ("urn:xmpp:sid:0",)),
    ServerXep("XEP-0363", "HTTP File Upload", "disco",
              ("urn:xmpp:http:upload*",)),
    ServerXep("XEP-0386", "Bind 2", "stream", ("urn:xmpp:bind:0",)),
    ServerXep("XEP-0388", "Extensible SASL Profile", "stream",
              ("urn:xmpp:sasl:2",)),
    ServerXep("XEP-0398", "User Avatar to vCard Conversion", "disco",
              ("urn:xmpp:pep-vcard-conversion:0",)),
    ServerXep("XEP-0401", "Easy User Onboarding", "stream",
              ("urn:xmpp:invite",)),
    ServerXep("XEP-0402", "PEP Native Bookmarks", "disco",
              ("urn:xmpp:bookmarks:1", "urn:xmpp:bookmarks:1#compat",
               "urn:xmpp:bookmarks:1#compat-pep")),
    ServerXep("XEP-0411", "Bookmarks Conversion", "disco",
              ("urn:xmpp:bookmarks-conversion:0",)),
    ServerXep("XEP-0490", "Message Displayed Synchronization", "disco",
              ("urn:xmpp:mds:displayed:0", "urn:xmpp:mds:server-assist:0")),
)


def _matches(values: set[str], keys: tuple[str, ...]) -> bool:
    for key in keys:
        if key.endswith("*"):
            if any(value.startswith(key[:-1]) for value in values):
                return True
        elif key in values:
            return True
    return False


def evaluate_server_xeps(context: dict) -> list[dict]:
    """Return one row per preset XEP: ``{xep, name, supported, detail}``."""
    disco = set(context.get("disco") or ())
    stream = set(context.get("stream") or ())
    upload_max = context.get("upload_max")
    rows: list[dict] = []
    for entry in SERVER_XEPS:
        values = stream if entry.source == "stream" else disco
        supported = _matches(values, entry.keys)
        detail = ""
        if entry.xep == "XEP-0363" and supported and upload_max:
            detail = format_size(int(upload_max))
        rows.append({"xep": entry.xep, "name": entry.name,
                     "supported": supported, "detail": detail})
    return rows


async def _disco(client, domain: str) -> tuple[set[str], dict]:
    """Return the domain's ``disco#info`` features and server identity."""
    features: set[str] = set()
    identity = {"name": "", "type": ""}
    try:
        info = await client.xmpp["xep_0030"].get_info(jid=domain)
        xml = getattr(info, "xml", None)
        if xml is not None:
            features = {str(el.get("var") or "") for el in xml.iter(
                "{%s}feature" % NS_DISCO_INFO)}
            for el in xml.iter("{%s}identity" % NS_DISCO_INFO):
                if str(el.get("category") or "") == "server":
                    identity = {"name": str(el.get("name") or ""),
                                "type": str(el.get("type") or "")}
    except Exception:
        logger.debug("Server disco#info failed for %s", domain, exc_info=True)
    return features, identity


async def _software(client, domain: str, identity: dict) -> str:
    """Return ``"<name> <version>"`` from XEP-0092 (falling back to disco)."""
    name = str(identity.get("name") or "")
    version = ""
    try:
        result = await client.xmpp.plugin["xep_0092"].get_version(domain)
        stanza = result["software_version"]
        name = str(stanza.get("name", "") or name)
        version = str(stanza.get("version", "") or "")
    except Exception:
        logger.debug("Server version query failed for %s", domain,
                     exc_info=True)
    return (name + " " + version).strip()


async def collect_server_features(client) -> dict:
    """Gather everything the "Server info" dialog needs to render."""
    domain = client.jid_str.split("@")[-1]
    disco, identity = await _disco(client, domain)
    stream = set(getattr(client.xmpp, "stream_feature_ns", set()))
    login = ""
    try:
        login = str(client.connection_info().get("sasl") or "")
    except Exception:
        login = ""
    software = await _software(client, domain, identity)
    upload_max = None
    try:
        upload_max = await client.http_upload_limit()
    except Exception:
        upload_max = None
    return {"domain": domain, "disco": disco, "stream": stream,
            "login": login, "identity": identity, "software": software,
            "upload_max": upload_max}
