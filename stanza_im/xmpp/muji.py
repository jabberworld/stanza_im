"""Multiparty Jingle (Muji, XEP-0272) coordination.

A Muji conference lives in a MUC room: participants advertise the media
contents they provide in their MUC presence (``<muji xmlns='urn:xmpp:jingle:muji:0'/>``),
and the joining participant opens a Jingle session with every other
participant's real JID, tagging the ``<jingle/>`` with ``<muji room='…'/>``.

This module implements the presence coordination, session orchestration
(via :class:`~stanza_im.xmpp.jingle_rtp.JingleRtpManager`), content add/remove,
leaving, and XEP-0482 call invites.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

logger = logging.getLogger("stanza_im.call.muji")

NS_MUJI = "urn:xmpp:jingle:muji:0"
NS_JINGLE = "urn:xmpp:jingle:1"
NS_RTP = "urn:xmpp:jingle:apps:rtp:1"
NS_CALL_INVITES = "urn:xmpp:call-invites:0"


def _q(ns: str, tag: str) -> str:
    return "{%s}%s" % (ns, tag)


@dataclass
class MujiParticipant:
    nick: str
    real_jid: str = ""
    preparing: bool = False
    contents: dict = field(default_factory=dict)   # name -> media type


@dataclass
class MujiConference:
    room: str
    self_nick: str = ""
    joined: bool = False
    preparing: bool = False
    contents: dict = field(default_factory=dict)   # name -> media ("audio"/"video")
    participants: dict = field(default_factory=dict)  # nick -> MujiParticipant


class MujiManager:
    """Coordinates Muji conferences for one :class:`JabberClient`."""

    def __init__(self, client):
        self.client = client
        self.conferences: dict[str, MujiConference] = {}
        logger.info("MUJI manager ready")

    # ── MUC presence (XEP-0272 §3/§5/§6) ──────────────────────────
    def handle_presence(self, pres) -> bool:
        """Parse a MUC presence <muji/> element.  Returns True if handled."""
        muji = pres.xml.find(_q(NS_MUJI, "muji"))
        if muji is None:
            return False
        frm = str(pres["from"])
        room, _, nick = frm.partition("/")
        conf = self.conferences.get(room)
        if conf is None:
            conf = MujiConference(room=room)
            self.conferences[room] = conf
        participant = conf.participants.setdefault(nick, MujiParticipant(nick))
        item = pres.xml.find(
            "{http://jabber.org/protocol/muc#user}x/"
            "{http://jabber.org/protocol/muc#user}item")
        if item is not None and item.get("jid"):
            participant.real_jid = item.get("jid", "")
        participant.preparing = muji.find(_q(NS_MUJI, "preparing")) is not None
        contents = {}
        for content in muji.findall(_q(NS_MUJI, "content")):
            name = content.get("name", "")
            desc = content.find(_q(NS_RTP, "description"))
            media = desc.get("media", "audio") if desc is not None else "audio"
            contents[name] = media
        participant.contents = contents
        if nick == conf.self_nick:
            conf.contents = contents
            conf.joined = bool(contents)
            conf.preparing = participant.preparing
        logger.debug("MUJI presence %s/%s preparing=%s contents=%s",
                     room, nick, participant.preparing, contents)
        self.client.emit("muji_updated", room)
        return True

    def note_session(self, room: str, peer_full_jid: str) -> None:
        """Record a peer seen through an incoming Jingle session.

        MUC presence sometimes arrives late or without the peer's <muji/>
        advertisement (late joiners, reduced-functionality clients), so a
        session-initiate may be our only record of a conference member.
        """
        peer_bare = str(peer_full_jid).split("/", 1)[0]
        nick = (str(peer_full_jid).split("/", 1)[1]
                if "/" in str(peer_full_jid) else peer_bare)
        conf = self.conferences.get(room)
        if conf is None:
            return
        participant = conf.participants.setdefault(
            nick, MujiParticipant(nick))
        if not participant.real_jid:
            participant.real_jid = peer_bare
        logger.info("MUJI session peer %s (%s) recorded in %s",
                    peer_full_jid, nick, room)
        self.client.emit("muji_updated", room)

    # ── join / leave ──────────────────────────────────────────────
    def join(self, room: str, self_nick: str, video: bool = False) -> None:
        conf = self.conferences.setdefault(room, MujiConference(room=room))
        conf.self_nick = self_nick
        conf.preparing = True
        logger.info("MUJI joining %s as %s (video=%s)", room, self_nick, video)
        self._send_presence(room, self_nick, preparing=True)
        # After the MUC rebroadcast we finalise the contents.
        self.client._start_task(self._finalise_join(room, self_nick, video))

    async def _finalise_join(self, room: str, self_nick: str,
                             video: bool) -> None:
        import asyncio
        await asyncio.sleep(1.0)
        conf = self.conferences.get(room)
        if conf is None:
            return
        contents = {"voice": "audio"}
        if video:
            contents["video"] = "video"
        conf.contents = contents
        conf.preparing = False
        self._send_presence(room, self_nick, contents=contents)
        await asyncio.sleep(1.0)
        self._initiate_sessions(room)
        self.client.emit("muji_joined", room)

    def leave(self, room: str) -> None:
        conf = self.conferences.get(room)
        if conf is None:
            return
        logger.info("MUJI leaving %s", room)
        self._send_presence(room, conf.self_nick, clearing=True)
        self.conferences.pop(room, None)
        self.client.rtp_calls.end_muji(room)
        self.client.emit("muji_left", room)

    def add_content(self, room: str, name: str, media: str) -> None:
        conf = self.conferences.get(room)
        if conf is None:
            return
        conf.contents[name] = media
        self._send_presence(room, conf.self_nick, contents=conf.contents)
        self.client.rtp_calls.add_muji_content(room, name, media)

    def remove_content(self, room: str, name: str) -> None:
        conf = self.conferences.get(room)
        if conf is None:
            return
        conf.contents.pop(name, None)
        self._send_presence(room, conf.self_nick, contents=conf.contents)
        self.client.rtp_calls.remove_muji_content(room, name)

    def _send_presence(self, room: str, nick: str, preparing: bool = False,
                       contents: dict | None = None,
                       clearing: bool = False) -> None:
        if not nick:
            return
        pres = self.client.xmpp.Presence()
        pres["to"] = "%s/%s" % (room, nick)
        pres["type"] = "available"
        if not clearing:
            muji = ET.SubElement(pres.xml, _q(NS_MUJI, "muji"))
            if contents:
                for name, media in contents.items():
                    content = ET.SubElement(muji, _q(NS_MUJI, "content"))
                    content.set("creator", "initiator")
                    content.set("name", name)
                    desc = ET.SubElement(content, _q(NS_RTP, "description"))
                    desc.set("media", media)
                    if media == "audio":
                        pt = ET.SubElement(desc, _q(NS_RTP, "payload-type"))
                        pt.set("id", "111")
                        pt.set("name", "opus")
                        pt.set("clockrate", "48000")
                        pt.set("channels", "2")
                    else:
                        pt = ET.SubElement(desc, _q(NS_RTP, "payload-type"))
                        pt.set("id", "96")
                        pt.set("name", "VP8")
                        pt.set("clockrate", "90000")
            if preparing:
                ET.SubElement(muji, _q(NS_MUJI, "preparing"))
        pres.send()
        logger.debug("MUJI presence sent to %s/%s", room, nick)

    def _initiate_sessions(self, room: str) -> None:
        conf = self.conferences.get(room)
        if conf is None:
            return
        for nick, participant in conf.participants.items():
            if nick == conf.self_nick or not participant.real_jid:
                continue
            logger.info("MUJI initiating session with %s (%s)",
                        participant.real_jid, nick)
            self.client.rtp_calls.start_call(
                participant.real_jid, video="video" in conf.contents.values(),
                muji_room=room)

    # ── XEP-0482 call invites ─────────────────────────────────────
    def handle_invite_message(self, msg) -> bool:
        invite = msg.xml.find(_q(NS_CALL_INVITES, "invite"))
        if invite is None:
            return False
        muji = invite.find(_q(NS_MUJI, "muji"))
        if muji is None:
            return False
        room = muji.get("room", "")
        frm = str(msg["from"]).split("/")[0]
        logger.info("MUJI invite from %s to room %s", frm, room)
        self.client.emit("muji_invite", frm, room)
        return True
