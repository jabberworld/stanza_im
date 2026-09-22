"""Server capability report used by the "Server info" dialog.

The preset XEP list is evaluated against several sources, because a server
advertises different capabilities in different places:

* the account domain's ``disco#info`` (server features),
* the account's bare JID ``disco#info`` (PEP, stanza IDs, bookmark/avatar
  conversion),
* the conference and HTTP-upload components discovered via ``disco#items``,
* the raw ``<stream:features>`` namespaces,
* the domain's ad-hoc command list (XEP-0401).

``evaluate_server_xeps`` is pure so it can be tested without a connection.
"""
from __future__ import annotations

import asyncio
import logging
from typing import NamedTuple

from stanza_im.core.client import (
    NS_DATA, NS_DISCO_INFO, _upload_max_file_size)
from stanza_im.include.utils import format_size

logger = logging.getLogger(__name__)

# XEP-0157: server contact addresses (disco#info serverinfo data form).
SERVER_INFO_NODE = "http://jabber.org/network/serverinfo"
CONTACT_FIELDS = ("abuse-addresses", "admin-addresses", "feedback-addresses",
                  "sales-addresses", "security-addresses", "status-addresses",
                  "support-addresses")

# Feature namespace -> (XEP, name) for the "Capabilities" list.  Keys ending
# with "*" match by prefix; the longest match wins.
_EXTRA_FEATURE_XEPS: tuple[tuple[str, str, str], ...] = (
    ("jabber:iq:last", "XEP-0012", "Last Activity"),
    ("jabber:iq:privacy", "XEP-0016", "Privacy Lists"),
    ("jabber:x:data", "XEP-0004", "Data Forms"),
    ("jabber:x:oob", "XEP-0066", "Out of Band Data"),
    ("jabber:x:conference", "XEP-0249", "Direct MUC Invitation"),
    ("jabber:iq:search", "XEP-0055", "Jabber Search"),
    ("jabber:iq:private", "XEP-0049", "Private XML Storage"),
    ("vcard-temp:x:update", "XEP-0153", "vCard-Based Avatars"),
    ("storage:bookmarks", "XEP-0048", "Bookmarks"),
    ("http://jabber.org/protocol/disco#*", "XEP-0030", "Service Discovery"),
    ("http://jabber.org/protocol/stats", "XEP-0039", "Statistics Gathering"),
    ("http://jabber.org/protocol/offline", "XEP-0013",
     "Flexible Offline Message Retrieval"),
    ("http://jabber.org/protocol/rosterx", "XEP-0144", "Roster Item Exchange"),
    ("http://jabber.org/protocol/pubsub*", "XEP-0060", "Publish-Subscribe"),
    ("http://jabber.org/protocol/chatstates", "XEP-0085",
     "Chat State Notifications"),
    ("http://jabber.org/protocol/caps", "XEP-0115", "Entity Capabilities"),
    ("http://jabber.org/protocol/muc*", "XEP-0045", "Multi-User Chat"),
    ("urn:xmpp:avatar:*", "XEP-0084", "User Avatar"),
    ("urn:xmpp:receipts", "XEP-0184", "Message Delivery Receipts"),
    ("urn:xmpp:features:rosterver", "XEP-0237", "Roster Versioning"),
    ("urn:xmpp:message-correct:*", "XEP-0308", "Last Message Correction"),
    ("urn:xmpp:chat-markers:0", "XEP-0333", "Displayed Markers"),
    ("urn:xmpp:jingle-message:0", "XEP-0353", "Jingle Message Initiation"),
    ("urn:xmpp:jingle:apps:file-transfer:*", "XEP-0234",
     "Jingle File Transfer"),
    ("urn:xmpp:jingle:apps:rtp:*", "XEP-0167", "Jingle RTP Sessions"),
    ("urn:xmpp:jingle:transports:ice-udp:*", "XEP-0176",
     "Jingle ICE-UDP Transport"),
    ("urn:xmpp:jingle:transports:s5b:*", "XEP-0260",
     "Jingle SOCKS5 Bytestreams"),
    ("urn:xmpp:jingle:transports:ibb:*", "XEP-0261",
     "Jingle In-Band Bytestreams"),
    ("urn:xmpp:jingle:jet:*", "XEP-0272", "Multiparty Jingle (Muji)"),
    ("urn:xmpp:jingle:1", "XEP-0166", "Jingle"),
    ("urn:xmpp:mam:*", "XEP-0313", "Message Archive Management"),
    ("urn:xmpp:hats:*", "XEP-0317", "Hats"),
    ("urn:xmpp:occupant-id:0", "XEP-0421", "Occupant IDs"),
    ("urn:xmpp:styling:0", "XEP-0393", "Message Styling"),
    ("urn:xmpp:reply:0", "XEP-0461", "Message Replies"),
    ("urn:xmpp:message-retract:*", "XEP-0424", "Message Retraction"),
    ("urn:xmpp:message-moderate:*", "XEP-0425",
     "Moderated Message Retraction"),
    ("urn:xmpp:fallback:0", "XEP-0428", "Fallback Indication"),
    ("urn:xmpp:reporting:*", "XEP-0377", "Blocking Command Reports"),
    ("urn:xmpp:push:0", "XEP-0357", "Push Notifications"),
    ("urn:xmpp:mucsub:0", "XEP-0405", "MUC Sub"),
    ("urn:xmpp:bookmarks-conversion:0", "XEP-0411", "Bookmarks Conversion"),
    ("urn:xmpp:pep-vcard-conversion:0", "XEP-0398",
     "User Avatar to vCard Conversion"),
    ("urn:xmpp:http:upload*", "XEP-0363", "HTTP File Upload"),
    ("urn:xmpp:blocking", "XEP-0191", "Blocking Command"),
    ("urn:xmpp:ping", "XEP-0199", "XMPP Ping"),
    ("urn:xmpp:time", "XEP-0202", "Entity Time"),
    ("urn:xmpp:extdisco:*", "XEP-0215", "External Service Discovery"),
    ("urn:xmpp:carbons:*", "XEP-0280", "Message Carbons"),
    ("urn:xmpp:sm:*", "XEP-0198", "Stream Management"),
    ("urn:xmpp:csi:0", "XEP-0352", "Client State Indication"),
    ("urn:xmpp:bind:0", "XEP-0386", "Bind 2"),
    ("urn:xmpp:sasl:*", "XEP-0388", "Extensible SASL Profile"),
    ("urn:xmpp:invite*", "XEP-0401",
     "Ad-hoc Account Invitation Generation"),
    ("urn:xmpp:sec-label:*", "XEP-0258", "Security Labels in XMPP"),
    ("urn:xmpp:sid:0", "XEP-0359", "Unique and Stable Stanza IDs"),
    ("urn:xmpp:mds:*", "XEP-0490", "Message Displayed Synchronization"),
    ("urn:xmpp:bookmarks:1*", "XEP-0402", "PEP Native Bookmarks"),
)


