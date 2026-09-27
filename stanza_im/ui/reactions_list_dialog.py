"""Full XEP-0444 reaction list for a message.

Opened by clicking the "+k" overflow chip under a message.  Shows every
reaction as a flat, newest-first list of ``emoji who — when`` rows.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr
from stanza_im.ui.emoji_picker_dialog import emoji_font_family


class ReactionsListDialog(QtWidgets.QDialog):
    """A read-only list of all reactions on a message."""

    def __init__(self, rows: list[dict] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("reaction_list_title"))
        self.setMinimumSize(320, 240)
        layout = QtWidgets.QVBoxLayout(self)

        self._list = QtWidgets.QListWidget(self)
        self._list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self._list.setUniformItemSizes(True)
        # Draw emoji with a colour font (falling back to the widget's own
        # families for the "who — when" text), or they show as tofu boxes.
        family = emoji_font_family()
        if family:
            font = self._list.font()
            font.setFamilies([family] + list(font.families()))
            self._list.setFont(font)
        layout.addWidget(self._list, 1)

        self.set_reactions(rows or [])

        buttons = QtWidgets.QDialogButtonBox(self)
        close = buttons.addButton(
            tr("dialog_close"),
            QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        close.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def set_reactions(self, rows: list[dict]) -> None:
        """Fill the list.

        Each row is ``{"emoji", "who", "at"}`` (``at`` already formatted);
        rows arrive oldest-first and are shown newest-first.
        """
        self._list.clear()
        for row in reversed(rows):
            emoji = str(row.get("emoji") or "")
            who = str(row.get("who") or "")
            at = str(row.get("at") or "")
            text = emoji
            if who:
                text += "  " + who
            if at:
                text += " — " + at
            self._list.addItem(text)
        if not rows:
            item = QtWidgets.QListWidgetItem(tr("reaction_list_empty"))
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self._list.addItem(item)
