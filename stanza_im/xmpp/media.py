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
import time
import weakref
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

#: Encoder defaults (bits/s); the live encoders are tracked so a quality
#: change takes effect without renegotiating the session.
_MEDIA_DEFAULTS = {"audio_bitrate": 96000, "video_bitrate": 1000000}
_AUDIO_ENCODERS: "weakref.WeakSet" = weakref.WeakSet()
_VIDEO_ENCODERS: "weakref.WeakSet" = weakref.WeakSet()

#: RTCP fraction_lost is an 8-bit value (0..255).  Keep the first threshold
#: at ~1 % and trust REMB fully from ~5 %.
_VIDEO_LOSS_LOW = 2.55
_VIDEO_LOSS_HIGH = 12.75
_VIDEO_HOLD_S = 5.0
_VIDEO_STEP_MEDIUM = 0.85
_VIDEO_STEP_LOW = 0.95
_VIDEO_STEP_INTERVAL_S = 2.0
_VIDEO_BOOST_STEP = 1.25
_VIDEO_BOOST_INTERVAL_S = 0.5
_VIDEO_BOOST_MIN_STEP = 100000
_VIDEO_MOTION_THRESHOLD = 4.0


class VideoRateController:
    """Loss-aware REMB follower for the outgoing video encoder.

    The configured value is a hard ceiling.  A decrease below the current
    target is accepted immediately when the peer reports heavy loss, applied
    in steps at medium loss, and only considered after a quiet period when
    there is no loss.  Increases are accepted up to the configured cap.
    This avoids aiortc's very conservative REMB cliff without forcing a fixed
    bitrate on every frame.
    """

    def __init__(self):
        self.user_change = False
        self.reset(0)

    def reset(self, target: int, now: float | None = None) -> None:
        self.cap = max(0, int(target or 0))
        self.target = self.cap
        self.loss = 0.0
        self.last_remb = self.cap
        self._low_since: float | None = None
        self._last_decrease = now if now is not None else time.monotonic()
        self._last_boost = self._last_decrease

    def user_target(self, target: int, now: float | None = None) -> None:
        """Apply an explicit user/call setting and reset adaptation state."""
        self.reset(target, now)

    def note_loss(self, fraction_lost) -> None:
        try:
            value = float(fraction_lost)
        except (TypeError, ValueError):
            return
        self.loss = max(0.0, min(255.0, value))
        if self.loss > _VIDEO_LOSS_LOW:
            self._low_since = None

    def loss_pct(self) -> float:
        return self.loss * 100.0 / 255.0

    def on_motion(self, now: float | None = None) -> int:
        """Boost the target after local motion, without waiting for REMB.

        Only low-loss links are boosted; a lossy link keeps the normal
        loss-aware behaviour.  Returns the new target, or ``0`` when no boost
        was applied (throttled or at the cap).
        """
        if not self.cap or self.loss >= _VIDEO_LOSS_HIGH:
            return 0
        if now is None:
            now = time.monotonic()
        if now - self._last_boost < _VIDEO_BOOST_INTERVAL_S:
            return 0
        old = self.target
        if old >= self.cap:
            return 0
        self._last_boost = now
        self.target = min(
            self.cap,
            max(int(old * _VIDEO_BOOST_STEP), old + _VIDEO_BOOST_MIN_STEP))
        self._low_since = None
        return self.target

    def on_remb(self, requested, now: float | None = None) -> int:
        """Return the target to apply for one REMB value."""
        if now is None:
            now = time.monotonic()
        try:
            requested = int(requested)
        except (TypeError, ValueError):
            return self.target
        requested = max(0, min(requested, self.cap))
        old = self.target
        if not self.cap:
            self.last_remb = requested
            return requested
        if requested >= old:
            self.target = requested
            self._low_since = None
        elif self.loss >= _VIDEO_LOSS_HIGH:
            self.target = requested
            self._low_since = None
        elif self.loss >= _VIDEO_LOSS_LOW:
            self.target = max(requested, int(old * _VIDEO_STEP_MEDIUM))
            self._low_since = None
        else:
            if self._low_since is None:
                self._low_since = now
            if (now - self._low_since >= _VIDEO_HOLD_S
                    and now - self._last_decrease >= _VIDEO_STEP_INTERVAL_S):
                self.target = max(requested, int(old * _VIDEO_STEP_LOW))
                self._last_decrease = now
            else:
                self.target = old
        self.last_remb = requested
        return self.target


_VIDEO_RATE = VideoRateController()
_VIDEO_RATE.reset(_MEDIA_DEFAULTS["video_bitrate"])


def media_defaults() -> dict:
    """The current encoder defaults (bits/s)."""
    return dict(_MEDIA_DEFAULTS)


def note_video_loss(fraction_lost) -> None:
    """Remember the latest peer-reported loss for the rate controller."""
    _VIDEO_RATE.note_loss(fraction_lost)


def boost_video_target(now: float | None = None) -> int:
    """Raise the video target after local motion and push it to encoders."""
    target = _VIDEO_RATE.on_motion(now)
    if not target:
        return 0
    _VIDEO_RATE.user_change = True
    try:
        for encoder in list(_VIDEO_ENCODERS):
            try:
                encoder.target_bitrate = target
            except Exception:  # noqa: BLE001 - best effort
                pass
    finally:
        _VIDEO_RATE.user_change = False
    logger.debug("CALL motion boost target=%d loss=%.1f%%",
                 target, _VIDEO_RATE.loss_pct())
    return target


def set_media_defaults(audio_kbps=None, video_kbps=None) -> None:
    """Set the initial encoder bitrates and update the live encoders.

    Audio is normally only changed before a call (Opus may need the codec to
    be reopened), video takes effect on the next encoded frame (aiortc
    recreates its codec when the target moves by more than 10 %).
    """
    if audio_kbps:
        try:
            value = max(8, min(256, int(audio_kbps))) * 1000
        except (TypeError, ValueError):
            value = 0
        if value:
            _MEDIA_DEFAULTS["audio_bitrate"] = value
            for encoder in list(_AUDIO_ENCODERS):
                try:
                    encoder.codec.bit_rate = value
                except Exception:  # noqa: BLE001 - best effort
                    pass
    if video_kbps:
        try:
            value = max(50, min(4000, int(video_kbps))) * 1000
        except (TypeError, ValueError):
            value = 0
        if value:
            _MEDIA_DEFAULTS["video_bitrate"] = value
            # A new call/quality choice starts from a clean loss estimate;
            # sample_stats() refreshes it from the peer's RTCP reports.
            _VIDEO_RATE.user_target(value)
            _VIDEO_RATE.user_change = True
            try:
                for encoder in list(_VIDEO_ENCODERS):
                    try:
                        encoder.target_bitrate = value
                    except Exception:  # noqa: BLE001 - best effort
                        pass
            finally:
                _VIDEO_RATE.user_change = False


