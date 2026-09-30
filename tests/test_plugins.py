"""Offscreen tests for the plugin system and the Notes plugin.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_plugins.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_plugins_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.core.client import NS_NOTES, _parse_notes
from stanza_im.core.storage import Config
from stanza_im.i18n import en, load as i18n_load, ru
from stanza_im.plugins import (
    discover, enabled_ids, get, missing_enabled, set_enabled,
    stored_enabled_ids)
from stanza_im.ui.notes_dialog import NoteDialog
from stanza_im.ui.plugin_manager_dialog import PluginManagerDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. Registry ----------------------------------------------------------------
plugins = discover()
ids = [p.id for p in plugins]
check("the notes plugin is discovered", "notes" in ids)
notes = get("notes")
check("the notes plugin has the Tools category",
      notes.category == "plugin_category_tools")
check("the notes plugin carries an icon", notes.icon == "draw-brush.png")
check("plugins are sorted deterministically",
      ids == [p.id for p in discover()])

# 2. Config state ------------------------------------------------------------
cfg = Config()
check("no plugin enabled by default", enabled_ids(cfg, plugins) == [])
set_enabled(cfg, "notes", True)
check("enabling persists in config", enabled_ids(cfg, plugins) == ["notes"])
set_enabled(cfg, "ghost", True)
check("a saved-but-missing plugin is reported",
      missing_enabled(cfg, plugins) == ["ghost"])
check("stored ids include the missing one",
      set(stored_enabled_ids(cfg)) == {"notes", "ghost"})

# 3. Manager dialog ----------------------------------------------------------
dlg = PluginManagerDialog(cfg)
seen = []
dlg.plugins_changed.connect(seen.append)
categories = [dlg._tree.topLevelItem(i).text(0)
              for i in range(dlg._tree.topLevelItemCount())]
check("the manager groups plugins by category", categories == ["Tools"])
check("the enabled plugin starts checked", dlg._checked_ids() == ["notes"])
dlg._accept()
check("Ok emits the enabled ids", seen == [["notes"]])
check("Ok writes the flags to the config", cfg.plugins.get("notes") is True)
check("Ok disables the previously unchecked plugin",
      cfg.plugins.get("ghost") is False)

# 4. Protocol round-trip -----------------------------------------------------
sample = ET.fromstring(
    '<iq xmlns="jabber:iq:private"><query><storage xmlns="%s">'
    '<note tags=""><title/><text>Проверка записной книжки</text></note>'
    '<note tags="notes"><title>Еще одна заметка</title><text>Проверка</text>'
    '</note></storage></query></iq>' % NS_NOTES)
parsed = _parse_notes(sample)
check("the protocol parser reads both notes", len(parsed) == 2)
check("an empty title is preserved", parsed[0]["title"] == "")
check("the note text is read", parsed[0]["text"] == "Проверка записной книжки")
check("the tags attribute is read", parsed[1]["tags"] == "notes")
check("the title is read", parsed[1]["title"] == "Еще одна заметка")

# 5. Editor dialog -----------------------------------------------------------
nd = NoteDialog({"title": "T", "tags": "a, b", "text": "body"})
check("the editor prefills the title", nd._title.text() == "T")
check("the editor prefills the tags", nd._tags.text() == "a, b")
check("the editor prefills the text", nd._text.toPlainText() == "body")
nd._title.setText("New")
nd._tags.setText(" x ")
nd._text.setPlainText("hello")
collected = nd.collect()
check("collect returns the trimmed fields",
      collected == {"title": "New", "tags": "x", "text": "hello"})

# 6. Notes tab ---------------------------------------------------------------
from stanza_im.ui.notes_widget import NotesWidget, _split_tags

check("tags split on commas and trim", _split_tags("a, b ,c") == ["a", "b", "c"])
check("empty tag list yields nothing", _split_tags("") == [])

stored: dict = {"notes": []}


class _FakeClient:
    async def get_notes(self):
        return [dict(n) for n in stored["notes"]]

    async def set_notes(self, notes):
        stored["notes"] = [dict(n) for n in notes]


tasks = []


def _run_task(coro):
    import asyncio
    return asyncio.get_event_loop().create_task(coro)


widget = NotesWidget(lambda: _FakeClient(), _run_task)
stored["notes"] = [
    {"title": "First", "tags": "work", "text": "one"},
    {"title": "Second", "tags": "home, work", "text": "two"},
]
widget.reload()
loop = __import__("asyncio").get_event_loop()
loop.run_until_complete(__import__("asyncio").sleep(0.2))
check("the tab lists the fetched notes", widget._list.count() == 2)
tags = [widget._tag_filter.itemData(i)
        for i in range(widget._tag_filter.count())]
check("the filter starts with All tags", tags[0] == "__all__")
check("the filter lists the collected tags", tags[1:] == ["home", "work"])

widget._tag_filter.setCurrentIndex(widget._tag_filter.findData("home"))
loop.run_until_complete(__import__("asyncio").sleep(0.05))
visible = [widget._list.item(i).text() for i in range(widget._list.count())
           if not widget._list.item(i).isHidden()]
check("filtering by a tag hides non-matching notes", visible == ["Second"])

widget._tag_filter.setCurrentIndex(0)
widget._search.setText("first")
loop.run_until_complete(__import__("asyncio").sleep(0.05))
visible = [widget._list.item(i).text() for i in range(widget._list.count())
           if not widget._list.item(i).isHidden()]
check("the search box filters by title", visible == ["First"])

# 7. i18n parity -------------------------------------------------------------
check("en and ru have the same keys", set(en.STRINGS) == set(ru.STRINGS))
check("the notes tab tooltip is translated",
      en.STRINGS.get("roster_tab_notes") and ru.STRINGS.get("roster_tab_notes"))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All plugin tests passed.")
