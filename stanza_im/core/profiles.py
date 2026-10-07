"""Application profiles: one account (Jabber ID) each.

A profile stores the credentials and connection settings of an account.  The
active account's credentials also live in the main config (``config.toml``);
this registry keeps every account the user created so it can be switched
without retyping.  Stored as JSON at
``$XDG_CONFIG_HOME/stanza-im/profiles.json`` (0600).

Selecting a profile (:func:`set_active`) points every per-account data store
(history, roster cache, unread counters, known contacts) at
``$XDG_DATA_HOME/stanza-im/<jid>/`` and drops the pooled history connections so
one account's data never leaks into another.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass

from stanza_im.include import constants
from stanza_im.include.constants import CONFIG_DIR, DATA_DIR

logger = logging.getLogger(__name__)

PROFILES_FILE = os.path.join(CONFIG_DIR, "profiles.json")


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class Profile:
    """Credentials and connection settings of one account."""

    jid: str
    password: str = ""
    save_password: bool = True
    override_host: bool = False
    host: str = ""
    port: int = 5222
    tls_mode: str = "prefer"
    starttls_mode: str = "always"
    proxy_mode: str = "none"
    proxy_host: str = ""
    proxy_port: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        data = data or {}
        return cls(
            jid=str(data.get("jid") or "").strip(),
            password=str(data.get("password") or ""),
            save_password=bool(data.get("save_password", True)),
            override_host=bool(data.get("override_host", False)),
            host=str(data.get("host") or ""),
            port=_coerce_int(data.get("port", 5222), 5222),
            tls_mode=str(data.get("tls_mode") or "prefer"),
            starttls_mode=str(data.get("starttls_mode") or "always"),
            proxy_mode=str(data.get("proxy_mode") or "none"),
            proxy_host=str(data.get("proxy_host") or ""),
            proxy_port=_coerce_int(data.get("proxy_port", 0), 0),
        )


def load() -> list[Profile]:
    """Return the stored profiles (empty on a missing/corrupt file)."""
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Could not read %s: %s", PROFILES_FILE, exc)
        return []
    if not isinstance(data, dict):
        return []
    items = data.get("profiles")
    if not isinstance(items, list):
        return []
    profiles: list[Profile] = []
    for entry in items:
        if isinstance(entry, dict) and str(entry.get("jid") or "").strip():
            profiles.append(Profile.from_dict(entry))
    return profiles


def save(profiles: list[Profile]) -> None:
    """Persist *profiles* to disk with 0600 permissions."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        payload = {"profiles": [asdict(p) for p in profiles]}
        tmp = PROFILES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, PROFILES_FILE)
        os.chmod(PROFILES_FILE, 0o600)
    except OSError as exc:
        logger.warning("Could not save profiles: %s", exc)


def get(jid: str) -> Profile | None:
    """Return the profile for *jid*, or ``None``."""
    jid = str(jid or "").strip()
    if not jid:
        return None
    for profile in load():
        if profile.jid == jid:
            return profile
    return None


def upsert(profile: Profile) -> None:
    """Insert or replace *profile* (matched by JID)."""
    if not profile or not profile.jid:
        return
    profiles = load()
    for index, existing in enumerate(profiles):
        if existing.jid == profile.jid:
            profiles[index] = profile
            break
    else:
        profiles.append(profile)
    save(profiles)


def remove(jid: str) -> None:
    """Drop the profile for *jid* from the registry (keeps its data)."""
    jid = str(jid or "").strip()
    profiles = [p for p in load() if p.jid != jid]
    save(profiles)


def from_config(config) -> Profile:
    """Build a profile from the active account in *config*."""
    conn = getattr(config, "connection", None)
    return Profile(
        jid=str(getattr(config, "jid", "") or "").strip(),
        password=str(getattr(config, "password", "") or ""),
        save_password=bool(getattr(config, "save_password", False)),
        override_host=bool(getattr(conn, "override_host", False)),
        host=str(getattr(conn, "host", "") or ""),
        port=_coerce_int(getattr(conn, "port", 5222), 5222),
        tls_mode=str(getattr(conn, "tls_mode", "prefer") or "prefer"),
        starttls_mode=str(getattr(conn, "starttls_mode", "always") or "always"),
        proxy_mode=str(getattr(conn, "proxy_mode", "none") or "none"),
        proxy_host=str(getattr(conn, "proxy_host", "") or ""),
        proxy_port=_coerce_int(getattr(conn, "proxy_port", 0), 0),
    )


def apply_to_config(config, profile: Profile) -> None:
    """Write *profile* as the active account and persist the config."""
    config.jid = profile.jid
    config.password = profile.password
    config.save_password = profile.save_password
    conn = config.connection
    conn.override_host = profile.override_host
    conn.host = profile.host
    conn.port = profile.port
    conn.tls_mode = profile.tls_mode
    conn.starttls_mode = profile.starttls_mode
    conn.proxy_mode = profile.proxy_mode
    conn.proxy_host = profile.proxy_host
    conn.proxy_port = profile.proxy_port
    config.save()


def delete_data(jid: str) -> bool:
    """Delete the per-account data directory for *jid* (history etc.)."""
    name = constants._safe_profile_name(jid)
    if not name or name in (".", ".."):
        return False
    path = os.path.join(DATA_DIR, name)
    if os.path.isdir(path):
        try:
            shutil.rmtree(path, ignore_errors=True)
        except OSError as exc:
            logger.warning("Could not delete profile data %s: %s", path, exc)
            return False
    return True


def set_active(jid: str) -> None:
    """Select *jid* as the active profile and point the data stores at it.

    Every per-account store is re-based and the pooled history connections are
    closed, so a contact's history from one account can never be served to
    another (the pool is keyed by the *contact* JID).
    """
    from stanza_im.core import (
        history, known_contacts, roster_cache, unread_state)
    history.set_profile(jid)
    roster_cache.set_profile(jid)
    unread_state.set_profile(jid)
    known_contacts.set_profile(jid)
    history.close_all()
