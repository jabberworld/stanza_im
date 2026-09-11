# SPEC.md — Stanza IM Specification

## 1. Overview

Stanza IM is a desktop XMPP/Jabber client for Linux, inspired by the original
Jabbim (2007-2012). It provides a classic two-panel IM experience: a roster
(contact list) panel on the left, and a tabbed chat area on the right.

**Target platform**: Linux (Debian 12+, Ubuntu 22.04+)
**Stack**: Python 3.10+, PyQt6, PyQt6-WebEngine, slixmpp, qasync, defusedxml

## 2. Launch

```bash
python main.py           # from project root
python -m stanza_im      # as module
```

Entry point: `main.py` → `stanza_im.app.run()` → creates QApplication + qasync
event loop (`qasync.QEventLoop`), creates MainWindow, enters loop.

## 3. File Structure

```
stanza_im/
├── app.py              — QApplication + qasync event loop
├── core/
│   ├── client.py       — XMPP client wrapper (slixmpp)
│   ├── storage.py      — Config (TOML) + JSONL chat history (XDG)
│   ├── history.py      — SQLite chat-history access (day/summary queries)
│   ├── known_contacts.py — persisted JID → name/groups/conference registry
│   └── vcard_cache.py  — vCard avatar download/cache coordination
├── ui/
│   ├── main_window.py  — Main window (3-page stack), actions and menus
│   ├── login_widget.py — Login form + config prefill/save
│   ├── roster_widget.py— Custom-painted contact list
│   ├── roster_style.py — QPainter rendering strategy
│   ├── chat_window.py  — Tab container for conversations
│   ├── chat_widget.py  — Single chat tab (header + view + input)
│   ├── chat_view.py    — QWebEngineView + JS bridge (QTextBrowser fallback)
│   ├── chat_themes.py  — Adium-style HTML generator
│   ├── preferences.py  — Settings dialog (icon navigation, nested tabs)
│   ├── conference_dialog.py — Join + XEP-0030 conference browser
│   ├── service_browser.py   — XEP-0030 service discovery browser
│   ├── history_manager.py   — Per-contact history browser
│   ├── vcard_dialog.py, search_dialog.py, registration_dialog.py,
│   ├── adhoc_dialog.py, add_contact_dialog.py, data_form_widget.py
│   ├── tray.py         — System tray icon
│   └── icons.py        — LRU icon cache
├── xmpp/               — Protocol helpers (message_styling.py = XEP-0393 parser)
├── i18n/               — Translation dicts (en.py, ru.py)
├── include/            — Constants (XDG paths), enumerators, utilities
└── plugins/            — (future)
```

Additional dialogs include `ui/preferences.py`, `ui/add_contact_dialog.py`
and `ui/conference_dialog.py`. Conference discovery uses XEP-0030; used
conference servers are stored in `connection.conference_servers`. XEP-0048
bookmark names are preserved and used in the Bookmarks menu with a localpart
fallback.
The conference browser consumes room names and metadata directly from
`disco#items`; it does not probe every room individually. Contact and room
vCard dialogs are opened asynchronously without nested modal event loops.
Appearance settings support independent ordinary-chat and conference theme
variants. Emoticon sets are discovered from cfg files under
`resources/emoticons`, and the settings dialog previews up to ten images from
the selected set.
The service browser uses XEP-0030 discovery, groups identities by category and
builds the tree fully lazily with no eager discovery: a node renders its direct
children "as is" from a single `disco#items` request (with the parent's `node`
attribute forwarded, so node-scoped gateways/services resolve fully), every
service item shows a tentative expand arrow immediately, and expanding or
clicking a node issues its own `disco#items` before the branch contents are
drawn — nodes that return no children lose their arrow. Deep items inherit the
parent's icon; only the top level is classified via `disco#info` to drive the
category grouping. Items that repeat their own parent (`jid`+`node`) are
dropped to avoid self-referencing loops.
`Автообзор` recursively browses the whole tree with a bounded depth. Used
servers are stored in `connection.service_servers`. Double-clicking a
conference pre-fills both room and server in the join dialog, which completes
the standard join flow (server persistence and bookmark support). Emoticon
replacement uses one non-overlapping match pass so generated image HTML is not
processed again as text. Chat avatar images are tagged `class="avatar"` so
avatar updates never overwrite emoticon images inside a message.

