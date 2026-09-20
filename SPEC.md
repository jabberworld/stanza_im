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
│   ├── client.py       — XMPP client wrapper (slixmpp), TLS/proxy/SM/CSI
│   ├── storage.py      — Config (TOML) + JSONL chat history (XDG)
│   ├── history.py      — SQLite chat-history access (day/summary + async wrappers)
│   ├── known_contacts.py — persisted JID → name/groups/conference registry
│   ├── unread_state.py — persisted per-contact unread counters (JSON)
│   ├── vcard_cache.py  — vCard avatar download/cache coordination
│   ├── discovery.py    — XEP-0065 proxy + STUN/TURN SRV discovery/cache
│   └── memstats.py     — periodic memory statistics (CLI -m)
├── ui/
│   ├── main_window.py  — Main window (3-page stack), actions and menus
│   ├── login_widget.py — Login form + config prefill/save
│   ├── roster_widget.py— Custom-painted contact list
│   ├── roster_style.py — QPainter rendering strategy
│   ├── chat_window.py  — Tab container for conversations
│   ├── chat_widget.py  — Single chat tab (header + view + input)
│   ├── chat_view.py    — QWebEngineView + JS bridge (QTextBrowser fallback)
│   ├── chat_themes.py  — Adium-style HTML generator
│   ├── nick_colors.py  — Session MUC nickname → color allocation
│   ├── preferences.py  — Settings dialog (icon navigation, nested tabs)
│   ├── media_preview.py — Inline image/audio/video previews
│   ├── media_viewer.py — Fullscreen image/video viewer (Ctrl+wheel zoom)
│   ├── map_widget.py   — In-app map window (OSM tiles, geo: URIs, live track)
│   ├── upload_dialog.py — HTTP upload / P2P progress dialog
│   ├── incoming_file_dialog.py — Incoming Jingle file-offer confirmation
│   ├── call_window.py  — Incoming call prompt, active call + Muji window
│   ├── device_test.py  — Devices self-tests (mic meter/tone/camera)
│   ├── conference_dialog.py — Join + XEP-0030 conference browser
│   ├── muc_config_dialog.py — XEP-0045 room management (affiliations + config)
│   ├── hats_dialog.py       — XEP-0317 hats tab + create/assign/unassign dialogs
│   ├── service_browser.py   — XEP-0030 service discovery browser
│   ├── certificate_dialog.py — Server TLS certificate details dialog
│   ├── history_manager.py   — Per-contact history browser
│   ├── vcard_dialog.py, search_dialog.py, registration_dialog.py,
│   ├── adhoc_dialog.py, add_contact_dialog.py, data_form_widget.py, captcha_dialog.py
│   ├── account_registration_dialog.py — XEP-0077 account creation wizard
│   ├── xml_console.py       — Raw XML console (filtered, coloured)
│   ├── tray.py         — System tray icon
│   └── icons.py        — LRU icon cache
├── xmpp/               — Protocol helpers (message_styling.py = XEP-0393 parser,
│                          jingle.py = XEP-0234/0260/0261 file transfer,
│                          jingle_rtp.py = XEP-0167/0176 A/V calls,
│                          muji.py = XEP-0272 conferences,
│                          media.py = aiortc media engine,
│                          bytestream.py = SOCKS5 bytestream transport,
│                          socks5.py = dependency-free SOCKS5 CONNECT)
├── i18n/               — Translation dicts (en.py, ru.py)
├── include/            — Constants (XDG paths), enumerators, pep payloads, utilities, geo (RFC 5870), hats (XEP-0317/0392)
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
variants, arranged in the «Темы», «Ростер», «Шрифты», «Цвет» and «Разное» tabs
(«Разное» holds the media-preview size, the preview cache TTL/limit and the MUC
mention highlight mode; «Ростер» toggles avatars/activity/mood in the roster).
Emoticon sets are discovered from cfg files under
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
the standard join flow (server persistence and bookmark support); the join
assembles `room@server` (`MainWindow._join_muc(..., server=)`) when the room
carries no `@`, so a bare localpart never reaches the XMPP layer as a JID.
Emoticon
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
| Discovery cache | `$XDG_CACHE_HOME/stanza-im/discovery.json` |

- Config uses nested tables: `config.ui.auto_connect`, `config.account.password`, ...
- Password stored **plaintext** (explicit user decision); file permissions 0600
- History appended line-by-line as JSON, one file per bare JID

### 4.1 Connection Settings (`connection.*`)

| Key | Default | Meaning |
|-----|---------|---------|
| `resource_mode` | `hostname` | Resource: machine hostname, or `manual` → `resource` |
| `resource` | `jabbim` | Manual resource string (when `resource_mode=manual`) |
| `priority_mode` | `status` | Priority from the presence show, or `manual` → `priority` |
| `priority` | `50` | Manual priority (0..127) |
| `override_host` / `host` / `port` | off / — / 5222 | Skip SRV and connect to an explicit host:port |
| `proxy_mode` | `none` | Account connection proxy: `none` or `socks5` |
| `proxy_host` / `proxy_port` | — / 0 | SOCKS5 proxy address (used when `proxy_mode=socks5`) |
| `tls_mode` | `prefer` | `direct` (TLS only) / `prefer` (direct TLS then fallback) / `normal` |
| `starttls_mode` | `always` | `always` / `opportunistic` / `never` (ignored for `tls_mode=direct`) |
| `keepalive` | `true` | Send whitespace keep-alive packets |
| `stream_management` | `true` | XEP-0198 resumption/acks |
| `csi` | `true` | XEP-0352 active/inactive |
| `csi_keep_active_for_typing_osd` | `false` | Keep the client active while `notifications.osd_typing` (and `osd_enabled`) are on, so servers do not buffer typing chat states |
| `pep_sweep_interval` | `0` | Periodic XEP-0080/0107/0108/0118 sweep (s); `0` = off. Preferences presents a selector: Off / 30 s / 1 min / 2 min / 5 min |
| `message_carbons` | `true` | XEP-0280 |
| `file_proxy_mode` / `file_proxy_manual` | `auto` / — | XEP-0065 file proxy (JID) |
| `stun_turn_mode` / `stun_turn_manual` | `auto` / — | STUN/TURN (host:port list) |
| `conference_servers` / `service_servers` | `[]` | Used discovery servers |

### 4.2 Appearance, Chat & Status Settings (`appearance.*`, `chat.*`, `status.*`)

| Key | Default | Meaning |
|-----|---------|---------|
| `chat.text_scale` | `1.0` | Chat text zoom factor; clamped to 0.5–3.0 (50–300 %). Ctrl+wheel in the chat view and the Preferences → Appearance → Fonts slider share this value; reopened 1:1 and MUC tabs re-apply it via `ChatWidget.set_text_scale`. When the WebEngine page owns focus, Chromium consumes Ctrl+wheel, so the factor is also followed by polling `QWebEngineView.zoomFactor()` in the 250 ms scroll poll (Qt 6 has no `zoomFactorChanged` signal) and saved the same way. |
| `chat.idle_unload_minutes` | `10` | Unload the WebEngine page of cold tabs after this many idle minutes (`0` = off). `MainWindow._maybe_suspend_tabs` skips the current tab and any tab with an unread message; `ChatWidget.suspend`/`resume` free and rebuild the view (`_NullView` stand-in in between). |
| `chat.history_limit` | `50` | History window: how many recent messages a tab loads on open (10–1000, Preferences → Chat → «Общие»/«General»; applies to 1:1 and MUC). `MainWindow._load_history_async` loads this many from local SQLite and sets `ChatWidget._window_size`; DB/MAM requests page in `_HISTORY_PAGE` (60) steps. `application.history_limit` is a legacy mirror. |
| `chat.allow_incoming_deletions` | `true` | Apply a peer's XEP-0424 retraction (Preferences → Chat → «Общие»/«General»). On: the message becomes a tombstone; off: it keeps its body and gains a "✕" marker. Applied live to the client from `_on_settings_applied`. |
| `chat.allow_moderation` | `true` | Apply a moderator's XEP-0425 retraction (Preferences → Chat → «Конференции»/«Conferences»). On: the message becomes a "Retracted by a moderator" tombstone with the reason; off: it keeps its body and gains a "✕" marker. It only governs the receive side — the moderator action in the message menu is unaffected. |
| `chat.confirm_retraction` | `false` | Ask for confirmation before retracting one of our own messages (message menu "Delete" / inline "✕"). |
| `chat.muc_name_source` | `from_name` | Conference display-name source (Preferences → Chat → «Конференции» + info label tooltip): `from_name` = bookmark name → room/disco name → JID localpart; `from_vcard` = bookmark name → vCard `fn` → vCard `nickname` → room/disco name → JID localpart. A bookmark name equal to the room JID is ignored. Applied live by `MainWindow._refresh_muc_names` (tab title + roster). |
| `appearance.roster_font` / `roster_font_size` | `""` / `0` | Roster typeface (QSS); `""`/`0` = Qt default. Rendered by `MainWindow._apply_roster_font`. |
| `appearance.chat_font` / `chat_font_size` | `""` / `0` | Chat font (pt) injected as a `body { font-family; font-size; } !important` override by `ChatThemeFactory.set_chat_font`; avatars/images are unaffected. |
| `appearance.nick_font` / `nick_font_size` | `""` / `0` | Message-nickname font (pt) via `ChatThemeFactory.set_nick_font`: a `.sender { … } !important` rule, plus a `<span class="sender">` wrapper around `%sender%` when the skin has no sender class (candy); `""`/`0` = inherit the chat font. |
| `appearance.participant_font` / `participant_font_size` | `""` / `0` | MUC participant sidebar font applied to `ChatWidget._users_list` by `ChatWidget.set_participant_font`; remembered per `ChatWindow` for new MUC tabs. |
| `appearance.roster_bg_color` | `#ffffff` | Roster background color (`MainWindow._apply_roster_colors` → `RosterStyle.set_colors` + viewport palette; `RosterWidget.paintEvent` fills with `style.bg_color()`). |
| `appearance.roster_group_bg_color` | `#ececec` | Roster group header stripe color, drawn by `RosterStyle.paint_group`. |
| `appearance.chat_bg_color` | `#ffffff` | Chat background override injected as `body { background-color: … !important; background-image: none !important }` by `ChatThemeFactory.set_chat_bg_color` (clears skin tile images); applied to both 1:1 and MUC theme factories. |
| `appearance.muc_highlight_color` | `#e53935` | MUC mention highlight color used by `ChatThemeFactory.set_highlight_color` in the XEP-0393 highlight `<span>`. |
| `appearance.colored_muc_nicks` | `true` | Colorful MUC nicknames: per-participant colors for message senders and the participant sidebar (`NickColorAllocator`, see §9.5). |
| `appearance.roster_show_avatars` | `true` | Show/hide vCard avatars in roster rows. Applied live via `MainWindow._apply_roster_options` → `RosterStyle.set_options`; gated in `RosterStyle.paint_user`. |
| `appearance.roster_show_activity` | `true` | Show/hide the PEP activity icon (XEP-0108) in roster rows, drawn from the same icon set as the mood/activity picker (`pep.activity_icon_path`). |
| `appearance.roster_show_mood` | `true` | Show/hide the PEP mood icon (XEP-0107) in roster rows (`pep.mood_icon_path`). |
| `appearance.interface_mode` | `separate` | Chat layout: `separate` (own top-level window) or `unified` (embedded beside the roster in a `QSplitter`). Applied live by `MainWindow._apply_interface_mode`; selector in Preferences → Appearance → «Разное». See §8.1. |
| `appearance.osd_font` / `osd_font_size` | `""` / `0` | OSD notification font; `OsdManager.apply_font` re-renders visible popups. |
| `appearance.osd_bg_color` | `#282828` | OSD bubble background color (rendered with `osd_opacity` as the alpha) via `OsdManager.apply_colors` → `_OsdWindow.apply_style`. |
| `appearance.osd_font_color` | `#ffffff` | OSD text color applied to all OSD labels (`_OsdWindow._stylesheet`). |
| `appearance.osd_opacity` | `92` | OSD background opacity in percent (0–100); the alpha is `round(opacity/100*255)`. |
| `status.auto_away` / `away_minutes` | `false` / `5` | Auto-switch to Away after inactivity (see below). |
| `status.auto_xa` / `xa_minutes` | `false` / `15` | Auto-switch to Extended Away; must be ≥ `away_minutes`. |
| `status.auto_status_message` | `""` | Single shared status text sent with the auto Away/XA presence (`MainWindow._check_auto_status`); when empty the previous status text is kept. Returning activity resumes `status.last_status` with an empty message, so the auto text is cleared. |
| `status.message` | `""` | User's presence status message; sent with every presence (`MainWindow._send_presence`) and edited from the roster bottom bar. |
| `status.mood` | `""` | Last published XEP-0107 mood key (cleared with `""`); republished on `session_started`. |
| `status.activity` | `""` | Last published XEP-0108 activity, stored as `group` or `group/sub`; republished on `session_started`. |

