"""Offscreen tests for XEP-0402 PEP Native Bookmarks.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_bookmarks2.py
"""
import asyncio
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_bm2_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

asyncio.set_event_loop(asyncio.new_event_loop())

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.core.client import (JabberClient, NS_BOOKMARKS2,
                                   NS_BOOKMARKS2_COMPAT, NS_PUBSUB,
                                   NS_PUBSUB_EVENT,
                                   _build_bookmarks2_conference,
                                   _bookmarks2_publish_options,
                                   _parse_bookmarks2)

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── stanza building / parsing ────────────────────────────────────
conf = _build_bookmarks2_conference("Puck", "secret", True, "Council")
check("conference element is namespaced", conf.tag == "{%s}conference" % NS_BOOKMARKS2)
check("autojoin serialized", conf.get("autojoin") == "true")
check("name serialized", conf.get("name") == "Council")
check("nick serialized", conf.findtext("{%s}nick" % NS_BOOKMARKS2) == "Puck")
check("password serialized",
      conf.findtext("{%s}password" % NS_BOOKMARKS2) == "secret")

form = ET.Element("{jabber:x:data}x")
_bookmarks2_publish_options(form)
vars_ = {f.get("var") for f in form.findall("{jabber:x:data}field")}
check("publish-options carry the required fields",
      {"FORM_TYPE", "pubsub#persist_items", "pubsub#max_items",
       "pubsub#send_last_published_item", "pubsub#access_model"} <= vars_)

items_xml = ET.fromstring(
    "<pubsub xmlns='%s'><items node='%s'>"
    "<item id='room@conference.example'><conference xmlns='%s' "
    "name='Room' autojoin='1'><nick>me</nick><password>pw</password>"
    "</conference></item></items></pubsub>" % (NS_PUBSUB, NS_BOOKMARKS2, NS_BOOKMARKS2))
parsed = _parse_bookmarks2(items_xml)
check("bookmark parsed",
      parsed == [{"jid": "room@conference.example", "nick": "me",
                  "password": "pw", "autojoin": True, "name": "Room"}])
check("empty payload yields no bookmarks", _parse_bookmarks2(None) == [])


# ── client storage logic ─────────────────────────────────────────
client = JabberClient("me@example.com/r", "pw")
calls = {}


def _record(name, result=None):
    def _fn(*args, **kwargs):
        calls.setdefault(name, []).append((args, kwargs))

        async def _coro():
            return result
        return _coro()
    return _fn


async def _recorded(name, result=None):
    calls.setdefault(name, []).append(result)
    return result


# save: unified server -> only XEP-0402
calls.clear()
client._bookmarks2_publish = _record("publish")
client._bookmarks2_compat_mode = _record("compat", "unified")
client._save_bookmark_legacy = _record("legacy")


async def _save_unified():
    await client.save_bookmark("room@x", "me", "pw", True, "Room")

asyncio.get_event_loop().run_until_complete(_save_unified())
check("unified server uses only XEP-0402",
      "publish" in calls and "legacy" not in calls)

# save: dual server -> also legacy
calls.clear()
client._bookmarks2_compat_mode = _record("compat", "dual")
asyncio.get_event_loop().run_until_complete(_save_unified())
check("dual server updates the legacy store too",
      "publish" in calls and "legacy" in calls)

# save: XEP-0402 failure -> legacy fallback
calls.clear()


def _failing_publish(*args, **kwargs):
    async def _coro():
        raise RuntimeError("no pep")
    return _coro()


client._bookmarks2_publish = _failing_publish
asyncio.get_event_loop().run_until_complete(_save_unified())
check("failed XEP-0402 publish falls back to legacy", "legacy" in calls)


# list: empty new node migrates the legacy bookmarks
async def _run_list(get_result, legacy):
    client._bookmarks2_get = _record_result(get_result)
    client._list_bookmarks_legacy = _record_result(legacy)
    return await client.list_bookmarks()


def _record_result(value):
    async def _fn(*args, **kwargs):
        return value
    return _fn


calls.clear()
legacy = [{"jid": "room@x", "nick": "me", "password": "pw",
           "autojoin": True, "name": "Room"}]
client._bookmarks2_publish = _record("publish")
result = asyncio.get_event_loop().run_until_complete(_run_list([], legacy))
check("empty new node migrates legacy bookmarks",
      result == legacy and "publish" in calls)

calls.clear()
client._bookmarks2_publish = _record("publish")
result = asyncio.get_event_loop().run_until_complete(_run_list(None, legacy))
check("unavailable new node returns legacy without migration",
      result == legacy and "publish" not in calls)

fresh = [{"jid": "room@y", "nick": "", "password": "", "autojoin": False,
          "name": ""}]
result = asyncio.get_event_loop().run_until_complete(_run_list(fresh, legacy))
check("new node wins when it has items", result == fresh)


# remove: dual server retracts both
calls.clear()
client._bookmarks2_retract = _record("retract")
client._bookmarks2_compat_mode = _record("compat", "dual")
client._remove_bookmark_legacy = _record("legacy")
asyncio.get_event_loop().run_until_complete(client.remove_bookmark("room@x"))
check("remove retracts and updates the legacy store",
      "retract" in calls and "legacy" in calls)

calls.clear()
client._bookmarks2_compat_mode = _record("compat", "unified")
asyncio.get_event_loop().run_until_complete(client.remove_bookmark("room@x"))
check("unified remove keeps the legacy store untouched",
      "retract" in calls and "legacy" not in calls)


# ── notifications ────────────────────────────────────────────────
scheduled = []
client._start_task = lambda coro: (scheduled.append(coro), coro.close())
items = ET.fromstring(
    "<items xmlns='%s' node='%s'>"
    "<item id='join@x'><conference xmlns='%s' autojoin='true'>"
    "<nick>me</nick></conference></item>"
    "<item id='leave@x'><conference xmlns='%s'/></item>"
    "<retract id='gone@x'/></items>"
    % (NS_PUBSUB_EVENT, NS_BOOKMARKS2, NS_BOOKMARKS2, NS_BOOKMARKS2))
client._handle_bookmarks2_event(client.jid_str, items)
check("bookmark notification schedules apply", len(scheduled) == 1)
scheduled.clear()
client._handle_bookmarks2_event("other@example.com", items)
check("foreign bookmark notifications are ignored", scheduled == [])


async def _apply_probe():
    joined, left, emitted = [], [], []
    client.groupchats = {"leave@x": object(), "gone@x": object()}
    client.autojoin_rooms = set()
    client.join_muc = lambda room, nick, **k: joined.append(room)
    client.leave_muc = lambda room, *a, **k: left.append(room)
    client.list_bookmarks = _record_result([])
    client.emit = lambda *a, **k: emitted.append(a[0])
    await client._bookmarks2_apply([("join@x", "me", "")],
                                   ["leave@x", "gone@x"])
    return joined, left, emitted


joined, left, emitted = asyncio.get_event_loop().run_until_complete(_apply_probe())
check("autojoin bookmark joins", joined == ["join@x"])
check("retracted/disabled bookmarks leave", left == ["leave@x", "gone@x"])
check("bookmarks_changed emitted", emitted == ["bookmarks_changed"])

# ── static wiring ────────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_root, "stanza_im", "core", "client.py"),
          encoding="utf-8") as fh:
    src = fh.read()
check("xep_0402 registered", 'register_plugin("xep_0402")' in src)
check("disco advertises bookmarks +notify",
      "NS_BOOKMARKS2 + \"+notify\"" in src)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
