"""Conference join and conference browser dialogs."""
from __future__ import annotations

import asyncio

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import CATEGORIES_DIR_16


class ConferenceBrowserDialog(QtWidgets.QDialog):
    room_selected = QtCore.pyqtSignal(str)
    vcard_requested = QtCore.pyqtSignal(str)

    def __init__(self, client, server: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._rooms: list[dict] = []
        self.setWindowTitle(tr("conference_browser_title"))
        self.resize(620, 420)
        layout = QtWidgets.QVBoxLayout(self)
        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText(tr("conference_search"))
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)
        self._table = QtWidgets.QTreeWidget()
        self._table.setHeaderLabels([tr("conference_name"), tr("conference_jid")])
        self._table.setColumnWidth(0, 360)
        self._table.itemDoubleClicked.connect(lambda *_: self._accept_selected())
        self._table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context)
        layout.addWidget(self._table)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if server.strip():
            asyncio.get_event_loop().create_task(self._load(server))
        else:
            self._filter("")

    async def _load(self, server: str):
        try:
            self._rooms = await self._client.list_conference_rooms(server)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.windowTitle(), str(exc))
            self._rooms = []
        self._filter(self._search.text())

    def _filter(self, text: str):
        query = text.casefold()
        self._table.clear()
        visible = 0
        for room in self._rooms:
            details = []
            if room.get("occupants"):
                details.append(str(room["occupants"]))
            if room.get("private"):
                details.append(tr("conference_private"))
            label = room["name"] + (" (" + ", ".join(details) + ")" if details else "")
            localpart = room["jid"].split("@", 1)[0]
            if query not in room["name"].casefold() and query not in localpart.casefold():
                continue
            visible += 1
            item = QtWidgets.QTreeWidgetItem([label, room["jid"]])
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, room["jid"])
            self._table.addTopLevelItem(item)
            for user in room.get("users", []):
                child = QtWidgets.QTreeWidgetItem([str(user), ""])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, room["jid"])
                item.addChild(child)
        self.setWindowTitle(f"{tr('conference_browser_title')} "
                            f"({tr('conference_found', n=visible)})")

    def _accept_selected(self):
        item = self._table.currentItem()
        if item:
            jid = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            self.room_selected.emit(jid.split("@", 1)[0])
            self.accept()

    def _context(self, pos):
        item = self._table.itemAt(pos)
        if not item:
            return
        jid = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or item.text(1)
        menu = QtWidgets.QMenu(self)
        menu.addAction(
            tr("conference_vcard"),
            lambda: (menu.close(), QtCore.QTimer.singleShot(
                0, lambda: self.vcard_requested.emit(jid))))
        menu.addAction(tr("conference_copy_jid"),
                       lambda: QtWidgets.QApplication.clipboard().setText(jid))
        menu.exec(self._table.viewport().mapToGlobal(pos))


class JoinConferenceDialog(QtWidgets.QDialog):
    vcard_requested = QtCore.pyqtSignal(str)
    def __init__(self, client, servers: list[str], bookmarks: list[dict],
                 parent=None, room: str = ""):
        super().__init__(parent)
        self._client = client
        self._bookmarks = bookmarks
        self._server_values = list(dict.fromkeys(servers))
        self.setWindowTitle(tr("conference_join_title"))
        self.setMinimumWidth(500)
        layout = QtWidgets.QVBoxLayout(self)
        head = QtWidgets.QHBoxLayout()
        icon = QtWidgets.QLabel()
        pix = QtGui.QPixmap(f"{CATEGORIES_DIR_16}/muc.png")
        if not pix.isNull():
            icon.setPixmap(pix.scaled(48, 48))
        head.addWidget(icon)
        head.addWidget(QtWidgets.QLabel(tr("conference_explanation")))
        head.addStretch()
        layout.addLayout(head)
        form = QtWidgets.QFormLayout()
        self._nick = QtWidgets.QLineEdit(client.jid_str.split("@", 1)[0])
        self._room = QtWidgets.QLineEdit(room)
        self._server = QtWidgets.QComboBox(); self._server.setEditable(True)
        self._server.addItems(self._server_values)
        self._password = QtWidgets.QLineEdit(); self._password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        form.addRow(tr("conference_nick"), self._nick)
        form.addRow(tr("conference_room"), self._room)
        form.addRow(tr("conference_server"), self._server)
        form.addRow(tr("conference_password"), self._password)
        layout.addWidget(QtWidgets.QLabel(tr("conference_join_title")))
        layout.addLayout(form)
        layout.addWidget(QtWidgets.QLabel(tr("conference_bookmarks")))
        self._save_bookmark = QtWidgets.QCheckBox(tr("conference_save_bookmark"))
        self._bookmark_name = QtWidgets.QLineEdit()
        self._auto_join = QtWidgets.QCheckBox(tr("conference_autojoin"))
        for widget in (self._bookmark_name, self._auto_join):
            widget.setEnabled(False)
        self._save_bookmark.toggled.connect(self._bookmark_name.setEnabled)
        self._save_bookmark.toggled.connect(self._auto_join.setEnabled)
        layout.addWidget(self._save_bookmark); layout.addWidget(self._bookmark_name); layout.addWidget(self._auto_join)
        buttons = QtWidgets.QDialogButtonBox()
        join = buttons.addButton(tr("conference_join"), QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = buttons.addButton(tr("dialog_cancel"), QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        browser = buttons.addButton(tr("conference_browser"), QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        join.clicked.connect(self._validate); cancel.clicked.connect(self.reject); browser.clicked.connect(self._browser)
        layout.addWidget(buttons)

    def _validate(self):
        if not self._room.text().strip() or not self._nick.text().strip():
            return
        self.accept()

    def _browser(self):
        server = self._server.currentText().strip()
        if not server:
            return
        dlg = ConferenceBrowserDialog(self._client, server, self)
        dlg.room_selected.connect(self._room.setText)
        dlg.vcard_requested.connect(self.vcard_requested)
        self._browser_dialog = dlg
        dlg.open()

    def collect(self):
        return {"room": self._room.text().strip(), "nick": self._nick.text().strip(),
                "server": self._server.currentText().strip(), "password": self._password.text(),
                "save": self._save_bookmark.isChecked(),
                "name": self._bookmark_name.text().strip(), "autojoin": self._auto_join.isChecked()}
