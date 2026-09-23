"""Non-modal "Service info" dialog for the service browser.

Three tabs: the server's version / statistics / uptime (XEP-0092/0039/0012),
the announced capabilities mapped to XEPs, and the XEP-0157 contact addresses.
"""
from __future__ import annotations

import asyncio
import html

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.core.server_features import (
    describe_features, service_details)
from stanza_im.i18n import tr

_CONTACT_LABELS = {
    "abuse-addresses": "server_contact_abuse",
    "admin-addresses": "server_contact_admin",
    "feedback-addresses": "server_contact_feedback",
    "sales-addresses": "server_contact_sales",
    "security-addresses": "server_contact_security",
    "status-addresses": "server_contact_status",
    "support-addresses": "server_contact_support",
}


def _human_seconds(seconds: int) -> str:
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


class ServiceInfoDialog(QtWidgets.QDialog):
    """Show a service's information, capabilities and contacts."""

    contact_uri_clicked = QtCore.pyqtSignal(str)

    def __init__(self, client, jid: str, node: str = "", parent=None):
        super().__init__(parent)
        self._client = client
        self._jid = jid
        self._node = node
        self._features: list[str] = []
        self._contacts: list[tuple[str, list[str]]] = []
        self._identity: dict = {"name": "", "category": "", "type": ""}
        self._info_text = tr("service_info_loading")
        self._caps_text = ""
        self._contacts_text = ""
        self.setWindowTitle(tr("service_info_title", jid=jid))
        self.setMinimumSize(560, 460)
        layout = QtWidgets.QVBoxLayout(self)

        self._tabs = QtWidgets.QTabWidget(self)
        self._info_edit = self._text_tab()
        self._caps_edit = self._text_tab()
        self._tabs.addTab(self._info_edit, tr("service_info_tab_info"))
        self._tabs.addTab(self._caps_edit, tr("service_info_tab_caps"))
        self._tabs.addTab(self._contacts_tab(), tr("service_info_tab_contacts"))
        layout.addWidget(self._tabs, 1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._copy = QtWidgets.QPushButton(tr("cert_copy"), self)
        self._copy.clicked.connect(self._on_copy)
        buttons.addWidget(self._copy)
        close = QtWidgets.QPushButton(tr("dialog_close"), self)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._info_edit.setPlainText(self._info_text)
        asyncio.create_task(self._load())

    # ── UI helpers ──────────────────────────────────────────────

    def _text_tab(self) -> QtWidgets.QPlainTextEdit:
        edit = QtWidgets.QPlainTextEdit(self)
        edit.setReadOnly(True)
        edit.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        return edit

    def _contacts_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(page)
        self._contacts_empty = QtWidgets.QLabel(
            tr("service_info_contacts_empty"), page)
        self._contacts_empty.setWordWrap(True)
        layout.addWidget(self._contacts_empty)
        inner = QtWidgets.QWidget(page)
        self._contacts_form = QtWidgets.QFormLayout(inner)
        self._contacts_form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        scroll = QtWidgets.QScrollArea(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        self._contacts_scroll = scroll
        return page

    # ── Loading ─────────────────────────────────────────────────

    async def _load(self) -> None:
        details = await service_details(self._client, self._jid, self._node)
        self._features = details["features"]
        self._contacts = details["contacts"]
        self._identity = details.get("identity") or self._identity

        self._caps_text = ("\n".join(describe_features(self._features))
                           or tr("service_info_caps_empty"))
        self._caps_edit.setPlainText(self._caps_text)

        self._render_contacts()
        self._info_text = await self._build_info()
        self._info_edit.setPlainText(self._info_text)

    async def _build_info(self) -> str:
        features = set(self._features)
        lines: list[str] = []

        lines.append(tr("service_info_entity") + ":")
        category = str(self._identity.get("category") or "")
        type_ = str(self._identity.get("type") or "")
        if category or type_:
            lines.append("  " + " / ".join(p for p in (category, type_) if p))
        else:
            lines.append("  " + tr("service_info_unavailable"))

        lines.append("")
        lines.append(tr("service_info_version") + ":")
        if "jabber:iq:version" in features:
            info = await self._client.get_entity_version(self._jid)
            if info.get("software"):
                lines.append("  " + tr("version_software",
                                       value=info["software"]))
            if info.get("version"):
                lines.append("  " + tr("version_number",
                                       value=info["version"]))
            if info.get("os"):
                lines.append("  " + tr("version_os", value=info["os"]))
            if not any(info.values()):
                lines.append("  " + tr("service_info_unavailable"))
        else:
            lines.append("  " + tr("service_info_unsupported"))

        lines.append("")
        lines.append(tr("service_info_stats") + ":")
        if "http://jabber.org/protocol/stats" in features:
            stats = await self._client.get_server_stats(self._jid)
            if stats:
                for stat in stats:
                    value = stat["value"]
                    if stat["units"]:
                        value = f"{value} {stat['units']}".strip()
                    lines.append(f"  {stat['name']} = {value}")
            else:
                lines.append("  " + tr("service_info_unavailable"))
        else:
            lines.append("  " + tr("service_info_unsupported"))

        lines.append("")
        lines.append(tr("service_info_uptime") + ":")
        if "jabber:iq:last" in features:
            seconds = await self._client.get_server_uptime(self._jid)
            if seconds is None:
                lines.append("  " + tr("service_info_unavailable"))
            else:
                lines.append("  " + tr("service_info_uptime_value",
                                       seconds=seconds,
                                       human=_human_seconds(seconds)))
        else:
            lines.append("  " + tr("service_info_unsupported"))
        return "\n".join(lines)

    def _render_contacts(self) -> None:
        while self._contacts_form.rowCount():
            self._contacts_form.removeRow(0)
        self._contacts_empty.setVisible(not self._contacts)
        self._contacts_scroll.setVisible(bool(self._contacts))
        lines: list[str] = []
        for var, values in self._contacts:
            label = tr(_CONTACT_LABELS.get(var, var))
            container = QtWidgets.QWidget(self._contacts_scroll)
            column = QtWidgets.QVBoxLayout(container)
            column.setContentsMargins(0, 0, 0, 0)
            for uri in values:
                column.addWidget(self._contact_label(uri))
            self._contacts_form.addRow(label, container)
            lines.append("%s: %s" % (label, ", ".join(values)))
        self._contacts_text = "\n".join(lines)

    def _contact_label(self, uri: str) -> QtWidgets.QLabel:
        safe = html.escape(uri)
        label = QtWidgets.QLabel(f'<a href="{safe}">{safe}</a>',
                                 self._contacts_scroll)
        label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setWordWrap(True)
        if uri.lower().startswith("xmpp:"):
            label.linkActivated.connect(self.contact_uri_clicked.emit)
        else:
            label.setOpenExternalLinks(True)
        return label

    def _on_copy(self) -> None:
        index = self._tabs.currentIndex()
        if index == 0:
            text = self._info_text
        elif index == 1:
            text = self._caps_text
        else:
            text = self._contacts_text
        QtWidgets.QApplication.clipboard().setText(text)