### 4.3 File Reception Settings (`files.*`, Preferences → Stanza IM → File Receiving)

| Key | Default | Meaning |
|-----|---------|---------|
| `files.auto_accept` | `false` | Automatically accept incoming P2P file offers and save them into `files.download_dir` (unique name) without a dialog. |
| `files.download_notifications` | `true` | Show an OSD notification when an incoming file offer is accepted. |
| `files.download_dir` | `""` | Directory for received files; empty falls back to `$XDG_DOWNLOAD_DIR` / `~/Downloads` (`include/utils.default_download_dir`). |

### 4.4 Call Settings (`devices.*`, `calls.*`, Preferences → Devices)

| Key | Default | Meaning |
|-----|---------|---------|
| `devices.audio_input` | `""` | Microphone device id (Qt Multimedia); empty = system default. |
| `devices.audio_output` | `""` | Speaker device id; empty = system default. |
| `devices.video_input` | `""` | Camera device id; empty = system default. |
| `calls.auto_accept` | `false` | Automatically accept incoming 1:1 calls (no prompt). |

Calling requires the optional `calls` extra (`aiortc`); without it the call
menus stay disabled (`NullMediaEngine`). STUN/TURN are resolved by
`client.ice_servers()` from XEP-0215, then the connection settings' STUN/TURN
endpoint, then DNS SRV.

The Devices page also provides hardware **self-tests** (disabled while a call
owns the devices): a live microphone peak meter, a speaker test tone and a
camera preview window (`ui/device_test.py`). The self-test controls are
icon-only buttons on the same row as the device selector (the mic control
toggles the meter, whose level bar sits on the same row). The mic meter and the
call's capture track read the `QAudioSource` stream directly (`io.read()`/
`readyRead`) and never gate on the QIODevice's `bytesAvailable()` — it can report 0 while
audio is streaming, which froze the meter and made calls one-way — so a live
PulseAudio capture always reaches the app. Capture/playback negotiate a
device-supported format (`isFormatSupported`, falling back to
`preferredFormat`) and convert to the encoder's s16/stereo/48 kHz 20 ms frames;
already-matching frames bypass aiortc's audio resampler (a PyAV/FFmpeg
compatibility shim in `xmpp/media.py`).

### 4.5 Map Settings (`map.*`)

| Key | Default | Meaning |
|-----|---------|---------|
| `map.tiles_url` | `https://tile.openstreetmap.org` | OSM tile server (``.../{z}/{x}/{y}.png``); empty disables fetch |
| `map.tile_cache_mb` | `64` | Tile cache size cap (LRU, `TileCache.prune`) |
| `map.tile_cache_days` | `14.0` | Tile TTL before pruning |
| `map.follow` | `true` | Auto-recenter the map on a new fix (toolbar toggle) |
| `map.window` | 700×520 | Map window geometry (`{width, height, x, y, maximized}`) |

The tile cache lives under `$XDG_CACHE_HOME/stanza-im/tiles/` (mirrors the
media cache layout: `{z}/{x}/{y}.png` + `index.json`).

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

### 5.2 Auto-Status

When `status.auto_away` / `auto_xa` are enabled, `MainWindow._check_auto_status`
(a 30 s idle timer; activity tracked by an application-level `eventFilter`)
sends Away / Extended Away presence once `idle_minutes` reaches
`away_minutes` / `xa_minutes` (XA wins when both are due; the Preferences page
forces `xa_minutes` ≥ `away_minutes`). The optional shared
`status.auto_status_message` rides along with that presence; when empty, the
previously stored status text is kept. Returning activity resumes
`status.last_status` with an empty message, so the auto text is cleared and
never sticks. Manual status changes reset the auto-applied state.

The auto-status field in Preferences → Status is a vertically fixed
`QPlainTextEdit` (max 70 px): it must not be vertically expanding, or the
page's `QFormLayout` (`ExpandingFieldsGrow`) spreads every row evenly over the
dialog height and the section looks gapped.

### 5.3 XML Console (`ui/xml_console.py`)

Actions → «XML-консоль» (directly under the disabled «Профили» item) opens a
non-modal `XmlConsoleDialog` (singleton kept on `MainWindow._xml_console`,
raised on reopen). It captures the raw stream from the `slixmpp.xmlstream`
logger — the same `SEND:`/`RECV:` dump as `-x` and the file log, so both
directions are seen. A `_XmlConsoleLogHandler` parses the `SEND: `/`RECV: `
prefix (decoding bytes arguments), ignores other debug records and forwards
each payload through the dialog's `stanza_captured` signal.

| Element | Behaviour |
|---------|-----------|
| Output | Read-only `QPlainTextEdit`, monospace, dark background; selectable/copyable |
| Filter | Checkboxes Сообщения / Присутствия / IQ / SM / Прочее (all on) + substring JID field; re-renders the buffer live |
| Enable | Off by default; remembers the logger level, sets `slixmpp.xmlstream` to DEBUG and adds the handler; disabling/closing removes it and restores the level (no-op under `-x`/`-l`) |
| Export | Writes the currently displayed text to a file |
| Clear | Empties the buffer and the view |
| Input XML | `XmlInputDialog` (multiline + Отправить/Отмена) → `client.send_raw_xml(text)` |

The JID field is a case-insensitive **substring** match over the full `from`/`to`
(resource included); an empty field matches everything. So
`conference.linuxoid.in` catches every room on that service regardless of the
room or nickname.

Classification: `message|presence|iq` by local name, accepting both a bare tag
and `xmlns="jabber:client"` (slixmpp omits the default namespace from top-level
stanzas), `urn:xmpp:sm:*` → SM, everything else (CSI, stream header/footer) →
«Прочее». Each stanza is pretty-printed with `minidom` (two-space indents,
text-only elements stay on one line, unparseable payloads unchanged). Colours —
incoming: message red, presence orange, iq turquoise, sm blue; outgoing:
message yellow, presence green, iq light blue, sm purple; other grey.
`send_raw_xml` accepts several top-level elements, strips an XML declaration
and gives an `<iq>` without an `id` one before sending. The buffer is capped at
5000 entries. Incoming non-stanza stream elements (SASL
challenge/success/proceed, `<stream:features>`) are not part of the raw dump and
therefore do not appear.

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

### 6.2 Connection Flow & Security

On `login_requested(jid, password, show)` MainWindow builds a `JabberClient`
from `connection.*` (resource mode, priority, TLS/STARTTLS mode, account proxy)
and runs `connect_async()`:

- "Только TLS"/"Предпочитать TLS" resolve `_xmpps-client._tcp`; "Только TLS"
  aborts with `login_tls_only_unavailable` when the record is missing.
- "Шифровать соединение = Всегда" aborts with `login_tls_required` when the
  server does not offer STARTTLS.
- Errors are shown on the login page and in the tray, and written to the
  console / `stanza-im.log` (with `-l`).
- With XEP-0198 enabled a dropped stream is resumed (`stream_resumed`); the UI
  shows "Переподключение…" → "Соединение восстановлено" instead of
  "Disconnected" while resumption is possible.

### 6.3 Roster Events (client → UI)

The XMPP client emits diff-based roster events:

| Event | Description |
|-------|-------------|
| `roster_received(items)` | Initial roster download finished |
| `roster_item_added(item)` | New contact (subscription change) |
| `roster_item_removed(jid)` | Contact removed |

Presence is aggregated per **bare JID** across resources — best `show` wins
via `SHOW_ORDER`; empty/`available` normalized to `"online"`.

### 6.4 Account Registration (`ui/account_registration_dialog.py`, XEP-0077)

Opened from the login window's "Создать аккаунт" link (`register_requested`) or
the icon-only button next to the Jabber ID in Preferences → Connection
(`register.png`). Step 1 collects the server — an editable combo whose
suggestions come from `resources/servers.txt` (one domain per line, `#` and
blank lines ignored; `include/constants.SERVERS_FILE`) — plus connection
settings mirroring Preferences → Advanced: "Specify host and port" (enabling
Host/Port), "Connection" (`tls_mode`, default `prefer`) and "Encrypt
connection" (`starttls_mode`, default `always`), and a proxy group
(`proxy_mode`/`proxy_host`/`proxy_port`). "Далее" builds a throwaway
`JabberClient` with those settings and calls
`JabberClient.connect_for_registration(server)`, which unregisters the SASL
feature, waits for `stream_negotiated` and fetches the server's registration
form; step 2 renders it (`DataFormWidget`/`LegacyFormWidget`) with
"Зарегистрировать"/"Отмена". On success the dialog writes `jid`, `password`,
`save_password=true` and the `connection.*` settings into the shared `Config`,
emits `registered(jid, password)`; `MainWindow` prefills the login form
(`LoginWidget.prefill`), returns to the login page, re-applies the settings and
closes the Preferences window when it was open. The login widget shares
`MainWindow._config` (passed into `LoginWidget`), so a later `save()` cannot
revert the newly written sections.

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
status message (italic, gray, truncated to 40 chars) + unread badge (red rounded rect)
+ PEP mood/activity icons (16×16 each). The icons appear between the name and the
badge (visible order: name, mood, activity, badge, avatar) when the contact has a
current XEP-0107 mood / XEP-0108 activity (`UserItem.mood`/`activity`, fed by
`MainWindow._on_contact_pep_updated` and seeded in `_add_roster_item` from
`client.pep_data`). Their artwork is the same icon set as the bottom-bar
mood/activity picker (`pep.mood_icon_path`/`pep.activity_icon_path`).
Each element is togglable from Preferences → Appearance → Roster
(`appearance.roster_show_avatars` / `roster_show_activity` / `roster_show_mood`,
all default `true`): `MainWindow._apply_roster_options` → `RosterStyle.set_options`
gates the avatar and the two icons live without relayout.

