# AGENTS.md — Stanza IM Architecture

## Overview

Stanza IM is a lightweight XMPP/Jabber desktop client for Linux, inspired by the
original Jabbim client (2007-2012). Written in Python 3 + PyQt6 + slixmpp.
The supported XMPP extensions are listed in `XEPs.md`.

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
│   ├── client.py                # JabberClient: slixmpp wrapper
│   ├── storage.py               # Config (TOML) + JSONL chat history (XDG)
│   ├── history.py               # SQLite chat-history queries (dates/load_day/search)
│   ├── known_contacts.py        # Persisted JID → name/groups/conference registry
│   └── vcard_cache.py           # vCard avatar download coordination
├── ui/
│   ├── main_window.py           # Main window: stack (login/splash/roster)
│   ├── login_widget.py          # Login form + config prefill/save
│   ├── roster_widget.py         # Custom-painted contact list
│   ├── roster_style.py          # QPainter roster rendering strategy
│   ├── chat_window.py           # Tab container for conversations
│   ├── chat_widget.py           # Single chat tab content
│   ├── chat_view.py             # QWebEngineView + QWebChannel bridge
│   ├── chat_themes.py           # Adium-style theme HTML generator
│   ├── tray.py                  # System tray icon + blink
│   ├── osd.py                   # OSD on-screen notification stack
│   └── icons.py                 # LRU icon cache (lazy, auto-evict)
├── xmpp/
│   └── message_styling.py       # XEP-0393 Message Styling parser
├── include/
│   ├── constants.py             # Paths, VERSION, APP_NAME, XDG dirs
│   ├── enumerators.py           # XMPP show/icon/mood/activity maps
│   └── utils.py                 # format_time, escape_html, etc.
├── i18n/
│   ├── __init__.py              # tr() function + auto language detection
│   ├── en.py                    # English strings (~150 keys)
│   └── ru.py                    # Russian strings
├── plugins/                     # (Future) Plugin system
resources/                       # Images, chat skins, sounds, etc.
old/                             # Original Jabbim code (reference only, gitignored)
main.py                          # python main.py entry point
pyproject.toml                   # Package config (distribution: stanza-im)
XEPs.md                          # Supported XEP list (living document)
```

Additional UI modules include `ui/preferences.py`, `ui/add_contact_dialog.py`
and `ui/conference_dialog.py`. The latter provides conference joining,
XEP-0030 room browsing, room vCard requests and JID copying. Conference
servers are persisted in `connection.conference_servers`; XEP-0048 bookmark
names are preserved and used as the menu label with a localpart fallback.
The conference browser uses the names and metadata returned by the service's
`disco#items` response and does not issue one `disco#info` request per room.
vCard information dialogs are opened non-modally from async callbacks.
Chat and MUC tabs use separate `ChatThemeFactory` instances, while emoticon
sets are discovered from `resources/emoticons/*/smileys*.cfg`. Preferences
show a live preview of the selected emoticon set.
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

`Config` has nested-table helpers, so `config.ui.auto_connect = True` works.
Passwords are stored plaintext per user request (file is 0600). History is
appended line-by-line as JSON, keyed by bare JID, one file per contact.

### 3. Custom-Painted Roster (`roster_widget.py` + `roster_style.py`)

A plain `QWidget` renders all contacts via `paintEvent()` + `QPainter`. No
QTreeView or QListView — zero child widgets. This is extremely memory-efficient
and allows full visual control (avatars, status icons, unread badges, mood icons).

**Data model**: `GroupItem` and `UserItem` dataclasses. The widget maintains
flat lists and sorted dicts. Hit-testing iterates items by accumulated Y offset.

