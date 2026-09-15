"""Offscreen smoke tests for MAM query-mode selection and the 1:1 sender guard.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_mam_modes.py
"""
import asyncio
import os
import sys
import tempfile
import unittest.mock
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_mam_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp

from stanza_im.core.client import JabberClient

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. _mam_query_modes --------------------------------------------------------
_modes = JabberClient._mam_query_modes
check("1:1, no end -> only with_jid",
      _modes(False, None) == [(False, None)])
end = object()
check("1:1, with end -> with_jid only, no archive-jid",
      _modes(False, end) == [(False, end), (False, None)])
check("MUC, no end -> archive-jid",
      _modes(True, None) == [(True, None)])
check("MUC, with end -> archive-jid first",
      _modes(True, end) == [(True, end), (True, None)])
check("never archive-jid for 1:1",
      all(use_jid is False for use_jid, _ in _modes(False, None)
          + _modes(False, end) if use_jid is not None))


# 2. _mam_belongs_to ---------------------------------------------------------
_belongs = JabberClient._mam_belongs_to
check("1:1 incoming from contact accepted",
      _belongs("kal@linuxoid.in", "kal@linuxoid.in/res", False, "me@x"))
check("1:1 outgoing from own bare accepted",
      _belongs("kal@linuxoid.in", "me@x", False, "me@x"))
check("1:1 outgoing from own full accepted",
      _belongs("kal@linuxoid.in", "me@x/res1", False, "me@x"))
check("1:1 stranger rejected",
      not _belongs("kal@linuxoid.in", "rss@service.org", False, "me@x"))
check("1:1 resource of contact accepted",
      _belongs("kal@linuxoid.in", "kal@linuxoid.in/phone", False, "me@x"))
check("1:1 case-insensitive",
      _belongs("Kal@Linuxoid.in", "kal@linuxoid.in", False, "me@x"))
check("MUC always accepted",
      _belongs("room@conf", "room@conf/nick", True, "me@x"))


# 3. MAM retrieval uses only with_jid for 1:1 --------------------------------
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


class _Holder:
    """Simple attribute bag holding recorded calls + canned results."""

    def __init__(self, with_results, jid_results):
        self.calls = []
        self.with_results = with_results
        self.jid_results = jid_results


class _Recorder:
    """Replace retrieve(); record calls and serve canned results."""

    def __init__(self, holder):
        self.holder = holder

    async def __call__(self, *, jid=None, with_jid=None, end=None,
                       rsm=None, **_kw):
        mode = "jid" if jid is not None else "with_jid"
        self.holder.calls.append((mode, jid or with_jid, end))
        results = (self.holder.jid_results if jid is not None
                   else self.holder.with_results)
        return {"type": "result", "mam": {"results": results}}


def _run_11_with_stranger():
    c = JabberClient("me@x/res", "pw")
    mam = c.xmpp.plugin["xep_0313"]
    holder = _Holder(
        [make_msg("kal@linuxoid.in", "hello", "m1"),
         make_msg("me@x", "out", "m2"),
         make_msg("pravda@rss.jabberworld.info", "news", "m3")],
        [])
    stored = {}
    async def _capture(jid, rows):
        stored[jid] = rows
        return len(rows)
    from stanza_im.core import history
    with unittest.mock.patch.object(mam, "retrieve", _Recorder(holder)):
        with unittest.mock.patch.object(history, "store_many_async",
                                        _capture):
            return (asyncio.run(c.fetch_history_mam("kal@linuxoid.in")),
                    stored, holder.calls)


stored_n, stored, calls = _run_11_with_stranger()
check("1:1 fetch stores rows", stored.get("kal@linuxoid.in") is not None
      and len(stored["kal@linuxoid.in"]) == 2)
check("stranger not stored",
      all(r.get("sender") != "pravda@rss.jabberworld.info"
          for r in stored.get("kal@linuxoid.in", [])))
check("direction classified",
      {r.get("direction") for r in stored["kal@linuxoid.in"]}
      == {"incoming", "outgoing"})
check("only with_jid used for 1:1",
      calls == [("with_jid", "kal@linuxoid.in", None)])


# 4. archive-jid mode never reached when with_jid is empty -------------------
def _run_empty_with():
    c = JabberClient("me@x/res", "pw")
    mam = c.xmpp.plugin["xep_0313"]
    holder = _Holder([], [make_msg("other@else.org", "intruder", "m9")])
    stored = {}
    async def _capture(jid, rows):
        stored[jid] = rows
        return len(rows)
    from stanza_im.core import history
    with unittest.mock.patch.object(mam, "retrieve", _Recorder(holder)):
        with unittest.mock.patch.object(history, "store_many_async",
                                        _capture):
            return (asyncio.run(c.fetch_history_mam("kal@linuxoid.in")),
                    stored, holder.calls)


stored_n2, stored2, calls2 = _run_empty_with()
check("empty with_jid results are not stored",
      stored2 == {})
check("archive-jid fallback never used for 1:1",
      [call for call in calls2 if call[0] == "jid"] == [])
check("1:1 with empty archive returns 0",
      stored_n2 == 0)


if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll tests passed.")