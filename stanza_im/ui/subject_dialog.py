"""Multi-language MUC subject editor dialog."""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr

_PRESET_LANGUAGES = [
    ("de", "Deutsch"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
    ("it", "Italiano"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("nl", "Nederlands"),
    ("pl", "Polski"),
    ("pt", "Português"),
    ("ru", "Русский"),
    ("uk", "Українська"),
    ("zh", "中文"),
]


class SubjectDialog(QtWidgets.QDialog):
    """Edit a room subject, one tab per language variant.

    The first tab holds the default subject (no ``xml:lang``).  A ``+``
    button in the tab row adds new language tabs; every tab uses a
    multiline editor.
    """

    def __init__(self, room: str, subjects: list[tuple[str, str]],
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("muc_set_subject_title"))
        self.setMinimumSize(520, 320)

        layout = QtWidgets.QVBoxLayout(self)

        self._tabs = QtWidgets.QTabWidget()
        self._editors: list[tuple[str, QtWidgets.QPlainTextEdit]] = []
        for lang, text in subjects:
            self._tabs.addTab(self._make_editor(lang, text),
                              tr("muc_subject_default") if not lang else lang)
        if not self._editors:
            self._tabs.addTab(self._make_editor("", ""),
                              tr("muc_subject_default"))
        layout.addWidget(self._tabs)

        add_btn = QtWidgets.QToolButton()
        add_btn.setText("+")
        add_btn.setToolTip(tr("muc_subject_add_language"))
        add_btn.clicked.connect(self._add_language)
        self._tabs.setCornerWidget(add_btn, QtCore.Qt.Corner.TopRightCorner)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(
            tr("dialog_ok"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
            tr("dialog_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _make_editor(self, lang: str, text: str) -> QtWidgets.QPlainTextEdit:
        editor = QtWidgets.QPlainTextEdit()
        editor.setTabChangesFocus(True)
        editor.setPlainText(text)
        self._editors.append((lang, editor))
        return editor

    def _pick_language(self) -> str:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(tr("muc_subject_add_language"))
        dialog.setMinimumWidth(280)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel(tr("muc_subject_language_select")))
        combo = QtWidgets.QComboBox()
        combo.setEditable(True)
        for code, name in _PRESET_LANGUAGES:
            combo.addItem(f"{name} ({code})", code)
        combo.setCurrentIndex(0)
        layout.addWidget(combo)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(
            tr("dialog_ok"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
            tr("dialog_cancel"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if not dialog.exec():
            return ""
        text = combo.currentText().strip()
        index = combo.findText(text)
        if index >= 0:
            return combo.itemData(index)
        return text

    def _add_language(self, language: str = ""):
        if not language:
            language = self._pick_language()
            if not language:
                return
        for i, (lang, _) in enumerate(self._editors):
            if lang == language:
                self._tabs.setCurrentIndex(i)
                return
        index = self._tabs.addTab(self._make_editor(language, ""), language)
        self._tabs.setCurrentIndex(index)

    def result_subjects(self) -> list[tuple[str, str]]:
        """Return non-empty variants, default (empty lang) first."""
        items = [(lang, editor.toPlainText().strip())
                 for lang, editor in self._editors if editor.toPlainText().strip()]
        items.sort(key=lambda pair: (1,) if pair[0] else (0,))
        return items