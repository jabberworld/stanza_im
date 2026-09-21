"""Read-only dialog with the live connection details.

The same lines are used for the connection-info tooltip in Preferences →
Connection → Advanced, so both places describe the connection identically.
"""
from __future__ import annotations

from PyQt6 import QtWidgets

from stanza_im.i18n import tr


def connection_info_lines(info: dict | None) -> list[str]:
    """Human-readable connection fields for the dialog and the tooltip."""
    if not info or not info.get("sasl"):
        return [tr("conn_info_not_connected")]
    mode_key = {"direct": "conn_info_direct",
                "starttls": "conn_info_starttls",
                "plain": "conn_info_plain"}.get(info.get("mode"),
                                                "conn_info_plain")
    lines = [tr("conn_info_title") + ":"]
    lines.append("  %s: %s" % (tr("conn_info_mode"), tr(mode_key)))
    if info.get("tls_version"):
        lines.append("  %s: %s" % (tr("conn_info_tls_version"),
                                   info["tls_version"]))
    if info.get("cipher"):
        lines.append("  %s: %s" % (tr("conn_info_cipher"), info["cipher"]))
    lines.append("  %s: %s" % (tr("conn_info_sasl"), info.get("sasl", "")))
    lines.append("  %s: %s" % (
        tr("conn_info_keepalive"),
        tr("conn_info_on") if info.get("keepalive") else tr("conn_info_off")))
    if info.get("sm"):
        lines.append("  %s: %s" % (tr("conn_info_sm"),
                                   tr("sm_state_" + info["sm"])))
    if info.get("csi"):
        lines.append("  %s: %s" % (tr("conn_info_csi"),
                                   tr("csi_state_" + info["csi"])))
    if info.get("host"):
        lines.append("  %s: %s:%s" % (tr("conn_info_server"),
                                      info["host"], info.get("port", "")))
    return lines


class ConnectionInfoDialog(QtWidgets.QDialog):
    """Non-modal, selectable view of the current connection."""

    def __init__(self, info: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("conn_info_dialog_title"))
        self.setMinimumSize(440, 300)
        layout = QtWidgets.QVBoxLayout(self)

        self._text = QtWidgets.QPlainTextEdit(
            "\n".join(connection_info_lines(info)), self)
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(
            QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._text, stretch=1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._copy = QtWidgets.QPushButton(tr("cert_copy"), self)
        self._copy.clicked.connect(self._on_copy)
        buttons.addWidget(self._copy)
        close = QtWidgets.QPushButton(tr("dialog_close"), self)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _on_copy(self) -> None:
        QtWidgets.QApplication.clipboard().setText(self._text.toPlainText())
