"""Reaction-picker-style popup with a contact's OMEMO devices.

Opened from the chat shield button: a compact frameless popup anchored at the
cursor, listing each device with a coloured trust-shield button (its state) and
icon buttons to rename/copy, plus a header button to the full device manager.
"""
from __future__ import annotations

import asyncio
import logging
import time

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon
from stanza_im.include.utils import escape_html

logger = logging.getLogger("stanza_im.omemo")

#: Gap between the click point and the popup, so the button that opened it is
#: never covered.
_GAP = 6
#: Above this many device rows the popup scrolls instead of growing further.
_MAX_ROWS_NO_SCROLL = 10
#: Smallest popup height (keeps the header + a row or two visible).
_MIN_POPUP_H = 120
#: Slack added to the natural height so a short list never shows a scrollbar
#: (the layout size hint can under-report the scroll area's real need).
_FIT_PAD = 6

_TRUST_LABELS = {
    "TRUSTED": "omemo_trust_trusted",
    "BLINDLY_TRUSTED": "omemo_trust_blindly",
    "UNDECIDED": "omemo_trust_undecided",
    "DISTRUSTED": "omemo_trust_distrusted",
}
_TRUST_ICONS = {
    "TRUSTED": "shield-trusted.svg",
    "BLINDLY_TRUSTED": "shield-blindly.svg",
    "UNDECIDED": "shield-unknown.svg",
    "DISTRUSTED": "shield-distrusted.svg",
}


def _trust_label(name: str) -> str:
    return tr(_TRUST_LABELS.get(name, "omemo_trust_undecided"))


def _trust_icon(name: str) -> str:
    return _TRUST_ICONS.get(name, "shield-unknown.svg")


def _is_trusted(name: str) -> bool:
    return name in ("TRUSTED", "BLINDLY_TRUSTED")


def _icon_button(name: str, tooltip: str, size: int = 24,
                 button: int = 34) -> QtWidgets.QToolButton:
    widget = QtWidgets.QToolButton()
    icon = QtGui.QIcon(find_icon(name))
    if not icon.isNull():
        widget.setIcon(icon)
    widget.setIconSize(QtCore.QSize(size, size))
    widget.setFixedSize(button, button)
    widget.setAutoRaise(True)
    widget.setToolTip(tooltip)
    return widget


