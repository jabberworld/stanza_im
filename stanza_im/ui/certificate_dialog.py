"""Read-only dialog listing the server's TLS certificate details.

The lines are shared with the connection-info tooltip so the certificate is
described identically everywhere.
"""
from __future__ import annotations

from PyQt6 import QtWidgets

from stanza_im.i18n import tr


def _distinguished(name_cn: str, name_o: str) -> str:
    if name_cn and name_o:
        return "%s (%s)" % (name_cn, name_o)
    return name_cn or name_o or ""


def certificate_lines(cert: dict) -> list[str]:
    """Human-readable certificate fields for the dialog and tooltips."""
    if not cert or not cert.get("available"):
        return [tr("conn_info_cert_none")]
    lines = []
    subject = _distinguished(cert.get("subject_cn", ""),
                             cert.get("subject_o", ""))
    if subject:
        lines.append("%s: %s" % (tr("cert_subject"), subject))
    issuer = _distinguished(cert.get("issuer_cn", ""),
                            cert.get("issuer_o", ""))
    if issuer:
        lines.append("%s: %s" % (tr("cert_issuer"), issuer))
    if cert.get("not_before"):
        lines.append("%s: %s" % (tr("cert_valid_from"), cert["not_before"]))
    if cert.get("not_after"):
        if cert.get("expired"):
            status = tr("cert_status_expired")
        elif cert.get("days_left") is not None:
            status = tr("cert_status_ok", days=cert["days_left"])
        else:
            status = ""
        value = cert["not_after"]
        if status:
            value = "%s (%s)" % (value, status)
        lines.append("%s: %s" % (tr("cert_valid_to"), value))
    if cert.get("serial"):
        lines.append("%s: %s" % (tr("cert_serial"), cert["serial"]))
    if cert.get("sans"):
        lines.append("%s: %s" % (tr("cert_san"), ", ".join(cert["sans"])))
    if cert.get("fingerprint"):
        lines.append("%s: %s" % (tr("cert_fingerprint"),
                                 cert["fingerprint"]))
    if not cert.get("verified"):
        lines.append(tr("cert_not_verified"))
    return lines


class CertificateDialog(QtWidgets.QDialog):
    """Non-modal, selectable view of the peer certificate."""

    def __init__(self, host: str, cert: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("cert_dialog_title", host=host or ""))
        self.setMinimumSize(480, 340)
        layout = QtWidgets.QVBoxLayout(self)

        self._text = QtWidgets.QPlainTextEdit(self)
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(
            QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.setPlainText("\n".join(certificate_lines(cert)))
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
