"""Backwards MAM media paging (used by the History Manager media tabs)."""
import asyncio
import os
import sys
import tempfile
import unittest.mock
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_mam_media_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp  # noqa: E402
from stanza_im.core.client import JabberClient  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def make_msg(frm, body, mid, ts="2026-09-14T10:00:00Z"):
    msg = slixmpp.Message()
    msg["from"] = frm
    msg["to"] = "me@x/res"
    msg["type"] = "chat"
    msg["body"] = body
    msg["id"] = mid
    delay = ET.SubElement(msg.xml, "{urn:xmpp:delay}delay")
    delay.set("stamp", ts)
    return msg


class _Recorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, *, jid=None, with_jid=None, end=None,
                       rsm=None, **_kw):
        self.calls.append((jid, with_jid, rsm))
        if not self.calls or len(self.calls) == 1:
            return {
                "type": "result",
                "mam": {"results": [
                    make_msg("bob@example.com",
                             "photo https://files.example/p.jpg",
                             "m1", "2026-09-14T10:00:00Z"),
                    make_msg("bob@example.com", "plain", "m2",
                             "2026-09-14T10:01:00Z"),
                ]},
                "mam_fin": {"complete": False,
                            "rsm": {"first": "m1", "last": "m2"}},
            }
        return {"type": "result", "mam": {"results": []},
                "mam_fin": {"complete": True, "rsm": {}}}


client = JabberClient("me@x/res", "pw")
mam = client.xmpp.plugin["xep_0313"]
recorder = _Recorder()
with unittest.mock.patch.object(mam, "retrieve", recorder):
    first = asyncio.run(client.fetch_mam_media_page("bob@example.com"))
    second = asyncio.run(client.fetch_mam_media_page(
        "bob@example.com", before=first[2]))

check("only the media-bearing row is returned",
      first is not None and len(first[0]) == 1)
check("the first backward page has no before cursor at first",
      recorder.calls[0][2].get("before") is True)
check("the next cursor is the oldest archive id",
      first[2] == "m1")
check("the next page requests older messages with before",
      recorder.calls[1][2].get("before") == "m1")
check("the final page completes", second[1] is True)

if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll MAM media tests passed.")
