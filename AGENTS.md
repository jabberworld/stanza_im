# AGENTS.md — Stanza IM Architecture

## Language

**Always explain your work in Russian.** Every plan, progress note, status
update and any commentary addressed to the user MUST be in Russian.

This rule holds **after every context reset or session compaction**: `AGENTS.md`
is re-read then, so switch to Russian immediately rather than waiting to be
asked again.

Code, identifiers, code comments, commit messages and the documentation files
(`AGENTS.md`, `SPEC.md`, `XEPs.md`) stay in English as before.

## Response conventions

When a reply lists several items or asks several questions, keep them in
**ascending order** matching the order of the referenced task items (1 → N).
Do not reorder between "items" and "questions": item 1 first, then 2, 3, ….

## Overview

Stanza IM is a lightweight XMPP/Jabber desktop client for Linux, inspired by the
original Jabbim client (2007-2012). Written in Python 3 + PyQt6 + slixmpp.
The supported XMPP extensions are listed in `XEPs.md`; the detailed behavioral
specification is `SPEC.md`. All three files are living documents — see
[Documentation Maintenance](#documentation-maintenance).

**Design goals**: lightweight, fast, low memory usage, modern XMPP standards.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| GUI | PyQt6 + PyQt6-WebEngine |
| XMPP | slixmpp (asyncio-based) |
| Async bridge | qasync (`qasync.QEventLoop`) — no busy-loop, ~0% idle CPU |
| Persistence | XDG Base Directory + TOML config + JSONL chat history |
| Chat rendering | QWebEngineView + QWebChannel (HTML/CSS themes) |
| Roster rendering | Custom QPainter on QWidget (no QTreeView) |
| i18n | Python dicts in `stanza_im/i18n/*.py`, no compilation |

## Directory Structure

```
stanza_im/                      # Python package
├── __init__.py
├── __main__.py                  # python -m stanza_im
├── app.py                       # Entry point: qasync event loop
├── core/
│   ├── client.py                # JabberClient: slixmpp wrapper, TLS/proxy/SM/CSI
│   ├── storage.py               # Config (TOML) + JSONL chat history (XDG)
│   ├── history.py               # SQLite history; RLock + store_many + async wrappers
│   ├── known_contacts.py        # Persisted JID → name/groups/conference registry
│   ├── omemo_aliases.py         # XEP-0384 device-name aliases (private PEP node)
│   ├── unread_state.py          # Persisted per-chat read state (unread/mentions/anchor)
│   ├── profiles.py              # Account registry + per-profile data dirs (JSON)
│   ├── vcard_cache.py           # vCard avatar download coordination
│   ├── discovery.py             # XEP-0065 proxy + STUN/TURN SRV discovery + cache
│   ├── privacy.py               # XEP-0016 privacy-list parse/build helpers
│   ├── server_features.py       # Server disco/stream capability report (XEP list)
│   └── memstats.py              # Periodic memory statistics (CLI -m)
├── ui/
│   ├── main_window.py           # Main window: stack (login/splash/roster)
│   ├── login_widget.py          # Login form + config prefill/save + profile selector
│   ├── profiles_dialog.py       # Application profile manager (create/apply/delete)
│   ├── profile_source_dialog.py # "Existing account" vs "Register new" choice
│   ├── existing_account_dialog.py # Existing-account credentials/connection form
│   ├── roster_widget.py         # Custom-painted contact list
│   ├── roster_style.py          # QPainter roster rendering strategy
│   ├── resource_tree.py         # Shared per-resource client-block HTML
│   ├── chat_window.py           # Tab container for conversations
│   ├── chat_widget.py           # Single chat tab content
│   ├── chat_view.py             # QWebEngineView + QWebChannel bridge
│   ├── chat_themes.py           # Adium-style theme HTML generator
│   ├── nick_colors.py           # Session MUC nickname → color allocation
│   ├── font_zoom.py             # Ctrl+wheel font-size helper (input/roster/MUC)
│   ├── resize_handle.py         # Thin draggable bar resizing a field (input/results)
│   ├── zoom_list.py             # List with Ctrl+wheel zoom + empty-click deselect
│   ├── preferences.py           # Settings dialog (icon nav, nested tabs)
│   ├── media_preview.py         # Inline image/audio/video previews
│   ├── media_viewer.py          # Fullscreen image/video viewer (Ctrl+wheel zoom)
│   ├── whiteboard_dialog.py     # Whiteboard dialog (tool palette + canvas)
│   ├── whiteboard_canvas.py     # QPainter whiteboard canvas + SVG export
│   ├── map_widget.py            # In-app OSM map window (geo: URIs, live track)
│   ├── emoji_picker_dialog.py   # XEP-0444 reaction picker (search/categories/recent)
│   ├── smiley_picker.py         # Emoticon-set smiley picker (Qt.Popup grid; unicode reuses the emoji picker)
│   ├── omemo_devices_dialog.py  # XEP-0384 device/trust manager
│   ├── omemo_popup.py           # Chat shield: quick device trust/rename popup
│   ├── qr_dialog.py             # QR code dialog (OMEMO fingerprint)
│   ├── reactions_list_dialog.py # XEP-0444 full reaction list ("+k" chip)
│   ├── upload_dialog.py         # HTTP upload / P2P progress dialog
│   ├── incoming_file_dialog.py  # Incoming Jingle file-offer confirmation
│   ├── call_window.py           # Call UI (incoming prompt, active call, Muji)
│   ├── device_test.py           # Devices self-tests (mic meter/tone/camera)
│   ├── status_message_dialog.py # Multiline presence status editor
│   ├── suspend_monitor.py       # logind/UPower sleep notifications (presence)
│   ├── captcha_dialog.py        # XEP-0158 CAPTCHA challenge prompt
│   ├── account_registration_dialog.py  # XEP-0077 account creation wizard
│   ├── registration_result_dialog.py   # Created-account summary (apply/copy)
│   ├── history_manager.py       # Per-contact history browser
│   ├── service_browser.py       # XEP-0030 service discovery browser
│   ├── service_info_dialog.py   # Service info (version/stats/caps/contacts)
│   ├── certificate_dialog.py    # Server TLS certificate details dialog
│   ├── connection_info_dialog.py # Live connection details dialog
│   ├── server_info_dialog.py    # Server capability report (XEP support)
│   ├── cache_dialog.py          # Cache sizes + per-cache clearing (Help)
│   ├── privacy_lists_dialog.py  # XEP-0016 privacy-list manager
│   ├── privacy_rule_dialog.py   # XEP-0016 rule add/edit dialog
│   ├── blocked_contacts_dialog.py # XEP-0191 blocklist editor
│   ├── report_dialog.py         # XEP-0377 spam/abuse report dialog
│   ├── xml_console.py           # Raw XML console (filtered, coloured)
│   ├── pep_manager_dialog.py    # PEP node manager (list/open/config/delete)
│   ├── tray.py                  # System tray icon + blink
│   ├── osd.py                   # OSD on-screen notification stack
│   ├── sounds.py                # Sound-effect player (QSoundEffect)
│   ├── url_schemes.py           # stanza/mam/xmpp QWebEngine scheme registration
│   ├── icons.py                 # LRU icon cache (lazy, auto-evict)
│   └── jid_edit.py              # JID line edits (paste normalisation, room split)
├── xmpp/
│   ├── message_styling.py       # XEP-0393 Message Styling parser
│   ├── message_markup.py        # XEP-0394 Message Markup parser/renderer
│   ├── jingle.py                # XEP-0234/0260/0261 Jingle FT + IBB
│   ├── jet.py                   # XEP-0391/0396 Jingle Encrypted Transports (OMEMO key)
│   ├── jingle_rtp.py            # XEP-0167/0176 Jingle RTP calls + SDP bridge
│   ├── jmi.py                   # XEP-0353 Jingle Message Initiation (shared)
│   ├── muji.py                  # XEP-0272 multiparty Jingle coordination
│   ├── media.py                 # aiortc media engine (capture/playback)
│   ├── bytestream.py            # SOCKS5 bytestream client + direct listener
│   ├── sxe.py                   # XEP-0284 Shared XML Editing record model
│   ├── whiteboard.py            # Collaborative SVG whiteboard (Jingle app + SXE)
│   ├── omemo/                   # XEP-0384 (availability/storage/plugin/manager/SCE/QR)
│   └── socks5.py                # Dependency-free SOCKS5 CONNECT for the account proxy
├── include/
│   ├── constants.py             # Paths, VERSION, APP_NAME, XDG dirs
│   ├── enumerators.py           # XMPP show/icon/mood/activity maps
│   ├── emoji_data.py            # XEP-0444 emoji catalogue (categories + search)
│   ├── pep.py                   # XEP-0080/0107/0108/0118 payloads + icon packs
│   ├── geo.py                   # RFC 5870 geo: URIs, Mercator math, track, tile cache
│   ├── xmpp_uri.py              # XEP-0147 xmpp: URI parse/build (RFC 5122)
│   ├── hats.py                  # XEP-0317 Hats + XEP-0392 HSLuv colour generation
│   ├── clients.py               # XEP-0115 caps node → client name/icon mapping
│   ├── sounds.py                # Sound-theme discovery/parsing (resources/sounds)
│   ├── svg_path.py              # SVG path-data parser/builder (QPainterPath)
│   ├── svg_transform.py         # SVG transform (matrix) parse/compose (no Qt)
│   └── utils.py                 # format_time, escape_html, etc.
├── i18n/
│   ├── __init__.py              # tr() function + auto language detection
│   ├── en.py                    # English strings (~530 keys)
│   └── ru.py                    # Russian strings
├── plugins/
│   ├── __init__.py              # Plugin registry (discover/manifest/hooks)
│   ├── notes/                   # Notes plugin (XEP-0049 private storage)
│   ├── attention/               # XEP-0224 attention plugin
│   └── digest/                  # Unread/messages digest (sticky OSD)
resources/                       # Images, chat skins, sounds, etc.
old/                             # Original Jabbim code (reference only, gitignored)
README.md                        # Общее описание проекта (назначение, возможности, зависимости)
FEATURES.md                      # User-facing feature list (living document)
main.py                          # python main.py entry point
pyproject.toml                   # Package config (distribution: stanza-im)
AGENTS.md                        # This architecture guide (living document)
SPEC.md                          # Detailed specification (living document)
XEPs.md                          # Supported XEP list (living document)
CHECKLIST.md                     # XEP-0479 Client/Advanced Client checklist
```

Additional UI modules include `ui/preferences.py`, `ui/add_contact_dialog.py`,
`ui/conference_dialog.py`, `ui/muc_config_dialog.py` and
`ui/hats_dialog.py`. The add-contact dialog has a compact "Service ID
translator" group (a `QVBoxLayout`: description over a `prompt` + fixed-size
"Get XMPP address" button, so the field grows); each of the Jabber ID and
Nickname fields carries a 16px icon button — `v-card.png` (tooltip `chat_vcard`)
emits `vcard_requested(jid)` for the entered address (`MainWindow._on_add_contact`
connects it to `_show_profile`), and `nick-fill.svg` (tooltip
`add_contact_fill_nick`) fetches the vCard and fills the nickname from `nickname`,
else `fn`, else the JID localpart. Its **service selector** lists the
transports the user actually **added** (`gateways=[(name, jid)]` from
`MainWindow._transport_gateways`, with `preselect=<jid>`) — never every gateway
of the account domain — so a contact can be added through a chosen transport.
The conference dialog
provides conference joining,
XEP-0030 room browsing, room vCard requests and JID copying. Conference
servers are persisted in `connection.conference_servers`; XEP-0048 bookmark
names are preserved and used as the menu label with a localpart fallback.
Bookmarks are stored with XEP-0402 PEP Native Bookmarks
(`urn:xmpp:bookmarks:1`, `core/client.py` `save_bookmark`/`list_bookmarks`/
`remove_bookmark`): legacy XEP-0048 bookmarks are migrated into the node, and
when the server does not announce `urn:xmpp:bookmarks:1#compat`/`#compat-pep`
the legacy XEP-0048 storage is kept in sync too; `+notify` updates refresh the
tab and auto-join/leave rooms (`_handle_bookmarks2_event`).

The roster window is a **tabbed host** (`MainWindow._build_roster_tabs`): an
icon-only `QTabBar` (tooltip = purpose) over a `QStackedWidget` with four tabs —
**Contacts** (the whole existing roster content), **Bookmarks**, **Events** and
**Transports**.
The Contacts tab (icon `system-users.png`) is active at startup and is the
`self._roster_page` placed in the stack/`QSplitter` (the `unified` layout wraps
only this left part). The Bookmarks tab (icon `bookmarks.svg`)
replaces the old menu: a search field plus a `QListWidget` of the conferences
(`_rebuild_bookmarks_view`), where a double click joins (`_join_bookmark`) and
the right-click menu offers Join (`ok.png`) / Edit (`edit.png`) / Share
(`send-arrow.svg`, sends `xmpp:<room>?join` through the share dialog,
`_share_bookmark`) / Auto-join (checkable) / Remove
(`_set_bookmark_autojoin`/`_remove_bookmark_confirmed`);
it loads the server bookmarks on tab activation (`_on_roster_tab_changed` →
`_load_bookmarks`). Below the list a toolbar of four wide (2:1) icon-only
buttons — Join (`ok.png`), Create (`about.png`), Edit (`edit.png`) and Remove
(`process-stop.png`) — covers the same actions; Join/Edit/Remove are enabled
only while a bookmark is selected (`_update_bookmark_actions`). Create and Edit
open `ui/bookmark_dialog.py::BookmarkDialog` (name / nickname / room / free-text
server / password / auto-join) and save via `client.save_bookmark`
(`_save_bookmark_values`); editing to a different room address removes the old
bookmark first, and removal always asks for confirmation
(`_remove_bookmark_confirmed`). The list shows the name (JID only in the
tooltip) and shares the roster font settings
(`_apply_roster_font`); `ui/zoom_list.ZoomListWidget` (used by the bookmarks,
events and notes lists) gives Ctrl+wheel font zoom and clears
the selection on a click over empty space. The Events tab
(icon `event`) — a search field and a list of system/subscription events; each
entry carries its time (`_push_system_event` prefixes `HH:MM`,
`_SubscriptionRequestRow` shows a timestamp label); new events **accumulate**
(the "events_empty" placeholder is marked with a `UserRole` flag so it — and
only it — is removed on the first real entry; an earlier check keyed on "a
single widget-less item" wrongly wiped the first event on the second push).
A smooth tab-icon blink
(`_start_event_blink`/`_event_blink_step`, the same cosine fade as the tray)
stops and clears when the tab is shown. The **Transports** tab (icon
`transports.png`) lists the roster contacts classified as gateways and manages
them: `_classify_transports` probes the roster's **server JIDs (no `@`)** once
each (cached in `_transport_jids`/`_transport_probed`,
`client.discover_service_info` identity `category == "gateway"`) on roster load
(`_on_roster_received`/`_on_roster_item_added`) and on tab activation — an
ordinary `user@host` contact or `room@conf` conference is never probed. The
result is persisted per profile (`core/transports.py` → `transports.json`) and
read back in `_load_transports` **before** the roster is built, so a gateway
never flashes in the Contacts roster (nor lingers there on a slow/offline
login); a definite non-gateway answer for a persisted JID drops it back into the
roster and a full roster prunes JIDs the server no longer returns
(`_prune_transports`). A classified transport is filtered out of the Contacts
roster (`_add_roster_item` skips it, `_probe_transport` removes the row) and
rendered by a **second `RosterWidget`** (`_transport_roster`, same
renderer/tooltip/font/colors, no group header). Its
context menu (`_on_transport_context`) offers Connect/Disconnect (a **directed**
presence — `JabberClient.send_directed_presence(to, type, status, priority)`;
`_toggle_transport` sends `unavailable` to disconnect or an available presence
to connect), vCard, chat, history, rename, the subscription submenu, the
ad-hoc command menu, «Добавить контакт через этот транспорт»
(`_on_add_contact_via_transport` → `AddContactDialog(preselect=…)`) and Remove
(confirmed, `_remove_transport_confirmed` → `remove_contact`). A bottom toolbar
(in the bookmarks style: a fixed-height bar of wide 2:1 icon-only buttons)
mirrors Connect/Disconnect (`_on_transport_toggle`; the icon shows the
**current** state — the dedicated `connected.svg`/`disconnected.svg`, a
diagonal chain with every link intact vs. with the middle link broken — while
the tooltip names the action),
Commands (`_on_transport_command` → `_open_adhoc`) and Remove, enabled only
while a transport is selected (`_update_transport_actions`, driven by
`contact_clicked` and the `RosterWidget.selection_changed` signal so an empty
click clears them). `_on_presence_changed` updates the transport row and the
button **live** (a disconnected transport turns offline). Ctrl+PgUp/PgDn cycles
the roster tabs only in the `separate` layout with the main window active
(`_cycle_roster_tab`); in `unified` the chat keeps the shortcut for its own tabs.
The conference browser uses the names and metadata returned by the service's
`disco#items` response and does not issue one `disco#info` request per room.
vCard information dialogs are opened **non-modally** (`_open_vcard_info`:
`setModal(False)` + `show()`, never `open()`/`exec()`) so the user can copy the
address from another window while it is open; the tab widget stretches
(`layout.addWidget(tabs, 1)`) so the tabs hug the header instead of leaving a
gap above them. `VCardInfoDialog` carries a "Обновить"/"Refresh" button (`refresh_requested`
→ `MainWindow._refresh_vcard` → `get_vcard(force=True)`); when the vCard
arrives, `_open_vcard_info` updates the already-open window in place
(`update_card`: header + field labels rewritten, the content widget is not
recreated and the active tab is preserved) instead of opening a second one,
and re-issues `probe_entity` (now a client **ping** only) so the Status tab
refreshes too (`update_status` merges values without switching tabs). The Status
tab renders per-resource client blocks (`_render_clients` → the shared
`ui/resource_tree.py::resource_tree_html`, the same tree as the roster tooltip)
in a dedicated **«Клиенты:»** form row (label left, tree right, hidden when
empty) built by `MainWindow._vcard_status` from `contact.resources` — or, for a
MUC participant opened from the room (`_show_muc_participant_profile` sets
`_vcard_muc_ctx`), from the single occupant — while a plain 1:1 contact is never
given a room nick (the old bogus «Ресурс»). Each client line reads «Клиент: name
version / OS»; the old per-entity «Клиент»/«Версия клиента»/«ОС»/«Время
клиента» rows are gone (client, version, OS and the local time live only in the
tree, per resource), leaving `ping` as the single entity row. The «Клиенты»
caption is top-aligned so the first resource name lines up with it, the dialog
opens with headroom (`_apply_default_size`, 700×550 clamped to the screen) and
every tab page is wrapped in a `QScrollArea` (`_scrolled`, widget-resizable, no
frame) so a long wrapped value (a status message) is never clipped when the
dialog is smaller than its content. The tree fills in as answers arrive
(`contact_client_updated` → `update_status`, and `groupchat_presence_details`
for a MUC occupant), and the "Refresh" button re-requests the resource versions
(`probe_resource_versions`). «Визитка обновлена» is shown as local
`YYYY-MM-DD HH:MM:SS` (`format_local_datetime`). Only the Close button
accepts the dialog — the `QDialogButtonBox.clicked` signal fires for every
button, so it must not be connected wholesale (a refresh would otherwise
close the window). `_find_open_vcard`
matches an open dialog by bare JID so a bare/full-JID key mismatch never opens
a second window.
Chat and MUC tabs use separate `ChatThemeFactory` instances, while emoticon
sets are discovered from `resources/emoticons/*/smileys*.cfg`. Preferences
show a live preview of the selected emoticon set. A set's `smileys*.cfg` maps
many text aliases to the same image; the picker and the preview list are keyed
by the **file** (one row per distinct image, `include.emoticons._file_codes`
keeps the longest alias), so `:)` and `:-)` never duplicate a row, while
`smile_to_html` still renders every alias. The emoticon-theme selector also
offers the `unicode` pseudo-skin (`include.emoticons.UNICODE_SKIN`): it has no
``smileys*.cfg`` set (every lookup is empty) and
`ChatWidget._open_smiley_picker` reuses the XEP-0444 reaction picker
(`EmojiPickerDialog`, search + recent + categories) through the
`emoji_picker_requested` signal → `MainWindow._on_emoji_picker_requested`
(anchored next to the smiley button like a reaction). The selector's last entry
is **«Без смайликов»** (`include.emoticons.NO_SKIN = "none"`): smiley rendering
is off entirely (no images, no unicode; the chat smiley button is a no-op). It
is a pseudo-skin too, so its label is localized. The legacy `none/smileys.cfg`
set id (the removed `resources/emoticons/none` directory) is normalized to
`NO_SKIN` by `include.emoticons.normalize_skin`, and `get_set` never falls back
to the default set for it. With
`appearance.emoticon_unicode_replace` (default on, Preferences → Appearance →
«Темы») `smile_to_html` substitutes the text codes with unicode emoji from
`include.emoticons.unicode_map()` — a `{code: emoji}` map derived from the
`default` theme's image semantics (`_UNICODE_BY_FILE`, one emoji per image, so
`: )`/`:-)` share 🙂). The substituted emoji are drawn with the platform font
(no chat-font override is injected). A code is converted only when it is not
adjacent to a letter or digit (any script): `200:/bla` and `Привет:)` stay
intact while `:):):)` and `:).` convert; the same boundary guards the image
substitution in `smile_to_html` (`_boundary_ok`/`_sub_guarded`).

**Room management** (`ui/muc_config_dialog.py`): the MUC header carries a gear
button right after the bookmark (`ChatWidget._config_btn`), hidden on 1:1 tabs
and enabled only for owners/admins (`MainWindow._apply_muc_admin` derives our
affiliation from `_muc_users`). It opens a non-modal `MucConfigDialog` with four
tabs: «Участники» — a `QTreeWidget` grouped into Владельцы/Администраторы/
Зарегистрированные пользователи/Заблокированные (owner/admin/member/outcast)
with «Jabber ID» and «Примечание» columns (the note is the XEP-0045 `<reason>`)
and Add/Edit/Delete buttons (Delete sets affiliation `none`); «Шапки» —
XEP-0317 hats (see below); «Настройки» —
enabled for the owner only and hosts the `muc#owner` room-configuration
`DataFormWidget` (its `list-single` selectors are aligned to one width via
`_align_selectors`); «Управление» — the owner only: a note that the room is
removed for every participant (the bookmark is kept), an optional «Причина»
and «Удалить конференцию» (confirmed) → `client.destroy_room` →
`xep_0045.destroy` (XEP-0045 §10.9), then the `room_destroyed` signal, an
error shown inline instead of a silent failure. Edits are collected and applied on «Ок» via
`client.muc_set_affiliation`/`client.muc_set_config`; `client.muc_get_affiliations`
builds a custom `muc#admin` IQ so the `reason` survives (slixmpp's helper keeps
only JIDs). The «Шапки», «Настройки» and «Управление» pages are wrapped in a
`QScrollArea`, so a long configuration form never pins the window: it can be
shrunk (460×300 minimum, size grip) and scrolls instead. The dialog opens
~1.5× taller (`_initial_height`, ≈720 px bounded by 85 % of the screen) and its
width follows the content (`_fit_to_content`, only growing, ≤90 % of the
screen), so the usual form needs no horizontal scrollbar; a page wider than the
screen still scrolls and the window stays resizable. [`tests/test_muc_config.py`]

**Voice requests (XEP-0045 §7.13)**: a visitor in a moderated room asks for
voice with a bodyless `<message>` (**no `type`** — a `groupchat` type would be a
broadcast and is rejected with `forbidden`) carrying a `muc#request` data form
(`FORM_TYPE=http://jabber.org/protocol/muc#request`, `muc#role=participant`);
`JabberClient.request_voice` builds it and never sets `from`. The stanza is
matched by its own `MatchPath` on `message/{jabber:x:data}x`
(`_on_bodyless_voice_stanza`) — a legacy `<x xmlns='…muc#user'><item
affiliation='member'/></x>` from an occupant JID (`room/nick`, with no `jid` on
the item) is still recognised by `_muc_voice_request`, while an
affiliation-change notification (from the bare room and/or naming a `jid`) is
not —
and emitted as `muc_voice_requested(room, jid, nick)`. A rejected request (the
server throttles repeats with `<error type='wait'><resource-constraint/>`) is
matched on the same bodyless path; the sent message's `id` is tracked in
`JabberClient._voice_requests` and `_voice_request_error` turns the reply into
`voice_request_failed(room, condition, text)`.
The MUC action panel above the input gains a «Попросить голос» bell/megaphone button
(`ChatWidget.set_voice_request`, icon `voice-request.svg`), visible/enabled only
when we are a `visitor` **and** the room is moderated (`MainWindow.
_apply_voice_request`, from `disco#info` features `muc_membersonly`/
`muc_moderated` emitted by `_fetch_muc_info`). Incoming requests are surfaced
only to moderators/owners/admins (`_can_moderate_room`): an Events row
(`_VoiceRequestRow`) «Пользователь … просит право голоса» with «Предоставить»
(`client.grant_voice(room, nick, jid)` → `muc#admin` `<item role='participant'/>`,
XEP-0045 §8.3) / «Отклонить» (marks the row only), plus an OSD and a tray
balloon. `MainWindow._on_muc_voice_request` uses the requester's **occupant JID**
(`room/nick`, not the bare room) as the target and derives the nick from it when
the stanza carried none, so the row names the visitor and the grant reaches the
right occupant. A **failed** request (`voice_request_failed`, e.g. the server rate-limit
`resource-constraint`) is shown to the user via a tray balloon, an OSD (when
enabled) and a chat status line; the «Попросить голос» button stays enabled.
When a message is **rejected** because we have no voice (the server returns
`<message type='error'><error type='auth'><forbidden/>`), the client emits
`muc_send_forbidden` (`_on_muc_message_error_stanza`, matched on the bodyless
`message/{error}` path) and the chat shows a one-line prompt
(`ChatWidget.show_voice_prompt`, at most once per 10 s) with an
`<a href="stanza:voice">` link that fires the same `voice_requested` action as
the toolbar button.
[`tests/test_muc_voice.py`]

