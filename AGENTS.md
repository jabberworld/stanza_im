# AGENTS.md — Stanza IM Architecture

## Language

**Always explain your work in Russian.** Every plan, progress note, status
update and any commentary addressed to the user MUST be in Russian.

This rule holds **after every context reset or session compaction**: `AGENTS.md`
is re-read then, so switch to Russian immediately rather than waiting to be
asked again.

Code, identifiers, code comments, commit messages and the documentation files
(`AGENTS.md`, `SPEC.md`, `XEPs.md`) stay in English as before.

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
│   ├── unread_state.py          # Persisted per-contact unread counters (JSON)
│   ├── vcard_cache.py           # vCard avatar download coordination
│   ├── discovery.py             # XEP-0065 proxy + STUN/TURN SRV discovery + cache
│   └── memstats.py              # Periodic memory statistics (CLI -m)
├── ui/
│   ├── main_window.py           # Main window: stack (login/splash/roster)
│   ├── login_widget.py          # Login form + config prefill/save
│   ├── roster_widget.py         # Custom-painted contact list
│   ├── roster_style.py          # QPainter roster rendering strategy
│   ├── chat_window.py           # Tab container for conversations
│   ├── chat_widget.py           # Single chat tab content
│   ├── chat_view.py             # QWebEngineView + QWebChannel bridge
│   ├── chat_themes.py           # Adium-style theme HTML generator
│   ├── nick_colors.py           # Session MUC nickname → color allocation
│   ├── preferences.py           # Settings dialog (icon nav, nested tabs)
│   ├── media_preview.py         # Inline image/audio/video previews
│   ├── media_viewer.py          # Fullscreen image/video viewer
│   ├── map_widget.py            # In-app OSM map window (geo: URIs, live track)
│   ├── upload_dialog.py         # HTTP upload / P2P progress dialog
│   ├── incoming_file_dialog.py  # Incoming Jingle file-offer confirmation
│   ├── call_window.py           # Call UI (incoming prompt, active call, Muji)
│   ├── device_test.py           # Devices self-tests (mic meter/tone/camera)
│   ├── status_message_dialog.py # Multiline presence status editor
│   ├── history_manager.py       # Per-contact history browser
│   ├── service_browser.py       # XEP-0030 service discovery browser
│   ├── certificate_dialog.py    # Server TLS certificate details dialog
│   ├── tray.py                  # System tray icon + blink
│   ├── osd.py                   # OSD on-screen notification stack
│   └── icons.py                 # LRU icon cache (lazy, auto-evict)
├── xmpp/
│   ├── message_styling.py       # XEP-0393 Message Styling parser
│   ├── jingle.py                # XEP-0234/0260/0261 Jingle FT + IBB
│   ├── jingle_rtp.py            # XEP-0167/0176 Jingle RTP calls + SDP bridge
│   ├── muji.py                  # XEP-0272 multiparty Jingle coordination
│   ├── media.py                 # aiortc media engine (capture/playback)
│   ├── bytestream.py            # SOCKS5 bytestream client + direct listener
│   └── socks5.py                # Dependency-free SOCKS5 CONNECT for the account proxy
├── include/
│   ├── constants.py             # Paths, VERSION, APP_NAME, XDG dirs
│   ├── enumerators.py           # XMPP show/icon/mood/activity maps
│   ├── pep.py                   # XEP-0080/0107/0108/0118 payloads + icon packs
│   ├── geo.py                   # RFC 5870 geo: URIs, Mercator math, track, tile cache
│   ├── xmpp_uri.py              # XEP-0147 xmpp: URI parse/build (RFC 5122)
│   ├── hats.py                  # XEP-0317 Hats + XEP-0392 HSLuv colour generation
│   └── utils.py                 # format_time, escape_html, etc.
├── i18n/
│   ├── __init__.py              # tr() function + auto language detection
│   ├── en.py                    # English strings (~530 keys)
│   └── ru.py                    # Russian strings
├── plugins/                     # (Future) Plugin system
resources/                       # Images, chat skins, sounds, etc.
old/                             # Original Jabbim code (reference only, gitignored)
README.md                        # Общее описание проекта (назначение, возможности, зависимости)
main.py                          # python main.py entry point
pyproject.toml                   # Package config (distribution: stanza-im)
AGENTS.md                        # This architecture guide (living document)
SPEC.md                          # Detailed specification (living document)
XEPs.md                          # Supported XEP list (living document)
```

Additional UI modules include `ui/preferences.py`, `ui/add_contact_dialog.py`,
`ui/conference_dialog.py`, `ui/muc_config_dialog.py` and
`ui/hats_dialog.py`. The conference dialog
provides conference joining,
XEP-0030 room browsing, room vCard requests and JID copying. Conference
servers are persisted in `connection.conference_servers`; XEP-0048 bookmark
names are preserved and used as the menu label with a localpart fallback.
The conference browser uses the names and metadata returned by the service's
`disco#items` response and does not issue one `disco#info` request per room.
vCard information dialogs are opened non-modally from async callbacks.
Chat and MUC tabs use separate `ChatThemeFactory` instances, while emoticon
sets are discovered from `resources/emoticons/*/smileys*.cfg`. Preferences
show a live preview of the selected emoticon set.

