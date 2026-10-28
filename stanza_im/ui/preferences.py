"""Preferences dialog with icon navigation and section tabs."""
from __future__ import annotations

import asyncio
import os
import textwrap

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.core.storage import Config
from stanza_im.core.discovery import DiscoveryCache, HAS_AIODNS
from stanza_im.i18n import tr
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.dialogs import show_modeless
from stanza_im.ui import icons as icons_mod
from stanza_im.ui.sounds import SoundPlayer
from stanza_im.ui.tray import normalize_popups_mode
from stanza_im.ui.font_zoom import clamp_font_size, wheel_font_size
from stanza_im.include import sounds as sounds_mod
from stanza_im.ui.certificate_dialog import CertificateDialog, certificate_lines
from stanza_im.ui.connection_info_dialog import connection_info_lines
from stanza_im.include import emoticons
from stanza_im.include.constants import find_icon, find_icon_sized

CONNECTION_FIELD_WIDTH = 300
# Uniform widths so numeric selectors and combo boxes line up across pages.
SPIN_WIDTH = 90
COMBO_WIDTH = 260

#: Camera output height presets (0 = keep the source size).
_CAMERA_HEIGHT_PRESETS = (0, 1080, 720, 480, 360)
#: Screen-sharing output boxes (width, height); (0, 0) = the source size.
_SCREEN_PRESETS = ((0, 0), (1920, 1080), (1280, 720), (854, 480))


def _screen_box(width, height) -> tuple[int, int]:
    """Normalise a stored screen box (a legacy width-only value gets 16:9)."""
    width = max(0, int(width or 0))
    height = max(0, int(height or 0))
    if width and not height:
        height = max(2, int(width * 9 / 16))
    return width, height


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


class _PrefsNavList(QtWidgets.QListWidget):
    """The section navigator; Ctrl+wheel scales its text and icons."""

    zoom_requested = QtCore.pyqtSignal(int)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        size = wheel_font_size(self.font(), event)
        if size is not None:
            self.zoom_requested.emit(size)
            event.accept()
            return
        super().wheelEvent(event)


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


class _LazyControls(dict):
    """A control map that builds every page on a missing-key lookup.

    The preferences pages are built lazily, but external callers (and tests)
    may read ``dialog._controls[key]`` for a control on a not-yet-built page;
    that lookup then forces all pages to build so the key is present.
    """

    def __init__(self, owner):
        super().__init__()
        self._owner = owner

    def __getitem__(self, key):
        if key not in self and self._owner is not None:
            self._owner._ensure_all_pages()
        return super().__getitem__(key)

    def __contains__(self, key):
        if not super().__contains__(key) and self._owner is not None:
            self._owner._ensure_all_pages()
        return super().__contains__(key)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if self._owner is not None:
            self._owner._record_control_page(key)


