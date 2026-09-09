"""Tabbed About dialog for Stanza IM."""
from __future__ import annotations

import os
import platform

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.include.constants import APP_NAME, LOGO_PNG, PROJECT_ROOT, VERSION
from stanza_im.i18n import tr


class AboutDialog(QtWidgets.QDialog):
    """Display application and dependency information."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("about_title"))
        self.setMinimumSize(520, 380)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        logo = QtWidgets.QLabel()
        pixmap = QtGui.QPixmap(LOGO_PNG)
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(
                72, 72, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation))
        header.addWidget(logo)
        title = QtWidgets.QLabel(f"<b>{APP_NAME}</b><br><span style='font-size: 16pt'>{VERSION}</span>")
        title.setTextFormat(QtCore.Qt.TextFormat.RichText)
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._version_page(), tr("about_tab_version"))
        tabs.addTab(self._text_page("LICENSE", "about_license_unavailable"),
                    tr("about_tab_license"))
        tabs.addTab(self._text_page("AUTHORS.md", "about_authors_unavailable"),
                    tr("about_tab_authors"))
        layout.addWidget(tabs)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Close).setText(
            tr("dialog_ok"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _version_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        try:
            import slixmpp
            slixmpp_version = getattr(slixmpp, "__version__", "unknown")
        except ImportError:
            slixmpp_version = "unknown"
        values = (
            ("about_component_app", f"{APP_NAME} {VERSION}"),
            ("about_component_pyqt", QtCore.PYQT_VERSION_STR),
            ("about_component_qt", QtCore.QT_VERSION_STR),
            ("about_component_python", platform.python_version()),
            ("about_component_slixmpp", str(slixmpp_version)),
        )
        for label_key, value in values:
            form.addRow(tr(label_key) + ":", QtWidgets.QLabel(value))
        return page

    def _text_page(self, filename: str, fallback_key: str) -> QtWidgets.QWidget:
        editor = QtWidgets.QPlainTextEdit()
        editor.setReadOnly(True)
        path = os.path.join(PROJECT_ROOT, filename)
        try:
            with open(path, encoding="utf-8") as source:
                content = source.read()
        except OSError:
            content = tr(fallback_key)
        editor.setPlainText(content)
        return editor
