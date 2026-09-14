"""Personal Eventing Protocol payloads for extended presence.

Covers the four "extended presence" XEPs used by the roster/profile UI:

* XEP-0080 User Location (``http://jabber.org/protocol/geoloc``)
* XEP-0107 User Mood (``http://jabber.org/protocol/mood``)
* XEP-0108 User Activity (``http://jabber.org/protocol/activity``)
* XEP-0118 User Tune (``http://jabber.org/protocol/tune``)

The module builds and parses the payload elements, parses the bundled Jabbim
mood/activity icon packs, and formats a human-readable summary for the roster
tooltip and the profile "Status" tab.
"""
from __future__ import annotations

import logging
import os
from xml.etree import ElementTree as ET

from stanza_im.include.constants import ACTIVITIES_DIR, MOODS_DIR, IMAGES_DIR
from stanza_im.include.enumerators import ACTIVITY_GROUPS, MOODS
from stanza_im.i18n import tr

logger = logging.getLogger(__name__)

NS_MOOD = "http://jabber.org/protocol/mood"
NS_ACTIVITY = "http://jabber.org/protocol/activity"
NS_TUNE = "http://jabber.org/protocol/tune"
NS_GEOLOC = "http://jabber.org/protocol/geoloc"

# node namespace -> short kind used in pep_data / UI
PEP_NODES: dict[str, str] = {
    NS_MOOD: "mood",
    NS_ACTIVITY: "activity",
    NS_TUNE: "tune",
    NS_GEOLOC: "location",
}
PEP_KINDS = tuple(PEP_NODES.values())

_TUNE_FIELDS = ("artist", "length", "rating", "source", "title", "track", "uri")
_GEOLOC_FIELDS = (
    "accuracy", "alt", "area", "bearing", "building", "country", "countrycode",
    "datum", "description", "floor", "lat", "locality", "lon", "postalcode",
    "region", "room", "speed", "street", "text", "timestamp", "tzo", "uri",
)


def _q(ns: str, tag: str) -> str:
    return "{%s}%s" % (ns, tag)


# ── Payload builders / parsers ────────────────────────────────────

def build_mood(key: str, text: str = "") -> ET.Element:
    """Build a ``<mood/>`` payload; an empty ``key``/``"none"`` clears it."""
    mood = ET.Element(_q(NS_MOOD, "mood"))
    if key and key != "none":
        ET.SubElement(mood, _q(NS_MOOD, key))
    if text:
        node = ET.SubElement(mood, _q(NS_MOOD, "text"))
        node.text = text
    return mood


def parse_mood(el: ET.Element) -> dict:
    """Parse a ``<mood/>`` element into ``{"key", "text"}``."""
    result = {"key": "", "text": ""}
    for child in el:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "text":
            result["text"] = (child.text or "").strip()
        elif not result["key"] and tag in MOODS:
            result["key"] = tag
    return result


def build_activity(group: str, sub: str = "") -> ET.Element:
    """Build an ``<activity/>`` payload (empty group clears it)."""
    activity = ET.Element(_q(NS_ACTIVITY, "activity"))
    if group:
        group_el = ET.SubElement(activity, _q(NS_ACTIVITY, group))
        if sub:
            ET.SubElement(group_el, _q(NS_ACTIVITY, sub))
    return activity


def parse_activity(el: ET.Element) -> dict:
    """Parse an ``<activity/>`` element into ``{"group", "sub", "text"}``."""
    result = {"group": "", "sub": "", "text": ""}
    for child in el:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "text":
            result["text"] = (child.text or "").strip()
            continue
        if not result["group"] and tag in ACTIVITY_GROUPS:
            result["group"] = tag
            for sub in child:
                sub_tag = sub.tag.rsplit("}", 1)[-1]
                if sub_tag not in ("text",):
                    result["sub"] = sub_tag
                    break
    return result


def _parse_fields(el: ET.Element, fields: tuple[str, ...]) -> dict:
    result: dict[str, str] = {}
    for child in el:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag in fields and (child.text or "").strip():
            result[tag] = (child.text or "").strip()
    return result


def parse_tune(el: ET.Element) -> dict:
    return _parse_fields(el, _TUNE_FIELDS)


def parse_geoloc(el: ET.Element) -> dict:
    return _parse_fields(el, _GEOLOC_FIELDS)


