"""Project-wide constants."""
import os

APP_NAME = "Jabbim-next"
VERSION = "0.1.0"

# Path to the resources/ directory.  When running from a source checkout the
# package lives in <project>/jabbim and resources are a sibling
# (<project>/resources).  When installed site-packages/<pkg>/jabbim may carry
# its own resources/ copy — prefer that if it exists.
_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # .../jabbim
_PROJECT_ROOT = os.path.dirname(_PKG_DIR)                                        # .../ (source checkout)
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

STATUS_DIR_16 = os.path.join(IMAGES_DIR, "16x16", "status")
STATUS_DIR_32 = os.path.join(IMAGES_DIR, "32x32", "status")
STATUS_DIR_48 = os.path.join(IMAGES_DIR, "48x48", "status")

ACTIONS_DIR_16 = os.path.join(IMAGES_DIR, "16x16", "actions")
ACTIONS_DIR_22 = os.path.join(IMAGES_DIR, "22x22", "actions")
CATEGORIES_DIR_16 = os.path.join(IMAGES_DIR, "16x16", "categories")
CATEGORIES_DIR_32 = os.path.join(IMAGES_DIR, "32x32", "categories")

APP_ICON_16 = os.path.join(IMAGES_DIR, "16x16", "apps")
APP_ICON_22 = os.path.join(IMAGES_DIR, "22x22", "apps")
APP_ICON_32 = os.path.join(IMAGES_DIR, "32x32", "apps")
APP_ICON_48 = os.path.join(IMAGES_DIR, "48x48", "apps")
APP_ICON_SVG = os.path.join(IMAGES_DIR, "scalable", "apps", "jabbim.svg")

LOGO_SVG = os.path.join(IMAGES_DIR, "scalable", "logo.svg")
LOGO_PNG = os.path.join(IMAGES_DIR, "logo.png")


# ── XDG Base Directory Specification ───────────────────────────────
# https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
#
# Config:   $XDG_CONFIG_HOME/jabbim   (default ~/.config/jabbim)
# Data:     $XDG_DATA_HOME/jabbim     (default ~/.local/share/jabbim)   — history
# Cache:    $XDG_CACHE_HOME/jabbim    (default ~/.cache/jabbim)
#
# Note: the app directory name is lowercased "jabbim" for the XDG dirs even
# though the product is displayed as "Jabbim-next".

_APP_DIR_NAME = "jabbim"


def _xdg_dir(env_var: str, default: str) -> str:
    value = os.environ.get(env_var, "").strip()
    base = value if value and os.path.isabs(value) else default
    return os.path.join(base, _APP_DIR_NAME)


CONFIG_DIR = _xdg_dir("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
DATA_DIR = _xdg_dir("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
CACHE_DIR = _xdg_dir("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.toml")
APP_LOG_FILE = os.path.join(_PROJECT_ROOT, "jabbim.log")

HISTORY_DIR = os.path.join(DATA_DIR, "history")
AVATARS_DIR = os.path.join(CACHE_DIR, "avatars")
