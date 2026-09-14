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
import importlib
import logging
import math
from fractions import Fraction

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
AUDIO_CHANNELS = 2                       # stereo matches the Opus encoder input
AUDIO_FORMAT = "s16"
AUDIO_SAMPLES_PER_FRAME = int(AUDIO_RATE * 0.02)   # 20 ms


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


_AV_SAMPLE_FORMATS = {"UInt8": "u8", "Int16": "s16", "Int32": "s32",
                      "Float": "flt"}
_BYTES_PER_SAMPLE = {"u8": 1, "s16": 2, "s32": 4, "flt": 4}


def _fmt_profile(fmt):
    """Return ``(sample_rate, channels, av_format)`` of a ``QAudioFormat``."""
    rate, channels, av_fmt = 0, 0, AUDIO_FORMAT
    try:
        if hasattr(fmt, "sampleRate"):
            rate = int(fmt.sampleRate())
        if hasattr(fmt, "channelCount"):
            channels = int(fmt.channelCount())
        sample_format = (fmt.sampleFormat() if hasattr(fmt, "sampleFormat")
                         else None)
        av_fmt = _AV_SAMPLE_FORMATS.get(getattr(sample_format, "name", ""),
                                        AUDIO_FORMAT)
    except Exception:
        logger.debug("CALL could not inspect audio format", exc_info=True)
    return rate, channels, av_fmt


def audio_format_info(fmt) -> str:
    rate, channels, av_fmt = _fmt_profile(fmt)
    return "%s Hz, %s ch, %s" % (rate or "?", channels or "?", av_fmt)


def _format_supported(device, fmt) -> bool:
    checker = getattr(device, "isFormatSupported", None)
    if not callable(checker):
        return True
    try:
        return bool(checker(fmt))
    except Exception:
        return True


def select_audio_format(device=None):
    """s16/stereo/48 kHz when the device supports it, else its preferred one."""
    if not HAS_QTMM:
        return None
    fmt = QAudioFormat()
    fmt.setSampleRate(AUDIO_RATE)
    fmt.setChannelCount(AUDIO_CHANNELS)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    if device is not None and not _format_supported(device, fmt):
        preferred = getattr(device, "preferredFormat", None)
        if callable(preferred):
            try:
                chosen = preferred()
                if chosen is not None:
                    logger.info("CALL device prefers %s", audio_format_info(chosen))
                    return chosen
            except Exception:
                logger.debug("CALL preferredFormat failed", exc_info=True)
    return fmt


def _audio_error(obj) -> str:
    """Human-readable error of a ``QAudioSource``/``QAudioSink`` ("" = none)."""
    getter = getattr(obj, "error", None)
    if not callable(getter):
        return ""
    try:
        error = getter()
    except Exception:
        return ""
    if error is None:
        return ""
    name = getattr(error, "name", None) or str(error)
    return "" if name in ("NoError", "0") else name


def open_audio_source(device_id: str = ""):
    """Open the selected microphone.

    Returns ``(source, io, fmt, name, error)``; *io* is ``None`` when the device
    could not be started and *error* carries the reason.
    """
    if not HAS_QTMM:
        return None, None, None, "", "Qt Multimedia unavailable"
    device = _find_device(QMediaDevices.audioInputs(), device_id)
    name = device.description() if device else "default"
    try:
        fmt = select_audio_format(device)
        source = QAudioSource(device, fmt) if device else QAudioSource(fmt)
        io = source.start()
        error = _audio_error(source)
        if io is None or error:
            logger.warning("CALL microphone error (%s): %s", name,
                           error or "no stream")
            return source, None, fmt, name, error or "no stream"
        logger.info("CALL microphone opened: %s (%s)", name,
                    audio_format_info(fmt))
        return source, io, fmt, name, ""
    except Exception as exc:
        logger.exception("CALL microphone open failed")
        return None, None, None, name, str(exc)


