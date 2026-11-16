"""Offscreen tests for the batched roster load and known-contact upserts."""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_roster_batch_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core import known_contacts
from stanza_im.ui.roster_style import UserItem
from stanza_im.ui.roster_widget import RosterWidget

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
rw = RosterWidget()
recalcs = []
_recalc = rw._recalc_heights


def _counting_recalc():
    recalcs.append(1)
    _recalc()


rw._recalc_heights = _counting_recalc
rw.begin_batch()
for index in range(200):
    rw.add_user(UserItem(jid=f"user{index}@example.com",
                         name=f"user{index}", group="Users"))
rw.end_batch()
check("a bulk roster load recalculates once", len(recalcs) == 1)
check("a bulk roster load keeps every row", len(rw._users) == 200)
check("a bulk roster load keeps the group", list(rw._groups) == ["Users"])
rw.close()

known_contacts.DATA_DIR = tempfile.mkdtemp(prefix="stanza_known_")
saves = []
_save = known_contacts.save


def _counting_save(data):
    saves.append(len(data))
    _save(data)


known_contacts.save = _counting_save
known_contacts.update_many([
    ("a@example.com", "A", ["Friends"], False),
    ("b@example.com", "B", ["Friends"], False),
    ("c@example.com", "C", [], False),
])
check("update_many saves the registry once", saves == [3])
check("update_many keeps all contacts",
      set(known_contacts.all()) == {"a@example.com", "b@example.com",
                                    "c@example.com"})

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All roster-batch tests passed.")
