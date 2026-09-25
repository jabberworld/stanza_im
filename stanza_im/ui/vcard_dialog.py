"""vCard (XEP-0054) display and editing dialogs."""
from __future__ import annotations

import os

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import ACTIONS_DIR_16, find_icon


def _photo_pixmap(card: dict, size: int = 96) -> QtGui.QIcon:
    photo = card.get("photo")
    if isinstance(photo, str):
        import base64
        try:
            photo = base64.b64decode(photo)
        except Exception:
            photo = None
    if isinstance(photo, (bytes, bytearray)):
        pix = QtGui.QPixmap()
        if pix.loadFromData(bytes(photo)):
            return QtGui.QIcon(pix.scaled(
                size, size,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation))
    path = card.get("avatar_path") or ""
    if path:
        pix = QtGui.QPixmap(path)
        if not pix.isNull():
            return QtGui.QIcon(pix.scaled(
                size, size,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation))
    style = QtWidgets.QApplication.style()
    return style.standardIcon(
        QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView)


class VCardInfoDialog(QtWidgets.QDialog):
    """Read-only summary of a contact's vCard."""

    edit_requested = QtCore.pyqtSignal(str)   # jid
    refresh_requested = QtCore.pyqtSignal(str)  # jid

    def __init__(self, jid: str, card: dict, status: dict | None = None,
                 parent=None, show_edit: bool = False,
                 can_edit: bool = False):
        super().__init__(parent)
        self.setWindowTitle(tr("vcard_info_title"))
        self.setMinimumWidth(360)
        self._jid = card.get("jid") or jid
        # ``{field key: value QLabel}`` and its owning form, so a refresh
        # updates the text/visibility in place instead of rebuilding.
        self._field_labels: dict[str, QtWidgets.QLabel] = {}
        self._field_forms: dict[str, QtWidgets.QFormLayout] = {}

        layout = QtWidgets.QVBoxLayout(self)
        self._content = self._build_content(card, status or {})
        layout.addWidget(self._content, 1)

        btn = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close)
        btn.button(QtWidgets.QDialogButtonBox.StandardButton.Close).setText(
            tr("dialog_ok"))
        btn.rejected.connect(self.reject)
        btn.clicked.connect(self.accept)
        self._refresh_btn = btn.addButton(
            tr("vcard_refresh"),
            QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        self._refresh_btn.setIcon(QtGui.QIcon(
            os.path.join(ACTIONS_DIR_16, "reload.png")))
        self._refresh_btn.clicked.connect(
            lambda: self.refresh_requested.emit(self._jid))
        self._edit_btn = btn.addButton(
            tr("vcard_edit"), QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        self._edit_btn.setIcon(QtGui.QIcon(
            os.path.join(ACTIONS_DIR_16, "edit.png")))
        self._edit_btn.setVisible(bool(show_edit))
        self._edit_btn.setEnabled(bool(can_edit))
        self._edit_btn.clicked.connect(
            lambda: self.edit_requested.emit(self._jid))
        layout.addWidget(btn)

    def _build_content(self, card: dict,
                       status: dict) -> QtWidgets.QWidget:
        """Build the head + tabs block (rebuilt in place by update_card)."""
        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)

        head = QtWidgets.QHBoxLayout()
        pic = QtWidgets.QLabel()
        pic.setFixedSize(96, 96)
        pic.setPixmap(_photo_pixmap(card).pixmap(96, 96))
        self._photo_label = pic
        head.addWidget(pic, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        title = QtWidgets.QLabel(card.get("fn") or self._jid)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        self._title_label = title
        subtitle = QtWidgets.QLabel(card.get("jid") or self._jid)
        subtitle.setStyleSheet("color: gray;")
        self._subtitle_label = subtitle
        copy_btn = QtWidgets.QToolButton()
        copy_btn.setIcon(QtGui.QIcon(find_icon("copy.svg")))
        copy_btn.setIconSize(QtCore.QSize(16, 16))
        copy_btn.setAutoRaise(True)
        copy_btn.setToolTip(tr("vcard_copy_jid"))
        copy_btn.clicked.connect(self._copy_jid)
        jid_row = QtWidgets.QHBoxLayout()
        jid_row.addWidget(subtitle)
        jid_row.addWidget(copy_btn)
        jid_row.addStretch(1)
        head_col = QtWidgets.QVBoxLayout()
        head_col.addWidget(title)
        head_col.addLayout(jid_row)
        head_col.addStretch()
        head.addLayout(head_col, 1)
        layout.addLayout(head)

        tabs = QtWidgets.QTabWidget()
        self._tabs = tabs
        self._general_index = tabs.addTab(self._fields_page(card, (
            "fn", "nickname", "bday", "tel", "url", "email")),
            tr("vcard_tab_general"))
        tabs.addTab(self._fields_page(card, (
            "org", "orgunit", "title", "role")),
            tr("vcard_tab_work"))
        tabs.addTab(self._fields_page(card, (
            "street", "locality", "region", "pcode", "country")),
            tr("vcard_tab_address"))
        tabs.addTab(self._fields_page(card, ("description",)),
                    tr("vcard_tab_about"))
        status_data = dict(status or {})
        status_data.setdefault("jid", card.get("jid") or self._jid)
        status_data.setdefault("vcard_updated", card.get("fetched_at", ""))
        self._status_data = status_data
        self._status_index = tabs.addTab(self._fields_page(status_data, (
            "jid", "presence", "subscription", "status_message", "mood", "activity",
            "tune", "location", "resource",
            "status_updated", "vcard_updated", "client_time", "software",
            "software_version", "os", "ping"), hide_empty=True),
            tr("vcard_tab_status"))
        layout.addWidget(tabs)
        return content

    def update_card(self, card: dict, status: dict | None = None) -> None:
        """Refresh the open dialog **in place** (no rebuild, no tab jump)."""
        self._jid = card.get("jid") or self._jid
        # Header: avatar, title and address.
        self._photo_label.setPixmap(_photo_pixmap(card).pixmap(96, 96))
        self._title_label.setText(card.get("fn") or self._jid)
        self._subtitle_label.setText(card.get("jid") or self._jid)
        # General/work/address/about fields.
        for key in ("fn", "nickname", "bday", "tel", "url", "email",
                    "org", "orgunit", "title", "role",
                    "street", "locality", "region", "pcode", "country",
                    "description"):
            self._set_field(key, card.get(key))
        if status:
            self.update_status(status)

    def _copy_jid(self):
        from stanza_im.include.xmpp_uri import make_xmpp_uri
        QtWidgets.QApplication.clipboard().setText(make_xmpp_uri(self._jid))

    def update_status(self, values: dict):
        """Merge *values* and refresh the Status tab in place (no tab switch)."""
        self._status_data.update({key: value for key, value in values.items()
                                  if value not in (None, "")})
        for key in (
                "jid", "presence", "subscription", "status_message", "mood",
                "activity", "tune", "location", "resource", "status_updated",
                "vcard_updated", "client_time", "software",
                "software_version", "os", "ping"):
            self._set_field(key, self._status_data.get(key),
                            hide_empty=(key != "jid"
                                        and key != "vcard_updated"))

    def _set_field(self, key: str, value, hide_empty: bool = False) -> None:
        """Update a field label in place (toggle its row for the Status tab)."""
        label = self._field_labels.get(key)
        if label is None:
            return
        has_value = bool(value) and str(value) != "-"
        label.setText(str(value) if has_value else "-")
        form = self._field_forms.get(key)
        if form is not None:
            form.setRowVisible(label, has_value if hide_empty else True)

    def _fields_page(self, values: dict, keys: tuple[str, ...],
                     hide_empty: bool = False) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        for key in keys:
            label = QtWidgets.QLabel(str(values.get(key) or "-"))
            form.addRow(f"{tr(f'vcard_field_{key}')}:", label)
            self._field_labels[key] = label
            self._field_forms[key] = form
            has_value = bool(values.get(key))
            if (hide_empty and not has_value
                    and key not in ("jid", "vcard_updated")):
                form.setRowVisible(label, False)
        form.addItem(QtWidgets.QSpacerItem(
            1, 1, QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding))
        return page


class VCardEditDialog(QtWidgets.QDialog):
    """Edit your own vCard; ``collect()`` returns a :mod:`~stanza_im.include.
    vcard`-compatible dict."""

    def __init__(self, card: dict, parent=None,
                 title_key: str = "vcard_edit_title"):
        super().__init__(parent)
        self.setWindowTitle(tr(title_key))
        self.setMinimumSize(520, 430)
        self._card = card

        self._photo: bytes | None = (card.get("photo")
                                     if isinstance(card.get("photo"), bytes)
                                     else None)
        if isinstance(card.get("photo"), str):
            import base64
            try:
                self._photo = base64.b64decode(card["photo"])
            except Exception:
                self._photo = None

        layout = QtWidgets.QVBoxLayout(self)

        head = QtWidgets.QHBoxLayout()
        self._pic_label = QtWidgets.QLabel()
        self._pic_label.setFixedSize(96, 96)
        self._refresh_pic()
        head.addWidget(self._pic_label, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        pic_col = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel(card.get("fn") or card.get("jid") or "")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        self._title_label = title
        subtitle = QtWidgets.QLabel(card.get("jid") or "")
        subtitle.setStyleSheet("color: gray;")
        pic_col.addWidget(title)
        pic_col.addWidget(subtitle)
        pic_col.addSpacing(8)
        self._pick_btn = QtWidgets.QPushButton(tr("vcard_pick_photo"))
        self._pick_btn.clicked.connect(self._pick_photo)
        self._remove_btn = QtWidgets.QPushButton(tr("vcard_remove_photo"))
        self._remove_btn.clicked.connect(self._remove_photo)
        pic_col.addWidget(self._pick_btn)
        pic_col.addWidget(self._remove_btn)
        pic_col.addStretch()
        head.addLayout(pic_col)
        layout.addLayout(head)

        self._fields: dict[str, QtWidgets.QLineEdit] = {}
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._edit_fields_page((
            "fn", "nickname", "bday", "tel", "url", "email")),
            tr("vcard_tab_general"))
        tabs.addTab(self._edit_fields_page((
            "org", "orgunit", "title", "role")),
            tr("vcard_tab_work"))
        tabs.addTab(self._edit_fields_page((
            "street", "locality", "region", "pcode", "country")),
            tr("vcard_tab_address"))
        tabs.addTab(self._edit_fields_page(("description",), multiline=True),
                    tr("vcard_tab_about"))
        layout.addWidget(tabs)

        self._fields["fn"].textChanged.connect(
            lambda value: self._title_label.setText(value or self._card.get("jid", "")))

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
            tr("dialog_cancel"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save).setText(
            tr("vcard_publish"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _edit_fields_page(self, keys: tuple[str, ...],
                          multiline: bool = False) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        for key in keys:
            if multiline:
                edit = QtWidgets.QPlainTextEdit(self._card.get(key) or "")
                edit.setMinimumHeight(180)
            else:
                edit = QtWidgets.QLineEdit(self._card.get(key) or "")
            self._fields[key] = edit
            form.addRow(tr(f"vcard_field_{key}"), edit)
        form.addItem(QtWidgets.QSpacerItem(
            1, 1, QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding))
        return page

    def _refresh_pic(self):
        if self._photo:
            pix = QtGui.QPixmap()
            pix.loadFromData(self._photo)
            self._pic_label.setPixmap(pix.scaled(
                96, 96, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation))
        else:
            style = QtWidgets.QApplication.style()
            self._pic_label.setPixmap(
                style.standardIcon(
                    QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView)
                .pixmap(96, 96))

    def _pick_photo(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("vcard_pick_photo"), "",
            tr("vcard_photo_filter"))
        if not path:
            return
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            return
        pix = QtGui.QPixmap()
        if not pix.loadFromData(data):
            return
        self._photo = data
        self._refresh_pic()

    def _remove_photo(self):
        self._photo = None
        self._refresh_pic()

    def collect(self) -> dict:
        card = {}
        for key, edit in self._fields.items():
            value = (edit.toPlainText() if isinstance(edit, QtWidgets.QPlainTextEdit)
                     else edit.text())
            card[key] = value.strip()
        card["photo"] = self._photo
        card["jid"] = self._card.get("jid", "")
        return card
