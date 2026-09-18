"""Preferences dialog with icon navigation and section tabs."""
from __future__ import annotations

import asyncio
import os

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.core.storage import Config
from stanza_im.core.discovery import DiscoveryCache, HAS_AIODNS
from stanza_im.i18n import tr
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui import icons as icons_mod
from stanza_im.ui.certificate_dialog import CertificateDialog, certificate_lines
from stanza_im.include import emoticons
from stanza_im.include.constants import ACTIONS_DIR_16

CONNECTION_FIELD_WIDTH = 300


def _default_download_dir() -> str:
    """Default directory for received files (XDG Downloads or ~/Downloads)."""
    try:
        location = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.DownloadLocation)
        if location:
            return location
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


def link_status_minutes(away: QtWidgets.QSpinBox, xa: QtWidgets.QSpinBox) -> None:
    """Keep the xa auto-status minutes strictly above the away minutes.

    Both spinners stay in the 1..1440 range; because xa must be greater than
    away, away is capped at 1439 (so xa can reach 1440).
    """

    def clamp_away(value: int) -> None:
        lo = value + 1
        if lo > xa.maximum():
            away.setValue(xa.maximum() - 1)
            return
        xa.setMinimum(lo)
        if xa.value() < lo:
            xa.setValue(lo)

    def clamp_xa(value: int) -> None:
        lo = away.value() + 1
        if xa.minimum() < lo:
            xa.setMinimum(lo)
        if value < lo:
            xa.setValue(lo)

    away.valueChanged.connect(clamp_away)
    xa.valueChanged.connect(clamp_xa)
    clamp_away(away.value())
    clamp_xa(xa.value())


class _SnapSlider(QtWidgets.QSlider):
    """Slider that snaps user drags/clicks to a value grid.

    Programmatic ``setValue`` calls (settings load, live zoom sync) are left
    untouched so the indicator shows the exact current scale; only real user
    interactions snap to the nearest multiple of ``grid``.
    """

    def __init__(self, *args, grid: int = 10, **kwargs):
        super().__init__(*args, **kwargs)
        self._grid = grid

    def _snap(self, value: int) -> int:
        return int(round(value / self._grid)) * self._grid

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.setValue(self._snap(self.value()))

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)
        if self.value() % self._grid:
            self.setValue(self._snap(self.value()))


class _ColorButton(QtWidgets.QPushButton):
    """A color picker button showing a swatch next to the hex value.

    Registered in ``self._controls`` under the config key; ``_value``/``_set``
    dispatch on this class instead of falling through to ``widget.text()``.
    """

    def __init__(self, default: str = "#000000", parent=None):
        super().__init__(parent)
        self._color = default
        self.clicked.connect(self._pick)
        self.set_color(default)

    def color(self) -> str:
        """Return the currently stored hex color (``#rrggbb``)."""
        return self._color

    def set_color(self, value: str) -> None:
        color = QtGui.QColor(str(value))
        if not color.isValid():
            color = QtGui.QColor("#000000")
        self._color = color.name()
        contrast = "#ffffff" if color.lightnessF() < 0.5 else "#000000"
        self.setText(self._color)
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._color}; color: {contrast}; "
            f"border: 1px solid #888; border-radius: 4px; }}")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    def _pick(self):
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(self._color), self)
        if color.isValid():
            self.set_color(color.name())