def _feature_map() -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for entry in SERVER_XEPS:
        for key in entry.keys:
            mapping.setdefault(key, (entry.xep, entry.name))
    for key, xep, name in _EXTRA_FEATURE_XEPS:
        mapping.setdefault(key, (xep, name))
    return mapping


_FEATURE_XEPS: dict[str, tuple[str, str]] = {}


def describe_feature(feature: str) -> str:
    """``"XEP-0092: Software Version"`` for a namespace, else the namespace."""
    best = ""
    for key in _FEATURE_XEPS:
        prefix = key[:-1] if key.endswith("*") else key
        if feature == key or (key.endswith("*") and feature.startswith(prefix)):
            if len(prefix) > len(best):
                best = key
    if not best:
        return feature
    xep, name = _FEATURE_XEPS[best]
    return f"{xep}: {name}"


def describe_features(features) -> list[str]:
    """Sorted, de-duplicated ``describe_feature`` lines."""
    return sorted({describe_feature(str(feature))
                   for feature in (features or ()) if feature})


class ServerXep(NamedTuple):
    """One preset XEP entry of the server report."""

    xep: str
    name: str
    source: str             # "disco" | "account" | "stream" | "commands"
    keys: tuple[str, ...]   # feature namespaces (a trailing "*" = prefix)
    alt_keys: tuple[tuple[str, ...], ...] = ()  # all keys of a group


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
    ServerXep("XEP-0163", "Personal Eventing Protocol", "account",
              ("http://jabber.org/protocol/pubsub#pep",),
              (("http://jabber.org/protocol/pubsub",
                "http://jabber.org/protocol/pubsub#publish-options"),)),
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
    ServerXep("XEP-0401", "Ad-hoc Account Invitation Generation", "commands",
              ("urn:xmpp:invite*",)),
    ServerXep("XEP-0402", "PEP Native Bookmarks", "disco",
              ("urn:xmpp:bookmarks:1#compat",
               "urn:xmpp:bookmarks:1#compat-pep")),
    ServerXep("XEP-0411", "Bookmarks Conversion", "disco",
              ("urn:xmpp:bookmarks-conversion:0",)),
    ServerXep("XEP-0490", "Message Displayed Synchronization (server assist)",
              "account", ("urn:xmpp:mds:server-assist:0",)),
)

