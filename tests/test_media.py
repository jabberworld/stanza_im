"""Offscreen smoke tests for media previews (kind/cache/markup/settings).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_media.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_media_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.include import media as media_mod
from stanza_im.include.media import MediaCache, media_kind
from stanza_im.include.utils import tokenize_urls, restore_url_tokens
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.media_preview import MediaPreviewService, mode_allows
from stanza_im.core.storage import Config

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _png_bytes():
    image = QtGui.QImage(6, 4, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtCore.Qt.GlobalColor.red)
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


# 1. kind detection -----------------------------------------------------------
check("image ext", media_kind("https://h/p/photo.JPG?x=1") == "image")
check("audio ext", media_kind("https://h/a/song.mp3") == "audio")
check("video ext", media_kind("https://h/v/clip.webm#t=1") == "video")
check("non-media url", media_kind("https://h/doc/report.pdf") is None)
check("encoded name", media_kind("https://h/a/my%20photo.png") == "image")

# 2. mode gating --------------------------------------------------------------
check("none gates all", not any(mode_allows("none", k)
      for k in ("image", "audio", "video")))
check("images only", mode_allows("images", "image")
      and not mode_allows("images", "audio"))
check("images_audio", mode_allows("images_audio", "image")
      and mode_allows("images_audio", "audio")
      and not mode_allows("images_audio", "video"))
check("all allows all", all(mode_allows("all", k)
      for k in ("image", "audio", "video")))

# 3. cache store / lookup -----------------------------------------------------
cache_dir = os.path.join(_SCRATCH, "mediacache")
cache = MediaCache(directory=cache_dir, ttl_days=30, max_bytes=10 * 1024 * 1024)
url = "https://h/p/photo.png"
cache.store(url, original_bytes=b"ORIGINAL", thumb_bytes=_png_bytes(),
            kind="image")
check("thumb cached", cache.has_thumb(url))
check("thumb path exists", os.path.isfile(cache.thumb_path(url) or ""))
check("original path exists", os.path.isfile(cache.original_path(url) or ""))

# 4. TTL pruning --------------------------------------------------------------
old_url = "https://h/old.png"
cache.store(old_url, original_bytes=b"OLD", thumb_bytes=_png_bytes())
cache._ttl = 1.0  # 1 second
cache._index[media_mod.url_key(old_url)]["last_access"] = time.time() - 60
removed = cache.prune()
check("ttl prune removed stale", removed >= 1 and not cache.has_thumb(old_url))

# 5. size-cap LRU pruning -----------------------------------------------------
cache2 = MediaCache(directory=os.path.join(_SCRATCH, "mediacache2"),
                    ttl_days=30, max_bytes=1000000)
u_old = "https://h/a.png"
u_new = "https://h/b.png"
cache2.store(u_old, original_bytes=b"x" * 2000)
cache2.store(u_new, original_bytes=b"y" * 2000)
keys = {k: media_mod.url_key(u) for k, u in (("old", u_old), ("new", u_new))}
cache2._index[keys["old"]]["last_access"] = time.time() - 100
cache2._index[keys["new"]]["last_access"] = time.time()
cache2._max_bytes = 2500
cache2.prune()
check("size cap evicts LRU", not cache2.original_path(u_old)
      and cache2.original_path(u_new))

# 6. service markup -----------------------------------------------------------
service = MediaPreviewService(cache)
service.set_size(180)
service.set_mode("all")
img_html = service.markup(url)
check("image markup embed", img_html and "stanza:view:image/" in img_html
      and "data:image/png;base64," in img_html and 'width="180"' in img_html)
audio_html = service.markup("https://h/a/song.mp3")
check("audio markup", audio_html and "<audio" in audio_html
      and 'data-media-url="https://h/a/song.mp3"' in audio_html)
video_html = service.markup("https://h/v/clip.mp4")
check("video markup", video_html and "<video" in video_html
      and "stanza:view:video/" in video_html)
service.set_mode("none")
check("none mode -> no markup", service.markup(url) is None)
service.set_mode("images")
check("images mode gates audio", service.markup("https://h/a/song.mp3") is None)
service.request = lambda _u: None
placeholder = service.markup("https://h/p/uncached.png")
check("uncached image placeholder", placeholder
      and "stanza-media-loading" in placeholder
      and "data:image/png;base64," not in placeholder)

# 7. theme integration --------------------------------------------------------
factory = ChatThemeFactory()
factory.set_message_styling(False)
factory.set_media_preview(service, "images", 180)
html = factory.render_message("Bob", f"look {url}", "12:00:00", "incoming")
check("theme embeds preview", "stanza-media" in html and "<img" in html)
factory.set_media_preview(service, "none", 180)
plain = factory.render_message("Bob", f"look {url}", "12:00:00", "incoming")
check("theme plain link when off", 'stanza-media' not in plain
      and f'<a href="{url}">' in plain)

# 8. tokenize_urls media hook -------------------------------------------------
_tmp, anchors = tokenize_urls("see https://h/p/x.png now")
check("default anchor", anchors and anchors[0].startswith("<a href="))
_tmp, anchors2 = tokenize_urls("see https://h/p/x.png now",
                               lambda u: "<b>EMBED</b>")
check("media_render hook", anchors2 == ["<b>EMBED</b>"])

# 9. config defaults + roundtrip ---------------------------------------------
cfg = Config()
check("default media_preview", cfg.chat.media_preview == "images")
check("default preview size", cfg.appearance.media_preview_size == 200)
check("default cache days", cfg.appearance.media_cache_days == 30)
check("default cache mb", cfg.appearance.media_cache_mb == 128)
cfg.chat.media_preview = "all"
cfg.appearance.media_preview_size = 320
cfg.appearance.media_cache_days = 7
cfg.appearance.media_cache_mb = 64
cfg.save()
cfg2 = Config()
check("media settings persisted",
      cfg2.chat.media_preview == "all"
      and cfg2.appearance.media_preview_size == 320
      and cfg2.appearance.media_cache_days == 7
      and cfg2.appearance.media_cache_mb == 64)

# 10. preferences controls ----------------------------------------------------
from stanza_im.ui.preferences import PreferencesDialog
prefs_cfg = Config()
prefs_cfg.chat.media_preview = "images"
dlg = PreferencesDialog(prefs_cfg, ChatThemeFactory())
for key in ("media_preview", "media_preview_size",
            "media_cache_days", "media_cache_mb"):
    check(f"prefs control {key}", key in dlg._controls)
check("prefs media_preview default",
      dlg._controls["media_preview"].currentData() == "images")

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
