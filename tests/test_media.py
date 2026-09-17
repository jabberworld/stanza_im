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

# 7b. startup wiring: the factory pushes the mode into the service ------------
#     (regression: MainWindow passed the mode only to the factory, so the
#      service kept its "images" default and dropped audio/video embeds)
startup_svc = MediaPreviewService(cache)
startup_factory = ChatThemeFactory()
startup_factory.set_message_styling(False)
startup_factory.set_media_preview(startup_svc, "all", 180)
check("startup service mode synced", startup_svc.mode == "all")
mp3_html = startup_factory.render_message(
    "Bob", "https://h/a/song.mp3", "12:00:00", "incoming")
check("startup audio embed", "<audio" in mp3_html)
mp4_html = startup_factory.render_message(
    "Bob", "https://h/v/clip.mp4", "12:00:00", "incoming")
check("startup video embed", "<video" in mp4_html)

# 7c. a URL query string is HTML-escaped exactly once -------------------------
q_url = "https://h/a/song.mp3?token=abc&x=1"
q_html = startup_factory.render_message("Bob", q_url, "12:00:00", "incoming")
check("query '&' single-escaped", "&amp;amp;" not in q_html
      and "?token=abc&amp;x=1" in q_html)

# 7d. thumbnail data-URI cache is bounded (LRU by bytes) ---------------------
from stanza_im.ui import media_preview as media_preview_mod

thumb_svc = MediaPreviewService(cache)
saved_thumb_budget = media_preview_mod._THUMB_CACHE_BYTES
media_preview_mod._THUMB_CACHE_BYTES = 40
try:
    for i in range(10):
        thumb_svc._remember_thumb("u%d" % i, "x" * 10)
    check("thumbnail cache respects the byte budget",
          thumb_svc._thumb_bytes <= media_preview_mod._THUMB_CACHE_BYTES)
    check("thumbnail cache evicts the oldest",
          "u9" in thumb_svc._thumb_uris and "u0" not in thumb_svc._thumb_uris)
finally:
    media_preview_mod._THUMB_CACHE_BYTES = saved_thumb_budget

# 7e. per-tab in-memory bounds (history / status lines / DOM) ----------------
from stanza_im.ui.chat_widget import ChatWidget, _STATUS_MAX
from stanza_im.ui import chat_widget as chat_widget_mod

tab = ChatWidget("bounds@example.com", "Bounds", ChatThemeFactory())
for i in range(_STATUS_MAX + 50):
    tab.add_status("s%d" % i, "12:00:00")
check("status lines bounded", len(tab._status_lines) == _STATUS_MAX)

tab._window_size = 50
hist_cap = max(chat_widget_mod._HISTORY_MAX, 50 * 10)
tab._messages = [
    {"sender": "A", "body": "m%d" % i, "direction": "incoming",
     "timestamp": "2026-01-01T00:00:00", "id": i}
    for i in range(hist_cap + 200)]
tab._merge_live_history()
check("history window bounded", len(tab._history) <= hist_cap)
tab.detach()

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_cv_src = open(os.path.join(_root, "stanza_im", "ui", "chat_view.py"),
               encoding="utf-8").read()
check("DOM message cap present",
      "_MAX_DOM_MESSAGES" in _cv_src and "removeChild" in _cv_src)

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

# 10a. Devices tab self-test controls ----------------------------------------
check("devices mic test control present",
      getattr(dlg, "_mic_test_button", None) is not None
      and getattr(dlg, "_mic_level", None) is not None)
check("devices speaker/camera test controls present",
      getattr(dlg, "_speaker_test_button", None) is not None
      and getattr(dlg, "_camera_test_button", None) is not None)
check("device tests enabled without a call", not dlg._call_active()
      and dlg._mic_test_button.isEnabled())
dlg._stop_device_tests()

# 11. media click relay (Python side of the scroll-poll delivery) -------------
from urllib.parse import quote
from stanza_im.ui.chat_widget import ChatWidget

cw = ChatWidget("bob@example.com", "Bob", ChatThemeFactory())
events = []
cw.media_view_requested.connect(lambda u, k, fs: events.append((u, k, fs)))
target = "https://upload.example.com/get/a/photo.png"
cw._handle_media_view_uri("stanza:view:image/" + quote(target, safe=""))
check("media uri -> image viewer",
      events == [(target, "image", False)])
events.clear()
cw._on_media_open_requested(target, "video")
check("media context menu video", events == [(target, "video", False)])
events.clear()
cw._on_media_open_requested(target, "video_fs")
check("media context menu fullscreen", events == [(target, "video", True)])

# 12. navigation routing regression (WebEngine path; static check, the page
#     cannot be instantiated in this sandbox) --------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = open(os.path.join(_root, "stanza_im", "ui", "chat_view.py"),
            encoding="utf-8").read()
check("data: navigation allowed (setHtml page load)",
      'if scheme == "data"' not in _src)
check("reload retry guard present", "_LOAD_RETRY_LIMIT" in _src)

# 13. media viewer render + geometry ------------------------------------------
from stanza_im.ui.media_viewer import MediaViewer

_mv_src = open(os.path.join(_root, "stanza_im", "ui", "media_viewer.py"),
               encoding="utf-8").read()
check("viewer defers initial image fit",
      "def showEvent" in _mv_src
      and "QtCore.QTimer.singleShot(0, self._fit_image)" in _mv_src)


class _StubService:
    def ensure_original_async(self, url, on_ready, on_error=None):
        return


check("media_viewer config default", cfg.media_viewer.width == 900
      and cfg.media_viewer.height == 680)
geo_cfg = {"width": 700, "height": 500, "x": 50, "y": 40, "maximized": False}
v1 = MediaViewer("https://h/p/photo.png", "image", _StubService(),
                 geometry_cfg=geo_cfg)
v1.resize(700, 500)
v1.move(50, 40)
v1.save_geometry()
check("viewer geometry saved",
      geo_cfg["width"] == 700 and geo_cfg["height"] == 500
      and abs(geo_cfg["x"] - 50) <= 4 and abs(geo_cfg["y"] - 40) <= 4)

v2 = MediaViewer("https://h/p/photo.png", "image", _StubService(),
                 geometry_cfg=dict(geo_cfg))
g = v2.geometry()
check("viewer geometry restored",
      g.width() == 700 and g.height() == 500
      and abs(g.x() - 50) <= 4 and abs(g.y() - 40) <= 4)

closed = []
v3 = MediaViewer("https://h/p/photo.png", "image", _StubService(),
                 geometry_cfg=dict(geo_cfg))
v3.closed.connect(lambda: closed.append(True))
v3.close()
check("viewer closed signal", closed == [True])

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
