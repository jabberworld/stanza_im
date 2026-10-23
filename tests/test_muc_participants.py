"""Offscreen tests for the incremental MUC participant sidebar.

A large conference join used to rebuild every participant row on each presence
(O(n^2) widgets/pixmaps).  These tests pin the incremental behaviour: rows are
created once, updated in place, moved between sections and removed without
touching the others.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_participants.py
"""
import inspect
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_mucparts_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import load as i18n_load, tr
from stanza_im.ui import chat_themes
from stanza_im.ui import chat_widget as chat_widget_mod

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
cw = chat_widget_mod.ChatWidget(
    "room@conf.example/me", "Room", chat_themes.ChatThemeFactory(), is_muc=True)
lw = cw._users_list

# Count row constructions to prove that presences do not rebuild the list.
built: list[str] = []
_build = cw._build_muc_user_row


def _counting_build(user):
    built.append(str(user.get("nick", "")))
    return _build(user)


cw._build_muc_user_row = _counting_build


def _user(nick, **extra):
    user = {"nick": nick, "show": "online", "role": "participant",
            "affiliation": "member"}
    user.update(extra)
    return user


def _row(nick):
    return cw._muc_rows.get(nick)


def _items():
    return [lw.item(i) for i in range(lw.count())]


def _nicks():
    return [item.data(QtCore.Qt.ItemDataRole.UserRole)
            for item in _items()
            if item.data(QtCore.Qt.ItemDataRole.UserRole)]


def _headers():
    return [item.text() for item in _items()
            if item.data(QtCore.Qt.ItemDataRole.UserRole) is None]


# 1. a growing list creates each row exactly once ---------------------------
users = [_user("user%02d" % i) for i in range(60)]
for index in range(len(users)):
    cw.update_muc_users(users[:index + 1])
check("a presence list of 60 creates exactly 60 rows", len(built) == 60)
check("every participant is listed once", len(_nicks()) == 60)
row_before = _row("user10")["row"]
cw.update_muc_users([_user("user%02d" % i, show="away") for i in range(60)])
check("a status update reuses the existing rows",
      len(built) == 60 and _row("user10")["row"] is row_before)

# 2. sections, ordering and counts ------------------------------------------
cw.update_muc_users([
    _user("mod2", role="moderator"),
    _user("guest1", role="visitor"),
    _user("alpha"),
    _user("mod1", role="moderator", affiliation="owner"),
    _user("zeta"),
    _user("guest2", role="visitor"),
])
check("sections are ordered moderators -> participants -> guests",
      _nicks() == ["mod1", "mod2", "alpha", "zeta", "guest1", "guest2"])
check("section headers carry the counts",
      _headers() == [tr("muc_section_moderators") + " (2)",
                     tr("muc_section_participants") + " (2)",
                     tr("muc_section_guests") + " (2)"])

# 3. a role change moves the row without recreating it ----------------------
built.clear()
alpha_row = _row("alpha")["row"]
cw.update_muc_users([
    _user("mod2", role="moderator"),
    _user("guest1", role="visitor"),
    _user("alpha"),
    _user("mod1", role="moderator", affiliation="owner"),
    _user("zeta", role="moderator"),
    _user("guest2", role="visitor"),
])
check("a role change recreates nothing", built == [])
check("a role change moves the row into its new section",
      _nicks() == ["mod1", "mod2", "zeta", "alpha", "guest1", "guest2"]
      and _row("alpha")["row"] is alpha_row)
check("the section counts follow the role change",
      _headers() == [tr("muc_section_moderators") + " (3)",
                     tr("muc_section_participants") + " (1)",
                     tr("muc_section_guests") + " (2)"])

# 4. leaving removes only that row -----------------------------------------
cw.update_muc_users([
    _user("mod2", role="moderator"),
    _user("guest1", role="visitor"),
    _user("alpha"),
    _user("mod1", role="moderator", affiliation="owner"),
    _user("zeta", role="moderator"),
])
check("a participant who left is gone", "guest2" not in _nicks()
      and "guest2" not in cw._muc_rows)
check("the guest header count follows the leave",
      tr("muc_section_guests") + " (1)" in _headers())
cw.update_muc_users([
    _user("mod2", role="moderator"),
    _user("alpha"),
    _user("mod1", role="moderator", affiliation="owner"),
    _user("zeta", role="moderator"),
])
check("the guest header disappears with its last member",
      all(tr("muc_section_guests") not in header for header in _headers()))

# 5. in-place badge/show updates -------------------------------------------
cw.update_muc_users([
    _user("mod2", role="moderator"),
    _user("alpha"),
    _user("mod1", role="moderator", affiliation="owner"),
    _user("zeta", show="dnd", role="moderator"),
])
check("a status change updates the row icon in place",
      bool(_row("zeta")["status"].pixmap())
      and _row("zeta")["user"]["show"] == "dnd")