_FEATURE_XEPS = _feature_map()


def _matches(values: set[str], keys: tuple[str, ...]) -> bool:
    for key in keys:
        if key.endswith("*"):
            if any(value.startswith(key[:-1]) for value in values):
                return True
        elif key in values:
            return True
    return False


def _matches_any(values: set[str], entry: ServerXep) -> bool:
    if _matches(values, entry.keys):
        return True
    return any(all(key in values for key in group)
               for group in entry.alt_keys)


def evaluate_server_xeps(context: dict) -> list[dict]:
    """Return one row per preset XEP: ``{xep, name, supported, detail}``."""
    disco = set(context.get("disco") or ())
    account = set(context.get("account") or ())
    stream = set(context.get("stream") or ())
    commands = set(context.get("commands") or ())
    upload_max = context.get("upload_max")
    rows: list[dict] = []
    for entry in SERVER_XEPS:
        values = {"stream": stream, "account": account,
                  "commands": commands}.get(entry.source, disco)
        supported = _matches_any(values, entry)
        detail = ""
        if entry.xep == "XEP-0363" and supported and upload_max:
            detail = format_size(int(upload_max))
        rows.append({"xep": entry.xep, "name": entry.name,
                     "supported": supported, "detail": detail})
    return rows


def parse_server_contacts(xml) -> list[tuple[str, list[str]]]:
    """XEP-0157 contact addresses: ``[(field, [value, …]), …]``.

    Looks for the ``jabber:x:data`` form whose FORM_TYPE is
    ``http://jabber.org/network/serverinfo`` and returns the known
    ``*-addresses`` fields in the XEP's order (empty fields are skipped).
    """
    if xml is None:
        return []
    form = None
    for candidate in xml.iter("{%s}x" % NS_DATA):
        form_type = ""
        for field in candidate.findall("{%s}field" % NS_DATA):
            if str(field.get("var") or "") != "FORM_TYPE":
                continue
            value = field.find("{%s}value" % NS_DATA)
            form_type = str(value.text or "") if value is not None else ""
        if form_type == SERVER_INFO_NODE:
            form = candidate
            break
    if form is None:
        return []
    by_var: dict[str, list[str]] = {}
    for field in form.findall("{%s}field" % NS_DATA):
        var = str(field.get("var") or "")
        if var not in CONTACT_FIELDS:
            continue
        values = [str(value.text or "").strip()
                  for value in field.findall("{%s}value" % NS_DATA)]
        by_var[var] = [value for value in values if value]
    return [(var, by_var[var]) for var in CONTACT_FIELDS if by_var.get(var)]


