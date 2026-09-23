"""Raw XML console (Actions → XML-консоль).

Shows every stanza crossing the stream, coloured by direction and kind, with
live filters (messages / presences / iq / sm / other) and a bare-JID filter.
The window is non-modal and captures the ``SEND:``/``RECV:`` raw dump from the
``slixmpp.xmlstream`` logger (the same source as ``-x`` and the file log).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable
from xml.dom import minidom
from xml.etree import ElementTree as ET

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr

_CLIENT_NS = "jabber:client"
_SM_NS_PREFIX = "urn:xmpp:sm:"
_LOGGER_NAME = "slixmpp.xmlstream"

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


def jid_matches(entry_from: str, entry_to: str, wanted: str) -> bool:
    """Case-insensitive substring filter over the full ``from``/``to`` JIDs.

    An empty ``wanted`` matches everything.  Matching the whole JID (resource
    included) lets e.g. ``conference.linuxoid.in`` catch every room on that
    service regardless of the room or nickname.
    """
    wanted = (wanted or "").strip().lower()
    if not wanted:
        return True
    return (wanted in (entry_from or "").lower()
            or wanted in (entry_to or "").lower())


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


class _XmlConsoleLogHandler(logging.Handler):
    """Forward the raw ``SEND:``/``RECV:`` dump to the console.

    Attached to the ``slixmpp.xmlstream`` logger, so it sees exactly the
    stanzas that ``-x`` / the file log show — in both directions.
    """

    def __init__(self, callback: Callable[[bool, str], None]):
        super().__init__(level=logging.DEBUG)
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            return
        if message.startswith("SEND: "):
            incoming = False
        elif message.startswith("RECV: "):
            incoming = True
        else:
            return
        payload = message[6:]
        args = record.args
        if (isinstance(args, tuple) and len(args) == 1
                and isinstance(args[0], (bytes, bytearray))):
            payload = bytes(args[0]).decode("utf-8", "replace")
        try:
            self._callback(incoming, payload)
        except Exception:
            pass


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

    stanza_captured = QtCore.pyqtSignal(bool, str)

    def __init__(self, get_client: Callable[[], object | None], parent=None):
        super().__init__(parent)
        self._get_client = get_client
        self._buffer: list[Entry] = []
        self._prev_log_level: int | None = None
        self._log_handler = _XmlConsoleLogHandler(self.stanza_captured.emit)
        self.stanza_captured.connect(self._on_raw)

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

        self._legend = self._build_legend()
        layout.addWidget(self._legend)

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

    # ── colour legend ───────────────────────────────────────────

    @staticmethod
    def _color_swatch(color: str, parent=None) -> QtWidgets.QLabel:
        """A small solid square showing *color* (the per-stanza text colour)."""
        label = QtWidgets.QLabel(parent)
        label.setFixedSize(12, 12)
        label.setStyleSheet(
            f"background-color: {color};"
            " border: 1px solid #666666; border-radius: 2px;")
        return label

    @staticmethod
    def _legend_arrow(incoming: bool, parent=None) -> QtWidgets.QLabel:
        """Direction marker: ↓ for incoming, ↑ for outgoing."""
        return QtWidgets.QLabel("↓" if incoming else "↑", parent)

    def _build_legend(self) -> QtWidgets.QWidget:
        """One-line legend: per kind a coloured square ↓ (in) / ↑ (out)."""
        legend = QtWidgets.QWidget(self)
        legend.setToolTip(tr("xml_console_legend_hint"))
        row = QtWidgets.QHBoxLayout(legend)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        self._legend_swatches: list[tuple[str, bool, QtWidgets.QLabel]] = []
        for index, (kind, key) in enumerate((
                ("message", "xml_console_messages"),
                ("presence", "xml_console_presences"),
                ("iq", "xml_console_iq"),
                ("sm", "xml_console_sm"),
                ("other", "xml_console_other"))):
            if index:
                row.addSpacing(10)
            row.addWidget(QtWidgets.QLabel(tr(key), legend))
            for incoming in (True, False):
                square = self._color_swatch(COLORS[(kind, incoming)], legend)
                row.addWidget(square)
                row.addWidget(self._legend_arrow(incoming, legend))
                self._legend_swatches.append((kind, incoming, square))
        row.addStretch(1)
        return legend

    # ── capture plumbing ────────────────────────────────────────

    def _on_enable_toggled(self, checked: bool) -> None:
        if checked:
            self._attach_logger()
        else:
            self._detach_logger()

    def _attach_logger(self) -> None:
        if self._prev_log_level is not None:
            return
        logger = logging.getLogger(_LOGGER_NAME)
        self._prev_log_level = logger.level
        logger.addHandler(self._log_handler)
        # The raw dump is only generated at DEBUG (as with -x / the file log).
        logger.setLevel(logging.DEBUG)

    def _detach_logger(self) -> None:
        if self._prev_log_level is None:
            return
        logger = logging.getLogger(_LOGGER_NAME)
        logger.removeHandler(self._log_handler)
        logger.setLevel(self._prev_log_level)
        self._prev_log_level = None

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
        return jid_matches(entry.from_, entry.to, self._jid_edit.text())

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
