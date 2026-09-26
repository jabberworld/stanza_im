"""Emoji picker for XEP-0444 message reactions.

A popup with a search field, a "Recent" area above the category tabs and an
emoji grid built from the static :mod:`stanza_im.include.emoji_data` catalogue.
Clicking an emoji emits ``emoji_chosen`` (the caller sends the reaction and
closes the popup); a "Remove reaction" button emits ``remove_requested``.
"""
from __future__ import annotations

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include import emoji_data

logger = logging.getLogger(__name__)

_CATEGORY_KEYS = {
    "smileys": "reaction_category_smileys",
    "gestures": "reaction_category_gestures",
    "hearts": "reaction_category_hearts",
    "nature": "reaction_category_nature",
    "food": "reaction_category_food",
    "objects": "reaction_category_objects",
    "symbols": "reaction_category_symbols",
    "flags": "reaction_category_flags",
}

# Colour-emoji fonts, most complete first.  Qt renders emoji as monochrome
# glyphs (or tofu boxes) unless a font that actually carries the glyphs is
# selected explicitly, so the picker/grid must ask for one by name.
_EMOJI_FONT_CANDIDATES = (
    "Noto Color Emoji",
    "Apple Color Emoji",
    "Segoe UI Emoji",
    "Twemoji Mozilla",
    "JoyPixels",
    "EmojiOne Color",
    "Symbola",
    "Noto Emoji",
)

_emoji_family_cache: str | None = None


def emoji_font_family() -> str:
    """Return an installed colour-emoji font family, or ``""`` if none."""
    global _emoji_family_cache
    if _emoji_family_cache is not None:
        return _emoji_family_cache
    try:
        installed = set(QtGui.QFontDatabase.families())
    except Exception:  # noqa: BLE001 - never let font probing break the UI
        installed = set()
    for name in _EMOJI_FONT_CANDIDATES:
        if name in installed:
            _emoji_family_cache = name
            return name
    logger.debug("No colour-emoji font found among %s",
                 ", ".join(_EMOJI_FONT_CANDIDATES))
    _emoji_family_cache = ""
    return ""


def emoji_font(point_size: int = 18) -> QtGui.QFont:
    """Return a QFont suitable for rendering emoji at *point_size*."""
    font = QtGui.QFont()
    family = emoji_font_family()
    if family:
        font.setFamily(family)
    font.setPointSize(point_size)
    return font


class EmojiPickerDialog(QtWidgets.QDialog):
    """Pick an emoji to add as a reaction (search + recent + categories)."""

    emoji_chosen = QtCore.pyqtSignal(str)
    remove_requested = QtCore.pyqtSignal()

    def __init__(self, recent: list[str] | None = None, can_remove: bool = False,
                 parent=None):
        super().__init__(parent)
        self._recent = [e for e in (recent or []) if e]
        self._emoji_font = emoji_font(18)
        self.setWindowTitle(tr("emoji_picker_title"))
        self.setMinimumSize(360, 300)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._search = QtWidgets.QLineEdit(self)
        self._search.setPlaceholderText(tr("emoji_search_placeholder"))
        self._search.textChanged.connect(self._populate)
        layout.addWidget(self._search)

        recent_label = QtWidgets.QLabel(tr("reaction_category_recent"), self)
        self._recent_label = recent_label
        layout.addWidget(recent_label)

        self._recent_grid = _EmojiGrid(self, self._on_pick, rows=2)
        self._recent_grid.setFixedHeight(
            self._recent_grid.height_for_rows(2))
        layout.addWidget(self._recent_grid)

        self._tabs = QtWidgets.QTabWidget(self)
        for key in emoji_data.categories():
            self._tabs.addTab(self._make_grid(),
                              tr(_CATEGORY_KEYS.get(key, key)))
        layout.addWidget(self._tabs, 1)

        buttons = QtWidgets.QDialogButtonBox(self)
        if can_remove:
            remove = buttons.addButton(
                tr("reaction_remove"),
                QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
            remove.clicked.connect(self._on_remove)
        close = buttons.addButton(
            tr("dialog_cancel"), QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        close.clicked.connect(self.reject)
        layout.addWidget(buttons)

        self._populate("")

    # ── Build ───────────────────────────────────────────────────────

    def _make_grid(self) -> "_EmojiGrid":
        return _EmojiGrid(self, self._on_pick)

    def _category_grids(self) -> list:
        return [self._tabs.widget(i) for i in range(self._tabs.count())]

    def _populate(self, query: str) -> None:
        query = (query or "").strip()
        if query:
            # A search shows its result set on the active category tab and
            # hides the "Recent" area.
            hits = emoji_data.search(query)
            for grid in self._category_grids():
                grid.set_emoji(hits)
            self._set_recent_visible(False)
            return
        self._set_recent_visible(bool(self._recent))
        self._recent_grid.set_emoji(self._recent)
        for key, grid in zip(emoji_data.categories(), self._category_grids()):
            grid.set_emoji(emoji_data.by_category(key))

    def _set_recent_visible(self, visible: bool) -> None:
        self._recent_label.setVisible(visible)
        self._recent_grid.setVisible(visible)

    # ── Events ──────────────────────────────────────────────────────

    def _on_pick(self, emoji: str) -> None:
        if emoji:
            self.emoji_chosen.emit(emoji)

    def _on_remove(self) -> None:
        self.remove_requested.emit()


class _EmojiGrid(QtWidgets.QScrollArea):
    """A scrollable flow grid of emoji buttons."""

    _COLUMNS = 8
    _BUTTON = 32
    _SPACING = 2

    def __init__(self, parent, on_pick, rows: int = 0):
        super().__init__(parent)
        self._on_pick = on_pick
        self._rows = rows
        self._font = emoji_font(18)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._inner = QtWidgets.QWidget()
        self._grid = QtWidgets.QGridLayout(self._inner)
        self._grid.setSpacing(self._SPACING)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self.setWidget(self._inner)

    def height_for_rows(self, rows: int) -> int:
        """Pixel height that fits *rows* rows of emoji buttons."""
        return (rows * self._BUTTON + max(0, rows - 1) * self._SPACING
                + 2 * self.frameWidth() + 4)

    def set_emoji(self, emoji: list[str]) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        limit = self._rows * self._COLUMNS if self._rows else None
        glyphs = emoji[:limit] if limit else emoji
        for index, glyph in enumerate(glyphs):
            button = QtWidgets.QToolButton(self._inner)
            button.setText(glyph)
            button.setAutoRaise(True)
            button.setFixedSize(self._BUTTON, self._BUTTON)
            button.setFont(self._font)
            button.clicked.connect(
                lambda checked=False, e=glyph: self._on_pick(e))
            self._grid.addWidget(button, index // self._COLUMNS,
                                 index % self._COLUMNS)
        self._grid.setRowStretch(self._grid.rowCount(), 1)
