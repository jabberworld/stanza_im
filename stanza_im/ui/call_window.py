"""Call UI: incoming-call prompt and the active-call window.

The window paints decoded remote video frames (QImage from
:mod:`stanza_im.xmpp.media`) and exposes simple controls (mute, camera,
hang up).  It is deliberately free of Qt Multimedia imports so it also works
where Qt Multimedia cannot load.
"""
from __future__ import annotations

import logging

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
    mute_toggled = QtCore.pyqtSignal(str, bool)
    video_toggled = QtCore.pyqtSignal(str, bool)

    def __init__(self, sid: str, peer: str, video: bool = False, parent=None):
        super().__init__(parent)
        self.sid = sid
        self.peer = peer
        self._video = video
        self.setWindowTitle(tr("call_window_title", peer=peer))
        self.setMinimumSize(420, 340)
        self._muted = False
        self._video_on = video

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
        self._cam_btn.toggled.connect(self._on_video)
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
        self.mute_toggled.emit(self.sid, checked)

    def _on_video(self, checked):
        self._video_on = checked
        self._video_view.setVisible(checked)
        self.video_toggled.emit(self.sid, checked)

    def closeEvent(self, event):
        # Closing the window also ends the call.
        self.hangup.emit(self.sid)
        super().closeEvent(event)


class MujiCallWindow(QtWidgets.QWidget):
    """Conference (Muji) window: participants, status and leave."""

    leave = QtCore.pyqtSignal(str)   # room

    def __init__(self, room: str, parent=None):
        super().__init__(parent)
        self.room = room
        self.setWindowTitle(tr("muji_window_title", room=room))
        self.setMinimumSize(360, 300)
        layout = QtWidgets.QVBoxLayout(self)
        self._title = QtWidgets.QLabel(room, self)
        self._title.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._title)
        self._state = QtWidgets.QLabel(tr("call_connecting"), self)
        self._state.setStyleSheet("color: gray;")
        layout.addWidget(self._state)
        self._list = QtWidgets.QListWidget(self)
        layout.addWidget(self._list, stretch=1)
        self._leave_btn = QtWidgets.QPushButton(tr("muji_leave"), self)
        self._leave_btn.clicked.connect(lambda: self.leave.emit(self.room))
        layout.addWidget(self._leave_btn)

    def set_participants(self, participants: list):
        self._list.clear()
        for nick in participants:
            self._list.addItem(nick)
        self._state.setText(tr("muji_participants",
                               count=len(participants)))

    def closeEvent(self, event):
        self.leave.emit(self.room)
        super().closeEvent(event)
