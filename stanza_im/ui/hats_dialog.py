"""XEP-0317 Hats: room-management tab and dialogs.

The ``HatsTab`` is embedded in the room-management dialog
(``ui/muc_config_dialog.py``); ``HatEditDialog`` / ``HatAssignDialog`` /
``HatUnassignDialog`` are the small modal dialogs used both there and from the
participant context menu (``MainWindow``).
"""
from __future__ import annotations

import asyncio
import re

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include import hats as hats_mod


def _hue_color(hue, saturation: float = 85.0,
               lightness: float = 42.0) -> str:
    return hats_mod.hue_to_color(hue, saturation, lightness)


class HatEditDialog(QtWidgets.QDialog):
    """Create/update a hat: a required title and an optional hue colour."""

    def __init__(self, title: str = "", hue=None,
                 title_key: str = "hats_create_title", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr(title_key))
        self.setMinimumWidth(360)
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)

        self._title = QtWidgets.QLineEdit(self)
        self._title.setPlaceholderText(tr("hats_title_placeholder"))
        form.addRow(tr("hats_field_title"), self._title)

        self._use_color = QtWidgets.QCheckBox(tr("hats_field_use_color"), self)
        self._use_color.setChecked(hue is not None)
        self._use_color.toggled.connect(self._on_color_toggle)
        form.addRow("", self._use_color)

        self._color = QtWidgets.QPushButton(self)
        self._color.setMinimumWidth(120)
        self._color.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._color.clicked.connect(self._pick_color)
        self._color_value = QtGui.QColor()
        form.addRow(tr("hats_field_color"), self._color)

        self._title.setText(title or "")
        if hue is not None:
            self._color_value = QtGui.QColor.fromHslF(
                (float(hue) % 360.0) / 360.0, 0.8, 0.5)
        self._refresh_swatch()
        self._on_color_toggle(self._use_color.isChecked())

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(tr("dialog_ok"))
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
                tr("dialog_cancel"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_color_toggle(self, checked: bool) -> None:
        self._color.setEnabled(checked)
        self._refresh_swatch()

    def _refresh_swatch(self) -> None:
        if not self._use_color.isChecked():
            self._color.setText(tr("hats_color_none"))
            self._color.setStyleSheet("")
            return
        name = self._color_value.name() if self._color_value.isValid() else "#888888"
        contrast = "#ffffff" if self._color_value.lightnessF() < 0.5 else "#000000"
        self._color.setText(name)
        self._color.setStyleSheet(
            f"QPushButton {{ background-color: {name}; color: {contrast}; "
            f"border: 1px solid #888; border-radius: 4px; }}")

    def _pick_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(self._color_value, self)
        if color.isValid():
            self._color_value = color
            self._use_color.setChecked(True)
            self._refresh_swatch()

    def _on_accept(self) -> None:
        if not self._title.text().strip():
            QtWidgets.QMessageBox.warning(
                self, tr("hats_create_title"), tr("hats_title_required"))
            return
        self.accept()

    def values(self) -> tuple[str, float | None]:
        title = self._title.text().strip()
        hue = None
        if self._use_color.isChecked() and self._color_value.isValid():
            hue_f = self._color_value.hueF()
            if hue_f >= 0:
                hue = hue_f * 360.0
        return title, hue


class HatUnassignDialog(QtWidgets.QDialog):
    """Pick one of a user's hats to remove (context-menu "Unassign")."""

    def __init__(self, hats: list[dict], nick: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("hats_unassign_title"))
        self.setMinimumWidth(360)
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(tr("hats_unassign_prompt", nick=nick))
        label.setWordWrap(True)
        layout.addWidget(label)
        self._list = QtWidgets.QListWidget(self)
        for hat in hats:
            item = QtWidgets.QListWidgetItem(hat.get("title") or hat.get("uri", ""))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, hat)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)
        layout.addWidget(self._list, 1)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(tr("dialog_ok"))
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
                tr("dialog_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def hat(self) -> dict:
        item = self._list.currentItem()
        return item.data(QtCore.Qt.ItemDataRole.UserRole) if item else {}


class HatAssignDialog(QtWidgets.QDialog):
    """Assign one hat to one or more present users or a manual JID."""

    def __init__(self, hats: list[dict], participants: list[dict],
                 preselect: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("hats_assign_title"))
        self.setMinimumSize(420, 400)
        preselect = {j.lower() for j in (preselect or []) if j}
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)

        self._hat = QtWidgets.QComboBox(self)
        for hat in hats:
            self._hat.addItem(hat.get("title") or hat.get("uri", ""),
                              hat.get("uri", ""))
        form.addRow(tr("hats_field_hat"), self._hat)

        self._users = QtWidgets.QListWidget(self)
        for person in participants or []:
            jid = str(person.get("jid") or "")
            nick = str(person.get("nick") or jid)
            item = QtWidgets.QListWidgetItem(
                f"{nick} ({jid})" if jid else tr("hats_jid_hidden", nick=nick))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, jid)
            flags = (QtCore.Qt.ItemFlag.ItemIsEnabled
                     | QtCore.Qt.ItemFlag.ItemIsSelectable
                     | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            if not jid:
                flags &= ~QtCore.Qt.ItemFlag.ItemIsEnabled
            item.setFlags(flags)
            item.setCheckState(
                QtCore.Qt.CheckState.Checked
                if jid and jid.lower() in preselect
                else QtCore.Qt.CheckState.Unchecked)
            self._users.addItem(item)
        layout.addWidget(QtWidgets.QLabel(tr("hats_assign_users")))
        layout.addWidget(self._users, 1)

        self._manual = QtWidgets.QLineEdit(self)
        self._manual.setPlaceholderText(tr("hats_manual_placeholder"))
        form2 = QtWidgets.QFormLayout()
        layout.addLayout(form2)
        form2.addRow(tr("hats_field_manual_jid"), self._manual)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self._ok = buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(tr("dialog_ok"))
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
                tr("dialog_cancel"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def hat_uri(self) -> str:
        return str(self._hat.currentData() or "")

    def jids(self) -> list[str]:
        out: list[str] = []
        for i in range(self._users.count()):
            item = self._users.item(i)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                jid = str(item.data(QtCore.Qt.ItemDataRole.UserRole) or "")
                if jid and jid not in out:
                    out.append(jid)
        for token in re.split(r"[\s,;]+", self._manual.text().strip()):
            if token and "@" in token and token not in out:
                out.append(token)
        return out

    def _on_accept(self) -> None:
        if not self.hat_uri():
            QtWidgets.QMessageBox.warning(
                self, tr("hats_assign_title"), tr("hats_no_hats"))
            return
        if not self.jids():
            QtWidgets.QMessageBox.warning(
                self, tr("hats_assign_title"), tr("hats_no_user"))
            return
        self.accept()


class HatsTab(QtWidgets.QWidget):
    """Room-management tab listing configured hats and their assignees."""

    def __init__(self, client, room: str, can_manage: bool = False, parent=None):
        super().__init__(parent)
        self._client = client
        self._room = room
        self._can_manage = can_manage
        self._hats: list[dict] = []
        self._assigned: list[dict] = []
        self._supported = True
        self._busy = False

        layout = QtWidgets.QHBoxLayout(self)
        left = QtWidgets.QVBoxLayout()
        layout.addLayout(left, 1)
        self._status = QtWidgets.QLabel(tr("hats_loading"))
        self._status.setWordWrap(True)
        left.addWidget(self._status)
        self._tree = QtWidgets.QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels([tr("hats_col_hat"), tr("hats_col_user")])
        self._tree.setColumnWidth(0, 240)
        self._tree.itemSelectionChanged.connect(self._update_buttons)
        left.addWidget(self._tree, 1)

        side = QtWidgets.QVBoxLayout()
        layout.addLayout(side)
        self._create_btn = self._side_button(side, "hats_create", self._on_create)
        self._edit_btn = self._side_button(side, "hats_edit", self._on_edit)
        self._assign_btn = self._side_button(side, "hats_assign", self._on_assign)
        self._unassign_btn = self._side_button(
            side, "hats_unassign", self._on_unassign)
        self._delete_btn = self._side_button(side, "hats_delete", self._on_delete)
        side.addStretch(1)

        self._update_buttons()
        self._start_task(self._reload())

    def _side_button(self, layout, key: str, handler) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton(tr(key))
        button.clicked.connect(handler)
        layout.addWidget(button)
        return button

    def _start_task(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        return loop.create_task(coro)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_buttons()

    async def _reload(self) -> None:
        try:
            self._supported = await self._client.room_supports_hats(self._room)
        except Exception:
            self._supported = False
        if not self._supported:
            self._hats = []
            self._assigned = []
            self._tree.clear()
            self._status.setText(tr("hats_unsupported"))
            self._update_buttons()
            return
        try:
            self._hats = await self._client.hats_list(self._room)
            self._assigned = await self._client.hats_list_assigned(self._room)
        except Exception as exc:
            self._status.setText(tr("hats_error", error=str(exc)))
            self._update_buttons()
            return
        if not self._assigned:
            self._assigned = self._presence_assignments()
        self._status.setText(tr("hats_loaded", hats=len(self._hats),
                                users=len(self._assigned)))
        self._rebuild_tree()

    def _presence_assignments(self) -> list[dict]:
        """Fallback: derive assignments from the occupants' presence hats."""
        groupchat = getattr(self._client, "groupchats", {}).get(self._room)
        if groupchat is None:
            return []
        out = []
        for nick, user in groupchat.users.items():
            jid = str(user.get("real_jid") or "")
            for hat in user.get("hats") or []:
                out.append({"uri": hat.get("uri", ""),
                            "title": hat.get("title", ""),
                            "hue": hat.get("hue"),
                            "jid": jid, "nick": nick})
        return out

    def _user_label(self, jid: str) -> str:
        groupchat = getattr(self._client, "groupchats", {}).get(self._room)
        if groupchat is not None and jid:
            for nick, user in groupchat.users.items():
                if str(user.get("real_jid") or "") == jid:
                    return f"{nick} ({jid})"
        return jid

    def _rebuild_tree(self) -> None:
        selected = self._current_ref()
        self._tree.clear()
        by_uri: dict[str, list[dict]] = {}
        for item in self._assigned:
            by_uri.setdefault(item.get("uri") or "", []).append(item)
        if not self._hats and self._assigned:
            seen: dict[str, dict] = {}
            for item in self._assigned:
                uri = item.get("uri") or ""
                if uri and uri not in seen:
                    seen[uri] = {"uri": uri,
                                 "title": item.get("title") or uri,
                                 "hue": item.get("hue")}
            self._hats = list(seen.values())
        for hat in sorted(self._hats, key=lambda h: (h.get("title") or "").lower()):
            uri = hat.get("uri") or ""
            users = by_uri.get(uri, [])
            parent = QtWidgets.QTreeWidgetItem(
                [f"{hat.get('title') or uri} ({len(users)})", ""])
            parent.setData(0, QtCore.Qt.ItemDataRole.UserRole,
                           {"kind": "hat", "hat": hat})
            color = _hue_color(hat.get("hue"))
            if color:
                parent.setForeground(0, QtGui.QBrush(QtGui.QColor(color)))
            self._tree.addTopLevelItem(parent)
            for user in users:
                jid = user.get("jid") or ""
                child = QtWidgets.QTreeWidgetItem(["", self._user_label(jid)])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole,
                              {"kind": "user", "hat": hat, "jid": jid})
                parent.addChild(child)
            parent.setExpanded(True)
            if selected and selected.get("kind") == "hat" \
                    and (selected.get("hat") or {}).get("uri") == uri:
                self._tree.setCurrentItem(parent)
        self._update_buttons()

    def _current_ref(self) -> dict:
        item = self._tree.currentItem()
        return item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item else {}

    def _update_buttons(self) -> None:
        ref = self._current_ref()
        kind = ref.get("kind")
        base = self._supported and self._can_manage and not self._busy
        self._create_btn.setEnabled(base)
        self._edit_btn.setEnabled(base and kind == "hat")
        self._delete_btn.setEnabled(base and kind == "hat")
        self._assign_btn.setEnabled(base and bool(self._hats))
        self._unassign_btn.setEnabled(base and kind == "user")

    # ── operations ────────────────────────────────────────────────

    def _run(self, coro) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._start_task(self._wrap(coro))

    async def _wrap(self, coro) -> None:
        try:
            await coro
        except Exception as exc:
            self._status.setText(tr("hats_error", error=str(exc)))
        await self._reload()
        self._set_busy(False)

    def _on_create(self) -> None:
        if not (self._can_manage and self._supported):
            return
        dialog = HatEditDialog(title_key="hats_create_title", parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        title, hue = dialog.values()
        self._run(self._client.hats_create(self._room, title, hue=hue))

    def _on_edit(self) -> None:
        ref = self._current_ref()
        hat = ref.get("hat") if ref.get("kind") == "hat" else None
        if not hat:
            return
        dialog = HatEditDialog(title=hat.get("title") or "",
                               hue=hat.get("hue"),
                               title_key="hats_edit_title", parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        title, hue = dialog.values()
        self._run(self._client.hats_update(
            self._room, hat.get("uri") or "", title, hue=hue))

    def _on_delete(self) -> None:
        ref = self._current_ref()
        hat = ref.get("hat") if ref.get("kind") == "hat" else None
        if not hat:
            return
        answer = QtWidgets.QMessageBox.question(
            self, tr("hats_delete_title"),
            tr("hats_confirm_delete", title=hat.get("title") or ""))
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._run(self._client.hats_destroy(self._room, hat.get("uri") or ""))

    def _on_assign(self) -> None:
        if not (self._can_manage and self._supported and self._hats):
            return
        dialog = HatAssignDialog(self._hats, self._participants(), parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self._run(self._assign_many(dialog.hat_uri(), dialog.jids()))

    async def _assign_many(self, uri: str, jids: list[str]) -> None:
        for jid in jids:
            await self._client.hats_assign(self._room, jid, uri)

    def open_assign(self, preselect: list[str]) -> None:
        """Open the assign dialog with *preselect* JIDs ticked."""
        if not (self._can_manage and self._supported):
            return
        dialog = HatAssignDialog(self._hats, self._participants(),
                                 preselect=preselect, parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self._run(self._assign_many(dialog.hat_uri(), dialog.jids()))

    def _on_unassign(self) -> None:
        ref = self._current_ref()
        if ref.get("kind") != "user":
            return
        hat = ref.get("hat") or {}
        jid = ref.get("jid") or ""
        if not jid:
            QtWidgets.QMessageBox.warning(
                self, tr("hats_unassign_title"), tr("hats_no_real_jid"))
            return
        answer = QtWidgets.QMessageBox.question(
            self, tr("hats_unassign_title"),
            tr("hats_confirm_unassign", title=hat.get("title") or "",
               user=self._user_label(jid)))
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._run(self._client.hats_unassign(
            self._room, jid, hat.get("uri") or ""))

    def _participants(self) -> list[dict]:
        groupchat = getattr(self._client, "groupchats", {}).get(self._room)
        if groupchat is None:
            return []
        out = []
        for nick, user in groupchat.users.items():
            out.append({"nick": nick, "jid": str(user.get("real_jid") or "")})
        out.sort(key=lambda p: p["nick"].lower())
        return out