**Rendering strategy**: `RosterStyle` is a pluggable class. `set_style()` hot-swaps
the renderer. Heights are dynamic: contacts with status messages are taller.

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
body)` (each field percent-encoded, joined with `/`). Clicking it — like any
link, MUC mention or `mam://load` marker — requests a navigation that is
intercepted on the C++ side by `_StanzaPage.acceptNavigationRequest` →
`ChatView._accept_navigation`, which emits `link_clicked` for the
`stanza`/`mam`/`http`/`https`/`mailto` schemes and denies the in-view load.
The `stanza`/`mam` schemes are pre-registered as app-handled with
`QWebEngineUrlScheme.registerScheme` (`_register_custom_url_schemes`) so
Chromium never starts (and errors on) a real load; a denied navigation is
thus harmless. A stray `loadFinished(false)` from a blocked link is
self-healed by `_on_load_finished`/`_probe_chat_alive`, which verifies that
`#chat` survived and un-wedges the pending-message buffer; if the document was
truly wiped it reloads the empty page and emits `document_lost`, which makes
`ChatWidget._restore_after_document_lost` re-render the whole conversation
instead of leaving a blank chat. `refresh_avatars`
updates avatar `<img>` elements in place instead of clearing the whole
document, so avatar caching can never stall live rendering.
No QWebChannel call, console mirror or JS click handler is involved, so clicks
reach Python even when the WebChannel transport is unavailable. The
`qwebchannel.js` glue (Qt `:/qtwebchannel` resource, falling back to
`resources/qwebchannel.js`) is kept only for scroll/jump reporting. Clicking
reply inserts the referenced message into the input as an XEP-0421 quote block
(`> Sender wrote:\n> text`) with the cursor below it; a banner remains as an
indicator and `×` cancels (removing the inserted quote).
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
Feature advertised as `urn:xmpp:reply:0`.

**MUC mentions & Tab completion**: in groupchats the incoming sender name is
rendered as a clickable `stanza:mention:` link (`render_message(mention=...)`,
enabled via `ChatView.mention_senders`); clicking it inserts `nick: ` into the
input with focus (`ChatWidget._handle_mention_uri`). Like reply and ordinary
links, the mention is a plain anchor whose click reaches Python through the
`acceptNavigationRequest` interception (no JS/bridge involved). `Tab`/`Shift+Tab`
in a MUC input
completes the nick before the cursor and cycles the candidate list on repeat
presses: a nick starting the line is inserted as an address (`nick: `),
mid-line only the bare nick is completed; the previous token is replaced so the
cycle wraps correctly (`ChatWidget._tab_complete_nick`). `Esc` in the chat
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
point wired for future p2p file transfers.

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
announces `urn:xmpp:mds:server-assist:0`); incoming PEP events and a catch-up
fetch apply remote displayed states — unread is cleared and an open chat gets
an "Displayed on another device" status line.

Last Message Correction (XEP-0308): any own message is editable (Ctrl+Up =
last sent; the message menu's "Edit" button for `data-stanza-outgoing` wrappers
stores the referenced id in `window.__stanzaEditRef`, which the always-running
scroll poll delivers to Python as a `stanza:edit:<id>` ``link_clicked`` —
editing never navigates, so the chat document is never reset); the body loads
into the input with a cancelable editing banner and `_send` emits
`message_edit_sent`, so the client sends `<replace id='…'/>` (fresh stanza id)
and replaces the message locally (1:1) or via the MUC echo. A post-click
content probe (`_schedule_content_probe`/`_verify_after_click`) restores the
window via `document_lost` if the conversation vanished. Incoming corrections
replace (edited flag + a large bold «✎» appended right after the edited phrase
via `render_message(edited=True)`, `chat.allow_incoming_edits` on) or arrive
as new messages (off). History gains `message_id`/`edited` columns and
`replace_message()`.

Preferences use icon navigation and nested tabs. `Apply` applies settings
without closing the dialog. Chat shortcuts include Enter/Ctrl+Enter, Esc,
Ctrl+PgUp/Ctrl+PgDown, Ctrl+1..9 and Ctrl+W. Contact context menus provide
checkable group assignment and creation of new groups.

## Memory Management Rules

1. **IconCache**: max 200 entries, 60s TTL, auto-eviction every 30s
2. **Avatars**: stored as `str` path, QPixmap created in paintEvent, never cached long-term
3. **ChatView**: shared `QWebEngineProfile` (not per-tab)
4. **Inactive MUCs**: planned — reduce resources after 10min idle
5. **Roster**: no child widgets, single QPainter pass

## Running

```bash
python main.py              # Direct
python -m stanza_im         # Module
```

Requires: Python 3.10+, PyQt6, PyQt6-WebEngine, slixmpp, qasync, defusedxml.
System libs: libglib2.0, libgl1, libx11-6, libfontconfig1 (for PyQt6).
Distribution name: `stanza-im` (console script `stanza-im`, legacy `jabbim`
alias kept for compatibility).

## Commit Convention

Commit changes to the local git repository automatically after each logical unit
of work (one bug fix or feature = one commit). Match the commit message style of
the existing history (short imperative summary line). Do not commit secrets or
unintended files; check `git status` before committing.

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

## Test Account

JID: `jabbim-test@linuxoid.in` / Password: `WyVwukeWiPr0U`
