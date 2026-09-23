"""One-shot WAV playback for sound notifications (``QSoundEffect``).

The sound *themes* are read from ``resources/sounds/`` by
:mod:`stanza_im.include.sounds`.  Playback degrades to a no-op when Qt
Multimedia (or its audio backend, e.g. libpulse) is unavailable.

Qt Multimedia is imported lazily on the first playback: keeping it off the
startup path avoids loading the multimedia backend for users who never enable
sounds (and avoids a failed backend load on systems without libpulse).
"""
from __future__ import annotations

import logging

from stanza_im.include import sounds as sounds_mod

logger = logging.getLogger("stanza_im.sounds")

# Cache: False = not tried yet, True/False = backend availability afterwards.
_QTMM_READY: bool | None = None
_QSoundEffect = None
_QUrl = None


def _load_qtmm() -> bool:
    """Import QSoundEffect/QUrl once; return whether playback is available."""
    global _QTMM_READY, _QSoundEffect, _QUrl
    if _QTMM_READY is not None:
        return _QTMM_READY
    try:  # optional Qt Multimedia (needs libpulse/gstreamer on the system)
        from PyQt6.QtCore import QUrl
        from PyQt6.QtMultimedia import QSoundEffect  # type: ignore
        _QSoundEffect, _QUrl = QSoundEffect, QUrl
        _QTMM_READY = True
    except Exception as exc:  # pragma: no cover - import guard
        _QTMM_READY = False
        logger.info("Sound playback unavailable: %s", exc)
    return _QTMM_READY


class SoundPlayer:
    """Play the current theme's sound for an event key, one ``QSoundEffect``
    per file (kept referenced so short sounds are not garbage-collected)."""

    def __init__(self):
        self._theme = sounds_mod.DEFAULT_THEME
        self._sounds: dict[str, str] = {}
        self._effects: dict[str, object] = {}
        self.set_theme(self._theme)

    @property
    def available(self) -> bool:
        return _load_qtmm() and bool(self._sounds)

    def set_theme(self, theme_id: str) -> None:
        self._theme = theme_id or sounds_mod.DEFAULT_THEME
        self._sounds = sounds_mod.theme_sounds(self._theme)

    def _path(self, event: str, theme_id: str | None) -> str:
        if theme_id is None or theme_id == self._theme:
            return self._sounds.get(event, "")
        return sounds_mod.theme_sounds(theme_id).get(event, "")

    def play(self, event: str, theme_id: str | None = None) -> None:
        """Play *event* (optionally from *theme_id* without switching theme)."""
        if not _load_qtmm():
            return
        path = self._path(event, theme_id)
        if not path:
            return
        effect = self._effects.get(path)
        if effect is None:
            try:
                effect = _QSoundEffect()
                effect.setSource(_QUrl.fromLocalFile(path))
                effect.setVolume(1.0)
            except Exception:  # pragma: no cover - defensive
                logger.debug("Could not prepare sound %s", path, exc_info=True)
                return
            self._effects[path] = effect
        effect.play()

    def stop(self) -> None:
        for effect in self._effects.values():
            try:
                effect.stop()
            except Exception:  # pragma: no cover - defensive
                pass
