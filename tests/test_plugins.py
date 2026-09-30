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

from PyQt6 import QtCore, QtGui, QtWidgets

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


def _roundtrip_setting(cfg) -> bool:
    """Save *cfg* and reload it; True when the fake setting survived."""
    from stanza_im.core.storage import Config
    cfg.save()
    reloaded = Config()
    return (reloaded.plugin_settings.get("fake", {}).get("greeting") == "hi")


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
tree = dlg._widget._tree
categories = [tree.topLevelItem(i).text(0)
              for i in range(tree.topLevelItemCount())]
check("the manager groups plugins by category", categories == ["Tools"])
check("the enabled plugin starts checked", dlg._widget.checked_ids() == ["notes"])
check("Configure is disabled for a plugin without settings",
      not dlg._widget._configure_btn.isEnabled())
dlg._accept()
check("Ok emits the enabled ids", seen == [["notes"]])
check("Ok writes the flags to the config", cfg.plugins.get("notes") is True)
check("Ok disables the previously unchecked plugin",
      cfg.plugins.get("ghost") is False)

# 3b. Per-plugin settings ----------------------------------------------------
from stanza_im.plugins import Plugin, settings_section  # noqa: E402
from stanza_im.ui.plugin_manager_dialog import PluginManagerWidget  # noqa: E402


class _FakeSettingsModule:
    """A minimal plugin module with a settings dialog."""

    def __init__(self):
        self.opened = 0

    def open_settings(self, config, parent=None):
        self.opened += 1
        settings_section(config, "fake").greeting = "hi"


_fake_mod = _FakeSettingsModule()
_fake = Plugin(id="fake", name="plugin_notes_name",
               category="plugin_category_tools", icon="draw-brush.png",
               module=_fake_mod, has_settings=True)
_plain = Plugin(id="notes", name="plugin_notes_name",
                category="plugin_category_tools", icon="draw-brush.png",
                module=_FakeSettingsModule(), has_settings=False)

w = PluginManagerWidget(cfg, plugins=[_fake, _plain])
check("Configure is disabled with no plugin selected",
      not w._configure_btn.isEnabled())
plain_item = None
for i in range(w._tree.topLevelItemCount()):
    hdr = w._tree.topLevelItem(i)
    for j in range(hdr.childCount()):
        if hdr.child(j).data(0, QtCore.Qt.ItemDataRole.UserRole) == "notes":
            plain_item = hdr.child(j)
w._tree.setCurrentItem(plain_item)
check("Configure stays disabled for a settings-less plugin",
      not w._configure_btn.isEnabled())
for i in range(w._tree.topLevelItemCount()):
    hdr = w._tree.topLevelItem(i)
    for j in range(hdr.childCount()):
        if hdr.child(j).data(0, QtCore.Qt.ItemDataRole.UserRole) == "fake":
            w._tree.setCurrentItem(hdr.child(j))
check("Configure is enabled for a settings-capable plugin",
      w._configure_btn.isEnabled())
w._on_configure()
check("Configure opens the plugin's settings dialog", _fake_mod.opened == 1)
check("the plugin's settings are stored in config.plugin_settings",
      cfg.plugin_settings.get("fake", {}).get("greeting") == "hi")
check("settings survive a config save/load round-trip",
      _roundtrip_setting(cfg))

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

# 6b. Clicking empty space clears the note selection (shared ZoomListWidget).
from stanza_im.ui.zoom_list import ZoomListWidget  # noqa: E402

check("the notes list is a ZoomListWidget", isinstance(widget._list, ZoomListWidget))
if widget._list.count():
    widget._list.setCurrentRow(0)
    widget._list.selectAll()
    pressed = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonPress,
        QtCore.QPointF(5, widget._list.height() - 1),
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier)
    widget._list.mousePressEvent(pressed)
    check("a click on empty space clears the note selection",
          widget._list.selectedItems() == [])

# 7. i18n parity + plugin strings --------------------------------------------
from stanza_im import i18n  # noqa: E402

i18n_load("en")
merged_en = dict(i18n._current)
i18n_load("ru")
merged_ru = dict(i18n._current)
check("the merged en/ru dictionaries have the same keys",
      set(merged_en) == set(merged_ru))
check("the plugin's own strings are merged in",
      i18n.tr("notes_open") == "Открыть"
      and i18n.tr("plugin_category_tools") == "Инструменты")
check("the manager's strings stay in the core dictionary",
      "plugin_manager_title" in en.STRINGS and "plugin_manager_title" in ru.STRINGS)
check("plugin-owned keys are no longer in the core dictionary",
      "notes_open" not in en.STRINGS and "notes_open" not in ru.STRINGS)
from stanza_im.plugins.notes import strings as _notes_strings  # noqa: E402

check("the plugin has its own en/ru string modules",
      _notes_strings.en.STRINGS and _notes_strings.ru.STRINGS)
check("the plugin's en/ru strings have the same keys",
      set(_notes_strings.en.STRINGS) == set(_notes_strings.ru.STRINGS))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All plugin tests passed.")