def request_video_keyframe(reason: str = "") -> int:
    """Ask the live video encoders for a keyframe (fixes a green peer view)."""
    count = 0
    for encoder in list(_VIDEO_ENCODERS):
        try:
            encoder._stanza_keyframe = True
            count += 1
        except Exception:  # noqa: BLE001 - best effort
            pass
    if count:
        logger.info("CALL keyframe requested (%s), %d encoder(s)",
                    reason or "manual", count)
    else:
        logger.debug("CALL keyframe requested (%s), no live encoder yet",
                     reason or "manual")
    return count


def sdp_media_codecs(sdp: str) -> dict:
    """The negotiated codec per media kind from an SDP answer.

    The first payload of each ``m=`` line is the codec selected for that
    stream; the name comes from the matching ``a=rtpmap``.
    """
    first_payload: dict[str, str] = {}
    rtpmap: dict[tuple[str, str], str] = {}
    kind = ""
    for raw in str(sdp or "").splitlines():
        line = raw.strip()
        if line.startswith("m="):
            parts = line[2:].split()
            kind = parts[0] if parts else ""
            if kind and len(parts) > 3 and kind not in first_payload:
                first_payload[kind] = parts[3]
        elif line.startswith("a=rtpmap:") and kind:
            value = line[len("a=rtpmap:"):]
            payload, _, rest = value.partition(" ")
            name = rest.split("/", 1)[0] if rest else ""
            if payload and name:
                rtpmap[(kind, payload)] = name
    result = {}
    for media in ("audio", "video"):
        payload = first_payload.get(media, "")
        name = rtpmap.get((media, payload), "")
        if name:
            result[media] = name
    return result


def _ordered_codecs(kind: str, choice: str) -> list:
    """Capabilities reordered with the preferred codec first (``auto`` empty).

    The negotiated payload types stay the same, so this only changes our SDP
    preference order; it must be applied before an offer/answer is created.
    """
    if not HAS_AIORTC or not choice or str(choice).lower() == "auto":
        return []
    try:
        from aiortc import RTCRtpSender
        codecs = list(RTCRtpSender.getCapabilities(kind).codecs or [])
    except Exception:  # noqa: BLE001 - optional dependency
        return []
    wanted = str(choice).lower()
    chosen = [codec for codec in codecs
              if str(getattr(codec, "mimeType", "")).lower().split("/")[-1]
              == wanted]
    if not chosen:
        return []
    return chosen + [codec for codec in codecs if codec not in chosen]


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


def _qt_pixel_format(pixel_format) -> str:
    """Map a Qt pixel format to the FFmpeg/v4l2 input format name."""
    name = str(getattr(pixel_format, "name", pixel_format))
    if "Jpeg" in name:          # Qt 6 names it Format_Jpeg (was MJpeg)
        return "mjpeg"
    if "YUYV" in name:
        return "yuyv422"
    if "UYVY" in name:
        return "uyvy422"
    if "NV12" in name:
        return "nv12"
    if "NV21" in name:
        return "nv21"
    return ""


