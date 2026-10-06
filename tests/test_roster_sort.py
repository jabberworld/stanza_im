"""Offscreen tests for the roster sort / group-display options.

Covers «Сортировать по непрочитанным» and «Показывать группы».

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_roster_sort.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_rostersort_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.ui.roster_style import UserItem  # noqa: E402
from stanza_im.ui.roster_widget import RosterWidget  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def order(widget):
    return [item.name for kind, item in widget._visible_items()
            if kind == "user"]


def make():
    w = RosterWidget()
    w.add_user(UserItem(jid="a@x", name="Alice", group="Friends",
                        status="online", unread_count=0))
    w.add_user(UserItem(jid="b@x", name="Bob", group="Friends",
                        status="online", unread_count=3))
    w.add_user(UserItem(jid="c@x", name="Carol", group="Friends",
                        status="away", unread_count=1))
    w.sort_and_update()
    return w


# 1. unread contacts come first -----------------------------------------------
w = make()
check("unread contacts sort before read ones", order(w) == ["Bob", "Carol",
                                                            "Alice"])
w.set_sort_by_unread(False)
check("disabling the unread sort restores the presence order",
      order(w) == ["Alice", "Bob", "Carol"])

# With the presence sort off, the unread priority still leads the alphabet.
w = make()
w.set_sort_by_status(False)
check("unread leads an alphabetical list too",
      order(w) == ["Bob", "Carol", "Alice"])
w.set_sort_by_unread(False)
check("plain alphabetical order without the unread sort",
      order(w) == ["Alice", "Bob", "Carol"])

# 2. flat list when groups are hidden -----------------------------------------
w = RosterWidget()
w.set_trailing_groups({"Conferences", "Personal"})
w.add_user(UserItem(jid="a@x", name="Alice", group="Friends", status="online"))
w.add_user(UserItem(jid="b@x", name="Bob", group="Work", status="online"))
# The same contact in two groups must produce a single flat row.
w.add_user(UserItem(jid="a@x", name="Alice", group="Work", status="online"))
w.add_user(UserItem(jid="room@conf", name="Room", group="Conferences",
                    status="online"))
w.add_user(UserItem(jid="c@x", name="Carol", group="Personal",
                    status="online"))
w.sort_and_update()
grouped_headers = [item.name for kind, item in w._visible_items()
                   if kind == "group"]
check("grouped mode shows the real and virtual headers",
      grouped_headers == ["Friends", "Work", "Conferences", "Personal"])
w.set_show_groups(False)
items = w._visible_items()
users = [item.name for kind, item in items if kind == "user"]
headers = [item.name for kind, item in items if kind == "group"]
check("flat mode lists each real contact once",
      users.count("Alice") == 1 and users.count("Bob") == 1)
check("flat mode drops the real group headers",
      "Friends" not in headers and "Work" not in headers)
check("flat mode keeps the virtual groups",
      headers == ["Conferences", "Personal"])
check("flat mode keeps the virtual group rows",
      "Room" in users and "Carol" in users)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All roster-sort tests passed.")
