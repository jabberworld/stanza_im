"""Language selection dialog for the optional spell checker."""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr
from stanza_im.ui.spellcheck import language_name


class SpellLanguagesList(QtWidgets.QListWidget):
    """Checkable list of installed spell-check dictionaries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.setUniformItemSizes(True)
        self.setMinimumHeight(150)

    def set_languages(self, tags) -> None:
        self.clear()
        for tag in tags:
            item = QtWidgets.QListWidgetItem(language_name(tag))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, tag)
            item.setToolTip(tag)
            item.setFlags(item.flags()
                          | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self.addItem(item)

    def selected(self) -> list[str]:
        out = []
        for row in range(self.count()):
            item = self.item(row)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                out.append(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        return out

    def set_selected(self, tags) -> None:
        wanted = {str(tag) for tag in (tags or [])}
        for row in range(self.count()):
            item = self.item(row)
            tag = str(item.data(QtCore.Qt.ItemDataRole.UserRole))
            item.setCheckState(
                QtCore.Qt.CheckState.Checked if tag in wanted
                else QtCore.Qt.CheckState.Unchecked)


class SpellCheckLanguagesDialog(QtWidgets.QDialog):
    """Pick the dictionaries checked in parallel (or the automatic pair)."""

    def __init__(self, selected, available, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("spellcheck_languages_title"))
        self.resize(360, 340)
        layout = QtWidgets.QVBoxLayout(self)
        self._auto = QtWidgets.QCheckBox(tr("prefs_spellcheck_auto"))
        self._auto.setToolTip(tr("prefs_spellcheck_auto_tip"))
        layout.addWidget(self._auto)
        self._list = SpellLanguagesList()
        self._list.set_languages(available)
        self._list.set_selected(selected)
        layout.addWidget(self._list, 1)
        self._buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        self._auto.setChecked(not bool(selected))
        self._auto.toggled.connect(self._sync)
        self._list.itemChanged.connect(lambda _item: self._sync())
        self._sync()

    def _sync(self, *_args) -> None:
        auto = self._auto.isChecked()
        self._list.setEnabled(not auto)
        ok = self._buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setEnabled(auto or bool(self._list.selected()))

    def languages(self) -> list[str]:
        """Return ``[]`` for automatic mode, else the checked enchant tags."""
        if self._auto.isChecked():
            return []
        return self._list.selected()