## 4. Configuration & Persistence

Follows the XDG Base Directory spec. All files created with **0600** perms.

| Path | Location |
|------|----------|
| Config (TOML) | `$XDG_CONFIG_HOME/stanza-im/config.toml` |
| Chat history (JSONL) | `$XDG_DATA_HOME/stanza-im/history/<bare-jid>.jsonl` |
| Chat history (SQLite) | `$XDG_DATA_HOME/stanza-im/history/` |
| Cache | `$XDG_CACHE_HOME/stanza-im/` |

- Config uses nested tables: `config.ui.auto_connect`, `config.account.password`, ...
- Password stored **plaintext** (explicit user decision); file permissions 0600
- History appended line-by-line as JSON, one file per bare JID

## 5. Main Window (`ui/main_window.py`)

Layout: `QMainWindow` with a `QStackedWidget` containing three pages:

| Page | Index | Content |
|------|-------|---------|
| Login | 0 | `LoginWidget` — JID, password, status, connect |
| Splash | 1 | Progress bar + status label + Cancel button |
| Roster | 2 | Status combo + search bar + `RosterWidget` in `QScrollArea` |

Window properties:
- Title: "Stanza IM" (with unread count prefix when applicable)
- Minimum size: 280×500, default: 300×600
- Close button hides to tray instead of quitting
- Tray icon always visible

### 5.1 State Transitions

```
Login → (connect) → Splash → (success) → Roster
Splash → (failure) → Login (with error message)
Roster → (close) → Tray (hidden)
Tray → (show) → Roster
```

## 6. Login Form (`ui/login_widget.py`)

Widgets:
- Logo image (from `resources/images/logo.png`)
- JID input (`QLineEdit`, placeholder "user@server")
- Password input (`QLineEdit`, echo=Password)
- Status combo (`QComboBox`): Online, Chatty, Away, XA, DND (with icons)
- "Save password" checkbox
- "Auto connect" checkbox (enabled only when save is checked)
- Connect button (default, triggers on Enter in JID/password)
- Info/error label

Signal: `login_requested(jid, password, show)`

### 6.1 Config Integration

- On startup, `_load_config()` prefills JID, password (if saved) and
  auto-connect checkbox from `config.toml`
- On connect, `_save_config()` writes lasted JID / password / status / flags
- `should_auto_connect()` — auto-connect on launch

## 6.2 Roster Events (client → UI)

The XMPP client emits diff-based roster events:

| Event | Description |
|-------|-------------|
| `roster_received(items)` | Initial roster download finished |
| `roster_item_added(item)` | New contact (subscription change) |
| `roster_item_removed(jid)` | Contact removed |

Presence is aggregated per **bare JID** across resources — best `show` wins
via `SHOW_ORDER`; empty/`available` normalized to `"online"`.

## 7. Roster (`ui/roster_widget.py` + `ui/roster_style.py`)

### 7.1 Data Model

```python
@dataclass
class GroupItem:
    name: str
    expanded: bool = True
    online_count: int = 0
    total_count: int = 0

@dataclass
class UserItem:
    jid: str
    name: str
    group: str
    status: str = "offline"
    status_message: str = ""
    icon_key: str = "offline"
    avatar_path: str | None = None
    unread_count: int = 0
    mood: str = ""
    meta_parent_jid: str | None = None
```

### 7.2 Rendering

Custom `paintEvent()` draws all items. No child widgets.

**Group header**: Background stripe (AlternateBase), expand/collapse arrow,
bold group name, online/total count "(3/7)" on the right.

**User item**: Status icon (16×16) + avatar placeholder (24×24) + name (bold) +
status message (italic, gray, truncated to 40 chars) + unread badge (red rounded rect).

Dynamic height: 32px without status message, 52px with.

### 7.3 Interactions

| Action | Trigger |
|--------|---------|
| Expand/collapse group | Left-click on group header |
| Select contact | Left-click on user item |
| Clear selection | Left/right-click on empty roster space |
| Open chat | Double-click on user item |
| Context menu | Right-click on user item (opens once via `contextMenuEvent`) |
| Search | Text in search input (filters by name/jid) |
| Keyboard: Enter | Open chat for selected contact |
| Keyboard: Delete | Context menu for selected contact |