class PreferencesDialog(QtWidgets.QDialog):
    """Edit application settings grouped like the original Jabbim dialog."""

    settings_applied = QtCore.pyqtSignal()
    password_changed = QtCore.pyqtSignal(str)

    def __init__(self, config: Config, theme_factory: ChatThemeFactory,
                 osd_manager=None, parent=None,
                 client=None):
        super().__init__(parent)
        self._config = config
        self._theme_factory = theme_factory
        self._osd_manager = osd_manager
        self._client = client
        self.setWindowTitle(tr("prefs_title"))
        self.setMinimumSize(760, 540)
        self._controls: dict[str, QtWidgets.QWidget] = {}
        self._build_ui()
        self._load_values()
        self._refresh_discovery_labels()
        self._refresh_connection_info()
        if self._client is not None and hasattr(self._client, "on"):
            self._client.on("services_discovered", self._on_services_discovered)
            self._client.on("connection_info", self._on_connection_info)

    def done(self, result):
        self._stop_device_tests()
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
            ("prefs_devices", "camera-web", self._page_devices),
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

    @staticmethod
    def _default_app_font() -> tuple[str, float]:
        """Resolve the de-facto widget font Qt applies (system default)."""
        font = QtWidgets.QApplication.font()
        size = float(font.pointSizeF() or 0)
        if size <= 0:
            size = 10.0
        return font.family(), size

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
        form.addRow(tr("prefs_tab_title_length"), self._spin("tab_title_length", 10, 120))

        files, file_form = self._page()
        file_form.addRow(self._check("file_auto_accept",
                                     tr("prefs_file_auto_accept")))
        file_form.addRow(self._check("file_download_notifications",
                                     tr("prefs_file_download_notifications")))
        directory = self._line("file_download_dir")
        directory.setMinimumWidth(260)
        browse = QtWidgets.QPushButton(tr("prefs_file_download_dir_browse"))
        browse.clicked.connect(self._pick_download_dir)
        file_form.addRow(tr("prefs_file_download_dir"),
                         self._row(directory, browse))
        return self._tabs([(tr("prefs_general"), general),
                           (tr("prefs_file_transfer"), files)])

    def _pick_download_dir(self):
        current = self._value("file_download_dir") or _default_download_dir()
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, tr("prefs_file_download_dir"), current)
        if path:
            self._set("file_download_dir", path)

    def _page_devices(self):
        """Audio/video device selectors and self-tests (Qt Multimedia)."""
        from stanza_im.xmpp import media
        from stanza_im.ui import device_test
        page, form = self._page()
        devices = media.enumerate_devices()
        self._mic_tester = device_test.MicrophoneTester(self)
        self._mic_tester.level.connect(self._on_mic_level)
        self._mic_tester.failed.connect(self._on_device_test_failed)
        self._mic_tester.running_changed.connect(self._on_mic_running)
        self._speaker_tester = device_test.SpeakerTester(self)
        self._speaker_tester.failed.connect(self._on_device_test_failed)
        self._mic_test_button = None
        self._speaker_test_button = None
        self._camera_test_button = None
        for key, label_key, kind in (
                ("devices_audio_input", "prefs_device_mic", "audio_input"),
                ("devices_audio_output", "prefs_device_speaker", "audio_output"),
                ("devices_video_input", "prefs_device_camera", "video_input")):
            combo = self._combo(key, [("prefs_device_default", "")])
            for dev_id, name in devices.get(kind, []):
                combo.addItem(name or dev_id, dev_id)
            controls = [combo]
            if kind == "audio_input":
                level = QtWidgets.QProgressBar()
                level.setRange(0, 100)
                level.setTextVisible(False)
                level.setMinimumWidth(120)
                self._mic_level = level
                button = QtWidgets.QToolButton()
                button.setCheckable(True)
                button.setAutoRaise(True)
                button.setIcon(self._device_test_icon("mic"))
                button.setIconSize(QtCore.QSize(16, 16))
                button.setToolTip(tr("prefs_device_mic_test_tip"))
                button.toggled.connect(self._on_mic_toggled)
                self._mic_test_button = button
                controls += [level, button]
            elif kind == "audio_output":
                button = QtWidgets.QToolButton()
                button.setAutoRaise(True)
                button.setIcon(self._device_test_icon("speaker"))
                button.setIconSize(QtCore.QSize(16, 16))
                button.setToolTip(tr("prefs_device_speaker_test_tip"))
                button.clicked.connect(self._on_speaker_test)
                self._speaker_test_button = button
                controls.append(button)
            elif kind == "video_input":
                button = QtWidgets.QToolButton()
                button.setAutoRaise(True)
                button.setIcon(self._device_test_icon("camera"))
                button.setIconSize(QtCore.QSize(16, 16))
                button.setToolTip(tr("prefs_device_camera_test_tip"))
                button.clicked.connect(self._on_camera_test)
                self._camera_test_button = button
                controls.append(button)
            form.addRow(tr(label_key), self._row(*controls))
        form.addItem(QtWidgets.QSpacerItem(
            1, 1, QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding))
        self._update_device_tests()
        return page

    def _call_active(self) -> bool:
        rtp = getattr(self._client, "rtp_calls", None)
        return bool(getattr(rtp, "sessions", None))

    def _update_device_tests(self) -> None:
        enabled = not self._call_active()
        for name in ("_mic_test_button", "_speaker_test_button",
                     "_camera_test_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(enabled)

    def _guard_device_test(self) -> bool:
        """False (and warn) while a call owns the devices."""
        if self._call_active():
            QtWidgets.QMessageBox.warning(
                self, tr("prefs_devices"), tr("prefs_device_test_busy"))
            return False
        return True

    def _on_mic_toggled(self, checked: bool) -> None:
        if checked:
            if not self._guard_device_test():
                self._mic_test_button.setChecked(False)
                return
            device_id = self._value("devices_audio_input") or ""
            if not self._mic_tester.start(device_id):
                self._mic_test_button.setChecked(False)
        else:
            self._mic_tester.stop()

    def _on_mic_level(self, value: float) -> None:
        bar = getattr(self, "_mic_level", None)
        if bar is not None:
            bar.setValue(int(max(0.0, min(1.0, value)) * 100.0))

    def _on_mic_running(self, running: bool) -> None:
        button = getattr(self, "_mic_test_button", None)
        if button is not None and button.isChecked() != running:
            button.blockSignals(True)
            button.setChecked(running)
            button.blockSignals(False)

    def _on_speaker_test(self) -> None:
        if not self._guard_device_test():
            return
        self._speaker_tester.play(self._value("devices_audio_output") or "")

    def _on_camera_test(self) -> None:
        if not self._guard_device_test():
            return
        from stanza_im.ui import device_test
        dialog = device_test.CameraPreviewDialog(
            self._value("devices_video_input") or "", self)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.show()

    def _on_device_test_failed(self, message: str) -> None:
        QtWidgets.QMessageBox.warning(
            self, tr("prefs_devices"),
            tr("prefs_device_test_failed", error=message))

    def _stop_device_tests(self) -> None:
        tester = getattr(self, "_mic_tester", None)
        if tester is not None:
            tester.stop()
        speaker = getattr(self, "_speaker_tester", None)
        if speaker is not None:
            speaker.stop()

    @staticmethod
    def _device_test_icon(name: str) -> QtGui.QIcon:
        """16px glyph for the icon-only device self-test buttons."""
        for ext in ("png", "svg"):
            icon = QtGui.QIcon(os.path.join(ACTIONS_DIR_16, f"{name}.{ext}"))
            if not icon.isNull():
                return icon
        return QtGui.QIcon()

    @staticmethod
    def _info_icon() -> QtGui.QIcon:
        """Blue "i" glyph for the information affordances/tooltips."""
        for ext in ("svg", "png"):
            icon = QtGui.QIcon(os.path.join(ACTIONS_DIR_16, f"info.{ext}"))
            if not icon.isNull():
                return icon
        return QtGui.QIcon()

    @staticmethod
    def _change_password_icon() -> QtGui.QIcon:
        """Key glyph for the icon-only "Change password" button."""
        icon = QtGui.QIcon(os.path.join(ACTIONS_DIR_16, "change-password.svg"))
        if not icon.isNull():
            return icon
        if icons_mod.icons is not None:
            return QtGui.QIcon(icons_mod.icons.get_action_icon("edit"))
        return QtGui.QIcon()

    @staticmethod
    def _row(*widgets: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Lay widgets out side by side inside a form field."""
        box = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for widget in widgets:
            layout.addWidget(widget)
        return box

    def _zoom_control(self, key: str) -> QtWidgets.QWidget:
        """Chat text-scale slider (50-300%, step 10%, stored as a factor)."""
        box = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        slider = _SnapSlider(QtCore.Qt.Orientation.Horizontal, grid=10)
        slider.setRange(50, 300)
        slider.setSingleStep(10)
        slider.setPageStep(10)
        slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(50)
        label = QtWidgets.QLabel()
        label.setFixedWidth(48)

        def _update_label(value: int):
            label.setText(f"{value}%")

        slider.valueChanged.connect(_update_label)
        _update_label(slider.value())
        layout.addWidget(slider, stretch=1)
        layout.addWidget(label)
        self._controls[key] = slider
        return box

    def _font_family_combo(self, key: str,
                           default_family: str) -> QtWidgets.QComboBox:
        """Combo of installed font families with a "default" first entry."""
        combo = QtWidgets.QComboBox()
        combo.addItem(tr("prefs_font_default", family=default_family), "")
        for family in QtGui.QFontDatabase.families():
            combo.addItem(family, family)
        self._controls[key] = combo
        return combo

    def _font_row(self, key: str, default_family: str = "",
                  default_size: float = 0) -> QtWidgets.QWidget:
        """A family combo + size spin box (0 points = default).

        When the stored value is empty/0 the controls show the *real* font
        Qt would use instead — ``default_family``/``default_size``.
        """
        combo = self._font_family_combo(key, default_family)
        combo.setMinimumWidth(220)
        size = self._spin(key + "_size", 0, 48)
        size.setValue(0)
        size.setSuffix(tr("prefs_font_pt"))
        if default_size > 0:
            size.setSpecialValueText(
                tr("prefs_font_size_default", size=f"{default_size:g}"))
        return self._row(combo, size)

    def _color_button(self, key: str, default: str = "#000000",
                      tooltip: str = "") -> _ColorButton:
        """A swatch button opening a QColorDialog, stored as ``#rrggbb``."""
        button = _ColorButton(default)
        if tooltip:
            button.setToolTip(tooltip)
        button.setMinimumWidth(120)
        self._controls[key] = button
        return button

    def _page_connection(self):
        connection, form = self._page()

        jid = self._line("jid")
        jid.setFixedWidth(CONNECTION_FIELD_WIDTH)
        form.addRow(tr("login_title"), jid)

        self._btn_change_password = QtWidgets.QPushButton()
        self._btn_change_password.setToolTip(tr("prefs_change_password"))
        self._btn_change_password.setAccessibleName(tr("prefs_change_password"))
        self._btn_change_password.setIcon(self._change_password_icon())
        self._btn_change_password.setIconSize(QtCore.QSize(16, 16))
        self._btn_change_password.setEnabled(self._client is not None)
        self._btn_change_password.clicked.connect(self._on_change_password)

        password = self._line("password", True)
        password.setFixedWidth(CONNECTION_FIELD_WIDTH)
        pw_row = QtWidgets.QWidget()
        pw_layout = QtWidgets.QHBoxLayout(pw_row)
        pw_layout.setContentsMargins(0, 0, 0, 0)
        pw_layout.setSpacing(6)
        pw_layout.addWidget(password)
        pw_layout.addWidget(self._btn_change_password)
        pw_layout.addStretch(1)
        form.addRow(tr("login_password"), pw_row)

        form.addRow(self._check("save_password", tr("prefs_save_password")))
        form.addRow(self._check("auto_connect", tr("prefs_auto_connect")))
        form.addRow(self._check("auto_join_conferences", tr("prefs_auto_join_conferences")))
        form.addRow(self._check("message_carbons", tr("prefs_message_carbons")))
        form.addRow(self._check("save_status_message", tr("prefs_save_status_message")))

        advanced, advanced_form = self._page()
        resource = self._line("resource")
        resource_mode = self._combo("resource_mode", [
            ("prefs_resource_hostname", "hostname"),
            ("prefs_resource_manual", "manual"),
        ])

        def _sync_resource():
            resource.setEnabled(resource_mode.currentData() == "manual")

        resource_mode.currentIndexChanged.connect(_sync_resource)
        _sync_resource()
        advanced_form.addRow(tr("prefs_resource"),
                             self._row(resource, resource_mode))

        priority_mode = self._combo("priority_mode", [
            ("prefs_priority_status", "status"),
            ("prefs_priority_manual", "manual"),
        ])
        priority_value = self._spin("priority", 0, 127)

        def _sync_priority():
            priority_value.setEnabled(priority_mode.currentData() == "manual")

        priority_mode.currentIndexChanged.connect(_sync_priority)
        _sync_priority()
        advanced_form.addRow(tr("prefs_priority"),
                             self._row(priority_mode, priority_value))
        advanced_form.addRow(QtWidgets.QLabel(tr("prefs_reconnect_hint")))

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

        advanced_form.addRow(self._check("keepalive", tr("prefs_keepalive")))
        advanced_form.addRow(self._check(
            "stream_management", tr("prefs_stream_management")))
        advanced_form.addRow(self._check("csi", tr("prefs_csi")))
        csi_keep = self._check(
            "csi_keep_active_for_typing_osd", tr("prefs_csi_keep_active"))
        self._csi_keep_info = QtWidgets.QLabel()
        csi_icon = self._info_icon()
        if not csi_icon.isNull():
            self._csi_keep_info.setPixmap(csi_icon.pixmap(16, 16))
        self._csi_keep_info.setToolTip(tr("prefs_csi_keep_active_tip"))
        advanced_form.addRow(self._row(csi_keep, self._csi_keep_info))
        pep_interval = self._combo("pep_sweep_interval", [
            ("prefs_pep_sweep_off", 0),
            ("prefs_pep_sweep_30", 30),
            ("prefs_pep_sweep_60", 60),
            ("prefs_pep_sweep_120", 120),
            ("prefs_pep_sweep_300", 300),
        ])
        advanced_form.addRow(tr("prefs_pep_sweep"), pep_interval)
        tls_mode = self._combo("tls_mode", [
            ("conn_mode_direct", "direct"),
            ("conn_mode_prefer", "prefer"),
            ("conn_mode_normal", "normal"),
        ])
        starttls_mode = self._combo("starttls_mode", [
            ("enc_always", "always"),
            ("enc_opportunistic", "opportunistic"),
            ("enc_never", "never"),
        ])

        def _sync_tls():
            starttls_mode.setEnabled(tls_mode.currentData() != "direct")

        tls_mode.currentIndexChanged.connect(_sync_tls)
        _sync_tls()
        advanced_form.addRow(tr("prefs_connection_mode"), tls_mode)

        self._conn_info = QtWidgets.QLabel()
        info_icon = self._info_icon()
        if not info_icon.isNull():
            self._conn_info.setPixmap(info_icon.pixmap(16, 16))
        self._conn_info.setToolTip(tr("conn_info_not_connected"))
        advanced_form.addRow(tr("prefs_encryption"),
                             self._row(starttls_mode, self._conn_info))

        self._cert_data: dict = {}
        self._conn_host = ""
        self._cert_btn = QtWidgets.QToolButton()
        if not info_icon.isNull():
            self._cert_btn.setIcon(info_icon)
        self._cert_btn.setIconSize(QtCore.QSize(16, 16))
        self._cert_btn.setAutoRaise(True)
        self._cert_btn.setEnabled(False)
        self._cert_btn.setToolTip(tr("conn_info_cert_none"))
        self._cert_btn.clicked.connect(self._on_show_certificate)
        advanced_form.addRow(tr("conn_info_cert"), self._cert_btn)

        proxy, proxy_form = self._page()
        proxy_form.addRow(self._connection_group())
        proxy_form.addRow(self._file_proxy_group())
        proxy_form.addRow(self._stun_turn_group())
        can_refresh = (self._client is not None
                       and hasattr(self._client, "refresh_services"))
        self._btn_discovery_refresh = QtWidgets.QPushButton(
            tr("prefs_discovery_refresh"))
        refresh_icon = QtGui.QIcon(os.path.join(ACTIONS_DIR_16, "reload.png"))
        if not refresh_icon.isNull():
            self._btn_discovery_refresh.setIcon(refresh_icon)
        self._btn_discovery_refresh.setEnabled(can_refresh)
        self._btn_discovery_refresh.clicked.connect(self._on_refresh_discovery)
        proxy_form.addRow(self._btn_discovery_refresh)
        proxy_form.addRow(QtWidgets.QLabel(tr("prefs_reconnect_hint")))
        return self._tabs([(tr("prefs_connection_tab"), connection),
                           (tr("prefs_advanced"), advanced),
                           (tr("prefs_proxy"), proxy)])

    def _connection_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox(tr("prefs_section_connection"))
        form = QtWidgets.QFormLayout(group)
        proxy_mode = self._combo("proxy_mode", [
            ("prefs_proxy_none", "none"),
            ("prefs_proxy_socks5", "socks5"),
        ])
        form.addRow(tr("prefs_proxy_type"), proxy_mode)
        proxy_host = self._line("proxy_host")
        proxy_port = self._spin("proxy_port", 0, 65535)
        form.addRow(tr("prefs_host"), proxy_host)
        form.addRow(tr("prefs_port"), proxy_port)

        def _sync_proxy():
            enabled = proxy_mode.currentData() == "socks5"
            proxy_host.setEnabled(enabled)
            proxy_port.setEnabled(enabled)

        proxy_mode.currentIndexChanged.connect(_sync_proxy)
        _sync_proxy()
        return group

    def _file_proxy_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox(tr("prefs_file_proxy"))
        form = QtWidgets.QFormLayout(group)
        mode = self._combo("file_proxy_mode", [
            ("prefs_file_proxy_auto", "auto"),
            ("prefs_file_proxy_manual", "manual"),
        ])
        self._file_proxy_auto_label = QtWidgets.QLabel("")
        form.addRow(self._row(mode, self._file_proxy_auto_label))
        manual = self._line("file_proxy_manual")
        manual.setPlaceholderText(tr("prefs_file_proxy_manual_hint"))
        form.addRow("", manual)

        def _sync_file():
            manual.setEnabled(mode.currentData() == "manual")

        mode.currentIndexChanged.connect(_sync_file)
        _sync_file()
        return group

    def _stun_turn_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox(tr("prefs_stun_turn"))
        form = QtWidgets.QFormLayout(group)
        mode = self._combo("stun_turn_mode", [
            ("prefs_stun_auto", "auto"),
            ("prefs_stun_manual", "manual"),
        ])
        self._stun_info = QtWidgets.QLabel()
        info_icon = self._info_icon()
        if not info_icon.isNull():
            self._stun_info.setPixmap(info_icon.pixmap(16, 16))
        self._stun_info.setToolTip(tr("prefs_stun_tip_empty"))
        form.addRow(self._row(mode, self._stun_info))
        manual = self._line("stun_turn_manual")
        manual.setPlaceholderText(tr("prefs_stun_manual_hint"))
        form.addRow("", manual)

        def _sync_stun():
            manual.setEnabled(mode.currentData() == "manual")

        mode.currentIndexChanged.connect(_sync_stun)
        _sync_stun()
        return group

    def _stun_tooltip(self) -> str:
        data = self._discovery_data()
        entries = (data or {}).get("stun_turn") or []
        lines = [tr("prefs_stun_tip") + ":"]
        if entries:
            for entry in entries:
                lines.append("  %s %s:%s" % (entry.get("service", ""),
                                             entry.get("host", ""),
                                             entry.get("port", "")))
        else:
            lines.append("  " + tr("prefs_stun_tip_empty"))
        if not HAS_AIODNS:
            lines.append(tr("prefs_stun_tip_nodep"))
        return "\n".join(lines)

    def _discovery_data(self) -> dict:
        """Auto-detected services from the live client or the disk cache."""
        data = None
        if self._client is not None:
            getter = getattr(self._client, "discovered_services", None)
            if callable(getter):
                data = getter()
        if not data:
            cache = DiscoveryCache()
            _, proxy = cache.get("file_proxy", max_age=float("inf"),
                                 negative_max_age=float("inf"))
            _, stun = cache.get("stun_turn", max_age=float("inf"),
                                negative_max_age=float("inf"))
            data = {"file_proxy": proxy, "stun_turn": stun}
        return data

    def _refresh_discovery_labels(self):
        label = getattr(self, "_file_proxy_auto_label", None)
        if label is None:
            return
        proxy = (self._discovery_data() or {}).get("file_proxy")
        if isinstance(proxy, dict) and proxy.get("host"):
            value = f"{proxy['host']}:{proxy['port']}"
        else:
            value = tr("prefs_file_proxy_none")
        label.setText(tr("prefs_file_proxy_auto_fmt", value=value))
        if hasattr(self, "_stun_info"):
            self._stun_info.setToolTip(self._stun_tooltip())

    def _on_services_discovered(self, *_args):
        self._refresh_discovery_labels()

    def _refresh_connection_info(self):
        label = getattr(self, "_conn_info", None)
        if label is None:
            return
        info = None
        if self._client is not None:
            getter = getattr(self._client, "connection_info", None)
            if callable(getter):
                try:
                    info = getter()
                except Exception:
                    info = None
        if not info or not info.get("sasl"):
            self._set_certificate(info)
            label.setToolTip(tr("conn_info_not_connected"))
            return
        self._set_certificate(info)
        mode_key = {"direct": "conn_info_direct",
                    "starttls": "conn_info_starttls",
                    "plain": "conn_info_plain"}.get(info.get("mode"),
                                                    "conn_info_plain")
        lines = [tr("conn_info_title") + ":"]
        lines.append("  %s: %s" % (tr("conn_info_mode"), tr(mode_key)))
        if info.get("tls_version"):
            lines.append("  %s: %s" % (tr("conn_info_tls_version"),
                                       info["tls_version"]))
        if info.get("cipher"):
            lines.append("  %s: %s" % (tr("conn_info_cipher"),
                                       info["cipher"]))
        lines.append("  %s: %s" % (tr("conn_info_sasl"), info.get("sasl", "")))
        lines.append("  %s: %s" % (
            tr("conn_info_keepalive"),
            tr("conn_info_on") if info.get("keepalive") else tr("conn_info_off")))
        if info.get("sm"):
            lines.append("  %s: %s" % (tr("conn_info_sm"),
                                       tr("sm_state_" + info["sm"])))
        if info.get("csi"):
            lines.append("  %s: %s" % (tr("conn_info_csi"),
                                       tr("csi_state_" + info["csi"])))
        if info.get("host"):
            lines.append("  %s: %s:%s" % (tr("conn_info_server"),
                                          info["host"], info.get("port", "")))
        label.setToolTip("\n".join(lines))

    def _set_certificate(self, info) -> None:
        """Cache the peer certificate and update the certificate info icon."""
        button = getattr(self, "_cert_btn", None)
        cert = (info or {}).get("cert") or {}
        self._cert_data = cert
        self._conn_host = (info or {}).get("host", "") or ""
        if button is None:
            return
        if cert.get("available"):
            button.setToolTip("\n".join(certificate_lines(cert)))
            button.setEnabled(True)
        else:
            button.setToolTip(tr("conn_info_cert_none"))
            button.setEnabled(False)

    def _on_show_certificate(self) -> None:
        if not self._cert_data or not self._cert_data.get("available"):
            return
        dialog = CertificateDialog(self._conn_host, self._cert_data, self)
        dialog.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.show()

    def _on_connection_info(self, *_args):
        self._refresh_connection_info()

    def _on_refresh_discovery(self):
        if self._client is None or not hasattr(self._client, "refresh_services"):
            return
        self._btn_discovery_refresh.setEnabled(False)
        self._btn_discovery_refresh.setText(tr("prefs_discovery_refreshing"))
        asyncio.create_task(self._run_refresh_discovery())

    async def _run_refresh_discovery(self):
        try:
            await self._client.refresh_services()
        except Exception:
            pass
        finally:
            self._btn_discovery_refresh.setText(tr("prefs_discovery_refresh"))
            self._btn_discovery_refresh.setEnabled(
                self._client is not None
                and hasattr(self._client, "refresh_services"))

    def _page_chat(self):
        general, general_form = self._page()
        general_form.addRow(self._check("send_ctrl_enter", tr("prefs_send_ctrl_enter")))
        general_form.addRow(self._check("message_displayed_sync",
                                        tr("prefs_message_displayed_sync")))
        general_form.addRow(self._check("allow_incoming_edits",
                                        tr("prefs_allow_incoming_edits")))
        general_form.addRow(tr("prefs_media_preview"),
                            self._combo("media_preview", [
                                ("media_preview_none", "none"),
                                ("media_preview_images", "images"),
                                ("media_preview_images_audio", "images_audio"),
                                ("media_preview_all", "all"),
                            ]))
        general_form.addRow(tr("prefs_idle_unload_minutes"),
                            self._spin("idle_unload_minutes", 0, 240))
        general_form.addRow(tr("prefs_history_limit"),
                            self._spin("history_limit_chat", 10, 1000))

        chat, chat_form = self._page()
        chat_form.addRow(self._check("show_status", tr("prefs_show_status")))
        chat_form.addRow(self._check("show_receipts", tr("prefs_show_receipts")))
        chat_form.addRow(self._check("show_mood", tr("prefs_show_mood"), False))
        chat_form.addRow(self._check("show_music", tr("prefs_show_music"), False))
        chat_form.addRow(self._check("show_avatars", tr("prefs_show_avatars")))
        chat_form.addRow(self._check("message_styling",
                                     tr("prefs_message_styling")))
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
        themes, form = self._page()
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

        roster, roster_form = self._page()
        roster_form.addRow(self._check("roster_show_avatars",
                                       tr("prefs_roster_show_avatars")))
        roster_form.addRow(self._check("roster_show_activity",
                                       tr("prefs_roster_show_activity")))
        roster_form.addRow(self._check("roster_show_mood",
                                       tr("prefs_roster_show_mood")))

        fonts, font_form = self._page()
        font_form.addRow(tr("prefs_zoom"), self._zoom_control("text_scale"))
        default_family, default_size = self._default_app_font()
        font_form.addRow(tr("prefs_font_roster"),
                         self._font_row("roster_font", default_family, default_size))
        font_form.addRow(tr("prefs_font_chat"),
                         self._font_row("chat_font", default_family, default_size))
        font_form.addRow(tr("prefs_font_nicks"),
                         self._font_row("nick_font", default_family, default_size))
        font_form.addRow(tr("prefs_font_participants"),
                         self._font_row("participant_font", default_family,
                                        default_size))
        font_form.addRow(tr("prefs_font_osd"),
                         self._font_row("osd_font", default_family, default_size))

        # The nickname "default" follows the chat font (a real value picks
        # the chat family/size; an empty one falls through to the system
        # font), so its default label tracks the chat row live.
        def _sync_nick_default():
            nick_combo = self._controls["nick_font"]
            family = self._controls["chat_font"].currentData() or default_family
            size = (self._controls["chat_font_size"].value()
                    or default_size)
            nick_combo.setItemText(
                0, tr("prefs_font_default", family=family))
            self._controls["nick_font_size"].setSpecialValueText(
                tr("prefs_font_size_default", size=f"{size:g}"))

        self._controls["chat_font"].currentIndexChanged.connect(
            _sync_nick_default)
        self._controls["chat_font_size"].valueChanged.connect(
            _sync_nick_default)
        _sync_nick_default()

        colors, color_form = self._page()
        color_form.addRow(tr("prefs_color_roster_bg"),
                          self._color_button("roster_bg_color", "#ffffff"))
        color_form.addRow(tr("prefs_color_group_bg"),
                          self._color_button("roster_group_bg_color", "#ececec"))
        color_form.addRow(tr("prefs_color_chat_bg"),
                          self._color_button("chat_bg_color", "#ffffff"))
        color_form.addRow(tr("prefs_color_highlight"),
                          self._color_button("muc_highlight_color", "#e53935"))
        color_form.addRow(
            self._check("colored_muc_nicks", tr("prefs_color_muc_nicks")))
        color_form.addRow(tr("prefs_color_osd_bg"),
                          self._color_button("osd_bg_color", "#282828"))
        color_form.addRow(tr("prefs_color_osd_font"),
                          self._color_button("osd_font_color", "#ffffff"))
        osd_opacity = self._spin("osd_opacity", 0, 100)
        osd_opacity.setSuffix(" %")
        color_form.addRow(tr("prefs_color_osd_opacity"), osd_opacity)

        misc, misc_form = self._page()
        misc_form.addRow(tr("prefs_media_preview_size"),
                         self._spin("media_preview_size", 64, 512))
        misc_form.addRow(tr("prefs_media_cache_days"),
                         self._spin("media_cache_days", 1, 3650))
        misc_form.addRow(tr("prefs_media_cache_mb"),
                         self._spin("media_cache_mb", 16, 4096))
        misc_form.addRow(tr("prefs_highlight"), self._combo("muc_highlight", [
            ("prefs_highlight_bold", "bold"),
            ("prefs_highlight_color", "color"),
            ("prefs_highlight_both", "both"),
        ]))
        misc_form.addRow(tr("prefs_interface_mode"),
                         self._combo("interface_mode", [
                             ("prefs_interface_separate", "separate"),
                             ("prefs_interface_unified", "unified"),
                         ]))

        return self._tabs([(tr("prefs_appearance_themes"), themes),
                           (tr("prefs_appearance_roster"), roster),
                           (tr("prefs_appearance_fonts"), fonts),
                           (tr("prefs_color_tab"), colors),
                           (tr("prefs_appearance_misc"), misc)])

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
        away_spin = self._spin("away_minutes", 1, 1440)
        form.addRow(tr("prefs_away_minutes"), away_spin)
        xa = self._check("auto_xa", tr("prefs_auto_xa"))
        form.addRow(xa)
        xa_spin = self._spin("xa_minutes", 1, 1440)
        form.addRow(tr("prefs_xa_minutes"), xa_spin)
        link_status_minutes(away_spin, xa_spin)
        status_message = QtWidgets.QPlainTextEdit()
        status_message.setMaximumHeight(70)
        status_message.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed)
        status_message.setPlaceholderText(tr("prefs_auto_status_message_placeholder"))
        self._controls["auto_status_message"] = status_message
        form.addRow(tr("prefs_auto_status_message"), status_message)
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
        if isinstance(widget, QtWidgets.QSlider):
            return widget.value() / 100.0
        if isinstance(widget, QtWidgets.QComboBox):
            return widget.currentData()
        if isinstance(widget, QtWidgets.QPlainTextEdit):
            return widget.toPlainText()
        if isinstance(widget, _ColorButton):
            return widget.color()
        return widget.text()

    def _set(self, key: str, value):
        widget = self._controls[key]
        if isinstance(widget, QtWidgets.QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QtWidgets.QSpinBox):
            widget.setValue(int(value or 0))
        elif isinstance(widget, QtWidgets.QSlider):
            widget.setValue(int(round((float(value or 1.0)) * 100)))
        elif isinstance(widget, QtWidgets.QComboBox):
            index = widget.findData(value)
            widget.setCurrentIndex(index if index >= 0 else 0)
        elif isinstance(widget, QtWidgets.QPlainTextEdit):
            widget.setPlainText(str(value or ""))
        elif isinstance(widget, _ColorButton):
            widget.set_color(str(value or ""))
        else:
            widget.setText(str(value or ""))

    def sync_scale(self, factor: float) -> None:
        """Reflect a scale changed live (e.g. Ctrl+wheel) into the slider."""
        if "text_scale" in self._controls:
            self._set("text_scale", factor)

    def _load_values(self):
        cfg = self._config
        app = cfg.application
        connection = cfg.connection
        chat = cfg.chat
        privacy = cfg.privacy
        appearance = cfg.appearance
        notifications = cfg.notifications
        status = cfg.status
        files = getattr(cfg, "files", None)
        values = {
            "close_to_tray": cfg.ui.close_to_tray,
            "history_limit_chat": chat.history_limit,
            "tab_title_length": app.tab_title_length or chat.tab_title_length,
            "tab_title_length_chat": chat.tab_title_length,
            "jid": cfg.jid, "password": cfg.password, "save_password": cfg.save_password,
            "auto_connect": cfg.auto_connect,
            "auto_join_conferences": connection.auto_join_conferences,
            "message_carbons": connection.message_carbons,
            "save_status_message": connection.save_status_message,
            "resource": connection.resource, "override_host": connection.override_host,
            "resource_mode": getattr(connection, "resource_mode", "hostname"),
            "priority_mode": getattr(connection, "priority_mode", "status"),
            "priority": getattr(connection, "priority", 50),
            "proxy_mode": getattr(connection, "proxy_mode", "none"),
            "file_proxy_mode": getattr(connection, "file_proxy_mode", "auto"),
            "file_proxy_manual": getattr(connection, "file_proxy_manual", ""),
            "stun_turn_mode": getattr(connection, "stun_turn_mode", "auto"),
            "stun_turn_manual": getattr(connection, "stun_turn_manual", ""),
            "keepalive": getattr(connection, "keepalive", True),
            "pep_sweep_interval": getattr(connection, "pep_sweep_interval", 0),
            "stream_management": getattr(connection, "stream_management", True),
            "csi": getattr(connection, "csi", True),
            "csi_keep_active_for_typing_osd": getattr(
                connection, "csi_keep_active_for_typing_osd", False),
            "tls_mode": getattr(connection, "tls_mode", "prefer"),
            "starttls_mode": getattr(connection, "starttls_mode", "always"),
            "host": connection.host, "port": connection.port,
            "proxy_host": connection.proxy_host, "proxy_port": connection.proxy_port,
            "send_ctrl_enter": chat.send_ctrl_enter, "show_status": chat.show_status,
            "message_displayed_sync": chat.message_displayed_sync,
            "allow_incoming_edits": chat.allow_incoming_edits,
            "show_receipts": chat.show_receipts, "show_mood": chat.show_mood,
            "show_music": chat.show_music, "show_avatars": chat.show_avatars,
            "message_styling": chat.message_styling,
            "media_preview": chat.media_preview,
            "idle_unload_minutes": int(getattr(chat, "idle_unload_minutes", 10) or 0),
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
            "media_preview_size": appearance.media_preview_size,
            "media_cache_days": appearance.media_cache_days,
            "media_cache_mb": appearance.media_cache_mb,
            "muc_highlight": getattr(appearance, "muc_highlight", "both"),
            "interface_mode": getattr(appearance, "interface_mode", "separate"),
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
            "auto_status_message": getattr(status, "auto_status_message", ""),
            "text_scale": chat.text_scale,
            "roster_font": getattr(appearance, "roster_font", ""),
            "roster_font_size": getattr(appearance, "roster_font_size", 0),
            "chat_font": getattr(appearance, "chat_font", ""),
            "chat_font_size": getattr(appearance, "chat_font_size", 0),
            "osd_font": getattr(appearance, "osd_font", ""),
            "osd_font_size": getattr(appearance, "osd_font_size", 0),
            "osd_bg_color": getattr(appearance, "osd_bg_color", "#282828"),
            "osd_font_color": getattr(appearance, "osd_font_color", "#ffffff"),
            "osd_opacity": getattr(appearance, "osd_opacity", 92),
            "nick_font": getattr(appearance, "nick_font", ""),
            "nick_font_size": getattr(appearance, "nick_font_size", 0),
            "participant_font": getattr(appearance, "participant_font", ""),
            "participant_font_size": getattr(appearance, "participant_font_size", 0),
            "roster_bg_color": getattr(appearance, "roster_bg_color", "#ffffff"),
            "roster_group_bg_color": getattr(appearance, "roster_group_bg_color", "#ececec"),
            "chat_bg_color": getattr(appearance, "chat_bg_color", "#ffffff"),
            "muc_highlight_color": getattr(appearance, "muc_highlight_color", "#e53935"),
            "colored_muc_nicks": getattr(appearance, "colored_muc_nicks", True),
            "roster_show_avatars": getattr(
                appearance, "roster_show_avatars", True),
            "roster_show_activity": getattr(
                appearance, "roster_show_activity", True),
            "roster_show_mood": getattr(appearance, "roster_show_mood", True),
            "file_auto_accept": bool(getattr(files, "auto_accept", False)),
            "file_download_notifications": bool(
                getattr(files, "download_notifications", True)),
            "file_download_dir": getattr(files, "download_dir", "") or "",
            "devices_audio_input": getattr(
                getattr(cfg, "devices", None), "audio_input", "") or "",
            "devices_audio_output": getattr(
                getattr(cfg, "devices", None), "audio_output", "") or "",
            "devices_video_input": getattr(
                getattr(cfg, "devices", None), "video_input", "") or "",
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
        for key in ("resource", "host", "proxy_host", "resource_mode",
                    "priority_mode", "proxy_mode", "file_proxy_mode",
                    "file_proxy_manual", "stun_turn_mode", "stun_turn_manual",
                    "tls_mode", "starttls_mode"):
            cfg.connection[key] = self._value(key)
        cfg.connection.priority = self._value("priority")
        cfg.connection.keepalive = self._value("keepalive")
        cfg.connection.pep_sweep_interval = int(
            self._value("pep_sweep_interval") or 0)
        cfg.connection.stream_management = self._value("stream_management")
        cfg.connection.csi = self._value("csi")
        cfg.connection.csi_keep_active_for_typing_osd = self._value(
            "csi_keep_active_for_typing_osd")
        cfg.connection.message_carbons = self._value("message_carbons")
        for key in ("override_host", "port", "proxy_port"):
            cfg.connection[key] = self._value(key)
        for key in ("send_ctrl_enter", "show_status", "show_receipts", "show_mood",
                    "show_music", "show_avatars", "message_styling",
                    "muc_show_presence",
                    "muc_show_status", "muc_show_status_text",
                    "muc_auto_nick", "muc_confirm_leave",
                    "muc_minimize_startup", "message_displayed_sync",
                    "allow_incoming_edits", "idle_unload_minutes"):
            cfg.chat[key] = self._value(key)
        cfg.chat.theme = self._value("chat_theme") or ""
        cfg.appearance.chat_theme = cfg.chat.theme
        cfg.appearance.muc_theme = self._value("muc_theme") or ""
        cfg.appearance.emoticon_theme = self._value("emoticon_theme") or "default/smileys.cfg"
        cfg.chat.media_preview = self._value("media_preview") or "images"
        cfg.appearance.media_preview_size = self._value("media_preview_size")
        cfg.appearance.media_cache_days = self._value("media_cache_days")
        cfg.appearance.media_cache_mb = self._value("media_cache_mb")
        cfg.appearance.muc_highlight = self._value("muc_highlight") or "both"
        cfg.appearance.interface_mode = self._value("interface_mode") or "separate"
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
        cfg.status.auto_status_message = self._value("auto_status_message")
        cfg.chat.text_scale = self._value("text_scale")
        for key in ("roster_font", "roster_font_size", "chat_font", "chat_font_size",
                    "osd_font", "osd_font_size", "nick_font", "nick_font_size",
                    "participant_font", "participant_font_size",
                    "osd_bg_color", "osd_font_color", "osd_opacity",
                    "roster_bg_color", "roster_group_bg_color", "chat_bg_color",
                    "muc_highlight_color", "colored_muc_nicks",
                    "roster_show_avatars", "roster_show_activity",
                    "roster_show_mood"):
            cfg.appearance[key] = self._value(key)
        if not hasattr(cfg, "files"):
            cfg.set("files", {"auto_accept": False,
                              "download_notifications": True,
                              "download_dir": ""})
        cfg.files.auto_accept = self._value("file_auto_accept")
        cfg.files.download_notifications = self._value(
            "file_download_notifications")
        cfg.files.download_dir = self._value("file_download_dir")
        if not hasattr(cfg, "devices"):
            cfg.set("devices", {"audio_input": "", "audio_output": "",
                                "video_input": ""})
        for key in ("audio_input", "audio_output", "video_input"):
            cfg.devices[key] = self._value("devices_" + key) or ""
        cfg.save()
        self.settings_applied.emit()

    # ── Change account password ──────────────────────────────────────

    def _on_change_password(self):
        if self._client is None:
            return
        from stanza_im.ui.change_password_dialog import ChangePasswordDialog
        dlg = ChangePasswordDialog(self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self._btn_change_password.setEnabled(False)
        asyncio.create_task(self._run_change_password(dlg.password()))

    async def _run_change_password(self, new_password: str):
        result = await self._do_change_password(new_password)
        self._btn_change_password.setEnabled(self._client is not None)
        if result == "ok":
            QtWidgets.QMessageBox.information(
                self, tr("change_password_title"),
                tr("change_password_success"))
        else:
            QtWidgets.QMessageBox.warning(
                self, tr("change_password_title"),
                tr("change_password_error", error=result))

    async def _do_change_password(self, new_password: str) -> str:
        """Submit the new password; return "ok" or an error text."""
        client = self._client
        if client is None:
            return tr("change_password_not_connected")
        try:
            await client.change_password(new_password)
        except Exception as exc:
            return str(exc)
        if self._value("save_password"):
            self._config.password = new_password
            self._config.save()
        self.password_changed.emit(new_password)
        return "ok"
