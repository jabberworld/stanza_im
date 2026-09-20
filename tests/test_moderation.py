"""Offscreen smoke tests for XEP-0425 moderated message retraction.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_moderation.py
"""
import asyncio
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_mod_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

asyncio.set_event_loop(asyncio.new_event_loop())

from PyQt6 import QtWidgets
from slixmpp.stanza import Message

from stanza_im.i18n import load as i18n_load
from stanza_im.i18n import tr
from stanza_im.core.client import (JabberClient, _StanzaXMPP, _moderation_info,
                                   NS_MODERATE, NS_RETRACT)
from stanza_im.core import history
from stanza_im.ui.chat_widget import ChatWidget, _ModerateDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _msg(xml_str):
    return Message(xml=ET.fromstring(xml_str))


# ── _moderation_info parsing ─────────────────────────────────────
broadcast = _msg(
    "<message xmlns='jabber:client' from='room@muc' type='groupchat'>"
    "<retract id='sid1' xmlns='urn:xmpp:message-retract:1'>"
    "<moderated by='room@muc/mod' xmlns='urn:xmpp:message-moderate:1'/>"
    "<reason>spam</reason></retract></message>")
info = _moderation_info(broadcast)
check("broadcast moderation parsed",
      info == {"moderated": True, "by": "room@muc/mod", "reason": "spam"})

tomb = _msg(
    "<message><retracted id='sid1' xmlns='urn:xmpp:message-retract:1'>"
    "<moderated by='mod@x' xmlns='urn:xmpp:message-moderate:1'/>"
    "<reason xmlns='urn:xmpp:message-moderate:1'>bad</reason>"
    "</retracted></message>")
check("tombstone moderation parsed",
      _moderation_info(tomb)["moderated"] is True
      and _moderation_info(tomb)["reason"] == "bad")

plain = _msg("<message><retract id='sid1' "
             "xmlns='urn:xmpp:message-retract:1'/></message>")
check("plain retraction is not moderation",
      _moderation_info(plain) == {"moderated": False, "by": "", "reason": ""})


# ── moderation IQ ────────────────────────────────────────────────
x = _StanzaXMPP("a@b", "pw")
client = JabberClient.__new__(JabberClient)
client.xmpp = x
events = []
client.emit = lambda *args, **kwargs: events.append(args)

iq = client._build_moderation("room@muc", "sid1", "spam")
mod = iq.xml.find("{%s}moderate" % NS_MODERATE)
check("moderation IQ is a set", iq["type"] == "set")
check("moderation IQ targets the room", str(iq["to"]) == "room@muc")
check("moderate element carries the id", mod is not None
      and mod.get("id") == "sid1")
check("moderate contains a retract",
      mod.find("{%s}retract" % NS_RETRACT) is not None)
check("moderate contains the reason",
      mod.find("{%s}reason" % NS_MODERATE).text == "spam")


async def _ok_send():
    return None


async def _fail_send():
    raise RuntimeError("forbidden")


_orig_build = client._build_moderation


def _build_ok(room, stanza_id, reason=""):
    built = _orig_build(room, stanza_id, reason)
    built.send = _ok_send
    return built


def _build_fail(room, stanza_id, reason=""):
    built = _orig_build(room, stanza_id, reason)
    built.send = _fail_send
    return built


client._build_moderation = _build_ok
check("moderate_message succeeds",
      asyncio.run(client.moderate_message("room@muc", "sid", "spam")) is True)
check("moderation_sent emitted",
      events and events[-1][0] == "moderation_sent")
client._build_moderation = _build_fail
events.clear()
check("moderate_message reports failure",
      asyncio.run(client.moderate_message("room@muc", "sid")) is False)
check("moderation_failed emitted",
      events and events[-1][0] == "moderation_failed")


# ── room feature discovery ───────────────────────────────────────
class _FakeDisco:
    def __init__(self, supported):
        self._supported = supported

    async def get_info(self, jid):
        var = (NS_MODERATE if self._supported else "urn:x:other")
        result = type("R", (), {})()
        result.xml = ET.fromstring(
            "<iq><query xmlns='http://jabber.org/protocol/disco#info'>"
            "<feature var='%s'/></query></iq>" % var)
        return result


c2 = JabberClient.__new__(JabberClient)
c2._moderation_support = {}
c2.xmpp = {"xep_0030": _FakeDisco(True)}
check("room moderation supported",
      asyncio.run(c2.room_supports_moderation("room@muc")) is True)
check("room moderation cached",
      asyncio.run(c2.room_supports_moderation("room@muc")) is True)
c2.xmpp = {"xep_0030": _FakeDisco(False)}
check("room moderation unsupported",
      asyncio.run(c2.room_supports_moderation("room@other")) is False)


# ── business rule: moderation must come from the room ────────────
c3 = JabberClient.__new__(JabberClient)
c3.groupchats = {}
gc_events = []
c3.emit = lambda *args, **kwargs: gc_events.append(args)


def _retraction(frm, moderated):
    msg = Message()
    msg["from"] = frm
    msg["type"] = "groupchat"
    retract = ET.SubElement(msg.xml, "{%s}retract" % NS_RETRACT)
    retract.set("id", "sid1")
    if moderated:
        el = ET.SubElement(retract, "{%s}moderated" % NS_MODERATE)
        el.set("by", "room@muc/mod")
    return msg


