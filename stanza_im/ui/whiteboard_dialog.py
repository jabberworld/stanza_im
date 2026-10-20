"""Whiteboard dialog: a drawing canvas with an icon-only tool palette.

The board is local by default (drawing, editing, SVG export); the «Поделиться»
button starts a collaborative session (Jingle application + XEP-0284 SXE) for
the conversation, after which local edits are broadcast and remote edits are
applied to the canvas.
"""
from __future__ import annotations

import os
import tempfile
import time

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon
from stanza_im.ui.whiteboard_canvas import (IMAGE_MAX_BYTES, WhiteboardCanvas,
                                            image_data_uri)

_TOOLS = (
    ("select", "wb-select.svg", "whiteboard_tool_select"),
    ("move", "wb-move.svg", "whiteboard_tool_move"),
    ("rotate", "wb-rotate.svg", "whiteboard_tool_rotate"),
    ("scale", "wb-scale.svg", "whiteboard_tool_scale"),
    ("pencil", "wb-pencil.svg", "whiteboard_tool_pencil"),
    ("line", "wb-line.svg", "whiteboard_tool_line"),
    ("arrow", "wb-arrow.svg", "whiteboard_tool_arrow"),
    ("rect", "wb-rect.svg", "whiteboard_tool_rect"),
    ("ellipse", "wb-ellipse.svg", "whiteboard_tool_ellipse"),
    ("polygon", "wb-polygon.svg", "whiteboard_tool_polygon"),
    ("fill", "wb-fill.svg", "whiteboard_tool_fill"),
    ("eraser", "wb-eraser.svg", "whiteboard_tool_eraser"),
    ("text", "wb-text.svg", "whiteboard_tool_text"),
)

_WIDTHS = (1, 2, 3, 5, 8)

#: Canvas-size presets, in increasing order (600×400 is the profile's default).
_CANVAS_PRESETS = ((600, 400), (640, 480), (800, 600), (1024, 768), (1280, 720),
                   (1280, 1024), (1440, 900), (1600, 1200), (1920, 1080))


def _canvas_size_items(width: int, height: int) -> tuple[list[str], int]:
    """Preset labels for the canvas-size picker and the current size's index.

    The current size is always present (appended when it is not a preset) and is
    the default selection.
    """
    current = (int(width), int(height))
    sizes = list(_CANVAS_PRESETS)
    if current not in sizes:
        sizes.append(current)
    return ["%d×%d" % (w, h) for w, h in sizes], sizes.index(current)


