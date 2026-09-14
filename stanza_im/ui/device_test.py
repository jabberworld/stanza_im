"""Device self-tests for Preferences → Devices.

Three small helpers back the "test" controls of the Devices page:

* :class:`MicrophoneTester` opens the selected input and emits a live peak
  level so the user can see whether the microphone actually captures;
* :class:`SpeakerTester` plays a short generated tone on the selected output;
* :class:`CameraPreviewDialog` shows a live camera preview.

They reuse the same format negotiation as calls (:mod:`stanza_im.xmpp.media`),
so a device that works here will also work during a call.
"""
from __future__ import annotations

import logging

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr
from stanza_im.xmpp import media

logger = logging.getLogger("stanza_im.ui.device_test")

TONE_SECONDS = 1.2


class MicrophoneTester(QtCore.QObject):
    """Reads the selected microphone and reports its peak level (0.0–1.0)."""

    level = QtCore.pyqtSignal(float)
    running_changed = QtCore.pyqtSignal(bool)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None
        self._io = None
        self._fmt = None
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._poll)

    def is_running(self) -> bool:
        return self._timer.isActive()

    def format_text(self) -> str:
        return media.audio_format_info(self._fmt) if self._fmt is not None else ""

    def start(self, device_id: str = "") -> bool:
        if self.is_running():
            return True
        source, io, fmt, name, error = media.open_audio_source(device_id)
        if io is None:
            if source is not None:
                try:
                    source.stop()
                except Exception:
                    pass
            self.failed.emit(error or "unknown")
            return False
        self._source, self._io, self._fmt = source, io, fmt
        try:
            io.readyRead.connect(self._poll)
        except Exception:
            logger.debug("mic test io has no readyRead", exc_info=True)
        self._timer.start()
        self.running_changed.emit(True)
        return True

    def stop(self) -> None:
        if not self.is_running() and self._source is None:
            return
        self._timer.stop()
        self._io = None
        if self._source is not None:
            try:
                self._source.stop()
            except Exception:
                logger.debug("mic test stop failed", exc_info=True)
        self._source = None
        self._fmt = None
        self.level.emit(0.0)
        self.running_changed.emit(False)

    def _poll(self) -> None:
        io = self._io
        if io is None:
            return
        source = self._source
        if source is not None:
            error = media._audio_error(source)
            if error:
                logger.warning("CALL mic test error: %s", error)
                self.failed.emit(error)
                self.stop()
                return
        try:
            # Never gate on io.bytesAvailable(): the QIODevice returned by
            # QAudioSource.start() can report 0 even while audio is being
            # captured, which froze the meter (and the call's mic track).
            data = bytes(io.read(16384))
        except RuntimeError:
            self.stop()
            return
        if data:
            self.level.emit(media.peak_level(data, self._fmt))


class SpeakerTester(QtCore.QObject):
    """Plays a short tone on the selected speaker."""

    failed = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sink = None
        self._io = None
        self._stop_timer = None

    def play(self, device_id: str = "") -> bool:
        self.stop()
        sink, io, fmt, name, error = media.open_audio_sink(device_id)
        if io is None:
            if sink is not None:
                try:
                    sink.stop()
                except Exception:
                    pass
            self.failed.emit(error or "unknown")
            return False
        self._sink, self._io = sink, io
        try:
            self._io.write(media.tone_pcm(TONE_SECONDS, fmt=fmt))
        except Exception as exc:
            self.failed.emit(str(exc))
            self.stop()
            return False
        self._stop_timer = QtCore.QTimer(self)
        self._stop_timer.setSingleShot(True)
        self._stop_timer.timeout.connect(self._on_finished)
        self._stop_timer.start(int((TONE_SECONDS + 0.3) * 1000))
        return True

    def _on_finished(self) -> None:
        self.stop()
        self.finished.emit()

    def stop(self) -> None:
        if self._stop_timer is not None:
            self._stop_timer.stop()
            self._stop_timer = None
        self._io = None
        if self._sink is not None:
            try:
                self._sink.stop()
            except Exception:
                logger.debug("speaker test stop failed", exc_info=True)
        self._sink = None


class CameraPreviewDialog(QtWidgets.QDialog):
    """Live preview of the selected camera (Qt Multimedia)."""

    def __init__(self, device_id: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("prefs_device_test_camera_title"))
        self.resize(480, 360)
        self._camera = None
        self._session = None
        self._video_widget = None
        layout = QtWidgets.QVBoxLayout(self)
        try:
            from PyQt6.QtMultimediaWidgets import QVideoWidget
        except Exception:
            QVideoWidget = None
        if QVideoWidget is None or not media.HAS_QTMM:
            label = QtWidgets.QLabel(tr("prefs_device_test_unavailable"))
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            return
        try:
            from PyQt6.QtMultimedia import QCamera, QMediaCaptureSession
            device = media._find_device(
                media.QMediaDevices.videoInputs(), device_id)
            self._camera = QCamera(device) if device else QCamera()
            self._video_widget = QVideoWidget()
            layout.addWidget(self._video_widget)
            self._session = QMediaCaptureSession()
            self._session.setCamera(self._camera)
            self._session.setVideoOutput(self._video_widget)
            self._camera.start()
        except Exception as exc:
            logger.warning("camera preview failed: %s", exc)
            self._teardown()
            label = QtWidgets.QLabel(tr("prefs_device_test_unavailable"))
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)

    def _teardown(self):
        if self._camera is not None:
            try:
                self._camera.stop()
            except Exception:
                pass
            self._camera = None
        self._session = None
        self._video_widget = None

    def closeEvent(self, event):  # noqa: N802 - Qt override
        self._teardown()
        super().closeEvent(event)
