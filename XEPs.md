# Stanza IM — Supported XMPP Extensions (XEPs)

The client is built on [slixmpp](https://slixmpp.readthedocs.io/) and registers
the extensions below in `stanza_im/core/client.py`. This list is a living
document — update it whenever a new XEP is implemented.

| XEP | Name | Where the client uses it |
|-----|------|--------------------------|
| XEP-0004 | Data Forms | Renders the XEP-0004 forms used by search, in-band registration and ad-hoc commands into a Qt form widget. |
| XEP-0030 | Service Discovery | `ServiceBrowserDialog` discovers conferences/gateways/services, the conference browser lists rooms, and `get_info`/`get_items` drive variant lookups. |
| XEP-0045 | Multi-User Chat | Joining/leaving conferences, roles and affiliations, the participant sidebar, and MUC private messages. |
| XEP-0048 | Bookmarks | Saves/removes conference bookmarks (menu "Conferences") and auto-joins rooms flagged for auto-join on startup. |
| XEP-0049 | Private XML Storage | Legacy bookmark store backend (when the server lacks pubsub-based XEP-0223 storage). |
| XEP-0050 | Ad-hoc Commands | `AdHocDialog` executes remote commands exposed by a service. |
| XEP-0054 | vCard | Displays/edits the own and contacts' vCards; avatar PHOTO data is cached by `include/avatars.py`. |
| XEP-0055 | Search | `SearchDialog` runs both legacy (Jabber Search) and form-based searches. |
| XEP-0059 | Result Set Management | Brought in by XEP-0313 for MAM pagination (large archive queries). |
| XEP-0066 | Out of Band Data | Plugin registered; actual file transfer is a Phase 2 stub (`send_file`). |
| XEP-0077 | In-Band Registration | `RegistrationDialog` fetches and submits service registration forms. |
| XEP-0082 | XMPP Date and Time Profiles | Normalizes server timestamps to canonical UTC ISO-8601 (`_normalize_ts`). |
| XEP-0085 | Chat State Notifications | Sends typing/composing states and shows the remote activity suffix in the chat window title. |
| XEP-0280 | Message Carbons | Copies of 1:1 messages sent/received by other of our resources are shown in the matching chats (`carbon_received`/`carbon_sent` in `core/client.py`, config `connection.message_carbons`) and stored in history. |
| XEP-0308 | Last Message Correction | Any of our own messages can be edited (Ctrl+Up for the last one, "Edit" in the message context menu); the input switches to edit mode with a cancelable banner and sending a correction attaches `<replace xmlns='urn:xmpp:message-correct:0' id='…'/>` (new stanza id) which replaces the original locally. Incoming corrections replace the message (✎ marker) or, with `chat.allow_incoming_edits` off, arrive as new messages. |
| XEP-0363 | HTTP File Upload | Uploads a file to a discovered HTTP Upload service (`urn:xmpp:http:upload:0`): requests a `<slot>` (filename/size/content-type), PUTs the bytes, and sends the returned `get` URL as the chat message (1:1 or MUC). Triggered from the chat toolbar, drag-and-drop into the chat window, and the roster "Send file → HTTP Upload" menu item. |
| XEP-0092 | Software Version | Contact and MUC participant tooltips show the remote client (`plugin["xep_0092"]`). |
| XEP-0096 | SI File Transfer | Not implemented yet — pre-registered for the Phase 2 file transfer work. |
| XEP-0107 | User Mood | Mood/activity name tables used for UI labels; publishing is not implemented yet. |
| XEP-0108 | User Activity | Activity group/sub-activity tables for UI labels; publishing is not implemented yet. |
| XEP-0128 | Service Discovery Extensions | Registers the disco identity/features extensions advertised to other clients. |
| XEP-0184 | Message Delivery Receipts | Marks delivered messages with a ✓ and requests receipts on sent stanzas. |
| XEP-0199 | XMPP Ping | Pings contacts/participants (`plugin["xep_0199"].ping`) for the connection diagnostics. |
| XEP-0202 | Entity Time | Displays the remote entity's time in contact diagnostics. |
| XEP-0203 | Delayed Delivery | Reads `<delay>` stamps for the original message time in MAM results and offline messages. |
| XEP-0223 | Persistent Storage | Conference bookmarks persist via pubsub storage (`plugin.storage_method == "xep_0223"`). |
| XEP-0224 | Attention | Support for attention requests ("nudge") between users. |
| XEP-0245 | The /me Command | Renders message bodies starting with `/me ` as "* sender phrase" italic action lines across every render path (live, history pagination, both chat backends); the body goes to the wire unchanged. The `/nick` command (rejoin with a new nickname) is an MUC companion feature. |
| XEP-0297 | Stanza Forwarding | Brought in by XEP-0313 to unwrap forwarded MAM results. |
| XEP-0313 | Message Archive Management | Loads server-side history for a chat (`plugin["xep_0313"], RSM-paginated`) into the conversation. |
| XEP-0393 | Message Styling | Parses `*bold*`/`_em_`/`` `code` ``/blockquote/pre markup (`xmpp/message_styling.py`), advertised via `urn:xmpp:styling:0`, toggleable in Preferences → Chat. |
| XEP-0461 | Message Replies | Reply button in message actions composes a reply with a quote banner; sends `<reply xmlns='urn:xmpp:reply:0' to='…' id='…'/>` as the first child of `<message>` (or falls back to a plain message without a reply source), picks the referenced id from `origin-id`/`id` in 1:1 chats and the server `stanza-id` in MUC, adds an XEP-0421 fallback body quote for legacy clients (`_send_reply`/`_attach_reply` in `core/client.py`), and renders the referenced message as a `.stanza-reply` bar above the body. |
| XEP-0490 | Message Displayed Synchronization | Own-device "displayed up to" state is published to the private PEP node `urn:xmpp:mds:displayed:0` (item id = chat JID, payload `<displayed><stanza-id …/></displayed>`, publish-options when supported, optional server-assist via a companion XEP-0333 marker); PEP notifications and a catch-up fetch apply remote displayed states (clearing unread + a status line). Config `chat.message_displayed_sync`. |

## Legacy / unplanned

Original Jabbim (2007-2012) code is kept in `old/` as reference only and is not
part of the Stanza IM protocol surface.