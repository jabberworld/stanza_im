"""Media engine for Jingle RTP calls (XEP-0167), built on aiortc.

The engine owns an ``aiortc.RTCPeerConnection`` per call, which provides ICE
(XEP-0176 transport), DTLS-SRTP and the RTP media path.  Jingle signalling is
translated to/from SDP in :mod:`stanza_im.xmpp.jingle_rtp`.

Capture/playback use Qt Multimedia (``QAudioSource``/``QAudioSink``/``QCamera``)
because the device selection in Preferences is Qt-based; decoded remote video
frames are painted by ``ui/call_window.VideoView`` (no gstreamer dependency).

Everything is import-guarded: without ``aiortc`` (or Qt Multimedia) the
:class:`NullMediaEngine` is used and the UI disables calling.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("stanza_im.call.media")

try:  # optional dependency
    import av  # type: ignore
    from aiortc import (  # type: ignore
        RTCConfiguration, RTCIceCandidate, RTCIceServer, RTCPeerConnection,
        RTCSessionDescription)
    from aiortc.mediastreams import (  # type: ignore
        AudioStreamTrack, VideoStreamTrack)
    HAS_AIORTC = True
except Exception as exc:  # pragma: no cover - import guard
    av = None  # type: ignore
    HAS_AIORTC = False
    logger.info("CALL aiortc unavailable: %s", exc)

try:  # optional Qt Multimedia (needs libpulse/gstreamer on the system)
    from PyQt6 import QtCore, QtGui
    from PyQt6.QtMultimedia import (  # type: ignore
        QAudioFormat, QAudioSink, QAudioSource, QCamera,
        QMediaDevices, QVideoSink)
    HAS_QTMM = True
except Exception as exc:  # pragma: no cover - import guard
    QtCore = QtGui = None  # type: ignore
    HAS_QTMM = False
    logger.info("CALL Qt Multimedia unavailable: %s", exc)


AUDIO_RATE = 48000
AUDIO_CHANNELS = 1
AUDIO_FORMAT = "s16"


def enumerate_devices() -> dict:
    """Return ``{"audio_input", "audio_output", "video_input"}`` lists of
    ``(id, name)`` tuples from Qt Multimedia (empty when unavailable)."""
    result = {"audio_input": [], "audio_output": [], "video_input": []}
    if not HAS_QTMM:
        logger.debug("CALL device enumeration skipped (no Qt Multimedia)")
        return result
    try:
        for dev in QMediaDevices.audioInputs():
            result["audio_input"].append((bytes(dev.id()).decode("utf-8", "replace"),
                                          dev.description()))
        for dev in QMediaDevices.audioOutputs():
            result["audio_output"].append((bytes(dev.id()).decode("utf-8", "replace"),
                                           dev.description()))
        for dev in QMediaDevices.videoInputs():
            result["video_input"].append((bytes(dev.id()).decode("utf-8", "replace"),
                                          dev.description()))
    except Exception:
        logger.exception("CALL device enumeration failed")
    logger.info("CALL devices: %d mic, %d speaker, %d camera",
                len(result["audio_input"]), len(result["audio_output"]),
                len(result["video_input"]))
    return result


def _find_device(devices, device_id):
    for dev in devices:
        if bytes(dev.id()).decode("utf-8", "replace") == device_id:
            return dev
    return None


if HAS_AIORTC:
    class _AudioCaptureTrack(AudioStreamTrack):
        """Microphone capture via QAudioSource → ``av.AudioFrame``."""

        def __init__(self, device_id: str = ""):
            super().__init__()
            self._source = None
            self._io = None
            self._frame_bytes = int(AUDIO_RATE * 0.02) * 2  # 20 ms s16 mono
            self.kind = "audio"
            if not HAS_QTMM:
                logger.warning("CALL audio capture unavailable (no Qt MM)")
                return
            try:
                fmt = QAudioFormat()
                fmt.setSampleRate(AUDIO_RATE)
                fmt.setChannelCount(AUDIO_CHANNELS)
                fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
                device = _find_device(QMediaDevices.audioInputs(), device_id)
                self._source = (QAudioSource(device, fmt) if device
                                else QAudioSource(fmt))
                self._io = self._source.start()
                logger.info("CALL microphone opened: %s",
                            device.description() if device else "default")
            except Exception:
                logger.exception("CALL microphone open failed")
                self._source = None

        async def recv(self):
            if self._io is None:
                await asyncio.sleep(0.02)
                return _silence(self._frame_bytes)
            deadline = asyncio.get_event_loop().time() + 0.25
            while self._io.bytesAvailable() < self._frame_bytes:
                if asyncio.get_event_loop().time() > deadline:
                    return _silence(self._frame_bytes)
                await asyncio.sleep(0.005)
            data = bytes(self._io.read(self._frame_bytes))
            frame = av.AudioFrame(format=AUDIO_FORMAT, layout="mono",
                                  samples=len(data) // 2)
            frame.sample_rate = AUDIO_RATE
            frame.planes[0].update(data)
            return frame

        def stop(self):
            try:
                if self._source is not None:
                    self._source.stop()
            except Exception:
                pass


    class _AudioPlayback:
        """Writes remote audio frames to a QAudioSink."""

        def __init__(self, device_id: str = ""):
            self._sink = None
            self._io = None
            if not HAS_QTMM:
                return
            try:
                fmt = QAudioFormat()
                fmt.setSampleRate(AUDIO_RATE)
                fmt.setChannelCount(AUDIO_CHANNELS)
                fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
                device = _find_device(QMediaDevices.audioOutputs(), device_id)
                self._sink = QAudioSink(device, fmt) if device else QAudioSink(fmt)
                self._io = self._sink.start()
                logger.info("CALL speaker opened: %s",
                            device.description() if device else "default")
            except Exception:
                logger.exception("CALL speaker open failed")

        def write(self, frame):
            if self._io is None:
                return
            try:
                data = bytes(frame.planes[0])
                self._io.write(data)
            except Exception:
                logger.debug("CALL speaker write failed", exc_info=True)

        def stop(self):
            try:
                if self._sink is not None:
                    self._sink.stop()
            except Exception:
                pass

    class _VideoCaptureTrack(VideoStreamTrack):
        """Camera capture via PyAV (v4l2/avfoundation/dshow)."""

        def __init__(self, device_id: str = ""):
            super().__init__()
            self.kind = "video"
            self._container = None
            self._stream = None
            self._device_id = device_id or ""
            self._start()

        def _device_path(self) -> str:
            dev = self._device_id
            if not dev:
                return "/dev/video0"
            if dev.startswith("/dev/"):
                return dev
            if dev.isdigit():
                return "/dev/video%s" % dev
            return dev

        def _start(self):
            if av is None:
                return
            path = self._device_path()
            try:
                # PyAV takes the file/device as a positional argument.
                self._container = av.open(path, format="v4l2")
                self._stream = self._container.streams.video[0]
                logger.info("CALL camera opened: %s", path)
            except Exception as exc:  # noqa: BLE001 - degrade to black frames
                logger.warning("CALL camera open failed for %s: %s", path, exc)
                self._container = None

        async def recv(self):
            if self._container is None or self._stream is None:
                await asyncio.sleep(0.05)
                return _black_frame()
            loop = asyncio.get_event_loop()
            pts = self.next_timestamp()
            frame = await loop.run_in_executor(None, self._next_frame)
            if frame is None:
                return _black_frame()
            frame.pts = pts
            frame.time_base = self._stream.time_base
            return frame

        def _next_frame(self):
            try:
                for frame in self._container.decode(self._stream):
                    return frame.reformat(format="yuv420p")
            except Exception:
                logger.debug("CALL camera decode ended", exc_info=True)
            return None

        def stop(self):
            try:
                if self._container is not None:
                    self._container.close()
            except Exception:
                pass


def _silence(frame_bytes: int):
    frame = av.AudioFrame(format=AUDIO_FORMAT, layout="mono",
                          samples=frame_bytes // 2)
    frame.sample_rate = AUDIO_RATE
    frame.planes[0].update(b"\x00" * frame_bytes)
    return frame


def _black_frame():
    frame = av.VideoFrame(320, 240, "yuv420p")
    for plane in frame.planes:
        plane.update(b"\x00" * plane.buffer_size)
    return frame


def _valid_ice_servers(ice_servers):
    """Drop ICE server entries aiortc's URI parser rejects (defensive)."""
    if not HAS_AIORTC:
        return []
    from aiortc.rtcicetransport import parse_stun_turn_uri
    valid: list[dict] = []
    seen: set[str] = set()
    for server in ice_servers or []:
        urls = server.get("urls")
        candidates = urls if isinstance(urls, (list, tuple)) else [urls]
        ok: list[str] = []
        for url in candidates:
            try:
                parse_stun_turn_uri(url)
            except Exception as exc:
                logger.warning("CALL dropping malformed ICE server %r: %s",
                               url, exc)
                continue
            if url not in seen:
                seen.add(url)
                ok.append(url)
        if ok:
            entry = dict(server)
            entry["urls"] = ok[0] if len(ok) == 1 else ok
            valid.append(entry)
    return valid