async def _disco(client, jid: str) -> tuple[set[str], dict, object]:
    """Return ``(features, server_identity, xml)`` for *jid*."""
    features: set[str] = set()
    identity = {"name": "", "type": ""}
    xml = None
    try:
        info = await client.xmpp["xep_0030"].get_info(jid=jid)
        xml = getattr(info, "xml", None)
        if xml is not None:
            features = {str(el.get("var") or "") for el in xml.iter(
                "{%s}feature" % NS_DISCO_INFO)}
            for el in xml.iter("{%s}identity" % NS_DISCO_INFO):
                if str(el.get("category") or "") == "server":
                    identity = {"name": str(el.get("name") or ""),
                                "type": str(el.get("type") or "")}
    except Exception:
        logger.debug("Server disco#info failed for %s", jid, exc_info=True)
    return features, identity, xml


async def service_details(client, jid: str, node: str = "") -> dict:
    """``disco#info`` of *jid*: features, XEP-0157 contacts and identity."""
    features: list[str] = []
    contacts: list[tuple[str, list[str]]] = []
    identity = {"name": "", "type": "", "category": ""}
    try:
        info = await client.xmpp["xep_0030"].get_info(jid=jid,
                                                       node=node or None)
        xml = getattr(info, "xml", None)
    except Exception:
        logger.debug("Service disco#info failed for %s", jid, exc_info=True)
        return {"features": features, "contacts": contacts,
                "identity": identity}
    if xml is not None:
        features = [str(el.get("var") or "") for el in
                    xml.iter("{%s}feature" % NS_DISCO_INFO)
                    if el.get("var")]
        contacts = parse_server_contacts(xml)
        for el in xml.iter("{%s}identity" % NS_DISCO_INFO):
            name = str(el.get("name") or "")
            if name and not identity["name"]:
                identity["name"] = name
            category = str(el.get("category") or "")
            if category and not identity["category"]:
                identity["category"] = category
                identity["type"] = str(el.get("type") or "")
    return {"features": features, "contacts": contacts, "identity": identity}


async def _safe(coro, default):
    """Await *coro*, returning *default* on any failure."""
    try:
        return await coro
    except Exception:
        logger.debug("Server info query failed", exc_info=True)
        return default


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
    ((domain_feats, identity, domain_xml), (account_feats, _, _), muc, upload,
     commands) = await asyncio.gather(
        _disco(client, domain),
        _disco(client, client.jid_str),
        _safe(client.discover_conference_service(), ""),
        _safe(client._http_upload_service(), ""),
        _safe(client.get_commands_list(domain), []),
        return_exceptions=True,
    )
    features = set(domain_feats) | set(account_feats)
    if muc:
        muc_feats, _, _ = await _disco(client, muc)
        features |= muc_feats
    upload_max = None
    if upload:
        upload_feats, _, upload_xml = await _disco(client, upload)
        features |= upload_feats
        upload_max = _upload_max_file_size(upload_xml) or None
    command_nodes = {str(item.get("node") or "") for item in (commands or [])}
    stream = set(getattr(client.xmpp, "stream_feature_ns", set()))
    login = ""
    try:
        login = str(client.connection_info().get("sasl") or "")
    except Exception:
        login = ""
    software = await _software(client, domain, identity)
    contacts = parse_server_contacts(domain_xml)
    if not contacts:
        info_xml = await _safe(_server_info_xml(client, domain), None)
        contacts = parse_server_contacts(info_xml)
    return {"domain": domain, "disco": features, "account": set(account_feats),
            "stream": stream, "commands": command_nodes, "login": login,
            "identity": identity, "software": software,
            "upload_max": upload_max, "contacts": contacts}


async def _server_info_xml(client, domain: str):
    """Fetch the XEP-0157 serverinfo node when the plain disco#info lacks it."""
    info = await client.xmpp["xep_0030"].get_info(jid=domain,
                                                  node=SERVER_INFO_NODE)
    return getattr(info, "xml", None)
