"""XEP-0144 Roster Item Exchange confirmation dialog."""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr

_ACTION_ORDER = ("add", "modify", "delete")
_ACTION_LABEL = {
    "add": "rosterx_add",
    "modify": "rosterx_modify",
    "delete": "rosterx_delete",
}


class RosterExchangeDialog(QtWidgets.QDialog):
    """Show the suggested roster changes and let the user pick what to apply.

    The tree has three levels: the action (Add/Modify/Delete), the suggested
    group (or "No group") and the JID/nickname.  Every node carries a
    checkbox; parents are auto-tristate, so unchecking one skips everything
    below it.
    """

    def __init__(self, sender: str, sender_name: str, items: list[dict],
                 body: str = "", parent=None):
        super().__init__(parent)
        self._items = list(items)
        self.setWindowTitle(tr("rosterx_title"))
        self.resize(520, 520)
        layout = QtWidgets.QVBoxLayout(self)

        title = QtWidgets.QLabel(tr("rosterx_title"), self)
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        who = sender_name or sender
        if sender and sender_name:
            who = f"{sender_name} ({sender})"
        label = QtWidgets.QLabel(tr("rosterx_from", who=who or sender), self)
        label.setWordWrap(True)
        label.setStyleSheet("color: gray;")
        layout.addWidget(label)

        if body:
            body_label = QtWidgets.QLabel(body.strip(), self)
            body_label.setWordWrap(True)
            layout.addWidget(body_label)

        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setHeaderHidden(True)
        layout.addWidget(self._tree, 1)

        self._build_tree()

        buttons = QtWidgets.QDialogButtonBox(self)
        self._apply = buttons.addButton(
            tr("rosterx_apply"),
            QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(
            tr("dialog_cancel"),
            QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        self._apply.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._sync_apply()

    # ── tree construction ───────────────────────────────────────

    def _build_tree(self) -> None:
        roots: dict[str, QtWidgets.QTreeWidgetItem] = {}
        for action in _ACTION_ORDER:
            entries = [i for i in self._items if i.get("action") == action]
            if not entries:
                continue
            root = QtWidgets.QTreeWidgetItem(self._tree,
                                             [tr(_ACTION_LABEL[action])])
            root.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled
                          | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                          | QtCore.Qt.ItemFlag.ItemIsAutoTristate)
            root.setExpanded(True)
            roots[action] = root
        for index, entry in enumerate(self._items):
            root = roots.get(entry.get("action"))
            if root is None:
                continue
            groups = [g for g in (entry.get("groups") or []) if g] or [""]
            for group in groups:
                group_item = self._group_item(root, group)
                leaf = QtWidgets.QTreeWidgetItem(group_item,
                                                 [self._leaf_label(entry)])
                leaf.setFlags(leaf.flags()
                              | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                leaf.setCheckState(0, QtCore.Qt.CheckState.Checked)
                leaf.setData(0, QtCore.Qt.ItemDataRole.UserRole, (index, group))
                leaf.setToolTip(0, entry.get("jid", ""))
        # Parents with auto-tristate pick up their children's state once the
        # leaves are checked; make sure the roots are fully checked.
        for root in roots.values():
            root.setCheckState(0, QtCore.Qt.CheckState.Checked)
        self._tree.expandAll()
        self._tree.itemChanged.connect(lambda *_: self._sync_apply())

    def _group_item(self, root: QtWidgets.QTreeWidgetItem,
                    group: str) -> QtWidgets.QTreeWidgetItem:
        for i in range(root.childCount()):
            child = root.child(i)
            if child.data(0, QtCore.Qt.ItemDataRole.UserRole) == group:
                return child
        item = QtWidgets.QTreeWidgetItem(root,
                                         [group or tr("rosterx_no_group")])
        item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled
                      | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                      | QtCore.Qt.ItemFlag.ItemIsAutoTristate)
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, group)
        item.setExpanded(True)
        return item

    @staticmethod
    def _leaf_label(entry: dict) -> str:
        jid = entry.get("jid", "")
        name = entry.get("name") or ""
        return f"{name} ({jid})" if name else jid

    # ── selection ───────────────────────────────────────────────

    def _leaves(self):
        stack = [self._tree.topLevelItem(i)
                 for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.childCount():
                stack.extend(item.child(i) for i in range(item.childCount()))
            elif item.data(0, QtCore.Qt.ItemDataRole.UserRole) is not None:
                yield item

    def selected_items(self) -> list[dict]:
        """The checked changes, one entry per JID with the selected groups."""
        picked: dict[int, set] = {}
        for leaf in self._leaves():
            if leaf.checkState(0) != QtCore.Qt.CheckState.Checked:
                continue
            index, group = leaf.data(0, QtCore.Qt.ItemDataRole.UserRole)
            picked.setdefault(index, set())
            if group:
                picked[index].add(group)
        out = []
        for index in sorted(picked):
            entry = self._items[index]
            groups = [g for g in (entry.get("groups") or [])
                      if g in picked[index]]
            out.append({"action": entry.get("action", "add"),
                        "jid": entry.get("jid", ""),
                        "name": entry.get("name", ""),
                        "groups": groups})
        return out

    def _sync_apply(self) -> None:
        self._apply.setEnabled(bool(self.selected_items()))
