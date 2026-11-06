"""Local-day history grouping and display (UTC storage → local UI).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_history_timezone.py
"""
import asyncio
import os
import sys
import tempfile
import time

os.environ["TZ"] = "Europe/Kyiv"
try:
    time.tzset()
except AttributeError:
    pass

_SCRATCH = tempfile.mkdtemp(prefix="stanza_history_tz_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.core import history  # noqa: E402
from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.include.utils import format_local_datetime, local_date  # noqa: E402
from stanza_im.ui.history_manager import (  # noqa: E402
    HistoryManagerDialog, _stamp, _time_of)
from stanza_im.ui.history_media import HistoryMediaView  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])
JID = "timezone@example.com"

# 22:30 UTC is 00:30 the next local day in Europe/Kyiv (+2 after DST).
history.store_message(
    JID, "incoming", "late message", timestamp="2026-10-29T22:30:00Z",
    sender="Bob", origin_id="tz-1", media={
        "url": "https://files.example/with_media.jpg",
        "media_type": "image/jpeg", "name": "with_media.jpg"})
# 21:30 UTC is still 23:30 the same local day.
history.store_message(
    JID, "incoming", "early message", timestamp="2026-10-29T21:30:00Z",
    sender="Bob", origin_id="tz-2")

check("local timestamp formatting crosses the day boundary",
      format_local_datetime("2026-10-29T22:30:00Z")
      == "2026-10-30 00:30:00")
check("local date helper crosses the day boundary",
      local_date("2026-10-29T22:30:00Z") == "2026-10-30")
check("text history time is local", _time_of("2026-10-29T22:30:00Z")
      == "00:30:00")
check("text history stamp is local",
      _stamp("2026-10-29T22:30:00Z") == "2026-10-30 00:30:00")

check("date list is grouped by local day",
      history.dates(JID) == ["2026-10-29", "2026-10-30"])
check("the late message belongs to the local next day",
      len(history.load_day(JID, "2026-10-30")) == 1
      and history.load_day(JID, "2026-10-30")[0]["body"] == "late message")
check("the early message stays on the local previous day",
      len(history.load_day(JID, "2026-10-29")) == 1
      and history.load_day(JID, "2026-10-29")[0]["body"] == "early message")
check("search groups matches by local day",
      history.search_dates(JID, "message")
      == [("2026-10-30", 1), ("2026-10-29", 1)])
check("media day filtering uses the local day",
      len(history.media_entries(JID, "2026-10-30")) == 1
      and history.media_entries(JID, "2026-10-29") == [])
check("media calendar dates are local",
      history.media_dates(JID) == ["2026-10-30"])

# Legacy rows without a timezone suffix are local wall-clock values; they must
# not be shifted as if they were UTC.
legacy_jid = "legacy@example.com"
history.store_message(
    legacy_jid, "incoming", "legacy local", timestamp="2026-10-29T23:30:00",
    sender="Bob", origin_id="legacy-1")
check("legacy naive timestamps keep their local day",
      history.dates(legacy_jid) == ["2026-10-29"]
      and len(history.load_day(legacy_jid, "2026-10-29")) == 1)
check("legacy naive timestamps still render their time",
      _stamp("2026-10-29T23:30:00") == "2026-10-29 23:30:00"
      and _time_of("2026-10-29T23:30:00") == "23:30:00")

# The text renderer must use the same local timestamp.
dialog = HistoryManagerDialog(
    lambda: [{"jid": JID, "name": "Bob", "groups": ["G"],
              "is_conference": False}])
dialog._entries = history.load_day(JID, "2026-10-30")
dialog._render_messages()
text = dialog._messages.toPlainText()
check("rendered history shows the local date and time",
      "2026-10-30 00:30:00" in text and "late message" in text)

# A media item on the UTC previous date must land in the local month group.
view = HistoryMediaView("image")
view.set_items([{
    "url": "https://files.example/month.jpg", "kind": "image",
    "name": "month.jpg", "timestamp": "2026-10-31T23:30:00Z",
    "jid": JID, "media_type": "image/jpeg",
}])
check("media month grouping is local",
      any(label.text() == "2026 November"
          for label in view.findChildren(QtWidgets.QLabel)))

dialog.close()
print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All history timezone tests passed.")
