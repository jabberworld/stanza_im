"""Call UI: incoming-call prompt and the active-call window.

The window paints decoded remote video frames (QImage from
:mod:`stanza_im.xmpp.media`) and exposes simple controls (mute, camera,
hang up).  It is deliberately free of Qt Multimedia imports so it also works
where Qt Multimedia cannot load.
"""
from __future__ import annotations

import logging
import math

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr

logger = logging.getLogger("stanza_im.call.ui")


class VideoView(QtWidgets.QLabel):
    """Paints decoded remote video frames."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#101010; color:#888;")
        self.setText(tr("call_no_video"))
        self._image = None

    def set_frame(self, image):
        self._image = image
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._image is None:
            return
        painter = QtGui.QPainter(self)
        scaled = self._image.scaled(
            self.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawImage(x, y, scaled)


class IncomingCallDialog(QtWidgets.QDialog):
    """Prompt shown for an incoming call offer."""

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
        self._accept = QtWidgets.QPushButton(tr("call_accept"), self)
        self._reject = QtWidgets.QPushButton(tr("call_reject"), self)
        self._accept.setDefault(True)
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
    """Active call window with remote video and controls."""

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
        layout.addWidget(self._video_view, stretch=1)
        if not video:
            self._video_view.setVisible(False)

        controls = QtWidgets.QHBoxLayout()
        self._mute_btn = QtWidgets.QToolButton(self)
        self._mute_btn.setText(tr("call_mute"))
        self._mute_btn.setCheckable(True)
        self._mute_btn.toggled.connect(self._on_mute)
        controls.addWidget(self._mute_btn)

        self._cam_btn = QtWidgets.QToolButton(self)
        self._cam_btn.setText(tr("call_camera"))
        self._cam_btn.setCheckable(True)
        self._cam_btn.setChecked(video)
        self._cam_btn.setVisible(video)
        self._cam_btn.toggled.connect(self._on_camera)
        controls.addWidget(self._cam_btn)
        controls.addStretch(1)

        self._hangup_btn = QtWidgets.QPushButton(tr("call_hangup"), self)
        self._hangup_btn.clicked.connect(lambda: self.hangup.emit(self.sid))
        controls.addWidget(self._hangup_btn)
        layout.addLayout(controls)

    def set_state(self, text: str):
        self._state.setText(text)

    def set_frame(self, image):
        self._video_view.set_frame(image)

    def _on_mute(self, checked):
        self._muted = checked
        self._mute_btn.setText(tr("call_unmute") if checked else tr("call_mute"))
        self.audio_toggled.emit(self.sid, not checked)

    def _on_camera(self, checked):
        self._camera_on = checked
        self._cam_btn.setText(tr("call_camera_off") if not checked
                              else tr("call_camera"))
        self.camera_toggled.emit(self.sid, checked)

    def closeEvent(self, event):
        # Closing the window also ends the call.
        self.hangup.emit(self.sid)
        super().closeEvent(event)


class MujiCallWindow(QtWidgets.QWidget):
    """Conference (Muji) window: video mosaic + participant list + per-party
    audio toggles.

    One window serves both audio and video conferences: the video mosaic is
    visible only when the conference carries a video content, the participant
    list always carries two per-row toggles — "send my microphone to this
    participant" and "hear this participant".
    """

    leave = QtCore.pyqtSignal(str)                      # room
    participant_audio = QtCore.pyqtSignal(str, str, bool)    # room, nick, send-enabled
    participant_receive = QtCore.pyqtSignal(str, str, bool)  # room, nick, receive-enabled

    def __init__(self, room: str, parent=None):
        super().__init__(parent)
        self.room = room
        self.setWindowTitle(tr("muji_window_title", room=room))
        self.setMinimumSize(520, 400)
        self._mic_state: dict[str, bool] = {}
        self._recv_state: dict[str, bool] = {}
        self._rows: dict[str, QtWidgets.QListWidgetItem] = {}
        layout = QtWidgets.QVBoxLayout(self)

        self._title = QtWidgets.QLabel(room, self)
        self._title.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._title)

        self._video = _MosaicVideo(self)
        layout.addWidget(self._video, stretch=1)
        self._video.setVisible(False)

        self._state = QtWidgets.QLabel(tr("call_connecting"), self)
        self._state.setStyleSheet("color: gray;")
        layout.addWidget(self._state)

        self._list = QtWidgets.QListWidget(self)
        layout.addWidget(self._list, stretch=1)

        self._leave_btn = QtWidgets.QPushButton(tr("muji_leave"), self)
        self._leave_btn.clicked.connect(lambda: self.leave.emit(self.room))
        layout.addWidget(self._leave_btn)

    def set_video(self, enabled: bool) -> None:
        self._video.setVisible(enabled)

    def set_participants(self, participants: list):
        current = {self._list.item(i).data(256)
                   for i in range(self._list.count())}
        # Drop rows for nicks that are no longer present.
        for nick in list(self._rows):
            if nick not in participants:
                item = self._rows.pop(nick)
                self._list.takeItem(self._list.row(item))
                self._video.remove_nick(nick)
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

    def set_frame(self, nick: str, image) -> None:
        self._video.set_frame(nick, image)

    def _make_row(self, nick: str) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget(self._list)
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(4, 2, 4, 2)
        name = QtWidgets.QLabel(nick, row)
        name.setStyleSheet("font-weight: bold;")
        layout.addWidget(name)
        layout.addStretch(1)

        mic = QtWidgets.QPushButton(
            tr("muji_party_mic_off"), row) \
            if self._mic_state.get(nick, True) is False \
            else QtWidgets.QPushButton(tr("muji_party_mic"), row)
        mic.setCheckable(True)
        mic.setChecked(self._mic_state.get(nick, True))
        mic.setToolTip(tr("muji_party_mic_tip"))
        mic.toggled.connect(
            lambda on, n=nick, b=mic: self._on_mic_toggle(n, on, b))
        layout.addWidget(mic)

        recv = QtWidgets.QPushButton(
            tr("muji_party_hear_off"), row) \
            if self._recv_state.get(nick, True) is False \
            else QtWidgets.QPushButton(tr("muji_party_hear"), row)
        recv.setCheckable(True)
        recv.setChecked(self._recv_state.get(nick, True))
        recv.setToolTip(tr("muji_party_hear_tip"))
        recv.toggled.connect(
            lambda on, n=nick, b=recv: self._on_recv_toggle(n, on, b))
        layout.addWidget(recv)
        return row

    def _on_mic_toggle(self, nick: str, enabled: bool,
                       button: QtWidgets.QPushButton) -> None:
        self._mic_state[nick] = enabled
        button.setText(tr("muji_party_mic" if enabled
                          else "muji_party_mic_off"))
        self.participant_audio.emit(self.room, nick, enabled)

    def _on_recv_toggle(self, nick: str, enabled: bool,
                        button: QtWidgets.QPushButton) -> None:
        self._recv_state[nick] = enabled
        button.setText(tr("muji_party_hear" if enabled
                          else "muji_party_hear_off"))
        self.participant_receive.emit(self.room, nick, enabled)

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

    def mousePressEvent(self, event):
        if self._clickable:
            self.activated.emit(self.nick)
        super().mousePressEvent(event)


class _MosaicVideo(QtWidgets.QWidget):
    """Video mosaic for a Muji conference.

    Grid mode shows one tile per video participant.  Clicking a tile switches
    to single-participant mode: the clicked participant fills the widget while
    the others shrink into a strip at the bottom; the "back" button returns to
    the grid.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
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

    # ── frames ───────────────────────────────────────────────────
    def set_frame(self, nick: str, image) -> None:
        if nick not in self._latest:
            self._latest[nick] = image
        if nick not in self._tiles:
            tile = _MujiTile(nick, parent=self._grid_holder.widget(0))
            tile.activated.connect(self._zoom_to)
            self._tiles[nick] = tile
            self._relayout()
        self._tiles[nick].set_frame(image)
        if self._zoomed == nick:
            self._big.set_frame(image)
        strip = self._strip_tiles.get(nick)
        if strip is not None:
            strip.set_frame(image)

    def remove_nick(self, nick: str) -> None:
        self._latest.pop(nick, None)
        tile = self._tiles.pop(nick, None)
        if tile is not None:
            tile.setParent(None)
            tile.deleteLater()
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
            tile = _MujiTile(other, min_size=(80, 60), parent=self._strip)
            tile.activated.connect(self._zoom_to)
            tile.set_frame(self._latest.get(other))
            self._strip_layout.addWidget(tile)
            self._strip_tiles[other] = tile
        self._big.nick = nick
        self._big.set_frame(self._latest.get(nick))
        self._grid_holder.setCurrentIndex(1)

    def _show_grid(self) -> None:
        self._zoomed = None
        self._grid_holder.setCurrentIndex(0)