def open_audio_sink(device_id: str = ""):
    """Open the selected speaker.  Returns ``(sink, io, fmt, name, error)``."""
    if not HAS_QTMM:
        return None, None, None, "", "Qt Multimedia unavailable"
    device = _find_device(QMediaDevices.audioOutputs(), device_id)
    name = device.description() if device else "default"
    try:
        fmt = select_audio_format(device)
        sink = QAudioSink(device, fmt) if device else QAudioSink(fmt)
        io = sink.start()
        error = _audio_error(sink)
        if io is None or error:
            logger.warning("CALL speaker error (%s): %s", name,
                           error or "no stream")
            return sink, None, fmt, name, error or "no stream"
        logger.info("CALL speaker opened: %s (%s)", name,
                    audio_format_info(fmt))
        return sink, io, fmt, name, ""
    except Exception as exc:
        logger.exception("CALL speaker open failed")
        return None, None, None, name, str(exc)


def peak_level(data: bytes, fmt) -> float:
    """Peak amplitude (0.0–1.0) of raw PCM *data* for the given format."""
    rate, channels, av_fmt = _fmt_profile(fmt)  # noqa: F841 - rate unused
    if not data:
        return 0.0
    try:
        import array
        if av_fmt == "s16":
            samples = array.array("h")
            samples.frombytes(data[:len(data) - (len(data) % 2)])
            peak = max((abs(s) for s in samples), default=0) / 32768.0
        elif av_fmt == "u8":
            peak = max((abs(b - 128) for b in data), default=0) / 128.0
        elif av_fmt == "s32":
            samples = array.array("i")
            samples.frombytes(data[:len(data) - (len(data) % 4)])
            peak = max((abs(s) for s in samples), default=0) / 2147483648.0
        elif av_fmt == "flt":
            samples = array.array("f")
            samples.frombytes(data[:len(data) - (len(data) % 4)])
            peak = max((abs(s) for s in samples), default=0.0)
        else:
            peak = 0.0
    except Exception:
        peak = 0.0
    return min(1.0, max(0.0, peak))


def tone_pcm(seconds: float = 1.2, freq: float = 440.0,
             amplitude: float = 0.28, fmt=None) -> bytes:
    """Generate a sine tone as raw PCM matching *fmt* (default s16/stereo/48k)."""
    if fmt is not None:
        rate, channels, av_fmt = _fmt_profile(fmt)
    else:
        rate, channels, av_fmt = AUDIO_RATE, AUDIO_CHANNELS, AUDIO_FORMAT
    rate = rate or AUDIO_RATE
    channels = channels or AUDIO_CHANNELS
    samples = int(rate * max(0.05, seconds))
    two_pi = 2.0 * math.pi
    if av_fmt == "u8":
        out = bytearray()
        for i in range(samples):
            value = int(128 + amplitude * 127 * math.sin(two_pi * freq * i / rate))
            out.extend(bytes([max(0, min(255, value))]) * channels)
        return bytes(out)
    if av_fmt == "s32":
        import struct
        out = bytearray()
        for i in range(samples):
            value = int(amplitude * 2147483647 * math.sin(two_pi * freq * i / rate))
            out.extend(struct.pack("<i", value) * channels)
        return bytes(out)
    if av_fmt == "flt":
        import struct
        out = bytearray()
        for i in range(samples):
            value = amplitude * math.sin(two_pi * freq * i / rate)
            out.extend(struct.pack("<f", value) * channels)
        return bytes(out)
    import array
    tone = array.array("h")
    for i in range(samples):
        value = int(amplitude * 32767 * math.sin(two_pi * freq * i / rate))
        tone.extend([value] * channels)
    return tone.tobytes()


