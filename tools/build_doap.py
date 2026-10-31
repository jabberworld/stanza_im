#!/usr/bin/env python3
"""Generate ``doap.xml`` (XEP-0453) from ``XEPs.md``.

Run after changing the supported XEP list:

    python3 tools/build_doap.py

The project metadata lives here; the ``xmpp:SupportedXep`` entries are derived
from the XEP table so the DOAP file can never silently drift from ``XEPs.md``.
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XEPS_MD = os.path.join(ROOT, "XEPs.md")
DOAP_XML = os.path.join(ROOT, "doap.xml")

# SupportedXep status overrides (XEP number -> status).  Everything else is
# "complete".  XEP-0096 was superseded by XEP-0234 and is not used.
STATUS = {
    "0096": "wontfix",
}

RFC_IMPLEMENTS = (
    "6120", "6121", "6122", "7590", "7622",
)


def xep_numbers() -> list[str]:
    """The XEP numbers listed in the XEPs.md table (stable order, unique)."""
    with open(XEPS_MD, encoding="utf-8") as fh:
        text = fh.read()
    numbers: list[str] = []
    for num in re.findall(r"^\|\s*XEP-(\d{4})\s*\|", text, re.MULTILINE):
        if num not in numbers:
            numbers.append(num)
    return numbers


def build() -> str:
    lines = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        "<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'",
        "         xmlns='http://usefulinc.com/ns/doap#'",
        "         xmlns:xmpp='https://linkmauve.fr/ns/xmpp-doap#'",
        "         xmlns:schema='https://schema.org/'>",
        "  <Project xml:lang='en'>",
        "    <name>Stanza IM</name>",
        "    <shortdesc xml:lang='en'>Lightweight XMPP/Jabber desktop client"
        " for Linux</shortdesc>",
        "    <shortdesc xml:lang='ru'>Лёгкий XMPP/Jabber-клиент для"
        " Linux</shortdesc>",
        "    <description xml:lang='en'>Stanza IM is a lightweight XMPP/Jabber"
        " desktop client for Linux inspired by the original Jabbim client,"
        " written in Python with PyQt6 and slixmpp.</description>",
        "    <description xml:lang='ru'>Stanza IM — лёгкий десктопный"
        " XMPP/Jabber-клиент для Linux, вдохновлённый оригинальным Jabbim;"
        " написан на Python с PyQt6 и slixmpp.</description>",
        "    <homepage rdf:resource='https://github.com/jabberworld/stanza_im'/>",
        "    <schema:documentation rdf:resource="
        "'https://github.com/jabberworld/stanza_im/blob/master/README.md'/>",
        "    <download-page rdf:resource="
        "'https://github.com/jabberworld/stanza_im/releases'/>",
        "    <bug-database rdf:resource="
        "'https://github.com/jabberworld/stanza_im/issues'/>",
        "    <license rdf:resource="
        "'https://www.gnu.org/licenses/old-licenses/gpl-2.0.html'/>",
        "    <language>en</language>",
        "    <language>ru</language>",
        "    <schema:logo rdf:resource='https://raw.githubusercontent.com/"
        "jabberworld/stanza_im/master/resources/images/scalable/apps/"
        "stanza-im.svg'/>",
        "    <programming-language>Python</programming-language>",
        "    <os>Linux</os>",
        "    <category rdf:resource="
        "'https://linkmauve.fr/ns/xmpp-doap#category-client'/>",
        "    <repository>",
        "      <GitRepository>",
        "        <browse rdf:resource="
        "'https://github.com/jabberworld/stanza_im'/>",
        "        <location rdf:resource="
        "'https://github.com/jabberworld/stanza_im.git'/>",
        "      </GitRepository>",
        "    </repository>",
    ]
    for rfc in RFC_IMPLEMENTS:
        lines.append(
            "    <implements rdf:resource="
            f"'https://xmpp.org/rfcs/rfc{rfc}.html'/>")
    for num in xep_numbers():
        status = STATUS.get(num, "complete")
        lines.extend([
            "    <implements>",
            "      <xmpp:SupportedXep>",
            "        <xmpp:xep rdf:resource="
            f"'https://xmpp.org/extensions/xep-{num}.html'/>",
            f"        <xmpp:status>{status}</xmpp:status>",
        ])
        if num == "0096":
            lines.append(
                "        <xmpp:note xml:lang='en'>Superseded by XEP-0234;"
                " not used by Stanza IM.</xmpp:note>")
        lines.extend([
            "      </xmpp:SupportedXep>",
            "    </implements>",
        ])
    lines.extend(["  </Project>", "</rdf:RDF>", ""])
    return "\n".join(lines)


def main() -> None:
    xml = build()
    with open(DOAP_XML, "w", encoding="utf-8") as fh:
        fh.write(xml)
    print(f"wrote {DOAP_XML} ({len(xep_numbers())} XEPs)")


if __name__ == "__main__":
    main()
