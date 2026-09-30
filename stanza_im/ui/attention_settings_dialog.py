"""Attention plugin settings dialog (XEP-0224).

Values live in ``config.plugin_settings.attention``:
``cooldown`` (incoming per-contact throttle, seconds), ``allow_dnd``,
``play_sound`` and ``show_events``.  The sound checkbox carries a note-glyph
preview button (same style as the sound preferences).
"""
from __future__ import annotations

import os

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import SOUNDS_DIR, find_icon
from stanza_im.ui.sounds import SoundPlayer


class AttentionSettingsDialog(QtWidgets.QDialog):
    """Edit the Attention plugin settings."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._sounds = getattr(parent, "_sounds", None)
        if self._sounds is None:
            # Opened from the plugin manager (no MainWindow) — own a player so
            # the preview still works.
            self._sounds = SoundPlayer()
        from stanza_im.plugins import settings_section
        self._section = settings_section(config, "attention")
        section = self._section

        self.setWindowTitle(tr("plugin_attention_settings_title"))
        self.setMinimumWidth(420)
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Cooldown row: spinner + "seconds".
        cooldown_row = QtWidgets.QHBoxLayout()
        self._cooldown = QtWidgets.QSpinBox()
        self._cooldown.setRange(1, 99)
        self._cooldown.setValue(int(getattr(section, "cooldown", 60) or 60))
        self._cooldown.setFixedWidth(70)
        cooldown_row.addWidget(self._cooldown)
        cooldown_row.addWidget(QtWidgets.QLabel(tr("attention_seconds")))
        cooldown_row.addStretch(1)
        form.addRow(tr("attention_cooldown_label"), cooldown_row)

        self._allow_dnd = QtWidgets.QCheckBox(tr("attention_allow_dnd"))
        self._allow_dnd.setChecked(bool(getattr(section, "allow_dnd", True)))
        form.addRow(self._allow_dnd)

        sound_row = QtWidgets.QHBoxLayout()
        self._play_sound = QtWidgets.QCheckBox(tr("attention_play_sound"))
        self._play_sound.setChecked(bool(getattr(section, "play_sound", True)))
        sound_row.addWidget(self._play_sound)
        preview = QtWidgets.QToolButton()
        icon = QtGui.QIcon(find_icon("sound.svg"))
        if not icon.isNull():
            preview.setIcon(icon)
        preview.setIconSize(QtCore.QSize(16, 16))
        preview.setAutoRaise(True)
        preview.setToolTip(tr("prefs_sound_preview_tip"))
        preview.clicked.connect(self._preview)
        sound_row.addWidget(preview)
        sound_row.addStretch(1)
        form.addRow(sound_row)

        self._show_events = QtWidgets.QCheckBox(tr("attention_show_events"))
        self._show_events.setChecked(bool(getattr(section, "show_events", True)))
        form.addRow(self._show_events)

        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(tr("dialog_ok"))
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
                tr("dialog_cancel"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _preview(self) -> None:
        path = os.path.join(SOUNDS_DIR, "effects", "door_bell.wav")
        if self._sounds is not None and os.path.isfile(path):
            self._sounds.play_file(path)

    def _accept(self) -> None:
        section = self._section
        section.cooldown = int(self._cooldown.value())
        section.allow_dnd = bool(self._allow_dnd.isChecked())
        section.play_sound = bool(self._play_sound.isChecked())
        section.show_events = bool(self._show_events.isChecked())
        self._config.save()
        self.accept()
