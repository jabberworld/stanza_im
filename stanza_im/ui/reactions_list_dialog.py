"""Full XEP-0444 reaction list for a message.

Opened by clicking the "+k" overflow chip under a message.  Shows every
reaction as a flat, newest-first list: the reactor (nick/JID) and the date/time
on the left in the normal font, the emoji on the right drawn with a colour-emoji
font.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.ui.emoji_picker_dialog import emoji_font


class ReactionsListDialog(QtWidgets.QDialog):
    """A read-only list of all reactions on a message."""

    _ROW_HEIGHT = 46

    def __init__(self, rows: list[dict] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("reaction_list_title"))
        self.setMinimumSize(340, 260)
        layout = QtWidgets.QVBoxLayout(self)

        self._list = QtWidgets.QListWidget(self)
        self._list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self._list.setUniformItemSizes(False)
        self._list.setWordWrap(False)
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
            item = QtWidgets.QListWidgetItem(self._list)
            item.setSizeHint(QtCore.QSize(0, self._ROW_HEIGHT))
            widget = _ReactionRow(
                str(row.get("emoji") or ""),
                str(row.get("who") or ""),
                str(row.get("at") or ""), self._list)
            self._list.setItemWidget(item, widget)
        if not rows:
            item = QtWidgets.QListWidgetItem(tr("reaction_list_empty"),
                                             self._list)
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)


class _ReactionRow(QtWidgets.QWidget):
    """One list row: reactor/time on the left, the emoji on the right."""

    def __init__(self, emoji: str, who: str, at: str, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(8)

        left = QtWidgets.QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        name_label = QtWidgets.QLabel(who or "—", self)
        name_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        time_label = QtWidgets.QLabel(at, self)
        time_label.setStyleSheet("color: #888; font-size: 90%;")
        left.addWidget(name_label)
        left.addWidget(time_label)
        layout.addLayout(left, 1)

        emoji_label = QtWidgets.QLabel(emoji, self)
        emoji_label.setFont(emoji_font(20))
        emoji_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter)
        emoji_label.setMinimumWidth(44)
        layout.addWidget(emoji_label, 0)