Context menu differs for conferences (items in `_conference_roster` /
`_muc_self_nicks`): «Переименовать», «Группа» and
«Повторить запрос авторизации» are hidden, and «Удалить контакт» becomes
«Покинуть конференцию» (`ctx_leave_conference`) which leaves the MUC
(`_on_muc_leave`) and closes its tab.

### 7.4 Strategy Pattern

`RosterStyle` is pluggable via `set_style()`. The default renderer handles
avatar, name, status icon, status message, unread badge.

Future: hot-swappable styles from `resources/rosterstyles/`.

## 8. Chat Window (`ui/chat_window.py`)

### 8.1 Modes

Configurable via settings (Phase 2):

| Mode | Behavior |
|------|----------|
| Standalone | Separate `QMainWindow`, hides when no tabs |
| Embedded | `QWidget` inside MainWindow splitter |

Default: standalone.

### 8.2 Tab Management

- Custom `_TabBar` with middle-click close and mouse-wheel cycling
- Close button in corner widget
- Tab tooltip shows full JID
- `Ctrl+1..9` for direct tab access (Phase 2)
- `Ctrl+Tab` / `Ctrl+Shift+Tab` for next/prev (native Qt)
- Tab label: display name (MUC: prefixed with room icon)
- Ctrl+PgUp/Ctrl+PgDown cycle tabs; Ctrl+1..9 selects a tab and Ctrl+W closes
  or leaves it.
- Esc on a conference collapses it back to the roster **without leaving it**:
  the tab is removed but the room stays joined (`ChatWindow._on_escape` →
  `close_chat`, no `muc_leave_requested`); other tabs keep the window open,
  it hides only once the last tab is closed.
- For 1-on-1 chats Esc and Ctrl+W both close the tab; for MUCs Ctrl+W is the
  equivalent of "Leave conference" (with `muc_confirm_leave` when enabled).

### 8.3 Tab Lifecycle

| Event | Action |
|-------|--------|
| Open chat | Create `ChatWidget`, add tab, focus input |
| Close tab | Remove tab, cleanup widget |
| Last tab closed | Hide window |
| New incoming message | Create tab if needed, add message, blink tray |

## 9. Chat Widget (`ui/chat_widget.py`)

Single conversation tab. Layout:

```
┌─────────────────────────────────────┐
│ Name Label          Status Label    │ ← contact info header
├─────────────────────────────────────┤
│                                     │
│         ChatView (QWebEngine)       │ ← messages
│                                     │
├─────────────────────────────────────┤
│ [Input: QTextPlainTextEdit] [Send]  │ ← input bar
└─────────────────────────────────────┘
```

- Input: `QPlainTextEdit`, max height 60px, placeholder "Send"
- Send on Enter (without Shift), Shift+Enter for newline
- Signal: `message_sent(jid, body)`

### 9.1 Slash Commands

- `/me <action>` (XEP-0245): intentionally NOT intercepted — the body goes to
  the wire unchanged (`<body>/me laughs</body>`). Rendering matches the first
  four characters `/me ` only, so `/meshrugs`, `/me's` or a leading space are
  plain messages. Any render path (live, re-render, history pagination, MAM
  prepend) presents such bodies as an italic action line `* sender phrase`
  (`ChatThemeFactory.render_action`, CSS class `.stanza-action`) on the
  WebEngine backend and as an italic rich-text line on the QTextBrowser
  fallback. The sender is the contact name / `Me` for 1-on-1 and the room nick
  for MUC. Tray popups strip the prefix and show `* sender phrase`. The phrase
  still goes through the plain fragment pipeline (escaped, URLs/emoticons
  clickable), but never through XEP-0393 styling.
