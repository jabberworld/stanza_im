"""Create-conference dialog.

Collects the room address, optional name and server, plus the initial room
configuration (persistent / invisible / members-only / anonymous) with three
quick presets.  The caller joins the room and, when the room was created by
this join (XEP-0045 status code 201), applies the chosen configuration.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon


class CreateConferenceDialog(QtWidgets.QDialog):
    """Ask for the address/server and the initial room settings."""

    def __init__(self, servers: list[str], default_server: str = "",
                 parent=None):
        super().__init__(parent)
        self._server_values = list(dict.fromkeys(
            [s for s in (servers or []) if s]))
        if default_server and default_server not in self._server_values:
            self._server_values.insert(0, default_server)
        self.setWindowTitle(tr("conference_create_title"))
        self.setMinimumWidth(460)
        layout = QtWidgets.QVBoxLayout(self)

        # ── Head ──────────────────────────────────────────────────
        head = QtWidgets.QHBoxLayout()
        icon = QtWidgets.QLabel()
        pix = QtGui.QIcon(find_icon("conference-add.svg")).pixmap(48, 48)
        if not pix.isNull():
            icon.setPixmap(pix)
        head.addWidget(icon, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        explanation = QtWidgets.QLabel(tr("conference_create_explanation"))
        explanation.setWordWrap(True)
        head.addWidget(explanation, 1)
        layout.addLayout(head)

        # ── Address / name / server ──────────────────────────────
        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._address = QtWidgets.QLineEdit()
        self._address.setPlaceholderText(tr("conference_address_placeholder"))
        address_row = self._row(self._address,
                                self._info_icon(tr("conference_address_info")))
        form.addRow(self._star_label(tr("conference_address")), address_row)

        self._name = QtWidgets.QLineEdit()
        name_row = self._row(self._name,
                             self._info_icon(tr("conference_name_info")),
                             stretch_index=0)
        form.addRow(tr("conference_name"), name_row)

        self._server = QtWidgets.QComboBox()
        self._server.setEditable(True)
        self._server.addItems(self._server_values)
        if default_server:
            self._server.setCurrentText(default_server)
        server_row = self._row(self._server,
                               self._info_icon(tr("conference_server_info")),
                               stretch_index=0)
        form.addRow(self._star_label(tr("conference_server")), server_row)
        layout.addLayout(form)

        # ── Settings ─────────────────────────────────────────────
        settings = QtWidgets.QGroupBox(tr("conference_settings"))
        s_form = QtWidgets.QFormLayout(settings)
        self._persistent = QtWidgets.QCheckBox()
        self._invisible = QtWidgets.QCheckBox()
        self._members_only = QtWidgets.QCheckBox()
        self._anonymous = QtWidgets.QCheckBox()
        self._anonymous.setChecked(True)
        for key, check, tip in (
                ("persistent", self._persistent, "conference_persistent_info"),
                ("invisible", self._invisible, "conference_invisible_info"),
                ("members_only", self._members_only,
                 "conference_members_only_info"),
                ("anonymous", self._anonymous, "conference_anonymous_info")):
            check.setText(tr(f"conference_{key}"))
            s_form.addRow(check, self._info_icon(tr(tip)))
        layout.addWidget(settings)

        # ── Presets ──────────────────────────────────────────────
        presets = QtWidgets.QHBoxLayout()
        public = QtWidgets.QPushButton(tr("conference_preset_public"))
        public.clicked.connect(self._preset_public)
        calls = QtWidgets.QPushButton(tr("conference_preset_calls"))
        calls.clicked.connect(self._preset_calls)
        private = QtWidgets.QPushButton(tr("conference_preset_private"))
        private.clicked.connect(self._preset_private)
        for button in (public, calls, private):
            presets.addWidget(button)
        layout.addLayout(presets)

        # ── Buttons ──────────────────────────────────────────────
        buttons = QtWidgets.QDialogButtonBox()
        create = buttons.addButton(
            tr("conference_create"),
            QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = buttons.addButton(
            tr("dialog_cancel"),
            QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        create.clicked.connect(self._validate)
        cancel.clicked.connect(self.reject)
        layout.addWidget(buttons)

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _info_icon(tooltip: str, parent=None) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(parent)
        icon = QtGui.QIcon(find_icon("info.svg"))
        if not icon.isNull():
            label.setPixmap(icon.pixmap(16, 16))
        label.setToolTip(tooltip)
        return label

    @staticmethod
    def _star_label(text: str, parent=None) -> QtWidgets.QLabel:
        """A field label with a red required marker."""
        label = QtWidgets.QLabel(f'{text} <span style="color:#c0392b">*</span>',
                                 parent)
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        return label

    @staticmethod
    def _row(*widgets: QtWidgets.QWidget,
             stretch_index: int | None = None) -> QtWidgets.QWidget:
        box = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for index, widget in enumerate(widgets):
            row.addWidget(widget, 1 if index == stretch_index else 0)
        return box

    # ── Presets ───────────────────────────────────────────────────

    def _preset_public(self) -> None:
        self._anonymous.setChecked(True)
        self._invisible.setChecked(False)
        self._members_only.setChecked(False)

    def _preset_calls(self) -> None:
        self._members_only.setChecked(True)
        self._anonymous.setChecked(False)

    def _preset_private(self) -> None:
        self._invisible.setChecked(True)
        self._members_only.setChecked(True)
        self._anonymous.setChecked(False)

    # ── Validation / result ───────────────────────────────────────

    def _validate(self) -> None:
        if not self._address.text().strip():
            self._address.setFocus()
            return
        if not self._server.currentText().strip():
            self._server.setFocus()
            return
        self.accept()

    def collect(self) -> dict:
        return {
            "room": self._address.text().strip(),
            "name": self._name.text().strip(),
            "server": self._server.currentText().strip(),
            "persistent": self._persistent.isChecked(),
            "invisible": self._invisible.isChecked(),
            "members_only": self._members_only.isChecked(),
            "anonymous": self._anonymous.isChecked(),
        }
