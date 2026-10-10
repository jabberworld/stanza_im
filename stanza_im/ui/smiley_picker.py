"""Popup smiley picker for the chat toolbar.

The picker is source-agnostic: a :class:`SmileySource` returns ``(token, icon)``
pairs and the chosen token is inserted into the message input as plain text.
Two sources are planned — the current ``smileys*.cfg`` emoticon set (token is
the text code, e.g. ``:-)``) and, later, a unicode-emoji catalogue wired into
the smiley-theme selector.
"""
from __future__ import annotations

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

logger = logging.getLogger("stanza_im.ui")

_ICON = 22
_BTN = _ICON + 6
_COLS = 8
_MAX_H = 260


class SmileySource:
    """A picker source: returns ordered ``(token, icon)`` pairs."""

    def entries(self) -> list[tuple[str, QtGui.QIcon]]:
        raise NotImplementedError


class EmoticonSetSource(SmileySource):
    """The active emoticon set: token is the plain-text code."""

    def __init__(self, skin: str):
        self._skin = skin

    def entries(self) -> list[tuple[str, QtGui.QIcon]]:
        from stanza_im.include import emoticons
        out: list[tuple[str, QtGui.QIcon]] = []
        for code, path in emoticons.set_items(self._skin):
            icon = QtGui.QIcon(path)
            if not icon.isNull():
                out.append((code, icon))
        return out


class UnicodeEmojiSource(SmileySource):
    """Unicode-emoji catalogue (placeholder for the future theme option).

    Not wired yet: it will return ``(emoji, glyph icon)`` pairs from the
    XEP-0444 catalogue once the smiley-theme selector offers the emoji variant.
    """

    def entries(self) -> list[tuple[str, QtGui.QIcon]]:
        return []


class SmileyPicker(QtWidgets.QFrame):
    """Frameless popup grid of smileys; emits the chosen token."""

    smiley_chosen = QtCore.pyqtSignal(str)

    def __init__(self, source: SmileySource, parent=None):
        super().__init__(parent, QtCore.Qt.WindowType.Popup)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        entries = source.entries()
        grid = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout(grid)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)
        for index, (token, icon) in enumerate(entries):
            btn = QtWidgets.QToolButton(grid)
            btn.setIcon(icon)
            btn.setIconSize(QtCore.QSize(_ICON, _ICON))
            btn.setFixedSize(_BTN, _BTN)
            btn.setAutoRaise(True)
            btn.setToolTip(token)
            btn.clicked.connect(
                lambda _checked=False, t=token: self._choose(t))
            layout.addWidget(btn, index // _COLS, index % _COLS)
        if not entries:
            layout.addWidget(QtWidgets.QLabel(""), 0, 0)
        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(grid)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        rows = max(1, (len(entries) + _COLS - 1) // _COLS)
        self.resize(_COLS * _BTN + 12, min(_MAX_H, rows * _BTN + 12))

    def _choose(self, token: str) -> None:
        self.close()
        if token:
            self.smiley_chosen.emit(token)