- `/nick <nick>` (MUC only): intercepted locally — nothing is sent to the
  room. The conference is re-joined with the new nickname using the stored
  room password (`client.join_muc`). Per XEP-0045 §17.1 a room nickname is a
  resourcepart: it must be non-empty (not invisible/whitespace-only), may
  contain `@`, `\` and spaces, but must not contain control characters, `/`
  (the resource separator) or exceed 1023 UTF-8 bytes (RFC 7622). A busy
  nickname reverts to the old one with a `muc_nick_busy` status (user-initiated
  changes never auto-append underscores). Other `/...` commands are not special
  and are sent as-is.

## 10. Chat View (`ui/chat_view.py`)

### 10.1 QWebEngineView Mode (default)

- Uses `QWebEngineView` + `QWebChannel` for Python↔JS communication
- `_ChatBridge` QObject exposed to JS as "bridge"
- Bridge methods: `on_link_clicked(url)`, `on_ft_accept(sid)`, `on_ft_reject(sid)`
- Messages added via `page().runJavaScript()` — creates div, inserts before the
  typing slot, auto-scrolls
- A permanent `#stanza-typing-slot` (`min-height`) sits at the bottom of `#chat`;
  the typing indicator only changes its `textContent`, so "пишет…"
  appearing/disappearing never shifts the chat
- Typing clears on any non-composing chat state (including `gone`) and is
  re-shown when composing resumes
- Shared `QWebEngineProfile` across all views (memory optimization)

### 10.2 QTextBrowser Fallback

When QWebEngine is not available, falls back to `QTextBrowser` with plain HTML
appending. No CSS themes, but functional. The typing block is marked and removed
on clear; new messages are inserted before it (no stale "пишет…" lines).

### 10.3 Chat States (XEP-0085)

`gone` sets the window title and chat header status to
«пользователь закрыл чат» (`chat_activity_gone` i18n key); any later non-`gone`
state clears it. MUC chats ignore remote activity. Closing a chat tab
(`close_chat`) discards the stored remote activity, so reopening the tab starts
with a clean title and header.

## 11. Chat Themes (`ui/chat_themes.py`)

### 11.1 Template System

Adium-compatible chat skins from `resources/chatskins/`.

Default skin: `minimal-mod/`

Template files:
- `Incoming/Content.html` — first message from contact
- `Incoming/NextContent.html` — consecutive message from same contact
- `Outgoing/Content.html` — first message from self
- `Outgoing/NextContent.html` — consecutive message from self
- `Status.html` — system/status messages
- `main.css` — base stylesheet
- `Variants/*.css` — 27 color variant stylesheets

### 11.2 Template Variables

| Variable | Description |
|----------|-------------|
| `%sender%` | Sender display name |
| `%message%` | Message body (HTML) |
| `%time%` | Timestamp (hh:mm:ss) |
| `%senderColor%` | Color for sender name |
| `%userIconPath%` | Path to user's buddy icon |
| `%textbackgroundcolor{0.75}%` | Background with opacity |

### 11.3 Rendering Pipeline

1. `ChatThemeFactory.render_message()` fills template variables
2. `ChatView.add_message()` wraps in JSON, calls JS `addMessage`
3. JS creates `<div>`, appends to `#chat`, scrolls to bottom
4. Auto-scroll only if user was near bottom

### 11.4 Message Styling (XEP-0393)