class PreferencesDialog(QtWidgets.QDialog):
    """Edit application settings grouped like the original Jabbim dialog."""

    settings_applied = QtCore.pyqtSignal()
    password_changed = QtCore.pyqtSignal(str)
    register_requested = QtCore.pyqtSignal()
    plugins_applied = QtCore.pyqtSignal(list)  # newly enabled plugin ids

    def __init__(self, config: Config, theme_factory: ChatThemeFactory,
                 osd_manager=None, parent=None,
                 client=None, sound_player=None):
        super().__init__(parent)
        self._config = config
        self._theme_factory = theme_factory
        self._osd_manager = osd_manager
        self._client = client
        self._camera_preview = None
        self._test_monitor = None
        self._sound_player = (sound_player if sound_player is not None
                              else SoundPlayer())
        self.setWindowTitle(tr("prefs_title"))
        self.setMinimumSize(760, 540)
        # Which page each control belongs to (for the «Reset to defaults»
        # button); ``_building_page`` is set by ``_page()`` while a page is
        # being constructed.
        self._control_pages: dict[str, QtWidgets.QWidget] = {}
        self._building_page: QtWidgets.QWidget | None = None
        # Pages are built lazily, so a direct ``controls[key]`` lookup for a
        # not-yet-built page forces every page to build (used by tests/tools);
        # the UI itself only touches built controls.
        self._controls: dict[str, QtWidgets.QWidget] = _LazyControls(self)
        self._build_ui()
        self._load_values()
        self._refresh_discovery_labels()
        self._refresh_connection_info()
        if self._client is not None and hasattr(self._client, "on"):
            self._client.on("services_discovered", self._on_services_discovered)
            self._client.on("connection_info", self._on_connection_info)

    def done(self, result):
        self._stop_device_tests()
        if getattr(self, "_defer_timer", None) is not None:
            self._defer_timer.stop()
        if self._osd_manager is not None:
            self._osd_manager.hide_preview()
        super().done(result)

    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        split = QtWidgets.QHBoxLayout()
        self._sections = _PrefsNavList()
        self._sections.setFixedWidth(190)
        self._sections.setIconSize(QtCore.QSize(24, 24))
        self._sections.setToolTip(tr("prefs_nav_zoom_tip"))
        self._sections.zoom_requested.connect(self._on_nav_zoom)
        self._sections.setStyleSheet(
            "QListWidget { background: white; border: 1px solid #d5d5d5; "
            "padding: 4px; } QListWidget::item { padding: 7px 4px; } "
            "QListWidget::item:selected { color: palette(highlighted-text); "
            "background: palette(highlight); }")
        self._sections.currentRowChanged.connect(self._on_section_changed)
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
        # The «Reset to defaults» button sits away from Ok/Apply/Cancel.
        bottom = QtWidgets.QHBoxLayout()
        self._btn_reset = QtWidgets.QToolButton()
        icon = QtGui.QIcon(find_icon("reset-defaults.svg"))
        if not icon.isNull():
            self._btn_reset.setIcon(icon)
        self._btn_reset.setIconSize(QtCore.QSize(16, 16))
        self._btn_reset.setAutoRaise(True)
        self._btn_reset.setToolTip(tr("prefs_reset_defaults_tip"))
        self._btn_reset.clicked.connect(self._reset_current_page)
        bottom.addWidget(self._btn_reset)
        bottom.addStretch(1)
        bottom.addWidget(buttons)
        outer.addLayout(bottom)

        sections = (
            ("prefs_application", "stanza-im", self._page_application),
            ("prefs_connection", "transports", self._page_connection),
            ("prefs_calls", "devices", self._page_calls),
            ("prefs_chat", "muc", self._page_chat),
            ("prefs_privacy", "privacy", self._page_privacy),
            ("prefs_appearance", "draw-brush", self._page_appearance),
            ("prefs_plugins", "plugins", self._page_plugins),
            ("prefs_notifications", "event", self._page_notifications),
            ("prefs_status", "status", self._page_status),
            ("prefs_shortcuts", "shortcuts", self._page_shortcuts),
        )
        # Build pages lazily: only the first one is created up front (so the
        # dialog opens instantly); the rest are built on first selection and in
        # the background after show.
        self._page_factories: list = []
        self._pages: list = []
        self._section_icon_names: list[str] = []
        for key, icon_name, page_factory in sections:
            self._section_icon_names.append(icon_name)
            icon = QtGui.QIcon()
            if icons_mod.icons:
                pixmap = icons_mod.icons.get_category_icon(icon_name, 24)
                if not pixmap.isNull():
                    icon = QtGui.QIcon(pixmap)
            self._sections.addItem(QtWidgets.QListWidgetItem(icon, tr(key)))
            self._page_factories.append(page_factory)
            self._pages.append(None)
            self._stack.addWidget(QtWidgets.QWidget())  # placeholder
        self._apply_nav_font()
        self._sections.setCurrentRow(0)
        self._ensure_page(0)

    def _category_icon(self, name: str,
                       size: int) -> QtGui.QIcon:
        if icons_mod.icons:
            pixmap = icons_mod.icons.get_category_icon(name, size)
            if not pixmap.isNull():
                return QtGui.QIcon(pixmap)
        # Tests may run without the global IconCache; still resolve and scale
        # the icon for every section.
        app = QtWidgets.QApplication.instance()
        screen = app.primaryScreen() if app is not None else None
        try:
            dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
        except Exception:
            dpr = 1.0
        path = find_icon_sized(name, size, dpr)
        if not path:
            path = find_icon(f"{name}.png")
        if not path:
            return QtGui.QIcon()
        target = max(1, int(round(int(size or 24) * dpr)))
        pixmap = QtGui.QIcon(path).pixmap(target, target)
        if (not pixmap.isNull()
                and (pixmap.width() < target or pixmap.height() < target)):
            pixmap = pixmap.scaled(
                target, target,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
        if dpr != 1.0 and not pixmap.isNull():
            pixmap.setDevicePixelRatio(dpr)
        return QtGui.QIcon(pixmap)

    def _apply_nav_font(self) -> None:
        """Apply the configured section font; icons keep the visual ratio."""
        appearance = self._config.appearance
        family = getattr(appearance, "prefs_nav_font", "") or ""
        try:
            size = int(getattr(appearance, "prefs_nav_font_size", 0) or 0)
        except (TypeError, ValueError):
            size = 0
        app_font = QtWidgets.QApplication.font()
        base = QtGui.QFont(app_font)
        if family:
            base.setFamily(family)
        if size > 0:
            base.setPointSize(size)
        self._sections.setFont(base)
        default_pt = float(app_font.pointSizeF() or 0) or 9.0
        point = float(base.pointSizeF() or 0)
        if point <= 0:
            point = default_pt
        icon_size = max(16, min(64, int(round(24 * point / default_pt))))
        self._sections.setIconSize(QtCore.QSize(icon_size, icon_size))
        metrics = QtGui.QFontMetrics(base)
        longest = 0
        for index, icon_name in enumerate(self._section_icon_names):
            item = self._sections.item(index)
            if item is None:
                continue
            item.setIcon(self._category_icon(icon_name, icon_size))
            item.setFont(base)
            longest = max(longest, metrics.horizontalAdvance(item.text()))
        width = max(190, min(340, icon_size + longest + 44))
        self._sections.setFixedWidth(width)

    def _on_nav_zoom(self, size: int) -> None:
        """Ctrl+wheel over the sections: scale and persist immediately."""
        size = clamp_font_size(size)
        self._config.appearance.prefs_nav_font_size = size
        self._config.save()
        self._apply_nav_font()
        self.sync_font_size("prefs_nav_font", size)

    def _on_section_changed(self, row: int) -> None:
        row = max(0, row)
        self._ensure_page(row)
        self._stack.setCurrentIndex(row)

    def _ensure_page(self, row: int) -> None:
        """Build the page at *row* on first use and load its saved values."""
        if row < 0 or row >= len(self._page_factories):
            return
        if self._pages[row] is not None:
            return
        factory = self._page_factories[row]
        before = set(self._controls)
        page = factory()
        placeholder = self._stack.widget(row)
        self._stack.removeWidget(placeholder)
        if placeholder is not None:
            placeholder.deleteLater()
        self._stack.insertWidget(row, page)
        self._pages[row] = page
        self._apply_values(self._values_dict(), set(self._controls) - before)
        self._refresh_discovery_labels()
        self._refresh_connection_info()

    def _ensure_all_pages(self) -> None:
        for row in range(len(self._page_factories)):
            self._ensure_page(row)

    def _build_pages_deferred(self) -> None:
        """Build any remaining pages one per event-loop turn (keeps UI live)."""
        if not self.isVisible():
            return
        for row in range(len(self._page_factories)):
            if self._pages[row] is None:
                self._ensure_page(row)
                if getattr(self, "_defer_timer", None) is not None:
                    self._defer_timer.start(0)
                return

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if self._test_monitor is None:
            self._test_monitor = QtCore.QTimer(self)
            self._test_monitor.setInterval(1000)
            self._test_monitor.timeout.connect(self._on_test_monitor)
        self._test_monitor.start()
        # After the dialog is visible, warm up the remaining pages in the
        # background so the first switch to any section is instant.  The timer
        # is a child of the dialog so it dies with it (no dangling callback).
        self._defer_timer = QtCore.QTimer(self)
        self._defer_timer.setSingleShot(True)
        self._defer_timer.timeout.connect(self._build_pages_deferred)
        self._defer_timer.start(0)

    def _page(self) -> tuple[QtWidgets.QWidget, QtWidgets.QFormLayout]:
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # Controls created from now on belong to this page (until the next
        # ``_page()`` call).
        self._building_page = page
        return page, form

    def _record_control_page(self, key: str) -> None:
        if self._building_page is not None:
            self._control_pages[key] = self._building_page

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
        widget.setFixedWidth(SPIN_WIDTH)
        self._controls[key] = widget
        return widget

    def _combo(self, key: str, options: list[tuple[str, str]],
               fixed_width: bool = True) -> QtWidgets.QComboBox:
        widget = QtWidgets.QComboBox()
        for label_key, data in options:
            widget.addItem(tr(label_key), data)
        if fixed_width:
            widget.setFixedWidth(COMBO_WIDTH)
        self._controls[key] = widget
        return widget

    def _page_application(self):
        general, form = self._page()
        form.addRow(self._check("close_to_tray", tr("prefs_close_to_tray")))

        from stanza_im.i18n import available_languages
        lang_options = [("prefs_language_default", "")] + [
            (None, code) for code, _name in available_languages()]
        lang = self._combo("language", lang_options)
        # The non-default entries need the native language name, which the
        # ``_combo`` helper (key-based) cannot express; rewrite them here.
        lang.clear()
        lang.addItem(tr("prefs_language_default"), "")
        for code, name in available_languages():
            lang.addItem(name, code)
        form.addRow(self._row(QtWidgets.QLabel(tr("prefs_language")), lang),
                    self._info_label(tr("prefs_language_restart_tip")))

        files, file_form = self._page()
        file_form.addRow(self._check("file_auto_accept",
                                     tr("prefs_file_auto_accept")))
        file_form.addRow(self._check("file_download_notifications",
                                     tr("prefs_file_download_notifications")))
        file_form.addRow(self._check("file_verify_hashes",
                                     tr("prefs_file_verify_hashes")))
        encryption = self._combo("file_encryption", [
            ("prefs_file_encryption_off", "off"),
            ("prefs_file_encryption_prefer", "prefer"),
            ("prefs_file_encryption_require", "require"),
            ("prefs_file_encryption_strict", "strict")], fixed_width=False)
        file_form.addRow(
            tr("prefs_file_encryption"),
            self._row(encryption, self._info_label(
                tr("prefs_file_encryption_tip")), trailing_stretch=True))
        directory = self._line("file_download_dir")
        directory.setMinimumWidth(260)
        browse = QtWidgets.QPushButton(tr("prefs_file_download_dir_browse"))
        browse.clicked.connect(self._pick_download_dir)
        file_form.addRow(tr("prefs_file_download_dir"),
                         self._row(directory, browse))

        # Startup / memory tuning (deferred loads, Chromium flags).  Every row
        # puts its label in the form's label column and the selector in the
        # field column (a shared, fixed width) so the controls line up.
        perf, perf_form = self._page()
        defer = self._check("defer_ui_build", tr("prefs_defer_ui_build"))
        perf_form.addRow(self._row(
            defer, self._info_label(tr("prefs_defer_ui_build_tip")),
            trailing_stretch=True))

        def _select(label_key: str, key: str, options, tip: str):
            combo = self._combo(key, options)
            perf_form.addRow(
                tr(label_key),
                self._row(combo, self._info_label(tip),
                          trailing_stretch=True))
            return combo

        _select("prefs_omemo_load", "omemo_load_mode", [
            ("prefs_load_lazy", "lazy"),
            ("prefs_load_startup", "startup"),
            ("prefs_load_off", "off")], tr("prefs_omemo_load_tip"))
        _select("prefs_calls_load", "calls_load_mode", [
            ("prefs_load_lazy", "lazy"),
            ("prefs_load_startup", "startup"),
            ("prefs_load_off", "off")], tr("prefs_calls_load_tip"))
        _select("prefs_webengine_engine", "webengine_mode", [
            ("webengine_engine_full", "full"),
            ("webengine_engine_nopreview", "no_preview"),
            ("webengine_engine_off", "off")],
            tr("prefs_webengine_engine_tip"))
        _select("prefs_webengine_mode", "webengine_memory_mode", [
            ("webengine_mode_off", "off"),
            ("webengine_mode_moderate", "moderate"),
            ("webengine_mode_aggressive", "aggressive")],
            tr("prefs_webengine_mode_tip"))
        cache = self._spin("webengine_cache_mb", 0, 512)
        cache.setFixedWidth(COMBO_WIDTH)
        perf_form.addRow(
            tr("prefs_webengine_cache_mb"),
            self._row(cache, self._info_label(
                tr("prefs_webengine_cache_mb_tip")), trailing_stretch=True))
        return self._tabs([(tr("prefs_general"), general),
                           (tr("prefs_file_transfer"), files),
                           (tr("prefs_performance"), perf)])

    def _pick_download_dir(self):
        current = self._value("file_download_dir") or _default_download_dir()
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, tr("prefs_file_download_dir"), current)
        if path:
            self._set("file_download_dir", path)

    def _page_calls(self):
        """Call settings: devices, codecs/bitrate and screen sharing."""
        page, form = self._page()
        if str(getattr(self._config.performance, "calls_load_mode",
                       "lazy") or "lazy") == "off":
            # Calls are off: never import aiortc/av (via xmpp.media) just to
            # list devices — that would defeat the memory-saving mode.
            note = QtWidgets.QLabel(tr("prefs_devices_calls_off"))
            note.setWordWrap(True)
            note.setStyleSheet("color: #c0392b;")
            form.addRow(note)
            return page
        from stanza_im.xmpp import media
        from stanza_im.ui import device_test
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
        self._camera_combo = None
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
                controls += [button, level]
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
                self._camera_combo = combo
                controls.append(button)
            form.addRow(tr(label_key), self._row(*controls))
        self._camera_mode_combo = self._combo(
            "devices_camera_mode", [("prefs_camera_mode_auto", "")],
            fixed_width=True)
        self._refresh_camera_modes()
        if self._camera_combo is not None:
            self._camera_combo.currentIndexChanged.connect(
                lambda _idx: self._refresh_camera_modes())
        self._camera_mode_info = self._info_label(
            tr("prefs_camera_mode_tip"))
        form.addRow(
            tr("prefs_camera_mode"),
            self._row(self._camera_mode_combo, self._camera_mode_info,
                      trailing_stretch=True))
        form.addItem(QtWidgets.QSpacerItem(
            1, 1, QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding))
        self._update_device_tests()

        # ── codecs / bitrate / outgoing camera resolution ──────────
        codecs_page, codecs_form = self._page()
        calls = getattr(self._config, "calls", None)
        audio_codec = self._combo("calls_audio_codec", [
            ("prefs_codec_auto", "auto"), ("prefs_codec_opus", "opus"),
            ("prefs_codec_g722", "g722"), ("prefs_codec_pcmu", "pcmu"),
            ("prefs_codec_pcma", "pcma")])
        codecs_form.addRow(
            tr("prefs_audio_codec"),
            self._row(audio_codec, self._info_label(
                tr("prefs_audio_codec_tip")), trailing_stretch=True))
        video_codec = self._combo("calls_video_codec", [
            ("prefs_codec_auto", "auto"), ("prefs_codec_vp8", "vp8"),
            ("prefs_codec_h264", "h264")])
        codecs_form.addRow(
            tr("prefs_video_codec"),
            self._row(video_codec, self._info_label(
                tr("prefs_video_codec_tip")), trailing_stretch=True))
        audio_rate = self._spin("calls_audio_bitrate_kbps", 16, 128)
        codecs_form.addRow(
            tr("prefs_audio_bitrate"),
            self._row(audio_rate, self._info_label(
                tr("prefs_audio_bitrate_tip")), trailing_stretch=True))
        video_rate = self._spin("calls_video_bitrate_kbps", 100, 1500)
        codecs_form.addRow(
            tr("prefs_video_bitrate"),
            self._row(video_rate, self._info_label(
                tr("prefs_video_bitrate_tip")), trailing_stretch=True))
        height = self._combo("calls_video_max_height", [
            ("prefs_resolution_auto", 0), ("prefs_resolution_1080", 1080),
            ("prefs_resolution_720", 720), ("prefs_resolution_480", 480),
            ("prefs_resolution_360", 360)])
        stored_height = int(getattr(calls, "video_max_height", 0) or 0)
        if stored_height not in _CAMERA_HEIGHT_PRESETS:
            height.insertItem(0, tr("prefs_resolution_custom",
                                    size=stored_height), stored_height)
        codecs_form.addRow(
            tr("prefs_video_max_height"),
            self._row(height, self._info_label(
                tr("prefs_video_max_height_tip")), trailing_stretch=True))
        codecs_form.addRow(
            self._check("calls_motion_boost", tr("prefs_motion_boost")),
            self._info_label(tr("prefs_motion_boost_tip")))
        codecs_form.addItem(QtWidgets.QSpacerItem(
            1, 1, QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding))

        # ── screen sharing ─────────────────────────────────────────
        screen_page, screen_form = self._page()
        stored = getattr(self._config, "devices", None)
        width, box_height = _screen_box(
            getattr(stored, "screen_share_max_width", 1920),
            getattr(stored, "screen_share_max_height", 0))
        screen = self._combo("devices_screen_resolution", [
            ("prefs_screen_native", "0x0"),
            ("prefs_screen_1920", "1920x1080"),
            ("prefs_screen_1280", "1280x720"),
            ("prefs_screen_854", "854x480")], fixed_width=False)
        key = "%dx%d" % (width, box_height)
        if (width or box_height) and key not in [screen.itemData(i)
                                                 for i in range(screen.count())]:
            screen.insertItem(0, tr("prefs_screen_custom",
                                    size="%d×%d" % (width, box_height)), key)
        screen_form.addRow(
            tr("prefs_screen_resolution"),
            self._row(screen, self._info_label(
                tr("prefs_screen_resolution_tip")), trailing_stretch=True))
        screen_form.addRow(
            tr("prefs_screen_fps"),
            self._combo("devices_screen_share_fps", [
                ("2", 2), ("5", 5), ("10", 10), ("15", 15)]))
        screen_form.addItem(QtWidgets.QSpacerItem(
            1, 1, QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding))

        return self._tabs([
            (tr("prefs_calls_devices"), page),
            (tr("prefs_calls_codecs"), codecs_page),
            (tr("prefs_calls_screen"), screen_page),
        ])

    def _refresh_camera_modes(self) -> None:
        """List the selected camera's supported modes (Auto by default)."""
        combo = getattr(self, "_camera_mode_combo", None)
        camera = getattr(self, "_camera_combo", None)
        if combo is None:
            return
        stored = str(getattr(getattr(self._config, "devices", None),
                             "camera_mode", "") or "")
        current = str(combo.currentData() or "") if combo.count() else ""
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(tr("prefs_camera_mode_auto"), "")
        device_id = str(camera.currentData() or "") if camera else ""
        try:
            from stanza_im.xmpp import media
            modes = media.camera_formats(device_id)
        except Exception:  # noqa: BLE001 - optional dependency
            modes = []
        for mode in modes:
            label = "%d×%d · %g fps" % (mode["width"], mode["height"],
                                        mode["fps"])
            if mode.get("format"):
                label += " · " + str(mode["format"]).upper()
            data = "%dx%d@%g" % (mode["width"], mode["height"], mode["fps"])
            if mode.get("format"):
                data += ":" + str(mode["format"])
            if combo.findData(data) < 0:
                combo.addItem(label, data)
        for value in (current, stored):
            if value and combo.findData(value) < 0:
                combo.insertItem(1, tr("prefs_camera_mode_custom",
                                       mode=value), value)
        wanted = current or stored
        index = combo.findData(wanted) if wanted else 0
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)

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
                self, tr("prefs_calls_devices"), tr("prefs_device_test_busy"))
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
        if self._camera_preview is not None:
            self._camera_preview.close()
        dialog = device_test.CameraPreviewDialog(
            self._value("devices_video_input") or "", self)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.finished.connect(self._on_camera_preview_finished)
        self._camera_preview = dialog
        dialog.show()

    def _on_camera_preview_finished(self, *_args) -> None:
        self._camera_preview = None

    def _on_test_monitor(self) -> None:
        """A call owns the devices: stop the previews/tests immediately."""
        if not self._call_active():
            return
        if self._camera_preview is not None:
            self._camera_preview.close()
            self._camera_preview = None
        self._stop_device_tests(keep_preview=True)
        self._update_device_tests()

    def hideEvent(self, event):  # noqa: N802 - Qt override
        if self._test_monitor is not None:
            self._test_monitor.stop()
        super().hideEvent(event)

    def _on_device_test_failed(self, message: str) -> None:
        QtWidgets.QMessageBox.warning(
            self, tr("prefs_calls_devices"),
            tr("prefs_device_test_failed", error=message))

    def _stop_device_tests(self, keep_preview: bool = False) -> None:
        tester = getattr(self, "_mic_tester", None)
        if tester is not None:
            tester.stop()
        speaker = getattr(self, "_speaker_tester", None)
        if speaker is not None:
            speaker.stop()
        if not keep_preview and self._camera_preview is not None:
            self._camera_preview.close()
            self._camera_preview = None

    @staticmethod
    def _device_test_icon(name: str) -> QtGui.QIcon:
        """16px glyph for the icon-only device self-test buttons."""
        for ext in ("png", "svg"):
            icon = QtGui.QIcon(find_icon(f"{name}.{ext}"))
            if not icon.isNull():
                return icon
        return QtGui.QIcon()

    @staticmethod
    def _info_icon() -> QtGui.QIcon:
        """Blue "i" glyph for the information affordances/tooltips."""
        for ext in ("svg", "png"):
            icon = QtGui.QIcon(find_icon(f"info.{ext}"))
            if not icon.isNull():
                return icon
        return QtGui.QIcon()

    @staticmethod
    def _change_password_icon() -> QtGui.QIcon:
        """Key glyph for the icon-only "Change password" button."""
        icon = QtGui.QIcon(find_icon("change-password.svg"))
        if not icon.isNull():
            return icon
        if icons_mod.icons is not None:
            return QtGui.QIcon(icons_mod.icons.get_action_icon("edit"))
        return QtGui.QIcon()

    @staticmethod
    def _register_icon() -> QtGui.QIcon:
        """Glyph for the icon-only "Create account" button."""
        icon = QtGui.QIcon(find_icon("register.png"))
        if not icon.isNull():
            return icon
        return QtGui.QIcon(find_icon("add-user.svg"))

    @staticmethod
    def _wrap_tooltip(text: str, width: int = 64) -> str:
        """Wrap a tooltip to *width* columns so it stays compact on screen.

        Existing line breaks are preserved; each paragraph is filled
        separately.
        """
        if not text:
            return text
        return "\n".join(
            textwrap.fill(part, width=width) if part.strip() else part
            for part in text.split("\n"))

    def _info_label(self, tooltip: str) -> QtWidgets.QLabel:
        """A non-clickable info glyph carrying an explanatory tooltip."""
        label = QtWidgets.QLabel()
        icon = self._info_icon()
        if not icon.isNull():
            label.setPixmap(icon.pixmap(16, 16))
        label.setToolTip(self._wrap_tooltip(tooltip))
        return label

    def _sound_button(self, event: str) -> QtWidgets.QToolButton:
        """A note glyph that previews the *event*'s sound (current theme)."""
        button = QtWidgets.QToolButton()
        icon = QtGui.QIcon(find_icon("sound.svg"))
        if not icon.isNull():
            button.setIcon(icon)
        button.setIconSize(QtCore.QSize(16, 16))
        button.setAutoRaise(True)
        button.setToolTip(tr("prefs_sound_preview_tip"))
        button.clicked.connect(lambda: self._play_sound(event))
        return button

    def _sound_file_button(self, rel: str) -> QtWidgets.QToolButton:
        """A note glyph that previews a loose effect file (e.g. the ringtone)."""
        button = QtWidgets.QToolButton()
        icon = QtGui.QIcon(find_icon("sound.svg"))
        if not icon.isNull():
            button.setIcon(icon)
        button.setIconSize(QtCore.QSize(16, 16))
        button.setAutoRaise(True)
        button.setToolTip(tr("prefs_sound_preview_tip"))
        button.clicked.connect(
            lambda: self._sound_player.play_file(
                sounds_mod.effect_path(rel)))
        return button

    def _play_sound(self, event: str) -> None:
        theme = self._controls.get("sound_theme")
        theme_id = theme.currentData() if theme is not None else None
        self._sound_player.play(event, theme_id)

    @staticmethod
    def _row(*widgets: QtWidgets.QWidget, stretch_first: bool = False,
             trailing_stretch: bool = False) -> QtWidgets.QWidget:
        """Lay widgets out side by side inside a form field.

        With *stretch_first* the first widget absorbs the spare width (e.g. a
        long fingerprint label); with *trailing_stretch* the widgets are packed
        to the left (so an info glyph sits right after its control instead of a
        gap opening up between them).
        """
        box = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for index, widget in enumerate(widgets):
            layout.addWidget(widget, 1 if (stretch_first and index == 0) else 0)
        if trailing_stretch:
            layout.addStretch(1)
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
        combo.addItem(default_family, "")
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
        combo.setMinimumWidth(160)
        if default_family:
            combo.setToolTip(tr("prefs_font_default", family=default_family))
        size = self._spin(key + "_size", 0, 48)
        size.setMinimumWidth(SPIN_WIDTH)
        size.setMaximumWidth(16777215)
        size.setValue(0)
        size.setSuffix(tr("prefs_font_pt"))
        # The default keeps the real size and marks it with a compact "(*)";
        # the full phrase lives in the tooltip.
        size.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        if default_size > 0:
            size.setSpecialValueText(
                tr("prefs_font_size_default_short", size=f"{default_size:g}"))
            size.setToolTip(
                tr("prefs_font_size_default", size=f"{default_size:g}"))
        # Both controls grow with the dialog (the form uses
        # ExpandingFieldsGrow); the family takes the larger share.
        for widget in (combo, size):
            widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                 QtWidgets.QSizePolicy.Policy.Fixed)
        box = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(combo, 3)
        layout.addWidget(size, 1)
        box.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                          QtWidgets.QSizePolicy.Policy.Fixed)
        return box

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
        self._btn_register = QtWidgets.QPushButton()
        self._btn_register.setToolTip(tr("login_create_account"))
        self._btn_register.setAccessibleName(tr("login_create_account"))
        self._btn_register.setIcon(self._register_icon())
        self._btn_register.setIconSize(QtCore.QSize(16, 16))
        self._btn_register.clicked.connect(self.register_requested.emit)
        jid_row = QtWidgets.QWidget()
        jid_layout = QtWidgets.QHBoxLayout(jid_row)
        jid_layout.setContentsMargins(0, 0, 0, 0)
        jid_layout.setSpacing(6)
        jid_layout.addWidget(jid)
        jid_layout.addWidget(self._btn_register)
        jid_layout.addStretch(1)
        form.addRow(tr("login_title"), jid_row)

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
        suspend_offline = self._check(
            "offline_on_suspend", tr("prefs_offline_on_suspend"))
        suspend_offline.setToolTip(tr("prefs_offline_on_suspend_tip"))
        form.addRow(suspend_offline)
        form.addRow(self._check("save_status_message", tr("prefs_save_status_message")))

        privacy_row = QtWidgets.QHBoxLayout()
        self._btn_privacy_lists = QtWidgets.QPushButton(
            tr("prefs_privacy_lists"), connection)
        self._btn_privacy_lists.clicked.connect(self._on_privacy_lists)
        privacy_row.addWidget(self._btn_privacy_lists)
        self._btn_blocked = QtWidgets.QPushButton(
            tr("prefs_blocked_contacts"), connection)
        self._btn_blocked.clicked.connect(self._on_blocked_contacts)
        privacy_row.addWidget(self._btn_blocked)
        privacy_row.addStretch(1)
        form.addRow(privacy_row)
        self._sync_privacy_buttons()

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
        advanced_form.addRow(self._row(
            csi_keep, self._csi_keep_info, trailing_stretch=True))
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
                             self._row(starttls_mode, self._conn_info,
                                       trailing_stretch=True))

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
        allow_invalid = self._check(
            "allow_invalid_cert", tr("prefs_allow_invalid_cert"))
        allow_invalid.setStyleSheet("color: #b00020;")
        advanced_form.addRow(self._row(
            allow_invalid,
            self._info_label(tr("prefs_allow_invalid_cert_tip")),
            trailing_stretch=True))

        proxy, proxy_form = self._page()
        proxy_form.addRow(self._connection_group())
        proxy_form.addRow(self._file_proxy_group())
        proxy_form.addRow(self._stun_turn_group())
        can_refresh = (self._client is not None
                       and hasattr(self._client, "refresh_services"))
        self._btn_discovery_refresh = QtWidgets.QPushButton(
            tr("prefs_discovery_refresh"))
        refresh_icon = QtGui.QIcon(find_icon("reload.png"))
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
        form.addRow(self._row(mode, self._file_proxy_auto_label,
                              trailing_stretch=True))
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
        form.addRow(self._row(mode, self._stun_info, trailing_stretch=True))
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
        self._set_certificate(info)
        label.setToolTip("\n".join(connection_info_lines(info)))
        self._sync_privacy_buttons()

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
        self._sync_privacy_buttons()

    def _sync_privacy_buttons(self) -> None:
        """Enable the privacy entries only when the server supports them."""
        client = self._client
        checks = (("_btn_privacy_lists", "supports_privacy"),
                  ("_btn_blocked", "supports_blocking"))
        for attr, method in checks:
            button = getattr(self, attr, None)
            if button is None:
                continue
            supported = bool(client) and callable(getattr(client, method, None))
            button.setEnabled(supported and getattr(client, method)())

    def _on_privacy_lists(self) -> None:
        if not self._client:
            return
        from stanza_im.ui.privacy_lists_dialog import PrivacyListsDialog
        dialog = PrivacyListsDialog(self._client, self)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.show()

    def _on_blocked_contacts(self) -> None:
        if not self._client:
            return
        from stanza_im.ui.blocked_contacts_dialog import BlockedContactsDialog
        dialog = BlockedContactsDialog(self._client, self)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.show()

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
        mds_throttle_spin = self._spin("mds_displayed_throttle", 1, 30)
        mds_throttle_spin.setSuffix(" с")
        general_form.addRow(tr("chat_mds_displayed_throttle"), mds_throttle_spin)
        general_form.addRow(self._check("allow_incoming_edits",
                                        tr("prefs_allow_incoming_edits")))
        general_form.addRow(self._check("allow_incoming_deletions",
                                        tr("prefs_allow_incoming_deletions")))
        general_form.addRow(self._check("confirm_retraction",
                                        tr("prefs_confirm_retraction")))
        general_form.addRow(tr("prefs_media_preview"),
                            self._combo("media_preview", [
                                ("media_preview_none", "none"),
                                ("media_preview_images", "images"),
                                ("media_preview_images_audio", "images_audio"),
                                ("media_preview_all", "all"),
                            ], fixed_width=False))
        general_form.addRow(tr("prefs_idle_unload_minutes"),
                            self._spin("idle_unload_minutes", 0, 240))
        general_form.addRow(tr("prefs_history_limit"),
                            self._spin("history_limit_chat", 10, 1000))

        chat, chat_form = self._page()
        chat_form.addRow(self._check("show_status", tr("prefs_show_status")))
        chat_form.addRow(self._check("whiteboard_show_status",
                                     tr("prefs_whiteboard_show_status")))
        chat_form.addRow(
            tr("prefs_whiteboard_image_upload"),
            self._combo("whiteboard_image_upload", [
                ("prefs_wb_image_auto", "auto"),
                ("prefs_wb_image_embed", "embed"),
            ], fixed_width=False))
        chat_form.addRow(self._check("show_receipts", tr("prefs_show_receipts")))
        chat_form.addRow(self._check("show_avatars", tr("prefs_show_avatars")))
        chat_form.addRow(self._check("message_styling",
                                     tr("prefs_message_styling")))
        chat_form.addRow(
            tr("prefs_tab_title_length"),
            self._row(self._spin("tab_title_length_chat", 10, 120),
                      self._info_label(tr("prefs_tab_title_length_info"))))

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
        name_source = self._combo("muc_name_source", [
            ("prefs_muc_name_from_name", "from_name"),
            ("prefs_muc_name_from_vcard", "from_vcard"),
        ])
        name_source_info = self._info_label(tr("prefs_muc_name_source_info"))
        muc_form.addRow(tr("prefs_muc_name_source"),
                        self._row(name_source, name_source_info,
                                  trailing_stretch=True))
        muc_form.addRow(self._check("muc_confirm_leave",
                                    tr("prefs_muc_confirm_leave")))
        muc_form.addRow(self._check("muc_minimize_startup",
                                    tr("prefs_muc_minimize_startup")))
        muc_form.addRow(self._check("allow_moderation",
                                    tr("prefs_allow_moderation")))
        return self._tabs([(tr("prefs_general"), general),
                           (tr("prefs_chat_tab"), chat),
                           (tr("prefs_conferences"), muc)])

    def _page_privacy(self):
        general, form = self._page()
        form.addRow(self._check("send_software", tr("prefs_send_software")))
        form.addRow(self._check("send_typing_notifications", tr("prefs_send_typing_notifications")))
        form.addRow(self._check("send_activity_notifications", tr("prefs_send_activity_notifications")))
        omemo = self._page_omemo()
        tabs = self._tabs([(tr("prefs_general"), general),
                           (tr("prefs_omemo"), omemo)])
        from stanza_im.xmpp.omemo import availability
        if not availability.AVAILABLE:
            # The tab stays enabled so the reason is readable in place; only
            # the OMEMO controls are absent.
            tabs.setTabToolTip(1, availability.detail())
        return tabs

    def _page_omemo(self):
        from stanza_im.xmpp.omemo import availability
        page, form = self._page()
        if availability.disabled():
            note = QtWidgets.QLabel(tr("omemo_disabled_settings"))
            note.setWordWrap(True)
            note.setStyleSheet("color: #c0392b;")
            form.addRow(note)
            return page
        if not availability.AVAILABLE:
            # No distribution-specific install instructions (the client runs on
            # many platforms): just the reason and the missing Python modules.
            note = QtWidgets.QLabel(tr("omemo_unavailable"))
            note.setWordWrap(True)
            note.setStyleSheet("color: #c0392b;")
            form.addRow(note)
            if availability.MISSING_MODULES:
                modules = QtWidgets.QLabel(
                    tr("omemo_missing_modules",
                       modules=", ".join(availability.MISSING_MODULES)))
                modules.setWordWrap(True)
                form.addRow(modules)
            return page

        btbv = self._check("blind_trust", tr("prefs_omemo_blind_trust"))
        form.addRow(self._row(
            btbv, self._info_label(tr("prefs_omemo_blind_trust_tip")),
            trailing_stretch=True))
        form.addRow(self._row(
            self._check("alias_sync", tr("prefs_omemo_alias_sync")),
            self._info_label(tr("prefs_omemo_alias_sync_tip")),
            trailing_stretch=True))
        form.addRow(self._check("auto_enable",
                                tr("prefs_omemo_auto_enable")))

        self._omemo_fp = QtWidgets.QLabel(tr("omemo_loading"))
        self._omemo_fp.setWordWrap(True)
        self._omemo_fp.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        copy_btn = QtWidgets.QToolButton()
        copy_btn.setIcon(QtGui.QIcon(find_icon("copy.svg")))
        copy_btn.setIconSize(QtCore.QSize(16, 16))
        copy_btn.setAutoRaise(True)
        copy_btn.setToolTip(tr("omemo_copy_fingerprint"))
        copy_btn.clicked.connect(self._on_omemo_copy_fp)
        qr_btn = QtWidgets.QToolButton()
        qr_btn.setIcon(QtGui.QIcon(find_icon("qr.svg")))
        qr_btn.setIconSize(QtCore.QSize(16, 16))
        qr_btn.setAutoRaise(True)
        qr_btn.setToolTip(tr("prefs_omemo_qr"))
        qr_btn.clicked.connect(self._on_omemo_qr)
        self._omemo_qr_btn = qr_btn
        form.addRow(tr("prefs_omemo_own_fingerprint"),
                    self._row(self._omemo_fp, copy_btn, qr_btn,
                              stretch_first=True))

        manage = QtWidgets.QPushButton(tr("prefs_omemo_manage"))
        manage.clicked.connect(self._on_omemo_manage)
        form.addRow(manage)

        self._load_omemo_fingerprint()
        return page

    def _load_omemo_fingerprint(self):
        client = self._client
        if client is None or not getattr(client.omemo, "available", False):
            return
        import asyncio

        async def _load():
            try:
                device = await client.omemo.own_device()
            except Exception:  # noqa: BLE001
                return
            fp = client.omemo.fingerprint(device.identity_key)
            self._omemo_fp.setText(fp)

        try:
            asyncio.ensure_future(_load())
        except RuntimeError:
            pass

    def _on_omemo_copy_fp(self):
        QtWidgets.QApplication.clipboard().setText(self._omemo_fp.text())

    def _on_omemo_qr(self):
        from stanza_im.ui.qr_dialog import show_fingerprint_qr
        show_fingerprint_qr(self, self._omemo_fp.text())

    def _on_omemo_manage(self):
        client = self._client
        if client is None:
            return
        from stanza_im.ui.omemo_devices_dialog import OmemoDevicesDialog
        show_modeless(OmemoDevicesDialog(client, client.jid_str, self,
                                         own=True))

    def _page_appearance(self):
        themes, form = self._page()
        theme = QtWidgets.QComboBox()
        for name in self._theme_factory.variant_names():
            theme.addItem(name, name)
        theme.insertItem(0, tr("prefs_theme_default"), "")
        theme.setFixedWidth(COMBO_WIDTH)
        self._controls["chat_theme"] = theme
        muc_theme = QtWidgets.QComboBox()
        for name in self._theme_factory.variant_names():
            muc_theme.addItem(name, name)
        muc_theme.insertItem(0, tr("prefs_theme_default"), "")
        muc_theme.setFixedWidth(COMBO_WIDTH)
        self._controls["muc_theme"] = muc_theme
        form.addRow(tr("prefs_chat_theme"), theme)
        form.addRow(tr("prefs_muc_theme"), muc_theme)
        emoticon_theme = QtWidgets.QComboBox()
        for item in emoticons.discover_sets():
            emoticon_theme.addItem(item["name"], item["id"])
        emoticon_theme.addItem(tr("prefs_emoticon_unicode"),
                               emoticons.UNICODE_SKIN)
        emoticon_theme.addItem(tr("prefs_emoticon_none"), emoticons.NO_SKIN)
        emoticon_theme.setFixedWidth(COMBO_WIDTH)
        self._controls["emoticon_theme"] = emoticon_theme
        form.addRow(tr("prefs_emoticon_theme"), emoticon_theme)
        self._emoticon_preview = QtWidgets.QHBoxLayout()
        preview_widget = QtWidgets.QWidget()
        preview_widget.setLayout(self._emoticon_preview)
        form.addRow(tr("prefs_emoticon_preview"), preview_widget)
        emoticon_theme.currentIndexChanged.connect(self._update_emoticon_preview)
        self._update_emoticon_preview()
        misc_unicode = self._check("emoticon_unicode_replace",
                                   tr("prefs_emoticon_unicode_replace"))
        misc_unicode.setToolTip(tr("prefs_emoticon_unicode_replace_info"))
        form.addRow(misc_unicode)

        roster, roster_form = self._page()
        roster_form.addRow(self._check("roster_show_avatars",
                                       tr("prefs_roster_show_avatars")))
        roster_form.addRow(self._check("roster_show_activity",
                                       tr("prefs_roster_show_activity")))
        roster_form.addRow(self._check("roster_show_mood",
                                       tr("prefs_roster_show_mood")))
        roster_form.addRow(self._check("roster_show_clients",
                                       tr("prefs_roster_show_clients")))

        conferences, conf_form = self._page()
        conf_form.addRow(self._check("muc_show_avatars",
                                     tr("prefs_muc_show_avatars")))
        conf_form.addRow(self._check("muc_show_clients",
                                     tr("prefs_muc_show_clients")))
        conf_form.addRow(self._check("muc_show_hats",
                                     tr("prefs_muc_show_hats")))

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
        font_form.addRow(tr("prefs_font_muc_subject"),
                         self._font_row("muc_subject_font", default_family,
                                        default_size))
        font_form.addRow(tr("prefs_font_input"),
                         self._font_row("input_font", default_family,
                                        default_size))
        font_form.addRow(tr("prefs_font_osd"),
                         self._font_row("osd_font", default_family, default_size))
        font_form.addRow(tr("prefs_font_menu"),
                         self._font_row("menu_font", default_family, default_size))
        font_form.addRow(tr("prefs_font_tab"),
                         self._font_row("tab_font", default_family, default_size))
        font_form.addRow(tr("prefs_font_selector"),
                         self._font_row("selector_font", default_family,
                                        default_size))
        font_form.addRow(tr("prefs_font_tooltip"),
                         self._font_row("tooltip_font", default_family,
                                        default_size))
        font_form.addRow(tr("prefs_font_service_browser"),
                         self._font_row("service_browser_font", default_family,
                                        default_size))
        font_form.addRow(tr("prefs_font_prefs_nav"),
                         self._font_row("prefs_nav_font", default_family,
                                        default_size))

        # The nickname and input "default" follow the chat font (a real value
        # picks the chat family/size; an empty one falls through to the system
        # font), so their default labels track the chat row live.
        def _sync_nick_default():
            family = self._controls["chat_font"].currentData() or default_family
            size = (self._controls["chat_font_size"].value()
                    or default_size)
            for key in ("nick_font", "input_font"):
                default_label = tr("prefs_font_default", family=family)
                self._controls[key].setItemText(0, family)
                self._controls[key].setToolTip(default_label)
                size_widget = self._controls[key + "_size"]
                size_widget.setSpecialValueText(
                    tr("prefs_font_size_default_short", size=f"{size:g}"))
                size_widget.setToolTip(
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
        avatar_radius = self._spin("avatar_radius", 0, 100)
        avatar_radius.setSuffix(" %")
        misc_form.addRow(tr("prefs_avatar_radius"), avatar_radius)
        misc_form.addRow(tr("prefs_tooltip_avatar_size"),
                         self._spin("tooltip_avatar_size", 32, 256))
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
        misc_form.addRow(self._check("show_unread_in_tabs",
                                     tr("prefs_show_unread_in_tabs")))

        return self._tabs([(tr("prefs_appearance_themes"), themes),
                           (tr("prefs_appearance_roster"), roster),
                           (tr("prefs_appearance_muc"), conferences),
                           (tr("prefs_appearance_fonts"), fonts),
                           (tr("prefs_color_tab"), colors),
                           (tr("prefs_appearance_misc"), misc)])

    def _update_emoticon_preview(self):
        while self._emoticon_preview.count():
            item = self._emoticon_preview.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        skin = self._controls["emoticon_theme"].currentData()
        if skin == emoticons.NO_SKIN:
            note = QtWidgets.QLabel(tr("prefs_emoticon_none_preview"))
            note.setStyleSheet("color: gray;")
            self._emoticon_preview.addWidget(note)
        elif skin == emoticons.UNICODE_SKIN:
            from stanza_im.include import emoji_data
            from stanza_im.ui.emoji_picker_dialog import emoji_font
            for glyph in emoji_data.all_emoji()[:10]:
                label = QtWidgets.QLabel(glyph)
                label.setFont(emoji_font(18))
                self._emoticon_preview.addWidget(label)
        else:
            for code, path in emoticons.preview_items(skin, 10):
                label = QtWidgets.QLabel()
                label.setToolTip(code)
                label.setPixmap(QtGui.QPixmap(path).scaled(
                    24, 24, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation))
                self._emoticon_preview.addWidget(label)
        self._emoticon_preview.addStretch()

    def _page_plugins(self):
        """Mirror of Actions → Plugins: the same enable/configure widget."""
        from stanza_im.ui.plugin_manager_dialog import PluginManagerWidget
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._plugin_widget = PluginManagerWidget(self._config, page)
        layout.addWidget(self._plugin_widget, 1)
        return page

    def _page_notifications(self):
        sounds, sound_form = self._page()
        theme_combo = QtWidgets.QComboBox()
        for item in (sounds_mod.discover_themes()
                     or [{"id": "default", "name": "default"}]):
            theme_combo.addItem(item["name"], item["id"])
        theme_combo.setFixedWidth(COMBO_WIDTH)
        self._controls["sound_theme"] = theme_combo
        sound_form.addRow(tr("prefs_sound_theme"), theme_combo)
        for key, event in (
                ("sound_first_message", "new_message"),
                ("sound_any_message", "message"),
                ("sound_muc_mention", "message"),
                ("sound_on_send", "message_send"),
                ("sound_ft_start", "ft_start"),
                ("sound_ft_finish", "ft_finish"),
                ("sound_contact_online", "contact_online"),
                ("sound_contact_offline", "contact_offline")):
            sound_form.addRow(self._row(self._sound_button(event),
                                        self._check(key, tr(f"prefs_{key}"))))
        sound_form.addRow(self._row(
            self._sound_file_button("effects/ringtone.wav"),
            self._check("sound_call_incoming",
                        tr("prefs_sound_call_incoming"))))

        osd, osd_form = self._page()
        osd_form.addRow(self._check("osd_enabled", tr("prefs_osd_enabled")))
        osd_form.addRow(tr("prefs_osd_duration"),
                        self._spin("osd_duration", 1, 60))
        osd_form.addRow(tr("prefs_osd_max"), self._spin("osd_max", 1, 10))
        osd_width = self._spin("osd_width", 160, 600)
        osd_width.setSingleStep(10)
        osd_width.setSuffix(" px")
        osd_form.addRow(tr("prefs_osd_width"), osd_width)
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
        tray_form.addRow(tr("prefs_popups"), self._combo("popups", [
            ("prefs_popups_off", "off"),
            ("prefs_popups_system", "system"),
            ("prefs_popups_system_messages", "system_messages"),
        ]))
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
        try:
            widget = self._controls[key]
        except KeyError:
            # A control can be absent when its page could not build its
            # optional part (e.g. the OMEMO controls without OMEMO); never
            # crash Apply — fall back to the caller's default.
            return default
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

    def sync_font_size(self, key: str, size: int) -> None:
        """Reflect a font size changed live (Ctrl+wheel) into its spin box."""
        spin_key = key + "_size"
        spin = self._controls.get(spin_key)
        if spin is not None:
            spin.setValue(int(size))

    def _load_values(self):
        self._apply_values(self._values_dict())

    def _apply_values(self, values, keys=None):
        """Apply *values* to built controls (all, or only *keys*)."""
        for key, value in values.items():
            # Use the plain dict membership (no lazy build) here.
            if key in self._controls.keys() and (keys is None or key in keys):
                self._set(key, value)

    def _values_dict(self, cfg=None):
        cfg = cfg if cfg is not None else self._config
        connection = cfg.connection
        chat = cfg.chat
        privacy = cfg.privacy
        appearance = cfg.appearance
        notifications = cfg.notifications
        status = cfg.status
        files = getattr(cfg, "files", None)
        calls = getattr(cfg, "calls", None)
        values = {
            "close_to_tray": cfg.ui.close_to_tray,
            "language": getattr(cfg.ui, "language", "") or "",
            "history_limit_chat": chat.history_limit,
            "tab_title_length_chat": chat.tab_title_length,
            "jid": cfg.jid, "password": cfg.password, "save_password": cfg.save_password,
            "auto_connect": cfg.auto_connect,
            "auto_join_conferences": connection.auto_join_conferences,
            "message_carbons": connection.message_carbons,
            "offline_on_suspend": getattr(
                connection, "offline_on_suspend", True),
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
            "allow_invalid_cert": bool(getattr(
                connection, "allow_invalid_cert", False)),
            "host": connection.host, "port": connection.port,
            "proxy_host": connection.proxy_host, "proxy_port": connection.proxy_port,
            "send_ctrl_enter": chat.send_ctrl_enter, "show_status": chat.show_status,
            "whiteboard_show_status": getattr(
                chat, "whiteboard_show_status", True),
            "whiteboard_image_upload": getattr(
                chat, "whiteboard_image_upload", "auto"),
            "message_displayed_sync": chat.message_displayed_sync,
            "mds_displayed_throttle": chat.mds_displayed_throttle,
            "allow_incoming_edits": chat.allow_incoming_edits,
            "allow_incoming_deletions": getattr(
                chat, "allow_incoming_deletions", True),
            "confirm_retraction": getattr(chat, "confirm_retraction", False),
            "show_receipts": chat.show_receipts,
            "show_avatars": chat.show_avatars,
            "message_styling": chat.message_styling,
            "media_preview": chat.media_preview,
            "idle_unload_minutes": int(getattr(chat, "idle_unload_minutes", 10) or 0),
            "muc_name_source": getattr(chat, "muc_name_source", "from_name"),
            "muc_show_presence": chat.muc_show_presence,
            "muc_show_status": chat.muc_show_status,
            "muc_show_status_text": chat.muc_show_status_text,
            "muc_auto_nick": chat.muc_auto_nick,
            "muc_confirm_leave": chat.muc_confirm_leave,
            "allow_moderation": bool(getattr(chat, "allow_moderation", True)),
            "muc_minimize_startup": chat.muc_minimize_startup,
            "send_software": privacy.send_software,
            "send_typing_notifications": getattr(privacy, "send_typing_notifications", privacy.send_chatstates),
            "send_activity_notifications": getattr(privacy, "send_activity_notifications", privacy.send_chatstates),
            "blind_trust": bool(getattr(cfg.omemo, "blind_trust", True)),
            "alias_sync": bool(getattr(cfg.omemo, "alias_sync", False)),
            "auto_enable": bool(getattr(cfg.omemo, "auto_enable", True)),
            "chat_theme": appearance.chat_theme or chat.theme,
            "muc_theme": appearance.muc_theme,
            "emoticon_theme": ("default/smileys.cfg"
                               if appearance.emoticon_theme == "default"
                               else emoticons.normalize_skin(
                                   appearance.emoticon_theme)),
            "emoticon_unicode_replace": getattr(
                appearance, "emoticon_unicode_replace", True),
            "media_preview_size": appearance.media_preview_size,
            "media_cache_days": appearance.media_cache_days,
            "media_cache_mb": appearance.media_cache_mb,
            "muc_highlight": getattr(appearance, "muc_highlight", "both"),
            "interface_mode": getattr(appearance, "interface_mode", "separate"),
            "tray_blink": notifications.tray_blink,
            "popups": normalize_popups_mode(notifications.popups),
            "osd_enabled": notifications.osd_enabled,
            "osd_duration": notifications.osd_duration,
            "osd_max": notifications.osd_max,
            "osd_width": getattr(notifications, "osd_width", 280),
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
            "muc_subject_font": getattr(appearance, "muc_subject_font", ""),
            "muc_subject_font_size": getattr(
                appearance, "muc_subject_font_size", 0),
            "input_font": getattr(appearance, "input_font", ""),
            "input_font_size": getattr(appearance, "input_font_size", 0),
            "menu_font": getattr(appearance, "menu_font", ""),
            "menu_font_size": getattr(appearance, "menu_font_size", 0),
            "tab_font": getattr(appearance, "tab_font", ""),
            "tab_font_size": getattr(appearance, "tab_font_size", 0),
            "selector_font": getattr(appearance, "selector_font", ""),
            "selector_font_size": getattr(appearance, "selector_font_size", 0),
            "tooltip_font": getattr(appearance, "tooltip_font", ""),
            "tooltip_font_size": getattr(appearance, "tooltip_font_size", 0),
            "service_browser_font": getattr(
                appearance, "service_browser_font", ""),
            "service_browser_font_size": getattr(
                appearance, "service_browser_font_size", 0),
            "prefs_nav_font": getattr(appearance, "prefs_nav_font", ""),
            "prefs_nav_font_size": getattr(
                appearance, "prefs_nav_font_size", 0),
            "avatar_radius": getattr(appearance, "avatar_radius", 20),
            "tooltip_avatar_size": getattr(
                appearance, "tooltip_avatar_size", 64) or 64,
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
            "roster_show_clients": getattr(
                appearance, "roster_show_clients", True),
            "muc_show_avatars": getattr(appearance, "muc_show_avatars", True),
            "muc_show_clients": getattr(appearance, "muc_show_clients", True),
            "muc_show_hats": getattr(appearance, "muc_show_hats", True),
            "show_unread_in_tabs": getattr(
                appearance, "show_unread_in_tabs", True),
            "file_auto_accept": bool(getattr(files, "auto_accept", False)),
            "file_download_notifications": bool(
                getattr(files, "download_notifications", True)),
            "file_verify_hashes": bool(
                getattr(files, "verify_hashes", True)),
            "file_encryption": str(
                getattr(files, "encryption", "prefer") or "prefer"),
            "file_download_dir": getattr(files, "download_dir", "") or "",
            "devices_audio_input": getattr(
                getattr(cfg, "devices", None), "audio_input", "") or "",
            "devices_audio_output": getattr(
                getattr(cfg, "devices", None), "audio_output", "") or "",
            "devices_video_input": getattr(
                getattr(cfg, "devices", None), "video_input", "") or "",
            "devices_screen_share_fps": int(getattr(
                getattr(cfg, "devices", None), "screen_share_fps", 5) or 5),
            "devices_camera_mode": str(getattr(
                getattr(cfg, "devices", None), "camera_mode", "") or ""),
            "devices_screen_resolution": "%dx%d" % _screen_box(
                getattr(getattr(cfg, "devices", None),
                        "screen_share_max_width", 1920),
                getattr(getattr(cfg, "devices", None),
                        "screen_share_max_height", 0)),
            "calls_audio_codec": getattr(calls, "audio_codec", "auto") or "auto",
            "calls_video_codec": getattr(calls, "video_codec", "auto") or "auto",
            "calls_audio_bitrate_kbps": int(getattr(
                calls, "audio_bitrate_kbps", 96) or 96),
            "calls_video_bitrate_kbps": int(getattr(
                calls, "video_bitrate_kbps", 1000) or 1000),
            "calls_video_max_height": int(getattr(
                calls, "video_max_height", 0) or 0),
            "calls_motion_boost": bool(getattr(
                calls, "motion_boost", False)),
        }
        performance = getattr(cfg, "performance", None)
        values["defer_ui_build"] = bool(getattr(
            performance, "defer_ui_build", True))
        values["omemo_load_mode"] = getattr(
            performance, "omemo_load_mode", "lazy")
        values["calls_load_mode"] = getattr(
            performance, "calls_load_mode", "lazy")
        values["webengine_mode"] = getattr(
            performance, "webengine_mode", "full") or "full"
        values["webengine_memory_mode"] = getattr(
            performance, "webengine_memory_mode", "moderate")
        values["webengine_cache_mb"] = int(
            getattr(performance, "webengine_cache_mb", 50) or 0)
        values["sound_theme"] = getattr(notifications, "sound_theme",
                                        "default") or "default"
        for key in ("sound_first_message", "sound_any_message",
                    "sound_muc_mention", "sound_on_send", "sound_ft_start",
                    "sound_ft_finish", "sound_contact_online",
                    "sound_contact_offline", "sound_call_incoming"):
            values[key] = bool(getattr(notifications, key, False))
        return values

    def _reset_current_page(self) -> None:
        """Reset the current tab's (or page's) controls to first-run defaults.

        Only the widgets are written; the values are persisted on
        «Ок»/«Применить» like any other edit.
        """
        page = self._stack.currentWidget()
        if isinstance(page, QtWidgets.QTabWidget):
            page = page.currentWidget()
        if page is None:
            return
        keys = [key for key, owner in self._control_pages.items()
                if owner is page]
        if not keys:
            return
        self._apply_values(self._values_dict(Config.defaults()), keys=keys)

    def _on_ok(self):
        self._apply_settings()
        self.accept()

    def _apply_settings(self):
        # Every control must exist before reading values (lazy pages).
        self._ensure_all_pages()
        cfg = self._config
        cfg.ui.close_to_tray = self._value("close_to_tray")
        cfg.ui.language = self._value("language") or ""
        cfg.application.close_to_tray = self._value("close_to_tray")
        cfg.application.history_limit = self._value("history_limit_chat")
        cfg.application.tab_title_length = self._value("tab_title_length_chat")
        # Startup / memory tuning (applied on the next restart).
        cfg.performance.defer_ui_build = bool(self._value("defer_ui_build"))
        cfg.performance.omemo_load_mode = self._value("omemo_load_mode") or "lazy"
        cfg.performance.calls_load_mode = self._value("calls_load_mode") or "lazy"
        cfg.performance.webengine_mode = self._value("webengine_mode") or "full"
        cfg.performance.webengine_memory_mode = (
            self._value("webengine_memory_mode") or "moderate")
        cfg.performance.webengine_cache_mb = int(
            self._value("webengine_cache_mb") or 0)
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
        cfg.connection.allow_invalid_cert = bool(
            self._value("allow_invalid_cert"))
        cfg.connection.priority = self._value("priority")
        cfg.connection.keepalive = self._value("keepalive")
        cfg.connection.pep_sweep_interval = int(
            self._value("pep_sweep_interval") or 0)
        cfg.connection.stream_management = self._value("stream_management")
        cfg.connection.csi = self._value("csi")
        cfg.connection.csi_keep_active_for_typing_osd = self._value(
            "csi_keep_active_for_typing_osd")
        cfg.connection.message_carbons = self._value("message_carbons")
        cfg.connection.offline_on_suspend = bool(
            self._value("offline_on_suspend"))
        for key in ("override_host", "port", "proxy_port"):
            cfg.connection[key] = self._value(key)
        for key in ("send_ctrl_enter", "show_status", "show_receipts",
                    "whiteboard_show_status", "whiteboard_image_upload",
                    "show_avatars", "message_styling",
                    "muc_show_presence",
                    "muc_show_status", "muc_show_status_text",
                    "muc_auto_nick", "muc_confirm_leave",
                    "muc_minimize_startup", "message_displayed_sync",
                    "allow_incoming_edits", "allow_incoming_deletions",
                    "allow_moderation",
                    "confirm_retraction", "idle_unload_minutes",
                    "muc_name_source"):
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
        if "blind_trust" in self._controls:
            # Only write the OMEMO settings when the controls exist; without
            # OMEMO the page omits them, and writing would clobber the stored
            # values.
            cfg.omemo.blind_trust = self._value("blind_trust")
            cfg.omemo.alias_sync = self._value("alias_sync")
            cfg.omemo.auto_enable = self._value("auto_enable")
        cfg.notifications.tray_blink = self._value("tray_blink")
        cfg.notifications.popups = self._value("popups")
        cfg.notifications.osd_enabled = self._value("osd_enabled")
        for key in ("osd_duration", "osd_max", "osd_message", "osd_file",
                    "osd_typing", "osd_status", "osd_conference",
                    "osd_topdown", "osd_width"):
            cfg.notifications[key] = self._value(key)
        cfg.notifications.sound_theme = self._value("sound_theme") or "default"
        for key in ("sound_first_message", "sound_any_message",
                    "sound_muc_mention", "sound_on_send", "sound_ft_start",
                    "sound_ft_finish", "sound_contact_online",
                    "sound_contact_offline", "sound_call_incoming"):
            cfg.notifications[key] = self._value(key)
        for key in ("auto_away", "away_minutes", "auto_xa", "xa_minutes"):
            cfg.status[key] = self._value(key)
        cfg.status.auto_status_message = self._value("auto_status_message")
        cfg.chat.text_scale = self._value("text_scale")
        cfg.appearance.avatar_radius = self._value("avatar_radius")
        for key in ("roster_font", "roster_font_size", "chat_font", "chat_font_size",
                    "osd_font", "osd_font_size", "nick_font", "nick_font_size",
                    "participant_font", "participant_font_size",
                    "muc_subject_font", "muc_subject_font_size",
                    "input_font", "input_font_size", "tooltip_avatar_size",
                    "menu_font", "menu_font_size", "tab_font", "tab_font_size",
                    "selector_font", "selector_font_size",
                    "tooltip_font", "tooltip_font_size",
                    "service_browser_font", "service_browser_font_size",
                    "prefs_nav_font", "prefs_nav_font_size",
                    "osd_bg_color", "osd_font_color", "osd_opacity",
                    "roster_bg_color", "roster_group_bg_color", "chat_bg_color",
                    "muc_highlight_color", "colored_muc_nicks",
                    "roster_show_avatars", "roster_show_activity",
                    "roster_show_mood", "roster_show_clients",
                    "muc_show_avatars", "muc_show_clients", "muc_show_hats",
                    "show_unread_in_tabs", "emoticon_unicode_replace"):
            cfg.appearance[key] = self._value(key)
        if not hasattr(cfg, "files"):
            cfg.set("files", {"auto_accept": False,
                              "download_notifications": True,
                              "download_dir": ""})
        cfg.files.auto_accept = self._value("file_auto_accept")
        cfg.files.download_notifications = self._value(
            "file_download_notifications")
        cfg.files.verify_hashes = self._value("file_verify_hashes")
        cfg.files.encryption = self._value("file_encryption") or "prefer"
        cfg.files.download_dir = self._value("file_download_dir")
        if not hasattr(cfg, "devices"):
            cfg.set("devices", {"audio_input": "", "audio_output": "",
                                "video_input": ""})
        for key in ("audio_input", "audio_output", "video_input"):
            cfg.devices[key] = self._value("devices_" + key) or ""
        cfg.devices.camera_mode = self._value("devices_camera_mode") or ""
        cfg.devices.screen_share_fps = int(
            self._value("devices_screen_share_fps") or 5)
        preset = str(self._value("devices_screen_resolution") or "0x0")
        try:
            screen_w, screen_h = (int(part) for part in preset.split("x", 1))
        except (TypeError, ValueError):
            screen_w, screen_h = 0, 0
        cfg.devices.screen_share_max_width = max(0, screen_w)
        cfg.devices.screen_share_max_height = max(0, screen_h)
        if not hasattr(cfg, "calls"):
            cfg.set("calls", {"auto_accept": False})
        cfg.calls.audio_codec = self._value("calls_audio_codec") or "auto"
        cfg.calls.video_codec = self._value("calls_video_codec") or "auto"
        cfg.calls.audio_bitrate_kbps = int(
            self._value("calls_audio_bitrate_kbps") or 96)
        cfg.calls.video_bitrate_kbps = int(
            self._value("calls_video_bitrate_kbps") or 1000)
        cfg.calls.video_max_height = int(
            self._value("calls_video_max_height") or 0)
        cfg.calls.motion_boost = bool(
            self._value("calls_motion_boost", False))
        # Apply the plugin manager page (mirror of Actions → Plugins) and let
        # the main window (de)activate the affected plugins live.
        plugin_ids = None
        widget = getattr(self, "_plugin_widget", None)
        if widget is not None:
            plugin_ids = widget.apply_checked()
        cfg.save()
        self.settings_applied.emit()
        # The app-wide stylesheet is re-applied by the main window on the
        # signal above; set the section navigator font after it.
        self._apply_nav_font()
        if plugin_ids is not None:
            self.plugins_applied.emit(list(plugin_ids))

    # ── Change account password ──────────────────────────────────────

    def _on_change_password(self):
        if self._client is None:
            return
        from stanza_im.ui.change_password_dialog import ChangePasswordDialog
        dlg = ChangePasswordDialog(self)

        def finished(result: int):
            if result != QtWidgets.QDialog.DialogCode.Accepted:
                return
            self._btn_change_password.setEnabled(False)
            asyncio.create_task(self._run_change_password(dlg.password()))
        show_modeless(dlg, finished)

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
