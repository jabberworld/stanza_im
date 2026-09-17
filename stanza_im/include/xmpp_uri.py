"""XEP-0147 XMPP URI query components (RFC 5122 / RFC 3986 subset).

The client both produces ``xmpp:`` URIs (copy-contact / copy-conference
actions) and consumes them (clickable links in chat bodies, see
``include/utils.py``): a URI is ``xmpp:<jid>[?<action>[;<key>=<value>…]]``.
Parsing lives here so every surface shares one grammar and is unit-testable.
"""
from __future__ import annotations

import re
from urllib.parse import quote, unquote

# Substring scanner used inside message bodies (URL-like boundaries).
_XMPP_URI_RE = re.compile(
    r"xmpp:[^\s<>\"'&]+",
    re.IGNORECASE,
)


def make_xmpp_uri(jid: str, action: str = "", **params: str) -> str:
    """Build an ``xmpp:`` URI (XEP-0147) for *jid*.

    With no *action* the URI is ``xmpp:<jid>``; a conference copy becomes
    ``xmpp:<room>@<server>?join``.  Extra *params* are appended as
    ``;key=<percent-encoded value>`` query components.
    """
    jid = (jid or "").strip()
    if not jid:
        return ""
    uri = "xmpp:" + quote(jid, safe="@/.~-_")
    if action:
        uri += "?" + quote(action, safe="")
        for key, value in params.items():
            uri += ";" + quote(str(key), safe="")
            if value:
                uri += "=" + quote(str(value), safe="")
    return uri


def parse_xmpp_uri(uri: str) -> dict | None:
    """Parse an ``xmpp:`` URI (XEP-0147).

    Returns ``{"jid": str, "action": str, "params": dict[str, str]}`` or
    ``None`` when *uri* is not a well-formed xmpp: URI.  The JID keeps its
    percent-decoded form; query keys/values are percent-decoded too, and a
    value without ``=`` parses as an empty string.  The address-less form
    ``xmpp:?message;body=…`` (XEP-0147) parses with an empty ``jid``.
    """
    if not isinstance(uri, str) or not _XMPP_URI_RE.fullmatch(uri.strip()):
        return None
    rest = uri[5:]
    jid_part, has_query, query = rest.partition("?")
    jid = unquote(jid_part)
    if not jid and not query:
        return None
    action = ""
    params: dict[str, str] = {}
    if has_query:
        segments = query.split(";")
        action = unquote(segments[0] or "").lower()
        for segment in segments[1:]:
            if not segment:
                continue
            key, sep, value = segment.partition("=")
            kw = unquote(key).lower()
            if not kw:
                continue
            params[kw] = unquote(value) if sep else ""
    return {"jid": jid, "action": action, "params": params}


def extract_xmpp_uris(body: str) -> list[str]:
    """Return every xmpp: URI substring found in *body* (in order)."""
    if not isinstance(body, str):
        return []
    return [match.group(0) for match in _XMPP_URI_RE.finditer(body)]