When enabled (Preferences → Chat), `xmpp/message_styling.py` parses the plain
text body first: `*strong*`, `_em_`, `~strike~`, `` `code` ``, ```` ``` ````
(pre) and `>` (blockquote). The styling fragment hook escapes text, links URLs
and swaps emoticons for the remaining plain spans only — never inside
`<code>`/`<pre>`. Incoming messages that carry `<unstyled/>` (or the setting
being off) fall back to the plain pipeline. Supported feature is advertised as
`urn:xmpp:styling:0`.

### 11.5 Message Replies (XEP-0461)

The per-message reply trigger is an anchor
(`<a href="stanza:reply:%REPLY_TARGET%">`, placeholder filled by
`ChatView._mark_message` via `_compose_reply_target`). Clicking it never
navigates: the `_ACTION_JS` document handler preventDefaults the anchor and
stores its `href` in `window.__stanzaReplyRef`, and the always-running scroll
poll delivers that `stanza:reply:` reference to Python as a `link_clicked`
(exactly like the `window.__stanzaEditRef` edit relay) — so the chat document
is never reset by the click. Real links, MUC mentions and the `mam://load`
marker request a navigation intercepted on the C++ side by
`_StanzaPage.acceptNavigationRequest` → `ChatView._accept_navigation`, which
emits `link_clicked` for the `stanza`/`mam`/`http`/`https`/`mailto` schemes
and denies the in-view load. `stanza`/`mam` are pre-registered as app-handled
schemes (`QWebEngineUrlScheme.registerScheme`) so Chromium never starts a real
load or error page; a stray `loadFinished(false)` from a blocked link is
self-healed by `_on_load_finished`/`_probe_chat_alive` (which probes that
`#chat` survived and un-wedges the pending buffer; a truly lost document
reloads the empty page and emits `document_lost`, so
`ChatWidget._restore_after_document_lost` re-renders the whole window), and
`refresh_avatars`
updates avatar `<img>` elements in place rather than reloading the document.
No QWebChannel call, console mirror or WebChannel-dependent JS is involved for
control clicks, so they reach Python even when the WebChannel transport is
unavailable. `ChatWidget._handle_reply_uri` decodes the URI and
inserts the referenced message into the input as an XEP-0421 quote block
(`> Sender wrote:\n> text`) with the cursor below it; a reply banner
(`chat_widget._reply_ctx`) stays as an indicator and `×` cancels, removing the
inserted quote. The `qwebchannel.js` glue prefers Qt's `:/qtwebchannel`
resource and falls back to the packaged `resources/qwebchannel.js`.
`JabberClient._attach_reply` attaches a `<reply xmlns='urn:xmpp:reply:0'
to='…' id='…'/>` as the **first child** of the `<message>` stanza; since the
quote is already in the body no automatic XEP-0421 fallback is prepended.

- Replyable ids: 1:1 messages use the local `origin-id` when present, else the
  message `id`; MUC messages use the server-assigned `stanza-id` (by the room's
  bare JID). Rendering falls back through `origin_id` → `archive_id` →
  `message_id` (`ChatWidget._reply_target_id`), so the action is never a silent
  no-op.
- When no reference id can be resolved the reply is still composed: the quote
  goes into the input and the message goes out as a plain `chat`/`groupchat`
  body (no `<reply/>` element). `_send` attaches the reply reference only while
  the quote is still in the body.
- Received replies are stored in history (`origin_id`, `reply_to`, `reply_id`
  columns) and rendered with the referenced text in a `.stanza-reply` quote bar
  above the body; leading XEP-0421 quote lines are stripped from the displayed
  body. Supported feature advertised as `urn:xmpp:reply:0`.

### 11.6 MUC Mentions & Nick Completion

- In groupchats the incoming sender name is rendered as a clickable
  `stanza:mention:nick` link (`ChatThemeFactory.render_message(mention=...)`,
  enabled per view via `ChatView.mention_senders`). Clicking it inserts
  `nick: ` at the cursor and focuses the input
  (`ChatWidget._handle_mention_uri`); the action is ignored in 1:1 chats. Like
  reply and ordinary links the mention is a plain anchor whose click reaches
  Python through the `acceptNavigationRequest` interception (no JS/bridge).
- `Tab` / `Shift+Tab` in a MUC input completes the nick before the cursor and
  cycles the candidate list with wrap-around on repeat presses. A nick that is
  the first token of the line is inserted as an address (`nick: ` with a
  trailing space); a nick completed mid-line is inserted bare. The previously
  inserted token is tracked and replaced, so the cycle never accumulates text,
  and any edit restarts the search (`ChatWidget._tab_complete_nick`).

## 12. Tray (`ui/tray.py`)

- System tray icon (built from `resources/images/scalable/apps/stanza-im.svg` +
  PNGs via `build_app_icon()`, multi-size 16/22/32/48)
- Context menu: Show/Hide, Quit
- Click: toggle main window visibility
- Blinking: alternates between icon and blank every 500ms when unread messages exist
- Notifications: `showMessage()` for connection status, errors

## 12A. OSD Notifications (`ui/osd.py`)

- `OsdManager` owns a stack of translucent frameless always-on-top windows
  (`Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint |
  X11BypassWindowManagerHint | WindowDoesNotAcceptFocus`) with an icon, bold
  title and word-wrapped body; clicking dismisses (and may focus the chat).
  Frame and label children are mouse-transparent so drags and clicks reach the
  window itself, and each window is raised on show/restack.
