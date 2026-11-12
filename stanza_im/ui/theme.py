"""Small helpers for palette-aware Qt widget colors.

The client follows the system Qt palette for every colour it does not let the
user override.  These helpers keep the fallback and contrast logic in one
place, so light and dark desktop themes behave the same way.
"""
from __future__ import annotations

from PyQt6 import QtGui, QtWidgets


def app_palette() -> QtGui.QPalette:
    """Return the application palette (a neutral one without QApplication)."""
    app = QtWidgets.QApplication.instance()
    return app.palette() if app is not None else QtGui.QPalette()


def is_dark(palette: QtGui.QPalette | None = None) -> bool:
    """Whether *palette* (default: application) is a dark colour scheme."""
    pal = palette if palette is not None else app_palette()
    return pal.color(QtGui.QPalette.ColorRole.Window).lightnessF() < 0.5


def contrasting_text(background) -> QtGui.QColor:
    """Black or white text with the best contrast against *background*."""
    color = QtGui.QColor(background)
    if not color.isValid():
        return QtGui.QColor("#000000")
    return QtGui.QColor("#000000" if color.lightnessF() >= 0.5
                        else "#ffffff")


def blend(foreground, background, alpha: float) -> QtGui.QColor:
    """Blend *foreground* into *background* with *alpha* (0..1)."""
    fg = QtGui.QColor(foreground)
    bg = QtGui.QColor(background)
    if not fg.isValid() or not bg.isValid():
        return QtGui.QColor(foreground)
    a = max(0.0, min(1.0, float(alpha)))
    return QtGui.QColor(
        round(fg.red() * a + bg.red() * (1.0 - a)),
        round(fg.green() * a + bg.green() * (1.0 - a)),
        round(fg.blue() * a + bg.blue() * (1.0 - a)),
    )


def muted_color(text, background, alpha: float = 0.62) -> QtGui.QColor:
    """A dimmed variant of *text* that stays readable on *background*."""
    return blend(text, background, alpha)


def error_color(palette: QtGui.QPalette | None = None) -> QtGui.QColor:
    """A red that remains readable in light and dark palettes."""
    return QtGui.QColor("#ff8a80" if is_dark(palette) else "#b00020")


def auto_color(value, palette: QtGui.QPalette | None = None,
               role: QtGui.QPalette.ColorRole = QtGui.QPalette.ColorRole.Base
               ) -> QtGui.QColor:
    """Return the explicit *value* or the palette colour for *role*."""
    text = str(value or "")
    color = QtGui.QColor(text)
    if text and color.isValid():
        return color
    pal = palette if palette is not None else app_palette()
    return pal.color(role)