**Room management** (`ui/muc_config_dialog.py`): the MUC header carries a gear
button right after the bookmark (`ChatWidget._config_btn`), hidden on 1:1 tabs
and enabled only for owners/admins (`MainWindow._apply_muc_admin` derives our
affiliation from `_muc_users`). It opens a non-modal `MucConfigDialog` with three
tabs: «Участники» — a `QTreeWidget` grouped into Владельцы/Администраторы/
Зарегистрированные пользователи/Заблокированные (owner/admin/member/outcast)
with «Jabber ID» and «Примечание» columns (the note is the XEP-0045 `<reason>`)
and Add/Edit/Delete buttons (Delete sets affiliation `none`); «Шапки» —
XEP-0317 hats (see below); «Настройки» —
enabled for the owner only and hosts the `muc#owner` room-configuration
`DataFormWidget`. Edits are collected and applied on «Ок» via
`client.muc_set_affiliation`/`client.muc_set_config`; `client.muc_get_affiliations`
builds a custom `muc#admin` IQ so the `reason` survives (slixmpp's helper keeps
only JIDs). [`tests/test_muc_config.py`]

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
gains a gated «Шапка» submenu (after «Изменить роль») with «Назначить»
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

**MUC join reliability**: presence status lines (`muc_user_joined`/`left`/
`muc_status_changed`) are shown only after a successful join — `MainWindow`
tracks `_muc_joined`/`_muc_join_grace` and suppresses them until
`_on_muc_joined` plus a 2 s grace window, so the server's initial occupant dump
is never rendered as "X joined". Auto-joined rooms are retried on transient
`muc_join_error` conditions (`timeout`/`unknown`/`remote-server-timeout`/
`internal-server-error`/`service-unavailable`) with a 5/15/45 s backoff, and
`client._autojoin_bookmarks` re-fetches the bookmarks and skips only rooms that
actually joined (a stale `GroupChatInfo` no longer blocks a retry; `join_muc`
cancels a pending join task). A bookmarked room that is also a normal roster
contact is moved to the conferences group before joining
(`_classify_bookmarked_conferences`). [`tests/test_muc_join.py`]

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
services and uncategorized items. It discovers the account domain on open and
builds the tree fully lazily with no eager discovery: a node renders its
direct children "as is" from one `disco#items` request, every service item
shows a tentative expand arrow, and expanding or clicking a node issues its
own `disco#items` before the branch contents are drawn — nodes that return no
children lose their arrow. Deep items inherit the parent's icon (no per-child
`disco#info`); only the top level is classified via `disco#info` to drive the
category grouping. Disco requests (items/info) pass the parent's
`node` attribute so node-scoped services (e.g. gateways) resolve fully, and
items that equal their own parent (`jid`+`node`) are dropped to prevent
self-referencing loops. `Автообзор` recursively pre-loads the tree (bounded
depth, cycle-safe). Used servers are persisted in `connection.service_servers`.
Double-clicking a conference fills both room and server in `JoinConferenceDialog`
and runs the full join flow (server persistence, bookmark support).
`MainWindow._join_muc(..., server=…)` accepts the room localpart and server
separately and assembles `room@server` when the room carries no `@` — both
dialog callers pass `data["server"]`, so a join never sends a bare localpart
or a `remote-server-not-found` disco to the room name alone.
Chat avatar `<img>` elements carry `class="avatar"`; `ChatView.update_sender_avatar`
updates only `img.avatar`, never emoticon images in the same message.
`HistoryManagerDialog` (opened from the roster contact context menu and the
Actions menu) groups contacts with history by their roster groups or the
`core/known_contacts.py` registry (persisted JID → name/groups/conference flag
so removed contacts keep their names), shows per-day bold dates in a
`QCalendarWidget`, and supports day-scoped and all-time substring search
(`core/history.dates/load_day/search_dates`).