- All windows dock to a saved base position (`notifications.osd_x/osd_y`, the
  position of the first notification) and stack from it: top-down when
  `osd_topdown` is on (second below, third below that), otherwise upward
  (newest above). Positions are recomputed on add/dismiss; `stack_position()` is
  a pure function. The max on-screen count is `osd_max` (oldest is evicted) and
  each window auto-hides after `osd_duration` seconds.
- Preferences → Notifications → OSD shows a draggable preview at the saved
  base position; dragging moves it by grabbing the mouse and calling
  `move()` on X11 (works even when the window manager ignores the
  `_NET_WM_MOVERESIZE` protocol, e.g. Trinity) or `QWindow.startSystemMove()`
  on Wayland, updates `osd_x/osd_y` in the shared
  `Config` (live, persisted on Save) and re-entry re-docks it to the saved
  position. The settings dialog is opened non-modally so the preview window
  keeps receiving mouse input (a modal `exec()` would block it).
- Triggers (all gated on `osd_enabled`):
  - `osd_message`: 1:1 and private-groupchat messages, only when the chat window
  is not the active window on that conversation.
  - `osd_typing`: a contact starting to compose (XEP-0085).
  - `osd_status`: `never` / `available` (crossings between online+chat and any
    other show) / `any` (every transition); skips the initial presence sync.
  - `osd_conference`: `never` / `mention` (own nick in the body) / `all`.
  - `osd_file`: `_notify_osd_file(sender, filename)` entry point reserved for
    incoming p2p file transfers.

## 13. Icon Cache (`ui/icons.py`)

LRU cache for QPixmap icons:

- Max 200 entries
- 60-second stale TTL
- Auto-eviction timer every 30 seconds
- Methods: `get(path)`, `get_status_icon(show)`, `get_action_icon(name)`, `get_category_icon(name)`
- Avatars NOT cached long-term — loaded on-demand in paintEvent

## 14. XMPP Client (`core/client.py`)

### 14.1 Architecture

Wraps `slixmpp.ClientXMPP`. Registers XEP plugins:
- xep_0054 (vCard), xep_0045 (MUC), xep_0066 (OOB), xep_0085 (Chat State)
- xep_0184 (Receipts), xep_0224 (Attention), xep_0048 (Bookmarks)
- xep_0050 (Ad-hoc Commands), xep_0004 (Data Forms), xep_0049 (Private XML)
- xep_0030 (Service Discovery), xep_0128 (Disco Extensions), xep_0055 (Search)
- xep_0077 (Registration), xep_0092 (Software Version), xep_0199 (Ping)
- xep_0202 (Entity Time), xep_0313 (MAM, pulls in xep_0059/xep_0297)
- xep_0280 (Message Carbons)
- XEP-0393 Message Styling advertised via disco feature `urn:xmpp:styling:0`
  (parsed by `xmpp/message_styling.py`; toggle in Preferences → Chat)
- XEP-0461 Message Replies advertised via disco feature `urn:xmpp:reply:0`
  (manual `<reply/>` handling in `client._on_message`/`_attach_reply` —
  slixmpp has no plugin for it)

### 14.2 Message Carbons (XEP-0280)

- Register/modified via the `xep_0280` plugin; `<enable/>` is sent right after
  initial presence when `connection.message_carbons` is on (default), disco
  feature `urn:xmpp:carbons:2` added by the plugin on bind.
- `carbon_received`: the forwarded inner `<message>` (parsed with
  `_carbon_inner`, wrapped into a `slixmpp.Message`) flows through the same
  `_message_fields` extraction as direct messages and is emitted as
  `message_received(..., carbon=True)`. UI renders/stores it like any incoming
  message (vCard fetch skipped).
- `carbon_sent`: emitted as `message_carbon_sent(to_bare, body, ts,
  stable_id, reply_to, reply_id)`; MainWindow shows it as an outgoing "Me"
  message in the target chat and stores it in history, so every device keeps
  the same conversation view.
- Non-`chat`/`normal` forwards (e.g. groupchat) are ignored, and nothing is
  ever re-forwarded/acknowledged in response to a carbon.

### 14.3 Message Displayed Synchronization (XEP-0490)