Dynamic height: 32px without status message, 52px with.

The roster typeface is taken live from `appearance.roster_font` /
`roster_font_size` (empty/0 = Qt default) and applied to the same QPainter
pass by `MainWindow._apply_roster_font` — no relayout/rebuild.

The roster background and the group-header stripe colorized per
`appearance.roster_bg_color` / `appearance.roster_group_bg_color`
(`RosterStyle.set_colors`): `paintEvent` first fills the whole item area with
`bg_color()` (white default), and `paint_group` draws its stripe with
`group_bg_color()`. `MainWindow._apply_roster_colors` also colors the roster
widget's viewport palette so the area below the last contact matches.

Groups sort case-folded, but `RosterWidget.set_trailing_groups` (set by
`MainWindow` to the conferences group, `roster_group_conferences`) forces those
groups after all contact groups.

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
(`_on_muc_leave`) and closes its tab. The conference menu also carries
«Скопировать адрес конференции» (`conference_copy_join`) directly below
«История переписки», and its «Звонок» submenu starts a Muji conference call
(`_join_muji`) instead of the 1:1 Jingle call, enabled only when aiortc is
available (`client.rtp_calls.available`). For a non-conference contact the menu
carries «Пригласить в» (`ctx_invite_to`) — a submenu of the conferences we are
currently in (XEP-0249): picking one calls
`client.send_muc_invite(target, room, reason, password)` (the room password is
included when known) and shows a tray notice; the entry is hidden when we are in
no conference. The MUC participant context menu offers the same submenu for a
participant with a visible real JID, excluding the room that participant is
already in. An incoming invitation opens `IncomingInviteDialog`: the inviter is
rendered as `nick (jid)` (the nick resolved from the room's occupants or the
XMPP roster, the real inviter taken from the XEP-0045 `<invite from>` when the
room relays the invitation), and a relay that names no inviter falls back to
`muc_invite_received_unknown`. An invitation stanza (the XEP-0249 shape and the
XEP-0045 mediated shape, `<x xmlns='http://jabber.org/protocol/muc#user'><invite
from='…'/></x>`) is never rendered as a chat message — `JabberClient._on_message`
drops it from `message_received` — and is surfaced only as the prompt plus an OSD
notification.

### 7.4 Strategy Pattern

`RosterStyle` is pluggable via `set_style()`. The default renderer handles
avatar, name, status icon, status message, unread badge.

Future: hot-swappable styles from `resources/rosterstyles/`.

## 8. Chat Window (`ui/chat_window.py`)

### 8.1 Modes

`appearance.interface_mode` selects how conversations are hosted:

| Mode | Behavior |
|------|----------|
| `separate` (default) | Standalone `QMainWindow`; hidden while it has no tabs. |
| `unified` | The `ChatWindow` is embedded as a child widget (`Qt.Widget`) in a horizontal `QSplitter` on the roster page, beside the contact list. |

The mode is applied live: `MainWindow._apply_interface_mode` (called from
`_on_settings_applied`) reparents the chat between the top-level window and the
splitter. `ChatWindow` gained an `embedded` constructor flag plus
`set_embedded()`; when embedded it suppresses title/geometry handling and the
show/raise/activate calls and emits `attention_requested` instead, so
`MainWindow._raise_chat_area` raises the main window. Default: `separate`.

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
| Close tab | Remove tab, `ChatWidget.detach()` (stops the typing timer + view scroll poll, drops the Python history copies) then `setParent(None)` + `deleteLater()`; a removed `QTabWidget` page stays parented and would otherwise leak its `QWebEngineView`/page |
| Last tab closed | Hide window |
| New incoming message | Create tab if needed, add message, blink tray |

Per-tab memory is bounded: `ChatWidget` keeps at most `_HISTORY_MAX` (5000)
history rows, `_MESSAGES_MAX` live rows and `_STATUS_MAX` (300) status lines,
and the WebEngine DOM trims to `ChatView._MAX_DOM_MESSAGES` (500) message nodes
(oldest first); everything older stays in SQLite/MAM and is re-fetched through
the history paging menus.

Cold tabs are additionally suspended: after `chat.idle_unload_minutes`
(default 10, `0` = off) `MainWindow._maybe_suspend_tabs` unloads a tab that is
not current, has no unread message and saw no recent activity; `ChatWidget.suspend`
frees the `ChatView`/WebEngine page and swaps in a `_NullView` stub, and
activating the tab (`ChatWindow._on_tab_changed` → `resume`) rebuilds the view
and re-renders `_history`/`_messages`.

`MainWindow._trim_main_process_memory` (30-min timer, plus after a tab closes
or suspends) runs `gc.collect()` and glibc `malloc_trim(0)` to return freed
main-process heap to the OS; the Chromium renderer processes are unaffected.

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
- Jump-to-bottom button (`_JumpButtonMixin`): shown while the view overflows and
  is not at the bottom. It shows the count of incoming, non-own messages that
  arrived while scrolled up (`ChatWidget.add_message` →
  `ChatView.is_scrolled_up` → `note_new_message`), as `▼ N` (capped `99+`). The
  first click jumps to the first such message (`scroll_to_message(..., highlight=False)`),
  the second click — or reaching the bottom — scrolls to the end and clears the
  counter, which lives until the actual bottom. WebEngine renders the button as
  the in-page `#stanza-jump` div (its click sets `window.__stanzaJumpPress` and
  is relayed by the scroll poll to `_on_jump_clicked`; `bridge.on_jump_clicked`
  is only an optional fast path); the QTextBrowser fallback uses a `QToolButton`
  and cannot target a message, so it always scrolls to the bottom. Incoming
  messages never force a scroll to the bottom — only the user's own outgoing
  messages do.
- MUC participant sidebar (`_users_list`, a `_ParticipantList` subclass): a
  single click selects a row (highlight only), a double-click opens the private
  chat (`participant_clicked` → MainWindow opens the participant's `real_jid`,
  falling back to `room/nick`), and a left click on empty list space clears the
  selection (`_ParticipantList.mousePressEvent`). Right-click opens the
  participant context menu; when the participant's real JID is visible it also
  offers «Пригласить в» (XEP-0249, §7.3).

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

### 9.5 Colorful MUC Nicknames (`appearance.colored_muc_nicks`)

When enabled (default), message senders in groupchats and the participant
sidebar rows are colored per participant. Colors are allocated by a session-only
`NickColorAllocator` (`ui/nick_colors.py`): each participant key — the
`normalize_nick`d nick (Unicode NFKC + whitespace collapse + case fold), bound
to the participant's `real_jid` when present, so the same person keeps one
color across nick spellings and renames to the same JID — gets a stable color.
The color map is built lazily from the currently present roster, so arrivals
receive the first free palette entry and `prune()` releases colors of
participants who left; a re-join may therefore reuse that color. Colors start
from a 15-shade fixed dark palette (maximally distinguishable, dark enough to
read on light chat backgrounds) and continue with a golden-angle HSL sequence
(hue = i·137.508°, s=0.55, l=0.30) for larger rooms.

`ChatWidget._entry_view_kwargs` injects the sender color as `sender_color`,
which `ChatThemeFactory.render_message` substitutes for `%senderColor%` (only
`minimal-mod` uses that placeholder; other skins keep their own styling). The
participant sidebar row label gets a matching inline `color:` stylesheet. 1:1
chats never color senders. Toggling the setting re-renders MUC tabs
(`ChatWindow.set_colored_muc_nicks` → `ChatWidget.set_colored_muc_nicks`, which
re-runs `_refresh_nick_colors` and re-renders messages and the participant
list).

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