c3._on_groupchat_message(_retraction("room@muc/bob", True))
check("spoofed moderation is discarded", gc_events == [])
c3._on_groupchat_message(_retraction("room@muc", True))
check("room moderation is accepted",
      gc_events and gc_events[-1][0] == "groupchat_message_retracted"
      and gc_events[-1][-1] is True)
c3._on_groupchat_message(_retraction("room@muc/bob", False))
check("author self-retraction still accepted",
      gc_events and gc_events[-1][0] == "groupchat_message_retracted"
      and gc_events[-1][-1] is False)


# ── bodyless retraction routing (slixmpp needs a <body>) ─────────
c4 = JabberClient.__new__(JabberClient)
c4.groupchats = {}
bl_events = []
c4.emit = lambda *args, **kwargs: bl_events.append(args)


def _bodyless(frm, mtype, body=""):
    msg = Message()
    msg["from"] = frm
    msg["type"] = mtype
    retract = ET.SubElement(msg.xml, "{%s}retract" % NS_RETRACT)
    retract.set("id", "sid1")
    if body:
        msg["body"] = body
    return msg


asyncio.run(c4._on_bodyless_retract_stanza(_bodyless("room@muc", "groupchat")))
check("bodyless groupchat retraction routed",
      bl_events and bl_events[-1][0] == "groupchat_message_retracted")
bl_events.clear()
asyncio.run(c4._on_bodyless_retract_stanza(_bodyless("a@b", "chat")))
check("bodyless 1:1 retraction routed",
      bl_events and bl_events[-1][0] == "message_retracted")
bl_events.clear()
asyncio.run(c4._on_bodyless_retract_stanza(
    _bodyless("room@muc", "groupchat", body="fallback")))
check("retraction with a fallback body is not double handled", bl_events == [])


# ── combined moderation dialog ───────────────────────────────────
dlg = _ModerateDialog(None)
dlg._reason.setText("  spam  ")
check("moderate dialog returns the trimmed reason", dlg.reason() == "spam")
check("moderate dialog is empty by default", _ModerateDialog(None).reason() == "")
check("moderate dialog focuses Cancel",
      dlg._cancel_btn.isDefault() and not dlg._ok_btn.isDefault())
check("moderate dialog buttons are localized",
      dlg._cancel_btn.text() == tr("moderate_cancel")
      and dlg._ok_btn.text() == tr("moderate_send")
      and tr("moderate_cancel") != "moderate_cancel")
check("reason field carries the hint",
      dlg._reason.placeholderText() == tr("moderate_reason_label")
      and dlg._reason.placeholderText())


# ── history persistence ──────────────────────────────────────────
jid = "room@muc"
history.store_message(jid, "incoming", "hello", sender="bob",
                      message_id="sid1")
history.retract_message(jid, "sid1", reason="spam", by="room@muc/mod")
entry = [e for e in history.load_history(jid)
         if e.get("message_id") == "sid1"][0]
check("history marks retracted", entry["retracted"] is True)
check("history keeps the reason", entry["retract_reason"] == "spam")
check("history keeps the moderator", entry["retract_by"] == "room@muc/mod")

history.store_message(jid, "incoming", "keep", sender="bob",
                      message_id="sid2")
history.retract_message(jid, "sid2", marker=True, reason="spam", by="mod")
entry2 = [e for e in history.load_history(jid)
          if e.get("message_id") == "sid2"][0]
check("marker keeps the body", entry2["body"] == "keep")
check("marker keeps the reason", entry2["retract_reason"] == "spam")
check("marker is not a tombstone", entry2["retract_marker"] is True
      and entry2["retracted"] is False)


# ── ChatWidget moderation eligibility ────────────────────────────
w = ChatWidget.__new__(ChatWidget)
w.is_muc = True
w._moderation_enabled = True
w._self_nick = "me"
incoming = {"direction": "incoming", "sender": "bob", "message_id": "sid"}
check("incoming message is moderatable",
      w._can_moderate_entry(incoming) is True)
check("own message is not moderatable",
      w._can_moderate_entry({"direction": "outgoing", "sender": "Me",
                             "message_id": "sid"}) is False)
check("message without id is not moderatable",
      w._can_moderate_entry({"direction": "incoming", "sender": "bob"}) is False)
check("retracted message is not moderatable",
      w._can_moderate_entry({**incoming, "retracted": True}) is False)
w._moderation_enabled = False
check("disabled moderation hides the action",
      w._can_moderate_entry(incoming) is False)
w._moderation_enabled = True
w.is_muc = False
check("1:1 chats are never moderatable",
      w._can_moderate_entry(incoming) is False)


# ── i18n & static wiring ─────────────────────────────────────────
check("moderate menu label translated",
      tr("chat_moderate") != "chat_moderate")
check("moderation option label translated",
      tr("prefs_allow_moderation") != "prefs_allow_moderation")

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(_root, *parts), encoding="utf-8") as fh:
        return fh.read()


cv = _read("stanza_im", "ui", "chat_view.py")
check("menu exposes the moderation action",
      "data-moderatable" in cv and "stanza:moderate:" in cv)
check("moderation label placeholder wired", "%MODERATE_LABEL%" in cv)
prefs = _read("stanza_im", "ui", "preferences.py")
check("preferences expose allow_moderation",
      "allow_moderation" in prefs and "prefs_allow_moderation" in prefs)
st = _read("stanza_im", "core", "storage.py")
check("allow_moderation defaults to on", '"allow_moderation": True' in st)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
