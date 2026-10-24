"""The Help -> Cache dialog and the per-cache cleanup APIs.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_cache_dialog.py
"""
import inspect
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_cache_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.core import discovery, history, roster_cache, vcard_cache
from stanza_im.i18n import load as i18n_load
from stanza_im.include import avatars as avatars_mod
from stanza_im.include import geo, media
from stanza_im.ui.cache_dialog import CacheDialog, CacheEntry, dir_size, file_size
from stanza_im.ui.main_window import MainWindow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


# ── the dialog: sizes, total, per-row clearing -----------------------------
work = tempfile.mkdtemp(prefix="cacherow_")
alpha = os.path.join(work, "alpha")
os.makedirs(alpha)
with open(os.path.join(alpha, "a.bin"), "wb") as fh:
    fh.write(b"x" * 2048)
beta = os.path.join(work, "beta.json")
with open(beta, "wb") as fh:
    fh.write(b"y" * 1024)

cleared = []


def clear_alpha():
    cleared.append("alpha")
    for name in os.listdir(alpha):
        os.remove(os.path.join(alpha, name))


def clear_beta():
    cleared.append("beta")
    os.remove(beta)


long_hint = "a verbose hint that would wrap the row " * 8
entries = [
    CacheEntry("alpha", "Alpha", "the alpha cache", "Clear alpha?",
               lambda: dir_size(alpha), clear_alpha),
    CacheEntry("beta", "Beta", long_hint, "Clear beta?",
               lambda: file_size(beta), clear_beta),
    CacheEntry("none", "None", "not there", "Clear none?",
               lambda: None, lambda: cleared.append("none")),
]
dialog = CacheDialog(entries)
check("the dialog measures every cache",
      dialog.sizes["alpha"] == 2048 and dialog.sizes["beta"] == 1024)
check("an unavailable size is reported as such", dialog.sizes["none"] is None)
check("the total sums the known sizes", dialog.total_size == 3072)
check("the table has one row per cache",
      dialog._table.rowCount() == 3
      and dialog._table.item(0, 0).text() == "Alpha")
check("each row carries a clear button", len(dialog._buttons) == 3)
check("the table keeps its four columns", dialog._table.columnCount() == 4)
check("the hint column elides instead of wrapping",
      dialog._table.wordWrap() is False
      and dialog._table.textElideMode() == QtCore.Qt.TextElideMode.ElideRight)
check("clear buttons are flat icon buttons in the OMEMO style",
      all(isinstance(button, QtWidgets.QToolButton)
          and button.autoRaise() and not button.icon().isNull()
          for button in dialog._buttons.values()))
check("the full hint stays in the tooltip",
      dialog._table.item(1, 1).toolTip() == long_hint)
dialog.show()
app.processEvents()
check("rows stay compact with a long hint even on first display",
      all(dialog._table.rowHeight(row) <= 34
          for row in range(dialog._table.rowCount())))

# A declined confirmation clears nothing.
_orig_question = QtWidgets.QMessageBox.question
QtWidgets.QMessageBox.question = staticmethod(
    lambda *a, **k: QtWidgets.QMessageBox.StandardButton.No)
check("a declined clear does nothing",
      dialog.clear_entry(entries[0]) is False and cleared == [])

