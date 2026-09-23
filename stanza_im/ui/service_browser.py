"""XEP-0030 service discovery browser.

The tree is built fully lazily with no eager discovery.  A node renders its
direct children "as is" from a single ``disco#items`` request and every
service item shows a tentative expand arrow immediately.  Expanding (or
clicking) a node issues its own ``disco#items`` and only then are the branch
contents drawn; nodes with no children lose their arrow.  Deep items inherit
the parent's icon instead of being probed with ``disco#info`` (only the top
level is classified to drive the category grouping).  The ``Автообзор``
checkbox opts into a recursive pre-discovery of the whole tree (bounded
depth, cycle-safe).
"""
from __future__ import annotations

import asyncio
import logging
import os

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon

logger = logging.getLogger(__name__)

_DEFAULT_ICON = "system-users.png"
_CAT_ICONS = {
    "conference": "muc.png",
    "gateway": "transports.png",
    "directory": "system-users.png",
    "store": "system-users.png",
    "auth": "gtk-preferences.png",
    "server": "gtk-preferences.png",
    "proxy": "gtk-preferences.png",
    "client": "event.png",
    "pubsub": "event.png",
    "headline": "event.png",
    "msg": "event.png",
    "component": "event.png",
    "hierarchy": "event.png",
    "gateway": "transports.png",
}
_ROOT_KEYS = (
    ("service_conferences", "muc.png"),
    ("service_transports", "transports.png"),
    ("service_services", "system-users.png"),
    ("service_other", "event.png"),
)
_ACTION_SPECS = (
    ("service_register", "register.png"),
    ("service_unregister", "register.png"),
    ("service_search", "search.png"),
    ("service_add_roster", "add-user.png"),
    ("service_commands", "exec.png"),
    ("service_version", "info.svg"),
    ("service_vcard", "v-card.png"),
)
_ACTION_TIPS = {
    "service_register": "register_tip",
    "service_unregister": "unregister_tip",
    "service_search": "search_tip",
    "service_add_roster": "add_tip",
    "service_commands": "commands_tip",
    "service_version": "version_tip",
    "service_vcard": "vcard_tip",
}
_MAX_DEPTH = 8


