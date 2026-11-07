"""Offscreen tests for jumping from a media card into the chat window.

A media jump must not trust the Python history window alone: the WebEngine
document keeps only the newest ``_MAX_DOM_MESSAGES`` nodes, so an older target
can be present in ``_history`` while its node is gone.  The jump then has to
prepend the missing contiguous slice and re-centre the target while media
previews settle.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_media_jump.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_mediajump_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402
from stanza_im.ui.chat_widget import ChatWidget  # noqa: E402
from stanza_im.ui import chat_view as chat_view_mod  # noqa: E402

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])


class _JumpView(QtWidgets.QWidget):
    """ChatView stand-in with a small per-message DOM cap."""

    _MAX_DOM_MESSAGES = 3

    def __init__(self):
        super().__init__()
        self.highlight_nick = ""
        self.added = []
        self.prepended = []
        self.scrolled = []
        self.bottom_scrolls = 0
        self.pin_values = []
        self._fraction = 1.0

    def shutdown(self):
        pass

    def set_chat_zoom(self, factor):
        pass

    def scroll_fraction(self):
        return self._fraction

    def set_scroll_fraction(self, fraction):
        self._fraction = fraction

    def clear(self):
        self.added = []

    def add_status(self, text, timestamp=""):
        pass

    def add_message(self, **kwargs):
        self.added.append(kwargs)

    def prepend_messages(self, messages, keep_position=True):
        self.prepended.append((list(messages), bool(keep_position)))

    def scroll_to_message(self, message_id, highlight=True, timestamp="",
                          anchor_restore=False, pin=False):
        self.scrolled.append((message_id, bool(pin)))
        self.pin_values.append(bool(pin))

    def scroll_to_time(self, timestamp, anchor_restore=False):
        self.scrolled.append((timestamp, False))

    def scroll_to_bottom(self):
        self.bottom_scrolls += 1

    def seed_unseen(self, *args, **kwargs):
        pass

    def is_scrolled_up(self):
        return False

    def note_new_message(self, *args, **kwargs):
        pass

    def update_sender_avatar(self, *args, **kwargs):
        pass

    def set_media_thumbnail(self, *args, **kwargs):
        pass


def row(index: int) -> dict:
    ref = f"m{index}"
    return {
        "id": index,
        "direction": "incoming",
        "sender": "A",
        "body": f"message {index}",
        "timestamp": f"2026-11-03T10:{index:02d}:00.000000Z",
        "archive_id": "",
        "origin_id": ref,
        "reply_to": "",
        "reply_id": "",
        "message_id": ref,
        "edited": False,
        "retracted": False,
        "retract_marker": False,
        "retract_reason": "",
        "retract_by": "",
        "reactions": [],
        "media": None,
        "markup": None,
        "encrypted": False,
        "encryption": "",
        "stanza_id": ref,
    }


jid = "media@conf.example"
cw = ChatWidget(jid, "Room", ChatThemeFactory(), is_muc=True)
view = _JumpView()
cw._view = view
entries = [row(i) for i in range(1, 11)]
cw.set_history(entries, 10, True)

check("the rendered registry keeps only the newest DOM page",
      len(cw._rendered_order) == 3
      and cw._rendered_keys == {
          cw._entry_key(entries[-3]), cw._entry_key(entries[-2]),
          cw._entry_key(entries[-1])})

cw.jump_to_message("m1", "2026-11-03T10:01:00.000000Z")

check("an old target outside the DOM page is prepended",
      view.prepended and len(view.prepended[0][0]) == 7)
check("the prepended slice starts at the target and ends before the DOM",
      [item["message_id"] for item in view.prepended[0][0]]
      == [f"m{i}" for i in range(1, 8)])
check("the target is scrolled after it is rendered",
      view.scrolled[-1] == ("m1", True))
check("the rendered registry now contains the target",
      cw._entry_key(entries[0]) in cw._rendered_keys)
check("the missing slice fills the gap from the target to the old page",
      not view.prepended[0][1])

# A second jump to the same already-rendered row must not duplicate the slice.
before = len(view.prepended)
cw.jump_to_message("m1", "2026-11-03T10:01:00.000000Z")
check("a second jump does not prepend the same rows again",
      len(view.prepended) == before)
check("a second jump still reaches the target",
      view.scrolled[-1] == ("m1", True))

# A full re-render drops the old nodes again; the next jump must refill them.
cw.set_history(entries, 10, True)
cw.jump_to_message("m2", "2026-11-03T10:02:00.000000Z")
check("a jump after a full re-render refills the missing window",
      len(view.prepended) == before + 1
      and [item["message_id"] for item in view.prepended[-1][0]]
      == [f"m{i}" for i in range(2, 8)])

# The view source keeps the centered jump and the settle-window re-centre.
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
source = open(os.path.join(root, "stanza_im", "ui", "chat_view.py"),
              encoding="utf-8").read()
check("the jump still centers the target",
      "block: 'center'" in source)
check("a media jump has a settle-window re-centre",
      "_repin_jump_target" in source
      and "_jump_pin_until" in source
      and "pin: bool = False" in source)
check("the fallback view accepts the pin keyword",
      source.count("def scroll_to_message(self, message_id: str") == 2
      and "pin: bool = False" in source)

if FAILURES:
    print("FAILURES:", FAILURES)
    raise SystemExit(1)
print("All media-jump tests passed.")