class OmemoPopup(QtWidgets.QFrame):
    """Frameless popup listing a contact's OMEMO devices."""

    def __init__(self, client, jid: str, parent=None, anchor=None):
        super().__init__(parent, QtCore.Qt.WindowType.Popup)
        self._client = client
        self._jid = str(jid).split("/")[0]
        self._devices: list = []
        #: Row widgets currently in the list (for size measurement).
        self._rows: list = []
        #: Screen point the click happened at; the popup's bottom-left corner.
        self._anchor = anchor
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setMinimumWidth(320)
        self._build_ui()
        self._reload()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._reposition()

    def _reposition(self) -> None:
        """Size and place the popup near the click point.

        The popup grows upward (into the chat view) by default and only scrolls
        once the list is long (> ``_MAX_ROWS_NO_SCROLL``) or neither side has
        room.  A small gap keeps the button that opened it uncovered.
        """
        if self._anchor is None:
            return
        anchor = self._anchor
        if isinstance(anchor, QtCore.QPoint):
            x, y = anchor.x(), anchor.y()
        else:
            x, y = anchor
        x, y = int(x), int(y)
        point = QtCore.QPoint(x, y)
        screen = (QtWidgets.QApplication.screenAt(point)
                  or QtWidgets.QApplication.primaryScreen())
        area = screen.availableGeometry() if screen else None
        if area is None or not area.isValid():
            self.adjustSize()
            self.move(x, y - self.height())
            return

        # Width and natural height are summed from the row widgets: the scroll
        # area's / container's size hint is 0 until the event loop runs, so it
        # cannot be measured synchronously right after the list is filled.
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()
        if spacing < 0:
            spacing = 6
        rows = len(self._rows)
        if rows:
            row_gap = self._body.spacing()
            content_h = sum(r.sizeHint().height() for r in self._rows)
            content_h += max(0, rows - 1) * row_gap
            content_w = max(r.sizeHint().width() for r in self._rows)
        else:
            content_h = 0
            content_w = 0
        chrome = (margins.top() + margins.bottom()
                  + self._header.sizeHint().height() + spacing)
        natural = chrome + content_h
        row_h = (content_h / rows) if rows else 44
        desired = min(natural + _FIT_PAD,
                      chrome + int(row_h * _MAX_ROWS_NO_SCROLL) + _FIT_PAD)
        width = max(self.minimumWidth(), content_w,
                    self._header.sizeHint().width())
        width += margins.left() + margins.right()
        width = min(width, max(1, area.width() - 2 * _GAP))

        space_above = y - area.top() - _GAP
        space_below = area.bottom() - y - _GAP
        # The layout enforces a minimum height, so position by the *actual*
        # size after resizing rather than the requested one.
        self.resize(int(width), int(desired))
        height = self.height()
        if height <= space_above:
            top = y - _GAP - height
        elif height <= space_below:
            top = y + _GAP
        elif space_above >= space_below:
            self.resize(int(width), int(max(_MIN_POPUP_H, space_above)))
            height = self.height()
            top = area.top() + _GAP
        else:
            self.resize(int(width), int(max(_MIN_POPUP_H, space_below)))
            height = self.height()
            top = y + _GAP
        height = min(height, area.height() - 2 * _GAP)
        self.resize(int(width), int(height))
        left = max(area.left() + _GAP,
                   min(x, area.right() - width - _GAP))
        self.move(int(left), int(top))

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self._header = QtWidgets.QWidget()
        header = QtWidgets.QHBoxLayout(self._header)
        header.setContentsMargins(0, 0, 0, 0)
        title = QtWidgets.QLabel(tr("omemo_devices_title", jid=self._jid))
        title.setStyleSheet("font-weight: bold;")
        header.addWidget(title)
        header.addStretch(1)
        manage = _icon_button("gtk-preferences.png", tr("omemo_manage"), 16, 24)
        manage.clicked.connect(self._open_manager)
        header.addWidget(manage)
        layout.addWidget(self._header)

        # The device rows live in a scroll area so a long list scrolls instead
        # of making the popup taller than the screen.
        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        container = QtWidgets.QWidget()
        self._body = QtWidgets.QVBoxLayout(container)
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(2)
        self._scroll.setWidget(container)
        layout.addWidget(self._scroll, 1)

    # ── data ────────────────────────────────────────────────────

    def _reload(self) -> None:
        try:
            asyncio.ensure_future(self._reload_async())
        except RuntimeError:
            pass

    async def _reload_async(self) -> None:
        omemo = self._client.omemo
        try:
            await omemo.refresh_device_lists([self._jid], force=True)
            devices = await omemo.devices(self._jid)
            sorter = getattr(omemo, "sorted_devices", None)
            self._devices = (sorter(self._jid, devices) if sorter
                             else list(devices))
        except Exception:  # noqa: BLE001
            logger.debug("OMEMO popup device load failed", exc_info=True)
            self._devices = []
        self._rebuild()

    def _rebuild(self) -> None:
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = []
        if not self._devices:
            self._body.addWidget(QtWidgets.QLabel(tr("omemo_devices_count",
                                                     count=0)))
        else:
            omemo = self._client.omemo
            for device in self._devices:
                row = self._device_row(omemo, device)
                self._rows.append(row)
                self._body.addWidget(row)
        self._reposition()

    def _device_row(self, omemo, device) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget(self)
        box = QtWidgets.QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(2)
        name = omemo.device_name(self._jid, int(device.device_id),
                                 str(getattr(device, "label", "") or ""))
        level = omemo.trust_level_name(device)
        trusted = _is_trusted(level)
        try:
            seen = omemo.device_last_seen(self._jid, int(device.device_id))
        except Exception:  # noqa: BLE001
            seen = 0.0
        seen_txt = (time.strftime("%Y-%m-%d %H:%M", time.localtime(seen))
                    if seen else "\u2014")
        label = QtWidgets.QLabel(
            f"<b>{escape_html(name)}</b><br>{escape_html(_trust_label(level))}"
            f"<br>{escape_html(tr('omemo_last_seen'))}: {escape_html(seen_txt)}")
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        tooltip = omemo.fingerprint(device.identity_key)
        try:
            resource = omemo.device_resource(self._jid, int(device.device_id))
        except Exception:  # noqa: BLE001
            resource = ""
        if resource:
            tooltip += "\n" + tr("omemo_device_resource", resource=resource)
        label.setToolTip(tooltip)
        box.addWidget(label, 1)

        # Coloured trust shield: the icon is the *state*; a click toggles it.
        trust_btn = _icon_button(
            _trust_icon(level),
            tr("omemo_trust_distrust") if trusted else tr("omemo_trust_verify"))
        trust_btn.clicked.connect(
            lambda: self._set_trust(
                device, "DISTRUSTED" if trusted else "TRUSTED"))
        box.addWidget(trust_btn)

        rename_btn = _icon_button("edit.png", tr("omemo_rename"), 16, 24)
        rename_btn.clicked.connect(lambda: self._rename(device))
        box.addWidget(rename_btn)
        copy_btn = _icon_button("copy.svg", tr("omemo_copy_fingerprint"), 16, 24)
        copy_btn.clicked.connect(lambda: self._copy(device))
        box.addWidget(copy_btn)
        return row

    # ── actions ─────────────────────────────────────────────────

    def _set_trust(self, device, level: str) -> None:
        asyncio.ensure_future(self._set_trust_async(device, level))

    async def _set_trust_async(self, device, level: str) -> None:
        try:
            await self._client.omemo.set_trust(
                device.bare_jid, device.identity_key, level)
        except Exception:  # noqa: BLE001
            logger.debug("OMEMO popup set_trust failed", exc_info=True)
        await self._reload_async()

    def _copy(self, device) -> None:
        QtWidgets.QApplication.clipboard().setText(
            self._client.omemo.fingerprint(device.identity_key))

    def _rename(self, device) -> None:
        omemo = self._client.omemo
        current = omemo.device_name(self._jid, int(device.device_id),
                                    str(getattr(device, "label", "") or ""))
        name, ok = QtWidgets.QInputDialog.getText(
            self, tr("omemo_rename"), tr("omemo_device_name"), text=current)
        if ok:
            omemo.set_device_alias(self._jid, int(device.device_id),
                                   name.strip())
            self._rebuild()

    def _open_manager(self) -> None:
        self.close()
        from stanza_im.ui.omemo_devices_dialog import OmemoDevicesDialog
        own_bare = (getattr(self._client, "jid_str", "") or "").split("/", 1)[0]
        OmemoDevicesDialog(self._client, self._jid, self.parent(),
                           own=(self._jid == own_bare)).exec()