if HAS_AIORTC:
    class _AudioCaptureTrack(AudioStreamTrack):
        """Microphone capture via QAudioSource → ``av.AudioFrame``."""

        def __init__(self, device_id: str = ""):
            super().__init__()
            self._source = None
            self._io = None
            self._pts = 0
            self._stopped = False
            self.kind = "audio"
            self._rate, self._channels = AUDIO_RATE, AUDIO_CHANNELS
            self._av_fmt = AUDIO_FORMAT
            self._resampler = None
            self._frame_bytes = AUDIO_SAMPLES_PER_FRAME * AUDIO_CHANNELS * 2
            if not HAS_QTMM:
                logger.warning("CALL audio capture unavailable (no Qt MM)")
                return
            self._source, self._io, fmt, name, error = open_audio_source(
                device_id)
            if fmt is not None:
                rate, channels, av_fmt = _fmt_profile(fmt)
                self._rate = rate or AUDIO_RATE
                self._channels = channels or AUDIO_CHANNELS
                self._av_fmt = av_fmt or AUDIO_FORMAT
                self._frame_bytes = max(2, self._input_bytes())
            if self._io is None:
                logger.warning("CALL microphone not streaming (%s): %s",
                               name, error or "unknown")

        def _input_bytes(self) -> int:
            rate = self._rate or AUDIO_RATE
            channels = self._channels or AUDIO_CHANNELS
            per_sample = _BYTES_PER_SAMPLE.get(self._av_fmt, 2)
            return int(rate * 0.02) * channels * per_sample

        def _to_encoder_format(self, frame):
            """Convert a device-format frame to the encoder's s16/stereo/48k."""
            if (self._av_fmt == AUDIO_FORMAT
                    and self._channels == AUDIO_CHANNELS
                    and self._rate in (0, AUDIO_RATE)):
                return frame
            try:
                if self._resampler is None:
                    self._resampler = av.AudioResampler(
                        format=AUDIO_FORMAT, layout="stereo", rate=AUDIO_RATE)
                frames = self._resampler.resample(frame)
            except Exception:
                logger.warning("CALL microphone resample failed", exc_info=True)
                return None
            return frames[0] if frames else None

        async def recv(self):
            def _silent():
                return self._stamp(_silence(AUDIO_SAMPLES_PER_FRAME,
                                            AUDIO_CHANNELS))

            io = self._io
            if self._stopped or io is None:
                await asyncio.sleep(0.02)
                return _silent()
            deadline = asyncio.get_event_loop().time() + 0.25
            try:
                while io.bytesAvailable() < self._frame_bytes:
                    if self._stopped:
                        return _silent()
                    if asyncio.get_event_loop().time() > deadline:
                        return _silent()
                    await asyncio.sleep(0.005)
                data = bytes(io.read(self._frame_bytes))
            except RuntimeError:
                # The Qt device was deleted by stop() while we were reading.
                self._stopped = True
                return _silent()
            per_sample = _BYTES_PER_SAMPLE.get(self._av_fmt, 2)
            samples = len(data) // max(1, (self._channels or 1) * per_sample)
            if samples <= 0:
                return _silent()
            layout = "stereo" if self._channels == 2 else "mono"
            frame = av.AudioFrame(format=self._av_fmt, layout=layout,
                                  samples=samples)
            frame.sample_rate = self._rate or AUDIO_RATE
            frame.planes[0].update(data)
            converted = self._to_encoder_format(frame)
            if converted is None:
                return _silent()
            return self._stamp(converted)

        def _stamp(self, frame):
            """Give the frame a monotonic sample timestamp (aiortc requires it)."""
            frame.pts = self._pts
            frame.time_base = Fraction(1, AUDIO_RATE)
            self._pts += frame.samples
            return frame

        def stop(self):
            # Mark stopped and detach the device *before* stopping the Qt
            # source, so an in-flight recv() cannot touch a deleted QIODevice.
            self._stopped = True
            self._io = None
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
            self._rate, self._channels = AUDIO_RATE, AUDIO_CHANNELS
            self._av_fmt = AUDIO_FORMAT
            self._resampler = None
            if not HAS_QTMM:
                return
            self._sink, self._io, fmt, name, error = open_audio_sink(device_id)
            if fmt is not None:
                rate, channels, av_fmt = _fmt_profile(fmt)
                self._rate = rate or AUDIO_RATE
                self._channels = channels or AUDIO_CHANNELS
                self._av_fmt = av_fmt or AUDIO_FORMAT
            if self._io is None:
                logger.warning("CALL speaker not streaming (%s): %s",
                               name, error or "unknown")

        def _to_device_format(self, frame):
            if (self._av_fmt == AUDIO_FORMAT
                    and self._channels == AUDIO_CHANNELS
                    and self._rate in (0, AUDIO_RATE)):
                return frame
            try:
                if self._resampler is None:
                    layout = "stereo" if self._channels == 2 else "mono"
                    self._resampler = av.AudioResampler(
                        format=self._av_fmt, layout=layout,
                        rate=self._rate or AUDIO_RATE)
                frames = self._resampler.resample(frame)
            except Exception:
                logger.debug("CALL speaker resample failed", exc_info=True)
                return None
            return frames[0] if frames else None

        def write(self, frame):
            if self._io is None:
                return
            try:
                out = self._to_device_format(frame)
                if out is None:
                    return
                self._io.write(bytes(out.planes[0]))
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
            self._stopped = False
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
            # aiortc >= 1.10: next_timestamp() is async and returns
            # (pts, time_base) in the video clock rate.
            pts, time_base = await self.next_timestamp()

            def _black():
                frame = _black_frame()
                frame.pts = pts
                frame.time_base = time_base
                return frame

            if self._stopped or self._container is None or self._stream is None:
                await asyncio.sleep(0.05)
                return _black()
            loop = asyncio.get_event_loop()
            try:
                frame = await loop.run_in_executor(None, self._next_frame)
            except RuntimeError:
                self._stopped = True
                return _black()
            if frame is None:
                frame = _black_frame()
            frame.pts = pts
            frame.time_base = time_base
            return frame

        def _next_frame(self):
            try:
                for frame in self._container.decode(self._stream):
                    return frame.reformat(format="yuv420p")
            except Exception:
                logger.debug("CALL camera decode ended", exc_info=True)
            return None

        def stop(self):
            self._stopped = True
            try:
                if self._container is not None:
                    self._container.close()
            except Exception:
                pass