class WhiteboardDialog(QtWidgets.QDialog):
    """A non-modal whiteboard window (one per conversation)."""

    share_requested = QtCore.pyqtSignal(str, bool)   # jid, is_muc
    share_png_requested = QtCore.pyqtSignal(str)     # temp PNG path

    def __init__(self, jid: str, parent=None, client=None, is_muc: bool = False,
                 config=None):
        super().__init__(parent)
        self._jid = jid
        self._client = client
        self._is_muc = is_muc
        self._config = config
        self._sid = ""
        self._editable = True
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
        for _key in ("Delete", "Backspace"):
            sc = QtGui.QShortcut(QtGui.QKeySequence(_key), self)
            sc.activated.connect(self._canvas.delete_selected)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Z"), self,
                        activated=self._on_undo)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Z"), self,
                        activated=self._on_redo)
        self._tool_group = QtWidgets.QButtonGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_buttons: dict[str, QtWidgets.QToolButton] = {}
        for tool, icon, tip_key in _TOOLS:
            if tool == "pencil":
                # «Удалить» / «Отмена» / «Вернуть» are object operations: they
                # close the manipulation group, then a separator starts the
                # drawing tools.
                self._delete_btn = self._tool_button(
                    "remove.svg", tr("whiteboard_tool_delete"))
                self._delete_btn.clicked.connect(self._canvas.delete_selected)
                toolbar.addWidget(self._delete_btn)
                self._undo_btn = self._tool_button("wb-undo.svg",
                                                   tr("whiteboard_undo"))
                self._undo_btn.clicked.connect(self._on_undo)
                toolbar.addWidget(self._undo_btn)
                self._redo_btn = self._tool_button("wb-redo.svg",
                                                   tr("whiteboard_redo"))
                self._redo_btn.clicked.connect(self._on_redo)
                toolbar.addWidget(self._redo_btn)
                self._order_btn = self._tool_button("wb-order.svg",
                                                    tr("whiteboard_order"))
                self._order_menu = QtWidgets.QMenu(self)
                for _op, _key in (("front", "whiteboard_order_front"),
                                  ("forward", "whiteboard_order_forward"),
                                  ("backward", "whiteboard_order_backward"),
                                  ("back", "whiteboard_order_back")):
                    _act = self._order_menu.addAction(tr(_key))
                    _act.triggered.connect(
                        lambda _checked=False, o=_op: self._reorder(o))
                self._order_btn.setPopupMode(
                    QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
                self._order_btn.setMenu(self._order_menu)
                toolbar.addWidget(self._order_btn)
                self._group_btn = self._tool_button("wb-group.svg",
                                                    tr("whiteboard_group"))
                self._group_btn.clicked.connect(self._group_selection)
                self._group_btn.setEnabled(False)
                toolbar.addWidget(self._group_btn)
                self._ungroup_btn = self._tool_button("wb-ungroup.svg",
                                                      tr("whiteboard_ungroup"))
                self._ungroup_btn.clicked.connect(self._ungroup_selection)
                self._ungroup_btn.setEnabled(False)
                toolbar.addWidget(self._ungroup_btn)
                toolbar.addWidget(self._separator())
            button = self._tool_button(icon, tr(tip_key), checkable=True)
            button.clicked.connect(
                lambda _checked=False, t=tool: self._canvas.set_tool(t))
            self._tool_group.addButton(button)
            self._tool_buttons[tool] = button
            toolbar.addWidget(button)
        self._tool_buttons["pencil"].setChecked(True)

        self._image_btn = self._tool_button("wb-image.svg",
                                            tr("whiteboard_insert_image"))
        self._image_btn.clicked.connect(self._insert_image)
        toolbar.addWidget(self._image_btn)

        toolbar.addWidget(self._separator())
        self._width_btn = self._tool_button("wb-line-width.svg",
                                            tr("whiteboard_line_width"))
        self._width_menu = QtWidgets.QMenu(self)
        self._width_group = QtGui.QActionGroup(self)
        self._width_group.setExclusive(True)
        self._width_actions: dict[int, QtGui.QAction] = {}
        for value in _WIDTHS:
            action = self._width_menu.addAction(f"{value} px")
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, w=value: self._set_width(w))
            self._width_group.addAction(action)
            self._width_actions[value] = action
        self._width_actions[self._width].setChecked(True)
        self._width_btn.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self._width_btn.setMenu(self._width_menu)
        toolbar.addWidget(self._width_btn)

        self._stroke_btn = self._tool_button("", tr("whiteboard_line_color"))
        self._stroke_btn.clicked.connect(self._pick_stroke)
        toolbar.addWidget(self._stroke_btn)

        self._fill_btn = self._tool_button("", tr("whiteboard_fill_color"))
        self._fill_btn.clicked.connect(self._pick_fill)
        toolbar.addWidget(self._fill_btn)

        self._fill_on_btn = self._tool_button("wb-fill-toggle.svg",
                                              tr("whiteboard_fill_toggle"),
                                              checkable=True)
        self._fill_on_btn.setChecked(False)
        self._fill_on_btn.toggled.connect(self._canvas.set_fill_enabled)
        toolbar.addWidget(self._fill_on_btn)

        toolbar.addWidget(self._separator())
        self._clear_btn = self._tool_button("clear.png",
                                            tr("whiteboard_clear"))
        self._clear_btn.clicked.connect(self._confirm_clear)
        toolbar.addWidget(self._clear_btn)
        save = self._tool_button("wb-save.svg", tr("whiteboard_save_svg"))
        save.clicked.connect(self._save_svg)
        toolbar.addWidget(save)
        save_png = self._tool_button("wb-save-png.svg",
                                     tr("whiteboard_save_png"))
        save_png.clicked.connect(self._save_png)
        toolbar.addWidget(save_png)
        self._share_png_btn = self._tool_button("send-arrow.svg",
                                                tr("whiteboard_share_png"))
        self._share_png_btn.clicked.connect(self._on_share_png)
        toolbar.addWidget(self._share_png_btn)

        self._size_btn = self._tool_button("wb-resize.svg",
                                           tr("whiteboard_canvas_size"))
        self._size_btn.clicked.connect(self._resize_canvas)
        toolbar.addWidget(self._size_btn)

        toolbar.addWidget(self._separator())
        self._share_btn = self._tool_button("system-users.png",
                                            tr("whiteboard_share"))
        self._share_btn.setCheckable(True)
        self._share_btn.clicked.connect(self._on_share)
        toolbar.addWidget(self._share_btn)
        self._finish_btn = self._tool_button("gtk-quit.png",
                                             tr("whiteboard_finish"))
        self._finish_btn.clicked.connect(self._confirm_finish)
        toolbar.addWidget(self._finish_btn)

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
        self._canvas.group_updated.connect(self._on_group_updated)
        self._canvas.selection_changed.connect(self._update_group_actions)
        self._canvas.changed.connect(self._update_undo_actions)
        self._canvas.selection_changed.connect(self._update_undo_actions)
        self._update_undo_actions()

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
        if self._client is not None:
            self.set_editable(self._client.whiteboard.may_edit(sid))
        # The shared session has its own (shared) undo/redo history.
        self._canvas.clear_history()
        self._update_undo_actions()
        self.refresh_from_session()

    def detach_session(self) -> None:
        self._sid = ""
        self._share_btn.setChecked(False)
        self._sync_label.setText(tr("whiteboard_not_shared"))
        self.set_editable(True)
        self._canvas.clear_history()
        self._update_undo_actions()

    def set_editable(self, editable: bool) -> None:
        """Reflect the session's Jingle ``senders``: may we edit the document?"""
        self._editable = bool(editable)
        self._canvas.set_editable(self._editable)
        for tool, button in self._tool_buttons.items():
            button.setEnabled(self._editable or tool == "select")
        for button in (self._delete_btn, self._undo_btn, self._redo_btn,
                       self._order_btn, self._group_btn, self._ungroup_btn,
                       self._image_btn, self._fill_on_btn, self._width_btn,
                       self._stroke_btn, self._fill_btn, self._size_btn,
                       self._clear_btn):
            button.setEnabled(self._editable)
        if not self._editable:
            self._tool_buttons["select"].setChecked(True)
        self._update_group_actions()
        self._update_undo_actions()

    def set_local_only(self) -> None:
        """Mark the board as local (a session with our own JID is pointless)."""
        self._share_btn.setChecked(False)
        self.set_editable(True)
        self._sync_label.setText(tr("whiteboard_local_only"))

    def show_warning(self, text: str) -> None:
        """Show a non-blocking notice without changing the session state."""
        self._sync_label.setText(text)

    def show_failed(self, reason: str) -> None:
        """Report a failed share and reset the dialog to the local board."""
        self._sid = ""
        self._share_btn.setChecked(False)
        self.set_editable(True)
        if reason == "unavailable":
            self._sync_label.setText(tr("whiteboard_failed_offline"))
        else:
            self._sync_label.setText(
                tr("whiteboard_failed_error", condition=reason))

    def refresh_from_session(self) -> None:
        if not (self._client and self._sid):
            return
        wb = self._client.whiteboard
        # The host's viewBox is authoritative, so adopt it before loading the
        # shapes (a peer may use a different canvas size than our default).
        width, height = wb.view_box(self._sid)
        self._canvas.set_view_box(width, height)
        self._canvas.load_shapes(wb.shapes(self._sid))

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
        action = self._width_actions.get(self._width)
        if action is not None:
            action.setChecked(True)

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

    def _insert_image(self) -> None:
        """Pick an image and place it on the board.

        In a shared session whose peer supports HTTP File Upload the image is
        uploaded and referenced by URL (the profile §12.2); otherwise it is
        embedded as a ``data:`` URI.
        """
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("whiteboard_insert_image"), "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)")
        if not path:
            return
        world = self._canvas.view_center_world()
        # ``embed`` forces the inline data: URI (compatible with the minimal
        # profile); ``auto`` uploads only when the peer advertises the feature.
        if self._image_upload_mode() == "embed" \
                or not self._peer_supports_upload():
            self._add_embedded_image(path, world)
            return
        self._client._start_task(self._upload_image_async(path, world))

    def _image_upload_mode(self) -> str:
        """``auto`` (upload when the peer supports it) or ``embed`` (always data:)."""
        chat = getattr(self._config, "chat", None)
        return str(getattr(chat, "whiteboard_image_upload", "auto") or "auto")

    def _peer_supports_upload(self) -> bool:
        """True when the peer advertises HTTP File Upload (the §12.5 rule)."""
        if not (self._client and self._sid):
            return False
        try:
            return bool(self._client.supports_feature(
                self._jid.split("/", 1)[0], "urn:xmpp:http:upload:0"))
        except Exception:  # noqa: BLE001
            return False

    def _add_embedded_image(self, path: str, world) -> bool:
        try:
            href = image_data_uri(path)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("whiteboard_insert_image"), str(exc))
            return False
        self._canvas.add_image(world, href)
        return True

    async def _upload_image_async(self, path: str, world) -> None:
        try:
            with open(path, "rb") as handle:
                raw = handle.read(IMAGE_MAX_BYTES + 1)
        except OSError:
            raw = b""
        try:
            media = await self._client.upload_http_media(path)
        except Exception:  # noqa: BLE001 - fall back to the embedded image
            media = None
        if media and media.get("url"):
            # Render our own copy from the bytes we just uploaded.
            self._canvas.cache_image(media["url"], raw)
            self._canvas.add_image(world, media["url"])
            return
        self._add_embedded_image(path, world)

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

    def _save_png(self) -> None:
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("whiteboard_save_png"), "whiteboard.png", "PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        if not self._canvas.save_png(path):
            QtWidgets.QMessageBox.warning(
                self, tr("whiteboard_save_png"), tr("whiteboard_save_failed"))

    def _on_share_png(self) -> None:
        """Render the board to a temp PNG and ask to share its link."""
        name = "whiteboard-%s.png" % time.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(tempfile.gettempdir(), name)
        if not self._canvas.save_png(path):
            QtWidgets.QMessageBox.warning(
                self, tr("whiteboard_share_png"),
                tr("whiteboard_share_png_failed"))
            return
        self.share_png_requested.emit(path)

    def _on_undo(self) -> None:
        if not self._editable:
            return
        if self._client and self._sid:
            self._client.whiteboard.undo(self._sid)
        else:
            self._canvas.undo_local()
        self._update_undo_actions()

    def _on_redo(self) -> None:
        if not self._editable:
            return
        if self._client and self._sid:
            self._client.whiteboard.redo(self._sid)
        else:
            self._canvas.redo_local()
        self._update_undo_actions()

    def _update_undo_actions(self) -> None:
        """Gate the undo/redo buttons on the available history."""
        manager = (getattr(self._client, "whiteboard", None)
                   if (self._client and self._sid) else None)
        if manager is not None and hasattr(manager, "can_undo"):
            can_undo = manager.can_undo(self._sid)
            can_redo = manager.can_redo(self._sid)
        else:
            can_undo = self._canvas.can_undo()
            can_redo = self._canvas.can_redo()
        self._undo_btn.setEnabled(self._editable and bool(can_undo))
        self._redo_btn.setEnabled(self._editable and bool(can_redo))

    def _reorder(self, op: str) -> None:
        """Change the selected shape's stacking order (front/back/±1)."""
        shape_id = self._canvas.selected_id()
        if not shape_id:
            return
        rid = self._canvas.selected_rid()
        if self._client and self._sid and rid:
            self._client.whiteboard.reorder(self._sid, rid, op)
        else:
            self._canvas.reorder_local(shape_id, op)

    def _update_group_actions(self) -> None:
        """Gate the group/ungroup buttons on the current selection."""
        self._group_btn.setEnabled(
            self._editable and len(self._canvas.selection()) >= 2)
        self._ungroup_btn.setEnabled(
            self._editable and bool(self._canvas.selected_group()))

    def _group_selection(self) -> None:
        """Group the selected shapes (Ctrl+click to select several)."""
        if len(self._canvas.selection()) < 2:
            return
        if self._client and self._sid:
            rids = [r for r in self._canvas.selected_rids() if r]
            if len(rids) >= 2:
                self._client.whiteboard.group_shapes(self._sid, rids)
                return
        # A local (unshared) board, or shapes without a document record.
        self._canvas.group_local()

    def _ungroup_selection(self) -> None:
        group = self._canvas.selected_group()
        if not group:
            return
        if self._client and self._sid:
            self._client.whiteboard.ungroup(self._sid, group)
        else:
            self._canvas.ungroup_local(group)

    def _on_group_updated(self, group_rid: str) -> None:
        if self._client and self._sid:
            self._client.whiteboard.set_group_transform(
                self._sid, group_rid,
                self._canvas.group_transform_str(group_rid))

    def _resize_canvas(self) -> None:
        """Resize the canvas (the shared document's ``viewBox``)."""
        width, height = self._canvas.view_box()
        labels, current = _canvas_size_items(width, height)
        choice, ok = QtWidgets.QInputDialog.getItem(
            self, tr("whiteboard_canvas_size"), tr("whiteboard_canvas_preset"),
            labels, current, False)
        if not ok:
            return
        try:
            new_w, new_h = (int(part) for part in
                            choice.replace(" ", "").split("×"))
        except (ValueError, TypeError):
            return
        self._canvas.set_view_box(new_w, new_h)
        if self._client and self._sid:
            self._client.whiteboard.set_view_box(self._sid, new_w, new_h)

    def _confirm_finish(self) -> None:
        answer = QtWidgets.QMessageBox.question(
            self, tr("whiteboard_finish"), tr("whiteboard_finish_confirm"))
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            self._end_board()

    def _end_board(self) -> None:
        """End the collaborative session, clear the board and hide the window."""
        if self._client and self._sid:
            self._client.whiteboard.end_session(self._sid)
        self.detach_session()
        self._canvas.clear()
        self._canvas.clear_history()
        self._canvas.reset_view()
        self.hide()

    def reject(self) -> None:  # noqa: D401
        """Esc must not close the board — it only clears the selection."""
        self._canvas.deselect()

    def closeEvent(self, event):  # noqa: N802
        # Hide instead of destroying so the board and its session survive and a
        # reopened window continues where the user left off.
        self.hide()
        event.ignore()

    @staticmethod
    def _separator() -> QtWidgets.QFrame:
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        return line
