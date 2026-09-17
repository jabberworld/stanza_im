"""Share dialog: pick roster contacts and/or joined conferences to forward to."""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr


class ShareDialog(QtWidgets.QDialog):
    """Pick multiple 1:1 contacts and/or conferences to share *content* with.

    *contacts* and *conferences* are ``(jid, name)`` pairs; the checked ones
    are returned by :meth:`selected_targets` as ``(jid, is_conference)``.
    """

    def __init__(self, contacts: list, conferences: list, content: str,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("share_dialog_title"))
        self.resize(460, 520)
        layout = QtWidgets.QVBoxLayout(self)

        preview = QtWidgets.QLabel(self._shorten(content), self)
        preview.setWordWrap(True)
        preview.setStyleSheet("color: gray;")
        layout.addWidget(preview)

        self._search = QtWidgets.QLineEdit(self)
        self._search.setPlaceholderText(tr("share_search"))
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setHeaderHidden(True)
        layout.addWidget(self._tree, stretch=1)

        self._contacts_root = self._make_root(tr("share_contacts"), contacts,
                                              False)
        self._conf_root = self._make_root(tr("share_conferences"),
                                          conferences, True)
        self._tree.expandAll()
        self._tree.itemChanged.connect(lambda *_: self._sync_send())

        buttons = QtWidgets.QDialogButtonBox(self)
        self._send = buttons.addButton(
            tr("share_send"),
            QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(
            tr("dialog_cancel"),
            QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        self._send.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._sync_send()

    def _make_root(self, title: str, entries: list,
                   is_conference: bool) -> QtWidgets.QTreeWidgetItem:
        root = QtWidgets.QTreeWidgetItem(self._tree, [title])
        root.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
        for jid, name in entries:
            item = QtWidgets.QTreeWidgetItem(root, [name or jid])
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole,
                         (jid, is_conference))
            item.setToolTip(0, jid)
        return root

    @staticmethod
    def _shorten(text: str, limit: int = 200) -> str:
        text = " ".join((text or "").split())
        return text[:limit] + ("…" if len(text) > limit else "")

    def _filter(self, text: str) -> None:
        query = text.strip().casefold()
        for root in (self._contacts_root, self._conf_root):
            any_visible = False
            for i in range(root.childCount()):
                child = root.child(i)
                data = child.data(0, QtCore.Qt.ItemDataRole.UserRole) or ("", )
                haystack = f"{child.text(0)} {data[0]}".casefold()
                hidden = bool(query) and query not in haystack
                child.setHidden(hidden)
                any_visible = any_visible or not hidden
            root.setHidden(not any_visible)

    def _sync_send(self) -> None:
        self._send.setEnabled(bool(self.selected_targets()))

    def selected_targets(self) -> list:
        """The checked ``(jid, is_conference)`` pairs."""
        selected = []
        for root in (self._contacts_root, self._conf_root):
            for i in range(root.childCount()):
                child = root.child(i)
                if child.checkState(0) == QtCore.Qt.CheckState.Checked:
                    data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                    if data:
                        selected.append(tuple(data))
        return selected
