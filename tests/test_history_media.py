"""Offscreen tests for the History Manager media calendar."""
import asyncio
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_history_media_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.core import history  # noqa: E402
from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.include.media import media_items_from_entry  # noqa: E402
from stanza_im.ui.history_manager import HistoryManagerDialog  # noqa: E402
from stanza_im.ui.history_media import HistoryMediaView  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
JID = "bob@example.com"

photo = {
    "url": "https://files.example/photo.jpg", "name": "photo.jpg",
    "media_type": "image/jpeg", "size": 1234,
}
video = {
    "url": "https://files.example/clip.mp4", "name": "clip.mp4",
    "media_type": "video/mp4",
}
audio = {
    "url": "aesgcm://files.example/song.ogg#key", "name": "song.ogg",
    "media_type": "audio/ogg",
}
entry = {"direction": "incoming", "sender": "bob",
         "timestamp": "2026-03-12T10:00:00Z",
         "body": "look https://files.example/photo.jpg and "
                 "aesgcm://files.example/song.ogg#key",
         "media": photo}
items = media_items_from_entry(entry, jid=JID)
check("SIMS photo and OMEMO aesgcm link are extracted",
      {item["kind"] for item in items} == {"image", "audio"})
check("the SIMS filename wins", any(item["name"] == "photo.jpg"
                                    for item in items))
check("the aesgcm URL is kept intact",
      any(item["url"].startswith("aesgcm://") for item in items))

history.store_message(
    JID, "incoming", "photo", timestamp="2026-03-12T10:00:00",
    sender="bob", origin_id="p1", media=photo)
history.store_message(
    JID, "incoming", "clip", timestamp="2026-04-02T10:00:00",
    sender="bob", origin_id="v1", media=video)
history.store_message(
    JID, "incoming", "song", timestamp="2026-04-03T10:00:00",
    sender="bob", origin_id="a1", media=audio)
check("media rows are read from SQLite",
      len(history.media_entries(JID)) == 3)

view = HistoryMediaView("image")
view.set_items(items)
check("the photo tab keeps only images",
      len(view._items) == 1 and view._items[0]["kind"] == "image")
check("media is grouped under a month header",
      any(label.text().startswith("---- 2026")
          for label in view.findChildren(QtWidgets.QLabel)))
view.set_filter("photo")
check("the filename filter is live",
      len(view._visible()) == 1)
view.set_filter("missing")
check("a missing filter result is empty", view._visible() == [])
view.set_filter("")

catalog = [{"jid": JID, "name": "Bob", "groups": ["G"],
            "is_conference": False}]
dialog = HistoryManagerDialog(lambda: catalog)
check("four history tabs are present", dialog._tabs.count() == 4)
check("the media tabs are photo/video/audio",
      [dialog._tabs.tabText(i) for i in range(1, 4)]
      == ["Photos", "Video", "Audio"])
check("media tabs duplicate the icon-only mode buttons",
      all(button.text() == "" and not button.icon().isNull()
          for kind in ("image", "video", "audio")
          for button in dialog._media_buttons[kind].values()))
dialog._tabs.setCurrentIndex(1)


async def load_contact():
    await dialog._select_jid_async(JID, "Bob")
    await asyncio.sleep(0.15)


asyncio.get_event_loop().run_until_complete(load_contact())
dialog._on_media_mode_toggled("all_time", True)
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.1))
check("the local photo tab is populated",
      [item["kind"] for item in dialog._media_views["image"]._items]
      == ["image"])
check("the video tab has its own catalog",
      [item["kind"] for item in dialog._media_views["video"]._items]
      == ["video"]
      and [item["kind"] for item in dialog._media_views["audio"]._items]
      == ["audio"])

# Server media pages use ordinary MAM rows and append older pages.
server_pages = []


async def server_media(jid, before=""):
    server_pages.append((jid, before))
    if not before:
        return [{"direction": "incoming", "sender": "bob",
                 "timestamp": "2026-05-01T10:00:00Z",
                 "body": "server photo", "media": {
                     "url": "https://files.example/server.png",
                     "name": "server.png", "media_type": "image/png"}}], \
            False, "cursor-1"
    return [], True, ""


dialog2 = HistoryManagerDialog(
    lambda: catalog, server_media=server_media,
    server_media_supported=lambda _jid: True)
dialog2._tabs.setCurrentIndex(1)


async def load_server():
    await dialog2._select_jid_async(JID, "Bob")
    await asyncio.sleep(0.1)
    dialog2._on_media_mode_toggled("server", True)
    await asyncio.sleep(0.2)


asyncio.get_event_loop().run_until_complete(load_server())
check("server media mode requests the first page without a cursor",
      server_pages and server_pages[0][1] == "")
check("server media rows reach the photo tab",
      any(item["name"] == "server.png"
          for item in dialog2._media_views["image"]._items))
check("a server page can request the next older page",
      not dialog2._media_server_complete)
dialog2._on_media_load_more("image")
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.15))
check("server media pagination stops at complete",
      dialog2._media_server_complete
      and server_pages[-1][1] == "cursor-1")

if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll history-media tests passed.")
