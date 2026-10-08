"""Reaction-picker-style popup with a contact's OMEMO devices.

Opened from the chat shield button: a compact frameless popup anchored at the
cursor, listing each device with quick trust and rename controls, plus a button
to the full device manager.
"""
from __future__ import annotations

import asyncio
import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr

logger = logging.getLogger("stanza_im.omemo")

_TRUST_LABELS = {
    "TRUSTED": "omemo_trust_trusted",
    "BLINDLY_TRUSTED": "omemo_trust_blindly",
    "UNDECIDED": "omemo_trust_undecided",
    "DISTRUSTED": "omemo_trust_distrusted",
}


def _trust_label(name: str) -> str:
    return tr(_TRUST_LABELS.get(name, "omemo_trust_undecided"))


class OmemoPopup(QtWidgets.QFrame):
    """Frameless popup listing a contact's OMEMO devices."""

    def __init__(self, client, jid: str, parent=None):
        super().__init__(parent, QtCore.Qt.WindowType.Popup)
        self._client = client
        self._jid = str(jid).split("/")[0]
        self._devices: list = []
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setMinimumWidth(320)
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QtWidgets.QLabel(tr("omemo_devices_title", jid=self._jid))
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)
        self._body = QtWidgets.QVBoxLayout()
        layout.addLayout(self._body)
        manage = QtWidgets.QPushButton(tr("prefs_omemo_manage"))
        manage.clicked.connect(self._open_manager)
        layout.addWidget(manage)

    # ── data ────────────────────────────────────────────────────

    def _reload(self) -> None:
        try:
            asyncio.ensure_future(self._reload_async())
        except RuntimeError:
            pass

    async def _reload_async(self) -> None:
        omemo = self._client.omemo
        try:
            await omemo.refresh_device_lists([self._jid])
            self._devices = sorted(await omemo.devices(self._jid),
                                   key=lambda d: int(d.device_id))
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
        if not self._devices:
            self._body.addWidget(QtWidgets.QLabel(tr("omemo_devices_count",
                                                     count=0)))
            return
        omemo = self._client.omemo
        for device in self._devices:
            self._body.addWidget(self._device_row(omemo, device))

    def _device_row(self, omemo, device) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget(self)
        box = QtWidgets.QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        name = omemo.device_name(self._jid, int(device.device_id),
                                 str(getattr(device, "label", "") or ""))
        label = QtWidgets.QLabel(
            f"{name}\n{device.device_id} · "
            f"{_trust_label(omemo.trust_level_name(device))}")
        box.addWidget(label, 1)
        trusted = omemo.is_trusted(device)
        trust_btn = QtWidgets.QToolButton()
        trust_btn.setText("✗" if trusted else "✓")
        trust_btn.setToolTip(tr("omemo_trust_distrust" if trusted
                                else "omemo_trust_verify"))
        trust_btn.clicked.connect(
            lambda: self._set_trust(device, not trusted))
        box.addWidget(trust_btn)
        rename_btn = QtWidgets.QToolButton()
        rename_btn.setText("✎")
        rename_btn.setToolTip(tr("omemo_rename"))
        rename_btn.clicked.connect(lambda: self._rename(device))
        box.addWidget(rename_btn)
        return row

    # ── actions ─────────────────────────────────────────────────

    def _set_trust(self, device, trust: bool) -> None:
        level = "TRUSTED" if trust else "DISTRUSTED"
        asyncio.ensure_future(self._set_trust_async(device, level))

    async def _set_trust_async(self, device, level: str) -> None:
        try:
            await self._client.omemo.set_trust(
                device.bare_jid, device.identity_key, level)
        except Exception:  # noqa: BLE001
            logger.debug("OMEMO popup set_trust failed", exc_info=True)
        await self._reload_async()

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
        OmemoDevicesDialog(self._client, self._jid, self.parent()).exec()
