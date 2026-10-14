"""Render a contact's per-resource client blocks as rich HTML.

Shared by the roster tooltip and the vCard Status tab so both show the same
tree: a status icon before the resource name, then — aligned under the name's
first letter — the local time on its own line, the client line and the status
message.  All resources share **one** table (no blank line between them).
"""
from __future__ import annotations

from stanza_im.i18n import tr
from stanza_im.include import clients as clients_mod
from stanza_im.include.constants import find_icon
from stanza_im.include.utils import (escape_html, local_time_from_tzo,
                                     status_icon_html)


def resource_tree_html(blocks: list[dict]) -> str:
    """Render *blocks* as one aligned ``<table>``.

    A block is ``{"resource", "show", "status", "client", "version", "tzo",
    "caps_node"}`` (``tzo`` is the XEP-0202 offset, turned into a live local
    time).
    """
    clock = find_icon("clock.svg")
    rows: list[str] = []
    for info in blocks:
        rows.extend(_block_rows(info, clock))
    if not rows:
        return ""
    return ('<table cellspacing="0" cellpadding="0" border="0">'
            + "".join(rows) + "</table>")


def _block_rows(info: dict, clock: str) -> list[str]:
    rows: list[str] = []
    name = escape_html(str(info.get("resource") or "*"))
    rows.append(
        f'<tr><td valign="top">{status_icon_html(str(info.get("show") or ""))}'
        f'</td><td><b>{name}</b></td></tr>')
    local = local_time_from_tzo(str(info.get("tzo") or ""))
    if local:
        rows.append(
            f'<tr><td></td><td><img src="{clock}" width="16" height="16"> '
            f'{escape_html(local)}</td></tr>')
    client = str(info.get("client") or "")
    version = str(info.get("version") or "")
    client_name = (client + (" " + version if version else "")).strip()
    if client_name:
        icon = clients_mod.client_icon_for(
            str(info.get("caps_node") or ""), 16)
        prefix = (f'<img src="{icon}" width="16" height="16"> ' if icon else "")
        rows.append(f'<tr><td></td><td>{prefix}{tr("tooltip_client")}: '
                    f'{escape_html(client_name)}</td></tr>')
    status = str(info.get("status") or "")
    if status.strip():
        status_html = escape_html(status).replace("\n", "<br>")
        rows.append(f'<tr><td></td><td>{tr("tooltip_status")}: '
                    f'{status_html}</td></tr>')
    return rows
