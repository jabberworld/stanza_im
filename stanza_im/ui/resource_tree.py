"""Render a contact's per-resource client blocks as rich HTML.

Shared by the roster tooltip and the vCard Status tab so both show the same
tree: a status icon before the resource name, then — aligned under the name's
first letter — the local time on its own line, the client line and the status
message.  All resources share **one** table (no blank line between them).
"""
from __future__ import annotations

from urllib.parse import quote

from stanza_im.i18n import tr
from stanza_im.include import clients as clients_mod
from stanza_im.include.constants import find_icon
from stanza_im.include.utils import (escape_html, local_time_from_tzo,
                                     status_icon_html)


def resource_tree_html(blocks: list[dict], link_prefix: str = "",
                       link_title: str = "") -> str:
    """Render *blocks* as one aligned ``<table>``.

    A block is ``{"resource", "show", "status", "client", "version", "tzo",
    "caps_node", "full_jid"}`` (``tzo`` is the XEP-0202 offset, turned into a
    live local time).  When *link_prefix* is set and a block carries
    ``full_jid``, its status icon and resource name become links to
    ``link_prefix + urlencoded full_jid`` (the vCard opens the client
    capabilities viewer this way; the roster tooltip passes no prefix).
    """
    clock = find_icon("clock.svg")
    rows: list[str] = []
    for info in blocks:
        rows.extend(_block_rows(info, clock, link_prefix, link_title))
    if not rows:
        return ""
    return ('<table cellspacing="0" cellpadding="0" border="0">'
            + "".join(rows) + "</table>")


def _block_rows(info: dict, clock: str, link_prefix: str = "",
                link_title: str = "") -> list[str]:
    rows: list[str] = []
    name = escape_html(str(info.get("resource") or "*"))
    icon_html = status_icon_html(str(info.get("show") or ""))
    name_html = f"<b>{name}</b>"
    full_jid = str(info.get("full_jid") or "")
    if link_prefix and full_jid:
        href = link_prefix + quote(full_jid, safe="")
        title = (f' title="{escape_html(link_title)}"' if link_title else "")
        icon_html = f'<a href="{href}"{title}>{icon_html}</a>'
        name_html = f'<a href="{href}"{title}>{name_html}</a>'
    rows.append(
        f'<tr><td valign="top">{icon_html}</td><td>{name_html}</td></tr>')
    local = local_time_from_tzo(str(info.get("tzo") or ""))
    if local:
        rows.append(
            f'<tr><td></td><td><img src="{clock}" width="16" height="16"> '
            f'{escape_html(local)}</td></tr>')
    client = str(info.get("client") or "")
    version = str(info.get("version") or "")
    os_name = str(info.get("os") or "")
    client_name = (client + (" " + version if version else "")).strip()
    if client_name:
        icon = clients_mod.client_icon_for(
            str(info.get("caps_node") or ""), 16)
        prefix = (f'<img src="{icon}" width="16" height="16"> ' if icon else "")
        line = f'{tr("tooltip_client")}: {escape_html(client_name)}'
        if os_name:
            line += " / " + escape_html(os_name)
        rows.append(f'<tr><td></td><td>{prefix}{line}</td></tr>')
    status = str(info.get("status") or "")
    if status.strip():
        status_html = escape_html(status).replace("\n", "<br>")
        rows.append(f'<tr><td></td><td>{tr("tooltip_status")}: '
                    f'{status_html}</td></tr>')
    return rows
