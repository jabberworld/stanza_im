"""Plugin manager dialog.

Shows the discovered plugins grouped by category in a tree with a checkbox per
plugin (and a tri-state checkbox per category).  The enabled set is written to
``config.plugins`` only when the user accepts ("Ok"); "Cancel" discards the
changes.  The dialog is agnostic about what a plugin does — it just reports the
new selection through ``plugins_changed``.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon
from stanza_im.plugins import Plugin, discover, stored_enabled_ids


class PluginManagerDialog(QtWidgets.QDialog):
    """Enable/disable the installed plugins."""

    plugins_changed = QtCore.pyqtSignal(list)  # new list of enabled plugin ids

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._plugins: list[Plugin] = discover()
        self.setWindowTitle(tr("plugin_manager_title"))
        self.setMinimumSize(460, 380)

        layout = QtWidgets.QVBoxLayout(self)

        if not self._plugins:
            label = QtWidgets.QLabel(tr("prefs_no_plugins"))
            label.setWordWrap(True)
            layout.addWidget(label)
        else:
            self._tree = QtWidgets.QTreeWidget()
            self._tree.setHeaderHidden(True)
            self._tree.setRootIsDecorated(True)
            layout.addWidget(self._tree, 1)
            self._build_tree()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(tr("dialog_ok"))
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
                tr("dialog_cancel"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Tree ──────────────────────────────────────────────────────

    def _build_tree(self) -> None:
        enabled = set(stored_enabled_ids(self._config))
        categories: dict[str, list[Plugin]] = {}
        for plugin in self._plugins:
            categories.setdefault(plugin.category, []).append(plugin)

        for category, plugins in categories.items():
            header = QtWidgets.QTreeWidgetItem(
                [tr(category) if category else tr("plugin_category_other")])
            header.setFlags(header.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                            | QtCore.Qt.ItemFlag.ItemIsAutoTristate)
            header.setExpanded(True)
            self._tree.addTopLevelItem(header)
            for plugin in plugins:
                item = QtWidgets.QTreeWidgetItem([tr(plugin.name)])
                icon_path = find_icon(plugin.icon) if plugin.icon else ""
                if icon_path:
                    item.setIcon(0, QtGui.QIcon(icon_path))
                if plugin.description:
                    item.setToolTip(0, tr(plugin.description)
                                    if plugin.description else "")
                item.setFlags(item.flags()
                              | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    0, QtCore.Qt.CheckState.Checked if plugin.id in enabled
                    else QtCore.Qt.CheckState.Unchecked)
                item.setData(0, QtCore.Qt.ItemDataRole.UserRole, plugin.id)
                header.addChild(item)

    def _checked_ids(self) -> list[str]:
        ids: list[str] = []
        for i in range(self._tree.topLevelItemCount()):
            header = self._tree.topLevelItem(i)
            for j in range(header.childCount()):
                child = header.child(j)
                if child.checkState(0) == QtCore.Qt.CheckState.Checked:
                    pid = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                    if pid:
                        ids.append(pid)
        return ids

    def _accept(self) -> None:
        ids = self._checked_ids() if self._plugins else []
        section = getattr(self._config, "plugins", None)
        if section is None:
            from stanza_im.core.storage import AttrDict
            section = AttrDict()
            self._config.plugins = section
        # Keep the flags of plugins that are currently missing from disk so a
        # temporarily absent plugin is not silently forgotten.
        for pid in list(dict(section)):
            section[pid] = False
        for pid in ids:
            section[pid] = True
        self.plugins_changed.emit(ids)
        self.accept()