QtWidgets.QMessageBox.question = staticmethod(
    lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
check("an accepted clear calls the callback",
      dialog.clear_entry(entries[0]) is True and cleared == ["alpha"])
check("the size is re-measured after clearing", dialog.sizes["alpha"] == 0)
check("the total follows", dialog.total_size == 1024)
dialog.close()
QtWidgets.QMessageBox.question = _orig_question

# ── the cache APIs ─────────────────────────────────────────────────────────
media_dir = os.path.join(work, "media")
mc = media.MediaCache(media_dir)
mc.store("https://example.com/a.png", original_bytes=b"z" * 512,
         mime="image/png", kind="image")
check("the media cache reports its size", mc.total_bytes() > 0)
mc.clear()
check("the media cache is emptied",
      mc.total_bytes() == 0 and dir_size(media_dir) == 0)

tile_dir = os.path.join(work, "tiles")
tc = geo.TileCache(tile_dir)
tc.put(3, 4, 5, b"png")
check("the tile cache reports its size", tc.total_bytes() > 0)
tc.clear()
check("the tile cache is emptied", tc.total_bytes() == 0)

vcard_file = os.path.join(work, "vcard-cache.json")
vc = vcard_cache.VCardCache(vcard_file)
vc.put("bob@example.com", {"fn": "Bob"})
check("the vCard cache writes its file", os.path.isfile(vcard_file))
vc.clear()
check("the vCard cache is emptied",
      not os.path.isfile(vcard_file) and vc.get("bob@example.com") is None)

disc_file = os.path.join(work, "discovery.json")
dc = discovery.DiscoveryCache(disc_file)
dc.put("key", {"host": "proxy"})
check("the discovery cache writes its file", os.path.isfile(disc_file))
dc.clear()
check("the discovery cache is emptied",
      not os.path.isfile(disc_file) and dc.get("key")[0] is False)

avatars_dir = os.path.join(work, "avatars")
os.makedirs(avatars_dir)
_orig_avatars_dir = avatars_mod.AVATARS_DIR
avatars_mod.AVATARS_DIR = avatars_dir
_forget = avatars_mod._URI_CACHE
avatars_mod._URI_CACHE = {}
open(os.path.join(avatars_dir, "bob@example.com.png"), "wb").write(b"a")
open(os.path.join(avatars_dir, avatars_mod.PLACEHOLDER_FILENAME), "wb").write(b"p")
check("the avatar cache is cleared, the placeholder stays",
      avatars_mod.clear_cache() == 1
      and os.path.isfile(os.path.join(
          avatars_dir, avatars_mod.PLACEHOLDER_FILENAME))
      and not os.path.isfile(os.path.join(avatars_dir, "bob@example.com.png")))
avatars_mod.AVATARS_DIR = _orig_avatars_dir
avatars_mod._URI_CACHE = _forget

history_dir = os.path.join(work, "history")
os.makedirs(history_dir)
for name in ("a.sqlite3", "a.sqlite3-wal", "a.sqlite3-shm", "a.jsonl",
             "keep.txt"):
    open(os.path.join(history_dir, name), "wb").write(b"h")
_orig_history_dir = history.HISTORY_DIR
history.HISTORY_DIR = history_dir
history.clear_all()
check("the history wipe removes only history files",
      not os.path.exists(os.path.join(history_dir, "a.sqlite3"))
      and not os.path.exists(os.path.join(history_dir, "a.jsonl"))
      and os.path.exists(os.path.join(history_dir, "keep.txt")))
history.HISTORY_DIR = _orig_history_dir

roster_dir = os.path.join(work, "roster")
os.makedirs(roster_dir)
open(os.path.join(roster_dir, "me@example.com.json"), "w").write("{}")
open(os.path.join(roster_dir, "keep.txt"), "w").write("x")
_orig_roster_data = roster_cache.DATA_DIR
roster_cache.DATA_DIR = os.path.dirname(roster_dir)
check("the roster cache is cleared",
      roster_cache.clear() == 1
      and not os.path.exists(os.path.join(roster_dir, "me@example.com.json"))
      and os.path.exists(os.path.join(roster_dir, "keep.txt")))
roster_cache.DATA_DIR = _orig_roster_data

# ── the Help menu wiring and the history reset -----------------------------
menu_src = inspect.getsource(MainWindow._on_cache_info) + inspect.getsource(
    MainWindow._cache_entries)
check("the Help menu opens the cache dialog",
      "menu_cache_info" in inspect.getsource(MainWindow._build_menu)
      and "CacheDialog" in inspect.getsource(MainWindow._on_cache_info))
check("the Help entries use distinct icons",
      all(icon in inspect.getsource(MainWindow._build_menu)
          for icon in ("connected.svg", "shield.svg", "server.svg",
                       "cache.svg")))
check("the cache dialog lists all caches",
      all(key in inspect.getsource(MainWindow._cache_entries)
          for key in ("media", "avatars", "tiles", "vcard", "discovery",
                      "roster", "webengine", "history")))
history_clear = inspect.getsource(MainWindow._clear_history_all)
check("clearing the history resets the read state",
      "self._unread_chats = {}" in history_clear
      and "history_mod.clear_all()" in history_clear
      and "chat.reset_history()" in history_clear)
check("clearing the roster cache keeps it absent until the next login",
      "_roster_cache_cleared = True"
      in inspect.getsource(MainWindow._clear_roster_cache))
from stanza_im.core.client import JabberClient  # noqa: E402
check("the client never rewrites a cleared roster cache",
      "_roster_cache_cleared" in inspect.getsource(
          JabberClient._save_roster_cache))
check("clearing avatars resets the known avatar hashes",
      "_avatar_ids" in inspect.getsource(MainWindow._clear_avatar_cache))

# A MainWindow (without a full UI) builds the real row list.
win = MainWindow.__new__(MainWindow)
win._media_cache = media.MediaCache(os.path.join(work, "media2"))
win._tile_cache = None
rows = {entry.key: entry for entry in win._cache_entries()}
check("MainWindow exposes every cache row",
      list(rows) == ["media", "avatars", "tiles", "vcard", "discovery",
                     "roster", "webengine", "history"])
check("the MainWindow size probes run",
      all(entry.size() is not None for entry in rows.values()))
check("the web engine cache path is known without importing Chromium",
      "PyQt6.QtWebEngineCore" not in sys.modules)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All cache-dialog tests passed.")