label_before = _row("zeta")["label"].text()
cw.update_muc_users([
    _user("mod2", role="moderator"),
    _user("alpha"),
    _user("mod1", role="moderator", affiliation="owner"),
    _user("zeta", show="dnd", role="moderator", affiliation="admin"),
])
check("an affiliation change updates the badge in place",
      _row("zeta")["label"].text() != label_before
      and "zeta" in _row("zeta")["label"].text())
built_before = len(built)
cw.set_self_nick("mod1")
check("the self nick is marked in place",
      tr("muc_you") in _row("mod1")["label"].text())
check("the self nick does not rebuild the list", len(built) == built_before)

# 6. case-insensitive alphabetical order inside a section -------------------
cw.update_muc_users([
    _user("bob"), _user("Alice"), _user("carol"),
])
check("names sort case-insensitively",
      _nicks() == ["Alice", "bob", "carol"])

# 7. a real full rebuild (font/options) can still be requested --------------
cw._render_muc_users()
check("a full rebuild lists everyone again", len(_nicks()) == 3)
check("a full rebuild recreates the rows", len(built) > built_before)

# 8. the large-channel case: 200 presences, 200 rows ----------------------
cw2 = chat_widget_mod.ChatWidget(
    "big@conf.example/me", "Big", chat_themes.ChatThemeFactory(), is_muc=True)
built2: list[str] = []
_build2 = cw2._build_muc_user_row


def _counting_build2(user):
    built2.append(str(user.get("nick", "")))
    return _build2(user)


cw2._build_muc_user_row = _counting_build2
big = [_user("member%03d" % i) for i in range(200)]
for index in range(len(big)):
    cw2.update_muc_users(big[:index + 1])
check("200 presences create exactly 200 rows", len(built2) == 200)
cw2.update_muc_users(big)
check("a full snapshot after the dump creates no rows", len(built2) == 200)
check("the large list holds every participant", len(cw2._muc_rows) == 200)
cw2.close()

# 9. one avatar/vCard update touches only that participant's row ----------
cw3 = chat_widget_mod.ChatWidget(
    "room@conf.example/me", "Room", chat_themes.ChatThemeFactory(), is_muc=True)
cw3.update_muc_users([_user("alice"), _user("bob"), _user("carol")])
bob_row = cw3._muc_rows["bob"]["row"]
alice_row = cw3._muc_rows["alice"]["row"]
avatar_before = cw3._muc_rows["bob"]["avatar"].pixmap().cacheKey()
pix = QtGui.QPixmap(24, 24)
pix.fill(QtGui.QColor("#d32f2f"))
avatar_file = os.path.join(_SCRATCH, "bob.png")
pix.save(avatar_file)
bob_user = next(u for u in cw3._users if u["nick"] == "bob")
bob_user["avatar_path"] = avatar_file
cw3.refresh_participant("bob")
check("refresh_participant keeps every row object in place",
      cw3._muc_rows["bob"]["row"] is bob_row
      and cw3._muc_rows["alice"]["row"] is alice_row)
check("refresh_participant applies the new avatar to that row",
      cw3._muc_rows["bob"]["avatar_path"] == avatar_file
      and cw3._muc_rows["bob"]["avatar"].pixmap().cacheKey()
      != avatar_before)
check("refresh_participant ignores a missing participant",
      cw3.refresh_participant("nobody") is None)
cw3.close()

# 10. a participant card never invalidates the roster or the whole list -----
from stanza_im.ui.main_window import MainWindow  # noqa: E402


class _FakeChat:
    def __init__(self):
        self.calls = []

    def refresh_participant(self, nick):
        self.calls.append(("row", nick))

    def refresh_avatar_for_sender(self, nick, jid):
        self.calls.append(("message", nick, jid))


win = MainWindow.__new__(MainWindow)
room = "room@conf.example"
win._muc_users = {room: {"bob": {"nick": "bob"}}}
win._pm_targets = {}
fake_chat = _FakeChat()
win._chat_window = type("Win", (), {
    "get_chat": lambda self, jid: fake_chat if jid == room else None})()
win._muji_windows = {}
win._refresh_avatar(f"{room}/bob", "/tmp/bob-card.png")
check("a participant card updates only its row and messages",
      win._muc_users[room]["bob"]["avatar_path"] == "/tmp/bob-card.png"
      and win._muc_users[room]["bob"]["avatar_jid"] == f"{room}/bob"
      and fake_chat.calls == [("row", "bob"),
                              ("message", "bob", f"{room}/bob")])
_src = inspect.getsource(MainWindow._refresh_avatar)
check("a participant card skips the whole-list avatar reload",
      "refresh_avatars=True" not in _src
      and "chat.refresh_participant(nick)" in _src)

cw.close()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All MUC participant tests passed.")
