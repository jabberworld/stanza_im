# AGENTS.md — Jabbim-next Architecture

## Overview

Jabbim-next is a lightweight XMPP/Jabber desktop client for Linux, inspired by the
original Jabbim client (2007-2012). Written in Python 3 + PyQt6 + slixmpp.

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
| i18n | Python dicts in `jabbim/i18n/*.py`, no compilation |

## Directory Structure

```
jabbim/                          # Python package
├── __init__.py
├── __main__.py                  # python -m jabbim
├── app.py                       # Entry point: qasync event loop
├── core/
│   ├── client.py                # JabberClient: slixmpp wrapper
│   └── storage.py               # Config (TOML) + JSONL chat history (XDG)
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
│   └── icons.py                 # LRU icon cache (lazy, auto-evict)
├── xmpp/                        # (Phase 2) Extended XMPP modules
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
old/                             # Original Jabbim code (reference only)
main.py                          # python main.py entry point
pyproject.toml                   # Package config
```

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
| Config (TOML) | `$XDG_CONFIG_HOME/jabbim/config.toml` (0600) |
| Chat history (JSONL) | `$XDG_DATA_HOME/jabbim/history/<bare-jid>.jsonl` (0600) |

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

## Memory Management Rules

1. **IconCache**: max 200 entries, 60s TTL, auto-eviction every 30s
2. **Avatars**: stored as `str` path, QPixmap created in paintEvent, never cached long-term
3. **ChatView**: shared `QWebEngineProfile` (not per-tab)
4. **Inactive MUCs**: planned — reduce resources after 10min idle
5. **Roster**: no child widgets, single QPainter pass

## Running

```bash
python main.py              # Direct
python -m jabbim            # Module
```

Requires: Python 3.10+, PyQt6, PyQt6-WebEngine, slixmpp, qasync, defusedxml.
System libs: libglib2.0, libgl1, libx11-6, libfontconfig1 (for PyQt6).

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
