"""XMPP presence enumerations: show states, icon keys, translated labels, moods, activities."""
from __future__ import annotations


# XMPP show -> numeric sort key (lower = higher priority)
SHOW_ORDER: dict[str, int] = {
    "online": 1,
    "available": 1,
    "chat": 0,
    "away": 3,
    "xa": 4,
    "dnd": 5,
    "offline": 9,
    "unavailable": 9,
    "None": 1,
    "": 1,
}

# Numeric key -> filename fragment for status icons
ICON_KEYS: dict[str, str] = {
    "1": "online",
    "0": "chat",
    "3": "away",
    "4": "xa",
    "5": "dnd",
    "9": "offline",
}

# XMPP show -> icon filename fragment (direct, non-numeric)
SHOW_TO_ICON: dict[str, str] = {
    "online": "online",
    "available": "online",
    "chat": "chat",
    "away": "away",
    "xa": "xa",
    "dnd": "dnd",
    "offline": "offline",
    "unavailable": "offline",
    "": "offline",
    "None": "online",
}


def show_to_icon_key(show: str) -> str:
    """Map an XMPP show value to a status-icon filename fragment."""
    return SHOW_TO_ICON.get(show, "offline")

# show string -> translated human-readable label (populated at init time)
STATUS_LABELS: dict[str, str] = {}

# XMPP mood names (XEP-0107)
MOODS: dict[str, str] = {
    "none": "None",
    "afraid": "afraid",
    "amazed": "amazed",
    "angry": "angry",
    "annoyed": "annoyed",
    "anxious": "anxious",
    "aroused": "aroused",
    "ashamed": "ashamed",
    "bored": "bored",
    "brave": "brave",
    "calm": "calm",
    "cold": "cold",
    "confused": "confused",
    "contented": "contented",
    "cranky": "cranky",
    "curious": "curious",
    "depressed": "depressed",
    "disappointed": "disappointed",
    "disgusted": "disgusted",
    "distracted": "distracted",
    "embarrassed": "embarrassed",
    "excited": "excited",
    "flirtatious": "flirtatious",
    "frustrated": "frustrated",
    "grumpy": "grumpy",
    "guilty": "guilty",
    "happy": "happy",
    "hot": "hot",
    "humbled": "humbled",
    "humiliated": "humiliated",
    "hungry": "hungry",
    "hurt": "hurt",
    "impressed": "impressed",
    "in_awe": "in awe",
    "in_love": "in love",
    "indignant": "indignant",
    "interested": "interested",
    "intoxicated": "intoxicated",
    "invincible": "invincible",
    "jealous": "jealous",
    "lonely": "lonely",
    "mean": "mean",
    "moody": "moody",
    "nervous": "nervous",
    "neutral": "neutral",
    "offended": "offended",
    "playful": "playful",
    "proud": "proud",
    "relieved": "relieved",
    "remorseful": "remorseful",
    "restless": "restless",
    "sad": "sad",
    "sarcastic": "sarcastic",
    "serious": "serious",
    "shocked": "shocked",
    "shy": "shy",
    "sick": "sick",
    "sleepy": "sleepy",
    "stressed": "stressed",
    "surprised": "surprised",
    "thirsty": "thirsty",
    "worried": "worried",
}

# XMPP activity groups and sub-activities (XEP-0108)
ACTIVITY_GROUPS: dict[str, list[str]] = {
    "doing_chores": ["groceries", "cooking", "maintenance", "dishes", "laundry", "gardening", "errand", "dog_walking"],
    "drinking": ["beer", "coffee", "tea"],
    "eating": ["snack", "breakfast", "dinner", "lunch"],
    "exercising": ["cycling", "dancing", "hiking", "jogging", "sports", "running", "skiing", "swimming", "workout"],
    "grooming": ["spa", "teeth", "haircut", "shaving", "bath", "shower"],
    "inactive": ["appointment", "day_off", "hanging_out", "hiding", "vacation", "praying", "holiday", "sleeping"],
    "thinking": ["fishing", "gaming", "going_out", "partying", "reading", "rehearsing", "shopping", "smoking", "socializing", "sunbathing", "tv", "movie", "talking", "real_life", "phone", "video_phone"],
    "traveling": ["commuting", "driving", "car", "bus", "plane", "train", "trip", "walking"],
    "working": ["coding", "meeting", "studying", "writing"],
}


def populate_translations(tr_func):
    """Populate STATUS_LABELS using the i18n tr() function."""
    STATUS_LABELS.update({
        "online": tr_func("status_online"),
        "available": tr_func("status_online"),
        "chat": tr_func("status_chat"),
        "away": tr_func("status_away"),
        "xa": tr_func("status_xa"),
        "dnd": tr_func("status_dnd"),
        "offline": tr_func("status_offline"),
        "unavailable": tr_func("status_offline"),
        "None": tr_func("status_online"),
        "": tr_func("status_online"),
        "invisible": tr_func("status_invisible"),
    })
