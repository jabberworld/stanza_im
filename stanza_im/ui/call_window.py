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

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.avatars import default_avatar
from stanza_im.include.constants import ACTIONS_DIR_16

logger = logging.getLogger("stanza_im.call.ui")

_ICON_CACHE: dict[str, QtGui.QIcon] = {}


def _icon(name: str) -> QtGui.QIcon:
    """Load a 16px action glyph (SVG preferred) for the call controls."""
    icon = _ICON_CACHE.get(name)
    if icon is None:
        icon = QtGui.QIcon()
        for ext in ("svg", "png"):
            path = os.path.join(ACTIONS_DIR_16, f"{name}.{ext}")
            if os.path.exists(path):
                candidate = QtGui.QIcon(path)
                if not candidate.isNull():
                    icon = candidate
                    break
        _ICON_CACHE[name] = icon
    return icon


def _rounded_avatar(path: str, size: int = 24) -> QtGui.QPixmap:
    """Return a circular, scaled avatar pixmap from *path*."""
    pix = QtGui.QPixmap(path)
    if pix.isNull():
        return pix
    scaled = pix.scaled(
        size, size, QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        QtCore.Qt.TransformationMode.SmoothTransformation)
    rounded = QtGui.QPixmap(size, size)
    rounded.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(rounded)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    clip = QtGui.QPainterPath()
    clip.addEllipse(0, 0, size, size)
    painter.setClipPath(clip)
    x = (scaled.width() - size) // 2
    y = (scaled.height() - size) // 2
    painter.drawPixmap(-x, -y, scaled)
    painter.end()
    return rounded