**Hats (XEP-0317, `include/hats.py` + `ui/hats_dialog.py`)**: occupants'
`<hats xmlns='urn:xmpp:hats:0'/>` presence lists are parsed by
`JabberClient._on_groupchat_presence` into `gi.users[nick]["hats"]` and emitted
with `groupchat_presence`; `MainWindow._muc_users[room][nick]["hats"]` feeds the
participant tooltip (`ChatWidget._participant_tooltip`, a «Шапки» line) and the
message chips. `HatsTab` (embedded in `MucConfigDialog`, always shown; a room
without `urn:xmpp:hats:0` gets a notice and disabled buttons) lists configured
hats as top-level categories with their assigned users underneath and offers
Создать/Изменить/Назначить/Снять/Удалить (Изменить/Удалить need a category
selected, Снять a user, Назначить at least one hat; owner/admin only). The hat
URI is `urn:xmpp:hats:<sha1(room + "\x00" + title)>`; the optional colour is a
`hats#hue` angle turned into RGB by the XEP-0392 HSLuv implementation in
`include/hats.py`. Management uses the `urn:xmpp:hats:commands` ad-hoc
`create`/`destroy`/`list`/`list-assigned`/`assign`/`unassign` nodes
(`client.hats_*`, custom IQs). A form is submitted with the action read from
the server's `<actions/>` (`complete` when there is none — ejabberd requires
the literal `complete`), and the URI field is whatever var the returned form
declares (`hats#uri` for create, `hat` for destroy/assign/unassign on
ejabberd). An error `<note/>`/status surfaces in the tab instead of being
silently reloaded away. The participant context menu
offers «Изменить роль» (visitor/participant/moderator, via
`client.set_muc_role`) and «Изменить ранг» (owner/admin/member/outcast/none, via
`client.muc_set_affiliation`), the latter enabled only when the occupant's real
JID is known and we are owner/admin (owner/admin options are the owner's alone);
then a gated «Шапка» submenu with «Назначить»
(preselects the user in `HatAssignDialog`) and «Снять» (`HatUnassignDialog`
lists the user's hats, then confirms). Messages render the sender's hats as
coloured `.stanza-hat` chips right of the nick. [`tests/test_hats.py`]

On «Ок» only the parts that actually changed are sent: affiliation edits go
through `client.muc_set_affiliation` (each pre-checked client-side against the
XEP-0045 rule — owners change any list, admins only member/outcast — so the edit
dialog warns immediately instead of deferring to the server), and the room
configuration is sent only when a form value changed, as a fresh `type='submit'`
form (`client.muc_set_config(room, values)`) so slixmpp never mutates the
server's own form (which raised `('options', None)`).

A room destroyed by its owner reaches the occupants as an unavailable
presence carrying `<x xmlns='http://jabber.org/protocol/muc#user'><destroy
jid='alternate'><reason/></destroy></x>`: `_muc_destroy_info(pres)` parses it and
`_on_groupchat_presence` reports it **once per room** (`_destroyed_rooms`),
drops `groupchats`/`_known_rooms` and ends the room's whiteboard sessions
(`WhiteboardManager.drop_room`), emitting `muc_destroyed(room, reason,
alternate)` — never a per-occupant "left" event. `MainWindow._on_muc_destroyed`
keeps the room tab open with a status line («Конференция … удалена» plus the
reason) and shows an OSD; our own delete (`_on_room_destroyed`) closes the tab,
stops the auto-join retries (`_drop_room_ui` clears every per-room map and the
conference roster row) and keeps the bookmark. [`tests/test_muc_destroy.py`]

**History behind an open tab**: a conference server replays its archive on
join as **delayed** groupchat messages — a XEP-0203 `<delay/>` is the reliable
signal; old servers send it **without** `<archived/>` (and `xep_0203` is not
registered, so the stamp is read from the XML, `_delay_stamp`). Any delayed
groupchat message is history: `JabberClient._on_groupchat_message` sets
`archived = bool(ts)` and `_on_groupchat_message`'s archived branch stores it
without rendering, sounding, OSD or unread counters. The MAM backfill may also
store rows while the tab is open. `ChatWidget.schedule_tail_refresh`
(debounced, also called after `server_fetch_done`) reloads the window only for
the visible, not-user-scrolled conversation (`refresh_tail_if_newer`; the flag
is set by an actual `last_seen` scroll-up and cleared when the view reaches the
bottom, so a transient "not at the bottom" while the page loads cannot block
it). A **join-time replay** (no archive id) forces the reload (`force=True`,
skipping the "nothing newer" check) because it is usually older than the tail
already on screen; a MAM page does not. The refresh keeps the unread boundary
and stays at the bottom; a suspended tab defers it to `resume`, a
background/user-scrolled tab is left alone. `TAIL[…]` debug lines trace the
merge. A groupchat message's stable id is its `origin-id` (falling back to the
room `stanza-id`, the MAM archive id and the stanza `id`), so the replay, MAM
and live copies of one message dedup; an archived row that finds no id match
**adopts** one id-less twin with the same direction/sender/body (an older build
stored the replay as live with the receive time): the ids are written onto that
row and its timestamp repaired, instead of adding a duplicate. Live rows never
adopt. Local paging is independent of the server archive: a room without MAM
(or a failed query, `mam_unavailable`) gets
`ChatWidget.set_server_archive_available(False)`, which only stops server
requests — scrolling up keeps loading the SQLite pages (`_on_near_top` no
longer treats `_server_exhausted` as "no history at all"). A near-top event
before the first local window is applied (`_initial_load_done`, set by
`set_history`) does nothing, so opening a room never fires a premature MAM
query or flashes the "loading from server" status. `history._insert` also
**repairs a stale timestamp** when an archive/origin/message id already exists with a
different one (the body is never rewritten — an edit is a separate update), so
an old malformed row cannot hide the new messages forever.
[`tests/test_history_tail_refresh.py`, `tests/test_history_dedup.py`]

**MUC join reliability**: presence status lines (`muc_user_joined`/`left`/
`muc_status_changed`) are shown only after a successful join — `MainWindow`
tracks `_muc_joined`/`_muc_join_grace` and suppresses them until
`_on_muc_joined` plus a 2 s grace window, so the server's initial occupant dump
is never rendered as "X joined". A MUC join error presence
(`<presence type='error'><x xmlns='…muc'/>`) is caught by a dedicated
`MatchXPath` handler (`client._on_muc_join_error_stanza`) — `join_muc_wait`
does not reliably raise for it, and slixmpp routes it to
`muc::<room>::presence-error` rather than `groupchat_presence` — and emitted as
`muc_join_error` with the condition (the condition/code are read by the pure
`_presence_error_condition` helper from `stanza["error"]["condition"]`/`["code"]`
— slixmpp has no `get_error()`). A permanent rejection (`muc_join_error` with
`forbidden`/`registration-required`/`not-allowed`/`banned`) aborts the optimistic
join (`_abort_muc_join`, which also cancels the pending join task): the
pseudo-occupant is dropped, the room is removed from the conference roster and
its tab closed, and the reason is shown — a `QMessageBox` with
`muc_join_cannot_join` for a manual join, a tray balloon/OSD for an auto-join — a
members-only room cannot be entered until we are added, so nothing is left
looking like a joined room.
`client._on_session_start` fetches the bookmark list **once, before the initial
presence** (the roster request is already in flight) and joins the auto-join
rooms from that fresh list — a room removed on another client is never joined,
and the join no longer queues behind the roster/PEP burst. A successful empty
answer is not an error; only a failed fetch is retried (1/2 s) in the
background, and the PEP subscriptions to the known contacts are background
work too. The fetched list is handed to the Bookmarks tab once
(`bookmarks_snapshot()`), so it needs no second request.
Auto-joined rooms are retried on transient
`muc_join_error` conditions (`timeout`/`unknown`/`remote-server-timeout`/
`internal-server-error`/`service-unavailable`) with a 5/15/45 s backoff, and
`client._autojoin_bookmarks` re-fetches the bookmarks and skips only rooms that
actually joined (a stale `GroupChatInfo` no longer blocks a retry; `join_muc`
cancels a pending join task). A bookmarked room that is also a normal roster
contact is moved to the conferences group before joining
(`_classify_bookmarked_conferences`) — only when it is actually joined or its
bookmark asks for auto-join; a plain (non-autojoin, unjoined) bookmark is not
forced into the Conferences group, and a room that is also a roster contact
stays in its own contact group. A **XEP-0410 self-ping** rounds this
out: `_muc_self_ping_loop` (started on `session_start`/`session_resumed`,
stopped on disconnect) pings our own occupant JID
(`<iq type='get' to='room/nick'><ping xmlns='urn:xmpp:ping'/></iq>`) after 15
minutes without any inbound room traffic; `service-unavailable`/
`feature-not-implemented`/`item-not-found`/`remote-server-timeout`/timeout keep
the room, any other error triggers `join_muc` (a rejoin). `_mark_muc_activity`
updates the per-room idle timer from groupchat presence/messages/subjects, and
a room mid-rejoin (`gi.joined` false, e.g. a `/nick` change) is skipped.
[`tests/test_muc_join.py`, `tests/test_muc_selfping.py`]

The MUC toolbar's vCard button opens the **room's** vCard (`MainWindow.
_show_muc_room_info` → `_show_profile(room)`, not our occupant's real JID). The
viewer (`VCardInfoDialog`) shows an Edit button for room cards, enabled for
owners/admins (`MainWindow._can_edit_room_vcard`); it reuses `VCardEditDialog`
(with `title_key="vcard_edit_room_title"`) and publishes via
`client.set_room_vcard` (`xep_0054.publish_vcard(..., jid=room)`, which also
refreshes the cached room card/avatar/title). The room vCard viewer, editor and
its confirmation boxes are parented to the chat window
(`MainWindow._chat_dialog_parent`), not the roster. [`tests/test_vcard_room.py`]

Conference display names honour `chat.muc_name_source` (Preferences → Chat →
«Конференции», which carries an info icon explaining the order):
`from_name` (default) resolves bookmark name → room/disco name → JID
localpart; `from_vcard` resolves bookmark name → vCard `fn` → vCard `nickname`
→ room/disco name → JID localpart. A bookmark name equal to the room JID
(slixmpp's default when no name is set) is ignored, and
`client.save_bookmark` drops that name element instead of storing the JID.
`MainWindow._muc_display_name` resolves it
and `_apply_muc_name` refreshes the tab title and roster row; the setting and
bookmark changes apply live (`_refresh_muc_names`). [`tests/test_muc_name.py`]
`ServiceBrowserDialog` groups XEP-0030 items into conferences, gateways,
services, **management** and uncategorized items — an `item` carrying a `node`
attribute (the server's administration nodes: config, users, s2s, …) goes to
the «Управление» section (icon `gtk-preferences.png`, the same as Actions →
Settings), its double click just expands it (the lazy `disco#items` with that
`node` browses nested nodes) and selecting it shows its `disco#info` with the
action buttons (including «Команды»/ad-hoc). A category with no items is
**hidden** entirely (`root.setHidden(root.childCount() == 0)`). It discovers the account domain on open and
builds the tree fully lazily with no eager discovery: a node renders its
direct children "as is" from one `disco#items` request, every service item
shows a tentative expand arrow, and expanding or clicking a node issues its
own `disco#items` before the branch contents are drawn — nodes that return no
children lose their arrow. Deep items inherit the parent's icon (no per-child
`disco#info`); only the top level is classified via `disco#info` to drive the
category grouping. A gateway whose identity `type` is `weather` gets the
`weather-online.png` icon (and `rss` the `rss-online.png` one) via
`_icon_for`. Disco requests (items/info) pass the parent's
`node` attribute so node-scoped services (e.g. gateways) resolve fully, and
items that equal their own parent (`jid`+`node`) are dropped to prevent
self-referencing loops. `Автообзор` recursively pre-loads the tree (bounded
depth, cycle-safe). Used servers are persisted in `connection.service_servers`.
Double-clicking a conference fills both room and server in `JoinConferenceDialog`
and runs the full join flow (server persistence, bookmark support).
`MainWindow._join_muc(..., server=…)` accepts the room localpart and server
separately and assembles `room@server` when the room carries no `@` — both
dialog callers pass `data["server"]`, so a join never sends a bare localpart
or a `remote-server-not-found` disco to the room name alone. The service
in-band registration dialog (`ui/registration_dialog.py`, XEP-0077) wraps its
`DataFormWidget` in an inner container inside the `QScrollArea` so
`fit_dialog_to_content` sizes the window to the form (no scrollbars) — a form
added directly to a widget-resizable scroll area reported the viewport height
and left the dialog clipped.
An XEP-0050 ad-hoc command dialog (`ui/adhoc_dialog.AdhocDialog`) browses a
service's command list, executes one and walks its data form; the command list
carries an «Выполнить» button enabled only while a command is selected
(double-click still works), and the dialog is opened **non-modally** from the
service browser and the roster contact menu. A form step whose server sends no
`<actions/>` (a single-step command) gets a «Отправить» button that submits the
XEP-0050 default action `complete` — without it only Cancel/Close were shown.
[`tests/test_adhoc.py`]
The Actions menu's first item «Создать конференцию»
(`ui/create_conference_dialog.py`, `conference-add.svg`) collects the room
**address** (required, the part before «@», with an info glyph), an optional
**name** and the **server** (required, prefilled with the account's
`discover_conference_service()`), plus the initial room settings — «Постоянная»
/ «Невидимая» / «Для своих» / «Анонимная» (each with an info glyph) and four
presets, each setting only what its scenario **requires**: Публичная
(anonymous on, invisible/members off), Звонки (**only** non-anonymous — Muji
needs the real JIDs, while membership and invisibility stay free), OMEMO
(non-anonymous + members-only, XEP-0384 §5.8; invisibility free) and Частная
(invisible + members-only on, anonymous off).  The room is joined and, only when this join created it
(XEP-0045 status code `201` — read both in `_join_muc_task` **and** in
`_on_groupchat_presence` for the self-presence that arrives first, then passed
through the `muc_joined` event), `MainWindow._apply_created_room_config`
submits `client.muc_creation_values(opts)` via `client.muc_set_config`
(`muc#roomconfig_persistentroom`, `_publicroom` = not «Невидимая»,
`_membersonly` = «Для своих», `_whois` = moderators/anyone per «Анонимная»,
`_roomname` when set). All values are **strings** (`"1"`/`"0"` for booleans):
slixmpp serialises form values with string methods, so an int raised
`'int' object has no attribute 'replace'`; `muc_set_config` also coerces any
non-str value with `str()`. A pre-existing room is left untouched (even for an
owner). The «Название» field carries an info glyph and the server combo fills
the row width. [`tests/test_create_conference.py`] The server-load
button is «Обзор» (`service_browse_action`); next to it an `info.svg` tool
button opens `ui/service_info_dialog.ServiceInfoDialog` for the selected node
(or the combo server): tabs «Информация» (XEP-0092 version, XEP-0039
statistics via `client.get_server_stats`, XEP-0012 uptime via
`client.get_server_uptime`, each gated on the announced feature),
«Возможности» (`describe_features` maps the announced namespaces to
`XEP-XXXX: Name`) and «Контакты» (XEP-0157, `xmpp:` links forwarded through
`ServiceBrowserDialog.xmpp_uri_requested` → `MainWindow._on_xmpp_uri`); one
«Копировать» button copies the active tab. [`tests/test_service_browser.py`]
Chat avatar `<img>` elements carry `class="avatar"`; `ChatView.update_sender_avatar`
updates only `img.avatar`, never emoticon images in the same message.
`HistoryManagerDialog` (opened from the roster contact context menu, the
Actions menu, and the chat toolbar's history button — `ChatWidget.
history_requested` right after the clear button, icon `history.png`) groups
contacts with history by their roster groups or the
`core/known_contacts.py` registry (persisted JID → name/groups/conference flag
so removed contacts keep their names), shows per-day bold dates in a
`QCalendarWidget`, and supports day-scoped, all-time and **all-contacts**
substring search (`core/history.dates/load_day/search_dates`). The «Все
контакты» toggle (`_btn_all_contacts`) searches every JID with a local store
(`history.list_history_jids`) in a worker thread, filters the left tree to the
contacts with matches (`_catalog_filter` → `_rebuild_tree`, whose groups are
expanded **only** in this mode) and lists `contact · date · count` rows; picking
one selects that contact's matched day (not the newest — `_pending_date` is
applied by the contact's date-load) and highlights the match. The results list
has a thin draggable handle under it (`ui/resize_handle.VerticalResizeHandle`,
shared with the chat input) that resizes it (session-only, 40–400 px). An export button
(`document-save.png`, `_on_export`) writes the **whole** conversation with the
selected contact to a `.txt` file in a worker thread (`history.dates` +
`load_day`), one `[YYYY-MM-DD HH:MM:SS] sender: body` line per message (own
messages as «Я»/«Me», newlines collapsed). `_select_jid_async` records the
target JID **before** awaiting the JSONL migration so the stale-selection guard
does not abort the first pick (a regression from moving the SQLite I/O off the
event loop). The dialog is a **reused singleton** (`MainWindow._history_manager`),
so closing it marks it released (`done()`) while `showEvent`/`open_for` revive
it — otherwise every async load would bail on `_released` and the reopened
manager would stay empty until a client restart. Clicking a calendar day that is
not yet among the cached `_dates` re-reads `history.dates_async` first
(`_recheck_date_async`), so a day added to SQLite by a MAM backfill after the
manager opened is highlighted and loads its messages instead of showing the
empty-day notice. `core/history._connection` refuses an empty JID (raises a
`sqlite3.OperationalError`, caught by every handler) and `_path` maps one to a
non-colliding name, so no nameless `<HISTORY_DIR>/.sqlite3` store is ever
created. The roster context menu's
«Очистить историю» and the chat toolbar's clear button both run
`MainWindow._on_clear_history`: after a confirmation it calls `history.clear`
(wipes the SQLite messages **and** the legacy JSONL file) and resets the open
tab; the server archive (MAM) is untouched, so a reopened chat may refill from
it. [`tests/test_history_manager.py`]

**Plugin system** (`stanza_im/plugins/__init__.py`, `ui/plugin_manager_dialog.py`):
plugins are self-contained sub-packages of `stanza_im.plugins`, each exposing a
manifest (`PLUGIN_ID`, `PLUGIN_NAME`/`PLUGIN_CATEGORY`/`PLUGIN_DESCRIPTION` i18n
keys, `PLUGIN_ICON`) and optional `activate(app)`/`deactivate(app)` hooks.
A plugin keeps its own UI strings in `plugins/<id>/strings/<lang>.py`
(`STRINGS = {...}`); `i18n.load()` merges every plugin's string module into the
active dictionary (so the shared `tr()` finds them), the core dictionary wins on
a collision. The category is declared by the plugin, so the manager groups
plugins by the `PLUGIN_CATEGORY` key — several plugins with the same category
share one branch.
A plugin may also define `on_client_ready(app)`: `MainWindow.
_notify_plugins_client_ready` (called at the end of `_on_login`, after the
client exists and its events are wired) runs it for every active plugin — a
plugin enabled before login (when `app._client` is still `None`) can then
subscribe to client events and re-apply its UI state. Because a logout
deactivates every plugin (`_reset_account_ui` → `_deactivate_plugins`), `_on_login`
re-runs `_apply_plugins()` before wiring the client, so a profile switch (or a
plain re-login) brings the plugin tabs/features back without a restart.
The login splash (`MainWindow._set_splash(text, percent)`, a determinate
`QProgressBar`) reports the connection stages: «Подключение…» (10 %) →
«Аутентификация…» (20 %) → «Соединение установлено» (60 %, after
`connect_async` returns) → «Получение списка контактов…» (80 %, on
`session_started`) → «Готово» (100 %, on `roster_received`, which then switches
to the roster page instead of a fixed timer). The initial connect is
**terminal and monotonic** (`_connect_progress_active`/`_conn_progress_value`):
the roster often arrives *before* `_on_session_started` (the client requests it
in `_on_session_start` and awaits the carbons enable before emitting
`session_started`), so the post-session 60 % write in `_connect_async` runs
after the finish — `_set_conn_progress` is a no-op once the connect finished and
never steps the value backwards, so the bar cannot resurrect at 60 %. `_on_login` renders the **cached** roster
before the client is even created: `_show_cached_roster(jid)` reads
`roster_cache.load(jid)` directly, rebuilds the rows, pre-fills the cached
avatar files and switches to the roster page (with a thin `_conn_progress` bar
above the status combo, `_set_conn_progress(5)`), so pressing Connect shows the
roster immediately while the client is constructed and the session is
established in the background; `client.seed_roster_cache()` is still called
afterwards for XEP-0237 versioning, and the splash is kept only for a first
login **without** a cache.
`_connect_async` waits for the session to actually start (a `_session_ready`
future resolved by `_on_session_started`, `_SESSION_TIMEOUT_S` = 30 s) —
`connect_async()` resolves even when every attempt failed (slixmpp reschedules
internally) — and a failure goes to `_on_connect_failed` (offline state on the
roster + the reconnect button, never a false "connected"); the tray stays
offline until a real session.
A plugin that offers settings sets `PLUGIN_HAS_SETTINGS = True` and defines
`open_settings(config, parent)` (opening its own dialog); its settings are
persisted in the shared config under `[plugin_settings.<id>]`
(`plugins.settings_section`, kept apart from the boolean `[plugins].<id>` flag).
`discover()` scans the directory (no external loading) and returns a sorted
`Plugin` list; `enabled_ids`/`set_enabled`/`missing_enabled` read and write the
`plugins` config section (plugin id → bool, `core/storage.py`). The reusable
`PluginManagerWidget` (`ui/plugin_manager_dialog.py`) is a `QTreeWidget` of
categories → plugins with a check per plugin (tri-state per category) plus a
«Настроить» button enabled only for a selected settings-capable plugin; the tree
opens fully expanded (`_build_tree` ends with `expandAll()`, after the children
exist). The
Actions menu's «Плагины» (`exec.png`) wraps it in the singleton
`PluginManagerDialog` with «Ок»/«Отмена»; «Ок» writes the flags and emits
`plugins_changed`, and `MainWindow._apply_plugins` activates/deactivates the
affected plugins **live** (no restart). The Preferences → «Плагины» page embeds
the **same widget** (mirror); the page's `apply_checked()` runs in
`PreferencesDialog._apply_settings`, and its `plugins_applied` signal is wired to
`MainWindow._on_plugins_changed`, which also rebuilds both views so they stay in
sync. If a saved-enabled plugin is missing on disk, `_on_plugins` shows a
`QMessageBox.warning` and the client keeps running. Plugin tabs are appended to the roster tab bar after the
built-ins through `MainWindow._add_roster_tab`/`_remove_roster_tab`, and
`_tab_index`/`_tab_key` resolve positions from the live `_roster_tab_keys` list
(the contiguous built-ins stay `roster`/`bookmarks`/`events`);
`_on_roster_tab_changed` calls a plugin page's `reload()` on activation.
`_deactivate_plugins` tears everything down on logout. [`tests/test_plugins.py`]
The bundled **Notes** plugin (`stanza_im/plugins/notes/`, category «Инструменты»)
adds a tab after the built-ins (icon `draw-brush.png`): a search box, a tag
filter («Все теги» + the collected tags), the note titles and the bookmarks-style
toolbar (Открыть/Создать/Изменить/Удалить, with a delete confirmation). The list
also has a **context menu** (like the bookmarks tab) with Открыть / Изменить /
**Переслать** / Удалить; «Переслать» opens the share window with the note's
`title\n\ntext` (tags excluded) via the plugin's `share` callback →
`MainWindow._on_share_requested`. Notes
live on the server in XEP-0049 private storage using the Miranda payload
(`http://miranda-im.org/storage#notes`): `JabberClient.get_notes`/`set_notes`
build raw IQs (one packet for the whole set) and `_parse_notes` reads
`<note tags><title><text>`. Because `set_notes` **replaces** the whole stored
set, `NotesWidget.add_note` first fetches the server set and merges the new note
into it (a note can be added from the message menu without the Notes tab ever
having been opened), and every notes operation is serialised by an
`asyncio.Lock`; success is reported via the `note_added(bool)` signal. The tab
re-fetches on activation (`on_client_ready` preloads it too); a server without
XEP-0049 shows a warning and an empty list, and an **offline** client skips the
fetch entirely (no 15 s IQ timeout and no traceback — `IqTimeout`/`IqError` are
logged as a one-line debug). The plugin sets
`MainWindow._notes_feature` while active; the message menu's **«В заметки»**
entry (after «Переслать», `chat_view.py`, gated by `window.__stanzaNotesEnabled`
via `ChatWindow.set_notes_enabled`/`ChatWidget.set_notes_enabled`) sends the
message in the same "[date] sender: text" format as Forward to
`MainWindow._on_note_requested`, which calls `NotesWidget.add_note(title, text,
"Сообщения")` with the title `@<room name or nick> <date> <time>` and shows an
OSD notice when notifications are on. That shared format (Copy / «Переслать» /
«В заметки») uses the **local** time: `fmtCopyTime` in `_ACTION_JS` parses the
stored UTC `data-stanza-time` with `new Date(...)` and formats it with the local
getters. For a media message the URL is hidden behind the preview, so the menu
prefers the original media URL (`wrap.querySelector('[data-media-url]')`) over
the visible SIMS label ("name · size"): `content = mediaUrl || body`. The
forwarded text is then the composed `[time] sender: <url>`, which
`MainWindow._resolve_share_media` parses (via `_URL_RE`) to attach the SIMS
metadata. [`tests/test_plugins.py`, `tests/test_ui_tweaks.py`]
The core exposes two generic extension points plugins may use: a contact-menu
hook list (`MainWindow.add_contact_menu_hook`/`remove_contact_menu_hook`, called
as `hook(menu, jid, is_conf)` inside `_on_contact_context`) and a 1:1 toolbar
`ChatWidget.set_attention_support` (driven by `MainWindow.apply_attention_support`
from the `_attention_feature` namespace a plugin installs).
The bundled **Attention** plugin (`stanza_im/plugins/attention/`, category
«Общение», icon `attention.svg` — a yellow bell) implements XEP-0224: its
contact-menu entry «Привлечь внимание» (after «Отправить контакт…») and the 1:1
chat bell (right of the call button) send a bodyless `<attention
xmlns='urn:xmpp:attention:0'/>` (`JabberClient.send_attention`, which delegates
to slixmpp's `xep_0224.request_attention` → `headline` type, so the request is
not stored offline, per XEP-0224 §3). The bell is **hidden**
while the plugin is inactive and shown (but disabled) until the peer counts as
supporting attention — that is, it advertises `urn:xmpp:attention:0` in its
caps (`supports_feature`, driven by `contact_caps` and
`MainWindow.apply_attention_support`) **or** it has ever sent us an attention
request (tracked in `MainWindow._attention_seen`, set by the plugin): Psi+ often
sends `<attention/>` **without announcing the feature in its caps**, so the
"proven by receipt" unlock keeps the bell/menu usable for it. `apply_attention_support`
computes both the plugin-active and peer-support flags. An incoming `<attention/>` arrives through slixmpp's
`xep_0224` plugin as its own **`attention` event** (`JabberClient.
_on_attention_event`, subscribed in `_register_handlers`): the core `message`
event only fires for a stanza with a `<body>`, so a bodyless attention (which
SHOULD use `headline`) never reaches `_on_message`. It is routed (never
rendered as a chat message) to the
`attention_received` event → the plugin plays `resources/sounds/effects/door_bell.wav`,
shows an OSD («Пользователь … пытается привлечь ваше внимание») and pushes an
Events entry. Its `[plugin_settings.attention]` holds `cooldown` (1–99 s,
incoming per-contact throttle), `allow_dnd` (notify while we are in «Не
беспокоить»), `play_sound` and `show_events`. [`tests/test_attention.py`]
The bundled **Digest** plugin (`stanza_im/plugins/digest/`, category
«Уведомления», icon `attention.svg`) keeps a single **sticky** OSD on screen
while there are unread messages from contacts (1:1 and MUC private messages) or
mentions in conferences, or unread Events-tab entries: the title is «У вас новые
непрочитанные сообщения:» and the body lists «N новых сообщений от M контактов»,
«K упоминаний в J конференциях» and/or «Y новых событий». It subscribes to the
`MainWindow.unread_changed` signal (emitted from
`_bump_unread`/`_reset_unread`/`_recount_unread`) and the `events_changed` one
(emitted from `_bump_event_unread`/`_stop_event_blink`), and recomputes
the counters from `_unread_chats` (conference keys — in `_conference_roster`,
`_muc_self_nicks` or the persisted `_known_conferences` set, seeded from
`known_contacts` at startup/profile switch — counted only by `mentions`, so a
room with restored unread is not miscounted as a contact before it is joined)
plus `_event_unread`; the sticky OSD is updated in
place via `OsdManager.show_sticky`/`update_sticky`. It is **gated on being
logged in** (`_refresh` dismisses when `app._client` is `None`), so the unread
counters restored from disk never pop a digest on the login screen (they still
show as roster badges). Closing it (its close button, `on_close`) hides it until
the total grows again; clicking it opens the **Events tab** when there are
unread events (`MainWindow._show_events_tab`), otherwise the topmost unread
conversation (`_on_tray_cycle_unread`). `deactivate` disconnects the signals and
`dismiss_sticky`. [`tests/test_digest.py`]

**Notification priority** (per-contact, `core/notification_priorities.py`): a
contact can be marked «Высокий»/«Обычный»/«Низкий» from the roster contact
context menu («Приоритет уведомлений», between «Подписка» and «Управление
OMEMO») and from a group header menu (applied to every member). The map lives
in the profile (`notification_priorities.json`) and is mirrored to the private
PEP node `urn:xmpp:notification-priority:0` (access `whitelist`;
`JabberClient.get/set_notification_priorities`, like the OMEMO aliases); on
login the server values are merged in (the server wins) and a change publishes
the whole set. The **effective** priority is the user setting (`high`/`low`)
over the XEP-0131 `Urgency` header (`medium` → normal; `JabberClient.
_shim_urgency`). Handling: `low` suppresses only the message OSD (unread /
mentions / digest are unchanged); `high` shows the normal message OSD **and** a
sticky «У вас новые важные сообщения:» OSD (`OsdManager.show_sticky("priority",
…)`, icon `high-priority.svg`) counting the `important` unread messages (a new
field in `core/unread_state.py`, bumped by `_bump_unread(important=True)`);
`normal` keeps the current behaviour. Only **messages** are affected (typing and
status OSDs are not). [`tests/test_notification_priority.py`]

The roster contact context menu also offers **«Выполнить команду»** (right after
«Приоритет уведомлений»): `MainWindow._build_adhoc_menu` lists the contact's
resources (`client.get_contact(bare).resources`), one entry per `bare/resource`
(or a single «пусто» entry targeting the bare JID when the contact has no known
resource). A **server JID** (a transport, no `@`) always targets the bare JID
(its commands live there) and its empty resource — a bare presence gives
`resources[""]` — is filtered out, so a blank entry / a `bare/` (unparseable)
target can never appear; picking one opens `ui/adhoc_dialog.AdhocDialog` for
that target **non-modally** (`_open_adhoc`, kept referenced in `_adhoc_dialogs`
and dropped on `finished`). [`tests/test_adhoc.py`]

A contact can be **dragged onto a group** (header or row): `RosterWidget`
starts a `QDrag` (`application/x-stanza-roster-jid`) and emits
`contact_dropped_on_group(jid, group)`, which `MainWindow.
_on_contact_dropped_on_group` applies through `_set_contact_groups` (moving the
contact to that one group; dropping on «Без группы» clears the groups; virtual
groups are ignored). The target header is highlighted during the drag.

UI convention: context menus and menu-bar menus always use icons. Load them via
`MainWindow._menu_icon(name)`, which resolves through
`include.constants.find_icon` (scalable dirs first, then the sized dirs);
`SearchDialog._icon` mirrors it.

**Non-modal dialogs**: a blocking (`exec()`/`open()`) dialog prevents copying
data from another window (e.g. a room name from a chat) into it, so every
dialog that holds editable fields or copyable data is shown modeless via
`ui/dialogs.py::show_modeless(dialog, on_finished)` — the accept/reject logic
moves into the `finished` slot and the dialog stays alive through its parent.
Only pure confirmations, checkbox-only selectors (`ShareDialog`,
`RosterExchangeDialog`), immediate prompts (`IncomingFileDialog`,
`IncomingCallDialog`, `CaptchaDialog`) and pickers stay modal.

**JID inputs** use `ui/jid_edit.py`: a `JidLineEdit` normalises what is pasted
right away (`xmpp:` scheme, URI query and, unless `resource=True`, the resource
are dropped; the domain is lower-cased) and its `jid()` normalises typed text,
so a JID copied from a vCard or a chat fits any form.  `QLineEdit` has no
`insertFromMimeData` virtual, so the field hooks the paste shortcut
(`keyPressEvent`) and drops itself, and normalises right after a context-menu
paste (that action is wired to `QLineEdit::paste()` in C++ and cannot be
replaced). The bare-JID forms are the add
contact dialog (and its vCard/nick lookup), the MUC participant editor, the
login form, the existing-account dialog and, via `normalize_jid`, the blocked
list and the hats manual list; privacy rules keep the resource. Room forms
(`create_conference_dialog`, `JoinConferenceDialog`, `BookmarkDialog`) use a
`RoomJidEdit`: pasting `room@conf[/nick]` leaves `room` in the field and emits
the server, which fills the separate server widget (a full JID typed or pasted
later also wins in `collect()` — otherwise the bookmark used to double the
domain).

The shared rich-text tooltip (`ui/tooltip.py`) is a frameless popup used by the
roster and the MUC participant list; its avatar is scaled to
`notifications`-independent `appearance.tooltip_avatar_size`
(`tooltip.set_avatar_size`, Preferences → Appearance → «Разное», 32–256 px,
default 64). Its text font follows `appearance.tooltip_font`/`tooltip_font_size`
(`tooltip.set_font`, Preferences → Appearance → «Шрифты»); the same setting also
reaches the native Qt tooltips through a `QToolTip { … }` rule in
`MainWindow._apply_widget_fonts`. `tooltip.show(..., wrap=True, max_width=…)`
wraps long content (the MUC subject: 700 px, newlines become `<br>`), and
`_place` pins the popup to the screen width so even an unwrapped long line
cannot run off the screen. The MUC participant tooltip names the occupant's client the way the
roster does: the XEP-0092 `client` if known, otherwise the XEP-0115 caps mapping
(`clients.find_client(caps_node)`), with the caps icon before the nick.

## Key Design Patterns

### 1. Asyncio + Qt Integration (`app.py`)

The app uses `qasync.QEventLoop(app)` as the asyncio loop. slixmpp runs
as asyncio tasks within this shared loop; no busy polling, ~0% idle CPU.
No Twisted dependency.

```python
loop = qasync.QEventLoop(app)      # replaces QTimer-polling bridge
asyncio.set_event_loop(loop)
loop.run_forever()
```

### 2. XDG Persistence (`core/storage.py`)

Everything follows the XDG Base Directory spec:

| Path | Location |
|------|----------|
| Config (TOML) | `$XDG_CONFIG_HOME/stanza-im/config.toml` (0600) |
| Profiles (JSON) | `$XDG_CONFIG_HOME/stanza-im/profiles.json` (0600) |
| Chat history (JSONL) | `$XDG_DATA_HOME/stanza-im/<jid>/history/<bare-jid>.jsonl` (0600) |
| Unread counters (JSON) | `$XDG_DATA_HOME/stanza-im/<jid>/unread.json` (0600) |
| OMEMO keys (JSON) | `$XDG_DATA_HOME/stanza-im/<jid>/omemo.json` (0600) |
| Notification priorities (JSON) | `$XDG_DATA_HOME/stanza-im/<jid>/notification_priorities.json` (0600) |
| Classified transports (JSON) | `$XDG_DATA_HOME/stanza-im/<jid>/transports.json` (0600) |

`Config` has nested-table helpers, so `config.ui.auto_connect = True` works.
The minimal TOML writer (`Config._write_toml`) serialises scalars with
`json.dumps(..., ensure_ascii=False)`: the file is UTF-8, so non-BMP characters
(emoji in `emoji.recent`) are stored literally — `ensure_ascii=True` would emit
single-surrogate escapes (`\ud83d`) that TOML parsers reject.
Passwords are stored plaintext per user request (file is 0600). History is
appended line-by-line as JSON, keyed by bare JID, one file per contact.

**Per-profile data.** Every account (Jabber ID) keeps its own state under
`$XDG_DATA_HOME/stanza-im/<jid>/`: `history/`, `roster/<account>.json`,
`unread.json`, `known_contacts.json`, `notification_priorities.json` and
`transports.json`
(`core/profiles.py` `set_active`).
`include/constants.set_active_profile` selects the subdirectory; each store
(`history`, `roster_cache`, `unread_state`, `known_contacts`,
`notification_priorities`, `transports`) exposes
`set_profile(jid)` that re-bases its module-level path and the pooled history
connections are closed, so a contact's history from one account is never served
to another (the pool is keyed by the *contact* JID). With no profile selected
(tests, before the first login) the unscoped `DATA_DIR` layout is used. The
`CACHE_DIR` stores (avatars, media, tiles, discovery, vCard cache) stay shared
across profiles.

**Application profiles** (`core/profiles.py` + `ui/profiles_dialog.py`): a
profile is one account — its name is the Jabber ID. The registry
(`profiles.json`) stores each account's credentials and connection settings
(`Profile`: jid, password, save_password, override_host, host, port,
tls_mode, starttls_mode, proxy_mode/host/port); the active account's values
also live in `config.toml`. The Actions menu's «Профили»
(`ui/profiles_dialog.ProfilesDialog`) lists the profiles (the active one in
bold) with «Создать»/«Применить»/«Удалить» and a «Закрыть» button. «Создать»
asks how (`ui/profile_source_dialog.ProfileSourceDialog`): «У меня уже есть
учетная запись» opens `ui/existing_account_dialog.ExistingAccountDialog`
(JID, password, optional host/port, encryption, proxy) and «Зарегистрировать
новую» reuses `AccountRegistrationDialog` opened with `store_account=False`
(it only returns the `Profile` via `result_profile()` and leaves the active
config untouched); either way the profile is only **added** to the list.
«Применить» emits `activated(jid)`; `MainWindow._activate_profile` writes the
profile to the config (`profiles.apply_to_config`), selects its data directory
(`profiles.set_active`), reloads the unread counters and, while a session is
open, asks for confirmation (`profiles_activate_question`) before logging out
and signing in to the new account — a profile with no stored password only
fills the login form. «Удалить» asks whether to delete the profile's data
(`profiles.delete_data` removes `<DATA_DIR>/<jid>`) or only the list entry.
The login form has a «Выбрать профиль» group: a profile selector, an `ok.png`
apply button (`LoginWidget._apply_profile`) that loads a profile into the config
and the form, and a `system-users.png` button (`profiles_requested` →
`MainWindow._on_profiles`) that opens the same manager dialog; the status
selector sits at the bottom and the Connect button keeps the focus. A manually
typed account is upserted into the registry on login (its password only when
«Сохранить пароль» is on). [`tests/test_profiles.py`]

### 3. Custom-Painted Roster (`roster_widget.py` + `roster_style.py`)

A plain `QWidget` renders all contacts via `paintEvent()` + `QPainter`. No
QTreeView or QListView — zero child widgets. This is extremely memory-efficient
and allows full visual control (avatars, status icons, unread badges, mood icons).

**Data model**: `GroupItem` and `UserItem` dataclasses. The widget maintains
flat lists and sorted dicts. Hit-testing iterates items by accumulated Y offset.
Groups sort case-folded, except the trailing groups (`set_trailing_groups`,
used by `MainWindow` for the conferences group **and** the private-messages
group) which always come last, and the leading groups (`set_leading_groups`,
used for the self-contact group) which always come first. Three groups hold an
app-computed row rather than a real contact group — conferences
(`MainWindow._sync_conference_roster`, one row per joined room), MUC private
messages **and** the account's own contact (`MainWindow._sync_self_roster`) — so
they are excluded from the group pickers and roster sharing via
`_virtual_roster_groups()` and are never persisted into
`core/known_contacts.py`. The server often returns the account itself in the
roster; `_add_roster_item` **always** skips the own JID (`client.jid_str`), so it
never becomes an ordinary contact. `_sync_self_roster` shows it on demand as a
single virtual row in the leading «Свой контакт» group
(`roster_group_self`) — only when `appearance.roster_show_self` is on (View
menu «Показывать свой контакт», default off) — with the account's name/JID;
clicking it opens a self-chat (notes to self via MAM). A **MUC private message
is always keyed by `room/nick`** (the occupant identity, whether or not the room
reveals real JIDs; the real JID is metadata for the status, avatar and vCard,
and a room PM the server relays from the real JID is mapped back by
`JabberClient._room_pm_occupant` when the MUC `<x/>` marks it). A normal 1:1
chat with the same user (bare JID) stays a separate conversation.
`MainWindow._sync_pm_roster(target, room, nick)` gives the conversation its own
row in the «Личные сообщения» group (`roster_group_personal_messages`), which
is exactly where its unread counter lives. The row appears only once a message
was actually **exchanged**: an incoming PM (`_on_muc_private_message`) or the
first outgoing one (`_note_pm_message` from `_on_message_send`) creates it,
while merely opening a participant's chat registers the target in
`_pm_targets` (no row). The row can be removed again from its context menu
(`_remove_pm_row`, session-only: the tab and history stay). `_apply_pm_presence`
pushes the participant's status/avatar into the tab (`ChatWidget.set_peer_avatar`),
switches it to the occupant feature set (`set_pm_mode`: no calls, whiteboard,
attention bell, OMEMO or P2P files — HTTP Upload, text, reactions, reply and
the participant vCard stay), and the toolbar vCard routes through
`_show_muc_participant_profile` (bare real JID or `room/nick`);
`_on_groupchat_presence` keeps it in step with presence — an occupant who
**leaves the room stays in the group shown offline** (the row lives for the
whole session and is only cleared on logout by `_reset_account_ui`); a full
roster refresh restores it through `_sync_all_pm_roster` (only the rows in
`_pm_roster`; called from `_on_roster_received` after `_rebuild_roster`, which
clears the widget). The PM context menu (`_build_pm_menu`) carries only the
occupant-safe actions: open chat, vCard, history, send file (HTTP Upload),
add to contacts (real JID known and not yet a contact), invite to a conference
and send contact (real JID known), mark read, clear history and remove the
row. The group shows the usual
online/total count through `_recount_groups`. The badge label is
`RosterStyle.badge_text`: `N`, or
`N / M` when the conversation has `M` unread messages naming our own nickname.
Contacts sort alphabetically inside a group by default; `set_sort_by_status`
(the View menu's «Сортировать по статусу», default on) instead ranks them by
presence — chat («free for chat») → online → away → xa → dnd → offline — with
the name as the tie-break. `set_sort_by_unread` (View menu's «Сортировать по
непрочитанным», default on) makes contacts with unread messages lead the list
(`RosterWidget._sort_key` puts `0 if unread_count else 1` first), then the
presence/name order applies inside each part. `set_show_groups` (View menu's
«Показывать группы», default on) draws the real contacts as one flat list
(one row per JID, sorted by the active options) when turned off, while the
virtual groups — conferences and private messages (`_trailing_groups`) and the
self-contact (`_leading_groups`) — keep their header. The flags live in
`appearance.roster_sort_by_status`/`roster_sort_by_unread`/`roster_show_groups`/
`roster_show_offline`/`roster_show_self` and are applied/toggled from the View
menu.

**Rendering strategy**: `RosterStyle` is a pluggable class. `set_style()` hot-swaps
the renderer. Heights are dynamic: contacts with status messages are taller.

**Mood/activity icons**: a roster row can carry the contact's PEP mood (XEP-0107)
and activity (XEP-0108) icons, drawn at 16px between the name and the unread
badge/avatar from the same icon set as the bottom-bar mood/activity picker
(`pep.mood_icon_path`/`pep.activity_icon_path`). `UserItem.mood`/`activity` are
seeded by `MainWindow._add_roster_item` from `client.pep_data` and kept live by
`MainWindow._on_contact_pep_updated`. Each element (avatar/activity/mood/client)
is togglable from Preferences → Appearance → «Ростер» via
`appearance.roster_show_avatars`/`roster_show_activity`/`roster_show_mood`/
`roster_show_clients` (default all `true`): `MainWindow._apply_roster_options` →
`RosterStyle.set_options` gates rendering live, no relayout.

**Client icon (XEP-0115)**: each presence's `<c node=…/>` is captured by
`_on_presence` (`_caps_node`) into `contact.resources[res]["caps_node"]`
(a MUC occupant presence is skipped there — it would otherwise give the room a
participant's icon; the room's **own** presence, `from="room@conf"` with no
resource and no `muc#user`, is skipped too via `_known_rooms` so a room never
becomes a roster/contact pseudo-entry or gets PEP subscriptions);
`JabberClient.client_icon(bare)` picks the best resource
with a known node and maps it through `include/clients.py` (`find_client`,
longest caps prefix; `icon_path`, size fallback) to an icon under
`resources/clients/<size>/`. `UserItem.client_icon` is drawn by
`RosterStyle.paint_user` right after the avatar (16px, before the unread
badge/mood/activity) and refreshed on `presence_changed`/`contact_caps`.
`_prefetch_version` (XEP-0092) additionally caches the resource's
`client_version` and `client_os` and, from XEP-0202, its `client_tzo` offset
(all preserved across presence updates like `client`), which the tooltip turns
into the contact's live local time; its `asyncio.wait_for` uses a generous
`_ENTITY_TIMEOUT` (30 s — a slow server can take >10 s) and it emits
`contact_client_updated(bare)` so an open vCard re-renders as each answer
arrives. `JabberClient.probe_resource_versions(bare)` re-runs it for every
resource (the vCard "Refresh" bypasses the once-per-session `_version_probed`).
A lookup that resolves nothing (no software and no tzo) drops its JID from
`_version_probed` so a later presence retries, and makes up to two attempts
itself; `JabberClient.ensure_contact_version(bare)` re-requests the resources
still missing client/time when a roster tooltip is built for them, so the data
appears without opening the vCard even for a peer that never re-sends its
presence. Concurrent lookups per JID are deduped by `_version_inflight`.
`JabberClient.best_full_jid(bare)` returns the full
JID of the best **online** resource; `probe_entity` probes **it** for the
software version, local time and ping (not the bare JID, which the server
answers) and skips the request entirely for an offline contact. The
contact tooltip is a per-resource **tree**: after the name/JID/subscription the
extended-presence lines (mood/activity/now playing/location, each prefixed with
`pep.mood_icon_path`/`pep.activity_icon_path`/`pep.tune_icon_path`) come first,
then all resources rendered by the shared
`ui/resource_tree.py::resource_tree_html` as **one** `<table>` (no blank line
between resources) whose first column holds the status icon
(`status_icon_html`, i.e. `jabber-<show>.png`) before the bold resource name, so
the following lines align under the name's first letter: the `clock.svg` icon
and the resource's live local time (`local_time_from_tzo`, XEP-0202 `client_tzo`)
on their **own** row, then the client line (`<img client-icon> Клиент: name
version / OS`) and «Статус: message» (`tooltip_status`).
The MUC participant sidebar shows the same client icon before the avatar
(`ChatWidget._build_muc_user_row`/`_apply_muc_user_row`,
`set_muc_participant_options`) and its tooltip before the nick; a presence
**merges** into the sidebar (`_sync_muc_users`/`_sync_muc_order`): only the
changed participant's row is created/updated/removed, rows move between the
moderator/participant/guest sections in place and the section counters
(`… (N)`) are refreshed, so a large-room join no longer recreates every row
per presence; roster and participant avatars are clipped by
`include.avatars.rounded_avatar` with `appearance.avatar_radius` (0 = square,
100 = circle; `RosterStyle.set_avatar_radius`/`ChatWidget.set_avatar_radius`,
applied live via `MainWindow._apply_avatar_radius`). A participant's vCard is
resolved **cache-first**: `MainWindow._on_groupchat_presence` only calls
`client.queue_participant_vcard(room, nick)` (never one vCard IQ per presence),
which applies a cached card at once (participant TTL 24 h) or appends the nick
to a single rate-limited background worker (2 requests/s, skipping occupants
who left); `_seed_muc_chat` uses the same queue for the join-time occupant list
(never one vCard IQ per occupant); a cached avatar **file** for `room/nick` is used immediately
(`_muc_cached_avatar`) so a returning nick shows its avatar without a request.
A card that finally arrives updates **only that participant's row** and its
messages (`ChatWidget.refresh_participant`; the message avatars are repainted
with `refresh_avatar_for_sender(..., force=True)`, since the avatar file keeps
its path and the sender JID does not change) — the roster and the other rows
are not touched (no `clear_pixmaps`, no full-list avatar reload). A cached
participant card is re-validated **once per session** when the presence's
XEP-0153 photo hash differs from the cached card's `photo_hash` (a nick can be
reused by another person), showing the cached avatar meanwhile.
The conference toggles are
`appearance.muc_show_avatars`/`muc_show_clients`/`muc_show_hats` (Preferences →
Appearance → «Конференции», all `true`; a participant's caps node is captured in
`_on_groupchat_presence`). `muc_show_hats` gates the XEP-0317 hat chips under
messages (`ChatWidget._user_hats` returns none when off, `set_muc_hats_visible`
re-renders) while the participant tooltip keeps listing the hats.
The sidebar never scrolls horizontally: the list
uses `QListView.ResizeMode.Adjust` + `ScrollBarAlwaysOff` and the nick is a
`_FadeLabel` that clips the text and fades its right edge into the background
(Psi+ style), so the status icon, client icon and avatar always stay visible.
A live search field above the list (`ChatWidget._participant_search`,
`set_participant_filter`) filters the rows by nick (NFKC + case-fold, so case
and width variants match), hides a section whose occupants all miss and shows
its count as `matched/total` (the plain count without a filter); a presence
arriving while the filter is active is filtered too, and a 1:1 tab shows no
search field.
Its width is remembered in `appearance.muc_participant_width`
(`ChatWidget.participant_width_changed` → `ChatWindow.set_muc_participant_width`)
and restored for new MUC tabs. The data file
`resources/clients/clients.txt` (`caps⇥name⇥icon`, both http/https variants)
is generated from the bundled `index.html` by
`resources/clients/build_clients.py`. [`tests/test_clients.py`]

### 4. Chat Rendering via QWebEngineView (`chat_view.py`)

Messages are rendered as HTML/CSS using Adium-compatible chat skins from
`resources/chatskins/`. A `QWebChannel` bridge (`_ChatBridge`) exposes Python
methods to JavaScript for link clicks, file transfer buttons, etc.
`chat_view.py` defines **two** `ChatView` classes: the WebEngine one and a
plain `QTextBrowser` fallback (used when QtWebEngine is missing **or** disabled
via `performance.webengine_mode = off`). The fallback must mirror the
WebEngine class's public API — `ChatWidget` calls the same methods on both
(`add_message` with the full kwarg set incl. `reactions`/`markup`,
`update_reactions`, `shutdown`, `set_media_thumbnail`, `prepend_messages`, …);
`tests/test_fallback_view.py` guards this parity (it forces the web engine off
before importing the module). The fallback keeps **undo/redo disabled** and
trims its `QTextDocument` to `_MAX_BLOCKS` (500) oldest blocks on append
(mirroring the WebEngine `_MAX_DOM_MESSAGES` DOM trim; older-history
`prepend_messages` is bounded by `_HISTORY_MAX` and not trimmed) — without this
a long-lived fallback tab grows without bound. Its `prepend_messages` inserts
**each message as its own block** (they used to run together on one line) and
restores the scroll position on the next event-loop turn (never a synchronous
`processEvents()`, which re-entered the loop from inside a coroutine). The
bottom report (`_note_bottom`) and the **near-top report** (`_check_scroll` →
`near_top`) are both **suspended** during programmatic scrolls (render, anchor
restore, prepend) exactly like the WebEngine view — otherwise a transient
bottom would mark the conversation read / drop the unread separator, and a MAM
prepend would re-trigger the next page forever.

**Theme engine** (`chat_themes.py`): Loads HTML templates and CSS variants from
`resources/chatskins/minimal-mod/` or `candy/`. Templates use `%sender%`,
`%message%`, `%time%`, `%userIconPath%`, `%senderColor%` placeholders.

**Message Styling** (`xmpp/message_styling.py`, XEP-0393): `render(body, fragment)`
parses `*em*`/`_em_`/`~strike~`/`` `code` ``/pre/quote markup and calls `fragment`
only for plain spans (escape + URLs + emoticons; never inside `<code>`/`<pre>`).
`ChatThemeFactory.set_message_styling()` toggles it; `unstyled` messages and the
preferences switch both fall back to the plain pipeline. Feature advertised as
`urn:xmpp:styling:0`.

**Message Markup** (`xmpp/message_markup.py`, XEP-0394): when a message carries
`<markup xmlns='urn:xmpp:markup:0'/>`, `parse_message(msg)` reads its
`<span>` (emphasis/strong/code/deleted), `<bcode>`, `<list>`/`<li>` and
`<bquote>` ranges (unicode code points over the body) and `render(body, markup,
fragment)` applies them, delegating plain regions to the fragment hook; the
body stays the source of truth and the structured markup takes precedence over
XEP-0393. Leading quote/list markers (`>`/`*`) are stripped one level per
nesting. `client.message_markup` parses it on receive and it is stored in the
history `markup` column and threaded like `media` (1:1/MUC/carbon/corrections/
MAM). Toggled by the same «Format message text» preference.

**Message Replies** (XEP-0461): the per-message reply trigger is an anchor
(`<a href="stanza:reply:%REPLY_TARGET%">`) whose target is filled in by
`ChatView._mark_message` from `_compose_reply_target(reply_id, author, sender,
body)` (each field percent-encoded, joined with `/`). Clicking it never
navigates: the `_ACTION_JS` document-level click handler preventDefaults the
anchor and stores its `href` in `window.__stanzaReplyRef`, and the
always-running scroll poll delivers that `stanza:reply:` reference to Python as
a `link_clicked` — exactly like the `window.__stanzaEditRef` edit relay — so
the chat document cannot be reset by the click. Pressing `Up` in the input
while it is empty starts a reply to the newest incoming message
(`ChatWidget._reply_to_last` walks `_newest_first()`, skips our own entries and
those without a replyable id, then runs the same `_on_reply_requested` flow as
the reply button; Ctrl+Up stays the XEP-0308 edit shortcut). Pressing `Down`
while the reply is still untouched (the input holds exactly the inserted quote)
cancels it again.
[`tests/test_reply_up.py`]

**Control links — mandatory rule**: *every* `stanza:` control link the chat
renders (message-menu buttons **and** links placed elsewhere: status lines,
`show_voice_prompt`, error hints) MUST be relayed in-page, never navigated:
an `a[href^="stanza:…"]` branch in the `_ACTION_JS` document-level handler calls
`e.preventDefault()` and stores the href in a `window.__stanza<Name>Ref`
variable; the always-running scroll poll appends that variable to its result
array **at the end** (indices are positional — never renumber the earlier
entries); `_on_scroll_position` reads it, guards the repeat with
`self._last_<name>_ref`, and emits `link_clicked`; and a matching
`_clear_<name>_request()` helper resets the variable. `ChatWidget._open_link`
then routes the scheme. A missing branch means Chromium navigates, the request
is denied by `_StanzaPage.acceptNavigationRequest`, and the resulting
`loadFinished(false)` makes `_probe_chat_alive` reload the document — the user
sees the whole conversation disappear. `tests/test_ui_tweaks.py` enforces this
statically: any `window.__stanza*Ref` assigned in `_ACTION_JS` must appear in
the poll and have a `_clear_*_request` helper.
Real links still request a navigation that is intercepted on the
C++ side by `_StanzaPage.acceptNavigationRequest` → `ChatView._accept_navigation`,
which emits `link_clicked` for the `stanza`/`mam`/`http`/`https`/`mailto`
schemes and denies the in-view load. The "local history was cleared — load it
from server" marker is a `stanza:load:` control link (`a.stanza-load`, the same
`preventDefault` + scroll-poll relay as reply/edit/mention), so it reloads the
server history without relying on a `mam:` navigation. The `stanza`/`mam` schemes are
pre-registered as app-handled with `QWebEngineUrlScheme.registerScheme`
(`_register_custom_url_schemes`) so Chromium never starts (and errors on) a
real load; they use the `Path` syntax, which preserves the opaque
`stanza:view:…`/`xmpp:…` forms verbatim so `linkUrl()` still reports them to
the media context menu. A denied navigation is thus harmless, and a stray
`loadFinished(false)` from a blocked link is self-healed by
`_on_load_finished`/`_probe_chat_alive`, which verifies that
`#chat` survived and un-wedges the pending-message buffer; if the document was
truly wiped it reloads the empty page and emits `document_lost`, which makes
`ChatWidget._restore_after_document_lost` re-render the whole conversation
instead of leaving a blank chat. `refresh_avatars`
updates avatar `<img>` elements in place instead of clearing the whole
document, so avatar caching can never stall live rendering.
No QWebChannel call, console mirror or WebChannel-dependent JS is involved for
control clicks, so they reach Python even when the WebChannel transport is
unavailable. The `qwebchannel.js` glue (Qt `:/qtwebchannel` resource, falling
back to `resources/qwebchannel.js`) is kept only for scroll/jump reporting.
Clicking reply inserts the referenced message into the input as an XEP-0421
quote block (`> Sender wrote:\n> text`) with the cursor below it; a banner
remains as an indicator and `×` cancels (removing the inserted quote).
`client._attach_reply` attaches `<reply xmlns='urn:xmpp:reply:0' to='…' id='…'/>`
as the first child of `<message>` for messages with a resolvable reference; the
quote is already in the body, so no automatic fallback is prepended. Replyable
ids come from `origin-id`/`id` (1:1) and the server `stanza-id` (MUC, by the
room's bare JID), falling back to `archive_id` then `message_id`
(`ChatWidget._reply_target_id`); a message with no resolvable reference still
gets the quote and is sent as a plain message. Received replies are parsed in
`client._on_message`/`_on_groupchat_message`, stored in history
(`origin_id`/`reply_to`/`reply_id`, see `core/history.py`) and rendered with the
`.stanza-reply` quote bar (body quotes stripped) via `chat_themes.render_reply()`.
The bar is clickable when the referenced message resolves locally
(`render_reply(sender, snippet, target_id)` → a `stanza:jump:` anchor): the page
scrolls to the `data-stanza-id` node and briefly highlights it; if the node is
not rendered, `ChatWidget._jump_to_message` walks the **local** SQLite archive
(never MAM, gated by `history.message_exists`) page by page, renders the loaded
pages and scrolls. Those pages are inserted with
`View.prepend_messages(keep_position=False)` so the reading-anchor restore cannot
revert the jump, and the target node is matched by `data-reply-id` or
`data-stanza-id`. Feature advertised as `urn:xmpp:reply:0`.

**Jump-to-bottom button** (`_JumpButtonMixin`, `chat_view.py`): the floating
`▼` button (WebEngine renders it as the in-page `#stanza-jump` div, the
QTextBrowser fallback as a `QToolButton`) shows how many messages arrived while
the view was scrolled up. `ChatWidget.add_message` counts incoming, non-own
messages while `ChatView.is_scrolled_up()` (`note_new_message`), showing
`▼ N` (capped `99+`). The first click jumps to the first such message
(`scroll_to_message(..., highlight=False)`), the second click (or reaching the
bottom) scrolls to the end and clears the counter, which lives until the actual
bottom. Incoming messages no longer force a scroll to the bottom (only the
user's own outgoing messages do); the HTML button's click sets
`window.__stanzaJumpPress` and is relayed through the scroll poll, with the
QWebChannel `bridge.on_jump_clicked` only as an optional fast path (the poll is
the fallback when the transport is unavailable). The 250 ms scroll poll runs
**only while the view is on screen** (`hideEvent` stops it, `showEvent` starts
it, and a load starts it only when visible) **and while the application is
active** (`poll_allowed(QApplication.applicationState())`: an inactive app
skips the `runJavaScript`, so a background window does not churn IPC/JS), so
background tabs are never polled; the last-seen query is skipped while the view
sits at the bottom. The
`▼` shares a centred
bottom row (`#stanza-fabs` / `_position_fab_buttons`) with the mention `@`
button (left) and the reaction `♥` button (right, see below); all three labels
are replayed after every page load (`_on_load_finished` calls
`_update_jump_label`/`_update_mention_label`/`_update_reaction_label`) so a
count seeded before the document existed still shows.
[`tests/test_jump_button.py`]

**Unread mentions & the `@` button**: an unread conference message naming our
nick is also handed to the tab (`MainWindow._note_unread_mention` →
`ChatWidget.note_unread_mention`, keyed by the reply target id). A **floating
`@ N` button left of `▼ N`** (same row/style; the WebEngine backend uses the
in-page `#stanza-mention` div, the QTextBrowser fallback a `QToolButton`; the
click is relayed by the scroll poll as `window.__stanzaMentionPress` →
`mention_jump_requested`) shows the **same mention counter the roster badge
does**: `MainWindow._push_unread_to_chat` mirrors `_unread_chats[jid]["mentions"]`
onto it (`ChatWidget.set_mention_count` → `ChatView.set_mention_count`) and the
counter ticks down as mentions are scrolled into view — `_on_chat_last_seen`
subtracts `ChatWidget.count_mentions_since(prev_seen, ts)` alongside the unread
count. The local `_mention_refs` list is only the first-click target: each click
jumps to the oldest mention not yet looked at (`_jump_to_next_mention`:
`scroll_to_message` when it is rendered, else `_jump_to_message` paging the
local archive) and `_drop_seen_mentions` removes the ones already shown;
`_on_chat_reached_bottom` (reaching the newest message, see the unread
paragraph below) calls `mark_mentions_read`, which clears the rest. The list is
**rebuilt from the window** on open (`refresh_unread_mentions`: every mention of
the loaded history after the read anchor is re-armed) and again after a deferred
archive resolve (`_finish_unread_resolve`); a room joined with unread messages
loads its history with the read anchor (`MainWindow._on_muc_joined`), so the `@`
target list and the separator are present on open.

**Reactions on our own messages (the `♥` button)**: a third floating button
right of `▼ N` (the WebEngine backend's in-page `#stanza-reaction` div, order
`2` in `#stanza-fabs`; the QTextBrowser fallback a `QToolButton`; the click is
relayed by the scroll poll as `window.__stanzaReactionPress`, index 24, with the
QWebChannel `on_reaction_clicked` as an optional fast path) counts the
**reactions other participants put on our own messages**. It is session-only and
never persisted: `MainWindow._reaction_pending` maps each chat-tab key to an
ordered `{message-ref: count}`. Every XEP-0444 update goes through
`_store_reactions`, which reads the reactor's previous emoji set
(`_reactor_set`) and applies the size delta (`_note_reaction_delta`): a reactor
who adds 5 reactions adds 5, one who takes 2 back subtracts 2, clamped at 0.
Only reactions on a message we sent (`_is_own_message`, via
`history.entry_by_ref`, which matches `archive_id`/`origin_id`/`message_id`) and
never our own reactions (`_reaction_is_mine`) count. The total is pushed to the
tab (`ChatWindow.set_reaction_pending` → `ChatWidget.set_reaction_pending` →
`ChatView.set_reaction_count`, mirrored on open by `_focus_chat`), shown as
`♥ N` (capped `99+`, hidden at 0). A click jumps to the first message with
pending reactions (`ChatWidget._jump_to_next_reaction`: `scroll_to_message` when
rendered, else `_jump_to_message`) and clears **that message's** count in one
batch (`reaction_seen` → `MainWindow._on_reaction_seen`); the button stays while
other messages still have pending reactions. It only ever decreases by clicking
it, not by reaching the bottom. [`tests/test_reaction_button.py`]

**MUC mentions & Tab completion**: in groupchats the incoming sender name is
rendered as a clickable `stanza:mention:` link (`render_message(mention=...)`,
enabled via `ChatView.mention_senders`); clicking it inserts `nick: ` into the
input with focus (`ChatWidget._handle_mention_uri`). Like reply/edit, the
mention is a plain anchor whose click is preventDefaulted by the `_ACTION_JS`
document handler and relayed through `window.__stanzaMentionRef` by the
always-running scroll poll (never a navigation), so a nick click can never
reset the chat document. `Tab`/`Shift+Tab`
in a MUC input
completes the nick before the cursor and cycles the candidate list on repeat
presses: a nick starting the line is inserted as an address (`nick: `),
mid-line only the bare nick is completed; the previous token is replaced so the
cycle wraps correctly (`ChatWidget._tab_complete_nick`). The MUC participant
sidebar (`ChatWidget._users_list`, a `_ParticipantList` subclass) opens the
private chat on a double-click of a participant row (`participant_clicked`;
single click only selects), a left click on empty list space clears the
selection (`_ParticipantList.mousePressEvent`), and the right-click participant
context menu offers «Пригласить в» (XEP-0249) when the participant's real JID is
visible. `Esc` in the chat
window collapses a conference back to the roster without leaving the room (the
tab is removed, the room stays joined, other tabs keep the window open); on a
1:1 tab Esc closes it. `Ctrl+W` leaves a conference (with the optional confirm,
`MainWindow._confirm_muc_leave`, shown over the chat window via
`_chat_dialog_parent`) and closes a 1:1 tab.

**OSD notifications** (`ui/osd.py`): `OsdManager` owns a stack of translucent
frameless always-on-top windows (flags include `X11BypassWindowManagerHint`,
children are mouse-transparent so drags/clicks reach the window) docked to a
saved base position (`notifications.osd_x/osd_y`). A draggable preview from the
preferences OSD page
moves the base (written to the shared `Config` live, persisted on Save); the
drag grabs the mouse and moves the window manually on X11 (reliable even on
window managers that ignore `_NET_WM_MOVERESIZE`, e.g. Trinity) and uses
`QWindow.startSystemMove()` on Wayland, and the settings
dialog is opened non-modally so the preview keeps receiving input. Stacking
is top-down or bottom-up per `osd_topdown`, capped by `osd_max` (oldest evicted),
auto-hiding after `osd_duration`, and its width is `osd_width` px (160–600,
Preferences → Notifications → OSD; `OsdManager.apply_width` resizes live
windows); a pure `stack_position()` keeps the math
unit-testable. In bottom-up mode `osd_y` is the **bottom line**: every
notification is anchored by its bottom edge (via `stack_position` subtracting
its own height) so a tall one grows upward instead of overlapping the one below
or overflowing the screen; the draggable preview stores its bottom
(`_preview_moved`). Hovering **any** OSD pauses the auto-hide timer of the whole
stack (and resumes it once the cursor leaves all of them), so a notification the
user is reading — and the ones around it — never vanish under the cursor.
MainWindow triggers gate on `notifications.osd_enabled` and the
per-event toggles: `osd_message` (1:1 + private, only while the chat window is
not the active window on that conversation), `osd_typing`, `osd_status`
(`never`/`available`/`any`; the first presence per JID is skipped and the whole
initial replay stays silent — `_presence_osd_grace_until` starts at
login/`stream_resumed` and every **newly-seen** contact pushes it out by
`_PRESENCE_OSD_TAIL_S` (2 s), so a slow or large roster never bursts into "X
came online" OSDs, and `_osd_status_seen` is cleared on each session
start/resume), `osd_conference` (`never`/`mention`/`all`), plus the
`_notify_osd_file` entry point wired for future p2p file transfers. The close
button (`#osd-close`) is 24×24; because the frame and its children are
mouse-transparent, a press that lands on its rectangle is routed to `_close()`
in `_OsdWindow.mousePressEvent` (never to the notification's `_click()`), so
the corner always dismisses. `OsdManager` also offers a **sticky** OSD
(`show_sticky(key, …)` / `update_sticky` / `dismiss_sticky`): no auto-hide,
excluded from the `osd_max` eviction, updated in place via
`_OsdWindow.set_text`, kept on a plain click and removed only by its close
button (which fires the owner's `on_close`) — used by the Digest plugin.
The bubble (rounded background +
`osd_opacity`, border) is painted in `_OsdWindow.paintEvent`. When
`compositing_available()` finds **no** X11 compositor (`_NET_WM_CM_S0` has no
owner, checked via `libX11`/ctypes) **and** the opacity is below 100 %,
`_refresh_backdrop()` snaps the desktop area behind the window
(`_grab_region`): it tries a region `QScreen.grabWindow(0, x, y, w, h)`, but a
one-time probe compares it against `grabWindow(0)` cropped to the same area
(`_region_matches`) and permanently falls back to the full-grab+crop path when
the platform ignores the region offsets; the snapshot is refreshed on spawn, on
preview drag and after every `_restack` (windows are briefly hidden) — and
painted under the translucent bubble so it looks transparent instead of black;
at 100 % opacity the whole rectangle is filled with the bubble color (straight
corners) and no snapshot is taken. Wayland/unknown platforms always composite
and use plain alpha. The tray icon's middle click
(`TrayIcon.cycle_unread_requested`, `ActivationReason.MiddleClick`) lets the
user walk unread conversations: `MainWindow._on_tray_cycle_unread` opens the
topmost roster contact with `unread_count > 0`, then `_reset_unread` +
`mds_mark_displayed` mark it read so each further middle click advances until
nothing is left. Tray balloons are gated by `notifications.popups`
(`off`/`system`/`system_messages`, default `system`; a legacy bool is coerced by
`tray.normalize_popups_mode`): `TrayIcon.show_message(..., kind="message")` is
the incoming-message preview and is shown only in `system_messages`, while
system balloons (connection/calls/invites/errors) are hidden only in `off`;
`MainWindow` re-applies the mode from `_on_settings_applied`.

**Sound notifications** (`include/sounds.py`, `ui/sounds.py`): themes live in
`resources/sounds/<id>/default.cfg` (`[header] name`, `[sounds] event=file`);
`include.sounds` discovers/parses them (`discover_themes`, `theme_sounds`;
events `new_message`/`message`/`message_send`/`ft_start`/`ft_finish`/
`contact_online`/`contact_offline`/`start`). `ui.sounds.SoundPlayer` plays a
theme's WAV for an event with one cached `QSoundEffect` per file, and degrades
to a no-op when Qt Multimedia (libpulse) is unavailable. `MainWindow._sounds`
is created in `__init__`, its theme re-applied in `_on_settings_applied` and
passed to `PreferencesDialog`. Triggers, each gated by
`notifications.sound_*` (all off by default; `sound_theme` default `default`):
`_notify_incoming_message` (called by `_on_message_received` — skipped for
carbons — and `_on_muc_private_message`, *before* the tab opens) plays
`new_message` when no tab is open and `message` when the tab is open but not
focused; `_on_groupchat_message` plays `message` on a mention of our nick
(`chat_themes.mentions_nick`, the same rule as the highlight) when
`sound_muc_mention` is on; the six send handlers (1:1/PM/MUC, incl. reply/edit)
play `message_send`; `_on_file_transfer_progress` plays `ft_start` on an
incoming `start` and `ft_finish` on `done`; `_on_presence_changed` plays
`contact_online`/`contact_offline` on a real transition, the first presence per
JID after login being recorded silently (`_presence_sound_seen`, cleared on
`session_started`/`disconnected`). **Call sounds** use the same player:
`SoundPlayer.play_file(path, loop=True)`/`stop_file` loop a loose effect (the
incoming 1:1 ringtone `resources/sounds/effects/ringtone.wav`, while an
`IncomingCallDialog` is open — `_start_call_ring`/`_stop_call_ring`, gated by
`notifications.sound_call_incoming`, default on), and
`include.sounds.call_tone_path("ringback"|"busy")` **generates** a call-progress
tone WAV (`generate_tone_wav`) played on an outgoing call (`_start_call_ringback`
while `call_state == "ringing"`, `_play_call_busy` on a rejection
`decline`/`busy`/`reject`; both stopped in `_on_call_ended`).
The Preferences → Notifications → Sounds tab
has a «Звуковая тема» selector, nine per-event checkboxes (label without the
old leading «Звук») and a note-icon preview button before each
(`prefs_sound_preview_tip`). [`tests/test_sounds.py`]

Unread counters are persisted per contact (`core/unread_state.py` →
`$XDG_DATA_HOME/stanza-im/<jid>/unread.json`) so the badges survive a restart.
`MainWindow` keeps one record per chat key in `_unread_chats` and derives the
`unread`/`mentions`/`read_sid` views from it (`_unread_counts`,
`_unread_mentions`, `_unread_displayed` are properties), so the badge, the tray
and the XEP-0490 seed can never drift apart. The same counter is mirrored on the
chat tabs and the window title (Psi style): `_push_unread_to_chat` →
`ChatWindow.set_unread(jid, unread, mentions)` renders `[N] name` on the tab and
paints it `#cc0000` for a 1:1/private chat with unread (a conference only when a
message mentions us), while the title shows `[<sum over the open tabs>] <active
chat name>` (in `unified` mode through the `window_title_changed` signal, since
the title belongs to the main window); `appearance.show_unread_in_tabs` (default
on, Preferences → Appearance → «Разное») turns it off.
`_recount_unread` recomputes the
aggregates (restored counters blink the tray again after a re-login,
`_on_session_started`). It loads them at startup, applies them when building
roster rows (`_add_roster_item`/`_sync_conference_roster`), keeps them updated
in `_bump_unread`/`_reset_unread` and flushes them to disk with a 1 s debounce
plus on quit. All three conversation kinds count unread: `_on_message_received`
(1:1), `_on_groupchat_message` (conference, `mention=is_mention` from
`mentions_nick` — the same rule as the highlight and the mention sound) and
`_on_muc_private_message` (attributed to the **sender**, under the PM chat key);
a message that arrives while its own conversation is the active one is skipped,
and an archived MAM replay never counts. `_reset_unread` also records the
**read anchor** via `ChatWidget.read_anchor()` (newest displayed message:
server `stanza-id` → `origin-id` → own message id, plus its raw timestamp).
**Reaching the newest message is the only thing that marks a conversation
read** — opening it, switching to it, sending into it and a remote XEP-0490
state never do. `MainWindow._restore_anchor_for` therefore hands the anchor to
the tab (`ChatWidget.set_restore_anchor`) on open (`_on_contact_open`,
`_on_muc_participant_clicked`) without clearing anything; `set_history` then
calls `_restore_from_anchor`, which scrolls to the anchor message (by ref, else
by timestamp via `_entry_before_or_at`, else paging the local archive with
`_jump_to_message`), so an unread chat opens with the unread block right below
the last message the user read. A legacy row with no replyable id is addressed
by its timestamp (`ChatView.scroll_to_time`, the last `.stanza-message` with
`data-stanza-time <= ts`), and an unreachable anchor falls back to the bottom
instead of leaving the reloaded page at its oldest row. The anchor is applied
once and dropped. The
parked scroll is **suspended** meanwhile (`ChatView._scroll_suspended`), so the
view does not report an "at the bottom" position for a document that is still
loading and the fresh window cannot mark itself read on its own. The explicit
**«Отметить прочитанным»** actions (a contact's context menu, before «Очистить
историю», and «Отметить все прочитанным» in the Actions menu) share the same
`MainWindow._mark_chat_read` helper: it clears the counters, removes the
divider of an open tab and publishes the XEP-0490 displayed state. A right
click on a roster **group header** opens its own menu
(`RosterWidget.group_context_menu` → `MainWindow._on_group_context`) with the
same «Отметить все прочитанным» action, scoped to that group's rows
(`_mark_group_read`). A real contact group (not a virtual group and not «Без
группы») also gets «Переименовать группу» (`_rename_group` →
`JabberClient.rename_group`, which rewrites the group of every member and
requests the roster once).

**Resuming an unread conversation (full window + unread separator)**: an
unread chat opens with **every** new message already on screen — the window is
the ordinary tail of the conversation and there is no forward pager (older
messages are reached by scrolling up or the archive/jump menus, the jump button
returns to the newest one). The persisted anchor therefore only does two
things: it places the separator and it is the position the window opens at.
`MainWindow._focus_chat(jid, chat, is_new=…)` (called from `_on_tab_focused`,
`_on_contact_open`, `_on_muc_participant_clicked`) resolves the anchor and
hands it to `ChatWidget.set_history(…, anchor=…)` (and `set_restore_anchor`)
alongside the tail loaded by `MainWindow._load_history[_async]`
(`history.load_history`, deduplicated per conversation through
`_history_loading`). The counters stay untouched, so the anchor cannot be
overwritten mid-open; a background auto-join MUC keeps loading the ordinary
tail and never applies an anchor.

The separator is part of the message stream rather than a control link:
`ChatThemeFactory.render_message(unread_marker=True)` prepends
`<div class="stanza-unread">` and `_UNREAD_CSS` styles it `font-size: 0.85em`,
so the label stays one step below the chat text and follows both the chat font
setting and the Ctrl+wheel zoom; it needs no change in the chat skins and works
in the `QTextBrowser` fallback alike. `ChatWidget` keeps the boundary in
`_unread_boundary` (`{"ref", "ts", "sid"}`) and hands the flag out once per
rendering in `_take_unread_marker`: entries arrive oldest-first, the entry
carrying the anchor's own reference is the last read one and the next message
opens the block (matched by reference, otherwise by the order of arrival). A
read point **older** than the whole loaded window — an unread block bigger than
`chat.history_limit` — is only reachable by paging the local archive back, so
`_boundary_reachable` defers the separator (`_unread_resolving`) until
`_load_jump_pages_async` located it and `_finish_unread_resolve` re-renders the
completed window; when the archive cannot reach the read point the separator
falls back to the first message of the window. A conversation with **no stored
read point** (never read to its end, so `ref`/`ts` are both empty) is treated as
wholly unread: `_boundary_reachable` returns true, the block spans the whole
loaded window and `set_history` opens the tab at its first message (it sets the
restore anchor to it), so the `▼ N` count and the `@` button are present right
away. `_finish_unread_resolve` re-runs `refresh_unread_mentions` as well, so a
mention that only surfaced after the archive paged back still reaches the `@`
button. A message arriving in an
open but unfocused tab is armed by `MainWindow._arm_unread_separator` **before**
`ChatWidget.add_message` renders it (`ChatWidget.note_unread_arrival`), so the
incoming entry carries the separator and the conversation the user already read
stays separated; a fully read tab has no boundary yet, so one is taken from the
newest message on screen. Arming *after* the render would be lost by the next
`_render_all` pass. The separator stays in the window **until the conversation
is actually read** (reaching the newest message removes it in place — a
re-render cannot resurrect it), `_render_all` re-emits it once per pass
(theme/font change, restore) and `detach`/`refresh_history` drop the state.
Reaching the bottom is `bottom_reached` again, with no trimming to suppress, so
the newest message always marks the conversation read. The same pass **seeds
the jump button** from the block that is already on screen
(`ChatView.seed_unseen(count, target_id)`, the first unseen message), so an
unread chat shows `▼ N` instead of an empty tail; a re-render does not recount
it. The count is cleared only when the view actually reaches the newest message
(`ChatView._note_bottom`, edge-triggered and suspension-aware), never by the
transient "at the bottom" position during the anchor restore.
`ChatView.scroll_to_message`/`scroll_to_time` park the request in
`_deferred_scroll` while the document is empty or has buffered chunks
(`clear()` loads a fresh page asynchronously), replaying it in
`_on_load_finished`/`_probe_chat_alive` after the pending markup is appended —
otherwise the anchor resume ran against a blank document and the chat stayed
scrolled to the newest message.
[`tests/test_read_anchor_restore.py`]

A conversation is marked read when its view **reaches the newest
message** — the single point described above: `ChatView._note_bottom` (both the WebEngine poll — fed by the
existing `st`/`innerHeight`/`scrollHeight` values, so no new JS control ref is
needed — and the `QTextBrowser` fallback's scrollbar) emits `bottom_reached`
edge-triggered, re-armed by scrolling up; `ChatWidget` →
`ChatWindow.bottom_reached(jid)` → `MainWindow._on_chat_reached_bottom`,
which resets only the conversation the chat area actually shows
(`_chat_area_active()` and `current_jid()`), so a background tab reaching the
bottom never clears its counters. An incoming message is published as
XEP-0490 displayed only when `MainWindow._chat_at_bottom(jid)`
(`ChatWidget.at_bottom()` → the view) holds, so a message that lands while the
user reads further up is not advertised as seen; the chat's own `bottom_reached`
marks it read when they get there.
The **tray only blinks while logged in**: `_sync_tray_blink`
(called from `_on_session_started`, `_on_stream_resumed`, `_bump_unread` and
`_reset_unread`) starts/stops it, and `_on_disconnected`/`_on_sm_failed` stop it
so the offline icon is visible — restored counters do not blink on the login
screen. The blink is **smooth** (`TrayIcon._blink_step`): a ~25 fps timer fades
the icon out and back in over a 1 s period following a cosine curve (the icon is
painted at the current opacity, so it pulses instead of toggling on/off). The
file is a **v2 payload**:
`{"account": "<jid>", "chats": {"<chat-key>": {"unread": N, "mentions": M,
"read_sid": "<stanza-id>", "read_ts": "<ts>", "read_ref": "<message-id>",
"seen_sid": "<stanza-id>", "seen_ts": "<ts>", "seen_ref": "<message-id>",
"seen_at": <unix>}}}`,
where *chat-key* is the conversation key the chat tabs use — a bare JID for 1:1
and MUC private messages (always `room/nick`), the bare room JID for a conference. `read_sid` is the last
displayed MDS
stanza-id (the v1 `{"count": N, "displayed": "sid"}` layout and the v0
`{"jid": N}` one are still read); `_flush_unread` collects it from the client's
`_mds_local` and
`_on_login` seeds it back via `client.set_displayed_state`, so the startup
XEP-0490 catch-up cannot clear unread messages that arrived after our own last
displayed point (a genuinely newer remote state still clears them). The
`seen_*` fields are the **partial progress** point: the newest message that has
scrolled into the viewport (see the partial-read paragraph below), kept next to
the read anchor so a partially read conversation resumes where the user stopped
looking.
`unread_state.load_chats()/save_chats()` are the v2 API; `load_state()`/`save()`
are the derived legacy views. OSD popups
are not replayed. The file also stores the owning account JID
(`unread_state.save_chats(..., account=cfg.jid)`); `load_chats(cfg.jid)` ignores
counters written for a different account, so switching accounts never keeps the
previous account's tray blinking (legacy account-less files still load). OSD
popups are not replayed. [`tests/test_unread_state.py`]

**Session logout**: the Actions menu's «Завершить сеанс» (above «Выход», same
`gtk-quit.png` icon) calls `MainWindow._logout`: it flushes unread/roster cache,
detaches the client (`JabberClient.detach` clears the UI event callbacks) so its
asynchronous disconnect cannot emit a late `disconnected`/roster event over the
next session, disconnects and drops `self._client`, clears the per-account UI
state (`_reset_account_ui`: roster, chat tabs via `ChatWindow.close_all`, MUC
maps, bookmarks, live unread totals, tray blink/offline icon) and returns to
the login page with the saved JID prefilled. `_on_session_started` clears the
status bar, so a successful (re)login never keeps a stale offline status. The
unread counters stay on disk (bound to that account), so logging back in
restores them; the application keeps running (unlike `_quit`).

**Media previews** (`include/media.py`, `ui/media_preview.py`, `ui/media_viewer.py`):
`media_kind(url)` classifies URLs by extension (image/audio/video). The
`chat.media_preview` selector (`none`/`images`/`images_audio`/`all`, default
`images`) gates substitution: `ChatThemeFactory.set_media_preview(service, mode,
size)` makes `_body_fragment` replace a media URL's `<a>` with an embed —
`MediaPreviewService.markup()` returns an `<a class="stanza-media"
href="stanza:view:image/<urlenc>">` wrapping an `<img>` (cached thumbnail as a
PNG data-URI), or a native HTML5 `<audio>`/`<video controls>` (the class sits on
a `.stanza-media-video` wrapper span — a single click on the video toggles
play/pause through a 250 ms timer that the document-level double-click handler
cancels, and the double click opens it fullscreen in the `MediaViewer`). Image originals
are downloaded in a worker (`asyncio.to_thread`/thread) and resized to
`appearance.media_preview_size`; thumbnails and originals live in
`MediaCache` (`$XDG_CACHE_HOME/stanza-im/media/`, `index.json`, last-access
tracking) and are evicted by `appearance.media_cache_days` (TTL) and
`appearance.media_cache_mb` (LRU) on a 30-min timer plus one deferred pass
after startup (never blocking startup). The ready PNG data-URIs are held in a bounded
in-memory LRU (`MediaPreviewService._thumb_uris`, 16 MB budget), so a long
session with many images cannot grow the thumbnail cache without limit.
The thumbnail is scaled to fit `media_preview_size` in **both** dimensions
(KeepAspectRatio), so `set_media_thumbnail` drops the placeholder's forced
`width` once the image loads — a portrait picture then shows at its real
(bounded) height instead of being stretched into a tall preview. The message
grows, so the view scrolls back to the end when it was already there (the same
`stick` rule as `update_reactions`).
`thumbnail_ready` is pushed into every open
view via `ChatView.set_media_thumbnail` (in-place `src` swap, no document
reset). Clicking the preview emits `stanza:view:` → `MediaViewer` (image fitted
to the window; video in a WebEngine `<video>` window with native `controls`
(a single click on the video toggles play/pause via a 250 ms timer that the
double click cancels, so the pair never fights), `F11`/double-click fullscreen —
the double-click asks Python through a QWebChannel `bridge.toggle_fullscreen()`
(a `stanza:viewer-fs` navigation, matched by its whole URL, is a fallback);
`Esc`
closes the viewer, `Ctrl+wheel` zooms the image (0.1–8×, `Ctrl+0`/double-click
resets to fit) and the zoomed image is dragged to pan with the left mouse
button (open/closed hand cursor)); the
WebEngine `contextMenuEvent` reads the request via
`QWebEngineView.lastContextMenuRequest()` (Qt 6; the old
`page().contextMenuData()` does not exist and silently fell back to the engine
menu) and always builds its own menu — never Chromium's. The media kind comes
from the `MediaType*` enum members, and for an embedded image the shareable
original URL is decoded from its `stanza:view:` link (the reported media URL is
only the data-URI thumbnail). Over media it keeps the
copy/Save as…/open viewer/fullscreen entries; otherwise it offers «Поделиться»
(«Share», only for `http(s)`), the `xmpp:` bookmark/contact entries (see above),
copy link / open in browser for a web link, copy for a selection, «В заметки»
(«Add to notes», only while the Notes plugin is active — it adds the selected
text as a note, title `@<name> <date> <time>`, tag «Сообщения») and "Select
all". Sharing (and an address-less
``xmpp:?message;body=…`` URI) opens `ShareDialog` — a checkable list of the
roster contacts and the conferences we are in — and sends each chosen target a
`«Переслано:»` line followed by the content as a XEP-0393 quote
(`compose_reply_body`); 1:1 targets are echoed locally via
`_display_local_outgoing` (and stored), conferences get a groupchat message.
When the shared content is a media URL, `MainWindow._resolve_share_media`
attaches XEP-0385 SIMS metadata so clients build a preview: the original
message's stored media dict (name/size/media-type/width/height/hashes) looked up
by URL via `ChatWindow.media_for_url` (`ChatWidget.media_for_url`), else the
media cache (`MediaCache.info`), else a URL-only descriptor (name/media-type
from the extension); `_send_share` passes it as `media=` to
`send_message`/`send_muc_message`. Previews are
off when QtWebEngine is unavailable. Settings changes re-render open chats via
`ChatWindow.rerender_messages()`. The `MediaViewer` window fits the image after
`showEvent` (a cached original returns before layout, so the initial fit is
deferred) and persists its geometry/position in the shared `media_viewer`
config section (image and video viewers share it). Three actions float over the
media **without a panel** — Download (`save_requested`), Copy link
(`copy_requested`) and Share (`share_requested`) — as a Qt overlay frame for
images and as an HTML overlay (wired through the `_VideoBridge`) for videos;
`MainWindow._on_media_view_requested` connects them to the existing
`_on_media_save_requested`/`_on_media_copy_requested`/`_on_share_requested`
handlers, passing the viewer as the dialog parent so the save/share dialogs open
over the viewer, not the roster. Covered by `tests/test_media.py`.

**CAPTCHA Forms (XEP-0158, `ui/captcha_dialog.py` + XEP-0221 media)**:
`<media xmlns='urn:xmpp:media-element'/>` on a form field is parsed from the
field's raw XML (no XEP-0221 plugin needed). A `cid:` media URI is resolved
from a sibling `<data xmlns='urn:xmpp:bob'/>` payload (XEP-0231) into an inline
`data:` URI by `_bob_data_uris`/`_resolve_bob_media` in `core/client.py`
(applied in `get_registration_form` and `_captcha_form`), and
`DataFormWidget._load_media_image` decodes such `data:` URIs without a network
fetch — so captcha images embedded by ejabberd are shown inline. A challenge
arrives either as a
`<message>` with
`<captcha xmlns='urn:xmpp:captcha'><x type='form'/>` (own `MatchXPath` handler;
a guard in `_on_message` keeps it from rendering as a chat message) or inside a
CAPTCHA-protected room's join error presence. Both emit
`captcha_challenge(jid, form, oob, body)`; `MainWindow._on_captcha_challenge`
opens a non-modal `CaptchaDialog` (`DataFormWidget` renders the challenge —
images are fetched in a worker thread and shown inline, audio/video open in the
media viewer, `SHA-256` hashcash fields are solved in the background) and
`client.answer_captcha` sends `<iq type='set'><captcha><x type='submit'>…`. A
room that rejected the join is re-joined after a successful answer. The
registration dialog renders an embedded CAPTCHA form the same way and also
shows the query-level `<instructions>`/OOB URL. [`tests/test_captcha.py`]

**Account registration (`ui/account_registration_dialog.py`, XEP-0077)**:
`LoginWidget`'s "Создать аккаунт" link (`register_requested`) and the
icon-only button next to the Jabber ID in Preferences → Connection
(`register.png`, styled like the change-password button) both open
`AccountRegistrationDialog`. Step 1 collects the server (editable combo; the
suggested list comes from `resources/servers.txt`, one domain per line with
`#`/blank lines ignored — `include/constants.SERVERS_FILE`) plus the
connection settings (host/port override, `tls_mode`, `starttls_mode`, proxy),
defaulting to "Prefer TLS"/"Always". "Далее" builds a throwaway `JabberClient`
and calls `connect_for_registration()`, which unregisters the SASL feature on
that connection and waits for `stream_negotiated`; the dialog then fetches the
XEP-0077 form with `get_registration_form(server)` (a connection failure and a
"server does not offer registration" failure are reported separately). Step 2
renders the form with `DataFormWidget`/`LegacyFormWidget`
("Зарегистрировать"/"Отмена"); a read-only URL field (`text-single` whose
value is an `http(s)` URL) renders as a clickable link **only** — no editable
input, link text is the field label (falling back to the short
`captcha_open_oob`), the URL is the tooltip and the value is submitted
unchanged (`DataFormWidget._link_label`/`_link_fields`); a `fixed` field with
no label spans the full row so its text is not wrapped into a narrow column;
a `text-multi` field renders as a multi-line `QPlainTextEdit` whose value is
the list of lines (one XEP-0004 `<value>` each). A `jid-multi` field (e.g. the
conference `muc#roomconfig_captcha_whitelist`) is edited the same way, one JID
per line (commas also split), and every JID is normalised (`normalize_jid`);
`JabberClient._config_form` submits a list as several `<value/>` elements.
The dialog is sized to the form (`fit_dialog_to_content`, deferred after the
form is built and re-run on the `media_ready` signal; it measures the live
inner widget because `QScrollArea` caches its size hint, and clamps to the
screen, the `QScrollArea` then providing scrolling only when needed). On
success the dialog shows
`ui/registration_result_dialog.py::RegistrationResultDialog` with the Jabber ID,
password, encryption/proxy details and the data actually submitted
("Копировать" copies the whole summary, "Применить" writes the account,
"Закрыть" discards it); only on "Применить" does the dialog store the account
(`jid`, `password`, `save_password`) and the connection/proxy settings in the
shared `Config` and emit `registered(jid, password)`; `MainWindow` prefills
the login form (`LoginWidget.prefill`), returns to the login page, re-applies
the settings and closes the Preferences window if it was open. The login
widget now shares `MainWindow._config` so the saved values cannot be
overwritten. [`tests/test_registration.py`]

**XML console (`ui/xml_console.py`, Actions → «XML-консоль» after «Профили»)**:
a non-modal window that captures the raw stream from the `slixmpp.xmlstream`
logger — the same `SEND:`/`RECV:` dump as `-x` and the file log — so both
directions are seen. A `_XmlConsoleLogHandler` parses the `SEND: `/`RECV: `
prefix (decoding bytes arguments), ignores other debug records and forwards
each payload through the dialog's `stanza_captured` signal (thread-safe).
«Включить» (off by default) remembers the logger's level, sets
`slixmpp.xmlstream` to DEBUG and adds the handler; disabling/closing removes the
handler and restores the level (a no-op under `-x`/`-l`, which already run at
DEBUG). The dialog buffers `Entry(incoming, kind, xml, from, to, ts)` rows
(cap 5000), classifies each payload by its **local name** with a namespace
check that accepts both the bare form and `jabber:client` (slixmpp omits the
default namespace from top-level stanzas, so a bare `<message>` must classify
as a message; `urn:xmpp:sm:*` → `sm`, anything else — CSI, stream
header/footer — → `other`), pretty-prints it with `minidom` (two-space indents,
text-only elements stay on one line, unparseable payloads pass through
unchanged) and renders it coloured by direction/kind in a read-only
`QPlainTextEdit` (incoming: message red, presence orange, iq turquoise, sm
blue; outgoing: message yellow, presence green, iq light blue, sm purple; other
grey; dark background). A one-line colour legend directly under the output
(`_build_legend`, full width) repeats that palette per kind — a coloured square
with ↓ for incoming and ↑ for outgoing, with a tooltip — so the colours are
self-explanatory. Five filter checkboxes (Сообщения/Присутствия/IQ/SM/
Прочее, all on) and a substring JID field re-render the whole buffer live
(unchecking hides already-captured stanzas, rechecking restores them; the JID
field is a case-insensitive substring match over the full `from`/`to`, so
`conference.linuxoid.in` catches every room on that service).
«Экспорт» writes the displayed text, «Очистить» empties the buffer and the
view, «Ввод XML» opens `XmlInputDialog` (multiline + Отправить/Отмена) and
`client.send_raw_xml(text)` sends each top-level element (an `<iq>` without an
`id` gets one) after stripping an XML declaration. Incoming non-stanza stream
elements (SASL challenge/success/proceed, `<stream:features>`) are not part of
the raw dump and therefore do not appear.
[`tests/test_xml_console.py`]

**PEP manager (`ui/pep_manager_dialog.py`, Actions → «PEP-менеджер» right after
«XML-консоль», same icon)**: one window with a `QStackedWidget` — a node list
(``client.pep_list_nodes`` = ``disco#items`` on our bare JID, keeping only items
that carry a ``node``), an "open" view (the node's items XML pretty-printed via
`xml_console.format_xml`, «Назад»/«Копировать») and a "settings" view
(`DataFormWidget` over the `pubsub#owner configure` form, «Назад»/«Применить» →
`client.pep_set_node_config`). The four list buttons — Refresh (`reload.png`),
Delete (`process-stop.png`), Settings (`edit.png`), Open
(`service-discovery.png`) — gate Delete/Settings/Open on a selection; Delete
confirms first (`client.pep_delete_node`). [`tests/test_pep_manager.py`]

**Slash commands**: `/me` (XEP-0245) is sent as-is; bodies starting with
`/me ` render as italic `.stanza-action` lines (`* sender phrase`) via
`ChatThemeFactory.render_action()`, branched in `chat_view.py` across live
messages, `prepend_messages`/history and the `QTextBrowser` fallback (the
phrase is escaped with URLs/emoticons, never XEP-0393-styled). `/nick <nick>`
is intercepted in `chat_widget._handle_slash_command()` (only in MUC) and
rejoined with the stored room password by `_on_nick_change`/`_update_muc_self_nick`;
per XEP-0045 §17.1 the nick is a resourcepart — `@`, `\` and spaces are valid,
but control characters, `/`, an all-whitespace nick or >1023 UTF-8 bytes are
rejected, and a busy nick reverts without the auto-underscore retry.

### 5. LRU Icon Cache (`icons.py`)

Pixmaps are cached with a 200-entry max and 60-second TTL. A `QTimer(30s)` evicts
stale entries. Avatars are stored as file paths only — `QPixmap` is created on-demand
during `paintEvent()` and never persisted in `UserItem`.

**SVG icon convention**: icons authored for the project live as SVG under
`resources/images/scalable/<category>/` (`actions`, `categories`, `places`,
`apps`); the sized directories keep the rasterised/legacy art. All icon
resolvers go through `include.constants.find_icon` (scalable first, then the
sized dirs), and `IconCache.get_category_icon(name, size)` renders the scalable
SVG at the requested size. The online / free-for-chat status icons use the
**green-bulb** variants `jabber-online-green`/`jabber-chat-green` (`.png` at 16
and 32 px, plus the `.svg` used by the View-menu entry) —
`IconCache.get_status_icon` maps `online`/`chat` to them; the original blue
`jabber-online`/`jabber-chat` files are kept so the look can be reverted by
changing the names back.

### 6. Lightweight i18n (`i18n/`)

Translation strings are plain Python dicts. `tr(key, **kwargs)` looks up and formats.
No `.ts`/`.qm` compilation. Language auto-detected from `LANG` env var.

### 7. Event-Driven XMPP (`core/client.py`)

`JabberClient` wraps slixmpp and emits callbacks via `emit(event_name, *args)`.
UI modules register with `client.on("event_name", callback)`. This decouples
the XMPP layer from the UI.

Roster events are diff-based: `roster_received(items)` fires after the initial
download, then `roster_item_added(item)` / `roster_item_removed(jid)` for
subscription changes. Presence is aggregated by **bare JID** across resources
(best `show` wins via `SHOW_ORDER`), and empty/`available` shows are normalized
to `"online"`. The roster is cached across sessions for
**XEP-0237 roster versioning** (`core/roster_cache.py`,
`$XDG_DATA_HOME/stanza-im/<jid>/roster/<account>.json`, 0600; a Unicode
account name gets a short SHA-1 suffix and the payload records its account, so
two such accounts never share a file): `_seed_roster_cache()`
(called at the start of `_on_session_start`, before `request_roster`) loads it
lazily and preloads `client_roster` + `version`, so the server can answer an
unchanged version with an empty result
instead of a full roster; `_schedule_roster_save` (1 s debounce) rewrites the
cache after every roster update and `flush_roster_cache` on quit. A
missing/corrupt cache falls back to the full request. **Room pseudo items**:
slixmpp's `basexmpp._handle_available` does `roster[pres['to']][pres['from']]`
for every presence, so a room's *own* presence (`from="room@conf"`, no
resource, no `muc#user`) creates a pseudo roster item inside `client_roster`.
`JabberClient._known_rooms` (filled on `join_muc` and any groupchat presence)
is filtered out in `get_roster_snapshot`/`get_roster_state` and in
`_seed_roster_cache`, so such rooms never appear as contacts nor get written to
the cache; `_on_presence` also ignores them. `_on_presence` is subscribed to the
generic `presence` event (not just `presence_available`): slixmpp folds a bare
`<show>` value into the presence `type`, so a transport/RSS presence with
`<show>away</show>` and no `type` arrives as `presence_away`; the handler treats
show-based types as available (with that show) and filters out the service types
(`subscribe`/`subscribed`/`unsubscribe`/`unsubscribed`/`probe`/`error`).
Diagnostic `ROSTER[…]` DEBUG lines
trace the roster end to end (`ROSTER[update]` in `_on_roster_update`,
`ROSTER[seed]`/`[save]`/`[state]` in the cache path, `ROSTER[cache]` in
`roster_cache.py`, `ROSTER[contact]` in `get_contact`, `ROSTER[presence]` in
`_on_presence`, `ROSTER[ui]` in the roster rebuild).

Roster Item Exchange (XEP-0144): an incoming `<x xmlns='http://jabber.org/protocol/rosterx'/>` (in a message, bodyless included — its own `MatchXPath` handler, and a guard in `_on_message`/`_on_carbon_received`) is parsed by `parse_roster_exchange` and emitted as `roster_exchange_received(from, items, body)`. `MainWindow._on_roster_exchange` opens `RosterExchangeDialog` — a three-level `Add/Modify/Delete → group ("No group") → jid (name)` `QTreeWidget` whose parents are auto-tristate and whose leaves are checked by default — and applies the checked rows through `client.apply_roster_exchange` following XEP-0144 §3: an `add` merges the suggested groups (subscribing for a new contact), a `delete` drops only the suggested group while other groups remain (otherwise removes the contact), and a `modify` touches existing items only. A contact's roster context menu also offers "Send contact…" (`_on_send_contact` → `ShareDialog` → `client.send_roster_exchange`, a `<message>` with the rosterx payload plus a readable body).
[`tests/test_rosterx.py`]

**Presence subscription requests** (`presence_subscribe`): an incoming
`<presence type='subscribe'/>` (e.g. from an RSS/gateway transport) is handled by
`JabberClient._on_subscription_request` — if the peer is already `to`/`both` it
is auto-approved, otherwise it is emitted as `subscription_requested(jid, nick,
name, groups)` (nick from a raw `<nick>` element) and shown in the **Events**
tab as a `_SubscriptionRequestRow` with «Разрешить» (`ok.png`) / «Отклонить»
(`process-stop.png`) buttons. `client.approve_subscription` sends `subscribed`
and, when `to` is still missing, a `subscribe` too (so a transport gets `both`);
`reject_subscription` sends `unsubscribed`. An incoming `unsubscribe` is
auto-answered with `unsubscribed` and surfaced as an event, and an incoming
`unsubscribed` emits `subscription_cancelled(jid)` (an informational event).
The Events list is kept **in memory** (lost on restart): a decision does not
remove the row — `_mark_event_for_jid` calls `_SubscriptionRequestRow.mark`,
which hides the buttons and shows «Разрешено»/«Отклонено», so the search box
stays useful. A server with subscription **pre-approval**
(`urn:xmpp:features:pre-approval`, e.g. ejabberd) may grant a mutual
subscription without the user confirming, so `MainWindow.
_resolve_pending_subscriptions` (called on every roster update) marks a still
pending row approved once `client.subscription(jid)` is `to`/`both` — otherwise
a request the server already satisfied would linger. Events rows are separated
by a thin line (the list's `QListWidget::item` bottom border for plain events,
`_event_separator()` for the request rows). The contact context menu carries a
subscription **submenu**
(`_build_subscription_menu`, icon `reload.png`) built from the current
subscription and the roster `ask`: «Запросить подписку» (`arrow-up.svg`,
`subscribe`) for `none`/`from`, «Отправить подписку» (`arrow-down.svg`,
`subscribed`) while `ask='subscribe'`, «Удалить подписку» (`remove.svg`,
`unsubscribe`) for `to`/`both`. The handlers log `SUB[...]`.
[`tests/test_subscriptions.py`]

Message Carbons (XEP-0280, `connection.message_carbons`, default on) are enabled
after initial presence; forwarded 1:1 copies from other of our resources are
picked out of `<received>`/`<sent>` with `_carbon_inner` and emitted as
`message_received(..., carbon=True)` / `message_carbon_sent(...)`, so the UI
renders and stores multi-device activity like normal incoming/outgoing messages.

Message Displayed Synchronization (XEP-0490, `chat.message_displayed_sync`,
default on): the latest server `stanza-id` per chat is tracked on receive and
published to the private PEP node `urn:xmpp:mds:displayed:0` when the chat is
focused/active (server-assist via a companion XEP-0333 marker when the server
announces `urn:xmpp:mds:server-assist:0`); incoming PEP events (routed like the
extended-presence notifications, see below) and a catch-up
fetch apply remote displayed states (`mds_displayed(chat_jid, sid)`); they never
add a chat status line. A PEP echo of a state this client published itself
(recognised by the `_mds_own_sids` registry, which matters because the server
buffers the echo while the client is inactive, XEP-0352) is ignored, so a
single-device account never treats its own read position as "another device".
The remote state is
**clamped** against our own position instead of clearing blindly:
`MainWindow._on_mds_displayed` resolves the incoming chat JID to one of our
conversation keys (`_resolve_mds_key` — a 1:1 chat and a conference collapse to
their bare JID, while a private message matches its own `room/nick`/real-JID key
verbatim, so it never clears the conference) and, when something is unread,
`_clamp_read_state` resolves the remote `sid` in the local archive
(`history.timestamp_for_ref`, `newest_timestamp`): a device that has seen at
least as much as we have drops our counters and moves the read anchor to it,
while a device that is behind us leaves the unread block untouched (an id we
never stored is treated as "seen everything"). `_mds_apply_remote` skips a state
equal to the one already recorded in `_mds_local`; that map is seeded at connect
from the persisted unread state, so the startup catch-up does not wipe restored
unread (see the unread-counters paragraph above).

**Partial read progress (`seen`)**: scrolling a conversation into view records
the bottom-most visible message (`ChatView._find_last_visible_ref`, a WebEngine
JS query of `#chat .stanza-message`; `_last_seen_result` reads its
`data-stanza-id`/`data-reply-id`/`data-stanza-time`) and emits
`last_seen_changed(ref, ts, sid)` — but only while the view is actually scrolled
up (`ChatWidget._on_last_seen` skips a view at the bottom), so the transient
"at the bottom" position during an anchor restore cannot jump the seen point to
the newest message. The seen point is **monotonic**: `ChatWidget._on_last_seen`
drops a report whose timestamp is not newer than the highest one already emitted
(`_last_seen_ts`, never moved back) and the stored `seen_ts` is only rewritten
when it advances (`MainWindow._on_chat_last_seen`), so scrolling back up or
re-showing an already seen message never subtracts the same messages again.
`ChatWindow.last_seen` relays it to
`MainWindow._on_chat_last_seen`, which advances the persisted `seen_*` point,
shrinks the unread badge by the messages that just became visible
(`ChatWidget.count_seen_since`), and arms the `@`/jump state accordingly. The
`▼ N` number is the conversation's **roster unread counter**: `MainWindow.
_push_unread_to_chat` mirrors `_unread_chats[jid]["unread"]` onto the button
(`ChatWidget.set_unread_count` → `ChatView.set_unseen_count`) on open, bump,
seen and reset, so it ticks down while the user scrolls just like the badge;
the first-click target is refreshed separately from the local block
(`ChatWidget._sync_jump_target_from_block` → `ChatView.set_unseen_target`).
`ChatWidget.set_seen()` moves the unread separator boundary with it, and
`_restore_anchor_for` prefers the seen point over the read anchor, so reopening
a partially read conversation resumes where the user stopped looking instead of
dropping back to the old read point. The XEP-0490 `displayed` update for
partial progress is published through a single-shot timer
(`MainWindow._mds_throttle_timer`, `_flush_mds_pending`) at most once per
`chat.mds_displayed_throttle` seconds (1–30, default 3; Preferences → Chat →
«Общие»), carrying the newest seen stanza-id; reaching the bottom
(`_on_chat_reached_bottom`) still publishes at once and folds `seen_*` onto the
read anchor. [`tests/test_unread_state.py`, `tests/test_read_anchor_restore.py`]

Last Message Correction (XEP-0308): any own message is editable (Ctrl+Up =
last sent; the message menu's "Edit" button for `data-stanza-outgoing` wrappers
stores the referenced id in `window.__stanzaEditRef`, which the always-running
scroll poll delivers to Python as a `stanza:edit:<id>` ``link_clicked`` —
editing never navigates, so the chat document is never reset); the body loads
into the input with a cancelable editing banner and `_send` emits
`message_edit_sent`, so the client sends `<replace id='…'/>` (fresh stanza id)
and replaces the message locally (1:1) or via the MUC echo. The same message
menu carries "Copy" and "Forward": the latter stores the whole message
(`[time] sender: text`, or the media URL for a media-only message) as
`window.__stanzaForwardRef` → the scroll poll delivers it as a
`stanza:forward:<urlencoded>` ``link_clicked`` → `ChatWidget._handle_forward_uri`
→ `share_requested`, i.e. the same `ShareDialog` flow. A post-click
content probe (`_schedule_content_probe`/`_verify_after_click`) restores the
window via `document_lost` if the conversation vanished. Incoming corrections
replace (edited flag + a large bold «✎» appended right after the edited phrase
via `render_message(edited=True)`, `chat.allow_incoming_edits` on) or arrive
as new messages (off). History gains `message_id`/`edited` columns and
`replace_message()`.

Message Retraction (XEP-0424, `urn:xmpp:message-retract:1`; the legacy `:0`
namespace is accepted on receive): our own messages can be retracted from the
message menu's "Delete" or the inline "✕" button placed between Reply and the
menu button (`a.action-delete` is in every skin template; the page CSS hides it
unless the wrapper has `data-stanza-outgoing`, so our own live MUC echoes and
archive replays both show it, while foreign messages do not; it feeds
`window.__stanzaDeleteRef`, the same JS
`preventDefault` + scroll-poll relay). `ChatWidget._handle_delete_uri`
optionally confirms (`chat.confirm_retraction`) and emits `message_retract_sent`;
`client.send_retraction` sends `<retract id='…'/>`,
`<fallback for='urn:xmpp:message-retract:1'/>`, a fallback `<body>` and a
`<store/>` hint, and the message is replaced locally with a tombstone (the
wrapper gains `data-retracted="1"`, which the page CSS and the menu JS use to
hide the inline "✕" and the "Изменить"/"Удалить" items). Incoming
retractions never render their fallback body: with `chat.allow_incoming_deletions`
on the referenced message becomes a tombstone, with the option off it keeps its
body and gains a "✕" marker (like the «✎» edit marker). Archived `<retracted/>`
tombstones from MAM are stored with `retracted=1`. History gains
`retracted`/`retract_marker` columns and `retract_message()`.
[`tests/test_retraction.py`]

Moderated Message Retraction (XEP-0425, `urn:xmpp:message-moderate:1`): a MUC
moderator (role `moderator` or affiliation owner/admin) can retract another
participant's message. `MainWindow._apply_muc_admin` also calls
`_apply_muc_moderation`, which resolves `client.room_supports_moderation`
(disco#info, cached) and enables `ChatWidget.set_moderation_enabled` for the
tab; the message menu then shows "Удалить (модерация)" on incoming messages with
a server `stanza-id` (`data-moderatable="1"`, set by `_mark_message` when
`ChatWidget._can_moderate_entry` allows it). The click is relayed in-page
(`stanza:moderate:<id>` via `window.__stanzaModerateRef`, the same
preventDefault + scroll-poll relay); `_handle_moderate_uri` shows a single
`_ModerateDialog` (confirmation + optional reason) and emits
`message_moderate_sent` →
`client.moderate_message` sends `<iq type='set'><moderate id='…'><retract
xmlns='urn:xmpp:message-retract:1'/><reason/></moderate></iq>`. The room's
groupchat broadcast (`<retract>` with a nested `<moderated by='…'/>` and
`<reason/>`) is only accepted from the MUC service itself (`from` is the bare
room JID), never from an occupant. Because slixmpp's MUC handler requires a
`<body>`, bodyless retractions are routed by dedicated `MatchXPath` matchers
(`{jabber:client}message/{urn:xmpp:message-retract:1|0}retract` →
`_on_bodyless_retract_stanza`, alongside the other bodyless handlers) so the
moderation broadcast still reaches `_on_groupchat_message`; messages that do
carry a fallback `<body>` take the normal path and are skipped there. The
tombstone renders "Отозвано модератором" with the reason and history stores
`retract_reason`/`retract_by`. `chat.allow_moderation` (Preferences → Chat →
«Конференции», default on) is a receive-side switch between the tombstone and
the "✕" marker. [`tests/test_moderation.py`]

**Message Reactions (XEP-0444, `urn:xmpp:reactions:0`)**: the first situational
message button is a smiley (`a.action-react`, inserted before Reply in every
skin template) whose click is kept in-page (`window.__stanzaReactRef` through the
`_ACTION_JS` handler + the always-running scroll poll, `stanza:react:<id>`, never
a navigation). The view first reports the button rectangle through
`reaction_anchor` (JS `getBoundingClientRect` delivered by the scroll poll,
scaled from CSS to the view's logical pixels by `view.width()/innerWidth`
— one CSS px maps to `zoom` logical px on a zoomed chat page — and mapped to
screen coordinates), so `ChatWidget.reaction_requested(jid, ref_id,
x, y, w, h)` carries the button's screen rect. `MainWindow._on_reaction_requested`
opens `ui/emoji_picker_dialog.EmojiPickerDialog` as a frameless `Qt.Popup`
anchored next to the 🙂 button through `_place_popup_above` →
`ui/popup_position.popup_position` (pure, tested): the side (above/below) is
chosen by the room, the popup sits adjacent to the button and never covers it
(the other side is used when the chosen one cannot fit), with the left edges
aligned and, when that overflows, the right edges, then clamped to the screen.
The popup re-anchors itself whenever it is shown or resized
(`EmojiPickerDialog.reposition`, set by the owner): the dialog's real size
settles only after `show()` (its `sizeHint` differs), so a one-shot move would
leave a fixed gap to the button. A `-d` `REACT[anchor]` line logs the anchor
rect, the popup size, the computed position and its real geometry. The picker
holds a search field, a «Недавние» (Recent) area above the tabs and the
eight `include/emoji_data.py` category tabs below it. Emoji are drawn with an
auto-detected colour-emoji font (`emoji_font`/`emoji_font_family` try
Noto/Apple/Segoe/Twemoji/Symbola/…), applied to the grid buttons and to the
chat chips via the page CSS. Clicking an emoji → `_apply_reaction` appends it to
our current set, remembers it in `emoji.recent` and re-sends the full set. The
picker's «Убрать реакцию» button (shown when we already reacted) clears it. `client.
send_reactions(target, target_id, emojis)` sends a bodyless `<message><reactions
id='<target>'><reaction>😀</reaction>…</reactions></message>` (1:1 `type='chat'`,
MUC `type='groupchat'`; an empty set removes our entry); `_reactions()` parses
incoming stanzas and the bodyless `MatchXPath` handler routes them (`_on_message`
→ `message_reactions`; `_on_groupchat_message` → `groupchat_message_reactions`,
carrying the reactor's XEP-0421 occupant-id) and returns before any body is
rendered — a MUC reaction must never appear as an empty groupchat message. A
reactions message that also carries a fallback `<body>` is delivered by
slixmpp's own `message`/`groupchat_message` event, so the bodyless handler skips
it to avoid processing it twice. Each reactor's set replaces its
previous set (keyed by occupant-id in MUC — `_occupant_id(pres)` is stored in
`gi.users[nick]["occupant_id"]` — else nickname/JID). `MainWindow` persists via
`history.set_reactions` (SQLite `reactions` JSON column, migration) and refreshes
the open tab in place with `ChatWindow.update_reactions` → `ChatWidget.
set_reactions`. `ChatWidget.compute_reactions` aggregates chips
`{emoji, count, mine, title}` (title lists reactors + timestamps) and
`chat_themes._render_reactions_chips` renders `.stanza-reaction` spans under the
body (sorted by count desc, capped at 6 with a "+k" chip). Clicking a chip is
context-sensitive: our own (`data-mine="1"`) removes just that emoji
(`stanza:unreact:<id>/<emoji>`), a foreign one adds the same emoji from us
without the picker (`stanza:react-like:<id>/<emoji>` →
`reaction_like_requested` → `MainWindow._on_reaction_like_requested` →
`_apply_reaction`); the "+k" chip (`data-reactions-more="1"`) opens
`ui/reactions_list_dialog.ReactionsListDialog` via `stanza:reactions:<id>` →
`reactions_list_requested`. The list is flat and newest-first; each row is a
custom widget (reactor nick/JID with the date/time beneath on the left, the
emoji on the right drawn with `emoji_font`, so the reactor text keeps the normal
font). `ChatView.update_reactions` keeps the view pinned to the bottom when a
reaction grows the last message, so the "jump to end" button never pops up for a
message the user was already reading at the end. All these relays fall back to
`data-reply-id` when `data-stanza-id` is absent. Feature advertised as
`urn:xmpp:reactions:0`. [`tests/test_reactions.py`]

**OMEMO Encryption (XEP-0384, `stanza_im/xmpp/omemo/`)**: optional end-to-end
encryption with legacy OMEMO 0.3 (`eu.siacs.conversations.axolotl`) and OMEMO 2
(`urn:xmpp:omemo:2`), detected at runtime by importing the components
(`availability.py`: `slixmpp-omemo` + `python-omemo` + `oldmemo`/`twomemo` +
`xmlschema` + `cryptography`), so a present-but-broken package (a missing
transitive dependency such as `xmlschema`) is reported by its root cause. When a
package is missing the feature is disabled with a detailed `logger.warning` at
startup, a red notice on the (kept enabled) Preferences «OMEMO» tab — a
distribution-neutral «OMEMO недоступен» and the missing Python modules, with no
install command (the client runs on many platforms) — and an «OMEMO» row on
Help → About; the chat/roster entries are hidden and an unexpected init failure
is logged without a traceback. The availability probe
(which imports the backends) runs in a **background daemon thread** started by
`app.py`, so the login window never waits for it; the module is imported once,
so the first access at login/About time is instant. Keys live per profile (`storage.py`: JSON `omemo.json` in the account's
data dir, 0600). The concrete plugin (`plugin.py`, `OmemoPlugin(XEP_0384)`)
implements the storage and the trust policy: BTBV on (`omemo.blind_trust`,
default) blindly trusts new devices and warns via `_devices_blindly_trusted`;
strict mode distrusted undecided devices in `_prompt_manual_trust` so only
manually trusted devices receive messages. `manager.py` (`client.omemo`,
`OmemoManager`) wraps the session manager: it encrypts/decrypts, manages device
names/aliases and last-seen, and — because `slixmpp-omemo` 2.2.0 does not
implement Stanza Content Encryption — builds and parses the XEP-0420
`urn:xmpp:sce:1` `<envelope/>` itself (`sce.py`) for `omemo:2` while still
using the plugin's `SessionManager` for device lists, bundles and trust.
Sending goes through `client.send_omemo_message` (the 1:1 send handlers route
to it when `omemo.chat_mode(jid) == "omemo"`); incoming encrypted stanzas are
decrypted in `_decrypt_and_dispatch` and re-enter the normal paths with an
`encrypted` flag, stored in the new `history` columns and rendered as a lock
before the body. Device names can be mirrored to a private PEP node
(`core/omemo_aliases.py`, `urn:xmpp:omemo:aliases:0`, opt-in
`omemo.alias_sync`) so they follow the user across clients: a **manual** rename
is published (overwriting), while a **learned** name is published only when the
node has no name for that device (it fills gaps, never overwrites); a publish is
the union of local aliases, the node's current names (preserved) and learned
names, and the node snapshot is fetched before the first publish so another
client's names are never wiped. Fetched server names merge into the local
aliases (local wins). The QR code is
rendered by a bundled pure-Python encoder (`qr.py`). UI: the Privacy
preferences tabs (compact copy/QR icon buttons), `ui/omemo_devices_dialog.py`
(per-row icon actions for trust/rename/copy/delete; only global Refresh/Close
at the bottom), the reaction-style `ui/omemo_popup.py` (chat shield) and the
roster «Управление OMEMO» entry (a shield icon, in the rename/group/
subscription block). The chat lock button is always shown while OMEMO is
available — only the «OMEMO» mode entry is gated on the peer's support, which
is determined by the peer's caps **or** by a non-empty device list (many clients
publish devices without advertising OMEMO in disco; `_check_peer_omemo`
force-downloads the list when the caps are silent). An incoming encrypted
message auto-enables OMEMO for that chat (`omemo.auto_enable`, default on). The
device manager and the shield popup force-download the device lists
(`refresh_device_lists(..., force=True)`), and our own device gets a readable
label from the resource at login (`ensure_own_label`) when it has none. A
contact device's display name (`OmemoManager.device_name`) is resolved as
**user alias → peer label (omemo:2 signed label) → learned client name → raw
resource → `Device <id>`**: the client name comes from the resource that last
sent us a **decrypted 1:1** message (`note_device_resource`, persisted in
`omemo.json` under `device_names`), resolved via XEP-0092 `<name>` or XEP-0115
caps (`JabberClient.resource_client_name`). The device's last-seen
(`device_last_seen`, `omemo.json`) is set when we decrypt a message from it and
refreshed from presence for devices already mapped to a resource
(`note_resource_seen`, throttled to one write per minute). On the
chat toolbar the lock and shield sit **after** the XEP-0224 attention bell, so
the shield appearing/disappearing only moves the trailing stretch; the lock's
mode menu entries are checkable (the active mode carries the tick). The device
manager and the shield popup show each device's trust as a **coloured shield
icon** (`shield-trusted.svg` solid green = manually trusted, `shield-blindly.svg`
green outline = blindly trusted, `shield-unknown.svg` yellow = undecided,
`shield-distrusted.svg` red = distrusted); a click toggles trusted↔distrusted,
and each manager **and popup** row also shows the device's `device_last_seen`
(the device name is bold). Devices are listed by `OmemoManager.sorted_devices` —
recent activity
first, then named devices (alias/label/learned), then the rest. The shield popup
(accepting a `QPoint` or a tuple) sizes to its content and grows **upward** from
the click point (a small gap keeps the button that opened it uncovered),
falling back below when there is no room above; it only scrolls once the list
exceeds ~10 rows or neither side fits, and carries a header button
(`gtk-preferences.png`) to the full manager (opened `own=True` when the popup is
our own JID; the popup is parented to `MainWindow._chat_dialog_parent()` so the
manager opens over the chat window, not the roster). Its height is summed from
the row widgets (the scroll area's size hint is 0 until the event loop runs).
Deleting an own device (`purge_device`) downloads the published
list per namespace, drops the device and re-uploads it (preserving the remaining
devices' signed labels) — `SessionManager.update_device_list` only handles
*incoming* updates and never publishes; `OmemoManager.devices()` filters out
devices inactive in every namespace, so a removed device (and a peer's removed
one) disappears from the manager even though the offline cache keeps it. A new/untrusted device warning is a chat status line naming the device
id, JID and a **short** fingerprint (first three groups + `…`) with a
`stanza:omemo:<jid>` control link to the manager (relayed in-page like every
`stanza:` link); an own device (`device.bare_jid` == our JID) gets a distinct
text. `aesgcm://` URLs are linkified (`include/utils._URL_RE`) so the media
preview embeds OMEMO-encrypted images/audio/video, and the preview
service downloads and decrypts them (`MediaPreviewService._download_aesgcm`
→ `slixmpp.plugins.xep_0454.XEP_0454.decrypt`; the media viewer and audio
playback use the same helper). Sending follows XEP-0454 too: a file sent
from an OMEMO chat over HTTP Upload is AES-256-GCM encrypted in memory
(`JabberClient.send_omemo_file` → `XEP_0454.encrypt`), only the ciphertext
is uploaded, and the `aesgcm://…#iv+key` URL is sent inside the OMEMO
message (`MainWindow._launch_file_uploads` picks this path for a 1:1 chat
whose OMEMO mode is on; a conference or a non-OMEMO chat uploads the file
unencrypted, and P2P transfers are not covered).
[`tests/test_omemo.py`, `tests/test_omemo_crypto.py`]

**geo: links & map window (RFC 5870, `include/geo.py` + `ui/map_widget.py`)**:
`geo:lat,lon;u=accuracy` URIs in message bodies are linkified inside
`tokenize_urls` — with a resolvable message id the anchor becomes
`stanza:geo:<ref>/<urlenc>` (so XEP-0308 corrections update the open map in
place), otherwise it stays plain `geo:`. Like every other `stanza:` control
link the click is preventDefaulted by the `_ACTION_JS` document handler and
relayed through the always-running scroll poll, so it never resets the chat
document; the QTextBrowser fallback linkifies geo: via
`geo.escape_body_with_geo`. `MainWindow._on_geo_view_requested` opens a
`GeoMapWindow` (custom-QPainter OSM tiles, no WebEngine) keyed by
`(chat, ref)`: `GeoMapWidget` projects the Web-Mercator raster with the pure
math in `include/geo.py`, draws the `;u=` accuracy zone scaled by
`meters_per_pixel`, the start marker, the track polyline and the current
position, and supports drag-pan / zoom (clamped 2–18) / follow. Corrections
carrying coordinates are fed to the matching window by
`MainWindow._on_geo_message_corrected` (`Track.add_fix`, duplicate/gap
filtered, haversine speed in km/h on the status bar); a corrected body without
coordinates calls `mark_track_final()`. OSM tiles are fetched by the paced
`TileLoader` worker (browser `User-Agent`, ≤2 req/s, retry backoff) into the
LRU disk `TileCache` (`map.tile_cache_mb`/`tile_cache_days`,
`$XDG_CACHE_HOME/stanza-im/tiles/`); the cache and its 30-min prune timer are
created lazily on the first map window (`MainWindow._ensure_tile_cache`), so a
session that never opens a map pays nothing. In-memory tile bitmaps use a 32 MB
LRU budget (`GeoMapWidget._MEM_PIXMAP_BYTES`) that `set_zoom` flushes when the
zoom level changes, and the live `Track` is capped at 2000 fixes (oldest
dropped). Offline or with a tiled URL unset the window still paints
markers/status. Window geometry is persisted under `map.window`.

**xmpp: URIs & vCard copy (XEP-0147, `include/xmpp_uri.py`)**:
`xmpp:<jid>[?<action>[;param=val…]]` URIs in message bodies are linkified
(`include/utils.tokenize_urls` for QWebEngine, `geo.escape_body_with_geo` for
the QTextBrowser fallback). Clicking them never navigates: the `_ACTION_JS`
document handler preventDefaults the anchor and the always-running scroll poll
delivers the `xmpp:` href to Python as a `link_clicked` (the same defensive
relay as reply/edit/mention/geo), so the chat document is never reset by the
click. It then emits `ChatWidget.xmpp_link_clicked`
→ `ChatWindow.xmpp_link_clicked` → `MainWindow._on_xmpp_uri`:
bare JID / `?message` opens the chat (prefilling `body`), `?join` opens the
conference join dialog (prepopulating room+server — the link's own server is
**preselected**, not the account default — and persisting the server),
`?roster`/`?subscribe` open `AddContactDialog` prefilled with the JID. An
address-less `xmpp:?message;body=…` (no JID) opens `ShareDialog` with that body
instead. The chat **context menu** on an `xmpp:` link offers a «Скопировать
ссылку» (copies the raw `xmpp:` URI) plus bookmark/contact
entries by action (`_xmpp_menu_target`): `?join` → only «Добавить в закладки»
(opens `BookmarkDialog`, or the edit dialog when it already exists,
`MainWindow._on_bookmark_jid_requested`), `?roster`/`?subscribe` → only «Добавить
контакт», a bare `xmpp:user@server` (ambiguous) → both.
Unrecognized actions warn the user. The vCard dialog shows its JID with an
icon-only copy button right beside the address (toolbar-style
`QToolButton`, `copy.svg` in `ACTIONS_DIR_16`, tooltip "Copy XMPP address",
`make_xmpp_uri(jid)` → clipboard; for a **room** card the copied address carries
`?join`); the conference roster context menu's
«Скопировать адрес конференции» entry (directly below «История переписки»)
copies `xmpp:<jid>?join`. A non-conference roster contact's context menu also
carries «Пригласить в» (`_build_invite_menu`), a submenu of the conferences we
are in; picking one calls `client.send_muc_invite(target, room, reason,
password)` (XEP-0249, the room password is included when known) and shows a tray
notice — the entry is hidden when we are in no conference. An incoming
invitation opens `IncomingInviteDialog`; the inviter is shown as `nick (jid)`
(the nick resolved from the room's occupants or the XMPP roster and the real
inviter taken from the XEP-0045 `<invite from>`, which is the only source when
the room relays the invitation), or a neutral text when the stanza names no
inviter (`muc_invite_received_unknown`). An invitation stanza — both the
XEP-0249 shape and the XEP-0045 mediated shape
(`<x xmlns='http://jabber.org/protocol/muc#user'><invite from='…'/></x>`, also
handled by its own `MatchXPath` when the `jabber:x:conference` element is
absent) — is never rendered as a 1:1 chat message
(`JabberClient._on_message` skips it, including carbon copies) and is surfaced
only as the prompt plus an OSD notification. Failed vCard fetches emit `vcard_error` on the event
bus; `MainWindow._on_vcard_error` shows the user a notice only when the request
was user-initiated (`_pending_profile` set), silently dropping background probes.
The notice is a **non-blocking** tray balloon (never a modal `QMessageBox`, which
opened from the client's vCard coroutine re-entered the event loop —
"Cannot enter into task").

HTTP File Upload (XEP-0363): a toolbar above the chat input carries flat
icon buttons for Clear, vCard, Smiley, Whiteboard and "Send file"; in a 1:1 chat "Send file"
is a menu ("P2P" / "P2P IBB" / "HTTP Upload"), while a conference only supports
HTTP Upload and gets a plain button (no menu). The Smiley button
(`smiley.svg`, `ChatWidget._open_smiley_picker`) opens
`ui/smiley_picker.py::SmileyPicker` — a frameless `Qt.Popup` grid of the current
emoticon set (`EmoticonSetSource` over `include.emoticons.set_items`); the chosen
code is inserted as plain text (`ChatWidget.insert_smiley`). With the `unicode`
emoticon-theme option the button instead emits `emoji_picker_requested` and
`MainWindow._on_emoji_picker_requested` opens the reaction picker
(`EmojiPickerDialog`) anchored above it. The Whiteboard button (`whiteboard.svg`,
`ChatWidget.whiteboard_requested` → `ChatWindow` → `MainWindow.
_on_whiteboard_requested`, also reachable from the roster contact/conference
context menu's «Открыть доску» right after the «Звонок» submenu) opens
`ui/whiteboard_dialog.py::WhiteboardDialog`
(non-modal, singleton per conversation): a custom `QPainter` canvas
(`ui/whiteboard_canvas.py::WhiteboardCanvas`; the logical board is `1280×720`
from `include.constants.WHITEBOARD_WIDTH/HEIGHT`, overridden by the shared
document's `viewBox` via `set_view_box`) with an icon-only tool palette
grouped by `QFrame` separators: the manipulation tools (select / move / rotate /
scale and «Удалить», an object operation) then, after a separator, the drawing
tools (pencil / line / **arrow** / rectangle / ellipse / rhombus / polygon, a **bucket**
«Заливка» that fills — or, on a second click, unfills — only the closed shape
under the cursor, and an **eraser** that removes the shape under the cursor on a
click and while dragging, plus a **text** tool: a click opens a multiline input
(`QInputDialog.getMultiLineText`) and the text is converted to vector glyph
outlines (`QPainterPath.addText` → `svg_path.path_to_d`) and stored as a plain
`<path d="…"/>` shape so it syncs/renders like any other, plus an **insert
image** button (`wb-image.svg`) that reads a PNG/JPEG/GIF/BMP/WebP file and
places an `<image>` shape at the view centre — in a shared session whose peer
advertises `urn:xmpp:http:upload:0` the image is uploaded (XEP-0363,
`client.upload_http_media`) and referenced by URL, otherwise it is embedded as a
`data:` URI (`image_data_uri`, a 2 MB/format limit); `chat.whiteboard_image_upload`
(`auto`/`embed`, Preferences → Chat → «Конференции») forces the inline form for
compatibility with the minimal profile; an uploaded URL is fetched
off the UI thread by `WhiteboardCanvas._ImageFetcher` (bounded, cached) and the
bytes we just uploaded seed the cache so our own copy renders at once; the shape
exports as `<image xlink:href="…"/>` and syncs like any other object); then the line width
(a menu whose actions are checkable, the active width ticked), line colour, fill
colour and a «Заливка» toggle (whether newly drawn closed shapes are filled);
a **stacking-order** menu (`wb-order.svg`, next to undo/redo: «На передний
план»/«Вперёд»/«Назад»/«На задний план» → `WhiteboardManager.reorder`, which
renumbers the drawable siblings' `primary-weight`; a local board reorders the
canvas list directly) and a **group/ungroup** pair
(`wb-group.svg`/`wb-ungroup.svg`, enabled when 2+ shapes / a grouped shape are
selected — Ctrl+click adds to the selection) → `WhiteboardManager.group_shapes`
(a `<g/>` + reparenting) / `ungroup` (composes the group's `transform` into the
children via `include/svg_transform.py`, reparents them back and removes the
group); a grouped shape is selected as a whole (outlined in green,
`WhiteboardCanvas._group_world_bbox`) and its drag moves the group's `transform`
(`set_group_transform`), a local board grouping the canvas list directly; then
the board
operations «Очистить» (removes the drawable children, the document metadata
stays), «Сохранить как SVG», «Сохранить как PNG», «Размер холста»
(`wb-resize.svg` → a preset picker (`_canvas_size_items`, 600×400 … 1920×1080,
the current size preselected) → `WhiteboardManager.set_view_box`, the `viewBox`
op) and
«Поделиться снимком» (renders the board to a temp PNG, then opens the
`ShareDialog` — with the source conversation preselected — and only on
«Отправить» uploads it via `JabberClient.upload_http_media` — HTTP
Upload/XEP-0363 — which returns the full XEP-0385 media dict, and shares the
link **with SIMS metadata** to the chosen targets; cancelling removes the temp
file); then «Поделиться доской» and «Завершить сеанс». An arrow is serialised as one
path — a shaft plus an **open (V) head** (`WhiteboardCanvas._arrow_d`), so it
renders identically locally and for a remote peer. The document is a list of
shape records (`id`, `rid`, `kind` — `path` or `image` — geometry,
`stroke`/`stroke-width`/`fill`/`fill-opacity`/`stroke-linecap`/
`stroke-linejoin`/`fill-rule` and a `QTransform`; a fill with
`fill-opacity="0"` is no fill — Psi+ sends a transparent fill for an outline).
The stroke cap/join and the fill rule are read from the records (an absent
attribute means the SVG default: `butt`/`miter`/`nonzero`) while our own shapes
are emitted and exported with `round`/`round`/`evenodd` (the board's look), so
both clients render them the same way; a vector shape is exported as
a `<path d="…"/>` (`include/svg_path.py`), an image as
`<image x/y/width/height/xlink:href/>`; `to_svg()`/`save_svg()`/`render_image()`/
`save_png()` serialise the document (the PNG is a board render, shapes only on
white). On receive, the basic SVG shapes a peer may send instead of a `<path/>`
(`rect`, `ellipse`, `circle`, `line`, `polyline`, `polygon` — Psi draws them)
are converted to path data by `include/svg_shapes.py::element_d`
(`WhiteboardManager._collect_shapes`); an unknown element is logged instead of
silently dropped. In the
**select** tool a click selects a shape and shows rotate/resize handles plus a
**move** marker below the box (`wb-move.svg`) so even a tiny shape is easy to
drag (dragging the shape body or the move marker moves it; the handles
rotate/scale it about the centre — the move/rotate/scale tools remain as an
alternative); `Delete`/`Backspace`
removes the selection; `Ctrl+wheel` zooms the view anchored at the cursor,
`Ctrl+0` and a double click on empty space reset it, and the view pans by
dragging empty space in the select tool **or** by dragging with the middle mouse
button in any tool (the view transform is local, never part of the document).
The «Заливка» toggle uses its own bucket-plus-check icon
(`wb-fill-toggle.svg`), distinct from the bucket tool. `Esc` only
clears the selection (it never closes the board) and closing the window
**hides** it — the board and its session live in `MainWindow._whiteboards`
until «Завершить сеанс» (confirm → end session → clear → hide) or logout
(`_reset_account_ui`), so a reopened window continues the drawing.
The dialog's «Поделиться доской» button starts a **collaborative** session
(`xmpp/whiteboard.py::WhiteboardManager`, `client.whiteboard`): a Jingle
application type `urn:xmpp:jingle:apps:svg-whiteboard:0` over the SXE transport
(`urn:xmpp:jingle:transports:sxe`) sharing an `xmpp/sxe.py::SxeDocument`
(XEP-0284 record model). For 1:1 the initiator is the host; for MUC the room JID
is the host and the SXE payloads are `groupchat` messages. Every document uses a
**fixed default root record id** (`whiteboard.WHITEBOARD_ROOT_RID`, `"0"` — the
value the specification's examples use), so an incremental
`<new parent="…"/>` edit refers to a record every peer already has — no snapshot
is needed first; a foreign host's own root RID is **adopted** from the snapshot
(`SxeDocument._adopt_root`, XEP-0284 §10.3, re-parenting the local top-level
records), so interop does not depend on the id. The canvas `viewBox` is read from
the document (`WhiteboardManager.view_box` → `WhiteboardCanvas.set_view_box`), the
host's being authoritative; `document-begin`'s `prolog` carries the XML prolog
plus the SVG DOCTYPE (`whiteboard.DOC_PROLOG`); the client advertises the
`collaboration`/`sxe` disco identity, and a refused invite
(`WhiteboardManager.refuse_session`) is a `session-terminate` with the
`<unsupported-applications/>` reason. A MUC session id is **derived from the room JID**
(`WhiteboardManager._muc_sid`), so all participants converge on one shared
document (a random per-participant sid gave each its own session and nothing
synced); `start_session` reuses an existing room session. A `document-begin`
snapshot is **merged**, not applied as a replace (`_apply_state` adopts the root
RID and unions the drawable records), so a late joiner gains the existing
shapes without the active peers losing theirs. The session lifecycle is surfaced
as a **chat status line** («Начата сессия рисования» / «Сессия рисования
завершена») gated by `chat.whiteboard_show_status` (default on): the manager
emits `whiteboard_activity(peer, active)` once per activity span
(`_active_peers`) from `start_session`/`_on_state_offer`/`session-initiate`
(start) and `end_session`/`session-terminate` (end). A MUC board **broadcasts a
`<close/>`** on `end_session` (a client extension, since a MUC board has no
Jingle session), but it means **"this participant left"**, not "the board is
over": a received `<close/>` keeps the session and the document, drops only the
sender from `session.participants` and emits `whiteboard_edit` (so the others
keep drawing with each other). Our own leave starts a 60 s grace
(`_left_rooms`) during which the room's SXE/presence is ignored (the continuing
board does not immediately re-invite us); an explicit `start_session`/`join_session`
clears it. A passive occupant (or a late room joiner, via the XEP-0284 §4.2
presence `<sxe>` advertisement — `JabberClient._on_sxe_presence` →
`handle_sxe_presence`) learns of a board from any incoming SXE and gets the start
line. Known limitation: the state snapshot is offered by the board's host, so a
**late** joiner after the host left may not receive it (the already-joined
clients keep drawing). **Undo/redo** (buttons
after «Удалить», `Ctrl+Z`/`Ctrl+Shift+Z`) is a **shared** history: every document
operation — own (`add_shape`/`update_shape`/`remove_shape`) or remote
(`_apply_state` incremental edits; a join snapshot is not recorded) — pushes a
patch of forward + inverse `<new>`/`<set>`/`<remove>` edits onto a per-session
stack (`WhiteboardManager._undo`/`_redo`, capped at 100); `undo`/`redo` apply the
inverse/forward to the document, **broadcast** it and emit `whiteboard_state`, so
the last move/rotate/scale/fill/add/delete is reverted for everyone; a new
operation clears the redo stack. A **local (unshared)** board has its own
undo/redo in `WhiteboardCanvas` (`_undo_stack`/`_redo_stack`, snapshots of the
shapes + group transforms via `push_history`, capped at 50; the dialog routes to
it when there is no session and clears it on attach/detach), so the undo/redo
buttons work on a plain board too; a drag pushes one snapshot
(`_push_transform_history`). Bodyless `<sxe>`
messages are routed by `JabberClient._on_sxe_stanza` (a dedicated `MatchXPath`
handler), Jingle IQs by `_dispatch_jingle_iq` (`is_whiteboard_jingle`), and the
features are advertised in disco. A 1:1 `session-initiate` is addressed to the
peer's **best full JID** (`WhiteboardManager._best_full_jid`: a resource whose
XEP-0115 caps announce the whiteboard/SXE, else the best available resource) —
a bare-JID Jingle IQ is rejected by the server (`service-unavailable`), so with
no known resource the share fails fast and `whiteboard_failed(sid, "unavailable")`
is emitted (the dialog and an OSD report it; `MainWindow._on_whiteboard_share`
also warns — without blocking — when the peer's caps do not announce the
feature). When the peer advertises `urn:xmpp:jingle-message:0` the share is
announced with XEP-0353 propose/proceed before the `session-initiate` (the
shared `xmpp/jmi.py` helper; `_propose_and_initiate` waits for a proceed, a
reject/retract emits `whiteboard_failed(sid, "rejected")`); an incoming
whiteboard proposal is routed by `JabberClient._on_jingle_message_stanza` (by the
`<description/>` namespace, or by `WhiteboardManager.owns_jmi(sid)` for a
response) and surfaced as `whiteboard_proposed`, answered via
`client.answer_proposal(..., kind="whiteboard")` (a proceed makes the following
`session-initiate` auto-join). `_dispatch_jingle_iq` **ignores error replies** (an error echoes the
original `<jingle action>` and must never be routed as an incoming action — that
produced a bogus invite) but routes an error for a known session to
`WhiteboardManager.handle_error` → `whiteboard_failed(sid, condition)`; sharing a
board in a chat with our **own** JID is kept local-only (`start_session` never
sends an invite).
Local canvas edits (`shape_added`/`shape_updated`/`shape_removed`) become
`add_shape`/`update_shape`/`remove_shape`; remote state (`whiteboard_state`)
rebuilds the canvas (`WhiteboardCanvas.load_shapes`); an incoming
`session-initiate` (`whiteboard_invite`) asks the user to join. An accepted
invitation reaches the session through the XEP-0353 propose/proceed path (the
`session-initiate` auto-joins), so `MainWindow._on_whiteboard_ready` opens the
board (`show`/`raise_`/`activateWindow`) instead of leaving the user to open it.
A **conference** board started by another occupant is never joined silently:
the presence advertisement (`<sxe session=…/>`, tracked as the room's session),
a groupchat `<connect/>`/`<state>` or an unsolicited `state-offer` emits
`whiteboard_invite(sid, room, True)` once (`WhiteboardSession.invited`), and
`_on_state_offer` refuses to accept the state until the user agrees
(`user_joined`). Declining (`whiteboard.decline_session`) keeps the session and
sends `refuse-state`, so the toolbar button and the roster's «Открыть доску»
can join it later (`session_for_peer` + `join_session`); the dialog is created
**without a parent** (a top-level window with its own taskbar entry) and is
placed near the main window. The board lists **who is drawing** in a
toggleable **sidebar** (`wb-participants.svg`, right of the canvas, hidden by
default and never persisted; the sidebar and the canvas share a `QSplitter`, so
its width is adjustable per session), ourselves first: `WhiteboardSession.participants`
records every inbound sender (`room/nick` or full JID) and emits
`whiteboard_edit(sid, frm)`, which `MainWindow` turns into rows with the MUC nick
or the roster name and an avatar (the `_muc_users` avatar, the real JID's cache,
`avatar_path(bare)` for 1:1, else the placeholder) plus a ~2 s row highlight of
the participant who edited last (the row paints a palette-highlight background,
`WA_StyledBackground`). The editor key is matched by bare JID, so 1:1 highlights
work too; an unchanged participant set only refreshes the highlight (the rows are
not recreated on every SXE edit) and a plain `whiteboard_state` refresh keeps it
(`set_participants(..., active=None)`; only the 2 s timer or an explicit empty
`active` clears it).
**Initial-state synchronization** follows XEP-0284 strictly: the accept echoes
the host named by the offered `<transport><host/>` (§4.2) and carries
`responder`, and the joiner sends `<connect/>` only after its `session-accept`
is acknowledged. A host offers the state only once its payload channel is ready
and silently drops a `connect` that arrives while it is still starting (Iris
starts accepted contents on the next event-loop turn), so
`WhiteboardManager._retry_connect` re-sends the request at 2/5/10 s until a
`state-offer` arrives. Until the snapshot (`<document-end>`) is applied the
joiner buffers its own edits (`WhiteboardSession.pending`, flushed in order once
`synced`) — a host ignores edits from an unsynchronized peer. A board drawn
**before** it is shared is not lost: `MainWindow._on_whiteboard_share` passes the
dialog's local shapes (canvas shapes without a document `rid`) and its size to
`start_session(shapes=…, view_box=…)`, so the host's document — and the snapshot
a joiner receives — already contains them; joining a peer's board merges them
instead (`WhiteboardManager.seed_local_shapes`, buffered until the snapshot,
then sent to the host). Ending a session clears the shapes' rids
(`WhiteboardCanvas.clear_rids`), so the same drawing becomes an ordinary local
board again and can be shared anew. A merged snapshot's root attributes replace
ours (`_adopt_snapshot_root_attrs`), so the host's `viewBox` is authoritative.
The SXE lifecycle
(`connect`/`state-offer`/`accept-state`/`state`) is logged as
`Whiteboard: SXE …` for diagnosis. The Jingle `senders` of the content are
honoured: `<content senders="none"/>` (a board switched off in Psi) freezes it,
so `WhiteboardManager.may_edit` gates every local edit and `_send_edits` drops
them; the accept echoes the offered value and a later `content-modify`
(`_apply_content_modify`) emits `whiteboard_senders(sid, editable)`, which
`MainWindow` forwards to `WhiteboardDialog.set_editable` (drawing tools and
object operations disabled, `WhiteboardCanvas.set_editable` ignores mouse/key
edits while pan/zoom keep working).
[`tests/test_whiteboard.py`, `tests/test_whiteboard_sync.py`,
`tests/test_jingle_error_router.py`, `tests/test_sxe.py`, `tests/test_svg_path.py`,
`tests/test_svg_transform.py`]
The "Send" control is a vertical
icon-only button (an Enter-style arrow) whose height follows the input field.
The input is vertically
resizable
(`chat.input_height`, persisted; the `_InputHandle` drag bar sits on the
input's top edge just below the toolbar — dragging up grows the field, down
shrinks it — and reads the stored height through a `get_height` callable
because a layout reparents it away from
`ChatWidget`) and files can be dropped straight into the chat (the view and the
input disable `acceptDrops` so file drops reach `ChatWidget`, which emits
`files_upload_requested(jid, [paths], method)`). Dropped/picked files open
`ui/upload_dialog.FileTransferDialog`: one row per file with an image
thumbnail or generic file icon, a per-file `QProgressBar` and one shared
caption (`QLineEdit`); each row also shows live transfer stats — transferred /
total, speed (EMA) and ETA (`format_speed`/`format_eta`) and the average speed
when finished. OK starts the transfers while the dialog stays open,
`file_upload_progress` events (phases `start`/`progress`/`done`/`error`, now
carrying the file `path`) update the bars. The dialog is parented to the
window that issued the request (`_place_dialog_over` centers it over the chat
window or the roster), and the caption is sent once — as a separate message —
after the batch finishes (`_send_caption_after`). File URLs and the caption are
rendered as real outgoing messages with clickable links: in 1:1 the client
displays them locally via `_display_local_outgoing` with the **sent** stanza id
and the media dict (`JabberClient.take_upload_result`), so an XEP-0184 receipt
matches the local row and the media card is rendered like any other media (no carbons echo reaches
the sending resource), in MUC the room echo renders them.
`client.upload_http(jid, path)` discovers the `urn:xmpp:http:upload:0` service
(cached), requests a `<slot>` and PUTs the bytes streamed in 64 KiB chunks via
`http.client` (Content-Length + `conn.send`), reporting the progress fraction
through a shared `_UploadProgress` object polled by the flow coroutine. The
roster context menu additionally offers "Send file → P2P / P2P IBB / HTTP
Upload".

**P2P file transfer** (`xmpp/jingle.py`, `xmpp/bytestream.py`,
`ui/incoming_file_dialog.py`): slixmpp has no Jingle core plugin, so the
XEP-0166 signalling and the two transports are implemented directly on the
slixmpp stanza objects. `JingleFileTransferManager` (`client.file_transfer`)
owns sessions keyed by the Jingle `sid` and is driven by four stanza handlers
registered via `MatchXPath("{jabber:client}iq/…")`: `…/{urn:xmpp:jingle:1}jingle`,
`…/{http://jabber.org/protocol/ibb}open`, `…close` and `…data`. A file offer
builds a XEP-0234 `<description>` (`<file>` with name/size/media-type/date and a
SHA-1 `<hash>` in `urn:xmpp:hashes:2`) plus a transport. The `"P2P"` menu uses
**Jingle SOCKS5 (XEP-0260)**: every candidate list contains our `direct`
listener candidates (`bytestream.listen_for_bytestream`, priority 126) and the
configured file proxy as a `proxy` candidate (priority 10); the initiator dials
the peer candidates in priority order (`bytestream.connect_bytestream`, the
SOCKS5 `DST.ADDR = SHA1(SID + initiator + responder)` calculated with port 0),
sends `candidate-used`, activates a nominated proxy candidate and streams the
file. **Encryption (XEP-0391/0396, `xmpp/jet.py`)**: when `files.encryption`
(`off`/`prefer`/`require`/`strict`) allows it and the peer advertises
`urn:xmpp:jingle:jet:0` + `urn:xmpp:jingle:jet-omemo:0`, the content carries
`<security/>` with a legacy OMEMO KeyTransportMessage (a per-device `<key/>`
header and `<iv/>`, no payload) holding the 16-byte transport key; the stream is
one AES-128-GCM stream with the tag appended (`StreamEncryptor`), and the
receiver decrypts with the CTR keystream plus a GCM tag check, keeping the file
as `<path>.part` until it verifies. `require`/`strict` refuse to send without a
key and answer `security-error` for an offer they cannot decrypt; `strict` also
terminates a plain offer. A refused offer emits `file_offer_rejected`; an
encrypted transfer shows a lock in the transfer/incoming dialogs and a chat
status line. `"P2P IBB"` uses **Jingle In-Band (XEP-0261/0047)** immediately;
`"P2P"`
falls back to IBB automatically when SOCKS5 fails by sending a
`transport-replace` and continuing as IBB. `client.send_file_p2p(jid, path,
method)` is serialized by a lock so a batch runs one session at a time.
Progress/done/error are emitted as `file_transfer_progress(jid, phase, detail,
path, direction)` and reused `FileTransferDialog` rows. Incoming offers are
emitted as `file_offer(offer_id, from, meta)`; `MainWindow._on_file_offer`
auto-accepts (saving into `files.download_dir`, unique name) when
`files.auto_accept` is on, otherwise shows `IncomingFileDialog` (confirm →
`QFileDialog.getSaveFileName`) and answers via `client.answer_file_offer`. When
an HTTP Upload slot is rejected for size (`file-too-large` /
`resource-constraint` / `not-acceptable`), `_http_upload_flow` emits
`http_upload_oversize(jid, path)` and MainWindow retries that file over P2P.

**User avatars (XEP-0084 / XEP-0153 / XEP-0398)** (`core/client.py`,
`include/avatars.py`): avatar files live in
`$XDG_CACHE_HOME/stanza-im/avatars/`; the name is the sanitized JID key
(`room/nick` for an occupant, else the bare JID) and, when the key contains
anything outside `[A-Za-z0-9_.@-]` (a Cyrillic nick, a Unicode localpart), a
short SHA-1 suffix is appended (`…______-ed48fde817.png`) so two non-Latin
nicks of the same length never share one cached file. A path from the older
naming scheme (e.g. a vCard cache entry) is copied to the current name by
`include.avatars.ensure_avatar` when it is applied
(`MainWindow._refresh_avatar`), so the sidebar and the chat agree on the file. `xep_0153` advertises our vCard avatar hash in presence
(`<x xmlns='vcard-temp:x:update'><photo>sha1</photo></x>`); its
`vcard_avatar_update` event makes `_on_vcard_avatar_update` refetch a contact's
vCard (`get_vcard(bare, force=True)`) when the hash changes. `xep_0084`
publishes our avatar to the PEP `avatar:data`/`avatar:metadata` nodes
(`_publish_own_avatar_async`, type and dimensions from
`include/avatars.image_mime`/`image_size`) whenever `set_own_vcard` stores a
PHOTO, and registers the `avatar:metadata` interest; incoming metadata events
(routed through `_maybe_pep_event`, and the `avatar:metadata` node is also
requested by `_ensure_pep_subscription`) fetch the image via `_retrieve_avatar`.
XEP-0398 bridges the two: both paths funnel into `_apply_avatar(jid, raw)`,
keyed by the SHA-1 of the image (unchanged avatars are skipped), which saves it
and emits `avatar_updated(jid, path)`; `MainWindow._on_avatar_updated` reuses
`_refresh_avatar` (the avatar-only part of `_on_vcard_received`) for the roster,
contacts and MUC occupants (it also invalidates the cached icon and the roster's
scaled pixmaps, since an avatar file keeps its name when it changes). The chat threads render the sender avatar via
`ChatWidget._user_icon` (for a MUC it prefers the participant's `avatar_path`
from the sidebar, then falls back to the JID-keyed file; a participant whose
cached avatar appears after the history was rendered gets that sender's messages
repainted by `update_muc_users`): incoming from the sender's cached avatar, outgoing from
**our own** — `ChatWindow.set_own_jid` (the bare JID, set by `MainWindow` after
login) feeds `avatar_data_uri(own)`, and our own vCard avatar is cached under the
bare JID (not the full one); `MainWindow._own_avatar_uri` pre-resolves it from
the contact's cached `avatar_path` first, so an older full-JID cache entry still
renders; `ChatWindow.refresh_avatars` updates both incoming
and outgoing `<img class="avatar">` elements in place when an avatar arrives.
Message avatars follow `appearance.avatar_radius` too: `_user_icon` clips the
data URI (`_rounded_avatar_uri`, cached by `(uri, radius)`; the source format is
auto-detected, so a JPEG/GIF/WebP vCard photo is rounded like a PNG and
re-encoded as PNG). The page also carries a CSS fallback
(`img.avatar { border-radius: …% }`, injected by `ChatView.set_avatar_radius`;
`avatar_css_radius` uses **half** the setting, since CSS percentages are
relative to the whole box while `rounded_avatar` uses the half-size) so an
image Qt cannot decode (e.g. an animated WebP) is still rounded like the rest,
and
`ChatWindow.set_avatar_radius` applies it to every open tab (the QTextBrowser
fallback gets the same clipped data URIs, since it has no CSS border-radius). A
PEP event is attributed to the XEP-0033
`<addresses><address type='replyto'/>` JID when present (`_replyto_address`), so
a server that relays it from a service JID still resolves the real sender; an
expected fetch failure (`IqError`/timeout, e.g. `item-not-found` for a stale
node) is logged briefly without a traceback and remembered in `_avatar_failed`
for the session. [`tests/test_avatars.py`]

**Extended presence (XEP-0080/0107/0108/0118)** (`include/pep.py`,
`core/client.py`): the four PEP nodes (`geoloc`, `mood`, `activity`, `tune`)
are advertised with `+notify` in disco. PEP notifications are bodyless
`<message type='headline'><event xmlns='http://jabber.org/protocol/pubsub#event'>`
stanzas, so slixmpp's `message` event (which requires a `<body>`) never delivers
them; a dedicated stanza handler ("PEP Event", `MatchXPath("{jabber:client}message/…{http://jabber.org/protocol/pubsub#event}event")`
registered in `_register_jingle_handlers`) routes them to
`JabberClient._maybe_pep_event` (alongside `_maybe_mds_event` for XEP-0490) into
`client.pep_data[bare_jid][kind]` and re-emits them as
`contact_pep_updated(jid, kind, data)`; `client.fetch_pep(bare)` pulls the
current nodes with `pubsub/items max_items=1` (called when a profile opens and
on presence via `JabberClient._maybe_refresh_pep` — the presence-driven pull
does not depend on the server pushing XEP-0163 notifications, and is bounded
per bare JID by an in-flight guard plus a 15 s cooldown
(`time.monotonic`-based `_pep_last_refresh`), so a burst of online presences
collapses to one fetch).
Contacts the server can push to are also **subscribed** to the four nodes
(XEP-0163) on presence/roster add (`JabberClient._ensure_pep_subscription`,
best-effort via `xep_0060.subscribe`, in-flight guard, 300 s retry cooldown on
failure), re-subscribed on every `session_started`/`stream_resumed` (servers
drop subscriptions on session end) and unsubscribed on roster removal
(`_unsubscribe_pep`); a terminal subscription state (e.g. `pending`, error)
counts as a failure. As a fallback for servers that never forward PEP
events, an optional periodic sweep polls online contacts' nodes every
`connection.pep_sweep_interval` seconds (`0` = off, the default; Preferences →
Connection → «Периодический опрос активности PEP» is a selector with
Off/30 s/1 min/2 min/5 min) via the same `_maybe_refresh_pep`
guards; the sweep is paused while the user is idle
(`client.set_pep_sweep_paused`, driven by `MainWindow._sync_pep_sweep_pause`
alongside the auto-status inactivity timer) and stopped on disconnect.
`include/pep.py` builds/parses the payloads, parses the bundled Jabbim icon
packs (`resources/moods|activities/<pack>/*.cfg`, `"key"=File.png`) and
formats a human summary (`format_summary`). The roster bottom bar gains two
icon-only `QToolButton`s right of the status combo: a smiley with a menu
("Mood" + nested "Activity" groups/subs, icons from the packs, plus a "None"
clear entry) that calls `client.publish_mood`/`publish_activity` and persists
to `status.mood` / `status.activity` (republished on `session_started` via
`MainWindow._republish_pep`); the menu's actions are checkable and
`_sync_pep_checks` (on `aboutToShow`) marks the currently active mood/activity,
including the first-level activity group entries (`submenu.menuAction()`), like
the tray status menu. An `edit.png` button opens
`ui/status_message_dialog.StatusMessageDialog` (multiline, preloaded from
`status.message`) whose result is sent with presence (`MainWindow._send_presence`).
Contacts' mood/activity/tune/location are shown in the roster tooltip
(`_roster_tooltip`) and on the vCard "Status" tab (`mood`/`activity`/`tune`/
`location` fields, updated live through `_on_contact_pep_updated`). Both also
show the roster subscription state (`client.subscription(bare)` →
`privacy_sub_none/to/from/both`, the tooltip under the JID and the vCard
`subscription` field). For an **offline** 1:1 contact the Status tab also shows
its last activity (XEP-0012): `MainWindow._request_last_activity` queries
`client.get_last_activity(bare)` (raw `jabber:iq:last`) and merges
`last_seen` (absolute `YYYY-MM-DD HH:MM` of `now − seconds`) and `last_status`
(the `<query>` text) into the dialog.

**A/V calls & Muji** (`xmpp/jingle_rtp.py`, `xmpp/media.py`,
`xmpp/muji.py`, `ui/call_window.py`): 1:1 audio/video calls use Jingle RTP
(XEP-0167) over ICE-UDP (XEP-0176) with DTLS-SRTP. `JingleRtpManager`
(`client.rtp_calls`) shares the single Jingle IQ router with the file-transfer
manager (`_dispatch_jingle_iq` routes by RTP/ICE content or known `sid`), builds
the RTP `<description>`/ICE `<transport>`/DTLS `<fingerprint>` elements and
converts them to/from an SDP offer/answer that `aiortc` understands
(`sdp_from_jingle`/`jingle_contents_from_sdp`); aiortc provides the actual
 ICE/DTLS/SRTP/RTP path. Candidates are sent in `session-initiate`/`accept` and
trickled via `transport-info`. The SDP↔Jingle bridge preserves the attributes
libwebrtc needs to leave its *connecting* state: `rtcp-mux` (always advertised
in our `<description>`), codec fmtp `<parameter>`, `<rtcp-fb>` (XEP-0293),
`<rtp-hdrext>` (XEP-0294), `<source>`/`<ssrc-group>`/`msid` (XEP-0339) and the
content `senders` direction; a BUNDLE `<group>` (XEP-0166 grouping) ties the
contents to one transport and the peer's `<trickle/>`/`<renomination/>`
transport options are echoed.
When the peer advertises `urn:xmpp:jingle-message:0`
the call is announced with XEP-0353 propose/proceed before `session-initiate`.
Per XEP-0353 the `propose` rings the peer's resources while the responses
(`proceed`/`reject`/`retract`) and the `session-initiate` go to the **full**
JID of the resource that accepted (the `proceed` sender). When the peer has
JMI-capable resources, the propose is sent to **each of their full JIDs**
(`_jmi_resources`, RTP-capable first) with
`<private xmlns='urn:xmpp:carbons:2'/>` + `<no-copy xmlns='urn:xmpp:hints'/>`
(XEP-0280 §9): the recipient's server then does not carbon-copy it to the
account's other resources, so a non-JMI desktop (Psi+) never sees — and never
rejects — a proposal meant for a phone. Both phones ring; the first `proceed`
wins and its carbon stops the other. Without a JMI resource the propose falls
back to the **bare** JID (server forking). A `<reject><busy/></reject>` from a
resource whose caps lack `urn:xmpp:jingle-message:0` is still **ignored** while
another resource of that account advertises JMI (a defence for forking
servers). The initial `peer_full` fallback is the best JMI-capable resource
(`_best_jmi_resource`), not the highest-priority resource — a peer with
several resources must not receive the Jingle IQ on a non-call resource.
Bodyless `<message>` stanzas (propose/retract, XEP-0482 call invites and
XEP-0249 MUC invitations) never reach
the core `message` event — slixmpp registers its IM handler as
`message/body` — so they have dedicated `MatchXPath` handlers
(`_on_jingle_message_stanza`/`_on_call_invite_stanza`/`_on_muc_invite_stanza`). Incoming proposals are
answered via `client.answer_proposal(sid, accept)` (sends `proceed`/`reject`);
the proposed media kind (`_propose_media`) is read from **all** `<description>`
elements (video wins; nested or not), and the session-initiate that follows a
`proceed` is auto-accepted.
`client.supports_calls(bare, video)` gates the UI on the peer's XEP-0115 caps
(`jingle:1 + ice-udp:1 + rtp:1 + dtls:0 + rtp:audio [+ rtp:video]`, fetched
per presence via `_load_caps`). Because slixmpp caches caps by the verification
string alone, a peer that shares our caps node (a second instance of this
client) can inherit our own cached feature set; when the resolved features lack
a call feature the resource is verified with a **live `disco#info`**
(`_load_caps_from_disco`, unioned in, once per resource via `_caps_verified`,
also reachable from `ensure_caps`). `JabberClient.__init__` also recomputes our
own caps (`update_caps`) after the full disco is registered. STUN/TURN come from `client.ice_servers()`
(XEP-0215 `urn:xmpp:extdisco:2` → the connection settings' STUN/TURN endpoint →
SRV discovery). The «Звонок» call menu is a submenu in the roster contact
context menu and an icon-only button in the chat toolbar (both enabled only for
capable contacts). Because `set_call_support` is otherwise driven by the
`contact_caps` event (which never fires again once the caps were resolved
before the tab opened), `MainWindow._apply_call_support(jid)` re-applies it from
the current caps whenever a 1:1 tab opens. For a **conference** contact the roster «Звонок» submenu
instead starts a Muji call (`_join_muji`, enabled only when
`client.rtp_calls.available`), while the 1:1 Jingle call is offered for
non-conference contacts. The toolbar button on a **MUC** tab instead starts a Muji
conference call: `ChatWidget._call_btn`'s Audio/Video menu actions emit
`muji_call_requested(room, video)` (never `call_requested`), which
`ChatWindow.open_groupchat` forwards and `MainWindow._on_muji_call_requested`
routes to `_join_muji`. The MUC button is gated solely on aiortc availability
(`set_muji_support` via `MainWindow._apply_muji_support`, called on every path
that opens a MUC tab — manual join, server auto-join in `_on_muc_joined`, roster
open in `_on_contact_open` — so an auto-joined room's button is never left
disabled) and is a no-op on 1:1 tabs. While a conference is live the same
button doubles as its indicator: `MainWindow._sync_muji_indicator(room)`
(lit while anyone in the room — ourselves or other participants — has an
active conference, so it stays lit after we leave as long as the room's
conference continues; also called from `_on_muji_updated`/`_on_muji_left`)
→ `ChatWindow.set_muji_active(room, active, video)` → `ChatWidget.set_muji_active`,
which swaps the idle `call` icon + `muji_button` tooltip for the `call-accept`
glyph and an audio/video-aware tooltip (`muji_active_audio`/`muji_active_video`
per the conference contents), and restores the idle look when the last
participant leaves. The A/V menu actions carry `mic.svg`/`camera.svg` icons.
The MUC chat reports the conference lifecycle as status lines (gated by `chat.muc_show_status`),
kind-aware to the conference's media:
`MujiManager` emits `muji_started(room, video)` once the media contents are
confirmed — our own join (`_finalise_join`) or a peer advertising real
contents in presence, peer-started calls included — so a preparing-only
presence or a session placeholder never locks in a wrong audio kind;
`_on_muji_started` writes `muji_started_audio`/`muji_started_video`. `muji_ended(room, video)`
is emitted when the last participant leaves (`MujiManager` drops the room record and
emits it → `_on_muji_ended` writes `muji_ended_audio`/`muji_ended_video`).
The start is reported once per conference lifetime (`_started` guard,
cleared when the room record drops) and the kind-aware texts read «Начата
аудио/видеоконференция» / «Аудио/видеоконференция завершена».
`ui/call_window.CallWindow` shows the active call and
`IncomingCallDialog` prompts for incoming offers; both are **separate
top-level windows** (never children of the main window, which would embed them
over the roster); both label the peer with its **roster name**
(`MainWindow._call_display_name`, the bare JID when unknown — the client's
`call_incoming`/`call_proposed` events carry the full JID with the resource).
The call state follows the media connection, not the SDP accept: `ringing`
(«Звоним…») → `connecting` («Соединение…», emitted on `session-accept`, by the
caller and the answerer) → `active` («Соединение установлено») only when the
peer connection reports `connected`; a `failed` media connection ends the call
with `connectivity-error`. The capture window opens on `connecting`, so it is
not shown as an established call while ICE/DTLS is still negotiating. The
incoming prompt puts Reject at the left edge and Accept at the right, a
stretch between them. The incoming prompt and an **audio** call window show the
peer's avatar (or the default placeholder, `MainWindow._call_avatar`) centered,
with the name and the call message below it (a video call shows the video
surface instead).
Remote video frames are painted by `VideoView`, which draws a
translucent nickname caption over the image. Every call control is **icon-only**
(tooltips instead of labels) using the 16px glyphs in
`resources/images/16x16/actions/` via `call_window._icon`: `mic`/`mic-off`,
`camera`/`camera-off` (the camera is a webcam glyph), `speaker`/`speaker-off`,
a red `call-hangup`, a green `call-accept` and a **quality** button
(`quality.svg`, a small bars glyph). Its menu changes the outgoing video
**bitrate** (200/500/1000 kbps) and **resolution** (source/1080/720/480/360) of
a live call (in Muji — of every session of the room):
`MainWindow._on_call_quality_requested`/`_on_muji_quality_requested` →
`rtp_calls.set_call_video_quality` → the engine call's `set_video_bitrate`
(updates the live encoders through the weak registry; aiortc recreates its
codec with a keyframe on the next frame) and `set_video_quality`
(`_VideoCaptureTrack.set_max_height`/`set_screen_box`, downscale only). The
choice is session-only (defaults come from the Calls preferences); the codec
cannot change during a call (that needs renegotiation) and audio is only
changed in the settings. An **info** button (`info.svg`) is a toggle: it shows
one compact line under the header — the outgoing and incoming codec and
resolution plus the target and measured bitrates (an audio call shows just the
codec and bitrate) — and refreshes it once a second while visible (the call/
duration timer drives it, so nothing is rebuilt and the line never disappears).
The codecs come from the negotiated answer SDP (`media.sdp_media_codecs`), the
outgoing size from the capture track and the incoming size from the decoded
remote frame; the actual rates are sampled every 2 s from the sender/transport
octet counters (`AiortcCall.sample_stats`). aiortc has no per-stream received
bytes, so the incoming figure is the transport total. The 1:1 window's header
is a single row — bold nick + gray `(state)` on the left and the session
duration on the right — so the video gets the space the old three rows used;
the `VideoView` caption keeps the nick over the video. A Muji room shows the
same toggle line under its title (first session plus the session count). A peer that missed the initial keyframe (a green
picture until the local video was toggled) is recovered by
`request_video_keyframe`: the VP8/H264 encoder shim forces the next frame to be
an I-frame (`_stanza_keyframe`, requested when the media connection becomes
`connected`, after a source/resolution change and once the first real video
frame is sent). The capture track keeps the last real frame size for its black
frames and retries a failed camera open every 2 s. The mute/camera buttons toggle
the **outgoing** capture — the muted
microphone sends silence and the switched-off camera sends black frames
(`set_audio_enabled`/`set_video_enabled`, no renegotiation, tracks stay
attached), while received audio/video keeps playing and the remote view is
never hidden. A `speaker`/`speaker-off` button mutes the **remote** audio
(`receive_toggled` → `rtp_calls.set_call_audio_receive`, the same knob Muji uses
per participant). One **video-mode combo** button (its icon reflects the active
source) offers «Без видео» / «Камера» / «Область экрана» / «Весь экран»
(`video_mode_requested(sid_or_room, mode)` →
`MainWindow._on_video_mode_requested`): «Без видео» disables the track (black
frames), «Камера» restores the camera, the two screen modes call
`rtp_calls.set_screen_share(key, "screen", region)` («Весь экран» = the monitor
under the cursor). In Muji the combo gates the whole room (`_all_cam`); the
per-party camera toggles remain a second layer. A region is picked in
`ui/screen_region_dialog.py::ScreenRegionDialog` — an **opaque** full-virtual-
desktop overlay that paints a snapshot of the screen (dimmed outside the
selection, bright inside) so it stays visible without a compositor; drag a
rectangle, `Esc`/right click cancels, clamped to the monitor under its top-left
corner. `media._VideoCaptureTrack` switches its source
live (`set_source("screen", region)`) — the camera opens lazily, the screen is
grabbed with `QScreen.grabWindow` on the GUI thread, throttled to
`devices.screen_share_fps` (default 5) and **downscaled only** to fit the
`devices.screen_share_max_width`×`screen_share_max_height` box (default
1920×1080; `0` = no limit on that side) — a smaller region is sent unchanged,
there is no upscale — with no renegotiation; the shared `include/screen.py` (`grab_region`/`grab_screen`,
also used by the OSD) handles the DPR and the "region grab ignores the position"
fallback. Wayland warns (grabs are usually blocked). `MujiCallWindow` switches
every session of the room. [`tests/test_screen_share.py`]
A duration counter (`format_duration`: `MM:SS`, `HH:MM:SS`
past an hour) runs from the call becoming active — the media connection, not
the session-accept (`CallWindow.start_duration`, stopped on the end) — and from
the first `active` session of the room in Muji
(`MujiCallWindow.start_duration`). The
**«Звонки»** preferences section has three tabs: **«Устройства»**,
**«Кодеки»** and **«Экран»**. «Устройства» also lists the camera's supported modes
(`devices.camera_mode`, `media.camera_formats` from Qt Multimedia; the mode is
passed to PyAV's v4l2 input as `video_size`/`framerate`/`input_format` and a
failed mode falls back to the driver default). «Кодеки» carries the preferred audio/video codec
(`calls.audio_codec`/`video_codec`, applied via
`RTCRtpTransceiver.setCodecPreferences` before an offer/answer; «auto» keeps
aiortc's order), the audio and video bitrate (`calls.*_bitrate_kbps`, applied
by the encoder shim in `xmpp/media.py` to `OpusEncoder.codec.bit_rate` and
`Vp8/H264Encoder.target_bitrate`) and the outgoing camera resolution cap
(`calls.video_max_height`, applied by `_limit_video_frame`, downscale only).
«Экран» holds the screen-sharing box and frame rate. The **«Устройства»** tab
hosts
(`devices.audio_input/audio_output/video_input`, enumerated with Qt
Multimedia) plus the camera's supported modes
(`devices.camera_mode`, `media.camera_formats`; the mode is passed to PyAV's
v4l2 input as `video_size`/`framerate`/`input_format`, a failed mode falls back
to the driver default), and its **self-tests** (`ui/device_test.py`): a live
microphone peak meter, a speaker test tone and a camera preview window,
disabled while a call owns the devices. The camera preview is closed when the
settings dialog closes and as soon as a call starts (a 1 s monitor in the
Preferences dialog), and it releases `QCamera` on hide — a background preview
must never keep `/dev/video*` busy for a call. `_VideoCaptureTrack.stop()`
clears its container, and a failed `av.open` logs the real FFmpeg reason via
`decode_ffmpeg_error` (PyAV raises a `UnicodeDecodeError` for a localized
error such as "Устройство занято" instead of the `FFmpegError`). The self-test controls are icon-only
buttons on the same row as the device selector; the mic control toggles
(checkable) the meter, whose level bar sits on the same row. The mic meter and
the call's capture track read the `QAudioSource` stream directly
(`io.read()`/`readyRead`) and
never gate on the QIODevice's `bytesAvailable()` (it can report 0 while audio
is streaming, which froze the meter and turned calls one-way), so a live
PulseAudio capture always reaches the app. Capture/playback negotiate a
device-supported format (`isFormatSupported` → `preferredFormat`) and convert
to the encoder's s16/stereo/48 kHz 20 ms frames; frames that already match
bypass aiortc's `av.AudioResampler` (a compatibility shim wraps the aiortc
encoder classes — never the immutable PyAV type — to avoid an FFmpeg `EINVAL`
whose non-ASCII message some PyAV builds turn into a fatal `UnicodeDecodeError`,
killing the RTP sender). For the *controlled* ICE role,
`JingleRtpManager._nomination_fallback` waits 5 s for the peer's own
`USE-CANDIDATE` (Conversations, the Jingle initiator, never sends one, so ICE
would stay `checking` forever) and then switches aioice to controlling — with
the tie-breaker forced to its 64-bit maximum so we deterministically win any
RFC 8445 §7.3.1.1 role conflict (a compliant peer with a smaller tie-breaker
backs down instead of answering 487) — and re-runs the best succeeded pair's
check via `AiortcCall._nominate_best_pair` so a real `USE-CANDIDATE` is sent
and ICE completes; and
`AiortcCall.close()` cancels the aioice checks so their STUN retry timers stop
spamming tracebacks after a hang-up. Muji (XEP-0272) coordinates conference calls inside a MUC: the
`<muji>` contents map is advertised in MUC presence (`MujiManager.handle_presence`),
the joiner opens a Jingle session with every other participant's real JID
tagged `<muji room=…/>` (`start_call(..., muji_room=rook)`), and content
add/remove, leaving and XEP-0482 invites are handled. Muji sessions never open
a 1:1 `CallWindow` — `MainWindow._on_call_state` skips windows whose session
carries `muji_room` — and incoming session-initiates are recorded as
participants via the `muji_session` event → `MujiManager.note_session` (a peer
whose MUC presence we missed is still listed). `note_session` matches peers by
**bare real JID**, and a session-only entry is a `virtual` placeholder that
`handle_presence` merges into the real MUC nickname once the occupant's presence
arrives — so a peer (e.g. Monocles mod) never appears twice, once under its room
nick and once under its Jingle resource. A presence from a tracked participant
that carries no `<muji/>` (or `type="unavailable"`) means the peer left the call
(XEP-0272 §6): the participant and its mosaic tile are dropped, `muji_updated`
fires and `JingleRtpManager.end_muji_peer` closes our session to that peer
(`_close_session` also calls `MujiManager.forget_session` to drop a virtual
placeholder); `_MosaicVideo.remove_nick` resets the zoom to the grid when the
enlarged participant leaves. The single `MujiCallWindow`
splits horizontally: the video mosaic / status on the left and the participant
list on the right (the same style as the MUC chat participant sidebar). Each
participant row carries a rounded avatar (`_rounded_avatar`, the cached vCard
PNG clipped by `include.avatars.rounded_avatar` using `appearance.avatar_radius`
— the same knob as the roster and MUC participant lists, 0 = square … 100 =
circle — filled by `MainWindow._muji_avatar` → `set_avatars`) before the nick
and **three**
icon-only toggles that swap their glyph on state — "send my mic to this
participant" (`set_call_audio`, per-session silence), "hear this participant"
(`set_call_audio_receive` → `AiortcCall.set_remote_audio_enabled` →
per-session playback mute, no renegotiation) and "send my video to this
participant" (`set_call_video`, per-session black frames). Below the list a
separate icon-only row — microphone, speaker and (video conferences only)
camera — beside the red `call-hangup` "leave" button drives the same devices
for **all** participants: the effective per-party state is the global layer AND
the per-party layer (`_effective`), so these toggles never change the per-party
configuration, and each channel is emitted only when it changes. A session is
often bound after its row was created, so `JingleRtpManager._bind_call` emits
`call_bound` → `MainWindow._on_call_bound` → `MujiCallWindow.apply_states`,
which re-applies the effective states to the freshly bound session. When the conference
carries video the mosaic (`_MosaicVideo`) shows one captioned tile per video
participant **plus a mirrored self tile** labelled with our own nick; clicking
a tile enlarges that participant with the rest as a bottom strip and a "back to
grid" button. Own video is fed by tapping the local capture: `_VideoCaptureTrack`
invokes an `on_local_frame` callback (only for real camera frames),
`JingleRtpManager._forward_local` re-emits it as `call_local_video_frame` for
the single session marked via `set_local_preview` (chosen by
`MainWindow._sync_muji_preview` as the room's first video session; since the UI
can pick it before the engine call exists, `_bind_call` re-applies the flag to
the call when it is created), and
`MainWindow._on_call_local_video_frame` pushes it into `MujiCallWindow
.set_local_frame`. While the room has **no** peer video session (e.g. we are
alone) `_sync_muji_preview` instead starts a standalone camera capture
(`media._LocalPreviewCapture` via `JingleRtpManager.start_local_preview`),
emitted as `muji_local_video_frame`; `_bind_call` stops it before a session's
own capture opens the device. Debug logging uses `stanza_im.call*` with `CALL[…]`/`MUJI[…]`
markers. The optional `calls` extra (`pip install .[calls]`) installs `aiortc`;
without it the engine is a `NullMediaEngine` and calling is disabled.

Preferences use icon navigation and nested tabs. The section icons come from
`IconCache.get_category_icon` (scalable SVG first): «Stanza IM» uses the app
icon, «Звонки» the headset, «Внешний вид» `draw-brush`, «Приватность» the
shield, «Плагины» the puzzle piece, «Статус» the speech bubble and «Горячие
клавиши» the keyboard. Pages are built **lazily** (`_ensure_page`): only the
first (visible) section is built when the dialog opens, the rest on first
selection and, after `showEvent`, one per event-loop turn
(`_build_pages_deferred`); `_ensure_all_pages` runs before Apply/OK (and
`_LazyControls` builds every page on a direct `controls[key]` lookup) so no
setting is lost — this keeps opening the dialog fast. A **«Reset to
defaults»** gear button (`reset-defaults.svg`) sits to the left of
Ok/Apply/Cancel: it resets the **current tab's** (or page's) controls to the
first-run values (`Config.defaults()` → `_values_dict(cfg)`, scoped by
`_control_pages`, which `_page()` fills while building); the widgets are only
re-filled — the values persist on Ok/Apply like any edit.
«Длина заголовка вкладки» lives only on the Chat tab (with an info glyph) and
sets `application.tab_title_length` + `chat.tab_title_length` together. The
«Stanza IM» → «Общие» page carries the «Язык приложения» selector
(`ui.language`, default `""` = system locale; its options come from
`i18n.available_languages()`); `MainWindow.__init__` calls `load_i18n(saved or
None)` right after constructing `Config`, so a chosen language applies on the
next start (an info glyph notes the restart). Numeric
spinners and combo boxes share a uniform fixed width (`SPIN_WIDTH`/`COMBO_WIDTH`)
so selectors line up across pages; the tray popup mode is a three-option
selector (`notifications.popups` = `off`/`system`/`system_messages`, see the
tray paragraph). The Appearance page is split
into «Темы», «Ростер», «Конференции», «Шрифты», «Цвет» and «Разное» («Ростер»
toggles the roster avatars/activity/mood/client, see §3; «Конференции» toggles
the MUC participant avatars/client icons; «Разное» holds the media-preview size,
the preview cache TTL/limit, the MUC mention highlight mode and the
`appearance.show_unread_in_tabs` toggle — the Psi-style unread indicator on the
chat tabs and the window title, default on). `Apply` applies
settings without closing the dialog. Chat shortcuts include Enter/Ctrl+Enter, Esc,
Up (empty input) to reply to the last incoming message, Down to cancel an
untouched reply, Ctrl+Up to edit the last own message, Ctrl+PgUp/Ctrl+PgDown,
Ctrl+1..9 and Ctrl+W; Esc also closes the media viewer. Contact context menus
provide
checkable group assignment and creation of new groups. Appearance → «Разное»
also selects the interface mode (`appearance.interface_mode`): `separate`
(default) keeps the chat in its own window, `unified` embeds the whole
`ChatWindow` as a child widget beside the roster in a horizontal
`QSplitter`; `MainWindow._apply_interface_mode` switches live and
`ChatWindow.set_embedded` toggles the window flags/title/geometry handling
(embedded `ChatWindow` emits `attention_requested`, which raises the main
window instead of the chat window).

**Chat text scale** (`chat.text_scale`, default `1.0`): a per-chat zoom in a
50–300 % range (clamped to 0.5–3.0 by `chat_view.clamp_zoom`, which also
guards non-numeric input) driven by Ctrl+wheel in the chat view
(`ChatView.set_chat_zoom`/`zoom_changed`). Chromium handles Ctrl+wheel itself
once the page owns focus, so our `wheelEvent` is never called; the WebEngine
view's always-running 250 ms scroll poll instead compares
`QWebEngineView.zoomFactor()` against the tracked `self._zoom` (guarded by a
`_loading` flag and a tolerance check to avoid loops and load-time resets) and
relays any Chromium-initiated zoom to `zoom_changed` — Qt 6 has no
`zoomFactorChanged` signal, so polling the property is the only reliable relay.
Both paths feed the same `zoom_changed → text_scale_changed
→ config.save() + _chat_options` chain. The value is re-applied to any
(re)opened 1:1 and MUC tab through `ChatWidget.set_text_scale` fed by the
`ChatWindow._chat_options` snapshot, so reopened tabs never reset to 100 %
(and `_on_load_finished` re-sends the zoom on every document load). The
Preferences → Appearance → Fonts «Масштаб текста чата» slider (same 50–300 %
range) is bidirectionally synced with the live factor via
`PreferencesDialog.sync_scale` and saved on Apply; it is a `_SnapSlider`
that snaps user drags/clicks/keys to the 10 % grid without touching
programmatic `setValue` (zoom sync from the wheel stays exact).

**Widget fonts** (`appearance.{roster,chat,osd,nick,participant,input,menu,tab,
selector}_font` + `{...}_font_size`, pt; `""`/`0` = Qt default; the input font
defaults to the chat font): applied live from Preferences.
The menu, tab-title and selector fonts (`menu_font`/`tab_font`/`selector_font`)
are applied **app-wide** by `MainWindow._apply_widget_fonts` via a
`QApplication` stylesheet with type selectors (`QMenuBar, QMenu` / `QTabBar` /
`QComboBox { font-family; font-size }`) — the only practical way to reach the
dynamically created menus, tab bars and dialog selectors.
A non-empty application stylesheet makes Qt re-polish every widget and
re-resolve the font of those without a stylesheet of their own, resetting the
chat input / MUC subject / participant fonts to the application default — so
`MainWindow._apply_widget_fonts` calls `ChatWindow.reapply_fonts()` right after
setting it, and `ChatWidget.showEvent` re-applies them (`ChatWidget.
reapply_fonts`) when a tab is shown; `_SubjectEdit` carries a local stylesheet
and is immune either way.
Roster rendering uses the QSS typeface via `MainWindow._apply_roster_font`
(same raster pass); chat text sets `ChatThemeFactory.set_chat_font(family,
size)`, which injects a `body { font-family: … !important; font-size: …pt
!important }` override into `generate_page`/`generate_empty_page` with
`font-family: inherit !important` for message descendants (`.sender`,
`.fromstatus`, `.next_label`, `.time_initial`, `.stanza-action`,
`.stanza-reply`); `ChatThemeFactory.set_nick_font(family, size)` adds a
`.sender { … } !important` rule and, when the skin packs no
`class="sender"` (e.g. `candy`), wraps the `%sender%` placeholder in a
`<span class="sender">` so the nickname font applies everywhere (skins with
their own sender class, e.g. `minimal-mod`, are never double-wrapped); OSD
notifications get `OsdManager.apply_font(family, size)` (re-renders visible
popups); the MUC participant sidebar gets `ChatWidget.set_participant_font`
(hosted by `ChatWindow.set_participant_font`, remembered for new MUC tabs via
`ChatWindow._participant_font`); the MUC subject header («Тема:» + the topic
text, not the room name) gets `ChatWidget.set_subject_font`
(`appearance.muc_subject_font`/`_size`, hosted by `ChatWindow.set_subject_font`,
remembered as `_subject_font`; `_SubjectButton`/`_SubjectEdit` use
`FontZoomMixin`, so Ctrl+wheel over the header emits
`subject_font_zoom_requested` → `MainWindow._on_subject_font_zoom` persists and
applies it). In the preferences «Шрифты» tab, empty/zero
values show the *real* font Qt would use instead: the family combo's first
entry is the plain default family name (for nicknames following the chat font
live) and the size spin shows the real size marked with a compact
«<size> pt (*)»; the full phrases («По умолчанию — <family>» / «<size> pt
(по умолчанию)») live in the two tooltips — both resolved from
`QApplication.font()` by `PreferencesDialog._default_app_font` while the stored
value stays `""`/`0`. The size spin is **left-aligned**
(`setAlignment(AlignLeft)`), and each font row's family combo + size
spin **expand with the dialog** (the form's `ExpandingFieldsGrow` + an
`Expanding` policy and a 3:1 stretch in `_font_row`).
The message input gets `ChatWidget.set_input_font` (hosted by
`ChatWindow.set_input_font`, remembered as `_input_font`); its placeholder
(«Отправить») is drawn by `_ChatInput.paintEvent` with the widget's own font
(`set_placeholder`), because Qt's built-in placeholder is painted with the
style-resolved font — a non-empty application stylesheet resets that to the
application default while the typed text keeps the document font.
**Ctrl+wheel** over
the input, the roster or the MUC participant list (including over a participant
**row**, whose child labels forward wheel events) changes only that widget's
**font size** (`ui/font_zoom.py` `FontZoomMixin`/`wheel_font_size`, 6–48 pt,
family unchanged); the widget emits `*_font_zoom_requested(size)`, MainWindow
persists it (`appearance.*_font_size`), calls the matching
`ChatWindow.set_*_font`/`_apply_roster_font` so **every** open tab and every
new one picks it up, and pushes it back into the open Preferences dialog via
`PreferencesDialog.sync_font_size(key, size)`. **Ctrl+wheel** over the **menu
bar** or a **tab bar** changes `appearance.menu_font_size`/`tab_font_size`
(`MainWindow._handle_widget_font_wheel`, in the app event filter; the event is
consumed so the tabs do not switch). `MainWindow.__init__` ends with
`_on_settings_applied()`, so all saved settings (fonts, colors, themes,
interface mode) are in effect from the first frame. The MUC participant nick is
drawn by `_FadeLabel.paintEvent`, which sets its own font on the pixmap painter
(a painter on a bare pixmap otherwise uses the application default, so the nick
would not resize).
Fonts affect text only — avatars/images scale solely with the text-scale
slider. Changing the chat font re-renders open tabs via
`ChatWindow.rerender_messages`.

**Colors** (`appearance.{roster_bg_color,roster_group_bg_color,chat_bg_color,
muc_highlight_color,osd_bg_color,osd_font_color,osd_opacity,
colored_muc_nicks}`, a «Цвет» page in Appearance
preferences): roster colors are drawn by the QPainter pass — `RosterStyle.set_colors`
(`bg_color()` fills each item area in `RosterWidget.paintEvent`, `group_bg_color()`
stripes the group headers) and `MainWindow._apply_roster_colors` also paints the
viewport so empty space below the roster matches. The chat background is a CSS
override injected by `ChatThemeFactory.set_chat_bg_color` (`body {
background-color: … !important; background-image: none !important }`, applied
to both 1:1 and MUC factories; it overrides the skin's tiled image); the MUC
mention highlight color feeds `ChatThemeFactory.set_highlight_color`. Color
changes re-render open chats via `ChatWindow.rerender_messages`. The OSD
background/text color and opacity (0–100 %) feed `OsdManager.apply_colors` →
`_OsdWindow.apply_style`, which rebuilds the OSD stylesheet (`rgba(r,g,b,a)`
background, text color on all labels); live popups update in place.

**Colorful MUC nicknames** (`appearance.colored_muc_nicks`, default on):
`ChatWidget` keeps a `NickColorAllocator` (`ui/nick_colors.py`); keys are the
`normalize_nick`d nick (NFKC + whitespace collapse + case fold) bound to the
participant's `real_jid` when present. Colors are allocated on first sight from
a 15-shade dark palette with a golden-angle HSL fallback for large rooms, are
released by `prune()` when participants leave, and are rebuilt from the current
roster in `update_muc_users`/`set_self_nick`. `_entry_view_kwargs` passes the
per-sender color as `sender_color` so `render_message` fills `%senderColor%`
(`minimal-mod`; other skins ignore it), and the participant-sidebar row label
gets the matching inline color. 1:1 chats never color senders. `ChatWindow.
set_colored_muc_nicks` toggles every MUC tab (and is remembered for new tabs);
toggling re-renders messages and the participant list.

**Auto-status message** (`status.auto_status_message`, default `""`): one
shared text sent with the show when `MainWindow._check_auto_status` switches
to `away`/`xa` after inactivity; when empty, the previously stored status
text is kept. Returning activity (`eventFilter`) resumes
`status.last_status` with an empty message, so the auto text never sticks.

### 8. Connection, TLS & Transport (`core/client.py`, `core/discovery.py`, `xmpp/socks5.py`)

- **Resource**: `connection.resource_mode` = `hostname` (default, uses
  `socket.gethostname()`) or `manual` (`connection.resource`).
- **Priority**: `connection.priority_mode` = `status` (default map:
  online/chat 50, away 40, xa 30, dnd 0) or `manual`
  (`connection.priority`, 0..127); computed in `send_presence`, re-sent live.
- **Account SOCKS5**: `connection.proxy_mode` = `none`/`socks5`.
  `xmpp/socks5.py` is a dependency-free RFC 1928 CONNECT connector;
  `JabberClient._install_socks_proxy` replaces `xmpp._attempt_connection`
  (instance attribute) to open the socket through the proxy and hand it to
  slixmpp via `loop.create_connection(sock=..., ssl=...)`.
- **TLS mode** `connection.tls_mode`: `direct` ("Только TLS"), `prefer`
  (default), `normal`. `_StanzaXMPP.order_tls_first` puts `_xmpps-client._tcp`
  records first (deterministic fallback); "TLS only" pre-resolves
  `core/discovery.resolve_client_srv()` and raises `TLSOnlyUnavailable` when the
  record is absent.
- **STARTTLS mode** `connection.starttls_mode`: `always` (default,
  `enable_plaintext=False`; `_StanzaXMPP._handle_stream_features` aborts with a
  `tls_required` event if the server does not offer STARTTLS),
  `opportunistic`, `never`. `tls_flags()` maps both selectors to slixmpp
  `enable_direct_tls/enable_starttls/enable_plaintext` + `_require_starttls`.
- **SASL**: no forced mechanism (slixmpp picks the strongest). On TLS 1.3
  without `tls-exporter` in `ssl.CHANNEL_BINDING_TYPES` (Python < 3.12),
  `filter_plus_mechs()` drops `*-PLUS` so SCRAM does not send an invalid
  channel binding and trigger a transient `failed_auth`.
- **Presence on system sleep**: `connection.offline_on_suspend` (default on,
  Preferences → Connection) — `ui/suspend_monitor.py` subscribes to logind's
  `PrepareForSleep` (UPower `Sleeping` fallback) on the system bus;
  `MainWindow._on_system_suspend` sends an `unavailable` presence with the
  dedicated `status_suspend` text («Компьютер перешел в спящий режим») and
  `_on_system_resume` restores the pre-sleep show and the user's status message
  (combo/tray synced). A stream lost during sleep is restored by
  `_on_session_started` (`_restore_suspended_presence`); auto-status is paused
  while suspended. No logind delay inhibitor is taken (best-effort send).
  [`tests/test_suspend_presence.py`]
- **Language**: the stream advertises the UI language
  (`i18n.current_language()`) as `xml:lang` (`_StanzaXMPP(jid, password,
  lang=…)`) and `start_stream_handler` forces `peer_default_lang` to it, so
  outgoing stanzas carry it and servers localize data forms (e.g. the room
  configuration) like Psi.
- **Keep-alive**: `connection.keepalive` → `xmpp.whitespace_keepalive`.
- `_connected_target` (via `_dns_hosts`) reports the real SRV endpoint;
  `connection_info()` feeds the preferences info icon (mode, TLS version,
  cipher, SASL, keep-alive, SM, CSI, server) and carries `cert` — the peer TLS
  certificate (`_peer_certificate(sock)`: subject/issuer CN+O, validity with
  days left/expired, serial, DNS SANs, SHA-256 fingerprint of the DER,
  `verified`). The Connection page's separate info icon (row «Сертификат»)
  opens `ui/certificate_dialog.CertificateDialog` non-modally with the same
  `certificate_lines()`; it is disabled when no certificate is available. These
  information affordances use the glyph
  `resources/images/16x16/actions/info.svg` (a blue «i» circle) via
  `PreferencesDialog._info_icon()`.
- **Help menu — connection / certificate / server info**: the «Справка» menu
  carries the three session-gated non-modal dialogs below (disabled until
  `session_started`, enabled again on `stream_resumed`, disabled on
  disconnect/auth/TLS failure via `_set_info_actions_enabled`) plus «О кэше»,
  which needs no session. The icons are distinct: `connected.svg`, `shield.svg`
  (security), `server.svg` and `cache.svg`. «О подключении»
  (`_on_connection_info`) shows
  `ui/connection_info_dialog.ConnectionInfoDialog`, which renders
  `connection_info_lines(info)` — the same lines as the Preferences connection
  tooltip. «О сертификате» (`_on_certificate_info`) reuses
  `CertificateDialog` (a message box when no certificate is available).
  «О сервере» (`_on_server_info`) shows
  `ui/server_info_dialog.ServerInfoDialog`, which calls
  `core/server_features.collect_server_features(client)` — the account domain's
  `disco#info` features, the account's **bare JID** features (PEP, stanza IDs,
  bookmark/avatar conversion), the conference and HTTP-upload components
  (`discover_conference_service` / `_http_upload_service`, the latter's
  `max-file-size`), the domain's ad-hoc command list (XEP-0401) and the raw
  `<stream:features>` namespaces captured by `_StanzaXMPP.stream_feature_ns`
  (stored as namespaces, not `{ns}tag`) — plus the negotiated SASL mechanism and
  the server identity/software (XEP-0092) — and marks the preset `SERVER_XEPS`
  list supported/unsupported (green/red) via the pure
  `evaluate_server_xeps(ctx)`. XEP-0163 is read from the account's
  `pubsub`+`publish-options` (ejabberd does not announce `#pep`), XEP-0402 from
  the `#compat`/`#compat-pep` features, XEP-0401 from the ad-hoc commands and
  XEP-0490 only from the account's `urn:xmpp:mds:server-assist:0` (the
  `displayed:0` node is a client PEP feature). The same dialog shows the
  XEP-0157 server contact addresses (`parse_server_contacts` reads the
  `http://jabber.org/network/serverinfo` data form from the domain's
  `disco#info`, falling back to the node query): a «Контакты сервера» group
  above the table with clickable links, `xmpp:` ones routed through
  `MainWindow._on_xmpp_uri` (`ServerInfoDialog.contact_uri_clicked`).
  [`tests/test_server_features.py`]
- **Cache overview (Help → «О кэше», `ui/cache_dialog.py`)**: a non-modal
  `CacheDialog` lists every on-disk cache with its size and a per-row
  «Очистить…» button (each asks for confirmation, then clears and re-measures;
  the total is shown below). Rows: media previews (`MediaCache.total_bytes`,
  `clear()`, plus `MediaPreviewService.clear_memory()`), avatars
  (`include.avatars.clear_cache`, then `_URI_CACHE`, `client._avatar_ids`/
  `_avatar_failed`, the roster pixmaps and the open chats are refreshed), map
  tiles (`TileCache.total_bytes`/`clear()`), the vCard metadata file
  (`VCardCache.clear()`), the discovery file (`DiscoveryCache.clear()`), the
  roster cache (`roster_cache.clear()`; the client keeps it absent until the
  next login via `_roster_cache_cleared`, the dialog warns it is recreated at
  login), the Chromium HTTP cache (`QWebEngineProfile.cachePath()` +
  `clearHttpCache()` when WebEngine is already imported, otherwise
  `QStandardPaths.CacheLocation/QtWebEngine/Default` is removed — importing
  Chromium just for the dialog is never done) and the whole local message
  history (`history.clear_all()`: closes the pooled connections, removes the
  SQLite/JSONL files, then resets the unread/read state and `_mds_local`, clears
  every open tab via `ChatWidget.reset_history()` and closes the History
  Manager; the server archive is untouched). Rows are one line each (the hint
  column elides, the full text stays in its tooltip; the vertical header uses
  `ResizeToContents` and the first `showEvent` re-fits the rows after the real
  column widths are known) and each row carries a flat, frameless
  `QToolButton` (`process-stop.png`) like the OMEMO device manager instead of a
  text button; its tooltip is the row's warning (what is stored, what clearing
  affects). The dialog is parented to the main window and kept as
  `_cache_dialog`.
  [`tests/test_cache_dialog.py`]
- **Privacy lists & blocking (XEP-0016/0191/0377)**: Preferences → Connection →
  «Подключение» carries two buttons gated on the account domain's disco
  (`supports_privacy`/`supports_blocking`, probed by `refresh_server_features`
  at `session_started`; `_server_feature` stays optimistic until then).
  «Списки приватности» opens `ui/privacy_lists_dialog.py` — the active-list and
  default-list selectors (`set_active_privacy_list` / `set_default_privacy_list`
  → `<active/>` / `<default/>`; the default applies per XEP-0016 when no active
  list is set, with an info glyph explaining that), the list editor
  (create/rename/delete) and the localized rule list
  with priority arrows and add/edit/delete/apply; the editor opens on the
  effective list (active, else default, else the first one). The wire format is built as
  raw IQs by `core/privacy.py` (`jabber:iq:privacy`) because slixmpp's
  `xep_0016` writes `presence-in` for `presence-out`; a rule is
  `jid`/`group`/`subscription`/all × `message`/`iq`/`presence-in`/
  `presence-out` × `allow`/`deny`, and an item without stanza flags means all
  (`ui/privacy_rule_dialog.py` + `describe_item`). Blocking uses XEP-0191
  (`xep_0191`): the roster context menu (between «Повторить запрос авторизации»
  and «Очистить историю») has a checkable «Заблокировать»/«Разблокировать»
  (blocked contacts are struck through via `UserItem.blocked` /
  `RosterWidget.set_blocked`) and «Пожаловаться» (`ui/report_dialog.py`,
  `client.report_contact` → XEP-0377 `<block><item><report reason=…><text/>`).
  The blocklist is read with `get_blocked()` and the items parsed from the raw
  XML (`_block_items`), because `get_blocked_jids()` only exists in newer
  slixmpp (1.10 ships `get_blocked` and returns a set of JIDs, 1.17 iterable
  items); the same XML parsing handles the `blocked`/`unblocked` pushes.
  Reports are offered whenever blocking is supported (`supports_reports()` →
  `supports_blocking()`), since servers that process reports often do not
  announce `urn:xmpp:reporting:1`. `ui/blocked_contacts_dialog.py`
  lists/adds/removes blocked JIDs; server pushes and the local operations emit
  `blocklist_updated`, which refreshes the roster. [`tests/test_privacy.py`]
- **Client identity / caps branding**: `JabberClient.__init__` adds a named
  disco identity (`client`/`pc`, `name=APP_NAME`) and overrides
  `xep_0115.caps_node` to the human-readable `Stanza IM <VERSION>` (slixmpp's
  default is a nameless `client/bot` plus the `http://slixmpp.com/ver/…` node;
  clients that keep a node→name table, e.g. Psi+/Gajim/Conversations, display
  the caps node verbatim for unknown clients). The XEP-0092
  `software_name`/`version`/`os` are set explicitly (slixmpp's `plugin_init`
  only honours the `name` config key), so version queries report Stanza IM.
  The advertised version is `constants.VERSION_DISPLAY` — the plain `VERSION`
  outside a git checkout, with the short HEAD commit appended (`0.1.0 (00dc38b)`)
  when running from one (`constants._git_commit`, `PROJECT_ROOT/.git`) — used in
  the caps node, XEP-0092, the About dialog and the startup log, so a stale build
  is visible at a glance. The disco identities/features are registered by
  `JabberClient._register_disco()`, called both in `__init__` and again in
  `_on_session_start` before the first presence (followed by
  `xep_0115.update_caps`): slixmpp stores a jid-less `add_feature`/`add_identity`
  under the JID bound at call time, and the server assigns the real resource only
  during the bind, so the `__init__` calls alone would be invisible to the
  post-bind disco (calls, the whiteboard, … would be missing from our caps).
  [`tests/test_client_branding.py`]

### 9. Thrifty traffic — Stream Management & CSI (XEP-0198/0352)

- **Graceful shutdown**: `JabberClient.disconnect()` disables reconnect
  (`_reconnect_enabled = False`, `_shutting_down = True`, `_cancel_reconnect()`),
  sends `<presence type='unavailable'/>` and **awaits**
  `xmpp.disconnect(wait=1.0)` (slixmpp's `XMLStream.disconnect` returns a future
  that drains the send queue and closes the stream). `MainWindow._shutdown_async`
  waits for it before cancelling tasks and quitting — otherwise the close is
  cancelled and the server keeps the session (the account stays online) for the
  XEP-0198 resumption window.

- `connection.stream_management` (default on) registers `xep_0198`: slixmpp
  enables SM after bind and resumes a dropped stream (`session_resumed`)
  without re-auth/roster/presence, replaying unacked stanzas.
  `JabberClient.resume_expected()` (true only while `xep_0198.sm_id` is set —
  slixmpp has **no** `auto_reconnect` option) drives the UI: while resume is
  possible MainWindow shows "Переподключение…". If the stream is not resumed
  within a short window (`_RESUME_WINDOW_S` = 10 s) or the server refuses
  (`sm_failed`), the client runs its **own reconnect loop**
  (`_reconnect_loop`): `connect_async` retried with a 1/2/5/15/30 s backoff
  (capped, **no attempt limit**) until connected, emitting
  `reconnecting(attempt, delay)` / `reconnect_failed(attempt)` / `reconnected`;
  a successful session re-runs the normal `_on_session_start`
  (roster/presence/PEP/autojoin). A `session_resumed` cancels any scheduled
  attempt. `disconnect()`/logout stops the loop; `manual_reconnect()` resets the
  backoff for the "Reconnect" button. Messages sent while offline are
  not hard-blocked (a future offline outbox will flush them on reconnect,
  `_offline_outbox` is the placeholder). MainWindow shows the connection state
  **above the status combo** in the roster's bottom panel (never in a window
  status bar, so the combo's area does not jump): a thin `_conn_progress` bar
  (`_set_conn_progress`, determinate for the login stages, indeterminate while
  reconnecting via `_set_busy_status`) and a flat `_reconnect_btn` whose text is
  the **countdown** «Переподключение N с» (`login_reconnect_countdown`, a 1 s
  `_reconnect_timer` from the `reconnecting` delay) or «Переподключиться»
  (`_set_offline_status`); clicking it runs `manual_reconnect`
  (`_on_reconnect_clicked`). `_clear_status` hides it once a session is live.
  The bar (`_ClickableProgressBar`) carries a **tooltip** with the current
  connection state and a **click** toggles a wide inline panel
  (`_conn_panel`) with the stage + `connection_info_lines`
  (`_conn_state_summary`/`_update_conn_hint`, refreshed from every status
  update).
- `connection.csi` (default on) registers `xep_0352`:
  `set_client_active()`/`_sync_csi()` send `<active/>`/`<inactive/>`.
  MainWindow derives activity from
  `QApplication.applicationState() == ApplicationActive` through an application
  `eventFilter` (`ApplicationStateChange`/`WindowActivate`/`WindowDeactivate`)
  plus the show/hide/toggle/Esc/close hooks, and re-sends the state on
  `session_start`/`session_resumed`/`csi_enabled`. The preference applies live
  (no restart): `JabberClient.set_csi_config()` (un)registers the plugin and
  sends `<active/>` on disable; MainWindow calls it from `_on_settings_applied`.
  Because a server holds non-urgent stanzas (chat states) while the client is
  inactive, the optional `connection.csi_keep_active_for_typing_osd` (default
  off, Preferences → Connection → Advanced) keeps the client active while
  `notifications.osd_enabled` **and** `osd_typing` are on
  (`MainWindow._keep_csi_active_for_typing_osd`), so typing OSDs still arrive
  with the window in the background. The option is followed by an info glyph
  (`resources/images/16x16/actions/info.svg`, a blue «i» circle) whose tooltip
  explains this server-side buffering; the same glyph is used for the
  encryption/certificate/STUN information affordances.

### 10. Service discovery — file proxy & STUN/TURN (`core/discovery.py`)

- **XEP-0065**: `discover_file_proxy()` uses slixmpp
  `xep_0065.discover_proxies()` (server `disco#items` then
  `category='proxy' type='bytestreams'`); the returned mapping is keyed by
  `slixmpp.JID`, which is not orderable, so it is sorted with `key=str`.
- **STUN/TURN**: `discover_stun_turn()` queries SRV
  `_turns/_stuns/_turn/_stun._tcp|udp` via aiodns, encrypted first and TURN
  before STUN.
- `DiscoveryCache` (JSON under `$XDG_CACHE_HOME/stanza-im/discovery.json`)
  keeps positives for 24 h and negatives for 10 min; `refresh()` isolates the
  two sections (a file-proxy failure never hides STUN/TURN) and
  `effective_endpoint()` implements the auto/manual choice. Discovery runs as a
  background task after `session_start`; "Detect again" calls
  `refresh_services()`.

## Memory Management Rules

1. **IconCache**: LRU, 512 entries, no time-based TTL (icon files are
   immutable); `forget(path)` drops one file whose content changed (avatar)
2. **Avatars**: stored as `str` path; the roster caches only the scaled/rounded
   variants per `(file, size, radius)` (`RosterStyle._scaled`, invalidated by
   `clear_pixmaps()` on an avatar update), never the full pixmap in `UserItem`
3. **ChatView**: shared `QWebEngineProfile` (not per-tab)
4. **Idle tab suspension**: `chat.idle_unload_minutes` (default `10`, `0` = off,
   Preferences → Chat → «General»). `MainWindow._maybe_suspend_tabs` (per-minute
   timer) asks `ChatWindow.suspend_tab` for tabs that are not current, have no
   unread message and saw no activity within the window; `ChatWidget.suspend`
   frees the `ChatView`/WebEngine page and swaps in a `_NullView` stub (messages
   keep accumulating in Python), while `resume` (lazy, on tab activation)
   rebuilds the view and re-renders `_history`/`_messages` **once**, deferred by
   80 ms (`_resume_render_timer`): an unread tab replaces that window with its
   history load, whose `_render_all` cancels the timer. The window-level setters
   `ChatWindow._resume_widget` re-applies are idempotent (participant font/
   options, coloured nicks, hats, avatar radius, text scale), so an unchanged
   activation no longer triggers 3-4 page loads and full participant rebuilds.
   [`tests/test_tab_suspend.py`, `tests/test_tab_resume.py`]
5. **Roster**: no child widgets, single QPainter pass
6. **Closed tabs**: `ChatWindow.close_chat` removes the tab, then
   `setParent(None)` + `deleteLater()` on the `ChatWidget` — a `QTabWidget`
   page stays parented after `removeTab` and would otherwise leak the whole
   `QWebEngineView`/page for the app's lifetime; `ChatWidget.detach` stops the
   typing timer and the view's scroll poll (`ChatView.shutdown`) and clears the
   Python message lists before deletion. [`tests/test_tab_leak.py`]
7. **Per-tab bounds**: an open tab keeps at most `_HISTORY_MAX` (5000) history
   rows, `_MESSAGES_MAX` live rows and `_STATUS_MAX` (300) status lines
   (`chat_widget.py`), while the WebEngine DOM trims to
   `ChatView._MAX_DOM_MESSAGES` (500) message nodes; older messages stay in
   SQLite/MAM and are re-fetched by the paging menus. `chat.history_limit`
   (default 50, 10–1000, Preferences → Chat → «General») is the on-open window;
   DB/MAM requests page in `_HISTORY_PAGE` (60) steps so a large window never
   turns into one huge request.
8. **Housekeeping**: a 1-min `MainWindow._maybe_trim_memory` asks
   `memstats.should_trim`; when the process grew by 200 MiB since the last trim
   (rate-limited to one trim per 5 min) or by 600 MiB at once, it runs
   `memstats.trim_heap()` (`gc.collect()` + glibc `malloc_trim(0)`) and records
   the new RSS baseline. The same trim runs right after a tab closes or is
   suspended. This keeps the RSS sawtooth flat with WebEngine children
   unaffected (they are separate processes).

## Running

```bash
python main.py              # Direct
python -m stanza_im         # Module
```

`Ctrl+C` runs the same graceful shutdown as the Quit action: `app.py` installs
`loop.add_signal_handler(SIGINT, …)` (qasync's loop subclasses the Unix selector
loop), so the SIGINT never raises `KeyboardInterrupt` inside the Qt loop (which
used to print a traceback in `eventFilter` and abort Qt) — the handler calls
`MainWindow._quit` (flush state, disconnect ≤3 s, cancel tasks, quit); a second
Ctrl+C forces `os._exit(130)`.

Command-line keys: `-d/--debug` (console debug output), `-x/--xml` (raw
SEND/RECV XML), `-l/--log` (full debug log to `stanza-im.log`), `-m/--memstat`
(periodic memory statistics; repeat as `-mm` for the deep Python-heap
breakdown), `-h/--help`. `app.prepare_qt_argv()` re-prepends the program name
before `QApplication` — QWebEngine aborts on an empty argv. `core/memstats.py`
has two levels: `-m` is cheap (no tracing — main RSS/PSS/peak plus
`private_dirty`/`anonymous`/`shared_clean` from `smaps_rollup` (heap vs
library growth), the Chromium **descendant processes** grouped by type *and*
listed one per line (`pid`, type, `comm`, rss, pss), the Qt
widget/WebEngine-view counts and `QPixmapCache` limit, the loaded heavy stacks);
`-mm` additionally enables `tracemalloc(nframe=1)` and logs the live Python
heap grouped by package. The **deep snapshot and the gc object-type breakdown
run on every fifth report only** (the first report is deep too): one
snapshot+statistics cycle churns tens of megabytes of native heap, which used
to dominate the RSS curve of a long `-mm` session. The snapshot runs in a
worker thread (the event loop is never blocked), logs its own RSS cost
(`rss before -> after`) and the **growth since the previous snapshot** per
package (only the small `package -> (bytes, count)` map is kept, not the
snapshot), and `malloc_trim(0)` runs right after it and after the gc scan so
the diagnostic churn does not accumulate. Chromium forks its renderer/GPU/network processes
from a zygote, so the whole descendant tree is walked (not just direct children)
via `_descendants_from`/`_proc_tree`; the type comes from
`--type=renderer|gpu-process|utility|zygote` (network = utility with
`--utility-sub-type=…network…`) with `/proc/<pid>/comm` as a fallback (a zygote
fork inherits the zygote's `cmdline`, so the per-process `comm` line is what
tells the roles apart). The gc breakdown counts only GC-tracked objects
(widgets, message objects, …), so it never inflates memory the way tracemalloc
does.

**Fast startup**: heavy optional modules are kept off the login-window path, all
tunable via Preferences → «Stanza IM» → «Производительность» (`[performance]`):
- `defer_ui_build` (default on): `MainWindow(app, defer=True)` builds only the
  shell + login/splash pages, `app.run()` calls `window.show()` and then
  `QTimer.singleShot(0, window.build_deferred)`; `build_deferred` (idempotent)
  builds the theme factories, chat window, tray, OSD, sounds, roster UI and
  applies the settings/plugins. `defer=False` (the default, used by tests)
  builds everything synchronously.
- `omemo_load_mode` (default `lazy`): `xmpp/omemo/availability.py` computes
  `AVAILABLE`/`BACKENDS`/`MISSING*` from `importlib.util.find_spec` (never
  importing `oldmemo`/`twomemo`/`slixmpp_omemo`/`xmlschema`/`doubleratchet`);
  `availability.verify()` does the real import once, at OMEMO plugin
  registration (login) or from the startup probe in `startup` mode, and catches
  a present-but-broken transitive dependency. `off` never imports the stack:
  `app.py` calls `availability.set_disabled(True)` (sticky — `verify()` stays
  off, `detail()`/`summary()` report the settings) and the client skips
  registration, so OMEMO is unavailable even when the packages are installed
  (the Preferences «OMEMO» tab shows the disabled notice).
- `calls_load_mode` (default `lazy`): `xmpp/jingle_rtp.py` no longer imports
  `xmpp.media` (aiortc/av); `JingleRtpManager.available` uses
  `find_spec("aiortc")` and the engine is created on the first call
  (`_ensure_engine`), or eagerly in `startup` mode (`warmup`). `off` makes
  `available` false (and `warmup` a no-op) so aiortc is never imported and the
  call menus are hidden. The mode is passed to `JabberClient` from the config
  (`main_window`), which also fixes the previously dead `startup` option. The
  Preferences «Устройства» page also honours it: with `off` it shows a notice
  instead of importing `xmpp.media`/`device_test` (and calling
  `enumerate_devices`), so opening Preferences never pulls aiortc/av.
- `webengine_mode` (`full`/`no_preview`/`off`): `app.py` calls
  `constants.set_webengine_enabled(mode != "off")` before the window;
  `constants.webengine_available()` gates on it. `off` makes `ui/chat_view.py`
  skip the WebEngine import entirely (all chats use the `QTextBrowser`
  fallback — no Chromium stack, the biggest memory consumer). `no_preview` keeps
  WebEngine but forces media previews off (`MainWindow._media_preview_mode`);
  `full` follows `chat.media_preview`.
- `webengine_memory_mode` (`off`/`moderate`/`aggressive`): `app.apply_chromium_flags`
  sets `QTWEBENGINE_CHROMIUM_FLAGS` before `QApplication` (moderate =
  `--renderer-process-limit=1`, `--js-flags=--max-old-space-size=128` and the
  background-service disables; aggressive adds `--disable-gpu`); a user-set
  environment value is respected. `webengine_cache_mb` caps the default
  `QWebEngineProfile` HTTP cache (`ui/url_schemes.configure_default_profile`,
  also sets in-memory cookies and disables plugins/popups; a no-op without a
  live `QApplication`).
The OMEMO startup probe runs in a background thread started only **after** the
window is shown (`app.py`, ~200 ms), so it never starves the login window; the
`plugins.attention` manifest does not import `core.client` (so plugin discovery
never pulls aiortc), and QtWebEngine is imported lazily — `chat_widget` imports
`chat_view` only when a chat view is built, `main_window` imports `media_viewer`
only when a media viewer opens, and the media-preview mode uses the pure
`constants.webengine_available()` (`find_spec`) probe. `stanza_im/__init__.py`
sets `Qt.AA_ShareOpenGLContexts` before any `QApplication` so the lazy WebEngine
import is still legal; the `stanza`/`mam`/`xmpp` URL schemes are registered by
the idempotent `ui/url_schemes.ensure_registered()` (called by both WebEngine
importers). `tests/test_startup.py` guards this laziness,
`tests/test_performance_prefs.py` the settings.

Requires: Python 3.10+, PyQt6, PyQt6-WebEngine, slixmpp, qasync, defusedxml,
aiodns (SRV discovery).
System libs: libglib2.0, libgl1, libx11-6, libfontconfig1 (for PyQt6).
Distribution name: `stanza-im` (console script `stanza-im`, legacy `jabbim`
alias kept for compatibility).

## Commit Convention

Commit changes to the local git repository automatically after each logical unit
of work (one bug fix or feature = one commit). Match the commit message style of
the existing history (short imperative summary line). Do not commit secrets or
unintended files; check `git status` before committing. Specification updates
(see below) belong to the same commit as the change that made them stale.

A modified `README.md` in `git status` that was **not** authored by the current
task (the user edits it by hand) must never be ignored and never folded
silently into an unrelated commit: point it out to the user, propose committing
it, and keep it in a commit of its own once they agree.

**Author attribution.** A commit created by the agent MUST be stamped with the
model that produced it:

```bash
git commit --author="opencode (<model>) <opencode@localhost>" -m "<message>"
```

`<model>` is the short model id of the current session (`opencode/big-pickle` →
`big-pickle`), taken from the session prompt; if it cannot be determined, ask
the user instead of guessing. The repo-local `git oca` alias wraps exactly this
call and reads `$STANZA_MODEL` when set, so `STANZA_MODEL=big-pickle git oca -m
"…"` is equivalent. The committer stays the configured one (`opencode
<opencode@localhost>`), which keeps the user's own commits under their
identity and leaves `user.name`/`user.email` untouched. Verify the result with
`git log -1 --format='%an <%ae>'`.

**Existing history is never rewritten** — no `--reset-author`, `rebase`,
`filter-repo`: `master` tracks `origin/master`, so altering old authors would
change every hash and require a force-push.

## Documentation Maintenance

`AGENTS.md`, `SPEC.md`, `XEPs.md`, `CHECKLIST.md` and `FEATURES.md` are living
documents and MUST be updated in the same logical unit of work as any change
that makes them stale:

- supported XEP added/removed or used differently → `XEPs.md` (+ `SPEC.md` §14)
  and, when it is a XEP-0479 compliance extension, `CHECKLIST.md`;
- configuration keys, defaults or persisted paths → `AGENTS.md` (XDG) and
  `SPEC.md` §4;
- new/removed modules or files → both directory-structure blocks
  (`AGENTS.md` Directory Structure, `SPEC.md` §3);
- architecture, UI patterns, shortcuts or dependencies → `AGENTS.md` and
  `SPEC.md` (relevant section);
- new/removed **user-facing feature** → `FEATURES.md` (and, when it changes the
  XEP surface, `XEPs.md`).  `FEATURES.md` is the user-facing feature list: a
  Russian bulleted list of bold categories with short, jargon-free phrases
  describing what the user sees.  Keep it in that style — no XEP numbers, no
  internal mode names, no implementation jargon.  **Any change to `FEATURES.md`
  MUST be proposed to and approved by the user first** (a new bullet, a
  reworded one, a removal); never add entries unilaterally.  Only genuinely new
  user-visible capabilities belong there — a bug fix or the correction of an
  oversight (e.g. a dialog that used to block other windows) is **not** a
  feature and must not be listed.

Before committing, check `git status`: when a change affects any of the above,
the corresponding spec file must appear in the same commit. `tests/test_spec_sync.py`
guards the XEP list and the `CHECKLIST.md` structure automatically. Record the
documentation update in `.opencode/work-state.md` (`Completed`).

## Session State Protocol

Long sessions can overflow the context window and be compacted or reset; tool
output may then appear duplicated or mangled. To survive this, keep every
non-trivial task's objective, reasoning, decisions and progress on disk:

- **Persist before acting.** As soon as a task's plan is being formed — before
  the first source file is edited — write `.opencode/work-state.md` with
  `Ground truth`, `Objective`, `Analysis` (findings and root causes with
  `file:line` evidence), `Decisions`, `Plan (ordered)`, `In progress`,
  `Completed`, `Next` and `Traps`.
- **`Decisions` records the Q&A.** For every clarifying question, store the
  question, the user's answer and the chosen trade-off as the answer arrives —
  not only at the end.
- **Plan-mode exception.** `.opencode/work-state.md` may be written even while
  in read-only plan mode; it is the ONLY file that may be modified then. The
  directory is gitignored, so this never changes the repository.
- **After each mutating batch** (edits / tests / commits), rewrite the file,
  updating `Completed` with `file:line` anchors and refreshing
  `In progress` / `Next`.
- **At the start of every session** (including after a context reset or
  compaction), read `.opencode/work-state.md`, verify its `Ground truth` against
  `git status --short`, `git log --oneline -2` and the test exit codes, re-read
  `Objective` / `Analysis` / `Decisions` / `Plan`, then continue from
  `In progress`. On a **recreated container** the same routine applies, but the
  test environment must be activated first: `source .testenv/env.sh` (see
  [Headless Test Environment](#headless-test-environment)).
- Never trust recalled state or a printed "success": confirm with `git diff`,
  `git status`, exit codes and a `Read` of the edited region. A remembered
  commit may not exist — check `git rev-parse --verify <hash>`.

State-file template:

```
# Session State
updated: <ISO-8601>   HEAD: <hash> <subject>
## Ground truth    # repo, git/working-tree state, test exit codes, env
## Objective       # current task, 1-3 lines
## Analysis        # findings + root causes, with file:line evidence
## Decisions       # Q: <question> -> A: <answer> (chosen option)
## Plan (ordered)
## In progress
## Completed       # commits + file:line anchors
## Next
## Traps
```

`.opencode/` is gitignored, so the state file is never committed.

## Headless Test Environment

**The test environment is vendored inside the repository, in the gitignored
`.testenv/` directory** (~693 MB): the Python packages (`site-packages/`), the
rootless Qt/system libraries extracted from Debian `.deb` packages
(`qtlibs/`), the console scripts (`bin/`), plus `env.sh`, `README.md` and
`manifest.txt`. This sandbox has no root, so everything is unpacked into the
user tree and loaded via `LD_LIBRARY_PATH`.

```bash
source .testenv/env.sh          # must be sourced from bash; one command, any cwd
python3 tests/test_ui_tweaks.py
python main.py
```

`env.sh` exports the three `qtlibs` loader directories, `QT_QPA_PLATFORM`
(`offscreen` unless already set) and `STANZA_ENV`, and it recreates three
compatibility symlinks — `~/.local/qtlibs`, `~/.local/lib/python3.11/site-packages`
and `~/.local/bin` — so the invocation still quoted in the ~57 test docstrings
(`LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu QT_QPA_PLATFORM=offscreen python3 tests/…`)
and a plain `python3 tests/…` keep working untouched.

**Mandatory after a container rebuild or a context compaction:** read
`.testenv/README.md` and run `source .testenv/env.sh` **first**. While the
`.testenv/` directory exists, never reinstall packages, re-download `.deb`
files or re-extract the libraries — that is what the directory is for. Only if
it is missing (fresh clone, or the repository volume was not mounted into the
new container) rebuild it from `.testenv/README.md` → *Rebuild*; `manifest.txt`
lists the exact pinned versions (slixmpp 1.10.0, PyQt6 6.11.0, aiortc 1.15.0,
…) and the `.deb` package names.

`QtWebEngine` now loads (all deps present). Note the **test suite was written
for the `QTextBrowser` fallback** in some places (`test_history_window`,
`test_jump_button`, `test_xep0461` call `toHtml`/`toPlainText`/`_jump_button`);
with a working WebEngine those specific checks fail on the WebEngine class —
pre-existing, unrelated to feature work.

The test runner detects success by `All tests passed`, `FAILURES: none` or
`All <x> tests passed` (a few print `FAILURES: <list>` on failure).

<!-- CODE_BRAIN_MANDATORY -->
## Code Brain MCP - Mandatory when loaded

Use Code Brain MCP first for substantive tasks in this project.

- Start with `start_task(runIntake=true)` or `neural_sync`.
- Use `agent_plan` before `agent_code` for chunk and deep work.
- Use `memory_retrieve` at intake and `memory_store` at task end.
- Use `uncertainty_guard` before storing conclusions.
- Disable duplicate MCPs with `get_superseded_mcps`.
<!-- CODE_BRAIN_MANDATORY -->

