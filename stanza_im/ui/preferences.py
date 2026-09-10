"""Preferences dialog with icon navigation and section tabs."""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import tr
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui import icons as icons_mod
from stanza_im.include import emoticons


class PreferencesDialog(QtWidgets.QDialog):
    """Edit application settings grouped like the original Jabbim dialog."""

    settings_applied = QtCore.pyqtSignal()

    def __init__(self, config: Config, theme_factory: ChatThemeFactory,
                 osd_manager=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._theme_factory = theme_factory
        self._osd_manager = osd_manager
        self.setWindowTitle(tr("prefs_title"))
        self.setMinimumSize(760, 540)
        self._controls: dict[str, QtWidgets.QWidget] = {}
        self._build_ui()
        self._load_values()

    def done(self, result):
        if self._osd_manager is not None:
            self._osd_manager.hide_preview()
        super().done(result)

    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        split = QtWidgets.QHBoxLayout()
        self._sections = QtWidgets.QListWidget()
        self._sections.setFixedWidth(190)
        self._sections.setIconSize(QtCore.QSize(24, 24))
        self._sections.setStyleSheet(
            "QListWidget { background: white; border: 1px solid #d5d5d5; "
            "padding: 4px; } QListWidget::item { padding: 7px 4px; } "
            "QListWidget::item:selected { color: palette(highlighted-text); "
            "background: palette(highlight); }")
        self._sections.currentRowChanged.connect(
            lambda row: self._stack.setCurrentIndex(max(0, row)))
        split.addWidget(self._sections)

        self._stack = QtWidgets.QStackedWidget()
        split.addWidget(self._stack, stretch=1)
        outer.addLayout(split, stretch=1)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Apply
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(tr("dialog_ok"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Apply).setText(tr("dialog_apply"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(tr("dialog_cancel"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).clicked.connect(
            self._on_ok)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply_settings)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        sections = (
            ("prefs_application", "gtk-preferences", self._page_application),
            ("prefs_connection", "transports", self._page_connection),
            ("prefs_chat", "muc", self._page_chat),
            ("prefs_privacy", "system-users", self._page_privacy),
            ("prefs_appearance", "gtk-preferences", self._page_appearance),
            ("prefs_plugins", "event", self._page_plugins),
            ("prefs_notifications", "event", self._page_notifications),
            ("prefs_status", "system-users", self._page_status),
            ("prefs_shortcuts", "gtk-preferences", self._page_shortcuts),
        )
        for key, icon_name, page_factory in sections:
            icon = QtGui.QIcon()
            if icons_mod.icons:
                pixmap = icons_mod.icons.get_category_icon(icon_name)
                if not pixmap.isNull():
                    icon = QtGui.QIcon(pixmap)
            self._sections.addItem(QtWidgets.QListWidgetItem(icon, tr(key)))
            self._stack.addWidget(page_factory())
        self._sections.setCurrentRow(0)

    @staticmethod
    def _page() -> tuple[QtWidgets.QWidget, QtWidgets.QFormLayout]:
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return page, form

    def _tabs(self, pages: list[tuple[str, QtWidgets.QWidget]]) -> QtWidgets.QWidget:
        tabs = QtWidgets.QTabWidget()
        for title, page in pages:
            tabs.addTab(page, title)
        return tabs

    def _check(self, key: str, label: str, enabled: bool = True) -> QtWidgets.QCheckBox:
        widget = QtWidgets.QCheckBox(label)
        widget.setEnabled(enabled)
        self._controls[key] = widget
        return widget

    def _line(self, key: str, password: bool = False) -> QtWidgets.QLineEdit:
        widget = QtWidgets.QLineEdit()
        if password:
            widget.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._controls[key] = widget
        return widget

    def _spin(self, key: str, minimum: int, maximum: int) -> QtWidgets.QSpinBox:
        widget = QtWidgets.QSpinBox()
        widget.setRange(minimum, maximum)
        self._controls[key] = widget
        return widget

    def _combo(self, key: str,
               options: list[tuple[str, str]]) -> QtWidgets.QComboBox:
        widget = QtWidgets.QComboBox()
        for label_key, data in options:
            widget.addItem(tr(label_key), data)
        self._controls[key] = widget
        return widget

    def _page_application(self):
        general, form = self._page()
        form.addRow(self._check("close_to_tray", tr("prefs_close_to_tray")))
        form.addRow(tr("prefs_history_limit"), self._spin("history_limit", 10, 5000))
        form.addRow(tr("prefs_tab_title_length"), self._spin("tab_title_length", 10, 120))

        files, file_form = self._page()
        file_form.addRow(self._check("file_auto_accept", tr("prefs_file_auto_accept"), False))
        file_form.addRow(self._check("file_download_notifications",
                                     tr("prefs_file_download_notifications"), False))
        return self._tabs([(tr("prefs_general"), general),
                           (tr("prefs_file_transfer"), files)])

    def _page_connection(self):
        connection, form = self._page()
        form.addRow(tr("login_title"), self._line("jid"))
        form.addRow(tr("login_password"), self._line("password", True))
        form.addRow(self._check("save_password", tr("prefs_save_password")))
        form.addRow(self._check("auto_connect", tr("prefs_auto_connect")))
        form.addRow(self._check("auto_join_conferences", tr("prefs_auto_join_conferences")))
        form.addRow(self._check("message_carbons", tr("prefs_message_carbons")))
        form.addRow(self._check("save_status_message", tr("prefs_save_status_message")))

        advanced, advanced_form = self._page()
        resource = self._line("resource")
        advanced_form.addRow(tr("prefs_resource"), resource)
        override = self._check("override_host", tr("prefs_override_host"))
        advanced_form.addRow(override)
        host = self._line("host")
        port = self._spin("port", 1, 65535)
        host.setEnabled(False)
        port.setEnabled(False)
        override.toggled.connect(host.setEnabled)
        override.toggled.connect(port.setEnabled)
        advanced_form.addRow(tr("prefs_host"), host)
        advanced_form.addRow(tr("prefs_port"), port)

        proxy, proxy_form = self._page()
        proxy_form.addRow(tr("prefs_proxy_host"), self._line("proxy_host"))
        proxy_form.addRow(tr("prefs_proxy_port"), self._spin("proxy_port", 0, 65535))
        proxy_form.addRow(QtWidgets.QLabel(tr("prefs_proxy_socks5_note")))
        return self._tabs([(tr("prefs_connection_tab"), connection),
                           (tr("prefs_advanced"), advanced),
                           (tr("prefs_proxy"), proxy)])

    def _page_chat(self):
        general, general_form = self._page()
        general_form.addRow(self._check("send_ctrl_enter", tr("prefs_send_ctrl_enter")))

        chat, chat_form = self._page()
        chat_form.addRow(self._check("show_status", tr("prefs_show_status")))
        chat_form.addRow(self._check("show_receipts", tr("prefs_show_receipts")))
        chat_form.addRow(self._check("show_mood", tr("prefs_show_mood"), False))
        chat_form.addRow(self._check("show_music", tr("prefs_show_music"), False))
        chat_form.addRow(self._check("show_avatars", tr("prefs_show_avatars")))
        chat_form.addRow(self._check("message_styling",
                                     tr("prefs_message_styling")))
        chat_form.addRow(tr("prefs_history_limit"), self._spin("history_limit_chat", 10, 5000))
        chat_form.addRow(tr("prefs_tab_title_length"), self._spin("tab_title_length_chat", 10, 120))

        muc, muc_form = self._page()
        muc_show_status = self._check("muc_show_status",
                                      tr("prefs_muc_show_status"))
        muc_form.addRow(self._check("muc_show_presence", tr("prefs_muc_show_presence")))
        muc_form.addRow(muc_show_status)
        muc_show_status_text = self._check(
            "muc_show_status_text", tr("prefs_muc_show_status_text"))
        muc_form.addRow(muc_show_status_text)
        muc_show_status_text.setEnabled(muc_show_status.isChecked())
        muc_show_status.toggled.connect(muc_show_status_text.setEnabled)
        muc_form.addRow(self._check("muc_auto_nick", tr("prefs_muc_auto_nick")))
        muc_form.addRow(self._check("muc_confirm_leave",
                                    tr("prefs_muc_confirm_leave")))
        muc_form.addRow(self._check("muc_minimize_startup",
                                    tr("prefs_muc_minimize_startup")))
        return self._tabs([(tr("prefs_general"), general),
                           (tr("prefs_chat_tab"), chat),
                           (tr("prefs_conferences"), muc)])

    def _page_privacy(self):
        page, form = self._page()
        form.addRow(self._check("send_software", tr("prefs_send_software")))
        form.addRow(self._check("send_typing_notifications", tr("prefs_send_typing_notifications")))
        form.addRow(self._check("send_activity_notifications", tr("prefs_send_activity_notifications")))
        return page

    def _page_appearance(self):
        page, form = self._page()
        theme = QtWidgets.QComboBox()
        for name in self._theme_factory.variant_names():
            theme.addItem(name, name)
        theme.insertItem(0, tr("prefs_theme_default"), "")
        self._controls["chat_theme"] = theme
        muc_theme = QtWidgets.QComboBox()
        for name in self._theme_factory.variant_names():
            muc_theme.addItem(name, name)
        muc_theme.insertItem(0, tr("prefs_theme_default"), "")
        self._controls["muc_theme"] = muc_theme
        form.addRow(tr("prefs_chat_theme"), theme)
        form.addRow(tr("prefs_muc_theme"), muc_theme)
        emoticon_theme = QtWidgets.QComboBox()
        for item in emoticons.discover_sets():
            emoticon_theme.addItem(item["name"], item["id"])
        self._controls["emoticon_theme"] = emoticon_theme
        form.addRow(tr("prefs_emoticon_theme"), emoticon_theme)
        self._emoticon_preview = QtWidgets.QHBoxLayout()
        preview_widget = QtWidgets.QWidget()
        preview_widget.setLayout(self._emoticon_preview)
        form.addRow(tr("prefs_emoticon_preview"), preview_widget)
        emoticon_theme.currentIndexChanged.connect(self._update_emoticon_preview)
        self._update_emoticon_preview()
        return page

    def _update_emoticon_preview(self):
        while self._emoticon_preview.count():
            item = self._emoticon_preview.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        skin = self._controls["emoticon_theme"].currentData()
        for code, path in emoticons.preview_items(skin, 10):
            label = QtWidgets.QLabel()
            label.setToolTip(code)
            label.setPixmap(QtGui.QPixmap(path).scaled(
                24, 24, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation))
            self._emoticon_preview.addWidget(label)
        self._emoticon_preview.addStretch()

    def _disabled_combo(self, key: str) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        combo.addItem(tr("prefs_not_implemented"))
        combo.setEnabled(False)
        self._controls[key] = combo
        return combo

    def _page_plugins(self):
        page, form = self._page()
        label = QtWidgets.QLabel(tr("prefs_no_plugins"))
        label.setWordWrap(True)
        form.addRow(label)
        return page

    def _page_notifications(self):
        sounds, sound_form = self._page()
        for key in ("sound_any_message", "sound_first_message", "sound_login",
                    "sound_file_transfer"):
            sound_form.addRow(self._check(key, tr(f"prefs_{key}"), False))

        osd, osd_form = self._page()
        osd_form.addRow(self._check("osd_enabled", tr("prefs_osd_enabled")))
        osd_form.addRow(tr("prefs_osd_duration"),
                        self._spin("osd_duration", 1, 60))
        osd_form.addRow(tr("prefs_osd_max"), self._spin("osd_max", 1, 10))
        osd_form.addRow(self._check("osd_message", tr("prefs_osd_message")))
        osd_form.addRow(self._check("osd_file", tr("prefs_osd_file")))
        osd_form.addRow(self._check("osd_typing", tr("prefs_osd_typing")))
        osd_form.addRow(tr("prefs_osd_status"),
                        self._combo("osd_status", [
                            ("osd_status_never", "never"),
                            ("osd_status_available", "available"),
                            ("osd_status_any", "any"),
                        ]))
        osd_form.addRow(tr("prefs_osd_conference"),
                        self._combo("osd_conference", [
                            ("osd_conf_never", "never"),
                            ("osd_conf_mention", "mention"),
                            ("osd_conf_all", "all"),
                        ]))
        osd_form.addRow(self._check("osd_topdown", tr("prefs_osd_topdown")))

        tray, tray_form = self._page()
        tray_form.addRow(self._check("tray_blink", tr("prefs_tray_blink")))
        tray_form.addRow(self._check("popups", tr("prefs_popups")))
        tabs = self._tabs([(tr("prefs_sounds"), sounds),
                           (tr("prefs_osd"), osd),
                           (tr("prefs_tray"), tray)])
        self._osd_tab_index = 1
        tabs.currentChanged.connect(self._on_notifications_tab_changed)
        return tabs

    def _on_notifications_tab_changed(self, index: int):
        if self._osd_manager is None:
            return
        if index == self._osd_tab_index:
            self._osd_manager.show_preview()
        else:
            self._osd_manager.hide_preview()

    def _page_status(self):
        page, form = self._page()
        away = self._check("auto_away", tr("prefs_auto_away"))
        form.addRow(away)
        form.addRow(tr("prefs_away_minutes"), self._spin("away_minutes", 1, 1440))
        xa = self._check("auto_xa", tr("prefs_auto_xa"))
        form.addRow(xa)
        form.addRow(tr("prefs_xa_minutes"), self._spin("xa_minutes", 1, 1440))
        return page

    def _page_shortcuts(self):
        page, form = self._page()
        label = QtWidgets.QLabel(tr("prefs_shortcuts_list"))
        label.setWordWrap(True)
        form.addRow(label)
        return page

    def _value(self, key: str, default=None):
        widget = self._controls[key]
        if isinstance(widget, QtWidgets.QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QtWidgets.QSpinBox):
            return widget.value()
        if isinstance(widget, QtWidgets.QComboBox):
            return widget.currentData()
        return widget.text()

    def _set(self, key: str, value):
        widget = self._controls[key]
        if isinstance(widget, QtWidgets.QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QtWidgets.QSpinBox):
            widget.setValue(int(value or 0))
        elif isinstance(widget, QtWidgets.QComboBox):
            index = widget.findData(value)
            widget.setCurrentIndex(index if index >= 0 else 0)
        else:
            widget.setText(str(value or ""))

    def _load_values(self):
        cfg = self._config
        app = cfg.application
        connection = cfg.connection
        chat = cfg.chat
        privacy = cfg.privacy
        appearance = cfg.appearance
        notifications = cfg.notifications
        status = cfg.status
        values = {
            "close_to_tray": cfg.ui.close_to_tray,
            "history_limit": app.history_limit or chat.history_limit,
            "history_limit_chat": chat.history_limit,
            "tab_title_length": app.tab_title_length or chat.tab_title_length,
            "tab_title_length_chat": chat.tab_title_length,
            "jid": cfg.jid, "password": cfg.password, "save_password": cfg.save_password,
            "auto_connect": cfg.auto_connect,
            "auto_join_conferences": connection.auto_join_conferences,
            "message_carbons": connection.message_carbons,
            "save_status_message": connection.save_status_message,
            "resource": connection.resource, "override_host": connection.override_host,
            "host": connection.host, "port": connection.port,
            "proxy_host": connection.proxy_host, "proxy_port": connection.proxy_port,
            "send_ctrl_enter": chat.send_ctrl_enter, "show_status": chat.show_status,
            "show_receipts": chat.show_receipts, "show_mood": chat.show_mood,
            "show_music": chat.show_music, "show_avatars": chat.show_avatars,
            "message_styling": chat.message_styling,
            "muc_show_presence": chat.muc_show_presence,
            "muc_show_status": chat.muc_show_status,
            "muc_show_status_text": chat.muc_show_status_text,
            "muc_auto_nick": chat.muc_auto_nick,
            "muc_confirm_leave": chat.muc_confirm_leave,
            "muc_minimize_startup": chat.muc_minimize_startup,
            "send_software": privacy.send_software,
            "send_typing_notifications": getattr(privacy, "send_typing_notifications", privacy.send_chatstates),
            "send_activity_notifications": getattr(privacy, "send_activity_notifications", privacy.send_chatstates),
            "chat_theme": appearance.chat_theme or chat.theme,
            "muc_theme": appearance.muc_theme,
            "emoticon_theme": ("default/smileys.cfg"
                               if appearance.emoticon_theme == "default"
                               else appearance.emoticon_theme),
            "tray_blink": notifications.tray_blink, "popups": notifications.popups,
            "osd_enabled": notifications.osd_enabled,
            "osd_duration": notifications.osd_duration,
            "osd_max": notifications.osd_max,
            "osd_message": notifications.osd_message,
            "osd_file": notifications.osd_file,
            "osd_typing": notifications.osd_typing,
            "osd_status": notifications.osd_status,
            "osd_conference": notifications.osd_conference,
            "osd_topdown": notifications.osd_topdown,
            "auto_away": status.auto_away, "away_minutes": status.away_minutes,
            "auto_xa": status.auto_xa, "xa_minutes": status.xa_minutes,
        }
        for key in ("sound_any_message", "sound_first_message", "sound_login", "sound_file_transfer"):
            values[key] = getattr(notifications, key)
        for key, value in values.items():
            if key in self._controls:
                self._set(key, value)

    def _on_ok(self):
        self._apply_settings()
        self.accept()

    def _apply_settings(self):
        cfg = self._config
        cfg.ui.close_to_tray = self._value("close_to_tray")
        cfg.application.close_to_tray = self._value("close_to_tray")
        cfg.application.history_limit = self._value("history_limit_chat")
        cfg.application.tab_title_length = self._value("tab_title_length_chat")
        cfg.chat.history_limit = self._value("history_limit_chat")
        cfg.chat.tab_title_length = self._value("tab_title_length_chat")
        cfg.jid = self._value("jid")
        cfg.save_password = self._value("save_password")
        cfg.password = self._value("password") if cfg.save_password else ""
        cfg.auto_connect = self._value("auto_connect")
        cfg.connection.auto_join_conferences = self._value("auto_join_conferences")
        cfg.connection.save_status_message = self._value("save_status_message")
        for key in ("resource", "host", "proxy_host"):
            cfg.connection[key] = self._value(key)
        cfg.connection.message_carbons = self._value("message_carbons")
        for key in ("override_host", "port", "proxy_port"):
            cfg.connection[key] = self._value(key)
        for key in ("send_ctrl_enter", "show_status", "show_receipts", "show_mood",
                    "show_music", "show_avatars", "message_styling",
                    "muc_show_presence",
                    "muc_show_status", "muc_show_status_text",
                    "muc_auto_nick", "muc_confirm_leave",
                    "muc_minimize_startup"):
            cfg.chat[key] = self._value(key)
        cfg.chat.theme = self._value("chat_theme") or ""
        cfg.appearance.chat_theme = cfg.chat.theme
        cfg.appearance.muc_theme = self._value("muc_theme") or ""
        cfg.appearance.emoticon_theme = self._value("emoticon_theme") or "default/smileys.cfg"
        cfg.privacy.send_software = self._value("send_software")
        cfg.privacy.send_typing_notifications = self._value("send_typing_notifications")
        cfg.privacy.send_activity_notifications = self._value("send_activity_notifications")
        cfg.privacy.send_chatstates = (cfg.privacy.send_typing_notifications
                                       or cfg.privacy.send_activity_notifications)
        cfg.notifications.tray_blink = self._value("tray_blink")
        cfg.notifications.popups = self._value("popups")
        cfg.notifications.osd_enabled = self._value("osd_enabled")
        for key in ("osd_duration", "osd_max", "osd_message", "osd_file",
                    "osd_typing", "osd_status", "osd_conference",
                    "osd_topdown"):
            cfg.notifications[key] = self._value(key)
        for key in ("sound_any_message", "sound_first_message", "sound_login", "sound_file_transfer"):
            cfg.notifications[key] = self._value(key)
        for key in ("auto_away", "away_minutes", "auto_xa", "xa_minutes"):
            cfg.status[key] = self._value(key)
        cfg.save()
        self.settings_applied.emit()