class VideoView(QtWidgets.QLabel):
    """Paints decoded video frames with an overlay nickname caption."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
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

    def set_caption(self, text: str) -> None:
        self._caption = text or ""
        self.update()

    def set_mirrored(self, mirrored: bool) -> None:
        self._mirrored = bool(mirrored)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = None
        if self._image is not None:
            painter = QtGui.QPainter(self)
            scaled = self._image.scaled(
                self.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            if self._mirrored:
                painter.translate(self.width(), 0)
                painter.scale(-1, 1)
            painter.drawImage(x, y, scaled)
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

    def __init__(self, caller: str, media_kind: str = "audio", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("call_incoming_title"))
        self._video = media_kind == "video"
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(
            tr("call_incoming_text", caller=caller,
               kind=tr("call_video" if self._video else "call_audio")), self)
        label.setWordWrap(True)
        layout.addWidget(label)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._accept = QtWidgets.QPushButton(self)
        self._accept.setIcon(_icon("call-accept"))
        self._accept.setIconSize(QtCore.QSize(22, 22))
        self._accept.setToolTip(tr("call_accept"))
        self._accept.setDefault(True)
        self._reject = QtWidgets.QPushButton(self)
        self._reject.setIcon(_icon("call-hangup"))
        self._reject.setIconSize(QtCore.QSize(22, 22))
        self._reject.setToolTip(tr("call_reject"))
        buttons.addWidget(self._accept)
        buttons.addWidget(self._reject)
        layout.addLayout(buttons)
        self._accept.clicked.connect(self._on_accept)
        self._reject.clicked.connect(self._on_reject)

    def _on_accept(self):
        self.decision.emit(True, self._video)
        self.accept()

    def _on_reject(self):
        self.decision.emit(False, False)
        self.reject()


class CallWindow(QtWidgets.QWidget):
    """Active call window with remote video and icon-only controls."""

    hangup = QtCore.pyqtSignal(str)          # sid
    audio_toggled = QtCore.pyqtSignal(str, bool)    # outgoing audio enabled
    camera_toggled = QtCore.pyqtSignal(str, bool)   # outgoing video enabled

    def __init__(self, sid: str, peer: str, video: bool = False, parent=None):
        super().__init__(parent)
        self.sid = sid
        self.peer = peer
        self._video = video
        self.setWindowTitle(tr("call_window_title", peer=peer))
        self.setMinimumSize(420, 340)
        self._muted = False
        self._camera_on = video

        layout = QtWidgets.QVBoxLayout(self)
        self._title = QtWidgets.QLabel(peer, self)
        self._title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self._title)

        self._state = QtWidgets.QLabel(tr("call_connecting"), self)
        self._state.setStyleSheet("color: gray;")
        layout.addWidget(self._state)

        self._video_view = VideoView(self)
        self._video_view.set_caption(peer)
        layout.addWidget(self._video_view, stretch=1)
        if not video:
            self._video_view.setVisible(False)

        controls = QtWidgets.QHBoxLayout()
        self._mute_btn = QtWidgets.QToolButton(self)
        self._mute_btn.setIcon(_icon("mic"))
        self._mute_btn.setIconSize(QtCore.QSize(20, 20))
        self._mute_btn.setToolTip(tr("call_mute"))
        self._mute_btn.setCheckable(True)
        self._mute_btn.toggled.connect(self._on_mute)
        controls.addWidget(self._mute_btn)

        self._cam_btn = QtWidgets.QToolButton(self)
        self._cam_btn.setIcon(_icon("camera"))
        self._cam_btn.setIconSize(QtCore.QSize(20, 20))
        self._cam_btn.setToolTip(tr("call_camera"))
        self._cam_btn.setCheckable(True)
        self._cam_btn.setChecked(video)
        self._cam_btn.setVisible(video)
        self._cam_btn.toggled.connect(self._on_camera)
        controls.addWidget(self._cam_btn)
        controls.addStretch(1)

        self._hangup_btn = QtWidgets.QToolButton(self)
        self._hangup_btn.setIcon(_icon("call-hangup"))
        self._hangup_btn.setIconSize(QtCore.QSize(20, 20))
        self._hangup_btn.setToolTip(tr("call_hangup"))
        self._hangup_btn.clicked.connect(lambda: self.hangup.emit(self.sid))
        controls.addWidget(self._hangup_btn)
        layout.addLayout(controls)

    def set_state(self, text: str):
        self._state.setText(text)

    def set_frame(self, image):
        self._video_view.set_frame(image)

    def _on_mute(self, checked):
        self._muted = checked
        self._mute_btn.setIcon(_icon("mic-off" if checked else "mic"))
        self._mute_btn.setToolTip(
            tr("call_unmute") if checked else tr("call_mute"))
        self.audio_toggled.emit(self.sid, not checked)

    def _on_camera(self, checked):
        self._camera_on = checked
        self._cam_btn.setIcon(_icon("camera" if checked else "camera-off"))
        self._cam_btn.setToolTip(
            tr("call_camera") if checked else tr("call_camera_off"))
        self.camera_toggled.emit(self.sid, checked)

    def closeEvent(self, event):
        # Closing the window also ends the call.
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

    def __init__(self, room: str, self_nick: str = "", parent=None):
        super().__init__(parent)
        self.room = room
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
        self._rows: dict[str, QtWidgets.QListWidgetItem] = {}
        layout = QtWidgets.QVBoxLayout(self)

        self._title = QtWidgets.QLabel(room, self)
        self._title.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._title)

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

        controls = QtWidgets.QHBoxLayout()
        self._all_mic_btn = self._icon_toggle(
            right, "mic", "mic-off", True, tr("muji_all_mic_tip"),
            self._on_all_mic)
        self._all_recv_btn = self._icon_toggle(
            right, "speaker", "speaker-off", True, tr("muji_all_hear_tip"),
            self._on_all_recv)
        self._all_cam_btn = self._icon_toggle(
            right, "camera", "camera-off", True, tr("muji_all_cam_tip"),
            self._on_all_cam)
        self._all_cam_btn.setVisible(False)
        controls.addWidget(self._all_mic_btn)
        controls.addWidget(self._all_recv_btn)
        controls.addWidget(self._all_cam_btn)
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
        self._all_cam_btn.setVisible(enabled)

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
                pix = _rounded_avatar(path)
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
            self._avatar_paths.get(nick) or default_avatar()))
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

    def _on_all_cam(self, enabled: bool) -> None:
        self._all_cam = enabled
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
        self._back_btn = QtWidgets.QPushButton(tr("muji_video_back"),
                                               zoom_page)
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
