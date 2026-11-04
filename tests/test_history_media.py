"""Offscreen tests for the History Manager media calendar."""
import asyncio
import os
import sys
import tempfile
import time

_SCRATCH = tempfile.mkdtemp(prefix="stanza_history_media_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets, QtTest  # noqa: E402

from stanza_im.core import history  # noqa: E402
from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.include.media import media_items_from_entry  # noqa: E402
from stanza_im.ui.history_manager import HistoryManagerDialog  # noqa: E402
from stanza_im.ui.history_media import HistoryMediaView, MediaCard  # noqa: E402

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
check("media is grouped under a standalone month header",
      any(label.text().startswith("2026 ")
          for label in view.findChildren(QtWidgets.QLabel)))
_before = len(view._items)
view.append_items([dict(items[0], origin_id="another-id")])
check("same media with a different id is not duplicated",
      len(view._items) == _before)
view.set_items(items)
check("month headers carry a horizontal separator",
      any(frame.frameShape() == QtWidgets.QFrame.Shape.HLine
          for frame in view.findChildren(QtWidgets.QFrame)))
_russian = QtCore.QLocale(QtCore.QLocale.Language.Russian)
_saved_locale = QtCore.QLocale()
QtCore.QLocale.setDefault(_russian)
try:
    check("the month is in the standalone form",
          HistoryMediaView._month_label("2026-10") == "2026 октябрь")
finally:
    QtCore.QLocale.setDefault(_saved_locale)
def settle_filter() -> None:
    deadline = time.time() + 1
    while view._filter_timer.isActive() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    view._apply_filter()


view.set_filter("photo")
settle_filter()
check("the filename filter is live",
      len(view._visible()) == 1)
view.set_filter("missing")
settle_filter()
check("a missing filter result is empty", view._visible() == [])
view.set_filter("")
settle_filter()
_extra = dict(items[0])
_extra["url"] = "https://files.example/photo2.jpg"
_extra["name"] = "photo2.jpg"
view.set_items([items[0], _extra])
view.resize(600, 420)
view.show()
app.processEvents()
_cards = view.findChildren(MediaCard)
check("both images are rendered", len(_cards) == 2)
check("media cards are flush with the left edge",
      min(card.geometry().x() for card in _cards) <= 10)
check("the media tooltip uses the interface timestamp format",
      any("2026-" in card.toolTip() and "T" not in card.toolTip()
          and ":" in card.toolTip() for card in _cards))
_seen = []
view.open_requested.connect(lambda url, kind: _seen.append((url, kind)))
if _cards:
    QtTest.QTest.mouseClick(
        _cards[0], QtCore.Qt.MouseButton.LeftButton)
    app.processEvents()
check("clicking a media card emits the open request",
      _seen == [("https://files.example/photo.jpg", "image")])
# Resizing must not leave old cards behind.
view.resize(360, 420)
_deadline = __import__("time").time() + 1
while __import__("time").time() < _deadline:
    app.processEvents()
    __import__("time").sleep(0.02)
check("resize reflows the grid without stale cards",
      len(view.findChildren(MediaCard)) == 2)

catalog = [{"jid": JID, "name": "Bob", "groups": ["G"],
            "is_conference": False}]
dialog = HistoryManagerDialog(lambda: catalog)
check("media all-time is on by default",
      dialog._media_mode["all_time"]
      and dialog._media_buttons["image"]["all_time"].isChecked())
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
dialog._on_media_mode_toggled("all_time", False)
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.15))
check("turning all-time off shows the selected-day context",
      not dialog._media_views["image"]._context.isHidden()
      and dialog._media_views["image"]._context.text())
check("the photo tab highlights dates with photos",
      "2026-03-12" in dialog._media_calendar_dates)
dialog._tabs.setCurrentIndex(2)
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.1))
check("the video tab highlights dates with videos",
      "2026-04-02" in dialog._media_calendar_dates)
dialog._tabs.setCurrentIndex(1)
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.1))

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

# Sparse archive pages (1 media per 100 messages) must auto-fill the grid
# until it becomes scrollable; otherwise only the newest image is visible.
auto_pages = []
EMPTY = "empty@example.com"


async def auto_server_media(jid, before=""):
    auto_pages.append(before)
    if len(auto_pages) <= 3:
        return [{"direction": "incoming", "sender": "bob",
                 "timestamp": "2026-05-01T10:00:00Z",
                 "body": "sparse photo", "media": {
                     "url": "https://files.example/sparse%d.png" % len(auto_pages),
                     "name": "sparse%d.png" % len(auto_pages),
                     "media_type": "image/png"}}], False, "c%d" % len(auto_pages)
    return [], True, ""


dialog4 = HistoryManagerDialog(
    lambda: [{"jid": EMPTY, "name": "Empty", "groups": ["G"],
              "is_conference": False}],
    server_media=auto_server_media,
    server_media_supported=lambda _jid: True)
dialog4.resize(900, 620)
dialog4.show()
dialog4._tabs.setCurrentIndex(1)


