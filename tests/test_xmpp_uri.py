"""Tests for XEP-0147 xmpp: URI parsing, tokenisation and rendering."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.include.xmpp_uri import make_xmpp_uri, parse_xmpp_uri, extract_xmpp_uris
from stanza_im.include.utils import tokenize_urls, restore_url_tokens
from stanza_im.include.geo import escape_body_with_geo

FAILURES: list[str] = []


def check(name: str, cond: bool):
    print(("PASS" if cond else "FAIL") + ":", name)
    if not cond:
        FAILURES.append(name)


# 1. make_xmpp_uri -----------------------------------------------------------------

check("make bare",
      make_xmpp_uri("romeo@montague.net") == "xmpp:romeo@montague.net")

check("make join",
      make_xmpp_uri("theconf@conference.example.org", "join")
      == "xmpp:theconf@conference.example.org?join")

uri_body = make_xmpp_uri("romeo@montague.net", "message", body="hi there")
check("make message body",
      "?message" in uri_body and ";body=hi%20there" in uri_body)

check("make empty",
      make_xmpp_uri("") == "")

# 2. parse_xmpp_uri ----------------------------------------------------------------

check("parse bare",
      parse_xmpp_uri("xmpp:romeo@montague.net")
      == {"jid": "romeo@montague.net", "action": "", "params": {}})

parsed = parse_xmpp_uri(
    "xmpp:romeo@montague.net?message;subject=Hello;body=hi%20there")
check("parse message", parsed["action"] == "message")
check("parse params",  parsed["params"] == {"subject": "Hello", "body": "hi there"})

check("parse join",
      parse_xmpp_uri("xmpp:theconf@conference.example.org?join")["action"]
      == "join")

check("parse full jid",
      parse_xmpp_uri("xmpp:juliet@capulet.com/balcony")["jid"]
      == "juliet@capulet.com/balcony")

check("parse unknown action",
      parse_xmpp_uri("xmpp:romeo@montague.net?browse")["action"] == "browse")

check("parse non-xmpp", parse_xmpp_uri("https://example.org") is None)
check("parse empty jid", parse_xmpp_uri("xmpp:") is None)

noaddr = parse_xmpp_uri(
    "xmpp:?message;body=https%3A%2F%2Fgultsch.de%2Fposts%2Fhow-do-we-gain-traction%2F")
check("parse address-less message", noaddr == {
    "jid": "", "action": "message",
    "params": {"body": "https://gultsch.de/posts/how-do-we-gain-traction/"}})
check("parse address-less empty query", parse_xmpp_uri("xmpp:?") is None)

# 3. roundtrip ----------------------------------------------------------------------

for jid in ("a@b.c", "room@conf.example.org"):
    for action in ("", "join", "message", "roster", "subscribe"):
        uri = make_xmpp_uri(jid, action)
        r = parse_xmpp_uri(uri)
        check(f"roundtrip {jid}/{action}", r["jid"] == jid and r["action"] == action)

# 4. extract_xmpp_uris --------------------------------------------------------------

check("extract from text",
      extract_xmpp_uris("join xmpp:room@conf.example.org?join now")
      == ["xmpp:room@conf.example.org?join"])

# 5. tokenize_urls ------------------------------------------------------------------

tmp, anchors = tokenize_urls("go xmpp:room@conf.example.org?join")
check("tokenise replaces", "\x000\x00" in tmp)
check("tokenise anchor",   '<a href="xmpp:room@conf.example.org?join">' in anchors[0])

tmp, anchors = tokenize_urls("chat xmpp:romeo@montague.net, please")
restored = restore_url_tokens(tmp, anchors)
check("tokenise trailing punct",
      '<a href="xmpp:romeo@montague.net">' in anchors[0]
      and anchors[0].endswith("romeo@montague.net</a>"))
check("restore full text", restored == 'chat <a href="xmpp:romeo@montague.net">xmpp:romeo@montague.net</a>, please')

tmp, anchors = tokenize_urls(
    "go xmpp:?message;body=https%3A%2F%2Fgultsch.de%2Fposts%2F")
check("tokenise address-less xmpp",
      "\x000\x00" in tmp and anchors[0].startswith('<a href="xmpp:?message;'))

# 6. escape_body_with_geo (QTextBrowser fallback) -----------------------------------

escaped = escape_body_with_geo("go xmpp:room@conf.example.org?join")
check("escape xmpp link",   '<a href="xmpp:room@conf.example.org?join">' in escaped)
check("escape not double-escaped", "&amp;" not in escaped.split("href")[0])

escaped2 = escape_body_with_geo("chat <b>xmpp:a@b.c</b>")
check("escape html + xmpp", '<a href="xmpp:a@b.c">' in escaped2)
check("escape safe html",   "&lt;b&gt;" in escaped2)

# ── summary ------------------------------------------------------------------------

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)