# Stanza IM — XMPP Compliance Checklist (XEP-0479)

Self-assessment of Stanza IM against the **XMPP Compliance Suites 2023**
([XEP-0479](https://xmpp.org/extensions/xep-0479.html)). XEP-0479 defines
application *categories* (Core, Web, IM, Mobile, A/V Calling) and *levels* —
the **Client** and **Advanced Client** columns of each category's table. The
lists below gather, per level, every feature marked as required (✓) for a
client, with the providers XEP-0479 names for it.

Stanza IM is a **desktop** client, so the **Web** suite (XEP-0479 §2.2) and the
**Mobile** suite (§2.4) are out of scope and are not assessed here. Only the
Core, IM and A/V Calling suites are listed. (Features that a desktop client
happens to share with those suites — e.g. XEP-0198 Stream Management, required
by the IM suite anyway — are kept where the applicable suite requires them.)

Legend: ✅ supported · ⚠️ partial · ❌ not implemented · — N/A (not applicable
to a desktop client).

The live list of every XEP the client uses (including non-compliance ones) is
`XEPs.md`; this file only tracks the XEP-0479 compliance surface.

## Client

Required features for the Client level of the applicable suites (Core, IM,
A/V Calling).

| Feature | Providers | Status | Notes |
|---------|-----------|--------|-------|
| Core features | RFC 6120 | ✅ | slixmpp core |
| TLS | RFC 7590 | ✅ | STARTTLS / direct TLS |
| Feature discovery | XEP-0030 | ✅ | `ServiceBrowserDialog`, room/variant lookups |
| Feature broadcasts | XEP-0115 | ✅ | caps node branded "Stanza IM <version>" |
| Core features (IM) | RFC 6121 | ✅ | roster, presence, 1:1 messaging |
| The /me Command | XEP-0245 | ✅ | rendered as `* sender phrase` |
| vcard-temp | XEP-0054 | ✅ | own/contact vCards, PHOTO avatars |
| Outbound Message Synchronization | XEP-0280 | ✅ | `connection.message_carbons` |
| Group Chat | XEP-0045, XEP-0249 | ✅ | MUC + direct invitations |
| File Upload | XEP-0363 | ✅ | HTTP Upload with automatic P2P fallback |
| Call Setup | XEP-0167, XEP-0353 | ✅ | Jingle RTP + Jingle Message Initiation |
| Transport | XEP-0176 | ✅ | ICE-UDP |
| Encryption | XEP-0320 | ✅ | DTLS-SRTP via aiortc (`calls` extra) |
| STUN/TURN server discovery | XEP-0215 | ✅ | `urn:xmpp:extdisco:2` + SRV fallback |

### Not implemented

None — every Client-level feature of the applicable suites (Core, IM and A/V
Calling) is implemented.

## Advanced Client

Required features for the Advanced Client level of the applicable suites
(Core, IM, A/V Calling). It includes everything the Client level requires; only
the additional features are listed here.

| Feature | Providers | Status | Notes |
|---------|-----------|--------|-------|
| Direct TLS | XEP-0368 | ✅ | `_xmpps-client._tcp` SRV, "TLS only"/"Prefer TLS" |
| Event publishing | XEP-0163 | ✅ | MDS node + extended presence (`+notify`) |
| User Avatars | XEP-0084 | ❌ | avatars are read from the vCard PHOTO (XEP-0054), not the PEP avatar node |
| User Avatar Compatibility | XEP-0398, XEP-0153 | ⚠️ | vCard PHOTO avatars are shown, but the `vcard-temp:x:update` presence hash protocol and the XEP-0398 conversion are not implemented |
| User Blocking | XEP-0191 | ❌ | no blocking command/UI |
| Advanced Group Chat | XEP-0048, XEP-0313, XEP-0402, XEP-0410 | ⚠️ | bookmarks via XEP-0048 stored through XEP-0223 pubsub (or XEP-0049 fallback), not PEP-native XEP-0402; XEP-0410 self-ping not implemented |
| Persistent Storage of Private Data via PubSub | XEP-0223 | ✅ | bookmark storage backend |
| Private XML Storage | XEP-0049 | ✅ | legacy bookmark backend |
| Stream Management | XEP-0198 | ✅ | `connection.stream_management`, resume |
| Message Acknowledgements | XEP-0184 | ✅ | delivery ✓ |
| History Storage / Retrieval | XEP-0313 | ✅ | MAM, RSM-paginated |
| Chat States | XEP-0085 | ✅ | typing/composing notifications |
| Message Correction | XEP-0308 | ✅ | own-message editing |
| File Upload | XEP-0363 | ✅ | HTTP Upload with automatic P2P fallback |
| Direct File Transfer | XEP-0234, XEP-0261 | ✅ | Jingle FT + IBB fallback (plus SOCKS5 XEP-0260, beyond the requirement) |
| Quality and Performance improvements | XEP-0293, XEP-0294, XEP-0338, XEP-0339 | ✅ | rtcp-fb, rtp-hdrext, BUNDLE grouping (XEP-0338, calls only), SSRC/source |

### Not implemented

- **XEP-0084 (User Avatar)** — the PEP avatar node is not used; avatars come
  from the vCard PHOTO (XEP-0054).
- **XEP-0398 (User Avatar to vCard-Based Avatars Conversion)** and **XEP-0153
  (vCard-Based Avatars)** — the avatar *data* is taken from the vCard, but the
  presence hash/update protocol and the XEP-0084↔vCard conversion are not
  implemented, so "User Avatar Compatibility" is only partially met.
- **XEP-0191 (Blocking Command)** — not implemented.
- **XEP-0402 (PEP Native Bookmarks)** — bookmarks use XEP-0048 via XEP-0223
  pubsub storage (XEP-0049 private XML as a fallback).
- **XEP-0410 (MUC Self-Ping)** — no self-ping; join reliability relies on
  presence, retries and XEP-0198.

## Specifications of note

Listed by XEP-0479 as useful but **not required** for compliance (only the
notes of the applicable suites).

| XEP | Status | Notes |
|-----|--------|-------|
| XEP-0077 (In-Band Registration) | ✅ | service registration + account creation |
| XEP-0066 (Out-of-Band Data) | ✅ | plugin registered; sharing uses Jingle/HTTP Upload |
| XEP-0392 (Consistent Color Generation) | ✅ | HSLuv hue→RGB for XEP-0317 hat colours |
| XEP-0393 (Message Styling) | ✅ | `*bold*`/`_em_`/`` `code` ``/quote/pre |
| XEP-0424 (Message Retraction) | ✅ | own-message retraction + tombstones |
| XEP-0425 (Moderated Message Retraction) | ✅ | MUC moderator retraction |
| XEP-0157 (Contact Addresses for XMPP Services) | ❌ | not implemented |
| XEP-0385 (Stateless Inline Media Sharing) | ❌ | not implemented |
| XEP-0433 (Extended Channel Search) | ❌ | not implemented |

## Future development

XEP-0479 §3 lists specifications that are not yet required for compliance.
Stanza IM does not implement any of them (except where noted).

| XEP | Status | Notes |
|-----|--------|-------|
| XEP-0386 (Bind 2) | ❌ | investigated; requires XEP-0388 SASL2, not implemented |
| XEP-0409 (IM Routing-NG) | ❌ | |
| XEP-0397 (Instant Stream Resumption) | ❌ | XEP-0198 resumption is used instead |
| XEP-0401 (Easy User Onboarding) | ❌ | |
| XEP-0379 (Pre-Authenticated Roster Subscription) | ❌ | |
| XEP-0445 (Pre-Authenticated In-Band Registration) | ❌ | |
| XEP-0333 (Displayed Markers) | ⚠️ | only as an optional XEP-0490 MDS server-assist marker |
| XEP-0369 (MIX) | ❌ | |
| XEP-0380 / XEP-0420 (E2EE tagging / Stanza Content Encryption) | ❌ | |
| XEP-0384 / XEP-0396 (OMEMO) | ❌ | |
| XEP-0374 (OpenPGP for XMPP) | ❌ | |
| XEP-0225 (Component Connections) | — | N/A (client) |
| XEP-0390 (Entity Capabilities 2.0) | ❌ | XEP-0115 is used |
| XEP-0455 (Service Outage Status) | ❌ | |

## Maintenance

`CHECKLIST.md` is a **living document**, like `XEPs.md`, `SPEC.md` and
`AGENTS.md`. Whenever a compliance-relevant XEP (one referenced by XEP-0479)
is implemented, removed, or starts being used differently:

1. update its row in the `Client` / `Advanced Client` / `Specifications of
   note` / `Future development` table (status and notes),
2. move it between the "Not implemented" list and the relevant table as
   appropriate,
3. keep it consistent with `XEPs.md` (which lists every XEP the client uses),
4. do all of this in the **same commit** as the code change.

`tests/test_spec_sync.py` guards the structure of this file.
