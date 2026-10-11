"""Whiteboard dialog: a drawing canvas with an icon-only tool palette.

Phase 1 is local (drawing, editing, SVG export); collaborative synchronisation
(Jingle + XEP-0284 SXE) is added on top of the same document model later.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon
from stanza_im.ui.whiteboard_canvas import WhiteboardCanvas

_TOOLS = (
    ("select", "wb-select.svg", "whiteboard_tool_select"),
    ("move", "wb-move.svg", "whiteboard_tool_move"),
    ("rotate", "wb-rotate.svg", "whiteboard_tool_rotate"),
    ("scale", "wb-scale.svg", "whiteboard_tool_scale"),
    ("pencil", "wb-pencil.svg", "whiteboard_tool_pencil"),
    ("line", "wb-line.svg", "whiteboard_tool_line"),
    ("rect", "wb-rect.svg", "whiteboard_tool_rect"),
    ("ellipse", "wb-ellipse.svg", "whiteboard_tool_ellipse"),
    ("polygon", "wb-polygon.svg", "whiteboard_tool_polygon"),
)

_WIDTHS = (1, 2, 3, 5, 8)


class WhiteboardDialog(QtWidgets.QDialog):
    """A non-modal whiteboard window (one per conversation)."""

    def __init__(self, jid: str, parent=None):
        super().__init__(parent)
        self._jid = jid
        self.setWindowTitle(tr("whiteboard_title"))
        self.setModal(False)
        self.resize(760, 560)

        self._stroke = "#1a1a1a"
        self._fill = "#e53935"
        self._width = 2

        layout = QtWidgets.QVBoxLayout(self)
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 0)
        toolbar.setSpacing(2)

        self._canvas = WhiteboardCanvas(self)
        self._tool_group = QtWidgets.QButtonGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_buttons: dict[str, QtWidgets.QToolButton] = {}
        for tool, icon, tip_key in _TOOLS:
            button = self._tool_button(icon, tr(tip_key), checkable=True)
            button.clicked.connect(
                lambda _checked=False, t=tool: self._canvas.set_tool(t))
            self._tool_group.addButton(button)
            self._tool_buttons[tool] = button
            toolbar.addWidget(button)
        self._tool_buttons["pencil"].setChecked(True)

        toolbar.addSpacing(10)
        self._width_btn = self._tool_button("wb-line-width.svg",
                                            tr("whiteboard_line_width"))
        width_menu = QtWidgets.QMenu(self)
        for value in _WIDTHS:
            action = width_menu.addAction(f"{value} px")
            action.triggered.connect(
                lambda _checked=False, w=value: self._set_width(w))
        self._width_btn.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self._width_btn.setMenu(width_menu)
        toolbar.addWidget(self._width_btn)

        self._stroke_btn = self._tool_button("", tr("whiteboard_line_color"))
        self._stroke_btn.clicked.connect(self._pick_stroke)
        toolbar.addWidget(self._stroke_btn)

        self._fill_btn = self._tool_button("", tr("whiteboard_fill_color"))
        self._fill_btn.clicked.connect(self._pick_fill)
        toolbar.addWidget(self._fill_btn)

        toolbar.addSpacing(10)
        finish = self._tool_button("ok.png", tr("whiteboard_finish"))
        finish.clicked.connect(self._canvas.finish_drawing)
        toolbar.addWidget(finish)
        clear = self._tool_button("clear.png", tr("whiteboard_clear"))
        clear.clicked.connect(self._confirm_clear)
        toolbar.addWidget(clear)
        save = self._tool_button("wb-save.svg", tr("whiteboard_save_svg"))
        save.clicked.connect(self._save_svg)
        toolbar.addWidget(save)
        delete = self._tool_button("remove.svg", tr("whiteboard_tool_delete"))
        delete.clicked.connect(self._canvas.delete_selected)
        toolbar.addWidget(delete)

        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        layout.addWidget(self._canvas, 1)

        self._refresh_swatches()

    # ── Toolbar helpers ───────────────────────────────────────────

    def _tool_button(self, icon_name: str, tooltip: str,
                     checkable: bool = False) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton(self)
        if icon_name:
            path = find_icon(icon_name)
            if path:
                button.setIcon(QtGui.QIcon(path))
        button.setIconSize(QtCore.QSize(20, 20))
        button.setToolTip(tooltip)
        button.setCheckable(checkable)
        button.setAutoRaise(True)
        return button

    @staticmethod
    def _swatch(color: str) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(18, 18)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setBrush(QtGui.QColor(color))
        painter.setPen(QtGui.QPen(QtGui.QColor("#888888"), 1.0))
        painter.drawRoundedRect(1, 1, 16, 16, 3, 3)
        painter.end()
        return QtGui.QIcon(pixmap)

    def _refresh_swatches(self) -> None:
        self._stroke_btn.setIcon(self._swatch(self._stroke))
        self._fill_btn.setIcon(self._swatch(self._fill))

    def _set_width(self, value: int) -> None:
        self._width = int(value)
        self._canvas.set_width(self._width)
        self._width_btn.setToolTip(
            f"{tr('whiteboard_line_width')}: {self._width} px")

    def _pick_stroke(self) -> None:
        color = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(self._stroke), self, tr("whiteboard_line_color"))
        if color.isValid():
            self._stroke = color.name()
            self._canvas.set_stroke(self._stroke)
            self._refresh_swatches()

    def _pick_fill(self) -> None:
        color = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(self._fill), self, tr("whiteboard_fill_color"))
        if color.isValid():
            self._fill = color.name()
            self._canvas.set_fill(self._fill)
            self._refresh_swatches()

    def _confirm_clear(self) -> None:
        answer = QtWidgets.QMessageBox.question(
            self, tr("whiteboard_clear"), tr("whiteboard_clear_confirm"))
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            self._canvas.clear()

    def _save_svg(self) -> None:
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("whiteboard_save_svg"), "whiteboard.svg",
            "SVG (*.svg)")
        if path:
            try:
                self._canvas.save_svg(path)
            except OSError:
                QtWidgets.QMessageBox.warning(
                    self, tr("whiteboard_save_svg"),
                    tr("whiteboard_save_failed"))