def _silence(samples: int, channels: int = AUDIO_CHANNELS):
    layout = "stereo" if channels == 2 else "mono"
    frame = av.AudioFrame(format=AUDIO_FORMAT, layout=layout, samples=samples)
    frame.sample_rate = AUDIO_RATE
    frame.planes[0].update(b"\x00" * (samples * channels * 2))
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


def decode_ffmpeg_error(exc) -> str:
    """Best-effort message for an FFmpeg/PyAV exception.

    On non-UTF-8/locale setups PyAV decodes the libav error text as ASCII and
    raises ``UnicodeDecodeError`` instead of the real ``FFmpegError``; the raw
    bytes live in ``exc.object``.
    """
    obj = getattr(exc, "object", None)
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", "replace")
    return str(exc)


class _PassthroughResampler:
    """Stand-in for ``av.AudioResampler`` yielding already-matching frames."""

    def resample(self, frame):
        return [frame]


def _frame_matches_resampler(frame, resampler) -> bool:
    fmt = getattr(getattr(resampler, "format", None), "name", None)
    layout = getattr(getattr(resampler, "layout", None), "name", None)
    rate = getattr(resampler, "rate", None)
    frame_size = getattr(resampler, "frame_size", None)
    if fmt is None and layout is None and rate is None:
        return False
    try:
        if fmt and frame.format.name != fmt:
            return False
        if layout and frame.layout.name != layout:
            return False
        if rate and frame.sample_rate != rate:
            return False
        if frame_size and frame.samples != frame_size:
            return False
    except Exception:
        return False
    return True


def _patch_audio_encoder(encoder_cls) -> None:
    """Make an aiortc audio encoder survive its own resampler.

    aiortc's encoders push each frame through an ``av.AudioResampler``.  When
    the frame already matches the encoder format (s16/stereo/48 kHz, 20 ms)
    that resample is a no-op — but some PyAV builds raise ``EINVAL`` from the
    FFmpeg filter graph, and a non-UTF-8 locale turns it into an opaque
    ``UnicodeDecodeError`` that kills the RTP sender.  Encoder instances are
    ordinary Python objects (unlike the immutable PyAV ``AudioResampler``), so
    temporarily installing a passthrough resampler is safe; any remaining
    resample failure is logged (with the real FFmpeg error) and swallowed.
    """
    if encoder_cls is None or getattr(encoder_cls, "_stanza_patched", False):
        return
    original_encode = encoder_cls.encode

    def encode(self, frame, force_keyframe=False):
        resampler = getattr(self, "resampler", None)
        if resampler is not None and _frame_matches_resampler(frame, resampler):
            self.resampler = _PassthroughResampler()
            try:
                return original_encode(self, frame, force_keyframe)
            finally:
                self.resampler = resampler
        try:
            return original_encode(self, frame, force_keyframe)
        except Exception as exc:
            logger.warning("CALL audio encode failed: %s",
                           decode_ffmpeg_error(exc))
            return [], None

    encoder_cls.encode = encode
    encoder_cls._stanza_patched = True


