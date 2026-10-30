"""Call UI: incoming-call prompt and the active-call window.

The window paints decoded remote video frames (QImage from
:mod:`stanza_im.xmpp.media`) and exposes icon-only controls (mute, camera,
hang up).  It is deliberately free of Qt Multimedia imports so it also works
where Qt Multimedia cannot load.
"""
from __future__ import annotations

import logging
import math
import os
import time

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.avatars import default_avatar
from stanza_im.include.constants import find_icon
from stanza_im.include.utils import format_duration
from stanza_im.include.network_quality import network_quality
from stanza_im.ui.network_quality import network_icon

logger = logging.getLogger("stanza_im.call.ui")

_ICON_CACHE: dict[str, QtGui.QIcon] = {}


def _icon(name: str) -> QtGui.QIcon:
    """Load a 16px action glyph (SVG preferred) for the call controls."""
    icon = _ICON_CACHE.get(name)
    if icon is None:
        icon = QtGui.QIcon()
        for ext in ("svg", "png"):
            path = find_icon(f"{name}.{ext}")
            if path:
                candidate = QtGui.QIcon(path)
                if not candidate.isNull():
                    icon = candidate
                    break
        _ICON_CACHE[name] = icon
    return icon


def _flat(button):
    """Make a call control look like the flat toolbar buttons in chats."""
    if isinstance(button, QtWidgets.QToolButton):
        button.setAutoRaise(True)
    elif isinstance(button, QtWidgets.QPushButton):
        button.setFlat(True)
    return button


#: Outgoing video modes: the combo button icon + its label key.
_VIDEO_MODE_ICONS = {"off": "camera-off", "camera": "camera",
                     "region": "wb-select", "screen": "screen-share"}
_VIDEO_MODE_TIPS = {"off": "video_mode_off", "camera": "video_mode_camera",
                    "region": "video_mode_region", "screen": "video_mode_screen"}

#: Live outgoing video quality presets (value, i18n key).
_QUALITY_BITRATES = ((200, "call_quality_low"), (500, "call_quality_medium"),
                     (1000, "call_quality_high"),
                     (1500, "call_quality_1500"))
_QUALITY_HEIGHTS = ((0, "call_quality_source"), (1080, "call_quality_1080"),
                    (720, "call_quality_720"), (480, "call_quality_480"),
                    (360, "call_quality_360"))
#: Incoming REMB cap presets (kbps, i18n label key).
_INCOMING_LIMITS = ((0, "prefs_incoming_auto"),
                    (200, "prefs_incoming_200"),
                    (500, "prefs_incoming_500"),
                    (1000, "prefs_incoming_1000"),
                    (1500, "prefs_incoming_1500"))


def _incoming_menu(parent, value: int) -> tuple[QtWidgets.QMenu, dict]:
    """Build the incoming-bitrate submenu and return its checkable actions."""
    menu = QtWidgets.QMenu(tr("call_incoming_max"), parent)
    actions = {}
    for kbps, key in _INCOMING_LIMITS:
        action = menu.addAction(tr(key))
        action.setCheckable(True)
        action.setChecked(kbps == int(value or 0))
        actions[kbps] = action
    return menu, actions


def entire_unknown() -> str:
    return tr("call_info_unknown")


def _fmt_kbps(value) -> str:
    if value is None:
        return entire_unknown()
    return tr("call_info_kbps", value=int(round(float(value))))


def _fmt_size(width, height) -> str:
    if not width or not height:
        return entire_unknown()
    return "%d×%d" % (int(width), int(height))


def _info_toggle(parent) -> QtWidgets.QToolButton:
    """A checkable button that shows/hides the codec information line."""
    button = QtWidgets.QToolButton(parent)
    button.setIcon(_icon("info"))
    button.setIconSize(QtCore.QSize(20, 20))
    button.setToolTip(tr("call_info"))
    button.setCheckable(True)
    return _flat(button)


_NETWORK_LABELS = {
    4: "call_network_excellent",
    3: "call_network_good",
    2: "call_network_fair",
    1: "call_network_poor",
    0: "call_network_unknown",
}
_NETWORK_REASONS = {
    "in_loss": "call_network_reason_in_loss",
    "out_loss": "call_network_reason_out_loss",
    "limited": "call_network_reason_limited",
    "lag": "call_network_reason_lag",
    "ok": "call_network_reason_ok",
    "unknown": "call_network_unknown",
}


def _network_tooltip(result: dict) -> str:
    """Human-readable network state for the indicator tooltip."""
    level = int(result.get("level") or 0)
    if level <= 0:
        return tr("call_network_unknown")
    label = tr(_NETWORK_LABELS.get(level, "call_network_unknown"))
    reason = tr(_NETWORK_REASONS.get(
        str(result.get("reason") or "unknown"), "call_network_unknown"))
    details = tr(
        "call_network_details",
        out_loss="%.1f" % float(result.get("out_loss") or 0),
        in_loss="%.1f" % float(result.get("in_loss") or 0),
        remb="%d" % int((result.get("remb_bps") or 0) / 1000),
        target="%d" % int((result.get("target_bps") or 0) / 1000),
        cap="%d" % int((result.get("cap_bps") or 0) / 1000),
    )
    return "%s: %s\n%s\n%s" % (
        tr("call_network"), label, reason, details)


def _format_info_line(info) -> str:
    """One compact line with the negotiated codecs/resolution/bitrates."""
    if not info:
        return tr("call_info_unavailable")
    parts: list[str] = []
    video_codec = str(info.get("video_codec") or "")
    if video_codec:
        out = video_codec + " " + _fmt_size(info.get("out_width"),
                                            info.get("out_height"))
        target = info.get("video_kbps")
        if target is not None:
            rate = _fmt_kbps(target)
            actual = info.get("out_video_bps")
            if actual is not None:
                rate += " (" + _fmt_kbps(actual / 1000) + ")"
            out += " · " + rate
        parts.append(out)
        if info.get("in_width") and info.get("in_height"):
            incoming = tr("call_info_in_short") + " " + _fmt_size(
                info.get("in_width"), info.get("in_height"))
            if info.get("in_bps") is not None:
                incoming += " · " + _fmt_kbps(info["in_bps"] / 1000)
            parts.append(incoming)
    audio_codec = str(info.get("audio_codec") or "")
    if audio_codec:
        audio = audio_codec
        if info.get("audio_kbps") is not None:
            audio += " " + _fmt_kbps(info["audio_kbps"])
        parts.append(audio)
    sessions = int(info.get("sessions") or 0)
    if sessions > 1:
        parts.append(tr("call_info_sessions", n=sessions))
    return " · ".join(parts) if parts else tr("call_info_unavailable")