def camera_formats(device_id: str = "") -> list[dict]:
    """Supported camera modes: ``{width, height, fps, format}`` (best effort).

    Qt Multimedia enumerates the driver's formats (including the MJPG modes
    many webcams expose); the chosen mode is passed to PyAV's v4l2 input.
    """
    if not HAS_QTMM:
        return []
    try:
        device = _find_device(QMediaDevices.videoInputs(), device_id)
        if device is None:
            return []
        supports = (getattr(device, "videoFormats", None)
                    or getattr(device, "supportedVideoFormats", None))
        if supports is None:
            return []
        formats = supports()
    except Exception:  # noqa: BLE001 - optional capability
        return []
    result: list[dict] = []
    seen: set[tuple] = set()
    for fmt in formats or []:
        try:
            size = fmt.resolution()
            item = {
                "width": int(size.width()),
                "height": int(size.height()),
                "fps": float(fmt.maxFrameRate() or 0),
                "format": _qt_pixel_format(fmt.pixelFormat()),
            }
        except Exception:  # noqa: BLE001 - skip a malformed entry
            continue
        if not item["width"] or not item["height"]:
            continue
        key = (item["width"], item["height"], round(item["fps"], 1),
               item["format"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    result.sort(key=lambda row: (row["width"] * row["height"], row["fps"],
                                 row["format"]), reverse=True)
    return result


def normalize_camera_mode(mode: str, device_id: str = "") -> str:
    """Add the pixel format to a stored ``WxH@fps`` mode (prefer MJPG).

    A mode saved before the pixel format was recognized (e.g. Qt reports
    ``Format_Jpeg``) would otherwise open the camera without
    ``input_format=mjpeg``, and the high-frame-rate MJPG mode cannot deliver
    frames in the driver's default format.
    """
    mode = str(mode or "").strip()
    if not mode or ":" in mode:
        return mode
    size, _, fps = mode.partition("@")
    candidates = []
    for item in camera_formats(device_id):
        if "%dx%d" % (item["width"], item["height"]) != size:
            continue
        if fps:
            try:
                wanted = float(fps)
            except ValueError:
                return mode
            if abs(float(item.get("fps") or 0) - wanted) > 0.5:
                continue
        candidates.append(item)
    if not candidates:
        return mode
    chosen = next((item for item in candidates
                   if item.get("format") == "mjpeg"), candidates[0])
    pixel_format = str(chosen.get("format") or "")
    return mode + (":" + pixel_format if pixel_format else "")


def _v4l2_open_options(mode: str) -> dict:
    """Parse ``WxH@F[:pixelformat]`` into PyAV v4l2 open options."""
    mode = str(mode or "").strip()
    if not mode:
        return {}
    spec, _, pixel = mode.partition(":")
    size, _, fps = spec.partition("@")
    width, _, height = size.partition("x")
    options: dict[str, str] = {}
    if width.isdigit() and height.isdigit():
        options["video_size"] = "%sx%s" % (width, height)
    if fps:
        try:
            float(fps)
        except ValueError:
            pass
        else:
            options["framerate"] = fps
    if pixel:
        options["input_format"] = pixel
    return options


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
            self._enabled = True
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
            except Exception as exc:
                logger.warning("CALL microphone resample failed: %s",
                               decode_ffmpeg_error(exc))
                return None
            return frames[0] if frames else None

        def set_enabled(self, enabled: bool) -> None:
            self._enabled = enabled

        async def recv(self):
            def _silent():
                return self._stamp(_silence(AUDIO_SAMPLES_PER_FRAME,
                                            AUDIO_CHANNELS))

            io = self._io
            if self._stopped or not self._enabled or io is None:
                await asyncio.sleep(0.02)
                return _silent()
            deadline = asyncio.get_event_loop().time() + 0.25
            chunks = bytearray()
            try:
                # Read directly instead of waiting for io.bytesAvailable():
                # the QIODevice from QAudioSource.start() may report 0 while
                # audio is actually streaming, which made us send silence.
                while len(chunks) < self._frame_bytes:
                    if self._stopped:
                        return _silent()
                    if asyncio.get_event_loop().time() > deadline:
                        return _silent()
                    chunk = io.read(self._frame_bytes - len(chunks))
                    if not chunk:
                        await asyncio.sleep(0.005)
                        continue
                    chunks.extend(chunk)
            except RuntimeError:
                # The Qt device was deleted by stop() while we were reading.
                self._stopped = True
                return _silent()
            data = bytes(chunks[:self._frame_bytes])
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
            self._enabled = True
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
            except Exception as exc:
                logger.debug("CALL speaker resample failed: %s",
                             decode_ffmpeg_error(exc))
                return None
            return frames[0] if frames else None

        def write(self, frame):
            if self._io is None or not self._enabled:
                return
            try:
                out = self._to_device_format(frame)
                if out is None:
                    return
                self._io.write(bytes(out.planes[0]))
            except Exception:
                logger.debug("CALL speaker write failed", exc_info=True)

        @property
        def enabled(self) -> bool:
            return self._enabled

        def set_enabled(self, enabled: bool) -> None:
            self._enabled = enabled

        def stop(self):
            try:
                if self._sink is not None:
                    self._sink.stop()
            except Exception:
                pass

    class _VideoCaptureTrack(VideoStreamTrack):
        """Local video source: the camera (PyAV) or a screen region.

        The source can be switched live (camera <-> screen) without
        renegotiation; the camera is opened lazily so a screen-only call never
        touches ``/dev/video0``.
        """

        def __init__(self, device_id: str = "", on_frame=None,
                     on_motion=None, screen_fps: int = 5,
                     screen_max_width: int = 1920,
                     screen_max_height: int = 0, max_height: int = 0,
                     camera_mode: str = ""):
            super().__init__()
            self.kind = "video"
            self._container = None
            self._stream = None
            self._stopped = False
            self._enabled = True
            self._device_id = device_id or ""
            self._on_frame = on_frame
            self._on_motion = on_motion
            self._motion_prev = None
            self._motion_score = 0.0
            self._motion_peak = 0.0
            self._source = "camera"
            self._region = None
            self._screen_fps = max(1, int(screen_fps or 5))
            self._screen_max_width = max(0, int(screen_max_width or 0))
            self._screen_max_height = max(0, int(screen_max_height or 0))
            self._max_height = max(0, int(max_height or 0))
            self._camera_mode = str(camera_mode or "")
            self._last_size = None
            self._last_open_attempt = 0.0
            self._decode_error = ""
            self._last_grab = 0.0
            self._last_image = None
            # The PyAV container is closed only after an in-flight decode
            # returns (see stop/_on_decode_done).  Closing it from the GUI
            # thread while the executor reads it crashes libavcodec.
            self._decode_future = None
            self._pending_close = None
            # Sent-frame counter for the call diagnostics (actual FPS).
            self._sent_frames = 0
            self._fps_started = time.monotonic()
            self._fps_value = 0.0
            self._open_camera()

        def _device_path(self) -> str:
            dev = self._device_id
            if not dev:
                return "/dev/video0"
            if dev.startswith("/dev/"):
                return dev
            if dev.isdigit():
                return "/dev/video%s" % dev
            return dev

        def _open_camera(self):
            if self._container is not None or av is None:
                return
            self._last_open_attempt = time.monotonic()
            path = self._device_path()
            effective_mode = normalize_camera_mode(self._camera_mode,
                                                   self._device_id)
            options = _v4l2_open_options(effective_mode)
            try:
                # PyAV takes the file/device as a positional argument.
                if options:
                    self._container = av.open(path, format="v4l2",
                                              options=options)
                else:
                    self._container = av.open(path, format="v4l2")
                self._stream = self._container.streams.video[0]
                logger.info("CALL camera opened: %s (%s, %s)", path,
                            effective_mode or "auto", options or "default")
            except Exception as exc:  # noqa: BLE001 - degrade to black frames
                reason = decode_ffmpeg_error(exc)
                if options:
                    logger.warning(
                        "CALL camera mode %s failed for %s (%s); using auto",
                        self._camera_mode, path, reason)
                    try:
                        self._container = av.open(path, format="v4l2")
                        self._stream = self._container.streams.video[0]
                        logger.info("CALL camera opened: %s (auto)", path)
                        return
                    except Exception as retry_exc:  # noqa: BLE001
                        exc = retry_exc
                logger.warning("CALL camera open failed for %s: %s", path,
                               decode_ffmpeg_error(exc))
                self._container = None

        def set_enabled(self, enabled: bool) -> None:
            self._enabled = enabled

        def set_max_height(self, height: int) -> None:
            """Cap the outgoing camera height (0 = the source size)."""
            self._max_height = max(0, int(height or 0))
            self._schedule_keyframe("camera-height")

        def set_screen_box(self, width: int, height: int) -> None:
            """Cap the outgoing screen-share resolution (0 = the source)."""
            self._screen_max_width = max(0, int(width or 0))
            self._screen_max_height = max(0, int(height or 0))
            self._schedule_keyframe("screen-box")

        @staticmethod
        def _schedule_keyframe(reason: str) -> None:
            try:
                asyncio.get_event_loop().call_later(
                    0.3, request_video_keyframe, reason)
            except Exception:  # noqa: BLE001 - no loop in tests
                pass

        def _note_size(self, frame) -> None:
            """Remember the sent frame size; keyframe once the video starts."""
            if frame is None:
                return
            first = self._last_size is None
            self._last_size = (frame.width, frame.height)
            self._sent_frames = getattr(self, "_sent_frames", 0) + 1
            if first:
                logger.info("CALL video frame %dx%d (max_height=%s)",
                            frame.width, frame.height,
                            getattr(self, "_max_height", 0) or "source")
                self._schedule_keyframe("first-video-frame")

        @staticmethod
        def _motion_sample(frame) -> bytearray:
            """A tiny luma grid, enough to tell motion from a static scene."""
            plane = frame.planes[0]
            raw = bytes(plane)
            width = max(1, int(frame.width))
            height = max(1, int(frame.height))
            stride = int(getattr(plane, "line_size", width) or width)
            step_x = max(1, width // 32)
            step_y = max(1, height // 18)
            sample = bytearray()
            for y in range(0, height, step_y):
                row = y * stride
                for x in range(0, width, step_x):
                    pos = row + x
                    if pos < len(raw):
                        sample.append(raw[pos])
            return sample

        def _note_motion(self, frame) -> None:
            """Notify the call when the local scene starts moving."""
            if self._on_motion is None or frame is None:
                return
            try:
                sample = self._motion_sample(frame)
            except Exception:  # noqa: BLE001 - diagnostics only
                return
            previous = self._motion_prev
            self._motion_prev = sample
            if previous is None or len(previous) != len(sample):
                return
            delta = sum(abs(a - b) for a, b in zip(previous, sample))
            self._motion_score = delta / max(1, len(sample))
            self._motion_peak = max(
                getattr(self, "_motion_peak", 0.0), self._motion_score)
            if self._motion_score >= _VIDEO_MOTION_THRESHOLD:
                try:
                    self._on_motion()
                except Exception:  # noqa: BLE001 - never break video
                    logger.debug("CALL motion callback failed", exc_info=True)

        def motion_score(self) -> float:
            """The last sampled luma difference (diagnostics)."""
            return float(getattr(self, "_motion_score", 0.0))

        def take_motion_peak(self) -> float:
            """The highest sample since the previous call statistics."""
            peak = float(getattr(self, "_motion_peak", 0.0))
            self._motion_peak = 0.0
            return peak

        def last_size(self):
            """The last sent frame size (width, height) or None."""
            return self._last_size

        def fps(self) -> float:
            """The outgoing capture frame rate over the last sampling window."""
            now = time.monotonic()
            started = getattr(self, "_fps_started", now)
            elapsed = max(0.001, now - started)
            if elapsed >= 1.0:
                self._fps_value = getattr(self, "_sent_frames", 0) / elapsed
                self._sent_frames = 0
                self._fps_started = now
            return float(getattr(self, "_fps_value", 0.0))

        def set_source(self, mode: str, region=None) -> None:
            """Switch the outgoing video between the camera and a screen area.

            *region* is an ``(x, y, w, h)`` rectangle in logical screen
            coordinates; ``None`` means the primary monitor.
            """
            self._source = "screen" if mode == "screen" else "camera"
            self._region = tuple(region) if region else None
            self._last_image = None
            self._last_grab = 0.0
            self._last_size = None
            self._schedule_keyframe("source-change")
            if self._source == "camera":
                self._open_camera()
            logger.info("CALL video source -> %s%s", self._source,
                        " %s" % (self._region,) if self._region else "")

        async def recv(self):
            # aiortc >= 1.10: next_timestamp() is async and returns
            # (pts, time_base) in the video clock rate.
            pts, time_base = await self.next_timestamp()

            def _stamp(frame):
                frame.pts = pts
                frame.time_base = time_base
                return frame

            def _black():
                return _stamp(_black_frame(self._last_size))

            if self._stopped or not self._enabled:
                await asyncio.sleep(0.05)
                return _black()
            if self._source == "screen":
                frame = self._screen_frame()
                if frame is None:
                    return _black()
                self._note_motion(frame)
                self._note_size(frame)
                self._emit_local(frame)
                return _stamp(frame)
            if self._container is None and (time.monotonic()
                                            - self._last_open_attempt > 2.0):
                self._open_camera()
            if self._container is None or self._stream is None:
                await asyncio.sleep(0.05)
                return _black()
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(None, self._next_frame)
            self._decode_future = future
            future.add_done_callback(self._on_decode_done)
            try:
                frame = await future
            except RuntimeError:
                self._stopped = True
                return _black()
            if self._stopped:
                # stop() deferred the container close until this decode
                # returned; do not touch the decoded frame any more.
                return _black()
            if self._handle_decode_error():
                await asyncio.sleep(0.05)
                return _black()
            if frame is None:
                frame = _black_frame(self._last_size)
            else:
                frame = _limit_video_frame(frame, self._max_height)
                self._note_motion(frame)
                self._note_size(frame)
                # Surface the real camera frame for the local self-preview
                # (black frames are not mirrored to the UI).
                self._emit_local(frame)
            return _stamp(frame)

        def _screen_frame(self):
            """Grab the screen region at most ``screen_fps`` times a second.

            ``grabWindow`` must run on the GUI thread (``recv`` is a coroutine
            on the same loop), and repeated grabs of a large screen are costly,
            so the same frame is reused between grabs.
            """
            now = time.monotonic()
            if (self._last_image is None
                    or now - self._last_grab >= 1.0 / self._screen_fps):
                self._last_grab = now
                self._last_image = _grab_screen_image(self._region)
            if self._last_image is None:
                return None
            return _qimage_to_frame(self._last_image, self._screen_max_width,
                                    self._screen_max_height)

        def _emit_local(self, frame) -> None:
            if self._on_frame is None:
                return
            try:
                self._on_frame(frame)
            except Exception:
                logger.debug("CALL local frame relay failed", exc_info=True)

        def _next_frame(self):
            # Snapshot both attributes before the blocking decode: stop() must
            # not clear them under the executor thread.
            container = self._container
            stream = self._stream
            if container is None or stream is None:
                return None
            try:
                for frame in container.decode(stream):
                    return frame.reformat(format="yuv420p")
            except Exception as exc:  # noqa: BLE001 - localized FFmpeg error
                self._decode_error = decode_ffmpeg_error(exc)
            return None

        def _close_container(self, container=None) -> None:
            """Close *container* once it is no longer used by the decoder."""
            if container is None:
                container = self._container
            if self._container is container:
                self._container = None
                self._stream = None
            try:
                if container is not None:
                    container.close()
                    logger.debug("CALL camera capture closed")
            except Exception:
                logger.debug("CALL camera capture close failed", exc_info=True)

        def _on_decode_done(self, future) -> None:
            """Finish a deferred stop after the executor decode returned."""
            if getattr(self, "_decode_future", None) is future:
                self._decode_future = None
            if not getattr(self, "_stopped", False):
                return
            container = getattr(self, "_pending_close", None)
            self._pending_close = None
            if container is not None:
                self._close_container(container)

        def _handle_decode_error(self) -> bool:
            """Drop a failing capture and reopen it (auto after a custom mode)."""
            error = self._decode_error
            if not error:
                return False
            self._decode_error = ""
            container = self._container
            self._container = None
            self._stream = None
            try:
                if container is not None:
                    container.close()
            except Exception:
                pass
            if self._camera_mode:
                logger.warning(
                    "CALL camera mode %s failed to decode (%s); using auto",
                    self._camera_mode, error)
                self._camera_mode = ""
            else:
                logger.warning("CALL camera decode failed: %s", error)
            self._last_open_attempt = 0.0
            return True

        def stop(self):
            self._stopped = True
            future = getattr(self, "_decode_future", None)
            container = self._container
            if future is not None and not future.done():
                # The executor is inside container.decode(); closing the PyAV
                # container here would free the decoder under it.  Let the
                # future callback close it after the current call returns.
                self._pending_close = container
                return
            self._close_container(container)


def _silence(samples: int, channels: int = AUDIO_CHANNELS):
    layout = "stereo" if channels == 2 else "mono"
    frame = av.AudioFrame(format=AUDIO_FORMAT, layout=layout, samples=samples)
    frame.sample_rate = AUDIO_RATE
    frame.planes[0].update(b"\x00" * (samples * channels * 2))
    return frame


def _black_frame(size=None):
    """A black frame; *size* keeps the last real frame's dimensions."""
    width, height = size or (320, 240)
    width = max(2, int(width)) & ~1
    height = max(2, int(height)) & ~1
    frame = av.VideoFrame(width, height, "yuv420p")
    for plane in frame.planes:
        plane.update(b"\x00" * plane.buffer_size)
    return frame


def _frame_to_qimage(frame):
    """Convert a decoded PyAV video frame to a ``QImage``; None on failure."""
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


def _qimage_to_frame(image, max_width: int = 0, max_height: int = 0):
    """Convert a ``QImage`` to a yuv420p ``av.VideoFrame``; None on failure.

    The image is only ever **downscaled** to fit the ``max_width``×``max_height``
    box (aspect preserved); a smaller capture is sent as is.  PyQt6 is
    imported locally because screen capture does not need Qt Multimedia.
    """
    if av is None or image is None or image.isNull():
        return None
    from PyQt6 import QtCore, QtGui
    try:
        scale = 1.0
        if max_width and image.width() > max_width:
            scale = min(scale, max_width / float(image.width()))
        if max_height and image.height() > max_height:
            scale = min(scale, max_height / float(image.height()))
        if scale < 1.0:
            target_w = max(2, int(image.width() * scale)) & ~1
            target_h = max(2, int(image.height() * scale)) & ~1
            image = image.scaled(
                target_w, target_h,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
        # yuv420p needs even dimensions; trim a stray pixel, never upscale.
        if image.width() % 2 or image.height() % 2:
            image = image.copy(0, 0, image.width() - image.width() % 2,
                               image.height() - image.height() % 2)
        if image.format() != QtGui.QImage.Format.Format_RGB888:
            image = image.convertToFormat(QtGui.QImage.Format.Format_RGB888)
        width, height = image.width(), image.height()
        stride = image.bytesPerLine()
        row = width * 3
        raw = image.constBits().asstring(image.sizeInBytes())
        if stride != row:
            raw = b"".join(raw[y * stride:y * stride + row]
                           for y in range(height))
        frame = av.VideoFrame(width, height, "rgb24")
        plane = frame.planes[0]
        # PyAV pads a plane row to ``line_size`` (e.g. 208 px for a 200 px
        # rgb24 image), so pad each row before the bulk update.
        if plane.line_size == row:
            plane.update(raw)
        else:
            padded = b"".join(raw[y * row:(y + 1) * row].ljust(
                plane.line_size, b"\x00") for y in range(height))
            plane.update(padded)
        return frame.reformat(format="yuv420p")
    except Exception:
        logger.debug("CALL screen frame conversion failed", exc_info=True)
        return None


def _limit_video_frame(frame, max_height: int = 0):
    """Downscale a camera frame to *max_height* (never enlarge it)."""
    if frame is None or not max_height or frame.height <= max_height:
        return frame
    scale = max_height / float(frame.height)
    width = max(2, int(frame.width * scale)) & ~1
    height = max(2, int(max_height)) & ~1
    try:
        return frame.reformat(width=width, height=height, format="yuv420p")
    except Exception:  # noqa: BLE001 - keep the original frame
        logger.debug("CALL camera downscale failed", exc_info=True)
        return frame


def _grab_screen_image(region=None):
    """QImage of *region* (x, y, w, h) or the primary monitor; None on failure."""
    try:
        from PyQt6 import QtCore
        from stanza_im.include import screen as screen_mod
        if region:
            x, y, w, h = region
            pixmap = screen_mod.grab_region(QtCore.QPoint(int(x), int(y)),
                                            QtCore.QSize(int(w), int(h)))
        else:
            pixmap = screen_mod.grab_screen()
    except Exception:
        logger.debug("CALL screen grab failed", exc_info=True)
        return None
    if pixmap is None or pixmap.isNull():
        return None
    return pixmap.toImage()


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


def _patch_encoder_defaults(encoder_cls, kind: str) -> None:
    """Apply the configured bitrate when aiortc creates an encoder."""
    if encoder_cls is None or getattr(encoder_cls, "_stanza_defaults_patched",
                                      False):
        return
    original_init = encoder_cls.__init__

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            if kind == "audio":
                codec = getattr(self, "codec", None)
                if codec is not None:
                    codec.bit_rate = _MEDIA_DEFAULTS["audio_bitrate"]
                _AUDIO_ENCODERS.add(self)
            else:
                _VIDEO_RATE.user_change = True
                try:
                    self.target_bitrate = _MEDIA_DEFAULTS["video_bitrate"]
                finally:
                    _VIDEO_RATE.user_change = False
                _VIDEO_ENCODERS.add(self)
        except Exception:  # noqa: BLE001 - never break the encoder setup
            logger.debug("CALL could not apply the encoder defaults",
                         exc_info=True)

    encoder_cls.__init__ = __init__
    encoder_cls._stanza_defaults_patched = True


def _patch_video_bitrate_cap(encoder_cls) -> None:
    """Route REMB through the loss-aware video rate controller.

    The settings/live menu value is a hard ceiling; REMB may adapt below it,
    but the controller resists abrupt drops without loss and allows only
    stepped decreases at medium loss.
    """
    if encoder_cls is None or getattr(encoder_cls, "_stanza_cap_patched",
                                      False):
        return
    original = encoder_cls.target_bitrate

    def getter(self):
        return original.fget(self)

    def setter(self, value):
        cap = _MEDIA_DEFAULTS.get("video_bitrate") or 0
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            numeric = None
        if numeric is not None and cap:
            numeric = min(numeric, cap)
            if not _VIDEO_RATE.user_change:
                old = _VIDEO_RATE.target
                numeric = _VIDEO_RATE.on_remb(numeric)
                if numeric != old:
                    logger.debug(
                        "CALL rate %d -> %d (loss=%.1f%%, remb=%d)",
                        old, numeric, _VIDEO_RATE.loss_pct(),
                        _VIDEO_RATE.last_remb)
        original.fset(self, numeric if numeric is not None else value)

    encoder_cls.target_bitrate = property(getter, setter)
    encoder_cls._stanza_cap_patched = True


def _patch_video_encoder_keyframes(encoder_cls) -> None:
    """Let ``request_video_keyframe`` force the next encoded frame to be an I-frame."""
    if encoder_cls is None or getattr(encoder_cls, "_stanza_keyframe_patched",
                                      False):
        return
    original_encode = encoder_cls.encode

    def encode(self, frame, force_keyframe=False):
        if getattr(self, "_stanza_keyframe", False):
            force_keyframe = True
            self._stanza_keyframe = False
        return original_encode(self, frame, force_keyframe)

    encoder_cls.encode = encode
    encoder_cls._stanza_keyframe_patched = True


def _install_encoder_defaults() -> None:
    """Patch the Opus/VP8/H264 encoders with the configured bitrates."""
    if not HAS_AIORTC:
        return
    for module_name, class_name, kind in (
            ("aiortc.codecs.opus", "OpusEncoder", "audio"),
            ("aiortc.codecs.vpx", "Vp8Encoder", "video"),
            ("aiortc.codecs.h264", "H264Encoder", "video")):
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 - not every build has every codec
            logger.debug("CALL %s is not available", module_name)
            continue
        _patch_encoder_defaults(getattr(module, class_name, None), kind)
        if kind == "video":
            video_cls = getattr(module, class_name, None)
            _patch_video_bitrate_cap(video_cls)
            _patch_video_encoder_keyframes(video_cls)


def _install_inbound_byte_counter() -> None:
    """Make aiortc keep per-stream received byte counters.

    aiortc's ``RTCInboundRtpStreamStats`` exposes packets/jitter but no
    ``bytesReceived``.  Wrapping ``StreamStatistics.add`` is the smallest
    non-invasive way to derive the incoming video/audio bitrate for the call
    diagnostics.
    """
    if not HAS_AIORTC:
        return
    try:
        from aiortc.rtcrtpreceiver import StreamStatistics
    except Exception:  # noqa: BLE001 - optional internals
        return
    if getattr(StreamStatistics, "_stanza_bytes_patched", False):
        return
    original_add = StreamStatistics.add

    def add(self, packet):
        try:
            self.bytes_received = (
                int(getattr(self, "bytes_received", 0) or 0)
                + len(packet.payload)
                + int(getattr(packet, "padding_size", 0) or 0))
        except Exception:  # noqa: BLE001 - diagnostics only
            pass
        return original_add(self, packet)

    StreamStatistics.add = add
    StreamStatistics._stanza_bytes_patched = True


def _receiver_bytes(receiver) -> int:
    """Total RTP payload bytes received on one aiortc receiver."""
    streams = getattr(receiver, "_RTCRtpReceiver__remote_streams", {}) or {}
    return sum(int(getattr(stream, "bytes_received", 0) or 0)
               for stream in streams.values())


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
        except ModuleNotFoundError:
            # Not every aiortc build ships every codec module (e.g. g722);
            # that is expected, so warn without dumping a traceback.
            logger.warning(
                "CALL audio codec %s is not available in this aiortc build; "
                "its encoder is left unpatched", module_name)
            continue
        except Exception:
            logger.debug("CALL could not patch %s", module_name, exc_info=True)
            continue
        for class_name in class_names:
            _patch_audio_encoder(getattr(module, class_name, None))


_install_audio_resampler_compat()
_install_encoder_defaults()
_install_inbound_byte_counter()


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

    def create_call(self, ice_servers, devices=None, on_ice_candidate=None,
                    on_remote_track=None, on_state=None, on_local_frame=None):
        raise RuntimeError("calling is not available")

    def create_local_preview(self, devices=None, on_frame=None):
        """A standalone camera capture that only feeds the UI (no peer)."""
        return None


class NullMediaEngine(MediaEngine):
    name = "null"
    available = False


if HAS_AIORTC:
    class AiortcCall:
        """One RTP session backed by an ``RTCPeerConnection``."""

        def __init__(self, ice_servers, devices=None,
                     on_ice_candidate=None, on_remote_track=None,
                     on_state=None, on_local_frame=None):
            self.devices = devices or {}
            self._codec_choices = {
                "audio": str(self.devices.get("audio_codec") or "auto").lower(),
                "video": str(self.devices.get("video_codec") or "auto").lower(),
            }
            set_media_defaults(self.devices.get("audio_bitrate_kbps"),
                               self.devices.get("video_bitrate_kbps"))
            self.on_ice_candidate = on_ice_candidate
            self.on_remote_track = on_remote_track
            self.on_state = on_state
            self.on_local_frame = on_local_frame
            self.local_preview_enabled = False
            self._audio_play = None
            self._video_widget = None
            self._tasks: list[asyncio.Task] = []
            self._local_audio = None
            self._local_video = None
            self._local_sdp = ""
            self._remote_sdp = ""
            self._remote_kind = ""
            self._remote_size = None
            self._stats: dict[str, int | None] = {}
            self._stats_prev: dict[str, tuple[float, int]] = {}
            self._stats_task = None
            self._closed = False
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
            state = getattr(self.pc, "connectionState", "")
            logger.info("CALL connection state: %s", state)
            if state == "connected":
                self._start_stats()
            if state == "connected" and self._local_video is not None:
                # A peer that missed the initial keyframe shows a green
                # picture until it is forced to decode a fresh I-frame.
                try:
                    loop = asyncio.get_event_loop()
                    for delay in (0.5, 1.5, 3.0):
                        loop.call_later(delay, request_video_keyframe,
                                        "connected")
                except Exception:  # noqa: BLE001 - no running loop
                    pass
            if self.on_state:
                self.on_state("connection", state)

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
                    if (self._audio_play is not None
                            and self._audio_play.enabled):
                        self._audio_play.write(frame)
            except Exception:
                # Normal at call end (MediaStreamError) — no traceback.
                logger.debug("CALL audio track ended")

        async def _consume_video(self, track):
            while True:
                try:
                    frame = await track.recv()
                except Exception:
                    # Normal at call end (MediaStreamError) — no traceback.
                    logger.debug("CALL video track ended")
                    return
                self._remote_size = (frame.width, frame.height)
                image = _frame_to_qimage(frame)
                if image is not None and self.on_remote_track:
                    self.on_remote_track("frame", image)

        # ── local media ───────────────────────────────────────────
        def add_audio(self):
            self._local_audio = _AudioCaptureTrack(
                self.devices.get("audio_input", ""))
            self.pc.addTrack(self._local_audio)
            self._apply_codec_preferences("audio")
            logger.info("CALL added local audio track")

        def add_video(self):
            self._local_video = _VideoCaptureTrack(
                self.devices.get("video_input", ""),
                on_frame=self._forward_local_frame,
                on_motion=self._on_local_motion,
                screen_fps=int(self.devices.get("screen_fps", 5) or 5),
                screen_max_width=int(
                    self.devices.get("screen_max_width", 1920) or 0),
                screen_max_height=int(
                    self.devices.get("screen_max_height", 0) or 0),
                max_height=int(
                    self.devices.get("video_max_height", 0) or 0),
                camera_mode=str(self.devices.get("camera_mode") or ""))
            self.pc.addTrack(self._local_video)
            self._apply_codec_preferences("video")
            logger.info("CALL added local video track")

        def _on_local_motion(self):
            """A local scene started moving: try to recover video quality."""
            try:
                boost_video_target()
            except Exception:  # noqa: BLE001 - media must keep running
                logger.debug("CALL motion boost failed", exc_info=True)

        def _forward_local_frame(self, frame):
            """Relay one own-camera frame to the UI (self-preview)."""
            if self.on_local_frame is None or not self.local_preview_enabled:
                return
            try:
                image = _frame_to_qimage(frame)
            except Exception:
                logger.debug("CALL local frame conversion failed",
                             exc_info=True)
                return
            if image is not None:
                self.on_local_frame(image)

        def set_local_preview(self, enabled: bool) -> None:
            """Toggle own-frame conversion for the UI self-preview."""
            self.local_preview_enabled = bool(enabled)

        def set_audio_enabled(self, enabled: bool) -> None:
            if self._local_audio is not None:
                self._local_audio.set_enabled(enabled)

        def set_remote_audio_enabled(self, enabled: bool) -> None:
            """Mute/unmute playback of this session's remote audio."""
            if self._audio_play is not None:
                self._audio_play.set_enabled(enabled)

        def set_video_enabled(self, enabled: bool) -> None:
            if self._local_video is not None:
                self._local_video.set_enabled(enabled)

        def set_video_quality(self, max_height: int) -> None:
            """Change the outgoing video resolution cap live (0 = source)."""
            if self._local_video is None:
                return
            self._local_video.set_max_height(max_height)
            self._local_video.set_screen_box(0, max_height)

        def set_video_bitrate(self, kbps: int) -> None:
            """Change the outgoing video bitrate live (updates live encoders)."""
            set_media_defaults(video_kbps=kbps)
            try:
                encoder = self._sender_encoder("video")
                target = getattr(encoder, "target_bitrate", None)
                logger.info("CALL video bitrate requested=%skbps default=%s "
                            "target=%s", kbps,
                            media_defaults()["video_bitrate"] // 1000,
                            (int(target) // 1000) if target else "none")
            except Exception:  # noqa: BLE001 - diagnostics only
                logger.debug("CALL video bitrate diagnostics failed",
                             exc_info=True)

        def set_video_source(self, mode: str, region=None) -> None:
            """Switch the outgoing video between the camera and a screen area."""
            if self._local_video is not None:
                self._local_video.set_source(mode, region)

        def _answer_sdp(self) -> str:
            """The SDP that carries the negotiated codecs (the answer)."""
            if self._remote_kind == "answer" and self._remote_sdp:
                return self._remote_sdp
            return self._local_sdp

        def _sender_encoder(self, kind: str):
            try:
                for sender in self.pc.getSenders():
                    if getattr(sender, "kind", "") == kind:
                        return getattr(sender, "_RTCRtpSender__encoder", None)
            except Exception:  # noqa: BLE001 - aiortc internals
                pass
            return None

        def _start_stats(self) -> None:
            if self._stats_task is not None or self._closed:
                return
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return
            self._stats_task = loop.create_task(self._stats_loop())

        async def _stats_loop(self) -> None:
            try:
                while not self._closed:
                    await self.sample_stats()
                    await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - stats must never break the call
                logger.debug("CALL stats loop stopped", exc_info=True)

        async def sample_stats(self) -> None:
            """Sample the RTP octet counters and derive the current bitrates."""
            now = time.monotonic()
            totals: dict[str, tuple[float, int]] = {}
            try:
                senders = list(self.pc.getSenders())
            except Exception:  # noqa: BLE001
                senders = []
            for sender in senders:
                kind = getattr(sender, "kind", "")
                try:
                    report = await sender.getStats()
                except Exception:  # noqa: BLE001
                    continue
                for stat in report.values():
                    stype = getattr(stat, "type", "")
                    if stype == "outbound-rtp":
                        totals["out_" + kind] = (
                            now, int(getattr(stat, "bytesSent", 0) or 0))
                    elif stype == "transport":
                        totals["in_total"] = (
                            now, int(getattr(stat, "bytesReceived", 0) or 0))
                    elif stype == "remote-inbound-rtp" and kind == "video":
                        note_video_loss(getattr(stat, "fractionLost", 0))
            try:
                receivers = list(self.pc.getReceivers())
            except Exception:  # noqa: BLE001
                receivers = []
            for receiver in receivers:
                kind = getattr(receiver, "kind", "")
                try:
                    await receiver.getStats()
                except Exception:  # noqa: BLE001
                    continue
                totals["in_" + kind] = (now, _receiver_bytes(receiver))
            for key, (stamp, total) in totals.items():
                previous = self._stats_prev.get(key)
                if previous is not None and stamp > previous[0]:
                    bits = max(0, total - previous[1]) * 8
                    self._stats[key + "_bps"] = int(
                        bits / (stamp - previous[0]))
                self._stats_prev[key] = (stamp, total)
            if self._stats:
                encoder = self._sender_encoder("video")
                target = getattr(encoder, "target_bitrate", None)
                fps = 0.0
                if self._local_video is not None:
                    try:
                        fps = self._local_video.fps()
                    except (AttributeError, RuntimeError):
                        pass
                motion = 0.0
                if self._local_video is not None:
                    try:
                        motion = self._local_video.take_motion_peak()
                    except (AttributeError, RuntimeError):
                        pass
                logger.debug(
                    "CALL stats out_video=%sbps out_audio=%sbps in=%sbps "
                    "in_video=%sbps in_audio=%sbps target=%sbps "
                    "loss=%.1f%% fps=%.1f motion_peak=%.1f",
                    self._stats.get("out_video_bps"),
                    self._stats.get("out_audio_bps"),
                    self._stats.get("in_total_bps"),
                    self._stats.get("in_video_bps"),
                    self._stats.get("in_audio_bps"),
                    int(target) if target else "none",
                    _VIDEO_RATE.loss_pct(), fps, motion)

        def quality_info(self) -> dict:
            """Codec/resolution/bitrate snapshot for the call info popup."""
            codecs = sdp_media_codecs(self._answer_sdp())
            defaults = media_defaults()
            out_size = (self._local_video.last_size()
                        if self._local_video is not None else None)
            video_encoder = self._sender_encoder("video")
            audio_encoder = self._sender_encoder("audio")
            video_target = getattr(video_encoder, "target_bitrate", None)
            audio_target = getattr(getattr(audio_encoder, "codec", None),
                                   "bit_rate", None)
            return {
                "audio_codec": codecs.get("audio", ""),
                "video_codec": codecs.get("video", ""),
                "out_width": out_size[0] if out_size else None,
                "out_height": out_size[1] if out_size else None,
                "in_width": (self._remote_size[0]
                             if self._remote_size else None),
                "in_height": (self._remote_size[1]
                              if self._remote_size else None),
                "video_kbps": int(round((video_target
                                         or defaults["video_bitrate"]) / 1000)),
                "audio_kbps": int(round((audio_target
                                         or defaults["audio_bitrate"]) / 1000)),
                "out_video_bps": self._stats.get("out_video_bps"),
                "out_audio_bps": self._stats.get("out_audio_bps"),
                "in_video_bps": self._stats.get("in_video_bps"),
                "in_audio_bps": self._stats.get("in_audio_bps"),
                "in_bps": self._stats.get("in_total_bps"),
            }

        def _apply_codec_preferences(self, kind: str) -> None:
            """Prefer the configured codec for the transceivers of *kind*."""
            ordered = _ordered_codecs(kind, self._codec_choices.get(kind, ""))
            if not ordered:
                return
            try:
                transceivers = self.pc.getTransceivers()
            except Exception:  # noqa: BLE001 - older aiortc
                return
            for transceiver in transceivers:
                track = getattr(transceiver.receiver, "track", None)
                if getattr(track, "kind", "") != kind:
                    continue
                try:
                    transceiver.setCodecPreferences(ordered)
                    logger.debug("CALL %s codec preference -> %s",
                                 kind, self._codec_choices.get(kind))
                except Exception:  # noqa: BLE001 - optional API
                    logger.debug("CALL setCodecPreferences failed",
                                 exc_info=True)

        # ── SDP ───────────────────────────────────────────────────
        async def create_offer(self) -> str:
            self._apply_codec_preferences("audio")
            self._apply_codec_preferences("video")
            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)
            self._local_sdp = self.pc.localDescription.sdp
            logger.debug("CALL local offer SDP:\n%s", self._local_sdp)
            return self._local_sdp

        async def create_answer(self) -> str:
            self._apply_codec_preferences("audio")
            self._apply_codec_preferences("video")
            answer = await self.pc.createAnswer()
            await self.pc.setLocalDescription(answer)
            self._local_sdp = self.pc.localDescription.sdp
            logger.debug("CALL local answer SDP:\n%s", self._local_sdp)
            return self._local_sdp

        async def set_remote(self, sdp: str, kind: str = "offer") -> None:
            logger.debug("CALL remote %s SDP:\n%s", kind, sdp)
            self._remote_sdp = str(sdp or "")
            self._remote_kind = kind
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
            """Nominate ourselves (fallback when a controlled peer never does).

            aioice performs regular nomination only inside a fresh
            connectivity check, so a bare role flip is a no-op on an already
            checked list and only clashes with a late peer nomination into a
            487 role-conflict deadlock.  We therefore switch to controlling
            *and* re-run the best succeeded, not-yet-nominated pair's check:
            that check is sent with ``USE-CANDIDATE`` and, on success,
            completes ICE.
            """
            switched = False
            for ice in self._ice_transports():
                connection = getattr(ice, "_connection", None)
                if connection is None:
                    continue
                try:
                    if self._force_controlling(connection):
                        switched = True
                    self._nominate_best_pair(connection)
                except Exception:
                    logger.debug("CALL ICE role switch failed", exc_info=True)
            return switched

        @staticmethod
        def _force_controlling(connection) -> bool:
            """Claim the controlling role and win any role conflict.

            A compliant controlling peer resolves a ``ICE-CONTROLLING``
            request against its own tie-breaker (RFC 8445 §7.3.1.1): the
            higher one stays controlling, the other becomes controlled.
            Since aioice's tie-breaker is a random 64-bit value we would lose
            ~50 % of the time and the peer would reject our ``USE-CANDIDATE``
            with 487, leaving ICE stuck in ``checking``.  Bumping the
            tie-breaker to its maximum before the role switch makes us win
            deterministically, so the peer backs down and accepts the
            nomination.
            """
            if connection.ice_controlling:
                return False
            connection._tie_breaker = (1 << 64) - 1
            connection.switch_role(True)
            return True

        @staticmethod
        def _nominate_best_pair(connection) -> None:
            """Send USE-CANDIDATE for the best succeeded, non-nominated pair."""
            nominating = set(connection._nominating)
            nominated = dict(connection._nominated)
            for pair in connection._check_list:
                if pair.component in nominating or pair.component in nominated:
                    continue
                if pair.state != getattr(pair.State, "SUCCEEDED"):
                    continue
                if pair.task is not None and not pair.task.done():
                    continue
                pair.task = asyncio.create_task(connection.check_start(pair))
                return

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
            self._closed = True
            if self._stats_task is not None:
                self._stats_task.cancel()
                self._stats_task = None
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


    class _LocalPreviewCapture:
        """Standalone camera capture that only feeds the UI self tile.

        Used for a Muji conference while no peer Jingle session (and thus no
        shared local video track) exists yet.  The capture is pumped by its own
        task; real camera frames reach *on_frame* through the track's
        ``_emit_local`` (black frames are skipped).
        """

        def __init__(self, device_id: str = "", on_frame=None):
            # The UI expects QImage frames; the track emits raw PyAV frames,
            # so convert here (the AiortcCall path does the same).
            self._on_image = on_frame
            self._track = _VideoCaptureTrack(device_id, on_frame=self._emit)
            self._task = None
            self._closed = False

        def _emit(self, frame) -> None:
            if self._on_image is None:
                return
            image = _frame_to_qimage(frame)
            if image is not None:
                self._on_image(image)

        def start(self) -> None:
            if self._task is None and not self._closed:
                self._task = asyncio.ensure_future(self._run())

        async def _run(self) -> None:
            try:
                while not self._closed and not self._track._stopped:
                    await self._track.recv()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("CALL local preview capture ended",
                             exc_info=True)

        def stop(self) -> None:
            self._closed = True
            self._track.stop()
            if self._task is not None:
                self._task.cancel()
                self._task = None


    class AiortcMediaEngine(MediaEngine):
        name = "aiortc"
        available = True

        def enumerate_devices(self) -> dict:
            return enumerate_devices()

        def create_call(self, ice_servers, devices=None,
                        on_ice_candidate=None, on_remote_track=None,
                        on_state=None, on_local_frame=None) -> "AiortcCall":
            return AiortcCall(ice_servers, devices, on_ice_candidate,
                              on_remote_track, on_state, on_local_frame)

        def create_local_preview(self, devices=None,
                                 on_frame=None) -> "_LocalPreviewCapture":
            return _LocalPreviewCapture(
                (devices or {}).get("video_input", ""), on_frame)


_engine: MediaEngine | None = None


def get_engine() -> MediaEngine:
    global _engine
    if _engine is None:
        _engine = AiortcMediaEngine() if HAS_AIORTC else NullMediaEngine()
        logger.info("CALL media engine: %s (aiortc=%s, qtmm=%s)",
                    _engine.name, HAS_AIORTC, HAS_QTMM)
    return _engine
