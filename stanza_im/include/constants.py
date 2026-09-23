"""Project-wide constants."""
import os

APP_NAME = "Stanza IM"
VERSION = "0.1.0"

# Path to the resources/ directory.  When running from a source checkout the
# package lives in <project>/stanza_im and resources are a sibling
# (<project>/resources).  When installed site-packages/<pkg>/stanza_im may
# carry its own resources/ copy — prefer that if it exists.
_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # .../stanza_im
_PROJECT_ROOT = os.path.dirname(_PKG_DIR)                                        # .../ (source checkout)
PROJECT_ROOT = _PROJECT_ROOT
_SIBLING_RESOURCES = os.path.join(_PROJECT_ROOT, "resources")
_PKG_RESOURCES = os.path.join(_PKG_DIR, "resources")
RESOURCES_DIR = (_PKG_RESOURCES if os.path.isdir(_PKG_RESOURCES)
                 else _SIBLING_RESOURCES)

IMAGES_DIR = os.path.join(RESOURCES_DIR, "images")
CHATSKINS_DIR = os.path.join(RESOURCES_DIR, "chatskins")
EMOTICONS_DIR = os.path.join(RESOURCES_DIR, "emoticons")
MOODS_DIR = os.path.join(RESOURCES_DIR, "moods")
ACTIVITIES_DIR = os.path.join(RESOURCES_DIR, "activities")
SOUNDS_DIR = os.path.join(RESOURCES_DIR, "sounds")
THEMES_DIR = os.path.join(RESOURCES_DIR, "themes")
# Optional list of suggested registration servers (one domain per line).
SERVERS_FILE = os.path.join(RESOURCES_DIR, "servers.txt")

# Jabber client icons (16x16/22x22/32x32/64x64) and the caps mapping file.
CLIENTS_DIR = os.path.join(RESOURCES_DIR, "clients")
CLIENTS_FILE = os.path.join(CLIENTS_DIR, "clients.txt")

STATUS_DIR_16 = os.path.join(IMAGES_DIR, "16x16", "status")
STATUS_DIR_32 = os.path.join(IMAGES_DIR, "32x32", "status")
STATUS_DIR_48 = os.path.join(IMAGES_DIR, "48x48", "status")

ACTIONS_DIR_16 = os.path.join(IMAGES_DIR, "16x16", "actions")
ACTIONS_DIR_22 = os.path.join(IMAGES_DIR, "22x22", "actions")
CATEGORIES_DIR_16 = os.path.join(IMAGES_DIR, "16x16", "categories")
CATEGORIES_DIR_32 = os.path.join(IMAGES_DIR, "32x32", "categories")

PLACES_DIR_16 = os.path.join(IMAGES_DIR, "16x16", "places")
PLACES_DIR_22 = os.path.join(IMAGES_DIR, "22x22", "places")
PLACES_DIR_32 = os.path.join(IMAGES_DIR, "32x32", "places")

APP_ICON_16 = os.path.join(IMAGES_DIR, "16x16", "apps")
APP_ICON_22 = os.path.join(IMAGES_DIR, "22x22", "apps")
APP_ICON_32 = os.path.join(IMAGES_DIR, "32x32", "apps")
APP_ICON_48 = os.path.join(IMAGES_DIR, "48x48", "apps")

# Scalable (SVG) source icons.  Icons authored for the project live here under
# a category matching the sized directories; the sized directories keep the
# rasterised/legacy art.  ``find_icon`` prefers the scalable copy.
SCALABLE_DIR = os.path.join(IMAGES_DIR, "scalable")
SCALABLE_ACTIONS_DIR = os.path.join(SCALABLE_DIR, "actions")
SCALABLE_CATEGORIES_DIR = os.path.join(SCALABLE_DIR, "categories")
SCALABLE_PLACES_DIR = os.path.join(SCALABLE_DIR, "places")
SCALABLE_APPS_DIR = os.path.join(SCALABLE_DIR, "apps")

APP_ICON_SVG = os.path.join(SCALABLE_APPS_DIR, "stanza-im.svg")

LOGO_SVG = os.path.join(SCALABLE_DIR, "logo.svg")
LOGO_PNG = os.path.join(IMAGES_DIR, "logo.png")

# Ordered icon search paths (scalable first, then the sized directories).
ICON_DIRS_ACTIONS = (SCALABLE_ACTIONS_DIR, ACTIONS_DIR_16, ACTIONS_DIR_22)
ICON_DIRS_CATEGORIES = (SCALABLE_CATEGORIES_DIR, CATEGORIES_DIR_16,
                        SCALABLE_APPS_DIR, APP_ICON_16)
ICON_DIRS_ALL = (SCALABLE_ACTIONS_DIR, ACTIONS_DIR_16, ACTIONS_DIR_22,
                 SCALABLE_CATEGORIES_DIR, CATEGORIES_DIR_16,
                 SCALABLE_PLACES_DIR, PLACES_DIR_22,
                 STATUS_DIR_32, PLACES_DIR_16, STATUS_DIR_16)


def find_icon(filename: str, directories=ICON_DIRS_ALL) -> str:
    """Return the first existing icon path for *filename*, or ""."""
    if not filename:
        return ""
    for directory in directories:
        path = os.path.join(directory, filename)
        if os.path.isfile(path):
            return path
    return ""


# ── XDG Base Directory Specification ───────────────────────────────
# https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
#
# Config:   $XDG_CONFIG_HOME/stanza-im   (default ~/.config/stanza-im)
# Data:     $XDG_DATA_HOME/stanza-im     (default ~/.local/share/stanza-im)   — history
# Cache:    $XDG_CACHE_HOME/stanza-im    (default ~/.cache/stanza-im)

_APP_DIR_NAME = "stanza-im"


def _xdg_dir(env_var: str, default: str) -> str:
    value = os.environ.get(env_var, "").strip()
    base = value if value and os.path.isabs(value) else default
    return os.path.join(base, _APP_DIR_NAME)


CONFIG_DIR = _xdg_dir("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
DATA_DIR = _xdg_dir("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
CACHE_DIR = _xdg_dir("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.toml")
APP_LOG_FILE = os.path.join(_PROJECT_ROOT, "stanza-im.log")

HISTORY_DIR = os.path.join(DATA_DIR, "history")
AVATARS_DIR = os.path.join(CACHE_DIR, "avatars")
