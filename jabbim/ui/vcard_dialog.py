"""vCard (XEP-0054) display and editing dialogs."""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from jabbim.i18n import tr


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

    def __init__(self, jid: str, card: dict, status: dict | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("vcard_info_title"))
        self.setMinimumWidth(360)

        layout = QtWidgets.QVBoxLayout(self)

        head = QtWidgets.QHBoxLayout()
        pic = QtWidgets.QLabel()
        pic.setFixedSize(96, 96)
        pic.setPixmap(_photo_pixmap(card).pixmap(96, 96))
        head.addWidget(pic, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        title = QtWidgets.QLabel(card.get("fn") or jid)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        subtitle = QtWidgets.QLabel(card.get("jid") or jid)
        subtitle.setStyleSheet("color: gray;")
        head_col = QtWidgets.QVBoxLayout()
        head_col.addWidget(title)
        head_col.addWidget(subtitle)
        head_col.addStretch()
        head.addLayout(head_col, 1)
        layout.addLayout(head)

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._fields_page(card, (
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
        status_data.setdefault("jid", card.get("jid") or jid)
        status_data.setdefault("vcard_updated", card.get("fetched_at", ""))
        tabs.addTab(self._fields_page(status_data, (
            "jid", "presence", "status_message", "resource",
            "vcard_updated", "client_time")),
            tr("vcard_tab_status"))
        layout.addWidget(tabs)

        btn = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close)
        btn.rejected.connect(self.reject)
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

    @staticmethod
    def _fields_page(values: dict, keys: tuple[str, ...]):
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        for key in keys:
            form.addRow(tr(f"vcard_field_{key}"),
                        QtWidgets.QLabel(str(values.get(key) or "-")))
        form.addItem(QtWidgets.QSpacerItem(
            1, 1, QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding))
        return page


class VCardEditDialog(QtWidgets.QDialog):
    """Edit your own vCard; ``collect()`` returns a :mod:`~jabbim.include.
    vcard`-compatible dict."""

    def __init__(self, card: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("vcard_edit_title"))
        self.setMinimumWidth(380)

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
        head.addWidget(self._pic_label)

        pic_col = QtWidgets.QVBoxLayout()
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
        form = QtWidgets.QFormLayout()
        for key in ("fn", "nickname", "email", "url", "bday", "title",
                    "role", "org", "orgunit", "tel"):
            edit = QtWidgets.QLineEdit(card.get(key) or "")
            self._fields[key] = edit
            form.addRow(tr(f"vcard_field_{key}"), edit)
        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
        card = {key: edit.text().strip()
                for key, edit in self._fields.items()}
        card["photo"] = self._photo
        return card