Per-chat text zoom (`chat.text_scale`, default 1.0, clamped to 0.5–3.0 by
`chat_view.clamp_zoom`): Ctrl+wheel calls `set_chat_zoom`, which is re-applied
on every `loadFinished` (the document never resets to 100%). `ChatWindow`
snapshots the value in `_chat_options` and re-applies it to any (re)opened 1:1
and MUC tab via `ChatWidget.set_text_scale`, so closed-and-reopened tabs keep
their zoom. The Preferences slider (50–300 %) is synced bidirectionally with
the live factor. Because Chromium handles Ctrl+wheel itself once the page
owns focus (the widget's `wheelEvent` is never invoked), the WebEngine view
relays the factor through its always-running 250 ms scroll poll: it compares
`QWebEngineView.zoomFactor()` with `self._zoom`, clamps the change, ignores it
while a document is loading, and only relays values that differ from
`self._zoom` (no feedback loop) — Qt 6 dropped the `zoomFactorChanged` signal,
so property polling is the only reliable relay. The same
`zoom_changed → text_scale_changed → config.save() + snapshot`
chain runs, so wheel/pinch zoom persists. The 50–300 % slider is a
`_SnapSlider`: user drags, clicks and keys snap to the 10 % grid, while
programmatic `setValue` (zoom sync from the wheel) stays exact.

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

**Chat font override**: `ChatThemeFactory.set_chat_font(family, size)`
(read from `appearance.chat_font` / `chat_font_size`, empty/0 = Qt default)
appends a `body { font-family: '…' !important; font-size: …pt !important }`
rule to `generate_page` / `generate_empty_page`. Message-text descendants
`.sender`, `.fromstatus`, `.next_label`, `.time_initial`, `.stanza-action` and
`.stanza-reply` force `font-family: inherit !important`, so the override
reaches message text without touching avatar/emoticon `<img>` sizing (images
scale only with `chat.text_scale`).

**Nickname font override**: `ChatThemeFactory.set_nick_font(family, size)`
(read from `appearance.nick_font` / `nick_font_size`, empty/0 = inherit the
chat font) appends a `.sender { font-family: '…' !important; font-size: …pt
!important }` rule to the page. When the chosen skin packs no
`class="sender"` on its sender element (e.g. `candy`), `render_message`
wraps the `%sender%` expansion in `<span class="sender">` so the selector
applies; skins with their own sender class (e.g. `minimal-mod`) are never
double-wrapped. The nickname font follows the chat font for its "default"
label in Preferences (a real chat font wins, otherwise the system font).

**MUC participant font**: `ChatWidget.set_participant_font(family, size)`
(from `appearance.participant_font` / `participant_font_size`) sets the font of
`ChatWidget._users_list`, which the participant row widgets and labels inherit;
`ChatWindow.set_participant_font` remembers it in `_participant_font` and
applies it to every new MUC tab (so the sidebar keeps the stored typeface
across reconnects). Re-renders the participant list (`_render_muc_users`) so
section headers pick up the family too.

**Preferences defaults**: on the «Шрифты» tab, empty/zero values display the
*real* font that would be used: the family combo's first entry reads
«По умолчанию — <family>» and the size spin shows «<size> pt (по умолчанию)»
via `setSpecialValueText`, both resolved by
`PreferencesDialog._default_app_font` from `QApplication.font()`; the stored
value stays `""`/`0`.

### 11.5 Message Replies (XEP-0461)

The per-message reply trigger is an anchor
(`<a href="stanza:reply:%REPLY_TARGET%">`, placeholder filled by
`ChatView._mark_message` via `_compose_reply_target`). Clicking it never
navigates: the `_ACTION_JS` document handler preventDefaults the anchor and
stores its `href` in `window.__stanzaReplyRef`, and the always-running scroll
poll delivers that `stanza:reply:` reference to Python as a `link_clicked`
(exactly like the `window.__stanzaEditRef` edit relay) — so the chat document
is never reset by the click. Pressing `Up` in an empty input starts a reply to
the newest incoming message (`ChatWidget._reply_to_last` skips our own entries
and those without a replyable id; Ctrl+Up remains the XEP-0308 edit shortcut).
Pressing `Down` while the reply is untouched (the input holds exactly the
inserted quote) cancels it.
Real links request a navigation intercepted on the C++ side by
`_StanzaPage.acceptNavigationRequest` → `ChatView._accept_navigation`, which
emits `link_clicked` for the `stanza`/`mam`/`http`/`https`/`mailto` schemes
and denies the in-view load. The "local history was cleared — load it from
server" marker is a `stanza:load:` control link (`a.stanza-load`, the same
`preventDefault` + scroll-poll relay as reply/edit/mention), so it reloads the
server history without relying on a `mam:` navigation. `stanza`/`mam` are
pre-registered as app-handled
schemes (`QWebEngineUrlScheme.registerScheme`) with the `Path` syntax, which
preserves the opaque `stanza:view:…`/`xmpp:…` forms verbatim (so `linkUrl()`
still reports them to the media context menu). Chromium thus never starts a
real load or error page; a stray `loadFinished(false)` from a blocked link is
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
- The quote bar is clickable when the referenced message resolves to a local
  DOM id: `render_reply(sender, snippet, target_id)` wraps it in a
  `stanza:jump:<urlencoded id>` anchor. The `_ACTION_JS` click handler
  preventDefaults it (never a navigation) and scrolls the matching
  `.stanza-message[data-stanza-id]` node into view with a brief
  `.stanza-jump-highlight` flash; if the node is not rendered yet it relays the
  reference through `window.__stanzaJumpRef` (scroll poll → `link_clicked` →
  `ChatWidget._jump_to_message`). The jump then walks the **local** SQLite
  archive only (`history.message_exists` + `older_available_timestamp`/
  `load_older_timestamp`, bounded by `_JUMP_MAX_PAGES`) — the server is never
  contacted — renders the loaded pages and scrolls. Those pages are prepended
  with `keep_position=False` so the reading-anchor restore (`restoreAnchor`)
  cannot revert the jump, and the target node is matched by `data-reply-id` or
  `data-stanza-id`. `ChatWidget._reply_reference` returns
  `(sender, snippet, target_id)`, where *target_id* is `_reply_target_id`
  (`origin_id` → `archive_id` → `message_id`).

### 11.6 MUC Mentions & Nick Completion

- In groupchats the incoming sender name is rendered as a clickable
  `stanza:mention:nick` link (`ChatThemeFactory.render_message(mention=...)`,
  enabled per view via `ChatView.mention_senders`). Clicking it inserts
  `nick: ` at the cursor and focuses the input
  (`ChatWidget._handle_mention_uri`); the action is ignored in 1:1 chats. Like
  reply/edit the mention is a plain anchor whose click is preventDefaulted by
  the `_ACTION_JS` document handler and relayed through
  `window.__stanzaMentionRef` by the always-running scroll poll (never a
  navigation), so a nick click can never reset the chat document.
- `Tab` / `Shift+Tab` in a MUC input completes the nick before the cursor and
  cycles the candidate list with wrap-around on repeat presses. A nick that is
  the first token of the line is inserted as an address (`nick: ` with a
  trailing space); a nick completed mid-line is inserted bare. The previously
  inserted token is tracked and replaced, so the cycle never accumulates text,
  and any edit restarts the search (`ChatWidget._tab_complete_nick`).

### 11.7 Room Management (XEP-0045)

The MUC tab header shows a gear button after the bookmark (hidden on 1:1 tabs),
enabled only for owners/admins (`MainWindow._apply_muc_admin`, fed by our
affiliation in `_muc_users`). It opens a non-modal `MucConfigDialog`
(`ui/muc_config_dialog.py`) with three tabs:

- «Участники» — a `QTreeWidget` with the four affiliation groups (Владельцы =
  owner, Администраторы = admin, Зарегистрированные пользователи = member,
  Заблокированные = outcast), columns «Jabber ID» and «Примечание» (the
  XEP-0045 `<reason>`), and Add/Edit/Delete buttons (Edit/Delete enabled only
  with a selected participant). Add/Edit use `_ParticipantEditDialog`
  (category + JID + note); Delete confirms and sets affiliation `none`.
  `client.muc_get_affiliations` builds a custom `muc#admin` IQ so the `reason`
  survives (slixmpp's `get_affiliation_list` returns only JIDs); a failing
  category is left empty.
- «Шапки» — XEP-0317 hats, see §11.7.1 (always shown; owner/admin only).
- «Настройки» — enabled for the owner only; fetches the `muc#owner` room form
  (`client.muc_get_config`) into a `DataFormWidget`.

Edits are collected and applied on «Ок» (`client.muc_set_affiliation`,
`client.muc_set_config`); «Отмена» discards them. Only what changed is sent:
affiliations when the participant list was edited (each pre-validated against
the XEP-0045 rule — owners may modify any list, admins only member/outcast, and
the edit dialog warns immediately otherwise) and the configuration only when a
form value changed, as a fresh `type='submit'` form built by
`client.muc_set_config(room, values)` (the server's own form is never mutated).

The MUC toolbar's vCard button opens the room's own vCard
(`MainWindow._show_muc_room_info` → `_show_profile(room)`). `VCardInfoDialog`
shows an Edit button for room cards, enabled for owners/admins
(`MainWindow._can_edit_room_vcard`); the editor reuses `VCardEditDialog`
(`title_key="vcard_edit_room_title"`) and saves through
`client.set_room_vcard` (`xep_0054.publish_vcard(..., jid=room)`); the open
viewer is refreshed afterwards. The room vCard viewer, editor and confirmation
boxes are parented to the chat window (`MainWindow._chat_dialog_parent`), not
the roster.

Conference display names follow `chat.muc_name_source`: `from_name` (default)
resolves bookmark name → room/disco name → JID localpart; `from_vcard`
resolves bookmark name → vCard `fn` → vCard `nickname` → room/disco name → JID
localpart. A bookmark name equal to the room JID (slixmpp's default when no
name is set) is ignored, and `client.save_bookmark` omits that name element.
`MainWindow._muc_display_name` resolves the name and
`_apply_muc_name` updates the tab title and roster row; the setting and
bookmark changes apply live (the Preferences combo has an info icon with this
order).

### 11.7.1 Hats (XEP-0317, `include/hats.py` + `ui/hats_dialog.py`)

Extended MUC roles. A room that supports hats advertises `urn:xmpp:hats:0`;
occupants' hats arrive as a `<hats xmlns='urn:xmpp:hats:0'/>` list of
`<hat uri title hue xml:lang/>` right under the presence. `JabberClient.\
_on_groupchat_presence` parses it with `hats.parse_hats` into
`gi.users[nick]["hats"]` and forwards it with the `groupchat_presence` event;
`MainWindow._muc_users[room][nick]["hats"]` feeds the participant tooltip
(«Шапки» line, coloured) and `ChatWidget._user_hats` (message chips).

- **Management** (`HatsTab`, embedded in `MucConfigDialog`, owner/admin, always
  visible; a room without `urn:xmpp:hats:0` shows `hats_unsupported` with the
  buttons disabled) lists configured hats from the `list` command as top-level
  categories and the assigned users from `list-assigned` underneath (falling
  back to the presence hats when the command returns nothing). Buttons:
  Создать/Изменить/Назначить/Снять/Удалить — Изменить/Удалить require a
  selected category, Снять a selected user, Назначить at least one hat.
- **Colour**: `HatEditDialog` has a required «Название» and an optional colour;
  a picked `QColor` is stored as the `hats#hue` angle and rendered through the
  XEP-0392 HSLuv conversion (`hue_to_color`, validated against the XEP test
  vectors) when the chip is drawn.
- **Commands**: `client.hats_create/update/destroy/assign/unassign/list/
  list_assigned` build custom `<command/>` IQs on the
  `urn:xmpp:hats:commands` nodes (execute → submit); `room_supports_hats` is a
  cached disco#info probe. The create URI is
  `urn:xmpp:hats:<sha1(room + "\x00" + title)>`.
  The form is submitted with `action` taken from the server's `<actions/>`
  (`complete` if absent, which ejabberd requires), and the URI goes into the
  field var the returned form declares (`hats#uri` for `create`, `hat` for
  `destroy`/`assign`/`unassign` on ejabberd); an error `<note/>` raises so the
  tab shows it instead of a silent reload.
- **Context menu**: the participant context menu gains a «Шапка» submenu after
  «Изменить роль» (owner/admin only) with «Назначить» (`HatAssignDialog`, the
  user preselected; present users or a manual JID) and «Снять»
  (`HatUnassignDialog` lists the user's hats, then confirms).
- **Rendering**: messages show the sender's hats as coloured `.stanza-hat`
  chips right of the nick (`ChatThemeFactory.render_message(hats=…)`; the
  QTextBrowser fallback appends them as `[Title, …]` text).

### 11.8 MUC Join Reliability

- Presence status lines (`muc_user_joined`/`muc_user_left`/`muc_status_changed`)
  are rendered only after a successful join: `MainWindow` tracks `_muc_joined`
  (set in `_on_muc_joined`) and a 2 s `_muc_join_grace`, so the server's initial
  occupant dump is never shown as "X joined" even when history loading lags.
- Auto-joined rooms are retried after transient `muc_join_error` conditions
  (`timeout`, `unknown`, `remote-server-timeout`, `internal-server-error`,
  `service-unavailable`) with a bounded 5/15/45 s backoff
  (`MainWindow._schedule_autojoin_retry`/`_retry_muc_join`); permanent
  conditions surface a failure status.
- `client._autojoin_bookmarks` retries the bookmarks fetch and skips only rooms
  that actually joined (`GroupChatInfo.joined`), so a stale entry from a failed
  attempt does not block the retry; `client.join_muc` cancels a pending join
  task before starting a new one.
- A bookmarked room that is also a plain roster contact is moved to the
  conferences group before joining
  (`MainWindow._classify_bookmarked_conferences`, run after bookmarks load and
  on roster additions).

## 12. Tray (`ui/tray.py`)

- System tray icon (built from `resources/images/scalable/apps/stanza-im.svg` +
  PNGs via `build_app_icon()`, multi-size 16/22/32/48)
- Context menu: Show/Hide, Quit
- Click: toggle main window visibility
- Middle-click: `cycle_unread_requested` → MainWindow opens the topmost roster
  contact with unread messages and marks it read, so each subsequent
  middle-click advances to the next unread contact until none remain
  (`MainWindow._on_tray_cycle_unread`)
- Blinking: alternates between icon and blank every 500ms when unread messages exist
- Unread counters are persisted (`$XDG_DATA_HOME/stanza-im/unread.json`,
  `core/unread_state.py`) and restored on startup: roster badges and tray
  blinking come back exactly as before the restart (`MainWindow._unread_counts`,
  applied in `_add_roster_item`/`_sync_conference_roster`, saved with a 1 s
  debounce and on quit). The file entry is `{"count": N, "displayed": "<sid>"}`
  (legacy `{"jid": N}` is still read): the displayed sid is the last XEP-0490
  point we published, seeded into the client on login, so the startup MDS
  catch-up does not clear unread that arrived after it. OSD popups are not
  replayed. Messages received while
  the client was offline are delivered by the server on reconnect and counted
  as unread in the new session (no MAM catch-up).
- Notifications: `showMessage()` for connection status, errors

## 12A. OSD Notifications (`ui/osd.py`)

- `OsdManager` owns a stack of translucent frameless always-on-top windows
  (`Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint |
  X11BypassWindowManagerHint | WindowDoesNotAcceptFocus`) with an icon, bold
  title and word-wrapped body; clicking dismisses (and may focus the chat).
  Frame and label children are mouse-transparent so drags and clicks reach the
  window itself, and each window is raised on show/restack. The bubble
  (rounded background using `appearance.osd_bg_color`/`osd_font_color`/
  `osd_opacity` and a 1px border) is drawn in `_OsdWindow.paintEvent`. When
  `compositing_available()` finds no X11 compositor (no `_NET_WM_CM_S0` owner)
  and the opacity is below 100 %, a desktop snapshot is painted under the
  bubble (`_grab_region`): it tries a region `QScreen.grabWindow(0, x, y, w, h)`,
  but a one-time probe compares it against `grabWindow(0)` cropped to the same
  area (`_region_matches`) and permanently falls back to the full-grab+crop path
  when the platform ignores the region offsets; the snapshot is refreshed on
  spawn, on preview drag and after every `_restack` (windows briefly hidden) so
  opacity still looks transparent rather than black. At 100 % opacity the whole
  rectangle is filled with the bubble color (straight corners) and no snapshot
  is taken. Wayland/unknown platforms always composite with plain alpha.
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

## 12B. Map window & geo: URIs (`ui/map_widget.py`, `include/geo.py`)

- **geo: links**: `geo:lat,lon;u=accuracy` URIs (RFC 5870) inside message
  bodies are linkified (`include/utils.tokenize_urls` → `geo_render` in
  `ChatThemeFactory._tokenize_urls`). With a resolvable message id the anchor
  carries it as `stanza:geo:<ref>/<urlenc>` (XEP-0308 corrections then update
  the already-open map in place); without one the href stays plain `geo:`.
  Both styles are intercepted like every other `stanza:` control link — the
  document-level click handler preventDefaults the anchor and the always-running
  scroll poll relays the reference as a `link_clicked`, so a geo click never
  resets the chat document. The QTextBrowser fallback linkifies geo: via
  `escape_body_with_geo`.
- **`GeoMapWindow`** (top-level `QMainWindow`, geometry persisted in
  `map.window`): a `GeoMapWidget` paints OSM raster tiles with a hand-rolled
  Web-Mercator projection (no WebEngine required) over a `QPainter` pass, then
  draws the accuracy zone (radius from `;u=` scaled by `meters_per_pixel`), the
  track polyline, a green start marker and a red current-position marker.
  Drag pans, wheel/double-click zooms (clamped 2–18, keep-anchor zooming),
  and a follow toggle re-centers on new fixes.
- **Live tracking**: clicking a geo: link seeds the window per
  `(chat, ref)`; `MainWindow._on_geo_message_corrected` feeds XEP-0308
  corrections whose bodies carry a geo: URI into the matching window
  (`update_position` → `Track.add_fix`, gap- and duplicate-filtered), and a
  correction without coordinates calls `mark_track_final()` (status-bar note,
  tracking stops). Speed = great-circle distance over time delta. The `Track`
  keeps at most 2000 fixes (oldest dropped), so a long live session stays
  bounded.
- **Tiles**: `TileLoader` (worker thread) fetches `{z}/{x}/{y}.png` with a
  browser-style `User-Agent`, ≤2 req/s pacing and retry backoff, into the
  on-disk LRU `TileCache` (`map.tile_cache_mb`/`tile_cache_days`). The cache
  and its 30-min prune timer are created lazily on the first map window
  (`MainWindow._ensure_tile_cache`); the decoded tile `QPixmap`s use a 32 MB
  in-memory LRU budget (`GeoMapWidget._MEM_PIXMAP_BYTES`), flushed by
  `set_zoom` on a zoom-level change. No tiles / empty `map.tiles_url`: the
  window still paints the markers, track, coordinates and status.

## 13. Icon Cache (`ui/icons.py`)

LRU cache for QPixmap icons:

- Max 200 entries
- 60-second stale TTL
- Auto-eviction timer every 30 seconds
- Methods: `get(path)`, `get_status_icon(show)`, `get_action_icon(name)`, `get_category_icon(name)`
- Avatars NOT cached long-term — loaded on-demand in paintEvent

## 14. XMPP Client (`core/client.py`)

### 14.1 Architecture

Wraps `slixmpp.ClientXMPP` through the `_StanzaXMPP` subclass (deterministic
direct-TLS ordering, STARTTLS enforcement, unusable `-PLUS` SASL filter). The
stream advertises the UI language (`i18n.current_language()`) as `xml:lang` and
`start_stream_handler` forces `peer_default_lang` to it, so outgoing stanzas
carry it and servers localize data forms (e.g. the MUC room configuration).
Registers XEP plugins (conditionally where noted):
- xep_0054 (vCard), xep_0045 (MUC), xep_0066 (OOB), xep_0085 (Chat State)
- xep_0184 (Receipts), xep_0224 (Attention), xep_0048 (Bookmarks)
- xep_0050 (Ad-hoc Commands), xep_0004 (Data Forms), xep_0049 (Private XML)
- xep_0030 (Service Discovery), xep_0128 (Disco Extensions), xep_0055 (Search)
- xep_0077 (Registration), xep_0092 (Software Version), xep_0199 (Ping)
- xep_0202 (Entity Time; the plugin's broken 1.17 responder is replaced by
  `JabberClient._on_time_request`/`_get_entity_time`)
- xep_0313 (MAM, pulls in xep_0059/xep_0297)
- xep_0280 (Message Carbons), xep_0060 (PubSub), xep_0163 (PEP)
- xep_0065 (SOCKS5 Bytestreams — file-proxy discovery)
- xep_0198 (Stream Management; `connection.stream_management`)
- xep_0352 (Client State Indication; `connection.csi`)
- SASL mechanism is **not forced**: slixmpp selects the strongest. On TLS 1.3
  without Python `tls-exporter` support, `*-PLUS` mechanisms are dropped to
  avoid an invalid channel binding and a transient auth failure.
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
- Incoming PEP events (`type=headline`, `from` = own bare JID, bodyless) are
  delivered through the shared "PEP Event" `MatchXPath` stanza handler (same
  routing as the extended-presence notifications, §14.10.1 — slixmpp's
  `message` event requires a `<body>`); a catch-up fetch after bind also
  applies remote displayed states (`mds_displayed` event):
  unread is cleared and an "Displayed on another device" status line is added
  to an open chat. `_mds_apply_remote` skips a state equal to `_mds_local`;
  on login `MainWindow` seeds `_mds_local` from the persisted unread state
  (`client.set_displayed_state`), so the startup catch-up does not wipe restored
  unread while a newer remote state still clears it.
  Config `chat.message_displayed_sync` (default on).

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
- The same message menu carries "Copy" and "Forward". "Forward" stores the whole
  message (`[time] sender: text`, or the media URL for a media-only message) in
  `window.__stanzaForwardRef`; the scroll poll delivers it as a
  `stanza:forward:<urlencoded>` ``link_clicked`` and
  `ChatWidget._handle_forward_uri` emits `share_requested` — the same
  `ShareDialog` flow as a URL/media/selection share (never navigation).

### 14.4.1 Message Retraction (XEP-0424)

- Our own messages can be retracted from the message menu's "Delete" item or
  the inline "✕" button between Reply and the menu button (`a.action-delete`,
  present in both the incoming and outgoing skin templates; the page CSS
  `.stanza-message:not([data-stanza-outgoing="1"]) …` hides it for foreign
  messages, so our own live MUC echoes and archive replays both show it).
  Both keep the click in-page (`window.__stanzaDeleteRef`
  via the `_ACTION_JS` handler + scroll-poll relay, `stanza:delete:<id>`), so the
  chat document is never reset. `ChatWidget._handle_delete_uri` optionally asks
  for confirmation (`chat.confirm_retraction`, default off) and emits
  `message_retract_sent`.
- `client.send_retraction` sends `<retract xmlns='urn:xmpp:message-retract:1'
  id='…'/>` (the room `stanza-id` in MUC, the message `id` in 1:1), a
  `<fallback xmlns='urn:xmpp:fallback:0' for='urn:xmpp:message-retract:1'/>`,
  a generic fallback `<body>` and a `<store xmlns='urn:xmpp:hints'/>` hint; the
  message is replaced locally with a tombstone and its wrapper gains
  `data-retracted="1"`, so the page CSS hides the inline "✕" and the menu JS
  omits both "Изменить" and "Удалить". The client advertises
  `urn:xmpp:message-retract:1` and accepts the legacy `:0` namespace on receive.
- Incoming retractions are routed by dedicated handlers (`message_retracted`,
  `message_retracted_own`, `groupchat_message_retracted`) — the fallback body is
  never rendered. With `chat.allow_incoming_deletions` on (default) the target
  message becomes a tombstone ("Сообщение отозвано"); off it keeps its body and
  gains a "✕" marker like the «✎» edit marker. A retraction is only applied when
  it comes from the original author.
- History gains `retracted`/`retract_marker` columns and `retract_message()`;
  `<retracted/>` tombstones found in MAM results are stored with `retracted=1`
  and render the same notice.

### 14.4.2 Moderated Message Retraction (XEP-0425)

- A MUC moderator (role `moderator` or affiliation owner/admin) can retract
  another participant's message. `MainWindow._apply_muc_admin` also calls
  `_apply_muc_moderation`, which resolves `client.room_supports_moderation`
  (disco#info, cached, `urn:xmpp:message-moderate:1`) and enables
  `ChatWidget.set_moderation_enabled` for the tab; the message menu then shows
  "Удалить (модерация)" on incoming messages that carry a server `stanza-id`
  (`data-moderatable="1"`).
- The click is relayed in-page (`stanza:moderate:<id>` via the `_ACTION_JS`
  handler + scroll-poll, `window.__stanzaModerateRef`). `ChatWidget.
  _handle_moderate_uri` opens a single `_ModerateDialog` (confirmation text +
  optional reason), then emits `message_moderate_sent(room, id, reason)` →
  `client.moderate_message`, which sends `<iq type='set'><moderate id='…'
  xmlns='urn:xmpp:message-moderate:1'><retract
  xmlns='urn:xmpp:message-retract:1'/><reason/></moderate></iq>` and emits
  `moderation_failed` on an error.
- The room's groupchat broadcast carries a normal XEP-0424 `<retract>` with a
  nested `<moderated by='…' xmlns='urn:xmpp:message-moderate:1'/>` and a
  `<reason/>`. It is bodyless, while slixmpp's MUC handler requires a `<body>`,
  so dedicated `MatchXPath` matchers (`{jabber:client}message/{urn:xmpp:
  message-retract:1|0}retract` → `_on_bodyless_retract_stanza`) route it to
  `_on_groupchat_message` (messages with a fallback `<body>` take the normal
  path and are skipped there). It is only accepted when it comes from the MUC
  service itself (`from` is the bare room JID), never from an occupant. The
  tombstone renders "Отозвано модератором" with the reason, and history stores
  the reason and moderator (`retract_reason`/`retract_by`).
  `chat.allow_moderation` (on by default) chooses between the tombstone and the
  "✕" marker.

### 14.4.2 CAPTCHA Forms (XEP-0158 / XEP-0221)

- A field's `<media xmlns='urn:xmpp:media-element'/>` is parsed from its raw
  XML (no XEP-0221 plugin needed). A challenge arrives as a `<message>` with
  `<captcha xmlns='urn:xmpp:captcha'><x type='form'/>` (handled by its own
  `MatchXPath`; the guard in `_on_message` keeps it out of the chat) or inside a
  CAPTCHA-protected room's join error presence. Both emit
  `captcha_challenge(jid, form, oob, body)`.
- `MainWindow._on_captcha_challenge` opens a non-modal `CaptchaDialog`; the
  `DataFormWidget` renders the challenge: an image URI is fetched in a worker
  thread and shown inline, audio/video URIs open in the media viewer, and a
  `SHA-256` hashcash field is solved in the background (`sha256(answer)`'s least
  significant bits match the field label, prefixed with the `from` JID).
- Answering calls `client.answer_captcha`, which sends
  `<iq type='set'><captcha><x type='submit'>…` (FORM_TYPE, challenge, sid and the
  answers copied verbatim); a room that rejected the join is re-joined
  afterwards. The registration dialog renders an embedded CAPTCHA form the same
  way and shows the query-level `<instructions>`/OOB URL. The media viewer zooms
  images with Ctrl+wheel (0.1–8×, Ctrl+0/double-click resets to fit) and pans a
  zoomed image by dragging it with the left mouse button.

### 14.5 HTTP File Upload (XEP-0363)

- A toolbar above the input offers flat icon buttons: Clear chat, vCard, and
  Send file (a menu with "P2P" and "HTTP Upload" for 1:1 chats; in a conference
  a plain button, HTTP Upload only). The Send control is a vertical icon-only
  button (an Enter-style arrow) whose height tracks the input field. The input
  is vertically resizable via a thin drag handle on
  its top edge, just below the toolbar (dragging up grows the field, down
  shrinks it; height persisted in `chat.input_height`), and files may be
  dropped directly into the chat window; the view and the input disable
  `acceptDrops` so drops reach the widget and are forwarded (multi-file) as
  `files_upload_requested(jid, [paths], method)`.
- Dropping or picking files opens the non-modal `FileTransferDialog`: one row
  per file — image thumbnail (or a generic file icon), name + size, and a
  per-file `QProgressBar` — plus one shared caption field and OK/Cancel. OK
  starts the transfers while the dialog stays open and shows live progress;
  Cancel (or Close) hides the dialog without aborting running uploads. Each
  row also shows live stats — transferred / total, the current speed (EMA over
  samples ≥ 0.3 s, `format_speed`) and an ETA (`format_eta`) — and the average
  speed on completion; the numbers are derived from the integer progress
  percentage and the file size, so no extra protocol data is needed.
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
- "P2P" routes to the Jingle file transfer (§14.5.1); the roster context menu
  also gains "Send file → P2P / P2P IBB / HTTP Upload" for contacts (and
  conferences).
- When the HTTP Upload slot request is rejected for the file being too large
  (`file-too-large`, or a `not-acceptable` / `resource-constraint` error),
  `_http_upload_flow` emits `http_upload_oversize(jid, path)` instead of an
  error; `MainWindow` retries that file over P2P with the SOCKS5 method.

See `XEPs.md` for the full supported-extensions matrix.

### 14.5.1 Jingle P2P File Transfer (XEP-0234/0260/0261, `xmpp/jingle.py`)

- slixmpp has no Jingle core plugin, so `JingleFileTransferManager`
  (`client.file_transfer`) implements the XEP-0166 signalling directly on the
  slixmpp stanza objects. It is driven by IQ handlers registered with
  `MatchXPath("{jabber:client}iq/…")` for `{urn:xmpp:jingle:1}jingle` and the
  XEP-0047 `{http://jabber.org/protocol/ibb}open|close|data` elements.
- **Sending**: `client.send_file_p2p(jid, path, method)` serializes sessions
  with a lock. A XEP-0234 `<description><file/>` carries name, size,
  media-type, date and a SHA-1 `<hash/>` (`urn:xmpp:hashes:2`).
  - `method="p2p"`: XEP-0260 SOCKS5 first. The candidate list always includes
    our `direct` listener candidates (`xmpp/bytestream.py`,
    `listen_for_bytestream`, priority 126<<16) and, when a file proxy is
    discovered/configured, a `proxy` candidate (priority 10<<16). The initiator
    dials the peer's candidates in priority order with
    `connect_bytestream` (`DST.ADDR = SHA1(SID + initiator + responder)`, port
    0), sends `candidate-used`, activates a nominated proxy candidate
    (`<activate/>` + `<activated/>`) and streams the file. On failure it sends
    `transport-replace` with the IBB transport, the peer answers
    `transport-accept`, and the file continues over IBB.
  - `method="p2p-ibb"`: XEP-0261 In-Band Bytestreams immediately — Jingle
    session negotiation, then XEP-0047 `<open/>`, base64 `<data seq sid/>`
    chunks of `block-size` bytes (seq wraps at 65536) and `<close/>`.
- **Receiving**: `file_offer(offer_id, from, meta)` is emitted for an incoming
  `session-initiate`. With `files.auto_accept` on, `MainWindow` answers
  immediately saving into `files.download_dir` (unique name); otherwise it
  shows `IncomingFileDialog` (confirm, then `QFileDialog.getSaveFileName`) and
  calls `client.answer_file_offer`. Accepted files are saved, acknowledged with
  a XEP-0234 `session-info <received/>` and the session is terminated. Remote
  file names are sanitized (`include/utils.safe_filename`) to prevent path
  traversal (XEP-0234 §12).
- **Progress**: `file_transfer_progress(jid, start|progress|done|error, detail,
  path, out|in)` updates the shared `FileTransferDialog` rows for sends and
  adds chat status lines for sends/receives; `file_transfer_status` reports the
  S5B→IBB fallback. Receiving shows the OSD via `_notify_osd_file` when
  `files.download_notifications` is on.
- Features `urn:xmpp:jingle:1`, `urn:xmpp:jingle:apps:file-transfer:5`,
  `urn:xmpp:jingle:transports:s5b:1` and `urn:xmpp:jingle:transports:ibb:1` are
  advertised in disco (`core/client.py`).

### 14.6 Connection Security & Transport

- **Resource / priority**: `resource_mode` (`hostname`/`manual`) and
  `priority_mode` (`status`/`manual`). Status priority map: online/chat 50,
  away 40, xa 30, dnd 0; the manual value (0..127) is sent on every presence.
- **Account SOCKS5** (`proxy_mode=none|socks5`): `xmpp/socks5.py` performs an
  RFC 1928 CONNECT; `JabberClient._install_socks_proxy` replaces
  `xmpp._attempt_connection` so the socket is opened through the proxy and
  handed to slixmpp (`loop.create_connection(sock=..., ssl=...)`).
- **TLS mode** `tls_mode`: `direct` ("Только TLS"), `prefer` (default),
  `normal`. `prefer` tries `_xmpps-client._tcp` records first and falls back to
  the normal connection. `direct` pre-resolves
  `core/discovery.resolve_client_srv()` and raises `TLSOnlyUnavailable`
  (`login_tls_only_unavailable`) when the record is missing.
- **STARTTLS mode** `starttls_mode`: `always` (default; refuses to connect
  without STARTTLS → `tls_required`/`login_tls_required`), `opportunistic`,
  `never`. `tls_flags()` maps both selectors to the slixmpp flags.
- **Keep-alive** `keepalive` → `xmpp.whitespace_keepalive`.
- `connection_info()` (mode, TLS version/cipher, SASL, keep-alive, SM, CSI,
  actual SRV endpoint, and `cert` — the peer certificate: subject/issuer CN+O,
  validity with days left/expired, serial, DNS SANs, SHA-256 fingerprint,
  `verified`) feeds the preferences info icon; the separate «Сертификат» icon
  opens `ui/certificate_dialog.CertificateDialog` non-modally with the shared
  `certificate_lines()`.
- **Client identity / caps branding**: a named disco identity
  (`client`/`pc`, `name=APP_NAME`) is added and `xep_0115.caps_node` is set to
  the human-readable `Stanza IM <VERSION>` (slixmpp's defaults are a nameless
  `client/bot` and the `http://slixmpp.com/ver/…` node; clients that map caps
  nodes to names display the node verbatim for unknown clients). The XEP-0092
  `software_name`/`version`/`os` attributes are set explicitly because
  slixmpp's `plugin_init` only honours the `name` config key.

### 14.7 Stream Management & Client State (XEP-0198/0352)

- **Graceful shutdown**: `JabberClient.disconnect()` disables
  `auto_reconnect`, sends `<presence type='unavailable'/>` and awaits
  `xmpp.disconnect(wait=1.0)` (slixmpp's future drains the send queue and closes
  the stream); `MainWindow._shutdown_async` waits for it before cancelling tasks
  and quitting, so the server ends the session immediately instead of holding it
  for the XEP-0198 resumption window (the account would otherwise stay online).
- `connection.stream_management` (default on) registers `xep_0198`: SM is
  enabled after bind and a dropped stream is resumed (`session_resumed`)
  without re-auth/roster/presence; unacked stanzas are replayed by `h` counter.
  `resume_expected()` drives MainWindow's "Переподключение…" /
  "Соединение восстановлено"; "Disconnected" only on `sm_failed`/`sm_disabled`.
- `connection.csi` (default on) registers `xep_0352`:
  `set_client_active()`/`_sync_csi()` send `<active/>`/`<inactive/>`.
  MainWindow recomputes activity from `QApplication.applicationState()` via an
  application event filter and the show/hide/toggle/Esc/close hooks, and
  re-sends the state on `session_start`/`session_resumed`/`csi_enabled`. The
  preference is applied live by `JabberClient.set_csi_config()` (called from
  `_on_settings_applied`): it registers/unregisters the plugin and sends
  `<active/>` before disabling. Servers hold non-urgent chat states while the
  client is inactive, so `connection.csi_keep_active_for_typing_osd` (default
  off) forces active while `notifications.osd_typing` and `osd_enabled` are on
  (`MainWindow._keep_csi_active_for_typing_osd`). The option carries an info
  glyph (`info.svg`, blue «i»; `PreferencesDialog._info_icon`) whose tooltip
  explains the server-side chat-state buffering; the same glyph is used for the
  connection/certificate/STUN information affordances.

### 14.8 Service Discovery — File Proxy & STUN/TURN (`core/discovery.py`)

- **XEP-0065**: `discover_file_proxy()` uses `xep_0065.discover_proxies()`
  (server `disco#items` + `category='proxy' type='bytestreams'`); JID keys are
  sorted with `key=str`.
- **STUN/TURN**: `discover_stun_turn()` queries SRV
  `_turns/_stuns/_turn/_stun._tcp|udp` via aiodns (encrypted first, TURN before
  STUN).
- `DiscoveryCache` (`$XDG_CACHE_HOME/stanza-im/discovery.json`): positives 24 h,
  negatives 10 min; `refresh()` isolates the two sections and
  `effective_endpoint()` implements the auto/manual choice. Runs as a
  background task after `session_start`; "Detect again" calls
  `refresh_services()`.

### 14.9 Event System

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
| stream_resumed | — | Stream resumed via XEP-0198 (no full re-login) |
| sm_enabled | — | Stream management enabled |
| sm_failed | — | Stream resumption failed (full reconnect) |
| sm_disabled | — | Stream management disabled/reset |
| csi_enabled | — | Server supports XEP-0352 |
| tls_required | — | Required STARTTLS not offered by the server |
| connection_info | dict | Endpoint/security state for the info icon |
| services_discovered | dict | File-proxy + STUN/TURN discovery result |
| message_corrected | jid, … | Incoming XEP-0308 correction applied |
| groupchat_message_corrected | room, … | Incoming MUC correction applied |
| subscribed | jid | Subscription accepted |
| unsubscribed | jid | Unsubscribed |

### 14.10 High-Level API

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
client.connection_info()        # Dict: mode/TLS/SASL/keepalive/SM/CSI/server/cert
client.set_client_active(bool)  # XEP-0352 active/inactive
client.resume_expected()        # True if XEP-0198 may resume the stream
client.discover_transfer_services()  # File proxy + STUN/TURN (cached)
client.refresh_services()       # Force re-discovery
client.discovered_services()    # Last discovery result
client.upload_http(jid, path)   # XEP-0363 upload
client.edit_message(jid, body, replace_id)  # XEP-0308 correction
client.publish_mood(key, text="")      # XEP-0107 PEP publish
client.publish_activity(group, sub="") # XEP-0108 PEP publish
client.fetch_pep(jid)           # XEP-0080/0107/0108/0118 items → contact_pep_updated
client.supports_calls(bare, video=False)  # XEP-0115 caps check for call gating
client.ice_servers()            # STUN/TURN (XEP-0215 → settings → SRV)
client.start_call(jid, video=False)   # XEP-0167/0176 A/V call
client.answer_call(sid, accept, video=False)
client.end_call(sid)
client.join_muji(room, nick, video=False)  # XEP-0272 conference
client.leave_muji(room)
```

### 14.10.1 Extended Presence (XEP-0080/0107/0108/0118)

- The four PEP nodes (`http://jabber.org/protocol/{geoloc,mood,activity,tune}`)
  are advertised with `+notify`. PEP notifications are bodyless
  `<message type='headline'><event xmlns='http://jabber.org/protocol/pubsub#event'>`
  stanzas, so they never reach slixmpp's `message` event (which requires a
  `<body>`); a "PEP Event" `MatchXPath` stanza handler registered in
  `_register_jingle_handlers` routes them (together with XEP-0490 MDS events) to
  `JabberClient._maybe_mds_event`/`_maybe_pep_event`, which parse them into
  `client.pep_data[bare_jid][kind]` and re-emit them as
`contact_pep_updated(jid, kind, data)` — so roster mood/activity icons and the
   tooltip refresh live without a vCard fetch. `fetch_pep(bare)` pulls
   the current nodes (`pubsub/items`, `max_items=1`) when a profile opens and
   on presence (`_maybe_refresh_pep`, gated by an in-flight guard plus a
   per-contact 15 s `time.monotonic` cooldown): a contact's online presence
   triggers a pull even though the server never pushed a XEP-0163 event, and a
   burst of presences collapses to a single fetch.
- Contacts are additionally **subscribed** to the four nodes (XEP-0163) on
  online presence and roster add (`_ensure_pep_subscription`,
  `xep_0060.subscribe`, in-flight guard, 300 s retry cooldown on failure),
  re-subscribed on every `session_started`/`stream_resumed` (servers drop
  subscriptions on session end) and unsubscribed on roster removal
  (`_unsubscribe_pep`); a `pending`/error subscription state counts as a
  failure. The `connection.pep_sweep_interval` setting (seconds, `0` = off)
  arms a periodic fallback sweep that re-pulls online contacts' nodes through
  the same `_maybe_refresh_pep` guards for servers that never forward PEP
  events; the sweep pauses while the user is idle
  (`client.set_pep_sweep_paused`, tied to the auto-status inactivity timer)
  and stops on disconnect.
- `include/pep.py` builds/parses mood (`<mood><key/><text/>`), activity
  (`<activity><group><sub/></group><text/></activity>`), tune and geoloc
  payloads, parses the bundled Jabbim icon packs
  (`resources/moods/<pack>/*.cfg`, `resources/activities/<pack>/*.cfg`) and
  formats a summary (`format_summary`).
- The roster bottom bar has two icon-only buttons: a smiley menu
  ("Mood" + nested "Activity" groups/sub-activities + "None", with pack icons)
  that publishes via `publish_mood`/`publish_activity` and persists
  `status.mood`/`status.activity` (republished on `session_started`); its actions
  are checkable and `MainWindow._sync_pep_checks` (on `aboutToShow`) marks the
  active mood/activity, including the first-level activity group entries
  (`submenu.menuAction()`), like the tray status menu. The `edit.png` button opens
  `StatusMessageDialog` (multiline, preloaded from
  `status.message`); the edited text is sent with presence.
- Contacts' mood/activity/tune/location are shown in the roster tooltip
  (`MainWindow._roster_tooltip`) and on the vCard "Status" tab
  (`mood`/`activity`/`tune`/`location`), updated live via
  `_on_contact_pep_updated`.

### 14.10.2 Jingle RTP Calls & Muji (XEP-0167/0176/0215/0272/0293/0294/0339/0353/0482)

- 1:1 calls live in `xmpp/jingle_rtp.py` (`client.rtp_calls`). The single
  Jingle IQ handler (`JingleRtpManager`) is routed by `JabberClient._dispatch_jingle_iq`
  (RTP/ICE content or a known call `sid` → calls, otherwise file transfer). The
  RTP `<description>` (Opus/telephone-event/VP8/H264, SSRCs), ICE-UDP
  `<transport>` (ufrag/pwd/candidates) and DTLS `<fingerprint>` are built from /
  converted to SDP so `aiortc` (`xmpp/media.py`) provides ICE, DTLS-SRTP and RTP.
  Candidates are offered in `session-initiate`/`accept` and trickled via
  `transport-info`. The SDP↔Jingle conversion preserves `rtcp-mux` (always
  advertised in our `<description>`), codec fmtp `<parameter>`, `<rtcp-fb>`
  (XEP-0293), `<rtp-hdrext>` (XEP-0294), `<source>`/`<ssrc-group>`/`msid`
  (XEP-0339) and the `senders` direction, groups the contents with a BUNDLE
  `<group>` and echoes the peer's `<trickle/>`/`<renomination/>` transport
  options, so libwebrtc peers (Conversations) leave their *connecting* state.
  Peers advertising `urn:xmpp:jingle-message:0` are rung with
  XEP-0353 propose/proceed first. slixmpp only fires the `message` event for
  stanzas with a `<body>`, so bodyless propose/retract and XEP-0482 invites have
  dedicated `MatchXPath` handlers; proposals are answered with
  `client.answer_proposal` (`proceed`/`reject`), the proposed media kind comes
  from all `<description>` elements (`_propose_media` returns video when any of
  them is a video m-line), and the following
  session-initiate is auto-accepted.
- Capability gating mirrors Conversations: `client.supports_calls(bare, video)`
  checks the peer's XEP-0115 caps (`jingle:1 + ice-udp:1 + rtp:1 + dtls:0 +
  rtp:audio [+ rtp:video]`). The roster contact context menu and the chat
  toolbar show a "Call → Audio/Video" menu enabled only for capable contacts.
- STUN/TURN: `client.ice_servers()` merges XEP-0215 `urn:xmpp:extdisco:2`
  services (with credentials) with `connection.stun_turn_*` and SRV discovery.
- `ui/call_window.CallWindow` / `IncomingCallDialog` provide the call UI;
  remote video frames are painted by `VideoView` with a translucent nickname
  caption over the image, and every control is **icon-only** (tooltips, no
  labels) using `resources/images/16x16/actions/` via `call_window._icon`:
  `mic`/`mic-off`, `camera`/`camera-off` (webcam glyph), `speaker`/`speaker-off`,
  red `call-hangup` and green `call-accept`. The call-window mute/camera buttons
  toggle the **outgoing** capture (silence / black frames via
  `set_audio_enabled`/`set_video_enabled`, no SDP renegotiation) and never
  affect the received stream — the remote view stays visible. Preferences →
  Devices selects
  the microphone/speaker/camera (`devices.*`, Qt Multimedia) and offers mic/
  speaker/camera self-tests (icon-only buttons on the same row as the device
  selector, `ui/device_test.py`, disabled during a call). The
  mic meter and the capture track read the `QAudioSource` stream directly
  (`io.read()`/`readyRead`) instead of waiting on the QIODevice's
  `bytesAvailable()` (which can report 0 while audio streams, freezing the
  meter and sending call silence).
  Capture/playback pick a device-supported format and feed aiortc s16/stereo/
  48 kHz 20 ms frames; matching frames bypass aiortc's audio resampler (the
  compatibility shim patches the aiortc encoder classes, never the immutable
  PyAV `AudioResampler`, to survive an FFmpeg `EINVAL`). If the *controlled* ICE
  agent stalls, `_nomination_fallback` waits 5 s for the peer's own
  `USE-CANDIDATE` (Conversations, the Jingle initiator, never sends one, so ICE
  stays `checking`) and only then switches aioice to controlling — with the
  tie-breaker forced to its 64-bit maximum so we deterministically win any
  RFC 8445 §7.3.1.1 role conflict instead of caving to a peer's 487 — and
  re-runs the best succeeded pair's check so a real `USE-CANDIDATE` is sent
  and ICE completes;
  `AiortcCall.close()` cancels the
  pending aioice checks to stop STUN retry tracebacks.
- Muji (`xmpp/muji.py`, `client.muji`): participants advertise a `<muji>`
  contents map in MUC presence; the joiner opens a Jingle session with every
  other participant's real JID tagged `<muji room='…'/>`, handles content
  add/remove and leaving, and parses XEP-0482 invites. Muji sessions never open
  a 1:1 `CallWindow` — `MainWindow._on_call_state` skips sessions whose
  `muji_room` is set — and incoming session-initiates are recorded as
  participants via the `muji_session` event → `MujiManager.note_session`, which
  matches by bare real JID (a session-only entry is a `virtual` placeholder that
  `handle_presence` merges into the real MUC nick, so one person never appears
  under both its room nick and its Jingle resource). A presence from a tracked
  participant without the `<muji/>` element (or `type="unavailable"`) means the
  peer left the call: the participant and its mosaic tile are dropped,
  `muji_updated` fires and `JingleRtpManager.end_muji_peer` /
  `MujiManager.forget_session` close our session and drop the placeholder;
  `MujiCallWindow` splits horizontally (video mosaic / status on the left,
  participant list on the right, like the MUC chat sidebar); each participant
  row shows a rounded avatar (`_rounded_avatar`, the cached vCard PNG masked to
  a circle, `set_avatars` from `MainWindow._muji_avatar`) before the nick and
  **three** icon-only toggles ("send my
  mic to this participant" via `set_call_audio`, "hear this participant" via
  `set_call_audio_receive`/`AiortcCall.set_remote_audio_enabled`, "send my video
  to this participant" via `set_call_video`, all local-only, no renegotiation);
  glyphs swap between the plain and crossed variants on state. Below the list a
  separate icon-only row (microphone, speaker and, for video conferences,
  camera) beside the red `call-hangup` "leave" button drives the devices for all
  participants: the effective per-party state is the global layer AND the
  per-party layer (`_effective`), so the global toggles leave the per-party
  configuration untouched and each channel is emitted only when it changes.
  `JingleRtpManager._bind_call` emits `call_bound` so
  `MainWindow._on_call_bound` → `MujiCallWindow.apply_states` re-applies the
  effective states to a session bound after its row was created. For video
  conferences `_MosaicVideo` shows one captioned tile per video participant
  **plus a mirrored self tile** labelled with our own nick: clicking a tile
  enlarges that participant (the rest become a bottom strip) and a "back to
  grid" button restores the grid. Own video is tapped from the local capture
  (`_VideoCaptureTrack.on_local_frame` → `JingleRtpManager._forward_local` →
  `call_local_video_frame`, only for the session marked via `set_local_preview`
  by `MainWindow._sync_muji_preview`, re-applied by `_bind_call` when the engine
  call is created) and painted by `MujiCallWindow
  .set_local_frame`. While no peer video session exists (e.g. alone in the
  room) `_sync_muji_preview` starts a standalone camera capture
  (`media._LocalPreviewCapture`, `JingleRtpManager.start_local_preview`) fed to
  the window as `muji_local_video_frame`; `_bind_call` stops it before a
  session's own capture opens the device. In a MUC chat tab the
  toolbar call button starts a Muji
  conference: `ChatWidget` emits `muji_call_requested(room, video)` (never
  `call_requested`) which `ChatWindow.open_groupchat` forwards and
  `MainWindow._on_muji_call_requested` routes to `_join_muji` (a conference
  contact's roster «Звонок» submenu calls `_join_muji` the same way). The button is
  enabled only when aiortc is available (`ChatWindow.set_muji_support`, applied
  by `MainWindow._apply_muji_support` on every MUC-tab open — `_join_muc`,
  `_on_muc_joined` for auto-joined rooms and `_on_contact_open`); it
  is a no-op on 1:1 tabs. While a conference is live the MUC call button
  doubles as its indicator: `MainWindow._sync_muji_indicator(room)` keeps it
  lit while anyone in the room (ourselves or other participants) has an
  active conference — `MujiManager.leave()` keeps the room record (joined=False)
  as long as peers continue, and drops it (emitting `muji_ended`) when the last
  participant leaves — so the indicator survives our own departure and goes
  dark only when nobody is left. It is called from `_apply_muji_support`,
  `_on_muji_updated` and `_on_muji_left` and forwards to
  `ChatWindow.set_muji_active(room, active, video)` →
  `ChatWidget.set_muji_active`, which swaps the idle `call` icon/tooltip
  (`muji_button`) for the `call-accept` glyph and an audio/video-aware
  tooltip (`muji_active_audio`/`muji_active_video` per the conference
  contents) and restores the idle look otherwise; it is a no-op on 1:1 tabs.
  The Audio/Video menu actions of the call button carry the `mic.svg` and
  `camera.svg` icons. The MUC chat shows conference lifecycle status lines
  (gated by `chat.muc_show_status`), kind-aware to the conference's media:
  `MujiManager` emits `muji_started(room, video)` once the media contents are
  confirmed — our own join (`_finalise_join`) or a peer advertising real
  contents in presence, peer-started calls included — so a preparing-only
  presence or a session placeholder never locks in a wrong audio kind, and
  `muji_ended(room, video)` when the last participant leaves;
  `_on_muji_started`/`_on_muji_ended` write the kind-aware
  `muji_started_audio`/`muji_started_video`/`muji_ended_audio`/`muji_ended_video`
  lines. `MujiManager` reports the start once per conference lifetime
  (`_started` guard, cleared when the room record drops). All call/Muji code
  logs via `stanza_im.call*` with `CALL[…]` / `MUJI[…]` markers.

### 14.11 Data Classes

```python
class ContactInfo:       # jid, name, groups, show, status, avatar_path, resources
class GroupChatInfo:     # room, nick, subject, users
```

### 14.12 XMPP URIs (XEP-0147)

`xmpp:` URIs are handled end-to-end (`include/xmpp_uri.py`):
- **Parse/build** — `parse_xmpp_uri`/`make_xmpp_uri` implement RFC 5122 /
  XEP-0147 (`xmpp:<jid>[?<action>[;<key>=<value>…]]`), percent-encoding
  preserved on round trips.
- **In chat bodies** — `tokenize_urls` (`include/utils.py`, QWebEngine path)
  and `escape_body_with_geo` (`include/geo.py`, QTextBrowser fallback) turn
  `xmpp:` URIs into clickable `<a>` anchors. In the WebEngine view a click is
  preventDefaulted by the `_ACTION_JS` document handler and relayed through the
  always-running scroll poll as a `link_clicked` (the same defensive relay as
  reply/edit/mention/geo, so the chat document is never reset by the click);
  `ChatWidget.xmpp_link_clicked`
  forwards them through `ChatWindow` to `MainWindow._on_xmpp_uri`.
- **Actions** — bare JID / `?message` opens the chat (a `body`/`thread` param
  is prefilled into the input), `?join` focuses the open room or prefills
  `JoinConferenceDialog` with the room (and persists the server in
  `connection.conference_servers` on accept), `?roster`/`?subscribe` open
  `AddContactDialog` prefilled with the JID, and unrecognized actions warn. An
  address-less `xmpp:?message;body=…` (empty JID) opens `ShareDialog` with that
  body instead.
- **Share** — the WebEngine chat context menu reads the request via
  `QWebEngineView.lastContextMenuRequest()` and always shows the app's own menu
  (never Chromium's): over media the copy/save/view entries, otherwise
  «Поделиться» for a media URL, a link or the selected text (only `http(s)`),
  copy link / open in browser, copy the selection, and "Select all". The media
  kind comes from the `MediaType*` enum members, and an embedded image's
  shareable original URL is decoded from its `stanza:view:` link (the request's
  media URL is only the data-URI thumbnail).
  `ChatView.share_requested` → `ChatWindow` → `MainWindow._on_share_requested`
  opens `ShareDialog` (a checkable list of the roster contacts and the
  conferences we are in) and sends each target a `«Переслано:»` line plus the
  content as a XEP-0393 quote (`compose_reply_body`): 1:1 targets are echoed via
  `_display_local_outgoing` and stored in history, conferences get a groupchat
  message, and a tray notice confirms the count. The per-message menu's
  "Forward" entry forwards the whole message (`[time] sender: text`) through the
  same dialog, and the QTextBrowser fallback adds «Поделиться» to its standard
  menu.
- **Copy to clipboard** — the vCard dialog shows an icon-only copy button
  right beside the JID address (`copy.svg`, tooltip "Copy XMPP address")
  copying `xmpp:<jid>`; the conference roster context menu ("Copy conference
  address") copies `xmpp:<jid>?join`.

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
- File transfer (SI + IBB) and use of the discovered XEP-0065 proxy / STUN-TURN
  for p2p transfers and calls
- Plugin system (convention-based discovery)
- Embedded chat mode (splitter in main window)

Implemented since the original spec: vCard viewing/editing, ad-hoc commands,
service discovery (browser), bookmarks management, MAM (XEP-0313),
preferences dialog, search/registration dialogs, HTTP Upload (XEP-0363),
message replies/corrections, displayed synchronization, media previews,
connection/TLS/STARTTLS/proxy settings, stream management (XEP-0198) and
client state indication (XEP-0352).
