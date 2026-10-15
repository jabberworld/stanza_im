"""Offscreen tests for the ad-hoc command dialog (XEP-0050).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_adhoc.py
"""
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_adhoc_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as load_i18n
from stanza_im.i18n import tr
from stanza_im.ui.adhoc_dialog import AdhocDialog

load_i18n("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _FakeClient:
    def __init__(self):
        self.started = []

    async def get_commands_list(self, jid):
        return [{"name": "Ping", "node": "ping", "jid": jid},
                {"name": "Echo", "node": "echo", "jid": jid}]

    async def start_command(self, jid, node):
        self.started.append((jid, node))
        return {"session": "s1", "form": None, "actions": [],
                "status": "completed", "notes": []}

    async def continue_command(self, session, action, form=None):
        return {"session": session, "form": None, "actions": [],
                "status": "completed", "notes": []}


loop = asyncio.get_event_loop()
client = _FakeClient()
dlg = AdhocDialog(client, "svc@example")
loop.run_until_complete(asyncio.sleep(0.1))

check("the command list is built", dlg._commands_widget is not None
      and dlg._commands_widget.topLevelItemCount() == 2)
check("the dialog has an Execute button", dlg._run_btn is not None)
check("Execute starts disabled", not dlg._run_btn.isEnabled())

dlg._commands_widget.setCurrentItem(dlg._commands_widget.topLevelItem(0))
check("selecting a command enables Execute", dlg._run_btn.isEnabled())

dlg._run_selected()
loop.run_until_complete(asyncio.sleep(0.1))
check("Execute runs the selected command",
      client.started == [("svc@example", "ping")])
check("the command list is gone after execution", dlg._commands_widget is None)

dlg.close()


# ── a form step with no <actions/> still offers a submit button ──────────────
class _FormClient(_FakeClient):
    async def start_command(self, jid, node):
        return {"session": "s2",
                "form": {"title": "Register", "instructions": [],
                         "fields": []},
                "actions": [], "status": "executing", "notes": []}


dlg2 = AdhocDialog(_FormClient(), "gw@example")
loop.run_until_complete(asyncio.sleep(0.1))
dlg2._commands_widget.setCurrentItem(dlg2._commands_widget.topLevelItem(0))
dlg2._run_selected()
loop.run_until_complete(asyncio.sleep(0.1))
labels = [dlg2._buttons.itemAt(i).widget().text()
          for i in range(dlg2._buttons.count())
          if dlg2._buttons.itemAt(i).widget() is not None]
check("a form with no actions offers a Send button",
      tr("adhoc_submit") in labels)
dlg2.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All adhoc tests passed.")