- Own "displayed up to" state is tracked per chat (`_mds_last_sid/…_id`) from
  the server `stanza-id` of received 1:1 / PM / MUC messages and published to
  the private PEP node `urn:xmpp:mds:displayed:0` (item id = the chat's JID,
  payload `<displayed><stanza-id by=… id=…/></displayed>`). Publish-options
  (persist/max/send-last/access=whitelist) are attached when the server
  advertises `http://jabber.org/protocol/pubsub#publish-options`.
- **Server-assist**: when the server announces `urn:xmpp:mds:server-assist:0`,
  a single message to the chat's bare JID carries both a XEP-0333
  `<displayed id=…/>` marker and the MDS `<displayed>` element (verified not
  to be an otherwise-empty message); otherwise plain PEP publication is used.
- Triggered from `MainWindow` when a chat becomes the focused tab
  (`_on_tab_focused`) or receives a message while active.
- Incoming PEP events (`type=headline`, `from` = own bare JID) and a catch-up
  fetch after bind apply remote displayed states (`mds_displayed` event):
  unread is cleared and an "Displayed on another device" status line is added
  to an open chat. Config `chat.message_displayed_sync` (default on).

### 14.4 Last Message Correction (XEP-0308)

- Any own message can be edited: Ctrl+Up in the input starts editing the last
  one, and the message menu adds "Edit" for our own messages. Edit requests are
  **not** routed through in-page navigation (which resets the chat document in
  some WebEngine setups): the menu button stores the referenced id in
  `window.__stanzaEditRef`, the always-running scroll poll
  (`_poll_scroll_position`) returns it, and `_on_scroll_position` forwards it
  as a `stanza:edit:<id>` ``link_clicked`` (deduplicated) into
  `ChatWidget._begin_edit` — the same Python-only path Ctrl+Up uses. The edited
  body loads into the input with a cancelable "Editing…" banner; sending emits
  `message_edit_sent` and the client attaches
  `<replace xmlns='urn:xmpp:message-correct:0' id='…'/>` as the first child
  (with a fresh stanza id). After every handled click a content probe
  (`_schedule_content_probe`/`_verify_after_click`) re-renders the window via
  `document_lost` if the conversation ever vanished.
- `send_message`/`send_muc_message` accept `replace_id`; `edit_message()`
  wraps them. Received corrections (1:1 and MUC) are matched by the referenced
  id and, with `chat.allow_incoming_edits` on (default), replace the original
  message in the chat and history (body updated, `edited` flag, message_id
  column); with the toggle off they are delivered as ordinary new messages.
- Replaced messages render a large bold «✎» at the very end of the edited
  phrase (`render_message(edited=True)`, i18n tooltip;
  `data-stanza-outgoing`/`data-edited` on the wrapper drives the menu).

### 14.5 HTTP File Upload (XEP-0363)

- A toolbar above the input offers icon buttons: Clear chat, History (moved
  from the tab header), vCard, and Send file (a menu with "P2P" and
  "HTTP Upload"). The input is vertically resizable via a thin drag handle
  (persisted in `chat.input_height`), and files may be dropped directly into
  the chat window; the view and the input disable `acceptDrops` so drops
  reach the widget and are forwarded (multi-file) as
  `files_upload_requested(jid, [paths], method)`.
- Dropping or picking files opens the non-modal `FileTransferDialog`: one row
  per file — image thumbnail (or a generic file icon), name + size, and a
  per-file `QProgressBar` — plus one shared caption field and OK/Cancel. OK
  starts the transfers while the dialog stays open and shows live progress;
  Cancel (or Close) hides the dialog without aborting running uploads.
- `core/client.py` implements the protocol:
  `upload_http(jid, path)` → discover the service (`urn:xmpp:http:upload:0`
  via disco items/info, cached) → request a `<slot>` (filename/size/
  content-type) → PUT the bytes streamed in 64 KiB chunks (`http.client`,
  Content-Length + `conn.send`, progress fraction shared via
  `_UploadProgress`) → send the `get` URL as a 1:1 or MUC message. Progress
  is reported through `file_upload_progress(jid, start|progress|done|error,
  detail, path)`, updating the dialog bars and chat status lines. The dialog
  is parented to the issuing window (chat or roster) and centered over it
  (`_place_dialog_over`). A caption typed in the dialog is sent once as a
  separate message after the batch finishes (`_send_caption_after`). For 1:1
  uploads the `get` URL and the caption are rendered as real outgoing
  messages with clickable links via `_display_local_outgoing` (the sending
  resource never sees its own carbons echo); in MUC the room echo renders
  both.
