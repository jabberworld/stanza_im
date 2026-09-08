"""XEP-0055 legacy & form-based search dialog."""
from __future__ import annotations

import asyncio
import os

from PyQt6 import QtCore, QtGui, QtWidgets

from jabbim.i18n import tr
from jabbim.include.constants import ACTIONS_DIR_16, CATEGORIES_DIR_16, \
    STATUS_DIR_32
from jabbim.ui.data_form_widget import DataFormWidget, LegacyFormWidget


class SearchDialog(QtWidgets.QDialog):
    """Show a service search form, run the query and list the results."""

    vcard_requested = QtCore.pyqtSignal(str)

    def __init__(self, client, jid: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._jid = jid
        self._form = None
        self._form_widget: DataFormWidget | None = None
        self._legacy_widget: LegacyFormWidget | None = None
        self.setWindowTitle(tr("search_title"))
        self.resize(520, 420)
        layout = QtWidgets.QVBoxLayout(self)
        self._status = QtWidgets.QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._body = QtWidgets.QVBoxLayout()
        layout.addLayout(self._body, 0)
        self._results = QtWidgets.QTreeWidget()
        self._results.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._results.customContextMenuRequested.connect(self._context)
        self._results.currentItemChanged.connect(self._on_result_selected)
        self._results.hide()
        layout.addWidget(self._results, 1)
        buttons = QtWidgets.QHBoxLayout()
        self._buttons = buttons
        self._btn_search = QtWidgets.QPushButton(tr("search_apply"))
        self._btn_search.clicked.connect(self._on_search)
        self._btn_search.setEnabled(False)
        self._btn_row_vcard = self._new_row_action(tr("service_vcard"),
                                                   "v-card.png")
        self._btn_row_vcard.clicked.connect(self._row_vcard)
        self._btn_row_add = self._new_row_action(tr("service_add_roster"),
                                                 "add-user.png")
        self._btn_row_add.clicked.connect(self._row_add)
        self._btn_row_vcard.hide()
        self._btn_row_add.hide()
        buttons.addWidget(self._btn_row_vcard)
        buttons.addWidget(self._btn_row_add)
        buttons.addStretch()
        close = QtWidgets.QPushButton(tr("dialog_close"))
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        asyncio.get_event_loop().create_task(self._load())

    # ── Building ───────────────────────────────────────────────────────

    @staticmethod
    def _icon(filename: str) -> QtGui.QIcon:
        for directory in (ACTIONS_DIR_16, CATEGORIES_DIR_16, STATUS_DIR_32):
            pix = QtGui.QPixmap(os.path.join(directory, filename))
            if not pix.isNull():
                return QtGui.QIcon(pix)
        return QtGui.QIcon()

    def _new_row_action(self, text: str, icon: str) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setText(text)
        button.setIcon(self._icon(icon))
        button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setEnabled(False)
        return button

    async def _load(self) -> None:
        try:
            info = await self._client.get_search_form(self._jid)
        except Exception as exc:
            self._status.setText(tr("search_error", error=str(exc)))
            return
        form = info.get("form")
        fields = info.get("fields")
        attached = False
        field_edit = None
        if form is not None:
            self._form = form
            self._form_widget = DataFormWidget(form)
            self._body.addWidget(self._form_widget)
            attached = self._form_widget.attach_button(self._btn_search)
            field_edit = self._form_widget.first_edit()
        elif fields:
            self._legacy_widget = LegacyFormWidget(fields)
            self._body.addWidget(self._legacy_widget)
            attached = self._legacy_widget.attach_button(self._btn_search)
            field_edit = self._legacy_widget.first_edit()
        else:
            self._status.setText(tr("search_no_form"))
        if not attached:
            self._buttons.insertWidget(0, self._btn_search)
        self._btn_search.setEnabled(form is not None or fields is not None)
        if self._btn_search.isEnabled():
            self._btn_search.setDefault(True)
            if field_edit is not None:
                field_edit.returnPressed.connect(self._on_search)
                field_edit.setFocus()
            else:
                self._btn_search.setFocus()

    def _on_search(self) -> None:
        asyncio.get_event_loop().create_task(self._run_search())

    async def _run_search(self) -> None:
        if self._form is not None:
            assert self._form_widget is not None
            error = self._form_widget.validate()
            if error:
                self._status.setText(error)
                return
            self._form_widget.apply_to_form()
            values = None
        elif self._legacy_widget is not None:
            values = self._legacy_widget.values()
        else:
            return
        self._btn_search.setEnabled(False)
        try:
            data = await self._client.submit_search(self._jid,
                                                    form=self._form,
                                                    values=values)
            self._show_rows(data["rows"], data["columns"])
        except Exception as exc:
            self._status.setText(tr("search_error", error=str(exc)))
        finally:
            self._btn_search.setEnabled(True)

    # ── Results table ──────────────────────────────────────────────────

    def _show_rows(self, rows: list[dict],
                   columns: list[tuple[str, str]]) -> None:
        self._results.clear()
        if not rows:
            self._status.setText(tr("search_none"))
            self._results.hide()
            self._btn_row_vcard.hide()
            self._btn_row_add.hide()
            self._btn_row_vcard.setEnabled(False)
            self._btn_row_add.setEnabled(False)
            return
        labels = []
        for var, label in columns:
            if var == "jid":
                label = tr("search_result_jid")
            elif var == "name":
                label = tr("search_result_name")
            labels.append(label)
        self._results.setColumnCount(len(columns))
        self._results.setHeaderLabels(labels)
        for row in rows:
            values = [str(row.get(var, "")) for var, _label in columns]
            item = QtWidgets.QTreeWidgetItem(values)
            for index, value in enumerate(values):
                item.setToolTip(index, value)
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole,
                         row.get("jid") or "")
            self._results.addTopLevelItem(item)
        for index, (var, _label) in enumerate(columns):
            if var == "jid":
                width = max(240, self._results.sizeHintForColumn(index))
                self._results.setColumnWidth(index, width)
            else:
                self._results.resizeColumnToContents(index)
        item = self._results.topLevelItem(0)
        if item is not None:
            self._results.setCurrentItem(item)
        self._status.clear()
        self._btn_row_vcard.show()
        self._btn_row_add.show()
        self._results.show()

    def _on_result_selected(self, current, _previous) -> None:
        jid = self._selected_jid(current)
        self._btn_row_vcard.setEnabled(bool(jid))
        self._btn_row_add.setEnabled(bool(jid))

    @staticmethod
    def _selected_jid(item) -> str:
        if item is None:
            return ""
        return str(item.data(0, QtCore.Qt.ItemDataRole.UserRole) or "")

    def _row_vcard(self) -> None:
        jid = self._selected_jid(self._results.currentItem())
        if jid:
            self.vcard_requested.emit(jid)

    def _row_add(self) -> None:
        jid = self._selected_jid(self._results.currentItem())
        if not jid:
            return
        answer = QtWidgets.QMessageBox.question(
            self, tr("service_add_roster"),
            tr("service_add_confirm", jid=jid))
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._client.add_contact(jid, request_subscription=True)
        self._status.setText(tr("service_added", jid=jid))

    def _context(self, pos: QtCore.QPoint) -> None:
        item = self._results.itemAt(pos)
        if item is None:
            return
        jid = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        menu = QtWidgets.QMenu(self)

        def defer(callback):
            menu.close()
            QtCore.QTimer.singleShot(0, callback)

        self._results.setCurrentItem(item)
        menu.addAction(self._icon("v-card.png"), tr("service_vcard"),
                       lambda checked=False: defer(self._row_vcard))
        menu.addAction(self._icon("add-user.png"), tr("service_add_roster"),
                       lambda checked=False: defer(self._row_add))
        menu.addSeparator()
        menu.addAction(tr("conference_copy_jid"),
                       lambda: QtWidgets.QApplication.clipboard().setText(jid))
        menu.exec(self._results.viewport().mapToGlobal(pos))