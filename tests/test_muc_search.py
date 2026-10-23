"""Live search in the MUC participant sidebar.

The sidebar carries a search field above the list: typing filters the rows by
nick (case/width-insensitive), hides sections without a match and reports the
matched/total count per section. The field itself is hidden for 1:1 tabs.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_search.py
"""
import inspect
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_mucsearch_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load, tr
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

cw = ChatWidget("room@conf.example/me", "Room",
                chat_themes.ChatThemeFactory(), is_muc=True)


def user(nick, role="participant", affiliation="member"):
    return {"nick": nick, "show": "online", "role": role,
            "affiliation": affiliation}


cw.update_muc_users([
    user("Alice"), user("Bob"), user("Bobby"), user("Carol", "moderator"),
    user("Dave", "visitor"),
])

check("the MUC sidebar carries a search field",
      cw._participant_search.isVisibleTo(cw))
check("the search field carries the localized placeholder",
      cw._participant_search.placeholderText()
      == tr("muc_search_placeholder"))


def visible(nick):
    state = cw._muc_rows[nick]
    return not state["item"].isHidden() and state["row"].isVisibleTo(cw)


def header(section):
    return cw._muc_headers[section].text()


check("all participants are visible without a filter",
      all(visible(n) for n in ("Alice", "Bob", "Bobby", "Carol", "Dave")))
check("the sections report their full counts",
      header("moderators") == f"{tr('muc_section_moderators')} (1)"
      and header("participants") == f"{tr('muc_section_participants')} (3)"
      and header("guests") == f"{tr('muc_section_guests')} (1)")

cw.set_participant_filter("bo")
check("a filter hides non-matching nicknames",
      visible("Bob") and visible("Bobby")
      and not visible("Alice") and not visible("Carol") and not visible("Dave"))
check("a section count reports matched/total",
      header("participants") == f"{tr('muc_section_participants')} (2/3)")
check("a section without a match is hidden", cw._muc_headers["guests"].isHidden())

cw.set_participant_filter("  CAROL ")
check("the filter ignores case and surrounding spaces",
      visible("Carol") and not visible("Bob")
      and header("moderators") == f"{tr('muc_section_moderators')} (1/1)")

cw.set_participant_filter("")
check("clearing the filter restores every row and count",
      all(visible(n) for n in ("Alice", "Bob", "Bobby", "Carol", "Dave"))
      and header("participants") == f"{tr('muc_section_participants')} (3)"
      and not cw._muc_headers["guests"].isHidden())

# A presence arriving while the filter is active respects it.
cw.set_participant_filter("ali")
cw.update_muc_users([user("Alice"), user("Bob"), user("Bobby"),
                     user("Carol", "moderator"), user("Dave", "visitor"),
                     user("Alicia")])
check("a new matching participant appears, others stay hidden",
      visible("Alice") and visible("Alicia") and not visible("Bob"))

pm = ChatWidget("alice@example.com", "Alice", chat_themes.ChatThemeFactory())
check("a 1:1 tab hides the MUC search field",
      not pm._participant_search.isVisibleTo(pm))

src = inspect.getsource(ChatWidget._on_splitter_moved)
check("the splitter remembers the whole sidebar width",
      "self._users_panel.width()" in src)

cw.detach()
pm.detach()

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All MUC participant-search tests passed.")