- "P2P" still routes to the `send_file` placeholder; the roster context menu
  also gains "Send file → P2P / HTTP Upload" for contacts (and conferences).

See `XEPs.md` for the full supported-extensions matrix.

### 14.2 Event System

```
slixmpp event → handler → emit(event_name, *args) → UI callbacks
```

| Event Name | Arguments | Description |
|------------|-----------|-------------|
| session_started | — | Session established |
| presence_changed | bare_jid, show, status | Contact presence update (agg. per bare JID) |
| roster_received | items | Initial roster download finished |
| roster_item_added | item | Contact added |
| roster_item_removed | jid | Contact removed |
| message_received | from, body, timestamp, unstyled | Incoming 1-on-1 message |
| message_failed | jid, body, error | Message delivery failed |
| groupchat_message | room, nick, body, ts, archived, archive_id, unstyled | Incoming MUC message |
| groupchat_presence | room, nick, show, status | MUC presence |
| auth_failed | — | Authentication error |
| disconnected | — | Connection lost |
| subscribed | jid | Subscription accepted |
| unsubscribed | jid | Unsubscribed |

### 14.3 High-Level API

```python
client.connect_async()          # Connect to server
client.disconnect()             # Graceful disconnect
client.send_message(jid, body)  # Send 1-on-1 message
client.send_presence(show, status)  # Set presence
client.send_chat_state(jid, state)  # Typing indicator
client.request_roster()         # Fetch roster
client.get_roster_snapshot()    # Return current roster as list of ContactInfo
client.get_contact(jid)         # Look up a contact by bare JID
client.add_contact(jid, name)   # Add + subscribe
client.remove_contact(jid)      # Remove + unsubscribe
client.join_muc(room, nick)     # Join MUC room
client.leave_muc(room)          # Leave MUC room
client.send_muc_message(room, body)  # Send to MUC
client.get_vcard(jid)           # Request vCard
```

### 14.4 Data Classes

```python
class ContactInfo:       # jid, name, groups, show, status, avatar_path, resources
class GroupChatInfo:     # room, nick, subject, users
```

## 15. i18n System (`i18n/`)

### 15.1 Format

Python modules with `STRINGS` dict:

```python
# stanza_im/i18n/en.py
STRINGS = {
    "status_online": "Online",
    "login_connect": "Connect",
    ...
}
```

### 15.2 Usage

```python
from stanza_im.i18n import tr
label.setText(tr("status_online"))
error.setText(tr("error_nickname_conflict"))
```

Auto-detects language from `LANG` env var. Falls back to English.

## 16. Resources

Copied from original Jabbim `resources/`:

| Resource | Count | Reusable |
|----------|-------|----------|
| Status icons (16/32/48) | ~300 PNG | Yes, as-is |
| Action icons (16/22) | ~30 PNG | Yes, as-is |
| Category icons (16/32) | ~15 PNG | Yes, as-is |
| App icons + SVG | ~10 files | Yes |
| Emoticons (39 × 2 sizes) | 78 PNG + cfg | Yes |
| Mood icons | 61 PNG + cfg | Yes |
| Activity icons | 78 PNG + cfg | Yes |
| Sound packs (3 × 9 WAV) | 27 WAV | Yes |
| Chat skins (minimal-mod, candy) | HTML/CSS | Yes, directly |
| CSS variants | 54 CSS | Yes, directly |
| QSS themes | 8 themes | Needs Qt6 syntax update |
| Locale .ts/.qm | 9 languages | Replaced by i18n/*.py |

## 17. Phase 2 Features (planned)

- PEP (User Tune, User Mood, User Activity publication)
- Privacy Lists
- Metacontacts
- HTTP Upload (XEP-0363) — file sending
- File transfer (SI + IBB)
- Plugin system (convention-based discovery)
- Embedded chat mode (splitter in main window)

Implemented since the original spec: vCard viewing/editing, ad-hoc commands,
service discovery (browser), bookmarks management, MAM (XEP-0313),
preferences dialog, search/registration dialogs.