def _quality_button(parent, bitrate: int, height: int, on_change):
    """An icon-only menu button for the live video bitrate/resolution."""
    button = QtWidgets.QToolButton(parent)
    button.setIcon(_icon("quality"))
    button.setIconSize(QtCore.QSize(20, 20))
    button.setToolTip(tr("call_quality"))
    button.setPopupMode(
        QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = QtWidgets.QMenu(button)
    bitrate_menu = menu.addMenu(tr("call_quality_bitrate"))
    bitrate_actions = {}
    for value, key in _QUALITY_BITRATES:
        action = bitrate_menu.addAction(tr(key))
        action.setCheckable(True)
        action.setChecked(value == int(bitrate or 0))
        action.triggered.connect(
            lambda checked=False, v=value: on_change(v, None))
        bitrate_actions[value] = action
    height_menu = menu.addMenu(tr("call_quality_resolution"))
    height_actions = {}
    for value, key in _QUALITY_HEIGHTS:
        action = height_menu.addAction(tr(key))
        action.setCheckable(True)
        action.setChecked(value == int(height or 0))
        action.triggered.connect(
            lambda checked=False, v=value: on_change(None, v))
        height_actions[value] = action
    button.setMenu(menu)
    return button, bitrate_actions, height_actions


def _add_quality_menus(menu, bitrate, height, on_change):
    """Append outgoing bitrate/resolution submenus to a menu."""
    bitrate_menu = menu.addMenu(tr("call_quality_bitrate"))
    bitrate_actions = {}
    for value, key in _QUALITY_BITRATES:
        action = bitrate_menu.addAction(tr(key))
        action.setCheckable(True)
        action.setChecked(value == int(bitrate or 0))
        action.triggered.connect(
            lambda checked=False, v=value: on_change(v, None))
        bitrate_actions[value] = action
    height_menu = menu.addMenu(tr("call_quality_resolution"))
    height_actions = {}
    for value, key in _QUALITY_HEIGHTS:
        action = height_menu.addAction(tr(key))
        action.setCheckable(True)
        action.setChecked(value == int(height or 0))
        action.triggered.connect(
            lambda checked=False, v=value: on_change(None, v))
        height_actions[value] = action
    return bitrate_actions, height_actions


def _rounded_avatar(path: str, size: int = 24,
                    radius_pct: int = 100) -> QtGui.QPixmap:
    """Return a scaled avatar pixmap clipped to a rounded square.

    *radius_pct* mirrors ``appearance.avatar_radius`` (100 = full circle).
    """
    from stanza_im.include.avatars import rounded_avatar
    return rounded_avatar(QtGui.QPixmap(path), size, radius_pct)


class VideoView(QtWidgets.QLabel):
    """Paints decoded video frames with an overlay nickname caption."""

    def __init__(self, parent=None, min_size=(320, 240)):
        super().__init__(parent)
        self.setMinimumSize(*min_size)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#101010; color:#888;")
        self.setText(tr("call_no_video"))
        self._image = None
        self._caption = ""
        self._mirrored = False
        self._caption_font = QtGui.QFont()
        self._caption_font.setPointSize(9)
        self._caption_font.setBold(True)

    def set_frame(self, image):
        # Only real QImage frames are paintable; a stray value (e.g. a raw
        # PyAV frame) must never reach paintEvent, which would abort Qt.
        if image is not None and not isinstance(image, QtGui.QImage):
            logger.debug("CALL ignoring non-QImage video frame: %r",
                         type(image).__name__)
            return
        self._image = image
        self.update()

    def content_rect(self) -> QtCore.QRect:
        """The rectangle actually covered by the aspect-fitted image."""
        if self._image is None or self._image.isNull():
            return self.rect()
        scaled = self._image.size().scaled(
            self.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        return QtCore.QRect(x, y, scaled.width(), scaled.height())

    def set_caption(self, text: str) -> None:
        self._caption = text or ""
        self.update()

    def set_mirrored(self, mirrored: bool) -> None:
        self._mirrored = bool(mirrored)
        self.update()

    def _target_rect(self) -> QtCore.QRect:
        """Aspect-fitted destination rectangle without allocating a QImage."""
        if self._image is None or self._image.isNull():
            return self.rect()
        size = self._image.size().scaled(
            self.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        x = (self.width() - size.width()) // 2
        y = (self.height() - size.height()) // 2
        return QtCore.QRect(x, y, size.width(), size.height())

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = None
        if self._image is not None:
            painter = QtGui.QPainter(self)
            target = self._target_rect()
            if self._mirrored:
                painter.translate(self.width(), 0)
                painter.scale(-1, 1)
            painter.drawImage(target, self._image)
            if self._mirrored:
                painter.resetTransform()
        if self._caption:
            if painter is None:
                painter = QtGui.QPainter(self)
            painter.setFont(self._caption_font)
            metrics = painter.fontMetrics()
            pad = 4
            rect = QtCore.QRect(
                6, 6, metrics.horizontalAdvance(self._caption) + pad * 2,
                metrics.height() + pad)
            painter.fillRect(rect, QtGui.QColor(0, 0, 0, 150))
            painter.setPen(QtGui.QColor(255, 255, 255))
            painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter,
                             self._caption)
        if painter is not None:
            painter.end()


class IncomingCallDialog(QtWidgets.QDialog):
    """Prompt shown for an incoming call offer (icon-only accept/reject)."""

    decision = QtCore.pyqtSignal(bool, bool)   # accept, video

    def __init__(self, caller: str, media_kind: str = "audio", parent=None,
                 avatar_path: str | None = None, avatar_radius: int = 100,
                 sid: str = "", show_self: bool = False):
        super().__init__(parent)
        self.sid = sid
        self.setWindowTitle(tr("call_incoming_title"))
        self._video = media_kind == "video"
        self._self_view = None
        layout = QtWidgets.QVBoxLayout(self)
        # The contact's avatar, centered, with the name and the call message
        # below it.
        avatar = QtWidgets.QLabel(self)
        avatar.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        pix = _rounded_avatar(avatar_path or default_avatar(), 96,
                              radius_pct=avatar_radius)
        if not pix.isNull():
            avatar.setPixmap(pix)
        layout.addWidget(avatar)
        name = QtWidgets.QLabel(caller, self)
        name.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(name)
        label = QtWidgets.QLabel(
            tr("call_incoming_kind",
               kind=tr("call_video" if self._video else "call_audio")), self)
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)

        if show_self and self._video:
            self_row = QtWidgets.QHBoxLayout()
            self_row.addStretch(1)
            self._self_view = VideoView(self, min_size=(1, 1))
            self._self_view.setFixedSize(150, 84)
            self._self_view.set_caption(tr("call_pip_self"))
            self._self_view.set_mirrored(True)
            self_row.addWidget(self._self_view)
            layout.addLayout(self_row)

        buttons = QtWidgets.QHBoxLayout()
        self._accept = QtWidgets.QPushButton(self)
        self._accept.setIcon(_icon("call-accept"))
        self._accept.setIconSize(QtCore.QSize(22, 22))
        self._accept.setToolTip(tr("call_accept"))
        self._accept.setDefault(True)
        self._reject = QtWidgets.QPushButton(self)
        self._reject.setIcon(_icon("call-hangup"))
        self._reject.setIconSize(QtCore.QSize(22, 22))
        self._reject.setToolTip(tr("call_reject"))
        # Reject on the left, accept on the right, one at each edge.
        buttons.addWidget(self._reject)
        buttons.addStretch(1)
        buttons.addWidget(self._accept)
        layout.addLayout(buttons)
        self._accept.clicked.connect(self._on_accept)
        self._reject.clicked.connect(self._on_reject)

    def set_local_frame(self, image) -> None:
        """Feed the pre-answer PiP self-view (video calls only)."""
        if self._self_view is not None:
            self._self_view.set_frame(image)

    def _on_accept(self):
        self.decision.emit(True, self._video)
        self.accept()

    def _on_reject(self):
        self.decision.emit(False, False)
        self.reject()


class CallWindow(QtWidgets.QWidget):
    """Active call window with remote video and icon-only controls."""

    hangup = QtCore.pyqtSignal(str)          # sid
    redial_requested = QtCore.pyqtSignal(str, str, bool)  # sid, jid, video
    render_size_changed = QtCore.pyqtSignal(str, int, int)  # sid, width, height
    audio_toggled = QtCore.pyqtSignal(str, bool)    # outgoing audio enabled
    video_mode_requested = QtCore.pyqtSignal(str, str)  # sid, mode
    receive_toggled = QtCore.pyqtSignal(str, bool)  # remote audio playback
    quality_requested = QtCore.pyqtSignal(str, int, int)  # sid, kbps, height
    incoming_requested = QtCore.pyqtSignal(str, int)  # sid, kbps
    pip_toggled = QtCore.pyqtSignal(str, bool)  # sid, enabled
    visibility_changed = QtCore.pyqtSignal(str, bool)  # sid, visible

    def __init__(self, sid: str, peer: str, video: bool = False, parent=None,
                 avatar_path: str | None = None, avatar_radius: int = 100,
                 video_bitrate: int = 1000, max_height: int = 0,
                 info_provider=None, audio_enabled: bool = True,
                 remote_audio_enabled: bool = True, incoming_max: int = 0,
                 pip_enabled: bool = True, peer_jid: str = ""):
        super().__init__(parent)
        self.sid = sid
        self.peer = peer
        self.peer_jid = peer_jid or peer
        self._failed = False
        self._ended = False
        self._ended_overlay = None
        self._last_render_size = (0, 0)
        self._quality_bitrate = int(video_bitrate or 0)
        self._quality_height = int(max_height or 0)
        self._info_provider = info_provider
        self._video = video
        self.setWindowTitle(tr("call_window_title", peer=peer))
        self.setMinimumSize(420, 340)
        self._muted = not bool(audio_enabled)
        self._hear_muted = not bool(remote_audio_enabled)
        self._incoming_max = int(incoming_max or 0)
        self._pip_enabled = bool(pip_enabled) and bool(video)

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        self._header = QtWidgets.QLabel(self)
        self._header.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._header.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self._state_text = tr("call_connecting")
        self._update_header()
        header.addWidget(self._header, 1)
        self._duration_label = QtWidgets.QLabel("", self)
        self._duration_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self._duration_label.setStyleSheet("color: gray;")
        self._duration_label.setVisible(False)
        header.addWidget(self._duration_label, 0)
        layout.addLayout(header)

        self._info_label = QtWidgets.QLabel("", self)
        self._info_label.setStyleSheet("color: gray;")
        self._info_label.setWordWrap(True)
        self._info_label.setVisible(False)
        layout.addWidget(self._info_label)

        if not video:
            # An audio call has no video surface — show the contact's avatar
            # (or the placeholder) below the header.
            avatar = QtWidgets.QLabel(self)
            avatar.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            pix = _rounded_avatar(avatar_path or default_avatar(), 96,
                                  radius_pct=avatar_radius)
            if not pix.isNull():
                avatar.setPixmap(pix)
            layout.addWidget(avatar)
        self._duration_timer = QtCore.QTimer(self)
        self._duration_timer.setInterval(1000)
        self._duration_timer.timeout.connect(self._tick_duration)
        self._duration_start = 0.0

        self._video_view = VideoView(self)
        self._video_view.set_caption(peer)
        layout.addWidget(self._video_view, stretch=1)
        if not video:
            self._video_view.setVisible(False)
        self._pip_view = VideoView(self._video_view, min_size=(1, 1))
        self._pip_view.set_caption(tr("call_pip_self"))
        self._pip_view.set_mirrored(True)
        self._pip_view.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._pip_view.setVisible(bool(self._pip_enabled and video))
        self._video_view.installEventFilter(self)

        controls = QtWidgets.QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(2)
        self._mute_btn = QtWidgets.QToolButton(self)
        self._mute_btn.setIcon(_icon("mic-off" if self._muted else "mic"))
        self._mute_btn.setIconSize(QtCore.QSize(20, 20))
        self._mute_btn.setToolTip(
            tr("call_unmute") if self._muted else tr("call_mute"))
        self._mute_btn.setCheckable(True)
        self._mute_btn.setChecked(self._muted)
        self._mute_btn.toggled.connect(self._on_mute)
        controls.addWidget(_flat(self._mute_btn))

        # Mute the *remote* audio (the contact's voice), not our microphone.
        self._hear_btn = QtWidgets.QToolButton(self)
        self._hear_btn.setIcon(
            _icon("speaker-off" if self._hear_muted else "speaker"))
        self._hear_btn.setIconSize(QtCore.QSize(20, 20))
        self._hear_btn.setToolTip(
            tr("call_unmute_peer") if self._hear_muted
            else tr("call_mute_peer"))
        self._hear_btn.setCheckable(True)
        self._hear_btn.setChecked(self._hear_muted)
        self._hear_btn.toggled.connect(self._on_hear)
        controls.addWidget(_flat(self._hear_btn))

        self._video_mode = "camera" if video else "off"
        self._video_btn = QtWidgets.QToolButton(self)
        self._video_btn.setIcon(_icon(_VIDEO_MODE_ICONS[self._video_mode]))
        self._video_btn.setIconSize(QtCore.QSize(20, 20))
        self._video_btn.setToolTip(tr(_VIDEO_MODE_TIPS[self._video_mode]))
        self._video_btn.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        video_menu = QtWidgets.QMenu(self._video_btn)
        self._video_actions = {}
        for mode in ("off", "camera", "region", "screen"):
            action = video_menu.addAction(
                _icon(_VIDEO_MODE_ICONS[mode]), tr(_VIDEO_MODE_TIPS[mode]),
                lambda checked=False, m=mode: self._request_mode(m))
            action.setCheckable(True)
            action.setChecked(mode == self._video_mode)
            self._video_actions[mode] = action
        self._video_btn.setMenu(video_menu)
        controls.addWidget(_flat(self._video_btn))
        self._pip_btn = QtWidgets.QToolButton(self)
        self._pip_btn.setIcon(_icon("pip"))
        self._pip_btn.setIconSize(QtCore.QSize(20, 20))
        self._pip_btn.setToolTip(tr("call_pip"))
        self._pip_btn.setCheckable(True)
        self._pip_btn.setChecked(self._pip_enabled)
        self._pip_btn.setVisible(video)
        self._pip_btn.toggled.connect(self._on_pip)
        controls.addWidget(_flat(self._pip_btn))
        self._network_btn = QtWidgets.QToolButton(self)
        self._network_btn.setIcon(network_icon(0))
        self._network_btn.setIconSize(QtCore.QSize(20, 20))
        self._network_btn.setAutoRaise(True)
        self._network_btn.setToolTip(tr("call_network_unknown"))
        self._network_btn.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        network_menu = QtWidgets.QMenu(self._network_btn)
        (self._quality_bitrate_actions,
         self._quality_height_actions) = _add_quality_menus(
            network_menu, self._quality_bitrate, self._quality_height,
            self._on_quality)
        incoming_menu, self._incoming_actions = _incoming_menu(
            self._network_btn, self._incoming_max)
        for kbps, action in self._incoming_actions.items():
            action.triggered.connect(
                lambda checked=False, value=kbps: self._on_incoming(value))
        network_menu.addMenu(incoming_menu)
        self._network_btn.setMenu(network_menu)
        controls.addWidget(_flat(self._network_btn))
        self._info_btn = _info_toggle(self)
        self._info_btn.toggled.connect(self._toggle_info)
        controls.addWidget(self._info_btn)
        self._redial_btn = _flat(QtWidgets.QPushButton(
            _icon("call-accept"), tr("call_redial"), self))
        self._redial_btn.setVisible(False)
        self._redial_btn.clicked.connect(
            lambda: self.redial_requested.emit(
                self.sid, self.peer_jid, bool(self._video)))
        controls.addWidget(self._redial_btn)
        controls.addSpacing(4)

        self._hangup_btn = QtWidgets.QToolButton(self)
        self._hangup_btn.setIcon(_icon("call-hangup"))
        self._hangup_btn.setIconSize(QtCore.QSize(20, 20))
        self._hangup_btn.setToolTip(tr("call_hangup"))
        self._hangup_btn.clicked.connect(self._on_hangup)
        controls.addWidget(_flat(self._hangup_btn))
        # Keep the control strip on its own line: its minimum width also
        # protects the buttons from being squeezed into the video area at the
        # smallest window size.
        self._controls_widget = QtWidgets.QWidget(self)
        self._controls_widget.setLayout(controls)
        self._controls_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed)
        layout.addWidget(self._controls_widget, 0,
                         QtCore.Qt.AlignmentFlag.AlignHCenter)
        self._fit_controls()

    def _fit_controls(self) -> None:
        """Keep the control strip exactly as wide/tall as its buttons."""
        layout = self._controls_widget.layout()
        if layout is None:
            return
        hint = layout.sizeHint()
        self._controls_widget.setFixedWidth(max(1, hint.width()))
        self._controls_widget.setFixedHeight(max(1, hint.height()))
        self._fit_window_height()

    def _fit_window_height(self) -> None:
        """Reserve enough height for the video even when codec info wraps."""
        layout = self.layout()
        if layout is None:
            return
        margins = layout.contentsMargins()
        spacing = max(0, layout.spacing())
        info_height = (self._info_label.sizeHint().height()
                       if self._info_label.isVisible() else 0)
        needed = (margins.top() + margins.bottom()
                  + self._header.sizeHint().height()
                  + info_height
                  + self._video_view.minimumHeight()
                  + self._controls_widget.height()
                  + spacing * 3 + 16)
        self.setMinimumHeight(max(340, needed))

    def show_ended(self) -> None:
        """Keep the last frame visible after a remote hangup until the user closes."""
        self._ended = True
        self._duration_timer.stop()
        self._duration_label.setVisible(False)
        self._state_text = tr("call_ended")
        self._update_header()
        for button in (self._mute_btn, self._hear_btn, self._video_btn,
                       self._pip_btn, self._network_btn, self._info_btn,
                       self._redial_btn):
            button.setVisible(False)
        self._pip_view.setVisible(False)
        self._hangup_btn.setToolTip(tr("dialog_close"))
        if self._ended_overlay is None:
            overlay = QtWidgets.QLabel(tr("call_ended"), self._video_view)
            overlay.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            overlay.setStyleSheet(
                "background: rgba(0,0,0,150); color: white; "
                "padding: 8px 16px; border-radius: 6px;")
            overlay.adjustSize()
            overlay.raise_()
            overlay.show()
            self._ended_overlay = overlay
        self._position_ended_overlay()

    def _position_ended_overlay(self) -> None:
        overlay = self._ended_overlay
        if overlay is None:
            return
        overlay.adjustSize()
        parent = self._video_view
        overlay.move(
            max(0, (parent.width() - overlay.width()) // 2),
            max(0, (parent.height() - overlay.height()) // 2))
        overlay.raise_()

    def show_failed(self, error: str = "") -> None:
        """Keep the window open after a failed call with a redial action."""
        self._failed = True
        self._duration_timer.stop()
        self._duration_label.setVisible(False)
        self._state_text = tr("call_connection_lost")
        self._update_header()
        self._info_label.setText(
            tr("call_failed", peer=self.peer,
               error=error or tr("call_connection_lost")))
        self._info_label.setVisible(True)
        for button in (self._mute_btn, self._hear_btn, self._video_btn,
                       self._pip_btn, self._network_btn, self._info_btn):
            button.setVisible(False)
        self._pip_view.setVisible(False)
        self._redial_btn.setVisible(True)
        self._hangup_btn.setToolTip(tr("dialog_close"))
        self._fit_controls()

    def _on_hangup(self) -> None:
        if self._failed or self._ended:
            # Let MainWindow drop the detached window from its sid map.
            self.hangup.emit(self.sid)
            self.close()
            return
        self.hangup.emit(self.sid)

    def _update_header(self) -> None:
        from stanza_im.include.utils import escape_html
        self._header.setText(
            "<span style='font-weight:bold;font-size:14px'>%s</span> "
            "<span style='color:gray'>(%s)</span>"
            % (escape_html(self.peer), escape_html(self._state_text)))

    def set_state(self, text: str):
        self._state_text = text
        self._update_header()

    def _toggle_info(self, checked: bool) -> None:
        self._info_label.setVisible(bool(checked))
        if checked:
            self._refresh_info()
        self._fit_window_height()
        QtCore.QTimer.singleShot(0, self._fit_window_height)

    def _refresh_info(self) -> None:
        info = None
        if self._info_provider is not None:
            try:
                info = self._info_provider(self.sid)
            except Exception:  # noqa: BLE001 - diagnostics only
                info = None
        self._info_label.setText(_format_info_line(info))
        self._fit_window_height()
        QtCore.QTimer.singleShot(0, self._fit_window_height)

    def start_duration(self) -> None:
        """Start (or restart) the call-duration counter."""
        self._duration_start = time.monotonic()
        self._duration_label.setVisible(True)
        self._tick_duration()
        self._duration_timer.start()

    def stop_duration(self) -> None:
        self._duration_timer.stop()
        self._duration_start = 0.0

    def _tick_duration(self) -> None:
        if not self._duration_start:
            return
        self._duration_label.setText(
            format_duration(time.monotonic() - self._duration_start))
        self._refresh_network()
        if self._info_label.isVisible():
            self._refresh_info()

    def _refresh_network(self) -> None:
        info = None
        if self._info_provider is not None:
            try:
                info = self._info_provider(self.sid)
            except Exception:  # noqa: BLE001 - diagnostics only
                info = None
        result = network_quality(info)
        self._network_btn.setIcon(network_icon(result["level"], 20))
        self._network_btn.setToolTip(_network_tooltip(result))

    def _on_incoming(self, kbps: int) -> None:
        self.set_incoming_max(kbps)
        self.incoming_requested.emit(self.sid, int(kbps))

    def set_incoming_max(self, kbps: int) -> None:
        """Reflect the incoming REMB cap chosen in Preferences or this menu."""
        self._incoming_max = int(kbps or 0)
        for value, action in self._incoming_actions.items():
            action.setChecked(value == self._incoming_max)

    def set_frame(self, image):
        self._video_view.set_frame(image)
        self._position_pip()

    def _on_mute(self, checked):
        self._muted = checked
        self._mute_btn.setIcon(_icon("mic-off" if checked else "mic"))
        self._mute_btn.setToolTip(
            tr("call_unmute") if checked else tr("call_mute"))
        self.audio_toggled.emit(self.sid, not checked)

    def _on_hear(self, checked):
        self._hear_muted = checked
        self._hear_btn.setIcon(_icon("speaker-off" if checked else "speaker"))
        self._hear_btn.setToolTip(
            tr("call_unmute_peer") if checked else tr("call_mute_peer"))
        self.receive_toggled.emit(self.sid, not checked)

    def set_muted(self, muted: bool) -> None:
        """Reflect a mute state chosen before the call window existed."""
        self._muted = bool(muted)
        self._mute_btn.blockSignals(True)
        self._mute_btn.setChecked(self._muted)
        self._mute_btn.blockSignals(False)
        self._mute_btn.setIcon(_icon("mic-off" if self._muted else "mic"))
        self._mute_btn.setToolTip(
            tr("call_unmute") if self._muted else tr("call_mute"))

    def set_hear_muted(self, muted: bool) -> None:
        """Reflect a remote-audio mute state without re-emitting the signal."""
        self._hear_muted = bool(muted)
        self._hear_btn.blockSignals(True)
        self._hear_btn.setChecked(self._hear_muted)
        self._hear_btn.blockSignals(False)
        self._hear_btn.setIcon(
            _icon("speaker-off" if self._hear_muted else "speaker"))
        self._hear_btn.setToolTip(
            tr("call_unmute_peer") if self._hear_muted
            else tr("call_mute_peer"))

    def _on_pip(self, enabled: bool) -> None:
        self._pip_enabled = bool(enabled) and bool(self._video)
        self._refresh_pip()
        self.pip_toggled.emit(self.sid, self._pip_enabled)

    def is_pip_enabled(self) -> bool:
        return bool(self._pip_enabled)

    def set_pip_enabled(self, enabled: bool) -> None:
        """Apply the PiP preference without re-emitting the toggle signal."""
        if self._failed:
            return
        self._pip_enabled = bool(enabled) and bool(self._video)
        self._pip_btn.blockSignals(True)
        self._pip_btn.setChecked(self._pip_enabled)
        self._pip_btn.blockSignals(False)
        self._refresh_pip()

    def set_local_frame(self, image) -> None:
        """Update the own-video overlay (camera or screen source)."""
        if not self._pip_enabled or not self._video:
            return
        self._pip_view.set_frame(image)
        self._refresh_pip()

    def _refresh_pip(self) -> None:
        self._pip_view.set_mirrored(self._video_mode == "camera")
        self._position_pip()

    def _position_pip(self) -> None:
        if not hasattr(self, "_pip_view"):
            return
        if self._failed:
            self._pip_view.setVisible(False)
            return
        parent = self._video_view
        content = parent.content_rect()
        if (not self._pip_enabled or not self._video
                or self._video_mode == "off"
                or content.width() < 200 or content.height() < 120):
            self._pip_view.setVisible(False)
            return
        width = max(64, min(240, int(content.width() * 0.28)))
        height = max(36, int(round(width * 9 / 16)))
        if height > int(content.height() * 0.45):
            height = max(36, int(content.height() * 0.45))
            width = max(64, int(round(height * 16 / 9)))
        width = min(width, content.width())
        height = min(height, content.height())
        self._pip_view.setGeometry(
            content.right() - width - 12,
            content.top() + 12, width, height)
        self._pip_view.setVisible(True)

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._video_view and event.type() == (
                QtCore.QEvent.Type.Resize):
            QtCore.QTimer.singleShot(0, self._position_pip)
        return super().eventFilter(obj, event)

    def _emit_render_size(self) -> None:
        size = (max(0, self._video_view.width()),
                max(0, self._video_view.height()))
        if not size[0] or not size[1] or size == self._last_render_size:
            return
        self._last_render_size = size
        self.render_size_changed.emit(self.sid, size[0], size[1])

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(0, self._position_pip)
        QtCore.QTimer.singleShot(0, self._position_ended_overlay)
        QtCore.QTimer.singleShot(0, self._emit_render_size)
        QtCore.QTimer.singleShot(0, self._fit_window_height)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._fit_controls()
        self._fit_window_height()
        QtCore.QTimer.singleShot(0, self._emit_render_size)
        self.visibility_changed.emit(self.sid, True)

    def hideEvent(self, event):  # noqa: N802
        super().hideEvent(event)
        self.visibility_changed.emit(self.sid, False)

    def _request_mode(self, mode: str) -> None:
        self.video_mode_requested.emit(self.sid, mode)

    def set_video_mode(self, mode: str) -> None:
        """Reflect the active video source (off/camera/region/screen)."""
        if mode not in _VIDEO_MODE_ICONS:
            mode = "off"
        self._video_mode = mode
        self._video_btn.setIcon(_icon(_VIDEO_MODE_ICONS[mode]))
        self._video_btn.setToolTip(tr(_VIDEO_MODE_TIPS[mode]))
        for m, action in self._video_actions.items():
            action.setChecked(m == mode)
        self._refresh_pip()

    def _on_quality(self, bitrate, height) -> None:
        if bitrate is not None:
            self._quality_bitrate = int(bitrate)
        if height is not None:
            self._quality_height = int(height)
        for value, action in self._quality_bitrate_actions.items():
            action.setChecked(value == self._quality_bitrate)
        for value, action in self._quality_height_actions.items():
            action.setChecked(value == self._quality_height)
        self.quality_requested.emit(
            self.sid, self._quality_bitrate, self._quality_height)

    def closeEvent(self, event):
        # Closing an active window also ends the call; a failed window is
        # already detached from its media session.
        if not self._failed and not self._ended:
            self.hangup.emit(self.sid)
        super().closeEvent(event)


class MujiCallWindow(QtWidgets.QWidget):
    """Conference (Muji) window: video mosaic (left) + participant list
    (right) with per-party audio/camera toggles.

    One window serves both audio and video conferences: the video mosaic is
    visible only when the conference carries a video content.  The participant
    list carries three per-row icon toggles — "send my microphone to this
    participant", "hear this participant" and "send my video to this
    participant" — preceded by the participant's rounded avatar.  Under the
    list a separate row of icon toggles (microphone, speaker, camera) drives
    the same devices for *all* participants at once: the effective per-party
    state is the global layer AND the per-party layer, so the global toggles
    never change the per-party button configuration.
    """

    leave = QtCore.pyqtSignal(str)                      # room
    participant_audio = QtCore.pyqtSignal(str, str, bool)    # room, nick, send-enabled
    participant_receive = QtCore.pyqtSignal(str, str, bool)  # room, nick, receive-enabled
    participant_camera = QtCore.pyqtSignal(str, str, bool)   # room, nick, video-enabled
    video_mode_requested = QtCore.pyqtSignal(str, str)       # room, mode
    quality_requested = QtCore.pyqtSignal(str, int, int)     # room, kbps, px
    incoming_requested = QtCore.pyqtSignal(str, int)         # room, kbps

    def __init__(self, room: str, self_nick: str = "", parent=None,
                 video_bitrate: int = 1000, max_height: int = 0,
                 info_provider=None, incoming_max: int = 0):
        super().__init__(parent)
        self.room = room
        self._quality_bitrate = int(video_bitrate or 0)
        self._quality_height = int(max_height or 0)
        self._info_provider = info_provider
        self._incoming_max = int(incoming_max or 0)
        self.self_nick = self_nick or ""
        self.setWindowTitle(tr("muji_window_title", room=room))
        self.setMinimumSize(560, 400)
        self._mic_state: dict[str, bool] = {}
        self._recv_state: dict[str, bool] = {}
        self._cam_state: dict[str, bool] = {}
        # Global ("all participants") device layer.  The effective per-party
        # state is global AND per-party, so the global toggles never change
        # the per-party button configuration — they are a separate channel.
        self._all_mic = True
        self._all_recv = True
        self._all_cam = True
        self._applied: dict[str, tuple[bool, bool, bool]] = {}
        self._avatar_paths: dict[str, str] = {}
        self._avatar_labels: dict[str, QtWidgets.QLabel] = {}
        self._avatar_radius = 20  # mirrors appearance.avatar_radius
        self._rows: dict[str, QtWidgets.QListWidgetItem] = {}
        layout = QtWidgets.QVBoxLayout(self)

        self._title = QtWidgets.QLabel(room, self)
        self._title.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._title)
        self._info_label = QtWidgets.QLabel("", self)
        self._info_label.setStyleSheet("color: gray;")
        self._info_label.setWordWrap(True)
        self._info_label.setVisible(False)
        layout.addWidget(self._info_label)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self)

        left = QtWidgets.QWidget(splitter)
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._video = _MosaicVideo(left)
        self._video.set_self_nick(self.self_nick)
        left_layout.addWidget(self._video, stretch=1)
        self._video.setVisible(False)

        self._state = QtWidgets.QLabel(tr("call_connecting"), left)
        self._state.setStyleSheet("color: gray;")
        left_layout.addWidget(self._state)

        self._duration_label = QtWidgets.QLabel("", left)
        self._duration_label.setStyleSheet("color: gray;")
        self._duration_label.setVisible(False)
        left_layout.addWidget(self._duration_label)
        self._duration_timer = QtCore.QTimer(self)
        self._duration_timer.setInterval(1000)
        self._duration_timer.timeout.connect(self._tick_duration)
        self._duration_start = 0.0

        right = QtWidgets.QWidget(splitter)
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._list = QtWidgets.QListWidget(right)
        right_layout.addWidget(self._list, stretch=1)

        self._leave_btn = QtWidgets.QToolButton(right)
        self._leave_btn.setIcon(_icon("call-hangup"))
        self._leave_btn.setIconSize(QtCore.QSize(20, 20))
        self._leave_btn.setToolTip(tr("muji_leave"))
        self._leave_btn.clicked.connect(lambda: self.leave.emit(self.room))
        _flat(self._leave_btn)

        controls = QtWidgets.QHBoxLayout()
        self._all_mic_btn = self._icon_toggle(
            right, "mic", "mic-off", True, tr("muji_all_mic_tip"),
            self._on_all_mic)
        self._all_recv_btn = self._icon_toggle(
            right, "speaker", "speaker-off", True, tr("muji_all_hear_tip"),
            self._on_all_recv)
        # One combo button for the outgoing video: off / camera / region /
        # screen (the per-party camera toggles stay a separate layer).
        self._video_mode = "camera"
        self._video_btn = QtWidgets.QToolButton(right)
        self._video_btn.setIcon(_icon(_VIDEO_MODE_ICONS[self._video_mode]))
        self._video_btn.setIconSize(QtCore.QSize(20, 20))
        self._video_btn.setToolTip(tr(_VIDEO_MODE_TIPS[self._video_mode]))
        self._video_btn.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        video_menu = QtWidgets.QMenu(self._video_btn)
        self._video_actions = {}
        for mode in ("off", "camera", "region", "screen"):
            action = video_menu.addAction(
                _icon(_VIDEO_MODE_ICONS[mode]), tr(_VIDEO_MODE_TIPS[mode]),
                lambda checked=False, m=mode: self._on_video_mode(m))
            action.setCheckable(True)
            action.setChecked(mode == self._video_mode)
            self._video_actions[mode] = action
        self._video_btn.setMenu(video_menu)
        _flat(self._video_btn)
        self._video_btn.setVisible(False)
        self._network_btn = QtWidgets.QToolButton(right)
        self._network_btn.setIcon(network_icon(0))
        self._network_btn.setIconSize(QtCore.QSize(20, 20))
        self._network_btn.setAutoRaise(True)
        self._network_btn.setToolTip(tr("call_network_unknown"))
        self._network_btn.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        _network_menu = QtWidgets.QMenu(self._network_btn)
        (self._quality_bitrate_actions,
         self._quality_height_actions) = _add_quality_menus(
            _network_menu, self._quality_bitrate, self._quality_height,
            self._on_quality)
        _inc_menu, self._incoming_actions = _incoming_menu(
            self._network_btn, self._incoming_max)
        for _kbps, _action in self._incoming_actions.items():
            _action.triggered.connect(
                lambda checked=False, value=_kbps: self._on_incoming(value))
        _network_menu.addMenu(_inc_menu)
        self._network_btn.setMenu(_network_menu)
        _flat(self._network_btn)
        controls.addWidget(self._all_mic_btn)
        controls.addWidget(self._all_recv_btn)
        controls.addWidget(self._video_btn)
        controls.addWidget(self._network_btn)
        self._info_btn = _info_toggle(self)
        self._info_btn.toggled.connect(self._toggle_info)
        controls.addWidget(self._info_btn)
        controls.addStretch(1)
        controls.addWidget(self._leave_btn)
        right_layout.addLayout(controls)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([self.width() - 200, 200])
        layout.addWidget(splitter, stretch=1)

    def set_video(self, enabled: bool) -> None:
        self._video.setVisible(enabled)
        self._video_btn.setVisible(enabled)

    def _toggle_info(self, checked: bool) -> None:
        self._info_label.setVisible(bool(checked))
        if checked:
            self._refresh_info()

    def _refresh_info(self) -> None:
        info = None
        if self._info_provider is not None:
            try:
                info = self._info_provider(self.room)
            except Exception:  # noqa: BLE001 - diagnostics only
                info = None
        self._info_label.setText(_format_info_line(info))

    def _on_quality(self, bitrate, height) -> None:
        if bitrate is not None:
            self._quality_bitrate = int(bitrate)
        if height is not None:
            self._quality_height = int(height)
        for value, action in self._quality_bitrate_actions.items():
            action.setChecked(value == self._quality_bitrate)
        for value, action in self._quality_height_actions.items():
            action.setChecked(value == self._quality_height)
        self.quality_requested.emit(
            self.room, self._quality_bitrate, self._quality_height)

    def _on_video_mode(self, mode: str) -> None:
        """Pick the outgoing video source for the whole conference."""
        self.set_video_mode(mode)
        self._all_cam = mode != "off"
        self._sync_states()
        self.video_mode_requested.emit(self.room, mode)

    def set_video_mode(self, mode: str) -> None:
        """Reflect the active video source (off/camera/region/screen)."""
        if mode not in _VIDEO_MODE_ICONS:
            mode = "off"
        self._video_mode = mode
        self._video_btn.setIcon(_icon(_VIDEO_MODE_ICONS[mode]))
        self._video_btn.setToolTip(tr(_VIDEO_MODE_TIPS[mode]))
        for m, action in self._video_actions.items():
            action.setChecked(m == mode)

    def start_duration(self) -> None:
        """Start (or restart) the conference-duration counter."""
        self._duration_start = time.monotonic()
        self._duration_label.setVisible(True)
        self._tick_duration()
        self._duration_timer.start()

    def stop_duration(self) -> None:
        self._duration_timer.stop()
        self._duration_start = 0.0

    def _tick_duration(self) -> None:
        if not self._duration_start:
            return
        self._duration_label.setText(
            format_duration(time.monotonic() - self._duration_start))
        self._refresh_network()
        if self._info_label.isVisible():
            self._refresh_info()

    def _refresh_network(self) -> None:
        info = None
        if self._info_provider is not None:
            try:
                info = self._info_provider(self.room)
            except Exception:  # noqa: BLE001 - diagnostics only
                info = None
        result = network_quality(info)
        self._network_btn.setIcon(network_icon(result["level"], 20))
        self._network_btn.setToolTip(_network_tooltip(result))

    def _on_incoming(self, kbps: int) -> None:
        self.set_incoming_max(kbps)
        self.incoming_requested.emit(self.room, int(kbps))

    def set_incoming_max(self, kbps: int) -> None:
        self._incoming_max = int(kbps or 0)
        for value, action in self._incoming_actions.items():
            action.setChecked(value == self._incoming_max)

    def set_self_nick(self, nick: str) -> None:
        """Update our own conference nick (labels the mirrored self tile)."""
        self.self_nick = nick or ""
        self._video.set_self_nick(self.self_nick)

    def set_participants(self, participants: list):
        current = {self._list.item(i).data(256)
                   for i in range(self._list.count())}
        # Drop rows for nicks that are no longer present.
        for nick in list(self._rows):
            if nick not in participants:
                item = self._rows.pop(nick)
                self._list.takeItem(self._list.row(item))
                self._video.remove_nick(nick)
                self._avatar_labels.pop(nick, None)
                # A rejoining participant gets a fresh session, so drop the
                # applied-state record to re-apply it later.
                self._applied.pop(nick, None)
        for nick in participants:
            if nick in current:
                continue
            item = QtWidgets.QListWidgetItem(self._list)
            item.setData(256, nick)
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
            item.setSizeHint(QtCore.QSize(0, 34))
            self._rows[nick] = item
            self._list.setItemWidget(item, self._make_row(nick))
        self._state.setText(tr("muji_participants", count=len(participants)))
        self._sync_states(list(participants))

    def set_avatars(self, avatars: dict) -> None:
        """Apply nick -> avatar cache path (the default is kept when absent)."""
        for nick, path in (avatars or {}).items():
            if not path:
                continue
            self._avatar_paths[nick] = path
            label = self._avatar_labels.get(nick)
            if label is not None:
                pix = _rounded_avatar(path, radius_pct=self._avatar_radius)
                if not pix.isNull():
                    label.setPixmap(pix)

    def set_avatar_radius(self, radius_pct: int) -> None:
        """Re-render participant avatars with a new corner rounding."""
        self._avatar_radius = max(0, min(100, int(radius_pct or 0)))
        for nick, label in self._avatar_labels.items():
            pix = _rounded_avatar(
                self._avatar_paths.get(nick) or default_avatar(),
                radius_pct=self._avatar_radius)
            if not pix.isNull():
                label.setPixmap(pix)

    def apply_states(self, nick: str) -> None:
        """Force the effective device states onto one participant.

        Called when a participant's engine call is bound *after* its row was
        created, so a global mute/camera set earlier reaches that session.
        """
        self._sync_states([nick], force=True)

    def set_frame(self, nick: str, image) -> None:
        self._video.set_frame(nick, image)

    def set_local_frame(self, image) -> None:
        """Feed this conference's own camera preview (mirrored self tile)."""
        if self.self_nick:
            self._video.set_frame(self.self_nick, image)

    def _make_row(self, nick: str) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget(self._list)
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(4, 2, 4, 2)
        avatar = QtWidgets.QLabel(row)
        avatar.setFixedSize(24, 24)
        avatar.setPixmap(_rounded_avatar(
            self._avatar_paths.get(nick) or default_avatar(),
            radius_pct=self._avatar_radius))
        self._avatar_labels[nick] = avatar
        layout.addWidget(avatar)
        name = QtWidgets.QLabel(nick, row)
        name.setStyleSheet("font-weight: bold;")
        layout.addWidget(name)
        layout.addStretch(1)

        layout.addWidget(self._icon_toggle(
            row, "mic", "mic-off", self._mic_state.get(nick, True),
            tr("muji_party_mic_tip"),
            lambda on, n=nick: self._on_mic_toggle(n, on)))
        layout.addWidget(self._icon_toggle(
            row, "speaker", "speaker-off", self._recv_state.get(nick, True),
            tr("muji_party_hear_tip"),
            lambda on, n=nick: self._on_recv_toggle(n, on)))
        layout.addWidget(self._icon_toggle(
            row, "camera", "camera-off", self._cam_state.get(nick, True),
            tr("muji_party_cam_tip"),
            lambda on, n=nick: self._on_cam_toggle(n, on)))
        return row

    @staticmethod
    def _icon_toggle(parent, on_name: str, off_name: str, checked: bool,
                     tip: str, handler) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton(parent)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setIcon(_icon(on_name if checked else off_name))
        button.setIconSize(QtCore.QSize(16, 16))
        button.setToolTip(tip)
        _flat(button)

        def _toggled(on: bool, b=button, a=on_name, o=off_name):
            b.setIcon(_icon(a if on else o))
            handler(on)

        button.toggled.connect(_toggled)
        return button

    def _on_mic_toggle(self, nick: str, enabled: bool) -> None:
        self._mic_state[nick] = enabled
        self._sync_states([nick])

    def _on_recv_toggle(self, nick: str, enabled: bool) -> None:
        self._recv_state[nick] = enabled
        self._sync_states([nick])

    def _on_cam_toggle(self, nick: str, enabled: bool) -> None:
        self._cam_state[nick] = enabled
        self._sync_states([nick])

    def _on_all_mic(self, enabled: bool) -> None:
        self._all_mic = enabled
        self._sync_states()

    def _on_all_recv(self, enabled: bool) -> None:
        self._all_recv = enabled
        self._sync_states()

    def _effective(self, nick: str) -> tuple[bool, bool, bool]:
        """The device states actually applied to a participant."""
        return (
            self._all_mic and self._mic_state.get(nick, True),
            self._all_recv and self._recv_state.get(nick, True),
            self._all_cam and self._cam_state.get(nick, True),
        )

    def _sync_states(self, nicks: list | None = None,
                     force: bool = False) -> None:
        """Emit the effective states, per channel, only when they changed.

        *force* re-applies every channel (a newly bound session that never saw
        the earlier emissions).
        """
        if nicks is None:
            nicks = list(self._rows)
        for nick in nicks:
            if nick not in self._rows:
                continue
            eff = self._effective(nick)
            prev = self._applied.get(nick, (True, True, True))
            if force or eff[0] != prev[0]:
                self.participant_audio.emit(self.room, nick, eff[0])
            if force or eff[1] != prev[1]:
                self.participant_receive.emit(self.room, nick, eff[1])
            if force or eff[2] != prev[2]:
                self.participant_camera.emit(self.room, nick, eff[2])
            self._applied[nick] = eff

    def closeEvent(self, event):
        self.leave.emit(self.room)
        super().closeEvent(event)


class _MujiTile(VideoView):
    """A VideoView that reports its conference nick when clicked."""

    activated = QtCore.pyqtSignal(str)

    def __init__(self, nick: str, min_size=(128, 96), clickable=True,
                 parent=None):
        super().__init__(parent)
        self.nick = nick
        self._clickable = clickable
        self.setMinimumSize(*min_size)
        self.set_caption(nick)

    def mousePressEvent(self, event):
        if self._clickable:
            self.activated.emit(self.nick)
        super().mousePressEvent(event)


class _MosaicVideo(QtWidgets.QWidget):
    """Video mosaic for a Muji conference.

    Grid mode shows one tile per video participant (including our own mirrored
    tile).  Clicking a tile switches to single-participant mode: the clicked
    participant fills the widget while the others shrink into a strip at the
    bottom; the "back" button returns to the grid.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._self_nick = ""
        self._grid_holder = QtWidgets.QStackedWidget(self)
        grid_page = QtWidgets.QWidget(self._grid_holder)
        self._grid = QtWidgets.QGridLayout(grid_page)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(2)
        zoom_page = QtWidgets.QWidget(self._grid_holder)
        zv = QtWidgets.QVBoxLayout(zoom_page)
        zv.setContentsMargins(0, 0, 0, 0)
        self._big = _MujiTile("", min_size=(320, 180), clickable=False,
                              parent=zoom_page)
        zv.addWidget(self._big, stretch=1)
        self._strip = QtWidgets.QWidget(zoom_page)
        self._strip_layout = QtWidgets.QHBoxLayout(self._strip)
        self._strip_layout.setContentsMargins(0, 0, 0, 0)
        self._strip_layout.setSpacing(2)
        zv.addWidget(self._strip)
        self._back_btn = _flat(QtWidgets.QPushButton(
            tr("muji_video_back"), zoom_page))
        self._back_btn.clicked.connect(self._show_grid)
        zv.addWidget(self._back_btn)
        self._grid_holder.addWidget(grid_page)
        self._grid_holder.addWidget(zoom_page)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._grid_holder)

        self._tiles: dict[str, _MujiTile] = {}
        self._strip_tiles: dict[str, _MujiTile] = {}
        self._latest: dict[str, object] = {}
        self._zoomed: str | None = None

    # ── tiles ────────────────────────────────────────────────────
    def _make_tile(self, nick: str, min_size=(128, 96), parent=None,
                   clickable=True) -> _MujiTile:
        tile = _MujiTile(nick, min_size=min_size, clickable=clickable,
                         parent=parent or self._grid_holder.widget(0))
        tile.set_mirrored(nick == self._self_nick)
        tile.activated.connect(self._zoom_to)
        return tile

    def set_self_nick(self, nick: str) -> None:
        self._self_nick = nick or ""
        if self._self_nick and self._self_nick not in self._tiles:
            self._tiles[self._self_nick] = self._make_tile(self._self_nick)
            self._relayout()

    # ── frames ───────────────────────────────────────────────────
    def set_frame(self, nick: str, image) -> None:
        if nick not in self._latest:
            self._latest[nick] = image
        if nick not in self._tiles:
            self._tiles[nick] = self._make_tile(nick)
            self._relayout()
        self._tiles[nick].set_caption(nick)
        self._tiles[nick].set_frame(image)
        if self._zoomed == nick:
            self._big.set_caption(nick)
            self._big.set_frame(image)
        strip = self._strip_tiles.get(nick)
        if strip is not None:
            strip.set_frame(image)

    def remove_nick(self, nick: str) -> None:
        if nick == self._self_nick:
            return
        self._latest.pop(nick, None)
        tile = self._tiles.pop(nick, None)
        if tile is not None:
            tile.setParent(None)
            tile.deleteLater()
        if self._zoomed == nick:
            # The enlarged participant left — fall back to the grid.
            self._show_grid()
        self._relayout()

    # ── layout ───────────────────────────────────────────────────
    def _relayout(self) -> None:
        nicks = sorted(self._tiles)
        cols = max(1, int(math.ceil(len(nicks) ** 0.5)))
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
        for i, nick in enumerate(nicks):
            self._grid.addWidget(self._tiles[nick], i // cols, i % cols)
            self._tiles[nick].show()

    def _zoom_to(self, nick: str) -> None:
        if self._zoomed == nick:
            return
        self._zoomed = nick
        while self._strip_layout.count():
            item = self._strip_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._strip_tiles.clear()
        for other in sorted(self._tiles):
            if other == nick:
                continue
            tile = self._make_tile(other, min_size=(80, 60),
                                   parent=self._strip)
            tile.set_frame(self._latest.get(other))
            self._strip_layout.addWidget(tile)
            self._strip_tiles[other] = tile
        self._big.nick = nick
        self._big.set_caption(nick)
        self._big.set_mirrored(nick == self._self_nick)
        self._big.set_frame(self._latest.get(nick))
        self._grid_holder.setCurrentIndex(1)

    def _show_grid(self) -> None:
        self._zoomed = None
        self._grid_holder.setCurrentIndex(0)