class MediaEngine:
    """Base media engine interface."""

    name = "null"
    available = False

    def enumerate_devices(self) -> dict:
        return {"audio_input": [], "audio_output": [], "video_input": []}

    def create_call(self, ice_servers, devices=None):
        raise RuntimeError("calling is not available")


class NullMediaEngine(MediaEngine):
    name = "null"
    available = False


if HAS_AIORTC:
    class AiortcCall:
        """One RTP session backed by an ``RTCPeerConnection``."""

        def __init__(self, ice_servers, devices=None,
                     on_ice_candidate=None, on_remote_track=None,
                     on_state=None):
            self.devices = devices or {}
            self.on_ice_candidate = on_ice_candidate
            self.on_remote_track = on_remote_track
            self.on_state = on_state
            self._audio_play = None
            self._video_widget = None
            self._tasks: list[asyncio.Task] = []
            self._local_audio = None
            self._local_video = None
            servers = _valid_ice_servers(ice_servers)
            logger.info("CALL creating RTCPeerConnection, ICE servers=%s",
                        [s.get("urls") for s in servers])
            cfg = RTCConfiguration(iceServers=[
                RTCIceServer(**s) for s in servers])
            self.pc = RTCPeerConnection(cfg)
            self.pc.on("icecandidate", self._on_ice_candidate)
            self.pc.on("track", self._on_track)
            self.pc.on("connectionstatechange", self._log_state)
            self.pc.on("iceconnectionstatechange", self._log_ice_state)
            self.pc.on("icegatheringstatechange", self._log_gather_state)

        # ── logging ───────────────────────────────────────────────
        def _log_state(self):
            logger.info("CALL connection state: %s",
                        getattr(self.pc, "connectionState", "?"))
            if self.on_state:
                self.on_state("connection",
                              getattr(self.pc, "connectionState", ""))

        def _log_ice_state(self):
            logger.info("CALL ICE state: %s",
                        getattr(self.pc, "iceConnectionState", "?"))

        def _log_gather_state(self):
            logger.info("CALL ICE gathering state: %s",
                        getattr(self.pc, "iceGatheringState", "?"))

        def _on_ice_candidate(self, candidate):
            if candidate is None:
                logger.info("CALL ICE gathering complete")
                return
            logger.debug("CALL local candidate: %s %s:%s %s/%s",
                         candidate.type, candidate.host, candidate.port,
                         candidate.protocol, candidate.foundation)
            if self.on_ice_candidate:
                try:
                    self.on_ice_candidate(candidate)
                except Exception:
                    logger.exception("CALL ice candidate relay failed")

        def _on_track(self, track):
            logger.info("CALL remote track: %s", track.kind)
            if track.kind == "audio":
                self._audio_play = _AudioPlayback(
                    self.devices.get("audio_output", ""))
                self._tasks.append(asyncio.ensure_future(
                    self._consume_audio(track)))
            elif track.kind == "video":
                self._tasks.append(asyncio.ensure_future(
                    self._consume_video(track)))
            if self.on_remote_track:
                self.on_remote_track(track.kind)

        async def _consume_audio(self, track):
            try:
                while True:
                    frame = await track.recv()
                    if self._audio_play:
                        self._audio_play.write(frame)
            except Exception:
                logger.debug("CALL audio track ended", exc_info=True)

        async def _consume_video(self, track):
            while True:
                try:
                    frame = await track.recv()
                except Exception:
                    logger.debug("CALL video track ended", exc_info=True)
                    return
                image = _frame_to_qimage(frame)
                if image is not None and self.on_remote_track:
                    self.on_remote_track("frame", image)

        # ── local media ───────────────────────────────────────────
        def add_audio(self):
            self._local_audio = _AudioCaptureTrack(
                self.devices.get("audio_input", ""))
            self.pc.addTrack(self._local_audio)
            logger.info("CALL added local audio track")

        def add_video(self):
            self._local_video = _VideoCaptureTrack(
                self.devices.get("video_input", ""))
            self.pc.addTrack(self._local_video)
            logger.info("CALL added local video track")

        # ── SDP ───────────────────────────────────────────────────
        async def create_offer(self) -> str:
            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)
            logger.debug("CALL local offer SDP:\n%s", self.pc.localDescription.sdp)
            return self.pc.localDescription.sdp

        async def create_answer(self) -> str:
            answer = await self.pc.createAnswer()
            await self.pc.setLocalDescription(answer)
            logger.debug("CALL local answer SDP:\n%s", self.pc.localDescription.sdp)
            return self.pc.localDescription.sdp

        async def set_remote(self, sdp: str, kind: str = "offer") -> None:
            logger.debug("CALL remote %s SDP:\n%s", kind, sdp)
            await self.pc.setRemoteDescription(RTCSessionDescription(sdp, kind))

        async def add_ice(self, cand: dict, sdp_mid: str = "",
                          sdp_mline_index: int = 0) -> None:
            """Add a remote ICE candidate described by a plain dict."""
            try:
                candidate = RTCIceCandidate(
                    component=int(cand.get("component", 1)),
                    foundation=str(cand.get("foundation", "0") or "0"),
                    ip=str(cand.get("ip", "")),
                    port=int(cand.get("port", 0)),
                    priority=int(cand.get("priority", 0)),
                    protocol=str(cand.get("protocol", "udp") or "udp"),
                    type=str(cand.get("type", "host") or "host"),
                    relatedAddress=cand.get("relatedAddress") or None,
                    relatedPort=cand.get("relatedPort") or None,
                    sdpMid=sdp_mid, sdpMLineIndex=sdp_mline_index)
                await self.pc.addIceCandidate(candidate)
                logger.debug("CALL added remote candidate %s:%s typ=%s mid=%s",
                             candidate.ip, candidate.port, candidate.type,
                             sdp_mid)
            except Exception:
                logger.exception("CALL addIceCandidate failed (%s)", cand)

        def close(self):
            logger.info("CALL closing peer connection")
            for task in self._tasks:
                task.cancel()
            self._tasks.clear()
            for obj in (self._local_audio, self._local_video,
                        self._audio_play):
                try:
                    if obj is not None:
                        obj.stop()
                except Exception:
                    pass
            try:
                asyncio.ensure_future(self.pc.close())
            except Exception:
                pass


    def _frame_to_qimage(frame):
        if QtGui is None:
            return None
        try:
            rgb = frame.reformat(width=frame.width, height=frame.height,
                                 format="rgb24")
            data = bytes(rgb.planes[0])
            image = QtGui.QImage(data, rgb.width, rgb.height,
                                 rgb.planes[0].line_size,
                                 QtGui.QImage.Format.Format_RGB888)
            return image.copy()
        except Exception:
            logger.debug("CALL frame conversion failed", exc_info=True)
            return None


    class AiortcMediaEngine(MediaEngine):
        name = "aiortc"
        available = True

        def enumerate_devices(self) -> dict:
            return enumerate_devices()

        def create_call(self, ice_servers, devices=None,
                        on_ice_candidate=None, on_remote_track=None,
                        on_state=None) -> "AiortcCall":
            return AiortcCall(ice_servers, devices, on_ice_candidate,
                              on_remote_track, on_state)


_engine: MediaEngine | None = None


def get_engine() -> MediaEngine:
    global _engine
    if _engine is None:
        _engine = AiortcMediaEngine() if HAS_AIORTC else NullMediaEngine()
        logger.info("CALL media engine: %s (aiortc=%s, qtmm=%s)",
                    _engine.name, HAS_AIORTC, HAS_QTMM)
    return _engine