UI convention: context menus and menu-bar menus always use icons. Load them via
`MainWindow._menu_icon(name)` (search order: `ACTIONS_DIR_16` →
`CATEGORIES_DIR_16` → `STATUS_DIR_32` → `PLACES_DIR_22`); `SearchDialog._icon`
mirrors the first three dirs.

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
| Chat history (JSONL) | `$XDG_DATA_HOME/stanza-im/history/<bare-jid>.jsonl` (0600) |
| Unread counters (JSON) | `$XDG_DATA_HOME/stanza-im/unread.json` (0600) |

`Config` has nested-table helpers, so `config.ui.auto_connect = True` works.
Passwords are stored plaintext per user request (file is 0600). History is
appended line-by-line as JSON, keyed by bare JID, one file per contact.

### 3. Custom-Painted Roster (`roster_widget.py` + `roster_style.py`)

A plain `QWidget` renders all contacts via `paintEvent()` + `QPainter`. No
QTreeView or QListView — zero child widgets. This is extremely memory-efficient
and allows full visual control (avatars, status icons, unread badges, mood icons).

**Data model**: `GroupItem` and `UserItem` dataclasses. The widget maintains
flat lists and sorted dicts. Hit-testing iterates items by accumulated Y offset.
Groups sort case-folded, except the trailing groups (`set_trailing_groups`,
used by `MainWindow` for the conferences group) which always come last.

**Rendering strategy**: `RosterStyle` is a pluggable class. `set_style()` hot-swaps
the renderer. Heights are dynamic: contacts with status messages are taller.

**Mood/activity icons**: a roster row can carry the contact's PEP mood (XEP-0107)
and activity (XEP-0108) icons, drawn at 16px between the name and the unread
badge/avatar from the same icon set as the bottom-bar mood/activity picker
(`pep.mood_icon_path`/`pep.activity_icon_path`). `UserItem.mood`/`activity` are
seeded by `MainWindow._add_roster_item` from `client.pep_data` and kept live by
`MainWindow._on_contact_pep_updated`. Each element (avatar/activity/mood) is
togglable from Preferences → Appearance → «Ростер» via
`appearance.roster_show_avatars`/`roster_show_activity`/`roster_show_mood`
(default all `true`): `MainWindow._apply_roster_options` → `RosterStyle.set_options`
gates rendering live, no relayout.

### 4. Chat Rendering via QWebEngineView (`chat_view.py`)

Messages are rendered as HTML/CSS using Adium-compatible chat skins from
`resources/chatskins/`. A `QWebChannel` bridge (`_ChatBridge`) exposes Python
methods to JavaScript for link clicks, file transfer buttons, etc.

**Theme engine** (`chat_themes.py`): Loads HTML templates and CSS variants from
`resources/chatskins/minimal-mod/` or `candy/`. Templates use `%sender%`,
`%message%`, `%time%`, `%userIconPath%`, `%senderColor%` placeholders.

