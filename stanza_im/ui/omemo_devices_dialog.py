"""OMEMO device manager (XEP-0384).

Lists the devices known for an account (our own or a contact's) and lets the
user change trust, rename a device, copy its fingerprint and — for our own
account — delete a device.  Every per-device action is an icon button right in
the device row; the bottom row only carries global actions.  All operations go
through ``client.omemo``.
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

_TRUST_LABELS = {
    "TRUSTED": "omemo_trust_trusted",
    "BLINDLY_TRUSTED": "omemo_trust_blindly",
    "UNDECIDED": "omemo_trust_undecided",
    "DISTRUSTED": "omemo_trust_distrusted",
}

#: Trust state -> coloured shield icon (state, not the action).
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


def _icon_button(name: str, tooltip: str) -> QtWidgets.QToolButton:
    button = QtWidgets.QToolButton()
    icon = QtGui.QIcon(find_icon(name))
    if not icon.isNull():
        button.setIcon(icon)
    button.setIconSize(QtCore.QSize(30, 30))
    button.setFixedSize(38, 38)
    button.setAutoRaise(True)
    button.setToolTip(tooltip)
    return button


class OmemoDevicesDialog(QtWidgets.QDialog):
    """Device & trust management for one account."""

    def __init__(self, client, jid: str, parent=None, own: bool = False):
        super().__init__(parent)
        self._client = client
        self._jid = str(jid).split("/")[0]
        self._own = bool(own)
        self._devices: list = []
        self.setWindowTitle(tr("omemo_devices_title", jid=self._jid))
        self.resize(760, 520)
        self._build_ui()
        self._reload()

    # ── UI ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self._status = QtWidgets.QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._list = QtWidgets.QListWidget()
        layout.addWidget(self._list, 1)

        bottom = QtWidgets.QHBoxLayout()
        refresh = QtWidgets.QPushButton(tr("omemo_refresh"))
        refresh.clicked.connect(self._reload)
        bottom.addWidget(refresh)
        bottom.addStretch(1)
        close = QtWidgets.QPushButton(tr("dialog_close"))
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        layout.addLayout(bottom)

    # ── data ────────────────────────────────────────────────────

    def _reload(self) -> None:
        omemo = getattr(self._client, "omemo", None)
        if omemo is None or not getattr(omemo, "available", False):
            self._status.setText(tr("omemo_unavailable"))
            return
        self._status.setText(tr("omemo_loading"))
        try:
            asyncio.ensure_future(self._reload_async())
        except RuntimeError:
            # No running loop (tests): leave the list empty.
            self._status.setText("")

    async def _reload_async(self) -> None:
        omemo = self._client.omemo
        try:
            await omemo.refresh_device_lists([self._jid], force=True)
            devices = await omemo.devices(self._jid)
        except Exception as exc:  # noqa: BLE001
            logger.debug("OMEMO device load failed", exc_info=True)
            self._status.setText(tr("omemo_load_failed", error=str(exc)))
            return
        sorter = getattr(omemo, "sorted_devices", None)
        self._devices = sorter(self._jid, devices) if sorter else list(devices)
        self._status.setText(tr("omemo_devices_count", count=len(self._devices)))
        self._rebuild()

    def _rebuild(self) -> None:
        self._list.clear()
        omemo = self._client.omemo
        for device in self._devices:
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, device)
            self._list.addItem(item)
            row = self._device_row(omemo, device)
            self._list.setItemWidget(item, row)
            item.setSizeHint(row.sizeHint())

    def _device_row(self, omemo, device) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget(self)
        box = QtWidgets.QHBoxLayout(row)
        box.setContentsMargins(2, 2, 2, 2)
        box.setSpacing(2)

        name = omemo.device_name(self._jid, int(device.device_id),
                                 str(getattr(device, "label", "") or ""))
        level = omemo.trust_level_name(device)
        trusted = _is_trusted(level)
        seen = omemo.device_last_seen(self._jid, int(device.device_id))
        seen_txt = (time.strftime("%Y-%m-%d %H:%M", time.localtime(seen))
                    if seen else "—")
        label = QtWidgets.QLabel(
            f"<b>{escape_html(name)}</b>  —  {escape_html(_trust_label(level))}"
            f"<br>{device.device_id}  ·  "
            f"{escape_html(omemo.fingerprint(device.identity_key))}"
            f"<br>{escape_html(tr('omemo_last_seen'))}: {escape_html(seen_txt)}")
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        tooltip = omemo.fingerprint(device.identity_key)
        try:
            resource = omemo.device_resource(self._jid, int(device.device_id))
        except Exception:  # noqa: BLE001
            resource = ""
        if resource:
            tooltip += "\n" + tr("omemo_device_resource", resource=resource)
        tooltip += "\n" + tr("omemo_last_seen_tip")
        label.setToolTip(tooltip)
        box.addWidget(label, 1)

        # The trust button shows the *state* (coloured shield); a click toggles
        # between trusted and distrusted.
        trust_btn = _icon_button(_trust_icon(level),
                                 tr("omemo_trust_distrust") if trusted
                                 else tr("omemo_trust_verify"))
        trust_btn.clicked.connect(
            lambda: self._set_trust(
                device, "DISTRUSTED" if trusted else "TRUSTED"))
        box.addWidget(trust_btn)

        rename_btn = _icon_button("edit.png", tr("omemo_rename"))
        rename_btn.clicked.connect(lambda: self._rename(device))
        box.addWidget(rename_btn)

        copy_btn = _icon_button("copy.svg", tr("omemo_copy_fingerprint"))
        copy_btn.clicked.connect(lambda: self._copy(device))
        box.addWidget(copy_btn)

        if self._own:
            delete_btn = _icon_button("process-stop.png",
                                      tr("omemo_delete_device"))
            delete_btn.clicked.connect(lambda: self._delete(device))
            box.addWidget(delete_btn)
        return row

    # ── actions ─────────────────────────────────────────────────

    def _set_trust(self, device, level: str) -> None:
        asyncio.ensure_future(self._set_trust_async(device, level))

    async def _set_trust_async(self, device, level: str) -> None:
        try:
            await self._client.omemo.set_trust(
                device.bare_jid, device.identity_key, level)
        except Exception as exc:  # noqa: BLE001
            self._status.setText(tr("omemo_trust_failed", error=str(exc)))
            return
        await self._reload_async()

    def _copy(self, device) -> None:
        fp = self._client.omemo.fingerprint(device.identity_key)
        QtWidgets.QApplication.clipboard().setText(fp)
        self._status.setText(tr("omemo_fingerprint_copied"))

    def _rename(self, device) -> None:
        omemo = self._client.omemo
        current = omemo.device_name(self._jid, int(device.device_id),
                                    str(getattr(device, "label", "") or ""))
        name, ok = QtWidgets.QInputDialog.getText(
            self, tr("omemo_rename"), tr("omemo_device_name"), text=current)
        if not ok:
            return
        omemo.set_device_alias(self._jid, int(device.device_id), name.strip())
        self._rebuild()

    def _delete(self, device) -> None:
        reply = QtWidgets.QMessageBox.question(
            self, tr("omemo_delete_device"),
            tr("omemo_delete_confirm", device=device.device_id),
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        asyncio.ensure_future(self._delete_async(device))

    async def _delete_async(self, device) -> None:
        try:
            await self._client.omemo.purge_device(device)
        except Exception as exc:  # noqa: BLE001
            self._status.setText(tr("omemo_delete_failed", error=str(exc)))
            return
        await self._reload_async()
