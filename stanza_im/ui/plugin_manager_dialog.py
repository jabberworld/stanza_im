"""Plugin manager.

``PluginManagerWidget`` is the reusable core: a tree of categories → plugins
with a checkbox per plugin (tri-state per category) plus a «Настроить» button
enabled only for a selected plugin that announces settings.  ``PluginManagerDialog``
wraps it with Ok/Cancel for the Actions menu; the Preferences page embeds the
widget directly.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon
from stanza_im.plugins import Plugin, discover, stored_enabled_ids


class PluginManagerWidget(QtWidgets.QWidget):
    """Inspectable enable/disable tree with a per-plugin settings button."""

    def __init__(self, config, parent=None, plugins: list[Plugin] | None = None):
        super().__init__(parent)
        self._config = config
        self._plugins: list[Plugin] = list(plugins) if plugins is not None \
            else discover()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not self._plugins:
            label = QtWidgets.QLabel(tr("prefs_no_plugins"))
            label.setWordWrap(True)
            layout.addWidget(label)
            self._tree = None
            return

        self._tree = QtWidgets.QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.itemSelectionChanged.connect(self._update_configure_enabled)
        layout.addWidget(self._tree, 1)
        self._build_tree()

        self._configure_btn = QtWidgets.QPushButton(tr("plugin_configure"))
        self._configure_btn.clicked.connect(self._on_configure)
        layout.addWidget(self._configure_btn)
        self._update_configure_enabled()

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
                    item.setToolTip(0, tr(plugin.description))
                item.setFlags(item.flags()
                              | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    0, QtCore.Qt.CheckState.Checked if plugin.id in enabled
                    else QtCore.Qt.CheckState.Unchecked)
                item.setData(0, QtCore.Qt.ItemDataRole.UserRole, plugin.id)
                header.addChild(item)

    def rebuild(self) -> None:
        """Re-read the plugins and their enabled state (e.g. after Apply)."""
        if self._tree is None:
            return
        self._tree.clear()
        self._build_tree()

    def checked_ids(self) -> list[str]:
        """Return the ids of the checked plugins."""
        if self._tree is None:
            return []
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

    def apply_checked(self) -> list[str]:
        """Write the checkbox state to ``config.plugins``; return the ids."""
        ids = self.checked_ids()
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
        return ids

    # ── Configure ─────────────────────────────────────────────────

    def _selected_plugin(self) -> Plugin | None:
        if self._tree is None:
            return None
        items = self._tree.selectedItems()
        for item in items:
            pid = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if pid:
                return next((p for p in self._plugins if p.id == pid), None)
        return None

    def _update_configure_enabled(self) -> None:
        plugin = self._selected_plugin()
        button = getattr(self, "_configure_btn", None)
        if button is not None:
            button.setEnabled(plugin is not None and plugin.has_settings)

    def _on_configure(self) -> None:
        plugin = self._selected_plugin()
        if plugin is None or not plugin.has_settings:
            return
        if plugin.open_settings(self._config, self):
            # A plugin persists its own settings in ``config.plugin_settings``
            # via the passed config; flush them so they survive immediately.
            self._config.save()


class PluginManagerDialog(QtWidgets.QDialog):
    """Enable/disable the installed plugins (Actions → Plugins)."""

    plugins_changed = QtCore.pyqtSignal(list)  # new list of enabled plugin ids

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle(tr("plugin_manager_title"))
        self.setMinimumSize(460, 380)

        layout = QtWidgets.QVBoxLayout(self)
        self._widget = PluginManagerWidget(config, self)
        layout.addWidget(self._widget, 1)

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

    def _accept(self) -> None:
        ids = self._widget.apply_checked()
        self.plugins_changed.emit(ids)
        self.accept()