**Message Styling** (`xmpp/message_styling.py`, XEP-0393): `render(body, fragment)`
parses `*em*`/`_em_`/`~strike~`/`` `code` ``/pre/quote markup and calls `fragment`
only for plain spans (escape + URLs + emoticons; never inside `<code>`/`<pre>`).
`ChatThemeFactory.set_message_styling()` toggles it; `unstyled` messages and the
preferences switch both fall back to the plain pipeline. Feature advertised as
`urn:xmpp:styling:0`.

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
Real links and the `mam://load`
marker still request a navigation that is intercepted on the
C++ side by `_StanzaPage.acceptNavigationRequest` → `ChatView._accept_navigation`,
which emits `link_clicked` for the `stanza`/`mam`/`http`/`https`/`mailto`
schemes and denies the in-view load. The `stanza`/`mam` schemes are
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
the fallback when the transport is unavailable).
[`tests/test_jump_button.py`]

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
1:1 tab Esc closes it. `Ctrl+W` leaves a conference (with the optional confirm)
and closes a 1:1 tab.

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
auto-hiding after `osd_duration`; a pure `stack_position()` keeps the math
unit-testable. MainWindow triggers gate on `notifications.osd_enabled` and the
per-event toggles: `osd_message` (1:1 + private, only while the chat window is
not the active window on that conversation), `osd_typing`, `osd_status`
(`never`/`available`/`any`, skipping the initial presence sync),
`osd_conference` (`never`/`mention`/`all`), plus the `_notify_osd_file` entry
point wired for future p2p file transfers. The bubble (rounded background +
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
nothing is left.

Unread counters are persisted per contact (`core/unread_state.py` →
`$XDG_DATA_HOME/stanza-im/unread.json`) so the badges and tray blinking survive
a restart: `MainWindow` loads them at startup, applies them when building
roster rows (`_add_roster_item`/`_sync_conference_roster`), keeps them updated
in `_bump_unread`/`_reset_unread` and flushes them to disk with a 1 s debounce
plus on quit. Alongside each count the file stores the last displayed MDS
stanza-id (`{"count": N, "displayed": "sid"}`; the legacy `{"jid": N}` format is
still read); `_flush_unread` collects it from the client's `_mds_local` and
`_on_login` seeds it back via `client.set_displayed_state`, so the startup
XEP-0490 catch-up cannot clear unread messages that arrived after our own last
displayed point (a genuinely newer remote state still clears them). OSD popups
are not replayed. [`tests/test_unread_state.py`]

**Media previews** (`include/media.py`, `ui/media_preview.py`, `ui/media_viewer.py`):
`media_kind(url)` classifies URLs by extension (image/audio/video). The
`chat.media_preview` selector (`none`/`images`/`images_audio`/`all`, default
`images`) gates substitution: `ChatThemeFactory.set_media_preview(service, mode,
size)` makes `_body_fragment` replace a media URL's `<a>` with an embed —
`MediaPreviewService.markup()` returns an `<a class="stanza-media"
href="stanza:view:image/<urlenc>">` wrapping an `<img>` (cached thumbnail as a
PNG data-URI), or a native HTML5 `<audio>`/`<video controls>`. Image originals
are downloaded in a worker (`asyncio.to_thread`/thread) and resized to
`appearance.media_preview_size`; thumbnails and originals live in
`MediaCache` (`$XDG_CACHE_HOME/stanza-im/media/`, `index.json`, last-access
tracking) and are evicted by `appearance.media_cache_days` (TTL) and
`appearance.media_cache_mb` (LRU) on a 30-min timer plus one deferred pass
after startup (never blocking startup). The ready PNG data-URIs are held in a bounded
in-memory LRU (`MediaPreviewService._thumb_uris`, 16 MB budget), so a long
session with many images cannot grow the thumbnail cache without limit.
`thumbnail_ready` is pushed into every open
view via `ChatView.set_media_thumbnail` (in-place `src` swap, no document
reset). Clicking the preview emits `stanza:view:` → `MediaViewer` (image fitted
to the window; video in a WebEngine `<video>` window, `F11` fullscreen); the
WebEngine `contextMenuEvent` reads the request via
`QWebEngineView.lastContextMenuRequest()` (Qt 6; the old
`page().contextMenuData()` does not exist and silently fell back to the engine
menu) and always builds its own menu — never Chromium's. The media kind comes
from the `MediaType*` enum members, and for an embedded image the shareable
original URL is decoded from its `stanza:view:` link (the reported media URL is
only the data-URI thumbnail). Over media it keeps the
copy/Save as…/open viewer/fullscreen entries; otherwise it offers «Поделиться»
(«Share», only for `http(s)`), copy link / open in browser for a web link, copy
for a selection, and "Select all". Sharing (and an address-less
``xmpp:?message;body=…`` URI) opens `ShareDialog` — a checkable list of the
roster contacts and the conferences we are in — and sends each chosen target a
`«Переслано:»` line followed by the content as a XEP-0393 quote
(`compose_reply_body`); 1:1 targets are echoed locally via
`_display_local_outgoing` (and stored), conferences get a groupchat message. Previews are
off when QtWebEngine is unavailable. Settings changes re-render open chats via
`ChatWindow.rerender_messages()`. The `MediaViewer` window fits the image after
`showEvent` (a cached original returns before layout, so the initial fit is
deferred) and persists its geometry/position in the shared `media_viewer`
config section (image and video viewers share it). Covered by
`tests/test_media.py`.

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
to `"online"`.

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
fetch apply remote displayed states — unread is cleared and an open chat gets
an "Displayed on another device" status line. `_mds_apply_remote` skips a state
equal to the one already recorded in `_mds_local`; that map is seeded at connect
from the persisted unread state, so the startup catch-up does not wipe restored
unread (see the unread-counters paragraph above).

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
conference join dialog (prepopulating room+server and persisting the server),
`?roster`/`?subscribe` open `AddContactDialog` prefilled with the JID. An
address-less `xmpp:?message;body=…` (no JID) opens `ShareDialog` with that body
instead.
Unrecognized actions warn the user. The vCard dialog shows its JID with an
icon-only copy button right beside the address (toolbar-style
`QToolButton`, `copy.svg` in `ACTIONS_DIR_16`, tooltip "Copy XMPP address",
`make_xmpp_uri(jid)` → clipboard); the conference roster context menu's
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

HTTP File Upload (XEP-0363): a toolbar above the chat input carries icon
buttons for Clear, History (moved from the tab header), vCard and "Send file"
(a menu with "P2P" / "P2P IBB" / "HTTP Upload"); the input is vertically
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
displays them locally via `_display_local_outgoing` (no carbons echo reaches
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
file. `"P2P IBB"` uses **Jingle In-Band (XEP-0261/0047)** immediately; `"P2P"`
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
`location` fields, updated live through `_on_contact_pep_updated`).

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
Per XEP-0353 the `propose` targets the peer's **bare** JID while the responses
(`proceed`/`reject`/`retract`) and the `session-initiate` are addressed to the
**full** JID of the resource that accepted (the `proceed` sender) — a peer with
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
per presence via `_load_caps`). STUN/TURN come from `client.ice_servers()`
(XEP-0215 `urn:xmpp:extdisco:2` → the connection settings' STUN/TURN endpoint →
SRV discovery). The «Звонок» call menu is a submenu in the roster contact
context menu and an icon-only button in the chat toolbar (both enabled only for
capable contacts). For a **conference** contact the roster «Звонок» submenu
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
over the roster); remote video frames are painted by `VideoView`, which draws a
translucent nickname caption over the image. Every call control is **icon-only**
(tooltips instead of labels) using the 16px glyphs in
`resources/images/16x16/actions/` via `call_window._icon`: `mic`/`mic-off`,
`camera`/`camera-off` (the camera is a webcam glyph), `speaker`/`speaker-off`,
a red `call-hangup` and a green `call-accept`. The mute/camera buttons toggle
the **outgoing** capture — the muted
microphone sends silence and the switched-off camera sends black frames
(`set_audio_enabled`/`set_video_enabled`, no renegotiation, tracks stay
attached), while received audio/video keeps playing and the remote view is
never hidden. Preferences
gains a **Devices** page
(`devices.audio_input/audio_output/video_input`, enumerated with Qt
Multimedia). The page also hosts **self-tests** (`ui/device_test.py`): a live
microphone peak meter, a speaker test tone and a camera preview window,
disabled while a call owns the devices. The self-test controls are icon-only
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
PNG masked to a circle, filled by `MainWindow._muji_avatar` →
`set_avatars`) before the nick and **three**
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

