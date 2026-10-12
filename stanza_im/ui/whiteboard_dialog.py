"""Whiteboard dialog: a drawing canvas with an icon-only tool palette.

The board is local by default (drawing, editing, SVG export); the «Поделиться»
button starts a collaborative session (Jingle application + XEP-0284 SXE) for
the conversation, after which local edits are broadcast and remote edits are
applied to the canvas.
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

    share_requested = QtCore.pyqtSignal(str, bool)   # jid, is_muc

    def __init__(self, jid: str, parent=None, client=None, is_muc: bool = False):
        super().__init__(parent)
        self._jid = jid
        self._client = client
        self._is_muc = is_muc
        self._sid = ""
        self.setWindowTitle(tr("whiteboard_title"))
        self.setModal(False)
        self.resize(1040, 680)

        self._stroke = "#1a1a1a"
        self._fill = "#e53935"
        self._width = 2

        layout = QtWidgets.QVBoxLayout(self)
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 0)
        toolbar.setSpacing(2)

        self._canvas = WhiteboardCanvas(self)
        # Ctrl+0 resets the view zoom/pan (Ctrl+wheel zooms, in the canvas).
        zoom_reset = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+0"), self)
        zoom_reset.activated.connect(self._canvas.reset_view)
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

        toolbar.addSpacing(10)
        self._share_btn = self._tool_button("system-users.png",
                                            tr("whiteboard_share"))
        self._share_btn.setCheckable(True)
        self._share_btn.clicked.connect(self._on_share)
        toolbar.addWidget(self._share_btn)

        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        layout.addWidget(self._canvas, 1)

        self._sync_label = QtWidgets.QLabel(tr("whiteboard_not_shared"))
        self._sync_label.setContentsMargins(6, 2, 6, 4)
        layout.addWidget(self._sync_label)

        self._refresh_swatches()

        self._canvas.shape_added.connect(self._on_shape_added)
        self._canvas.shape_updated.connect(self._on_shape_updated)
        self._canvas.shape_removed.connect(self._on_shape_removed)

    # ── Collaboration ─────────────────────────────────────────────

    def session_id(self) -> str:
        return self._sid

    def _on_share(self, checked: bool) -> None:
        if not self._client:
            return
        if not checked:
            self._end_session()
            return
        self.share_requested.emit(self._jid, self._is_muc)

    def attach_session(self, sid: str) -> None:
        """Bind the dialog to a running collaborative session."""
        self._sid = sid
        self._share_btn.setChecked(True)
        self._sync_label.setText(tr("whiteboard_shared"))
        self.refresh_from_session()

    def detach_session(self) -> None:
        self._sid = ""
        self._share_btn.setChecked(False)
        self._sync_label.setText(tr("whiteboard_not_shared"))

    def set_local_only(self) -> None:
        """Mark the board as local (a session with our own JID is pointless)."""
        self._share_btn.setChecked(False)
        self._sync_label.setText(tr("whiteboard_local_only"))

    def show_warning(self, text: str) -> None:
        """Show a non-blocking notice without changing the session state."""
        self._sync_label.setText(text)

    def show_failed(self, reason: str) -> None:
        """Report a failed share and reset the dialog to the local board."""
        self._sid = ""
        self._share_btn.setChecked(False)
        if reason == "unavailable":
            self._sync_label.setText(tr("whiteboard_failed_offline"))
        else:
            self._sync_label.setText(
                tr("whiteboard_failed_error", condition=reason))

    def refresh_from_session(self) -> None:
        if not (self._client and self._sid):
            return
        shapes = self._client.whiteboard.shapes(self._sid)
        self._canvas.load_shapes(shapes)

    def _end_session(self) -> None:
        if self._client and self._sid:
            self._client.whiteboard.end_session(self._sid)
        self.detach_session()

    def _on_shape_added(self, shape: dict) -> None:
        if not (self._client and self._sid):
            return
        rid = self._client.whiteboard.add_shape(
            self._sid, WhiteboardCanvas.shape_attrs(shape))
        self._canvas.set_rid(shape["id"], rid)

    def _on_shape_updated(self, shape: dict) -> None:
        if not (self._client and self._sid and shape.get("rid")):
            return
        self._client.whiteboard.update_shape(
            self._sid, shape["rid"], WhiteboardCanvas.shape_attrs(shape))

    def _on_shape_removed(self, shape: dict) -> None:
        if not (self._client and self._sid and shape.get("rid")):
            return
        self._client.whiteboard.remove_shape(self._sid, shape["rid"])

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