async def auto_load():
    await dialog4._select_jid_async(EMPTY, "Empty")
    await asyncio.sleep(0.1)
    dialog4._on_media_mode_toggled("server", True)
    for _ in range(20):
        app.processEvents()
        await asyncio.sleep(0.05)


asyncio.get_event_loop().run_until_complete(auto_load())
check("sparse server pages auto-fill until scrollable",
      len(auto_pages) > 1
      and len(dialog4._media_views["image"]._items) > 1)

# Switching contacts on a media tab must reload that contact's catalog even
# when both contacts share the newest date.
history.store_message(
    "carol@example.com", "incoming", "carol photo",
    timestamp="2026-11-03T10:00:00", sender="carol", origin_id="cp1",
    media={"url": "https://files.example/carol.jpg", "name": "carol.jpg",
           "media_type": "image/jpeg"})
catalog2 = [{"jid": JID, "name": "Bob", "groups": ["G"],
             "is_conference": False},
            {"jid": "carol@example.com", "name": "Carol", "groups": ["G"],
             "is_conference": False}]
dialog3 = HistoryManagerDialog(lambda: catalog2)
dialog3._tabs.setCurrentIndex(1)


async def switch_contacts():
    await dialog3._select_jid_async(JID, "Bob")
    await asyncio.sleep(0.1)
    await dialog3._select_jid_async("carol@example.com", "Carol")
    await asyncio.sleep(0.1)


asyncio.get_event_loop().run_until_complete(switch_contacts())
check("switching contacts refreshes the photo tab",
      [item["name"] for item in dialog3._media_views["image"]._items]
      == ["carol.jpg"])

# Context-menu "go to message" selects the Text tab/contact/day and highlights
# the matching entry.
photo_item = items[0]


async def jump_to_text():
    await dialog._jump_to_media_message_async(photo_item)


asyncio.get_event_loop().run_until_complete(jump_to_text())
check("go-to-message switches to the Text tab",
      dialog._tabs.currentIndex() == 0)
check("go-to-message opens the media date", dialog._date == "2026-03-12")
check("go-to-message highlights the target entry",
      dialog._messages.textCursor().hasSelection()
      and "photo" in dialog._messages.textCursor().selectedText())

# A persisted continuous marker makes the next server run start below it and
# signing off a page advances the low bound.
marker_jid = "marker@example.com"
history.save_mam_sync(
    marker_jid, low_archive_id="low1", low_ts="2026-01-01T00:00:00Z",
    high_archive_id="high1", high_ts="2099-01-01T00:00:00Z",
    complete_down=False)
marker = history.load_mam_sync(marker_jid)
check("continuous MAM marker round-trips",
      marker.get("low_archive_id") == "low1"
      and marker.get("high_ts") == "2099-01-01T00:00:00Z")
marker_pages = []


async def marker_server(jid, before=""):
    marker_pages.append((jid, before))
    return [], True, ""


marker_dialog = HistoryManagerDialog(
    lambda: [{"jid": marker_jid, "name": "Marker", "groups": ["G"],
              "is_conference": False}],
    server_media=marker_server, server_media_supported=lambda _jid: True)
marker_dialog._tabs.setCurrentIndex(1)


async def marker_run():
    await marker_dialog._select_jid_async(marker_jid, "Marker")
    await asyncio.sleep(0.1)
    marker_dialog._on_media_mode_toggled("server", True)
    await asyncio.sleep(0.1)


asyncio.get_event_loop().run_until_complete(marker_run())
check("server paging starts at the stored low cursor",
      marker_pages and marker_pages[0][1] == "low1")

# A newer local message above the marker's high opens a gap; the forward sync
# closes it before older server pages are requested.
gap_jid = "gap@example.com"
history.store_message(gap_jid, "incoming", "new", sender="bob",
                      timestamp="2026-06-01T10:00:00Z", origin_id="g1")
history.save_mam_sync(
    gap_jid, low_archive_id="", low_ts="",
    high_archive_id="", high_ts="2026-01-01T00:00:00Z",
    complete_down=False)
gap_calls = []


async def gap_sync(jid, high_ts, high_id=""):
    gap_calls.append((jid, high_ts))
    return 1, "2026-06-01T10:00:00Z", "g1", True


async def gap_server(jid, before=""):
    return [], True, ""


gap_dialog = HistoryManagerDialog(
    lambda: [{"jid": gap_jid, "name": "Gap", "groups": ["G"],
              "is_conference": False}],
    server_media=gap_server, server_media_supported=lambda _jid: True,
    server_gap_sync=gap_sync)
gap_dialog._tabs.setCurrentIndex(1)


async def gap_run():
    await gap_dialog._select_jid_async(gap_jid, "Gap")
    await asyncio.sleep(0.1)
    gap_dialog._on_media_mode_toggled("server", True)
    await asyncio.sleep(0.1)


asyncio.get_event_loop().run_until_complete(gap_run())
check("a gap above the marker is closed before older paging",
      gap_calls and gap_calls[0][1] == "2026-01-01T00:00:00Z")

if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll history-media tests passed.")
