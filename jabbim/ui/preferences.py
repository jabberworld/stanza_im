"""Settings dialog organised into sections (General/Connection/Chat/
Appearance/Notifications/Plugins/Shortcuts)."""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from jabbim.core.storage import Config
from jabbim.i18n import tr
from jabbim.ui.chat_themes import ChatThemeFactory


class PreferencesDialog(QtWidgets.QDialog):
    """Modal settings dialog.  Reads/writes the shared :class:`Config`.

    Emits :attr:`settings_applied` after a successful Save so callers can
    apply the new values to live widgets.
    """

    settings_applied = QtCore.pyqtSignal()

    def __init__(self, config: Config, theme_factory: ChatThemeFactory,
                 parent=None):
        super().__init__(parent)
        self._config = config
        self._theme_factory = theme_factory
        self.setWindowTitle(tr("prefs_title"))
        self.setMinimumSize(520, 380)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        split = QtWidgets.QHBoxLayout()
        self._sections = QtWidgets.QListWidget()
        self._sections.setFixedWidth(160)
        self._sections.currentRowChanged.connect(self._on_section_changed)
        split.addWidget(self._sections)

        self._stack = QtWidgets.QStackedWidget()
        split.addWidget(self._stack, stretch=1)
        layout.addLayout(split)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._sections.addItems([
            tr("prefs_general"),
            tr("prefs_connection"),
            tr("prefs_appearance"),
            tr("prefs_chat"),
            tr("prefs_notifications"),
            tr("prefs_plugins"),
            tr("prefs_shortcuts"),
        ])

        self._stack.addWidget(self._page_general())
        self._stack.addWidget(self._page_connection())
        self._stack.addWidget(self._page_appearance())
        self._stack.addWidget(self._page_chat())
        self._stack.addWidget(self._page_notifications())
        self._stack.addWidget(self._page_plugins())
        self._stack.addWidget(self._page_shortcuts())
        self._sections.setCurrentRow(0)

    def _on_section_changed(self, row: int):
        self._stack.setCurrentIndex(max(0, row))

    @staticmethod
    def _page() -> tuple[QtWidgets.QWidget, QtWidgets.QFormLayout]:
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        return page, form

    def _page_general(self):
        page, form = self._page()
        self._close_to_tray = QtWidgets.QCheckBox()
        form.addRow(tr("prefs_close_to_tray"), self._close_to_tray)
        return page

    def _page_connection(self):
        page, form = self._page()
        self._auto_connect = QtWidgets.QCheckBox()
        form.addRow(tr("prefs_auto_connect"), self._auto_connect)
        self._save_password = QtWidgets.QCheckBox()
        form.addRow(tr("prefs_save_password"), self._save_password)
        return page

    def _page_appearance(self):
        page, form = self._page()
        self._show_avatars = QtWidgets.QCheckBox()
        form.addRow(tr("prefs_show_avatars"), self._show_avatars)
        self._theme_combo = QtWidgets.QComboBox()
        variants = self._theme_factory.variant_names()
        for name in variants:
            self._theme_combo.addItem(name, name)
        self._theme_combo.insertItem(0, tr("prefs_theme_default"), "")
        form.addRow(tr("prefs_theme"), self._theme_combo)
        return page

    def _page_chat(self):
        page, form = self._page()
        self._history_limit = QtWidgets.QSpinBox()
        self._history_limit.setRange(10, 5000)
        self._history_limit.setSingleStep(10)
        form.addRow(tr("prefs_history_limit"), self._history_limit)
        self._tab_title_length = QtWidgets.QSpinBox()
        self._tab_title_length.setRange(10, 120)
        self._tab_title_length.setSingleStep(5)
        form.addRow(tr("prefs_tab_title_length"), self._tab_title_length)
        return page

    def _page_notifications(self):
        page, form = self._page()
        self._tray_blink = QtWidgets.QCheckBox()
        form.addRow(tr("prefs_tray_blink"), self._tray_blink)
        self._popups = QtWidgets.QCheckBox()
        form.addRow(tr("prefs_popups"), self._popups)
        return page

    def _page_plugins(self):
        page, form = self._page()
        label = QtWidgets.QLabel(tr("prefs_no_plugins"))
        label.setWordWrap(True)
        form.addRow(label)
        return page

    def _page_shortcuts(self):
        page, form = self._page()
        label = QtWidgets.QLabel(tr("prefs_shortcuts_list"))
        label.setWordWrap(True)
        form.addRow(label)
        return page

    # ── Value load / save ────────────────────────────────────────

    def _load_values(self):
        cfg = self._config
        self._close_to_tray.setChecked(cfg.ui.close_to_tray)
        self._auto_connect.setChecked(cfg.auto_connect)
        self._save_password.setChecked(cfg.save_password)
        self._show_avatars.setChecked(cfg.chat.show_avatars)
        idx = self._theme_combo.findData(cfg.chat.theme)
        self._theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._history_limit.setValue(int(cfg.chat.history_limit or 200))
        self._tab_title_length.setValue(int(cfg.chat.tab_title_length or 30))
        self._tray_blink.setChecked(cfg.notifications.tray_blink)
        self._popups.setChecked(cfg.notifications.popups)

    def _on_save(self):
        cfg = self._config
        cfg.ui.close_to_tray = self._close_to_tray.isChecked()
        cfg.auto_connect = self._auto_connect.isChecked()
        cfg.save_password = self._save_password.isChecked()
        cfg.chat.show_avatars = self._show_avatars.isChecked()
        cfg.chat.theme = self._theme_combo.currentData() or ""
        cfg.chat.history_limit = self._history_limit.value()
        cfg.chat.tab_title_length = self._tab_title_length.value()
        cfg.notifications.tray_blink = self._tray_blink.isChecked()
        cfg.notifications.popups = self._popups.isChecked()
        cfg.save()
        self.settings_applied.emit()
        self.accept()
