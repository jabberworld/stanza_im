"""Offscreen tests for the History Manager XEP-0431 mode."""
import asyncio
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_server_ui_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.include.constants import find_icon  # noqa: E402
from stanza_im.ui.history_manager import HistoryManagerDialog  # noqa: E402
from stanza_im.ui.main_window import MainWindow  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
JID = "bob@example.com"
ROOM = "room@conference.example"
calls = []


def row(ref, body, stamp):
    return {
        "direction": "incoming", "body": body, "timestamp": stamp,
        "sender": JID, "archive_id": ref, "stanza_id": ref,
        "origin_id": ref, "reply_to": "", "reply_id": "",
        "retracted": False, "retract_reason": "", "retract_by": "",
        "replace_id": "", "markup": None, "media": None,
        "encrypted": False, "encryption": "",
    }


async def search(jid, query, after=""):
    calls.append((jid, query, after))
    if after:
        return [row("a2", "second", "2026-11-02T10:00:00.000000Z")], True, ""
    return [row("a1", "first", "2026-11-01T10:00:00.000000Z")], False, "a1"


dialog = HistoryManagerDialog(
    lambda: [], server_search=search, server_supported=lambda _jid: True)
check("the globe icon exists", bool(find_icon("globe.svg")))
for _button in (dialog._btn_all_time, dialog._btn_all_contacts,
                dialog._btn_server):
    check("a mode button is icon-only",
          _button.text() == "" and not _button.icon().isNull())
check("mode buttons keep their tooltips",
      dialog._btn_all_time.toolTip() == "All time"
      and dialog._btn_all_contacts.toolTip()
      and dialog._btn_server.toolTip())
dialog._jid = JID
dialog._name = "Bob"
dialog._update_server_button()
dialog._search.setText("hello")
dialog._btn_server.setChecked(True)
check("the server toggle is enabled for a supported chat",
      dialog._btn_server.isEnabled() and dialog._btn_server.isChecked())
asyncio.get_event_loop().run_until_complete(dialog._run_server_search_async())
check("the first server page is requested without an RSM cursor",
      calls == [(JID, "hello", "")])
check("the first page is displayed and stored in the calendar model",
      dialog._all_days == ["2026-11-01"] and dialog._server_days
      == {"2026-11-01": 1} and dialog._results.count() == 1)
check("an incomplete page shows Load more",
      not dialog._btn_server_more.isHidden())
asyncio.get_event_loop().run_until_complete(
    dialog._run_server_search_async(more=True))
check("Load more sends the previous RSM cursor",
      calls[-1] == (JID, "hello", "a1"))
check("the next page is appended and Complete hides Load more",
      dialog._server_days == {"2026-11-01": 1, "2026-11-02": 1}
      and dialog._btn_server_more.isHidden())
dialog.deleteLater()

dialog2 = HistoryManagerDialog(
    lambda: [], server_search=search, server_supported=lambda _jid: False)
dialog2._jid = JID
dialog2._update_server_button()
check("an unsupported chat disables the server toggle",
      not dialog2._btn_server.isEnabled())
dialog2.deleteLater()


class _ServerClient:
    def supports_mam_fulltext(self, jid, is_muc=False):
        return is_muc and jid == ROOM

    def supports_mam_archive(self, jid, is_muc=False):
        return is_muc and jid == ROOM


class _ServerWindow:
    _client = _ServerClient()
    _conference_roster = set()
    _muc_self_nicks = {ROOM}

    @staticmethod
    def _is_conference_jid(jid):
        return jid == ROOM

    def _history_server_archive_jid(self, jid):
        return jid, True, jid in self._muc_self_nicks


win = _ServerWindow()
check("a joined room enables server history search",
      MainWindow._history_server_supported(win, ROOM))
win._muc_self_nicks = set()
check("an unjoined room disables server history search",
      not MainWindow._history_server_supported(win, ROOM))
check("an unjoined room disables server media search",
      not MainWindow._history_server_media_supported(win, ROOM))
win._muc_self_nicks = {ROOM}
check("a joined room enables server media search",
      MainWindow._history_server_media_supported(win, ROOM))

if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll history server-UI tests passed.")
