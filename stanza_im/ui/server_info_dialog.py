"""Non-modal "Server info" dialog.

Shows the account domain's server software, the XEP-0157 contact addresses and
a preset list of XEPs marked as supported or not, based on the domain's
``disco#info`` features and the advertised stream features.
"""
from __future__ import annotations

import asyncio
import html

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.core.server_features import (
    collect_server_features, evaluate_server_xeps)
from stanza_im.i18n import tr

_GREEN = "#1b8a2f"
_RED = "#c0392b"

_CONTACT_LABELS = {
    "abuse-addresses": "server_contact_abuse",
    "admin-addresses": "server_contact_admin",
    "feedback-addresses": "server_contact_feedback",
    "sales-addresses": "server_contact_sales",
    "security-addresses": "server_contact_security",
    "status-addresses": "server_contact_status",
    "support-addresses": "server_contact_support",
}


class ServerInfoDialog(QtWidgets.QDialog):
    """Request the server capabilities and render them as a table."""

    contact_uri_clicked = QtCore.pyqtSignal(str)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        self._header_text = tr("server_info_loading")
        self.setWindowTitle(tr("server_info_title"))
        self.setMinimumSize(560, 480)
        layout = QtWidgets.QVBoxLayout(self)

        self._header = QtWidgets.QLabel(self._header_text)
        self._header.setWordWrap(True)
        layout.addWidget(self._header)

        self._contacts: list[tuple[str, list[str]]] = []
        self._contacts_box = QtWidgets.QGroupBox(tr("server_contacts_title"),
                                                 self)
        self._contacts_form = QtWidgets.QFormLayout(self._contacts_box)
        self._contacts_form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._contacts_box.setVisible(False)
        layout.addWidget(self._contacts_box)

        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels([tr("server_info_col_xep"),
                                    tr("server_info_col_name"),
                                    tr("server_info_col_status")])
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self._tree, stretch=1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._copy = QtWidgets.QPushButton(tr("cert_copy"), self)
        self._copy.clicked.connect(self._on_copy)
        buttons.addWidget(self._copy)
        close = QtWidgets.QPushButton(tr("dialog_close"), self)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        asyncio.create_task(self._load())

    async def _load(self) -> None:
        try:
            context = await collect_server_features(self._client)
        except Exception:
            self._header.setText(tr("server_info_error"))
            return
        self._render(context)

    def _render(self, context: dict) -> None:
        head: list[str] = []
        domain = str(context.get("domain") or "")
        software = str(context.get("software") or "")
        login = str(context.get("login") or "")
        if domain:
            head.append("%s: %s" % (tr("server_info_server"), domain))
        if software:
            head.append("%s: %s" % (tr("server_info_software"), software))
        if login:
            head.append("%s: %s" % (tr("server_info_login"), login))
        self._header_text = "\n".join(head)
        self._header.setText(self._header_text)

        self._render_contacts(context.get("contacts") or [])

        self._tree.clear()
        for row in evaluate_server_xeps(context):
            name = row["name"]
            if row["detail"]:
                name = "%s (%s)" % (name, row["detail"])
            item = QtWidgets.QTreeWidgetItem([row["xep"], name, ""])
            if row["supported"]:
                item.setText(2, tr("server_info_supported"))
                color = _GREEN
            else:
                item.setText(2, tr("server_info_unsupported"))
                color = _RED
            item.setForeground(2, QtGui.QBrush(QtGui.QColor(color)))
            self._tree.addTopLevelItem(item)
        self._tree.resizeColumnToContents(0)
        self._tree.resizeColumnToContents(1)
        self._tree.resizeColumnToContents(2)

    def _render_contacts(self, contacts: list) -> None:
        self._contacts = list(contacts)
        while self._contacts_form.rowCount():
            self._contacts_form.removeRow(0)
        self._contacts_box.setVisible(bool(contacts))
        for var, values in contacts:
            container = QtWidgets.QWidget(self._contacts_box)
            column = QtWidgets.QVBoxLayout(container)
            column.setContentsMargins(0, 0, 0, 0)
            for uri in values:
                column.addWidget(self._contact_label(uri))
            self._contacts_form.addRow(
                tr(_CONTACT_LABELS.get(var, var)), container)

    def _contact_label(self, uri: str) -> QtWidgets.QLabel:
        safe = html.escape(uri)
        label = QtWidgets.QLabel(f'<a href="{safe}">{safe}</a>',
                                 self._contacts_box)
        label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setWordWrap(True)
        if uri.lower().startswith("xmpp:"):
            label.linkActivated.connect(self.contact_uri_clicked.emit)
        else:
            label.setOpenExternalLinks(True)
        return label

    def _on_copy(self) -> None:
        lines = [self._header_text, ""] if self._header_text else []
        if self._contacts:
            lines.append(tr("server_contacts_title") + ":")
            for var, values in self._contacts:
                lines.append("  %s: %s"
                             % (tr(_CONTACT_LABELS.get(var, var)),
                                ", ".join(values)))
            lines.append("")
        for index in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(index)
            lines.append("%s: %s — %s" % (item.text(0), item.text(1),
                                          item.text(2)))
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))