Preferences use icon navigation and nested tabs. The Appearance page is split
into «Темы», «Ростер», «Шрифты», «Цвет» and «Разное» («Ростер» toggles the
roster avatars/activity/mood, see §3; «Разное» holds the media-preview size,
the preview cache TTL/limit and the MUC mention highlight mode). `Apply` applies
settings without closing the dialog. Chat shortcuts include Enter/Ctrl+Enter, Esc,
Ctrl+PgUp/Ctrl+PgDown, Ctrl+1..9 and Ctrl+W. Contact context menus provide
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

**Widget fonts** (`appearance.{roster,chat,osd,nick,participant}_font` +
`{...}_font_size`, pt; `""`/`0` = Qt default): applied live from Preferences.
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
`ChatWindow._participant_font`). In the preferences «Шрифты» tab, empty/zero
values show the *real* font Qt would use instead: the family combo's first
entry reads «По умолчанию — <family>» (for nicknames following the chat
font live) and the size spin shows «<size> pt (по умолчанию)» via
`setSpecialValueText`, both resolved from `QApplication.font()` by
`PreferencesDialog._default_app_font` while the stored value stays `""`/`0`.
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

### 9. Thrifty traffic — Stream Management & CSI (XEP-0198/0352)

- `connection.stream_management` (default on) registers `xep_0198`: slixmpp
  enables SM after bind and resumes a dropped stream (`session_resumed`)
  without re-auth/roster/presence, replaying unacked stanzas.
  `JabberClient.resume_expected()` drives the UI: while resume is possible
  MainWindow shows "Переподключение…" and then "Соединение восстановлено";
  "Disconnected" appears only on `sm_failed`/`sm_disabled`.
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