def _install_audio_resampler_compat() -> None:
    """Patch aiortc's audio encoders (never the immutable PyAV classes)."""
    if not HAS_AIORTC:
        return
    for module_name, class_names in (
            ("aiortc.codecs.opus", ("OpusEncoder",)),
            ("aiortc.codecs.g711", ("PcmEncoder",)),
            ("aiortc.codecs.g722", ("G722Encoder",))):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            logger.debug("CALL could not patch %s", module_name, exc_info=True)
            continue
        for class_name in class_names:
            _patch_audio_encoder(getattr(module, class_name, None))


_install_audio_resampler_compat()


def audio_encode_selftest() -> tuple[bool, str]:
    """Encode one 20 ms silence frame through aiortc's Opus encoder.

    Returns ``(ok, detail)``; used by the test suite and to diagnose a broken
    local audio pipeline without placing a call.
    """
    if not HAS_AIORTC:
        return False, "aiortc unavailable"
    try:
        from aiortc.codecs.opus import OpusEncoder
        frame = _silence(AUDIO_SAMPLES_PER_FRAME, AUDIO_CHANNELS)
        frame.pts = 0
        frame.time_base = Fraction(1, AUDIO_RATE)
        packets, _timestamp = OpusEncoder().encode(frame)
        return True, "%d packet(s)" % len(packets)
    except Exception as exc:
        return False, decode_ffmpeg_error(exc)


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
                # Normal at call end (MediaStreamError) — no traceback.
                logger.debug("CALL audio track ended")

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

        # ── ICE role / nomination fallback ────────────────────────
        def _ice_transports(self):
            try:
                transceivers = list(self.pc.getTransceivers())
            except Exception:
                return
            for transceiver in transceivers:
                dtls = getattr(getattr(transceiver, "receiver", None),
                               "transport", None)
                ice = getattr(dtls, "transport", None)
                if ice is not None:
                    yield ice

        def ice_role(self) -> str:
            for ice in self._ice_transports():
                return getattr(ice, "role", "") or ""
            return ""

        def connection_state(self) -> str:
            return getattr(self.pc, "connectionState", "")

        def ice_state(self) -> str:
            return getattr(self.pc, "iceConnectionState", "")

        def force_ice_controlling(self) -> bool:
            """Ask aioice to nominate (fallback when a peer never does).

            Some libwebrtc peers (Conversations) leave the controlled role
            without ever sending ``USE-CANDIDATE``; switching to controlling
            makes aioice perform regular nomination, while a compliant
            controlling peer resolves the resulting role conflict via the RFC
            5245 tie-breaker.
            """
            switched = False
            for ice in self._ice_transports():
                connection = getattr(ice, "_connection", None)
                if connection is None:
                    continue
                try:
                    if not connection.ice_controlling:
                        connection.switch_role(True)
                        switched = True
                except Exception:
                    logger.debug("CALL ICE role switch failed", exc_info=True)
            return switched

        def _cancel_ice_checks(self) -> None:
            """Cancel pending aioice checks so their STUN retry timers stop.

            aioice's ``Connection.close`` does not cancel the in-flight check
            tasks, so their ``Transaction`` retransmit timers fire on a closed
            transport and spam tracebacks after a hang-up.
            """
            for ice in self._ice_transports():
                connection = getattr(ice, "_connection", None)
                for check in list(getattr(connection, "_check_list", []) or []):
                    task = getattr(check, "task", None)
                    if task is not None and not task.done():
                        try:
                            task.cancel()
                        except Exception:
                            pass

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
            self._cancel_ice_checks()
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
