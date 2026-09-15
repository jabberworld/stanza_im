"""XDG Base Directory persistence: application config and chat history.

Config is stored in ``$XDG_CONFIG_HOME/stanza-im/config.toml`` (default
``~/.config/stanza-im/config.toml``).  Chat history is stored per-JID as JSON
lines in ``$XDG_DATA_HOME/stanza-im/history/`` (default
``~/.local/share/stanza-im/history/``).
"""
from __future__ import annotations

import json
import logging
import os
import time
import tomllib

from stanza_im.include.constants import CONFIG_DIR, CONFIG_FILE, HISTORY_DIR

logger = logging.getLogger(__name__)


def _ensure_dirs() -> None:
    for d in (CONFIG_DIR, HISTORY_DIR):
        os.makedirs(d, exist_ok=True)


def _chmod_private(path: str) -> None:
    """Restrict permissions of a file to the current user (0600)."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        logger.warning("Could not chmod %s to 0600", path)


class AttrDict(dict):
    """dict that also exposes its keys as attributes (recursive sections)."""

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value) -> None:
        self[name] = value

    def _wrap(self) -> "AttrDict":
        for key, value in list(self.items()):
            if isinstance(value, dict) and not isinstance(value, AttrDict):
                self[key] = AttrDict(value)
        return self


class Config:
    """Thin wrapper around the TOML config file.

    Values are exposed as attributes with defaults.  ``save()`` writes the
    whole config back verbatim (only the values that were loaded, plus any
    that have been set) so manual edits are preserved.  Nested sections are
    returned as :class:`AttrDict`, so ``cfg.chat.show_avatars`` works.
    """

    DEFAULTS: dict = {
        "jid": "",
        "password": "",
        "save_password": False,
        "auto_connect": False,
        "last_status": "online",
        "window": {"width": 300, "height": 600,
                   "x": 0, "y": 0, "maximized": False},
        "chat": {"show_avatars": True, "theme": "", "history_limit": 60,
                 "tab_title_length": 30, "send_ctrl_enter": False,
                 "show_status": True, "show_receipts": True,
                 "show_mood": False, "show_music": False,
                 "muc_show_presence": True, "muc_show_status": True,
                 "muc_show_status_text": True,
                 "muc_auto_nick": True, "muc_confirm_leave": True,
                 "muc_minimize_startup": True, "message_styling": True,
                 "message_displayed_sync": True,
                 "allow_incoming_edits": True, "input_height": 60,
                 "text_scale": 1.0, "media_preview": "images"},
        "chat_window": {"width": 640, "height": 480,
                        "x": 0, "y": 0, "maximized": False},
        "media_viewer": {"width": 900, "height": 680,
                         "x": 0, "y": 0, "maximized": False},
        "map": {"tiles_url": "https://tile.openstreetmap.org",
                "tile_cache_mb": 64, "tile_cache_days": 14.0,
                "follow": True,
                "window": {"width": 700, "height": 520,
                           "x": 0, "y": 0, "maximized": False}},
        "application": {"close_to_tray": True, "history_limit": 60,
                         "tab_title_length": 30},
        "connection": {"auto_join_conferences": True,
                        "save_status_message": True, "resource": "jabbim",
                        "resource_mode": "hostname",
                        "priority_mode": "status", "priority": 50,
                        "override_host": False, "host": "", "port": 5222,
                        "proxy_mode": "none",
                        "proxy_host": "", "proxy_port": 0,
                        "file_proxy_mode": "auto", "file_proxy_manual": "",
                        "stun_turn_mode": "auto", "stun_turn_manual": "",
                        "keepalive": True,
                        "stream_management": True,
                        "csi": True,
                        "tls_mode": "prefer",
                        "starttls_mode": "always",
                        "pep_sweep_interval": 0,
                        "message_carbons": True,
                        "conference_servers": [], "service_servers": []},
        "privacy": {"send_software": True, "send_typing_notifications": True,
                     "send_activity_notifications": True, "send_chatstates": True},
        "files": {"auto_accept": False, "download_notifications": True,
                  "download_dir": ""},
        "devices": {"audio_input": "", "audio_output": "", "video_input": ""},
        "calls": {"auto_accept": False},
        "appearance": {"chat_theme": "", "muc_theme": "",
                        "emoticon_theme": "default/smileys.cfg",
                        "media_preview_size": 200,
                        "media_cache_days": 30,
                        "media_cache_mb": 128,
                        "muc_highlight": "both",
                        "roster_bg_color": "#ffffff",
                        "roster_group_bg_color": "#ececec",
                        "chat_bg_color": "#ffffff",
                        "muc_highlight_color": "#e53935",
                        "colored_muc_nicks": True,
                        "roster_show_avatars": True,
                        "roster_show_activity": True,
                        "roster_show_mood": True,
                        "roster_font": "", "roster_font_size": 0,
                        "chat_font": "", "chat_font_size": 0,
                        "osd_font": "", "osd_font_size": 0,
                        "nick_font": "", "nick_font_size": 0,
                        "participant_font": "", "participant_font_size": 0},
        "notifications": {"tray_blink": True, "popups": True,
                           "sound_any_message": False,
                           "sound_first_message": False,
                           "sound_login": False, "sound_file_transfer": False,
                           "osd_enabled": False, "osd_message": True,
                           "osd_file": True, "osd_typing": False,
                           "osd_status": "available",
                           "osd_conference": "mention",
                           "osd_topdown": True, "osd_duration": 5,
                           "osd_max": 3, "osd_x": 0, "osd_y": 0},
        "status": {"auto_away": False, "away_minutes": 5,
                   "auto_xa": False, "xa_minutes": 15,
                   "auto_status_message": "",
                   "message": "", "mood": "", "activity": ""},
        "ui": {"close_to_tray": True},
    }

    def __init__(self):
        self._data: dict = {k: AttrDict(v)._wrap() if isinstance(v, dict) else v
                            for k, v in self.DEFAULTS.items()}
        self.load()

    # ── Loading / saving ─────────────────────────────────────────

    def load(self) -> None:
        """Load config from disk (missing file → defaults)."""
        _ensure_dirs()
        if not os.path.isfile(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "rb") as fh:
                data = tomllib.load(fh)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            logger.warning("Could not parse %s: %s", CONFIG_FILE, exc)
            return

        for key, value in data.items():
            if key in self.DEFAULTS and isinstance(value, type(self.DEFAULTS[key])):
                # Deep-merge so default keys survive partial TOML sections.
                if isinstance(value, dict):
                    merged = AttrDict({**self.DEFAULTS[key], **value})._wrap()
                else:
                    merged = value
                self._data[key] = merged
            elif key not in self.DEFAULTS:
                self._data[key] = value

    def save(self) -> None:
        """Write config to disk with 0600 permissions."""
        _ensure_dirs()
        tmp_path = CONFIG_FILE + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                self._write_toml(fh, self._data)
            os.replace(tmp_path, CONFIG_FILE)
            _chmod_private(CONFIG_FILE)
        except OSError as exc:
            logger.warning("Could not save config: %s", exc)

    @staticmethod
    def _write_toml(fh, data: dict) -> None:
        """Minimal recursive TOML writer (nested dicts as dot-tables)."""

        def _write(fh, data: dict, prefix: str) -> None:
            scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
            tables = {k: v for k, v in data.items() if isinstance(v, dict)}
            if scalars:
                if prefix:
                    fh.write(f"[{prefix}]\n")
                for key, value in scalars.items():
                    fh.write(f"{key} = {json.dumps(value)}\n")
                fh.write("\n")
            for key, value in tables.items():
                _write(fh, value, f"{prefix}.{key}" if prefix else key)

        _write(fh, data, "")

    # ── Attribute access ──────────────────────────────────────────

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value

    def __getattr__(self, name: str):
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def as_dict(self) -> AttrDict:
        """Return the underlying data as a plain dict (for TOML writing)."""
        return self._data


# ── Chat history ──────────────────────────────────────────────────


def history_path(jid: str) -> str:
    """Return the JSON-lines file for a single JID's history."""
    safe = jid.lower().replace("/", "_")
    return os.path.join(HISTORY_DIR, f"{safe}.jsonl")


def save_history_entry(jid: str, direction: str, body: str,
                       timestamp: str | None = None, sender: str = "") -> None:
    """Append one message to the history log for *jid*.

    *direction* is "incoming" or "outgoing"; *sender* is the display name
    (for outgoing this is typically the local nick).
    """
    try:
        os.makedirs(HISTORY_DIR, exist_ok=True)
        entry = {
            "direction": direction,
            "sender": sender,
            "body": body,
            "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with open(history_path(jid), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            _chmod_private(history_path(jid))
    except OSError as exc:
        logger.warning("Could not save history for %s: %s", jid, exc)


def load_history(jid: str, limit: int = 200) -> list[dict]:
    """Read recent history entries for *jid* (oldest first, capped at
    *limit*)."""
    path = history_path(jid)
    if not os.path.isfile(path):
        return []
    entries: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        logger.warning("Could not read history for %s: %s", jid, exc)
        return []
    return entries[-limit:]