1. **IconCache**: max 200 entries, 60s TTL, auto-eviction every 30s
2. **Avatars**: stored as `str` path, QPixmap created in paintEvent, never cached long-term
3. **ChatView**: shared `QWebEngineProfile` (not per-tab)
4. **Idle tab suspension**: `chat.idle_unload_minutes` (default `10`, `0` = off,
   Preferences → Chat → «General»). `MainWindow._maybe_suspend_tabs` (per-minute
   timer) asks `ChatWindow.suspend_tab` for tabs that are not current, have no
   unread message and saw no activity within the window; `ChatWidget.suspend`
   frees the `ChatView`/WebEngine page and swaps in a `_NullView` stub (messages
   keep accumulating in Python), while `resume` (lazy, on tab activation)
   rebuilds the view and re-renders `_history`/`_messages`.
   [`tests/test_tab_suspend.py`]
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
8. **Housekeeping**: a 30-min `MainWindow._trim_main_process_memory` runs
   `gc.collect()` + glibc `malloc_trim(0)` (also right after a tab closes or is
   suspended) to return freed main-process heap to the OS; WebEngine renderers
   are separate processes and are unaffected.

## Running

```bash
python main.py              # Direct
python -m stanza_im         # Module
```

Command-line keys: `-d/--debug` (console debug output), `-x/--xml` (raw
SEND/RECV XML), `-l/--log` (full debug log to `stanza-im.log`), `-m/--memstat`
(periodic memory statistics), `-h/--help`. `app.prepare_qt_argv()` re-prepends
the program name before `QApplication` — QWebEngine aborts on an empty argv.

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

## Documentation Maintenance

`AGENTS.md`, `SPEC.md` and `XEPs.md` are living documents and MUST be updated in
the same logical unit of work as any change that makes them stale:

- supported XEP added/removed or used differently → `XEPs.md` (+ `SPEC.md` §14);
- configuration keys, defaults or persisted paths → `AGENTS.md` (XDG) and
  `SPEC.md` §4;
- new/removed modules or files → both directory-structure blocks
  (`AGENTS.md` Directory Structure, `SPEC.md` §3);
- architecture, UI patterns, shortcuts or dependencies → `AGENTS.md` and
  `SPEC.md` (relevant section).

Before committing, check `git status`: when a change affects any of the above,
the corresponding spec file must appear in the same commit. `tests/test_spec_sync.py`
guards the XEP list automatically. Record the documentation update in
`.opencode/work-state.md` (`Completed`).

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
  `In progress`.
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

This sandbox has no root, so PyQt6's system deps (libGL, libglib, libx11, etc.)
were extracted from Debian `.deb` packages into `~/.local/qtlibs` and loaded via
`LD_LIBRARY_PATH`:

```bash
export LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
export QT_QPA_PLATFORM=offscreen   # run GUI without a display
python main.py
```

Note: `QtWebEngine` cannot load here (missing `libnss3` on the local apt mirror),
but `chat_view.py` falls back to `QTextBrowser` gracefully. All other Qt modules
(core, gui, widgets, webchannel) work offscreen.

<!-- CODE_BRAIN_MANDATORY -->
## Code Brain MCP - Mandatory when loaded

Use Code Brain MCP first for substantive tasks in this project.

- Start with `start_task(runIntake=true)` or `neural_sync`.
- Use `agent_plan` before `agent_code` for chunk and deep work.
- Use `memory_retrieve` at intake and `memory_store` at task end.
- Use `uncertainty_guard` before storing conclusions.
- Disable duplicate MCPs with `get_superseded_mcps`.
<!-- CODE_BRAIN_MANDATORY -->

