"""Non-modal client-capabilities viewer.

Shows the features and identities a peer's client announced through XEP-0115
entity capabilities (or a live ``disco#info``), plus the raw caps data.  It is
opened from the vCard Status tab by clicking a resource row — there is no
menu entry; the window is a debugging aid.
"""
from __future__ import annotations

import asyncio

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.core.server_features import describe_feature
from stanza_im.i18n import tr
from stanza_im.include.utils import local_time_from_tzo
from stanza_im.ui.xml_console import format_xml

_FEATURE_COLUMNS = ("client_features_col_xep", "client_features_col_name",
                    "client_features_col_namespace")
_IDENTITY_COLUMNS = ("client_features_col_category",
                     "client_features_col_type",
                     "client_features_col_identity_name",
                     "client_features_col_lang")


class ClientFeaturesDialog(QtWidgets.QDialog):
    """Advertised features/identities of one contact resource."""

    def __init__(self, client, full_jid: str, block: dict | None = None,
                 parent=None):
        super().__init__(parent)
        self._client = client
        self._full_jid = str(full_jid or "")
        self._block = dict(block or {})
        self._info: dict = {}
        self._closed = False
        self.setWindowTitle(tr("client_features_title"))
        self.setMinimumSize(660, 520)
        layout = QtWidgets.QVBoxLayout(self)

        self._meta = QtWidgets.QFormLayout()
        self._meta.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._meta_labels: dict[str, QtWidgets.QLabel] = {}
        for key in ("resource", "client", "presence", "priority", "caps_node",
                    "caps_ver", "caps_hash", "source"):
            value = QtWidgets.QLabel("-")
            value.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            self._meta_labels[key] = value
            self._meta.addRow(f"{tr('client_features_' + key)}:", value)
        self._counts = QtWidgets.QLabel("")
        self._counts.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self._meta.addRow("", self._counts)
        layout.addLayout(self._meta)

        self._status = QtWidgets.QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._tabs = QtWidgets.QTabWidget(self)
        layout.addWidget(self._tabs, 1)

        # Features -----------------------------------------------------
        features_page = QtWidgets.QWidget()
        features_layout = QtWidgets.QVBoxLayout(features_page)
        features_layout.setContentsMargins(0, 0, 0, 0)
        self._filter = QtWidgets.QLineEdit(features_page)
        self._filter.setPlaceholderText(
            tr("client_features_filter_placeholder"))
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        features_layout.addWidget(self._filter)
        self._features_tree = QtWidgets.QTreeWidget(features_page)
        self._features_tree.setColumnCount(len(_FEATURE_COLUMNS))
        self._features_tree.setHeaderLabels(
            [tr(key) for key in _FEATURE_COLUMNS])
        self._features_tree.setRootIsDecorated(False)
        self._features_tree.setAlternatingRowColors(True)
        self._features_tree.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        features_layout.addWidget(self._features_tree, 1)
        self._features_empty = QtWidgets.QLabel(
            tr("client_features_empty"), features_page)
        self._features_empty.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter)
        features_layout.addWidget(self._features_empty)
        self._tabs.addTab(features_page, tr("client_features_tab_features"))

        # Identities ---------------------------------------------------
        identities_page = QtWidgets.QWidget()
        identities_layout = QtWidgets.QVBoxLayout(identities_page)
        identities_layout.setContentsMargins(0, 0, 0, 0)
        self._identities_tree = QtWidgets.QTreeWidget(identities_page)
        self._identities_tree.setColumnCount(len(_IDENTITY_COLUMNS))
        self._identities_tree.setHeaderLabels(
            [tr(key) for key in _IDENTITY_COLUMNS])
        self._identities_tree.setRootIsDecorated(False)
        self._identities_tree.setAlternatingRowColors(True)
        self._identities_tree.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        identities_layout.addWidget(self._identities_tree, 1)
        self._identities_empty = QtWidgets.QLabel(
            tr("client_features_no_identities"), identities_page)
        self._identities_empty.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter)
        identities_layout.addWidget(self._identities_empty)
        self._tabs.addTab(identities_page,
                          tr("client_features_tab_identities"))

        # Raw data -----------------------------------------------------
        self._raw = QtWidgets.QPlainTextEdit(self)
        self._raw.setReadOnly(True)
        self._raw.setLineWrapMode(
            QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        font = QtGui.QFontDatabase.systemFont(
            QtGui.QFontDatabase.SystemFont.FixedFont)
        self._raw.setFont(font)
        self._tabs.addTab(self._raw, tr("client_features_tab_raw"))

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._refresh = QtWidgets.QPushButton(tr("vcard_refresh"), self)
        self._refresh.clicked.connect(lambda:
                                      asyncio.create_task(self._load(True)))
        buttons.addWidget(self._refresh)
        self._copy = QtWidgets.QPushButton(tr("cert_copy"), self)
        self._copy.clicked.connect(self._on_copy)
        buttons.addWidget(self._copy)
        close = QtWidgets.QPushButton(tr("dialog_close"), self)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._populate_block()
        self._render({"features": [], "identities": [], "node": "",
                      "ver": "", "hash": "", "raw": "", "source": ""})
        if self._client is not None:
            asyncio.create_task(self._load(False))

    # ── rendering ──────────────────────────────────────────────────
    def _populate_block(self) -> None:
        block = self._block
        self._meta_labels["resource"].setText(self._full_jid or "-")
        client = str(block.get("client") or "")
        version = str(block.get("version") or "")
        os_name = str(block.get("os") or "")
        client_line = (client + (" " + version if version else "")).strip()
        if os_name:
            client_line += (" / " if client_line else "") + os_name
        local = local_time_from_tzo(str(block.get("tzo") or ""))
        if local:
            client_line += f"  ({local})"
        self._meta_labels["client"].setText(client_line or "-")
        show = str(block.get("show") or "")
        status = str(block.get("status") or "")
        presence = show or "-"
        if status:
            presence += f" — {status}"
        self._meta_labels["presence"].setText(presence)
        priority = block.get("priority")
        self._meta_labels["priority"].setText(
            "-" if priority in (None, "") else str(priority))
        self._meta_labels["caps_node"].setText(
            str(block.get("caps_node") or "-"))
        self._meta_labels["caps_ver"].setText(
            str(block.get("caps_ver") or "-"))
        self._meta_labels["caps_hash"].setText(
            str(block.get("caps_hash") or "-"))
        self._meta_labels["source"].setText("-")

    def _render(self, info: dict) -> None:
        self._info = dict(info or {})
        features = [str(item) for item in (self._info.get("features") or [])
                    if item]
        identities = list(self._info.get("identities") or [])
        self._meta_labels["caps_node"].setText(
            str(self._info.get("node")
                or self._block.get("caps_node") or "-"))
        self._meta_labels["caps_ver"].setText(
            str(self._info.get("ver")
                or self._block.get("caps_ver") or "-"))
        self._meta_labels["caps_hash"].setText(
            str(self._info.get("hash")
                or self._block.get("caps_hash") or "-"))
        source = str(self._info.get("source") or "")
        source_text = {"caps": tr("client_features_source_caps"),
                       "disco": tr("client_features_source_disco")}.get(
                           source, source or "-")
        self._meta_labels["source"].setText(source_text)
        self._counts.setText(tr("client_features_counts",
                               features=len(features),
                               identities=len(identities)))

        self._features_tree.clear()
        for namespace in sorted(features, key=str.casefold):
            described = describe_feature(namespace)
            if described.startswith("XEP-") and ": " in described:
                xep, name = described.split(": ", 1)
            else:
                xep, name = "", ""
            item = QtWidgets.QTreeWidgetItem([xep, name, namespace])
            self._features_tree.addTopLevelItem(item)
        self._features_empty.setVisible(not features)
        for column in range(self._features_tree.columnCount()):
            self._features_tree.resizeColumnToContents(column)
        self._apply_filter(self._filter.text())

        self._identities_tree.clear()
        for identity in sorted(
                identities,
                key=lambda row: (str(row.get("category") or "").casefold(),
                                 str(row.get("type") or "").casefold(),
                                 str(row.get("name") or "").casefold())):
            self._identities_tree.addTopLevelItem(QtWidgets.QTreeWidgetItem([
                str(identity.get("category") or ""),
                str(identity.get("type") or ""),
                str(identity.get("name") or ""),
                str(identity.get("xml_lang") or ""),
            ]))
        self._identities_empty.setVisible(not identities)
        for column in range(self._identities_tree.columnCount()):
            self._identities_tree.resizeColumnToContents(column)

        self._raw.setPlainText(self._raw_text())

    def _apply_filter(self, text: str) -> None:
        needle = str(text or "").casefold()
        for index in range(self._features_tree.topLevelItemCount()):
            item = self._features_tree.topLevelItem(index)
            haystack = " ".join(
                item.text(column)
                for column in range(self._features_tree.columnCount()))
            item.setHidden(bool(needle) and needle not in haystack.casefold())

    def _raw_text(self) -> str:
        info = self._info
        lines = [
            f"{tr('client_features_resource')}: {self._full_jid}",
            f"{tr('client_features_caps_node')}: {info.get('node') or '-'}",
            f"{tr('client_features_caps_ver')}: {info.get('ver') or '-'}",
            f"{tr('client_features_caps_hash')}: {info.get('hash') or '-'}",
            f"{tr('client_features_source')}: {info.get('source') or '-'}",
            "",
            f"{tr('client_features_raw_identities')}:",
        ]
        identities = info.get("identities") or []
        if identities:
            for identity in identities:
                lang = identity.get("xml_lang") or ""
                lines.append(
                    "  {category}/{type}{lang}: {name}".format(
                        category=identity.get("category") or "",
                        type=identity.get("type") or "",
                        lang=f" [{lang}]" if lang else "",
                        name=identity.get("name") or ""))
        else:
            lines.append("  -")
        lines.append("")
        lines.append(f"{tr('client_features_raw_features')}:")
        features = info.get("features") or []
        if features:
            lines.extend(f"  {feature}" for feature in features)
        else:
            lines.append("  -")
        raw = str(info.get("raw") or "")
        if raw:
            lines.append("")
            lines.append(f"{tr('client_features_raw_xml')}:")
            lines.append(format_xml(raw))
        return "\n".join(lines)

    def _on_copy(self) -> None:
        QtWidgets.QApplication.clipboard().setText(
            self._raw_text() + "\n\n" + self._raw.toPlainText())

    # ── loading ────────────────────────────────────────────────────
    async def _load(self, refresh: bool) -> None:
        if self._client is None:
            return
        self._refresh.setEnabled(False)
        self._status.setText(tr("client_features_loading"))
        try:
            info = await self._client.resource_caps(
                self._full_jid, refresh=refresh)
        except Exception:
            if not self._closed:
                self._status.setText(tr("client_features_error"))
                self._refresh.setEnabled(True)
            return
        if self._closed:
            return
        self._status.setText("")
        self._refresh.setEnabled(True)
        self._render(info)

    def done(self, result: int) -> None:
        self._closed = True
        super().done(result)
