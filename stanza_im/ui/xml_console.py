"""Raw XML console (Actions → XML-консоль).

Shows every stanza crossing the stream, coloured by direction and kind, with
live filters (messages / presences / iq / sm / other) and a bare-JID filter.
The window is non-modal and fed by ``JabberClient.set_xml_console_hook``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable
from xml.dom import minidom
from xml.etree import ElementTree as ET

from PyQt6 import QtGui, QtWidgets

from stanza_im.i18n import tr

_CLIENT_NS = "jabber:client"
_SM_NS_PREFIX = "urn:xmpp:sm:"

KINDS = ("message", "presence", "iq", "sm", "other")

# (kind, incoming) -> foreground colour.  Incoming: message red, presence
# orange, iq turquoise, sm blue; outgoing: message yellow, presence green,
# iq light blue, sm purple.  "Other" is neutral grey in both directions.
COLORS = {
    ("message", True): "#ff5c5c",
    ("presence", True): "#ffa64d",
    ("iq", True): "#00ced1",
    ("sm", True): "#4d8bff",
    ("other", True): "#9aa0a6",
    ("message", False): "#ffd93b",
    ("presence", False): "#4cd964",
    ("iq", False): "#4fc3f7",
    ("sm", False): "#c07cff",
    ("other", False): "#9aa0a6",
}

_MAX_ENTRIES = 5000


def bare_jid(value: str) -> str:
    """Lower-case the JID without its resource (empty string stays empty)."""
    return (value or "").split("/", 1)[0].lower()


def _split_tag(tag: str) -> tuple[str, str]:
    """Split an ElementTree tag into ``(namespace, localname)``."""
    if tag.startswith("{"):
        namespace, local = tag[1:].split("}", 1)
        return namespace, local
    return "", tag


def classify(xml_text: str) -> tuple[str, str, str] | None:
    """Return ``(kind, from, to)`` for a raw XML payload.

    ``None`` means the payload is pure whitespace (keep-alive) and should be
    dropped.  Stream headers/footers and any other unparseable payload fall
    into the ``other`` category.

    The match is namespace-agnostic for the client stanzas: slixmpp omits the
    default ``jabber:client`` namespace from top-level stanzas, so a bare
    ``<message>`` and ``<message xmlns="jabber:client">`` must classify alike.
    """
    text = (xml_text or "").strip()
    if not text:
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ("other", "", "")
    namespace, local = _split_tag(root.tag)
    if local in ("message", "presence", "iq") and namespace in ("", _CLIENT_NS):
        kind = local
    elif namespace.startswith(_SM_NS_PREFIX):
        kind = "sm"
    else:
        kind = "other"
    return (kind, root.get("from", "") or "", root.get("to", "") or "")


def format_xml(xml_text: str) -> str:
    """Indent a stanza's XML for readability.

    Nested elements get two-space indents; an element whose content is only
    text (e.g. ``<body>hi</body>``) stays on one line.  Payloads that are not
    well-formed standalone XML (stream footer, partial data) are returned
    unchanged.
    """
    text = (xml_text or "").strip()
    if not text:
        return text
    try:
        pretty = minidom.parseString(text).toprettyxml(indent="  ")
    except Exception:
        return text
    lines = [line for line in pretty.splitlines() if line.strip()]
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    return "\n".join(lines)


@dataclass
class Entry:
    incoming: bool
    kind: str
    xml: str
    from_: str
    to: str
    ts: float


class XmlInputDialog(QtWidgets.QDialog):
    """Multiline editor for manually sending XML."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("xml_console_input_title"))
        self.resize(520, 320)
        layout = QtWidgets.QVBoxLayout(self)

        self._edit = QtWidgets.QPlainTextEdit(self)
        self._edit.setFont(self._fixed_font())
        layout.addWidget(self._edit)

        buttons = QtWidgets.QDialogButtonBox(self)
        buttons.addButton(
            tr("xml_console_send"), QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(
            tr("xml_console_cancel"), QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _fixed_font() -> QtGui.QFont:
        return QtGui.QFontDatabase.systemFont(
            QtGui.QFontDatabase.SystemFont.FixedFont)

    def text(self) -> str:
        return self._edit.toPlainText()


class XmlConsoleDialog(QtWidgets.QDialog):
    """Non-modal window showing raw XML with live filters."""

    def __init__(self, get_client: Callable[[], object | None], parent=None):
        super().__init__(parent)
        self._get_client = get_client
        self._buffer: list[Entry] = []
        self._attached_client = None

        self.setWindowTitle(tr("xml_console_title"))
        self.resize(860, 620)
        self._build_ui()

    # ── UI construction ─────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        self._output = QtWidgets.QPlainTextEdit(self)
        self._output.setReadOnly(True)
        self._output.setFont(QtGui.QFontDatabase.systemFont(
            QtGui.QFontDatabase.SystemFont.FixedFont))
        self._output.setStyleSheet(
            "QPlainTextEdit { background-color: #1e1e1e; color: #d0d0d0; }")
        self._output.setLineWrapMode(
            QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._output, 1)

        filters = QtWidgets.QGroupBox(tr("xml_console_filter"), self)
        row = QtWidgets.QHBoxLayout(filters)
        self._kind_boxes: dict[str, QtWidgets.QCheckBox] = {}
        for kind, key in (("message", "xml_console_messages"),
                          ("presence", "xml_console_presences"),
                          ("iq", "xml_console_iq"),
                          ("sm", "xml_console_sm"),
                          ("other", "xml_console_other")):
            box = QtWidgets.QCheckBox(tr(key), filters)
            box.setChecked(True)
            box.toggled.connect(self._rerender)
            self._kind_boxes[kind] = box
            row.addWidget(box)
        row.addStretch(1)
        row.addWidget(QtWidgets.QLabel(tr("xml_console_jid"), filters))
        self._jid_edit = QtWidgets.QLineEdit(filters)
        self._jid_edit.setMinimumWidth(220)
        self._jid_edit.textChanged.connect(self._rerender)
        row.addWidget(self._jid_edit)
        layout.addWidget(filters)

        bottom = QtWidgets.QHBoxLayout()
        self._enable = QtWidgets.QCheckBox(tr("xml_console_enable"), self)
        self._enable.setChecked(False)
        self._enable.toggled.connect(self._on_enable_toggled)
        bottom.addWidget(self._enable)
        bottom.addStretch(1)

        export = QtWidgets.QPushButton(tr("xml_console_export"), self)
        export.clicked.connect(self._on_export)
        clear = QtWidgets.QPushButton(tr("xml_console_clear"), self)
        clear.clicked.connect(self._on_clear)
        send = QtWidgets.QPushButton(tr("xml_console_input"), self)
        send.clicked.connect(self._on_input_xml)
        close = QtWidgets.QPushButton(tr("xml_console_close"), self)
        close.clicked.connect(self.close)
        for button in (export, clear, send, close):
            bottom.addWidget(button)
        layout.addLayout(bottom)

    # ── capture plumbing ────────────────────────────────────────

    def attach_client(self) -> None:
        """(Re)attach the feed to the current client if capture is enabled."""
        if not self._enable.isChecked():
            return
        client = self._get_client()
        if client is not None:
            client.set_xml_console_hook(self._on_raw)
            self._attached_client = client

    def _on_enable_toggled(self, checked: bool) -> None:
        client = self._get_client()
        if client is not None:
            client.set_xml_console_hook(self._on_raw if checked else None)
        self._attached_client = client if checked else None

    def _on_raw(self, incoming: bool, xml_text: str) -> None:
        classified = classify(xml_text)
        if classified is None:
            return
        kind, frm, to = classified
        entry = Entry(incoming, kind, format_xml(xml_text), frm, to,
                      time.time())
        self._buffer.append(entry)
        if len(self._buffer) > _MAX_ENTRIES:
            del self._buffer[:len(self._buffer) - _MAX_ENTRIES]
        if self._passes(entry):
            self._append(entry)

    # ── filtering / rendering ───────────────────────────────────

    def _passes(self, entry: Entry) -> bool:
        box = self._kind_boxes.get(entry.kind)
        if box is not None and not box.isChecked():
            return False
        wanted = bare_jid(self._jid_edit.text())
        if wanted and wanted not in (bare_jid(entry.from_), bare_jid(entry.to)):
            return False
        return True

    def _append(self, entry: Entry) -> None:
        scroll = self._output.verticalScrollBar()
        at_bottom = scroll.value() >= scroll.maximum() - 4
        cursor = self._output.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QColor(COLORS[(entry.kind, entry.incoming)]))
        cursor.insertText(entry.xml + "\n", fmt)
        if at_bottom:
            scroll.setValue(scroll.maximum())

    def _rerender(self) -> None:
        self._output.clear()
        for entry in self._buffer:
            if self._passes(entry):
                self._append(entry)

    # ── actions ─────────────────────────────────────────────────

    def _on_clear(self) -> None:
        self._buffer.clear()
        self._output.clear()

    def _on_export(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("xml_console_export_title"),
            "stanza-xml.txt", "*.txt")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self._output.toPlainText())
        except OSError as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("xml_console_title"),
                tr("xml_console_export_failed", error=str(exc)))

    def _on_input_xml(self) -> None:
        client = self._get_client()
        if client is None:
            QtWidgets.QMessageBox.warning(
                self, tr("xml_console_title"), tr("xml_console_not_connected"))
            return
        dialog = XmlInputDialog(self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        text = dialog.text().strip()
        if not text:
            return
        try:
            client.send_raw_xml(text)
        except ET.ParseError:
            QtWidgets.QMessageBox.warning(
                self, tr("xml_console_title"), tr("xml_console_invalid_xml"))
        except Exception as exc:  # NotConnectedError and friends
            QtWidgets.QMessageBox.warning(
                self, tr("xml_console_title"),
                tr("xml_console_send_failed", error=str(exc)))

    def closeEvent(self, event):
        # Stop capturing when the window is closed; the buffer stays until the
        # next "Clear" so reopening keeps the history.
        if self._enable.isChecked():
            self._enable.setChecked(False)
        super().closeEvent(event)
