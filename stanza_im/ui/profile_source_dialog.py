"""Ask how a new profile should be created (XEP-0077 registration vs. an
existing account)."""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon


def _icon(name: str) -> QtGui.QIcon:
    path = find_icon(name)
    return QtGui.QIcon(path) if path else QtGui.QIcon()


class ProfileSourceDialog(QtWidgets.QDialog):
    """Two choices: an existing account or a new registration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._choice = ""
        self.setWindowTitle(tr("profiles_source_title"))
        self.setMinimumWidth(340)
        layout = QtWidgets.QVBoxLayout(self)
        prompt = QtWidgets.QLabel(tr("profiles_source_prompt"))
        prompt.setWordWrap(True)
        layout.addWidget(prompt)

        existing = QtWidgets.QPushButton(tr("profiles_source_existing"))
        existing.setIcon(_icon("v-card.png"))
        existing.setIconSize(QtCore.QSize(16, 16))
        existing.clicked.connect(lambda: self._pick("existing"))
        layout.addWidget(existing)

        register = QtWidgets.QPushButton(tr("profiles_source_register"))
        register.setIcon(_icon("add-user.png"))
        register.setIconSize(QtCore.QSize(16, 16))
        register.clicked.connect(lambda: self._pick("register"))
        layout.addWidget(register)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        cancel = QtWidgets.QPushButton(tr("dialog_cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _pick(self, choice: str) -> None:
        self._choice = choice
        self.accept()

    def choice(self) -> str:
        """``"existing"``, ``"register"`` or ``""`` when cancelled."""
        return self._choice
