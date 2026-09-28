"""PEP manager dialog.

Lists the account's PEP nodes (via ``disco#items``), lets the user open a node
(its XML payload), view/edit its configuration form and delete nodes.  The whole
flow lives in a single window with a ``QStackedWidget`` (Gajim-style).
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon
from stanza_im.ui.data_form_widget import DataFormWidget
from stanza_im.ui.xml_console import format_xml


def _button(text: str, icon_name: str, tooltip: str = "") -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    icon = QtGui.QIcon(find_icon(icon_name))
    if not icon.isNull():
        button.setIcon(icon)
    if tooltip:
        button.setToolTip(tooltip)
    return button


class PepManagerDialog(QtWidgets.QDialog):
    """List and manage the account's PEP nodes."""

    def __init__(self, get_client, run_task, parent=None):
        super().__init__(parent)
        self._get_client = get_client
        self._run_task = run_task
        self._node = ""
        self.setWindowTitle(tr("pep_manager_title"))
        self.setMinimumSize(560, 420)

        layout = QtWidgets.QVBoxLayout(self)
        self._stack = QtWidgets.QStackedWidget()
        layout.addWidget(self._stack, 1)

        self._stack.addWidget(self._build_list_page())
        self._stack.addWidget(self._build_view_page())
        self._stack.addWidget(self._build_settings_page())
        self._stack.setCurrentIndex(0)

    # ── Pages ─────────────────────────────────────────────────────

    def _build_list_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        self._status = QtWidgets.QLabel(tr("pep_list_nodes"))
        self._status.setStyleSheet("color: gray;")
        layout.addWidget(self._status)

        self._list = QtWidgets.QTreeWidget()
        self._list.setColumnCount(2)
        self._list.setHeaderLabels([tr("pep_node"), tr("pep_name")])
        self._list.setRootIsDecorated(False)
        self._list.itemSelectionChanged.connect(self._update_actions)
        self._list.itemDoubleClicked.connect(lambda *_: self._open_selected())
        layout.addWidget(self._list, 1)

        buttons = QtWidgets.QHBoxLayout()
        self._refresh_btn = _button(tr("pep_refresh"), "reload.png")
        self._refresh_btn.clicked.connect(self.refresh)
        self._delete_btn = _button(tr("pep_delete"), "process-stop.png")
        self._delete_btn.clicked.connect(self._delete_selected)
        self._settings_btn = _button(tr("pep_settings"), "edit.png")
        self._settings_btn.clicked.connect(self._settings_selected)
        self._open_btn = _button(tr("pep_open"), "service-discovery.png")
        self._open_btn.clicked.connect(self._open_selected)
        buttons.addWidget(self._refresh_btn)
        buttons.addWidget(self._delete_btn)
        buttons.addWidget(self._settings_btn)
        buttons.addWidget(self._open_btn)
        layout.addLayout(buttons)
        self._update_actions()
        return page

    def _build_view_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._view_title = QtWidgets.QLabel("")
        self._view_title.setStyleSheet("font-weight: bold;")
        self._view_title.setWordWrap(True)
        layout.addWidget(self._view_title)
        self._view_text = QtWidgets.QPlainTextEdit()
        self._view_text.setReadOnly(True)
        layout.addWidget(self._view_text, 1)
        buttons = QtWidgets.QHBoxLayout()
        back = _button(tr("pep_back"), "arrow-down.svg")
        back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        copy = _button(tr("pep_copy"), "copy.svg")
        copy.clicked.connect(self._copy_view)
        buttons.addWidget(back)
        buttons.addStretch(1)
        buttons.addWidget(copy)
        layout.addLayout(buttons)
        return page

    def _build_settings_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._settings_title = QtWidgets.QLabel("")
        self._settings_title.setStyleSheet("font-weight: bold;")
        self._settings_title.setWordWrap(True)
        layout.addWidget(self._settings_title)
        self._settings_scroll = QtWidgets.QScrollArea()
        self._settings_scroll.setWidgetResizable(True)
        layout.addWidget(self._settings_scroll, 1)
        self._settings_form_holder = QtWidgets.QWidget()
        self._settings_scroll.setWidget(self._settings_form_holder)
        self._form_widget: DataFormWidget | None = None
        self._form = None
        buttons = QtWidgets.QHBoxLayout()
        back = _button(tr("pep_back"), "arrow-down.svg")
        back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        self._apply_btn = _button(tr("pep_apply"), "ok.png")
        self._apply_btn.clicked.connect(self._apply_settings)
        buttons.addWidget(back)
        buttons.addStretch(1)
        buttons.addWidget(self._apply_btn)
        layout.addLayout(buttons)
        return page

    # ── Data ------------------------------------------------------

    def _client(self):
        return self._get_client() if self._get_client else None

    def refresh(self) -> None:
        client = self._client()
        if client is None:
            return
        self._status.setText(tr("pep_list_nodes"))
        self._run_task(self._load_nodes())

    async def _load_nodes(self) -> None:
        client = self._client()
        if client is None:
            return
        nodes = await client.pep_list_nodes()
        if nodes is None:
            self._status.setText(tr("pep_error"))
            return
        self._list.clear()
        for item in nodes:
            entry = QtWidgets.QTreeWidgetItem(
                [item.get("node", ""), item.get("name", "")])
            entry.setData(0, QtCore.Qt.ItemDataRole.UserRole, item["node"])
            self._list.addTopLevelItem(entry)
        self._status.setText(tr("pep_nodes_count", n=len(nodes)))
        self._update_actions()

    def _selected_node(self) -> str:
        item = self._list.currentItem()
        if item is None:
            return ""
        return str(item.data(0, QtCore.Qt.ItemDataRole.UserRole) or "")

    def _update_actions(self) -> None:
        has = bool(self._selected_node())
        for name in ("_delete_btn", "_settings_btn", "_open_btn"):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(has)

    def _open_selected(self) -> None:
        node = self._selected_node()
        if not node:
            return
        self._node = node
        self._view_title.setText(node)
        self._view_text.setPlainText(tr("pep_loading"))
        self._stack.setCurrentIndex(1)
        self._run_task(self._load_node(node))

    async def _load_node(self, node: str) -> None:
        client = self._client()
        if client is None:
            return
        xml = await client.pep_get_node_items(node)
        if xml is None:
            self._view_text.setPlainText(tr("pep_error"))
            return
        self._view_text.setPlainText(format_xml(ET.tostring(xml, encoding="unicode")))

    def _copy_view(self) -> None:
        QtWidgets.QApplication.clipboard().setText(self._view_text.toPlainText())

    def _settings_selected(self) -> None:
        node = self._selected_node()
        if not node:
            return
        self._node = node
        self._settings_title.setText(node)
        self._set_form_placeholder(tr("pep_loading"))
        self._stack.setCurrentIndex(2)
        self._run_task(self._load_config(node))

    def _set_form_placeholder(self, text: str) -> None:
        self._form_widget = None
        self._form = None
        holder = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(holder)
        label = QtWidgets.QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        self._settings_scroll.setWidget(holder)
        self._settings_form_holder = holder

    async def _load_config(self, node: str) -> None:
        client = self._client()
        if client is None:
            return
        form = await client.pep_get_node_config(node)
        if form is None:
            self._set_form_placeholder(tr("pep_error"))
            return
        self._form = form
        self._form_widget = DataFormWidget(form)
        self._settings_scroll.setWidget(self._form_widget)
        self._settings_form_holder = self._form_widget

    def _apply_settings(self) -> None:
        client = self._client()
        if client is None or self._form is None or not self._node:
            return
        values = self._form_widget.values() if self._form_widget else {}
        for var, value in values.items():
            try:
                self._form[var] = value
            except Exception:  # noqa: BLE001 - ignore unknown fields
                pass
        self._run_task(self._submit_config(self._node, self._form))

    async def _submit_config(self, node: str, form) -> None:
        client = self._client()
        if client is None:
            return
        ok = await client.pep_set_node_config(node, form)
        self._settings_title.setText(
            node if ok else "%s — %s" % (node, tr("pep_error")))

    def _delete_selected(self) -> None:
        node = self._selected_node()
        if not node:
            return
        answer = QtWidgets.QMessageBox.question(
            self, tr("pep_delete"),
            tr("pep_delete_confirm", node=node))
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._run_task(self._delete_node(node))

    async def _delete_node(self, node: str) -> None:
        client = self._client()
        if client is None:
            return
        if await client.pep_delete_node(node):
            self.refresh()
        else:
            QtWidgets.QMessageBox.warning(self, tr("pep_manager_title"),
                                          tr("pep_error"))