class ServiceBrowserDialog(QtWidgets.QDialog):
    conference_requested = QtCore.pyqtSignal(str)
    vcard_requested = QtCore.pyqtSignal(str)
    servers_updated = QtCore.pyqtSignal(list)
    xmpp_uri_requested = QtCore.pyqtSignal(str)

    def __init__(self, client, servers: list[str], parent=None):
        super().__init__(parent)
        self._client = client
        self._servers = [servers] if isinstance(servers, str) else list(servers)
        self._server_values = list(dict.fromkeys(self._servers))
        self._gen = 0
        self._kids: dict[str, list[dict]] = {}
        self._kid_futures: dict[str, asyncio.Future] = {}
        self._info_futures: dict[tuple[str, str], asyncio.Future] = {}
        self._selected: QtWidgets.QTreeWidgetItem | None = None
        self._seen: set[tuple[str, str]] = set()
        self._visited: set[tuple[str, str]] = set()
        self._roots: dict[str, QtWidgets.QTreeWidgetItem] = {}
        self.setWindowTitle(tr("service_browser_title"))
        self.resize(650, 500)
        layout = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel(tr("service_server")))
        self._server = QtWidgets.QComboBox(); self._server.setEditable(True)
        self._server.addItems(self._server_values)
        top.addWidget(self._server, 1)
        ok = QtWidgets.QPushButton(tr("service_browse_action"))
        ok.clicked.connect(self._browse)
        top.addWidget(ok)
        self._info_btn = QtWidgets.QToolButton()
        self._info_btn.setIcon(self._icon("info.svg"))
        self._info_btn.setToolTip(tr("service_info_tooltip"))
        self._info_btn.setAutoRaise(True)
        self._info_btn.clicked.connect(self._open_info)
        top.addWidget(self._info_btn)
        layout.addLayout(top)
        self._tree = QtWidgets.QTreeWidget()
        self._tree.setHeaderLabels([tr("service_name"), tr("service_jid")])
        self._tree.setColumnWidth(0, 360)
        self._tree.itemDoubleClicked.connect(self._double_click)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.currentItemChanged.connect(self._on_item_selected)
        self._tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._context)
        layout.addWidget(self._tree, 1)
        actions = QtWidgets.QHBoxLayout()
        self._action_buttons: dict[str, QtWidgets.QToolButton] = {}
        self._action_handlers = {
            "service_register": self._register,
            "service_unregister": self._unregister,
            "service_search": self._search,
            "service_add_roster": self._add_to_roster,
            "service_commands": self._commands,
            "service_version": self._version,
            "service_vcard": self._vcard,
        }
        for key, icon in _ACTION_SPECS:
            actions.addWidget(self._new_action(key, icon))
        self._btn_register = self._action_buttons["service_register"]
        self._btn_unregister = self._action_buttons["service_unregister"]
        self._btn_search = self._action_buttons["service_search"]
        self._btn_add = self._action_buttons["service_add_roster"]
        self._btn_commands = self._action_buttons["service_commands"]
        self._btn_version = self._action_buttons["service_version"]
        self._btn_vcard = self._action_buttons["service_vcard"]
        for key, handler in self._action_handlers.items():
            self._action_buttons[key].clicked.connect(handler)
        layout.addLayout(actions)
        bottom = QtWidgets.QHBoxLayout()
        self._auto = QtWidgets.QCheckBox(tr("service_auto_browse"))
        self._auto.toggled.connect(self._on_auto_toggled)
        bottom.addWidget(self._auto)
        bottom.addStretch()
        self._status = QtWidgets.QLabel()
        self._status.setStyleSheet("color: #b00020;")
        bottom.addWidget(self._status)
        close = QtWidgets.QPushButton(tr("dialog_close")); close.clicked.connect(self.reject)
        bottom.addWidget(close)
        layout.addLayout(bottom)
        if self._server_values:
            self._server.setCurrentIndex(0)
            default = self._server_values[0]
            asyncio.get_event_loop().create_task(self._load(default))

    # ── Building the tree ──────────────────────────────────────────────

    @staticmethod
    def _icon(filename: str) -> QtGui.QIcon:
        path = find_icon(filename)
        if path:
            pix = QtGui.QPixmap(path)
            if not pix.isNull():
                return QtGui.QIcon(pix)
        return QtGui.QIcon()

    def _new_action(self, text_key: str, icon: str) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setText(tr(text_key))
        tip_key = _ACTION_TIPS.get(text_key)
        if tip_key:
            button.setToolTip(tr(tip_key))
        button.setIcon(self._icon(icon))
        button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setEnabled(False)
        self._action_buttons[text_key] = button
        return button

    def _icon_for(self, item: dict) -> str:
        type_ = (item.get("type") or "").lower()
        if type_ == "rss":
            return "rss-online.png"
        if type_ == "weather":
            return "weather-online.png"
        category = item.get("category", "")
        return (_CAT_ICONS.get(category.lower(), _DEFAULT_ICON)
                if category else _DEFAULT_ICON)

    @staticmethod
    def _node_tooltip(data: dict) -> str:
        """Rich-text tooltip from the cached disco#info/items data of a node."""
        from stanza_im.include.utils import escape_html
        lines = []
        jid = data.get("jid", "")
        if jid:
            lines.append(f"{tr('tooltip_jid')}: <b>{escape_html(jid)}</b>")
        node = data.get("node", "")
        if node:
            lines.append(f"{tr('tooltip_node')}: {escape_html(node)}")
        category = data.get("category", "")
        if category:
            lines.append(f"{tr('tooltip_category')}: {escape_html(category)}")
        type_ = data.get("type", "")
        if type_:
            lines.append(f"{tr('tooltip_type')}: {escape_html(type_)}")
        features = data.get("features") or []
        if features:
            lines.append(tr("tooltip_features") + ":")
            shown = features[:12]
            lines += [f"&nbsp;&nbsp;&middot;&nbsp; {escape_html(f)}"
                      for f in shown]
            if len(features) > 12:
                lines.append(f"&#8230; +{len(features) - 12}")
        if not lines:
            return ""
        return "<br>".join(lines)

    def _make_node(self, item: dict, icon: str = "") -> QtWidgets.QTreeWidgetItem:
        name = item.get("name") or item.get("jid", "")
        category = item.get("category", "")
        node = QtWidgets.QTreeWidgetItem([name, item.get("jid", "")])
        if not icon:
            icon = self._icon_for(item)
        node.setData(0, QtCore.Qt.ItemDataRole.UserRole, {
            "jid": item.get("jid", ""), "node": item.get("node", ""),
            "name": name, "category": category, "type": item.get("type", ""),
            "icon": icon, "features": item.get("features", [])})
        node.setIcon(0, self._icon(icon))
        node.setToolTip(0, self._node_tooltip(
            node.data(0, QtCore.Qt.ItemDataRole.UserRole)))
        node.setChildIndicatorPolicy(
            QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        return node

    @staticmethod
    def _category_root_key(category: str) -> str:
        if category == "conference":
            return "service_conferences"
        if category == "gateway":
            return "service_transports"
        if category:
            return "service_services"
        return "service_other"

    def _record_server(self, server: str) -> None:
        if server and server not in self._server_values:
            self._server_values.append(server)
            self._server.addItem(server)
        self.servers_updated.emit(list(self._server_values))

    # ── Discovery ───────────────────────────────────────────────────────

    def _kids_future(self, jid: str, node: str) -> asyncio.Future:
        key = (jid, node)
        fut = self._kid_futures.get(key)
        if fut is None or fut.done():
            fut = asyncio.get_event_loop().create_future()
            self._kid_futures[key] = fut
            asyncio.get_event_loop().create_task(
                self._fetch_kids(jid, node, fut, self._gen))
        return fut

    async def _fetch_kids(self, jid: str, node: str, fut: asyncio.Future,
                          gen: int) -> None:
        try:
            children = await self._client.discover_service_items(jid, node)
            children = [child for child in children
                        if not (child.get("jid", "") == jid
                                and child.get("node", "") == node)]
        except Exception as exc:
            logger.warning("Cannot browse %s/%s: %s", jid, node, exc)
            children = []
        if self._gen == gen:
            self._kids[(jid, node)] = children
        if not fut.done():
            fut.set_result(children)

    async def _load(self, server: str) -> None:
        gen = self._gen + 1
        self._gen = gen
        self._tree.clear()
        self._roots.clear()
        self._kids.clear()
        self._kid_futures.clear()
        self._info_futures.clear()
        self._selected = None
        self._seen.clear()
        self._visited.clear()
        self._status.clear()
        try:
            services = await self._client.discover_services(server)
        except Exception as exc:
            if self._gen == gen:
                self._status.setText(str(exc))
            return
        if self._gen != gen:
            return
        roots = {}
        for key, icon in _ROOT_KEYS:
            root = QtWidgets.QTreeWidgetItem([tr(key), ""])
            root.setIcon(0, self._icon(icon))
            self._tree.addTopLevelItem(root)
            roots[key] = root
        self._roots = roots
        for item in services:
            jid = item.get("jid", "")
            if not jid:
                continue
            key = (jid, item.get("node", ""))
            if key in self._seen:
                continue
            self._seen.add(key)
            roots[self._category_root_key(item.get("category", ""))].addChild(
                self._make_node(item))
        self._record_server(server)
        if self._auto.isChecked():
            for root in roots.values():
                await self._recursive(root, gen, 0)

    async def _ensure_children(self, item: QtWidgets.QTreeWidgetItem,
                               gen: int) -> None:
        """Load (cached) children of a service node and reveal them once."""
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data or not data.get("jid"):
            return
        fut = self._kids_future(data["jid"], data.get("node", ""))
        children = await fut
        if self._gen != gen or item.treeWidget() is None:
            return
        if not children:
            item.setChildIndicatorPolicy(
                QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)
            item.setExpanded(False)
            return
        icon = data.get("icon") or _DEFAULT_ICON
        existing = set()
        for index in range(item.childCount()):
            child_data = item.child(index).data(0, QtCore.Qt.ItemDataRole.UserRole)
            if child_data:
                existing.add((child_data.get("jid"), child_data.get("node", "")))
        for child in children:
            if not child.get("jid"):
                continue
            key = (child["jid"], child.get("node", ""))
            if key in existing:
                continue
            item.addChild(self._make_node(child, icon))
            existing.add(key)

    async def _recursive(self, item: QtWidgets.QTreeWidgetItem,
                         gen: int, depth: int) -> None:
        if self._gen != gen or depth >= _MAX_DEPTH:
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if data and data.get("jid"):
            key = (data["jid"], data.get("node", ""))
            if key in self._visited:
                return
            self._visited.add(key)
            await self._ensure_children(item, gen)
            if self._gen != gen:
                return
        for index in range(item.childCount()):
            await self._recursive(item.child(index), gen, depth + 1)

    # ── User interaction ────────────────────────────────────────────────

    def _browse(self) -> None:
        server = self._server.currentText().strip()
        if server:
            asyncio.get_event_loop().create_task(self._load(server))

    def _open_info(self) -> None:
        """Show the info dialog for the selected node or the server."""
        data = self._current_data()
        if data and data.get("jid"):
            jid, node = data["jid"], data.get("node", "")
        else:
            jid, node = self._server.currentText().strip(), ""
        if not jid:
            return
        from stanza_im.ui.service_info_dialog import ServiceInfoDialog
        dialog = ServiceInfoDialog(self._client, jid, node, self)
        dialog.contact_uri_clicked.connect(self.xmpp_uri_requested.emit)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.show()

    def _on_auto_toggled(self, checked: bool) -> None:
        if not checked:
            return
        gen = self._gen
        for root in self._roots.values():
            asyncio.get_event_loop().create_task(self._recursive(root, gen, 0))

    def _on_item_expanded(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """On expand: discover this node's children (no eager probing)."""
        gen = self._gen
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if data and data.get("jid") and item.childCount() == 0:
            asyncio.get_event_loop().create_task(self._ensure_children(item, gen))

    def _on_item_clicked(self, item: QtWidgets.QTreeWidgetItem,
                         _column: int) -> None:
        """A click preloads the node's children so expansion is instant."""
        gen = self._gen
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if data and data.get("jid") and item.childCount() == 0:
            asyncio.get_event_loop().create_task(self._ensure_children(item, gen))

    def _emit_conference(self, jid: str) -> None:
        self.conference_requested.emit(jid)

    def _double_click(self, item: QtWidgets.QTreeWidgetItem,
                      _column: int) -> None:
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data or not data.get("jid"):
            return
        if data.get("category") == "conference":
            if item.isExpanded():
                item.setExpanded(False)
            self._emit_conference(data["jid"])
        else:
            self._open_add_contact(data["jid"])

    def _open_add_contact(self, jid: str) -> None:
        """Open the add-contact dialog with *jid* pre-filled."""
        from stanza_im.ui.add_contact_dialog import AddContactDialog
        groups = sorted({
            group
            for item in self._client.get_roster_snapshot()
            for group in item.get("groups") or []
            if group not in (tr("roster_group_conferences"),
                             tr("roster_group_transports"),
                             tr("roster_group_ungrouped"))
        }, key=str.casefold)
        dlg = AddContactDialog(groups, self._client, self, jid=jid)
        if not dlg.exec():
            return
        data = dlg.collect()
        self._client.add_contact(data["jid"], data["name"],
                                 [data["group"]] if data["group"] else [],
                                 data["message"], data["subscribe"])
        self._client.request_roster()

    def _current_data(self) -> dict | None:
        item = self._tree.currentItem()
        if item is None:
            return None
        return item.data(0, QtCore.Qt.ItemDataRole.UserRole)

    def _on_item_selected(self, current: QtWidgets.QTreeWidgetItem,
                          _previous: QtWidgets.QTreeWidgetItem) -> None:
        """Enable/disable the action buttons for the selected service."""
        self._selected = current
        data = self._current_data()
        self._apply_actions(None)
        if not data or not data.get("jid"):
            return
        features = data.get("features")
        if features:
            self._apply_actions(features)
            return
        gen = self._gen
        asyncio.get_event_loop().create_task(
            self._resolve_selected(gen, data["jid"], data.get("node", "")))

    async def _resolve_selected(self, gen: int, jid: str, node: str) -> None:
        key = (jid, node)
        fut = self._info_futures.get(key)
        if fut is None or fut.done():
            fut = asyncio.get_event_loop().create_future()
            self._info_futures[key] = fut
            asyncio.get_event_loop().create_task(self._fetch_info(key, fut))
        try:
            info = await asyncio.wait_for(fut, timeout=30)
        except Exception:
            return
        if self._gen != gen or self._selected is None:
            return
        data = self._selected.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data or (data.get("jid"), data.get("node", "")) != key:
            return
        if not data.get("category"):
            data["category"] = info.get("category", "")
        if not data.get("type"):
            data["type"] = info.get("type", "")
        if not data.get("features"):
            data["features"] = info.get("features", [])
        self._selected.setData(0, QtCore.Qt.ItemDataRole.UserRole, data)
        self._selected.setToolTip(0, self._node_tooltip(data))
        self._apply_actions(info.get("features"))

    async def _fetch_info(self, key: tuple[str, str],
                          fut: asyncio.Future) -> None:
        jid, node = key
        try:
            info = await self._client.discover_service_info(jid, node)
        except Exception:
            info = {"features": []}
        if not fut.done():
            fut.set_result(info)

    def _apply_actions(self, features: list[str] | None) -> None:
        features = set(features or ())
        data = self._current_data()
        for key in self._action_buttons:
            self._action_buttons[key].setEnabled(
                self._action_enabled(key, features, data))

    def _register(self) -> None:
        data = self._current_data()
        if not data or not data.get("jid"):
            return
        from stanza_im.ui.registration_dialog import RegistrationDialog
        RegistrationDialog(self._client, data["jid"], self).exec()

    def _search(self) -> None:
        data = self._current_data()
        if not data or not data.get("jid"):
            return
        from stanza_im.ui.search_dialog import SearchDialog
        dlg = SearchDialog(self._client, data["jid"], self)
        dlg.vcard_requested.connect(self.vcard_requested)
        dlg.exec()

    def _commands(self) -> None:
        data = self._current_data()
        if not data or not data.get("jid"):
            return
        from stanza_im.ui.adhoc_dialog import AdhocDialog
        AdhocDialog(self._client, data["jid"], self).exec()

    def _unregister(self) -> None:
        data = self._current_data()
        if not data or not data.get("jid"):
            return
        jid = data["jid"]
        answer = QtWidgets.QMessageBox.question(
            self, tr("service_unregister"),
            tr("service_unregister_confirm", jid=jid))
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        asyncio.get_event_loop().create_task(self._do_unregister(jid))

    async def _do_unregister(self, jid: str) -> None:
        try:
            await self._client.unregister(jid)
            self._status.setText(tr("register_removed"))
        except Exception as exc:
            self._status.setText(tr("register_error", error=str(exc)))

    def _add_to_roster(self) -> None:
        data = self._current_data()
        if not data or not data.get("jid"):
            return
        jid = data["jid"]
        answer = QtWidgets.QMessageBox.question(
            self, tr("service_add_roster"),
            tr("service_add_confirm", jid=jid))
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._client.add_contact(jid, request_subscription=True)
        self._status.setText(tr("service_added", jid=jid))

    def _version(self) -> None:
        data = self._current_data()
        if not data or not data.get("jid"):
            return
        asyncio.get_event_loop().create_task(self._show_version(data["jid"]))

    async def _show_version(self, jid: str) -> None:
        try:
            info = await self._client.get_entity_version(jid)
        except Exception as exc:
            QtWidgets.QMessageBox.information(
                self, tr("version_title"),
                tr("version_error", error=str(exc)))
            return
        if not any(info.values()):
            QtWidgets.QMessageBox.information(self, tr("version_title"),
                                              tr("version_unknown", jid=jid))
            return
        text = tr("version_jid", jid=jid)
        if info.get("software"):
            text += "\n" + tr("version_software", value=info["software"])
        if info.get("version"):
            text += "\n" + tr("version_number", value=info["version"])
        if info.get("os"):
            text += "\n" + tr("version_os", value=info["os"])
        QtWidgets.QMessageBox.information(self, tr("version_title"), text)

    def _vcard(self) -> None:
        data = self._current_data()
        if not data or not data.get("jid"):
            return
        self.vcard_requested.emit(data["jid"])

    def _context(self, pos: QtCore.QPoint) -> None:
        item = self._tree.itemAt(pos)
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not data or not data.get("jid"):
            return
        self._tree.setCurrentItem(item)
        self._selected = item
        self._build_menu(data).exec(self._tree.viewport().mapToGlobal(pos))

    def _build_menu(self, data: dict) -> QtWidgets.QMenu:
        jid = data["jid"]
        conference = (data.get("category") == "conference")
        features = self._resolve_features(data)
        menu = QtWidgets.QMenu(self)
        if conference:
            menu.addAction(self._icon("muc.png"),
                           tr("service_open_conference"),
                           lambda: self._emit_conference(jid))
        for key, icon in _ACTION_SPECS:
            action = menu.addAction(self._icon(icon), tr(key),
                                    self._action_handlers[key])
            action.setEnabled(self._action_enabled(key, features, data))
        menu.addSeparator()
        menu.addAction(tr("conference_copy_jid"),
                       lambda: QtWidgets.QApplication.clipboard().setText(jid))
        return menu

    def _resolve_features(self, data: dict) -> set[str]:
        features = data.get("features")
        if features:
            return set(features)
        fut = self._info_futures.get((data.get("jid"), data.get("node", "")))
        if fut is not None and fut.done():
            try:
                info = fut.result()
            except Exception:
                info = {}
            return set(info.get("features", ()) or ())
        return set()

    def _action_enabled(self, key: str, features: set[str],
                        data: dict) -> bool:
        if key in ("service_register", "service_unregister"):
            return "jabber:iq:register" in features
        if key == "service_search":
            return "jabber:iq:search" in features
        if key == "service_commands":
            return "http://jabber.org/protocol/commands" in features
        return bool((data or {}).get("jid"))