def parse_payload(node: str, el: ET.Element) -> dict:
    """Dispatch on the PEP node namespace."""
    if node == NS_MOOD:
        return parse_mood(el)
    if node == NS_ACTIVITY:
        return parse_activity(el)
    if node == NS_TUNE:
        return parse_tune(el)
    if node == NS_GEOLOC:
        return parse_geoloc(el)
    return {}


# ── Icon packs (resources/moods, resources/activities) ────────────

_ICON_CACHE: dict[str, dict[str, str]] = {}


def _parse_icon_cfg(path: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [line.strip() for line in fh]
    except OSError:
        return mapping
    active = False
    for line in lines:
        if not line:
            continue
        if line.startswith("["):
            active = line.strip("[]").lower() in ("moods", "activities")
            continue
        if not active or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().strip("'\"")
        value = value.strip().strip("'\"")
        if key and value:
            mapping.setdefault(key, value)
    return mapping


def _icon_pack(root: str, kind: str) -> dict[str, str]:
    """Return ``{key: absolute icon path}`` for the default icon pack."""
    if kind in _ICON_CACHE:
        return _ICON_CACHE[kind]
    resolved: dict[str, str] = {}
    cfg_path = ""
    for dirpath, _dirs, files in os.walk(root):
        for filename in sorted(files):
            if filename.endswith(".cfg"):
                cfg_path = os.path.join(dirpath, filename)
                break
        if cfg_path:
            break
    if cfg_path:
        directory = os.path.dirname(cfg_path)
        for key, filename in _parse_icon_cfg(cfg_path).items():
            path = os.path.join(directory, filename)
            if os.path.isfile(path):
                resolved[key] = path
    _ICON_CACHE[kind] = resolved
    return resolved


def mood_icons() -> dict[str, str]:
    return _icon_pack(MOODS_DIR, "mood")


def activity_icons() -> dict[str, str]:
    return _icon_pack(ACTIVITIES_DIR, "activity")


def default_icon(kind: str) -> str:
    """Generic icon used for the "none" entry and unknown keys."""
    if kind == "mood":
        candidate = os.path.join(IMAGES_DIR, "16x16", "emotes", "smile.png")
    else:
        candidate = activity_icons().get("inactive", "")
    return candidate if os.path.isfile(candidate) else ""


def mood_icon_path(key: str) -> str:
    """Absolute icon path for a mood ``key`` ('' when unset)."""
    if not key or key == "none":
        return ""
    return mood_icons().get(key) or default_icon("mood")


def activity_icon_path(key: str) -> str:
    """Absolute icon path for an activity leaf ``key`` ('' when unset)."""
    if not key:
        return ""
    return activity_icons().get(key) or default_icon("activity")


def clear_cache() -> None:
    _ICON_CACHE.clear()


# ── Summary for tooltip / profile ─────────────────────────────────

def mood_label(key: str) -> str:
    if not key or key == "none":
        return tr("pep_none")
    return tr("mood_%s" % key)


def activity_label(group: str, sub: str = "") -> str:
    parts = []
    if group:
        parts.append(tr("activity_group_%s" % group))
    if sub:
        parts.append(tr("activity_%s" % sub))
    return " \u203a ".join(parts) if parts else tr("pep_none")


def format_summary(entry: dict) -> dict[str, str]:
    """Turn a cached PEP entry into ``{kind: display string}`` pairs."""
    out: dict[str, str] = {}
    mood = entry.get("mood")
    if mood and mood.get("key"):
        text = mood.get("text") or ""
        label = mood_label(mood["key"])
        out["mood"] = f"{label}: {text}" if text else label
    activity = entry.get("activity")
    if activity and activity.get("group"):
        text = activity.get("text") or ""
        label = activity_label(activity.get("group", ""), activity.get("sub", ""))
        out["activity"] = f"{label}: {text}" if text else label
    tune = entry.get("tune")
    if tune:
        artist = tune.get("artist", "")
        title = tune.get("title", "")
        if artist and title:
            value = f"{artist} \u2014 {title}"
        else:
            value = title or artist or tune.get("source", "")
        if value:
            out["tune"] = value
    location = entry.get("location")
    if location:
        place = ", ".join(p for p in (location.get("locality", ""),
                                      location.get("country", "")) if p)
        coords = ""
        if location.get("lat") and location.get("lon"):
            coords = "%s, %s" % (location["lat"], location["lon"])
        if place and coords:
            value = f"{place} ({coords})"
        else:
            value = place or coords or location.get("description", "")
        if value:
            out["location"] = value
    return out
