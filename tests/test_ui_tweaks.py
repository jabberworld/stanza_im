"""Offscreen tests for recent UI tweaks: OSD width, event time, chat CSS and
the conference subject header font.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_ui_tweaks.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_tweaks_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PyQt6 import QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.osd import OsdManager, _OsdWindow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _css(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _src(*parts):
    return _css(*parts)


# 1. OSD width ---------------------------------------------------------------
cfg = Config()
check("osd_width default is 280", cfg.notifications.osd_width == 280)
cfg.notifications.osd_width = 420
cfg.save()
check("osd_width persists", Config().notifications.osd_width == 420)

win = _OsdWindow(None, "T", "B", width=420)
check("osd window honours the configured width", win.width() == 420)
win.deleteLater()

manager = OsdManager(cfg)
rec = manager._spawn(None, "T", "B", draggable=False, preview=True,
                     duration=0)
check("manager spawns with the configured width",
      rec["window"].width() == 420)
manager.apply_width(360)
check("apply_width resizes live windows", rec["window"].width() == 360)
manager.dismiss_all()

# 2. Event time --------------------------------------------------------------
from stanza_im.ui.main_window import MainWindow  # noqa: E402

w = MainWindow(app)
w._client = None
w._on_subscription_request("rss@transport", name="News")
row = w._events_list.itemWidget(w._events_list.item(0))
labels = [lb.text() for lb in row.findChildren(QtWidgets.QLabel)]
check("subscription event shows a time label",
      any(len(t) == 5 and t[2] == ":" for t in labels))
w._push_system_event("disconnected")
_last = w._events_list.item(w._events_list.count() - 1).text()
check("system event is prefixed with the time", _last[:5].count(":") == 1)

# 2b. Login splash stages ----------------------------------------------------
w._set_splash("stage", 40)
check("the splash bar is determinate (0..100)",
      w._splash_progress.minimum() == 0 and w._splash_progress.maximum() == 100)
check("_set_splash sets the label and value",
      w._splash_label.text() == "stage" and w._splash_progress.value() == 40)
w._set_splash("clamp", 250)
check("_set_splash clamps the percentage", w._splash_progress.value() == 100)
w.close()

# 3/4. Chat CSS: no dashed underline on nicknames/mentions or action buttons --
css = _css("resources", "chatskins", "minimal-mod", "main.css")
check("mention links reset the dashed underline",
      ".sender a.mention" in css and "border-bottom: none" in css)
check("action buttons reset the dashed underline",
      ".message_actions a.action-react" in css
      and ".message_actions a.action-reply" in css)
candy = _css("resources", "chatskins", "candy", "main.css")
check("candy has no generic dashed anchor rule",
      "border-bottom: 1px dashed" not in candy)

# 5. Conference subject header font ------------------------------------------
check("muc_subject_font config default",
      getattr(Config().appearance, "muc_subject_font", None) == ""
      and getattr(Config().appearance, "muc_subject_font_size", None) == 0)
cw = ChatWidget("room@conf.example", "Room", ChatThemeFactory(), is_muc=True)
cw.set_subject_font("DejaVu Sans", 17)
check("subject font applies to the label and the field",
      cw._subject_btn.font().pointSize() == 17
      and cw._subject_edit.font().pointSize() == 17)

from PyQt6 import QtCore, QtGui  # noqa: E402


def _wheel(delta=120, ctrl=True):
    return QtGui.QWheelEvent(
        QtCore.QPointF(5, 5), QtCore.QPointF(5, 5),
        QtCore.QPoint(0, 0), QtCore.QPoint(0, delta),
        QtCore.Qt.MouseButton.NoButton,
        (QtCore.Qt.KeyboardModifier.ControlModifier if ctrl
         else QtCore.Qt.KeyboardModifier.NoModifier),
        QtCore.Qt.ScrollPhase.NoScrollPhase, False)


zoomed = []
cw.subject_font_zoom_requested.connect(zoomed.append)
cw._subject_edit.wheelEvent(_wheel())
check("Ctrl+wheel on the subject field zoom requests the new size",
      zoomed == [18] and cw._subject_edit.font().pointSize() == 18)
zoomed.clear()
cw._subject_btn.wheelEvent(_wheel())
check("Ctrl+wheel on the subject button zoom requests the new size",
      zoomed == [19])
zoomed.clear()
cw._subject_edit.wheelEvent(_wheel(ctrl=False))
check("a plain wheel over the subject does not zoom", zoomed == [])
cw.detach()

# 6. Chat message-menu JS: every %LABEL% placeholder is declared and filled --
# (A missing `var X_LABEL = %X_LABEL%;` aborts openMenu, so the menu vanishes.)
import re  # noqa: E402

view_src = _src("stanza_im", "ui", "chat_view.py")
# The JS template body (between the _ACTION_JS """ and its closing """).
m = re.search(r'_ACTION_JS = """(.*?)"""', view_src, re.S)
check("the message-menu JS template is found", m is not None)
js = m.group(1) if m else ""
placeholders = set(re.findall(r"%([A-Z_]+)%", js))
declared = set(re.findall(r"var ([A-Z_]+) = %[A-Z_]+%;", js))
check("every label placeholder is declared as a JS var",
      placeholders <= declared)
check("the notes label placeholder is declared", "TONOTE_LABEL" in declared)
check("the notes-enabled flag is initialised in JS",
      "window.__stanzaNotesEnabled = window.__stanzaNotesEnabled || false;"
      in js)
# Copy/Forward/Notes show LOCAL time: fmtCopyTime must parse the (UTC) ISO
# timestamp with Date and use the local getters, not slice the string.
fmt = re.search(r"function fmtCopyTime\(raw\)\s*\{(.*?)\n            \}",
                js, re.S)
check("fmtCopyTime is found", fmt is not None)
fmt_body = fmt.group(1) if fmt else ""
check("fmtCopyTime parses the timestamp with Date", "new Date(full)" in fmt_body)
check("fmtCopyTime uses local getters",
      "getHours" in fmt_body and "getMinutes" in fmt_body)

# 6b. The xmpp: context-menu routing (conference -> bookmark, contact -> add).
from stanza_im.ui.chat_view import ChatView  # noqa: E402

t = ChatView._xmpp_menu_target
check("an xmpp ?join link is a conference",
      t("xmpp:room@conf.example?join") == ("room@conf.example", "join"))
check("an xmpp ?roster link is a contact",
      t("xmpp:user@server.example?roster") == ("user@server.example", "roster"))
check("a bare xmpp jid parses with an empty action",
      t("xmpp:user@server.example") == ("user@server.example", ""))
check("a non-xmpp link is not a target", t("https://example.com") is None)
check("an xmpp link without @ is not a target",
      t("xmpp:server.example?join") is None)
# The context-menu text mentions the two new entries.
check("the bookmark entry has a label",
      "ctx_bookmark_add" in view_src)
check("the add-contact entry has a label",
      "ctx_add_contact_short" in view_src)
check("the selection menu offers Add to notes",
      'tr("chat_to_note")' in view_src and "_notes_enabled" in view_src)
# _install_action_js must substitute every placeholder the template uses.
install = re.search(r"def _install_action_js\(self\):(.*?)runJavaScript",
                    view_src, re.S)
check("the action-JS installer is found", install is not None)
substituted = set(re.findall(r'\.replace\("%([A-Z_]+)%"',
                             install.group(1) if install else ""))
missing = placeholders - substituted
check("every label placeholder is substituted when installing (%s)"
      % (", ".join(sorted(missing)) if missing else "none"), not missing)

# Every control ref the menu sets must also be read back by the scroll poll,
# and have a matching `_clear_*_request` — otherwise the click is silently lost.
poll = re.search(r'var st = window\.scrollY(.*?)self\._on_scroll_position',
                 view_src, re.S)
check("the scroll-poll block is found", poll is not None)
poll_js = poll.group(0) if poll else ""
poll_refs = set(re.findall(r"window\.(__stanza[A-Za-z]+Ref)", poll_js))
set_refs = set(re.findall(r"window\.(__stanza[A-Za-z]+Ref)\s*=", js))
# Ignore refs that are only reset to '' (cleared), they are not menu actions.
set_refs = {r for r in set_refs if not r.endswith("NotesEnabled")}
missing_in_poll = set_refs - poll_refs
check("every menu ref is read by the scroll poll (%s)"
      % (", ".join(sorted(missing_in_poll)) if missing_in_poll else "none"),
      not missing_in_poll)
check("the notes ref is polled", "__stanzaToNoteRef" in poll_refs)
# Each polled ref has a clear<Name>Request helper, mirroring the pattern.
clear_funcs = set(re.findall(r"def _clear_([a-z_]+)_request", view_src))
for ref in sorted(poll_refs):
    name = ref[len("__stanza"):-len("Ref")]  # e.g. ToNote / MediaFs
    split = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    flat = name.lower()
    # The codebase uses both conventions (`media_fs`, but `xmpp`/`tonote`).
    check(f"a _clear_*_request helper exists for {ref}",
          split in clear_funcs or flat in clear_funcs)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All UI tweak tests passed.")
