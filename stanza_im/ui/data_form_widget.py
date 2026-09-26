"""Rendering of XEP-0004 data forms into a Qt widget."""
from __future__ import annotations

import base64
import hashlib
import html
import threading
import urllib.request

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr

_TEXT_TYPES = {"text-single", "text-private", "jid-single", "text-multi",
               "jid-multi"}
_MEDIA_NS = "urn:xmpp:media-element"


class _MediaFetcher(QtCore.QObject):
    """Fetch a CAPTCHA image in a worker thread (XEP-0221 ``<media/>``)."""

    ready = QtCore.pyqtSignal(str, bytes)
    failed = QtCore.pyqtSignal(str, str)

    def fetch(self, url: str) -> None:
        threading.Thread(target=self._run, args=(url,), daemon=True).start()

    def _run(self, url: str) -> None:
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "Stanza IM"})
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read(2 * 1024 * 1024)
            self.ready.emit(url, data)
        except Exception as exc:
            self.failed.emit(url, str(exc))


class _HashcashSolver(QtCore.QObject):
    """Solve an XEP-0158 SHA-256 hashcash challenge in a worker thread."""

    solved = QtCore.pyqtSignal(str)
    failed = QtCore.pyqtSignal(str)

    def solve(self, prefix: str, label: str) -> None:
        threading.Thread(target=self._run, args=(prefix, label),
                         daemon=True).start()

    def _run(self, prefix: str, label: str) -> None:
        try:
            target = int(label, 16)
            bits = len(label) * 4
            mask = (1 << bits) - 1
            prefix = prefix or ""
            for counter in range(20_000_000):
                candidate = f"{prefix}{counter:016X}"
                digest = hashlib.sha256(candidate.encode("utf-8")).digest()
                if int.from_bytes(digest, "big") & mask == target:
                    self.solved.emit(candidate)
                    return
        except Exception:
            pass
        self.failed.emit(tr("captcha_solve_failed"))


def _field_media(field):
    """Return ``{kind, url, mime, alt}`` for a XEP-0221 media field, else None.

    Prefers an image URI (OCR CAPTCHA), then audio, then video.
    """
    xml = getattr(field, "xml", None)
    if xml is None:
        return None
    media = xml.find("{%s}media" % _MEDIA_NS)
    if media is None:
        return None
    uris = []
    for uri in media.findall("{%s}uri" % _MEDIA_NS):
        value = str(uri.text or "").strip()
        if value:
            uris.append((str(uri.get("type") or ""), value))
    for prefix, kind in (("image/", "image"), ("audio/", "audio"),
                         ("video/", "video")):
        for mime, value in uris:
            if mime.startswith(prefix):
                return {"kind": kind, "url": value, "mime": mime,
                        "alt": str(media.get("alt") or "")}
    return None


def _as_url(value) -> str | None:
    """Return *value* as a clickable ``http(s)`` URL, else ``None``."""
    text = str(value or "").strip()
    if text.lower().startswith(("http://", "https://")) and " " not in text:
        return text
    return None


def _link_label(url: str, text: str = "", parent=None) -> QtWidgets.QLabel:
    """A label rendering *text* as a clickable external link to *url*."""
    safe_url = html.escape(url, quote=True)
    safe_text = html.escape(text or url)
    label = QtWidgets.QLabel(f'<a href="{safe_url}">{safe_text}</a>', parent)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(
        QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)
    label.setWordWrap(True)
    label.setToolTip(url)
    return label


def _url_label(url: str, parent=None) -> QtWidgets.QLabel:
    """A label rendering *url* as a clickable external link."""
    return _link_label(url, url, parent)


def fit_dialog_to_content(dialog: QtWidgets.QDialog) -> None:
    """Grow *dialog* to fit its content, clamped to the available screen.

    ``QScrollArea`` caches the inner widget's size hint, so ``adjustSize``
    would size the dialog to a stale value.  The full content size is
    reserved on the scroll area for the duration of the ``adjustSize`` call
    (so the measurement never depends on the current viewport or on whether
    the dialog has been laid out yet), then released.  If the content is
    larger than the screen the dialog stays clamped and the scroll area
    provides the scrolling.
    """
    layout = dialog.layout()
    if layout is not None:
        layout.activate()
    scroll = getattr(dialog, "_form_scroll", None)
    inner = scroll.widget() if scroll is not None else None
    if scroll is not None and inner is not None:
        hint = inner.sizeHint()
        frame = 2 * scroll.frameWidth()
        scroll.setMinimumSize(hint.width() + frame, hint.height() + frame)
        if layout is not None:
            layout.activate()
        dialog.adjustSize()
        scroll.setMinimumSize(0, 0)
        if layout is not None:
            layout.activate()
    else:
        dialog.adjustSize()
    screen = dialog.screen() or QtWidgets.QApplication.primaryScreen()
    if screen is None:
        return
    available = screen.availableGeometry()
    dialog.resize(min(dialog.width(), int(available.width() * 0.9)),
                  min(dialog.height(), int(available.height() * 0.9)))


def _place_button_in_row(layout: QtWidgets.QFormLayout,
                         widget: QtWidgets.QWidget,
                         button: QtWidgets.QPushButton) -> None:
    container = QtWidgets.QWidget(widget.parentWidget())
    row = QtWidgets.QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    layout.replaceWidget(widget, container,
                         QtCore.Qt.FindChildOption.FindDirectChildrenOnly)
    widget.setParent(container)
    row.addWidget(widget)
    row.addWidget(button)


class DataFormWidget(QtWidgets.QWidget):
    """Render a slixmpp XEP-0004 form and write user input back to it."""

    media_open_requested = QtCore.pyqtSignal(str, str)  # url, kind
    media_ready = QtCore.pyqtSignal()  # an inline image finished loading

    def __init__(self, form, parent=None, media_service=None):
        super().__init__(parent)
        self._form = form
        self._media_service = media_service
        self._fetchers: list = []
        self._hashcash = None
        self._fields: dict[str, object] = {}
        self._multi_fields: dict[str, list] = {}
        self._link_fields: set[str] = set()
        self._combos: list[QtWidgets.QComboBox] = []
        form_layout = QtWidgets.QFormLayout(self)
        self._form_layout = form_layout
        form_layout.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        if form["title"]:
            title = QtWidgets.QLabel(str(form["title"]))
            title.setStyleSheet("font-weight: bold;")
            form_layout.addRow(title)
        instructions = form["instructions"]
        if isinstance(instructions, str):
            instructions = [instructions] if instructions else []
        for instruction in instructions or ():
            label = QtWidgets.QLabel(str(instruction))
            label.setWordWrap(True)
            form_layout.addRow(label)
        for field in form["fields"]:
            if not self._build_field(form_layout, field):
                continue
        self._align_selectors()

    def _align_selectors(self) -> None:
        """Give every list-single selector the same width (widest value)."""
        if not self._combos:
            return
        width = max(combo.sizeHint().width() for combo in self._combos)
        for combo in self._combos:
            combo.setFixedWidth(width)

    def _build_field(self, layout: QtWidgets.QFormLayout, field) -> bool:
        ftype = str(field["type"] or "text-single")
        var = str(field["var"] or "")
        label = str(field.get("label", "") or var)
        if field["required"]:
            label += " *"
        value = field["value"]
        options = list(field["options"] or ())

        if ftype == "hidden":
            return False

        if ftype == "fixed":
            fixed_url = _as_url(field["value"])
            if fixed_url is not None:
                widget = _url_label(fixed_url)
            else:
                widget = QtWidgets.QLabel(str(field["value"] or ""))
                widget.setWordWrap(True)
                widget.setTextInteractionFlags(
                    widget.textInteractionFlags()
                    | QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            if label.strip():
                layout.addRow(label, widget)
            else:
                layout.addRow(widget)
            return True

        if ftype in _TEXT_TYPES or ftype in ("", "text-single"):
            initial = value if isinstance(value, str) else (
                value[0] if isinstance(value, list) and value else "")
            media = _field_media(field)
            url = _as_url(initial)
            if media is None and url is not None:
                # A server-supplied read-only URL: show a link only, the value
                # is submitted unchanged via the field's own value.
                if var:
                    self._link_fields.add(var)
                link = _link_label(url, label.strip() or tr("captcha_open_oob"))
                layout.addRow(link)
                return True
            edit = QtWidgets.QLineEdit()
            if ftype == "text-private":
                edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            edit.setText(initial)
            if ftype == "text-multi":
                edit.setPlaceholderText("line1\\nline2")
            self._fields[var] = edit
            if media is not None:
                layout.addRow(label, self._media_row(media, edit))
            else:
                layout.addRow(label, edit)
            if var == "SHA-256":
                self._start_hashcash(field, edit)
            return True

        if ftype == "boolean":
            check = QtWidgets.QCheckBox()
            check.setChecked(bool(value))
            self._fields[var] = check
            layout.addRow(label, check)
            return True

        if ftype == "list-single":
            combo = QtWidgets.QComboBox()
            current = value if isinstance(value, str) else (
                value[0] if isinstance(value, list) and value else "")
            index = 0
            for option in options:
                option_value = str(option["value"] or "")
                option_label = str(option.get("label", "") or option_value)
                combo.addItem(option_label, option_value)
                if option_value == current:
                    index = combo.count() - 1
            combo.setCurrentIndex(max(0, index))
            if field["required"]:
                combo.setEditable(False)
            self._fields[var] = combo
            self._combos.append(combo)
            layout.addRow(label, combo)
            return True

        if ftype == "list-multi":
            widget = QtWidgets.QWidget()
            column = QtWidgets.QVBoxLayout(widget)
            column.setContentsMargins(0, 0, 0, 0)
            checks = []
            selected = value if isinstance(value, list) else ([] if value is None else [value])
            selected = [str(item) for item in selected]
            for option in options:
                option_value = str(option["value"] or "")
                option_label = str(option.get("label", "") or option_value)
                check = QtWidgets.QCheckBox(option_label)
                check.setChecked(option_value in selected)
                column.addWidget(check)
                checks.append((check, option_value))
            if not options:
                free = QtWidgets.QLineEdit()
                free.setText(", ".join(selected))
                column.addWidget(free)
                checks = [("free", free)]
            self._fields[var] = widget
            self._multi_fields[var] = checks
            layout.addRow(label, widget)
            return True

        edit = QtWidgets.QLineEdit()
        initial = value if isinstance(value, str) else (
            value[0] if isinstance(value, list) and value else "")
        edit.setText(initial)
        self._fields[var] = edit
        layout.addRow(label, edit)
        return True

    def _media_row(self, media, edit):
        """A CAPTCHA challenge widget (image inline / audio-video button)."""
        container = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        if media["kind"] == "image":
            label = QtWidgets.QLabel(tr("form_media_loading"))
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(48)
            column.addWidget(label)
            self._load_media_image(media["url"], label)
        else:
            button = QtWidgets.QToolButton()
            button.setText(tr("form_media_open"))
            button.clicked.connect(
                lambda: self.media_open_requested.emit(media["url"],
                                                       media["kind"]))
            column.addWidget(button)
            if media.get("alt"):
                alt = QtWidgets.QLabel(str(media["alt"]))
                alt.setWordWrap(True)
                column.addWidget(alt)
        column.addWidget(edit)
        return container

    def _load_media_image(self, url: str, label) -> None:
        lower = url.lower()
        if lower.startswith("data:"):
            # XEP-0231 Bits of Binary resolved to an inline data URI.
            try:
                _header, payload = url.split(",", 1)
                self._set_media_pixmap(label, base64.b64decode(payload))
            except Exception:
                label.setText(tr("form_media_failed"))
            return
        if not lower.startswith(("http://", "https://")):
            label.setText(url)
            return
        fetcher = _MediaFetcher(self)
        fetcher.ready.connect(
            lambda _url, data, lbl=label: self._set_media_pixmap(lbl, data))
        fetcher.failed.connect(
            lambda _url, _err, lbl=label: lbl.setText(tr("form_media_failed")))
        self._fetchers.append(fetcher)
        fetcher.fetch(url)

    def _set_media_pixmap(self, label, data) -> None:
        pixmap = QtGui.QPixmap()
        if not pixmap.loadFromData(data):
            label.setText(tr("form_media_failed"))
            return
        if pixmap.width() > 640:
            pixmap = pixmap.scaledToWidth(
                640, QtCore.Qt.TransformationMode.SmoothTransformation)
        label.setPixmap(pixmap)
        label.setFixedSize(pixmap.size())
        self.media_ready.emit()

    def _hidden_value(self, var: str) -> str:
        for field in self._form["fields"]:
            if str(field["var"] or "") != var:
                continue
            value = field["value"]
            if isinstance(value, list):
                return str(value[0]) if value else ""
            return str(value or "")
        return ""

    def _start_hashcash(self, field, edit) -> None:
        label = str(field.get("label", "") or "").strip()
        if not label or any(c not in "0123456789abcdefABCDEF" for c in label):
            return
        edit.setPlaceholderText(tr("captcha_solving"))
        solver = _HashcashSolver(self)
        solver.solved.connect(edit.setText)
        solver.failed.connect(edit.setPlaceholderText)
        self._hashcash = solver
        solver.solve(self._hidden_value("from"), label)

    def validate(self) -> str | None:
        """Return a translated message for the first missing required field."""
        for field in self._form["fields"]:
            if not field["required"]:
                continue
            var = str(field["var"] or "")
            if var in self._link_fields:
                continue  # a pre-filled read-only URL, always satisfied
            widget = self._fields.get(var)
            if isinstance(widget, QtWidgets.QLineEdit):
                if widget.text().strip():
                    continue
            elif isinstance(widget, QtWidgets.QCheckBox):
                continue
            elif isinstance(widget, QtWidgets.QComboBox):
                continue
            else:
                checks = self._multi_fields.get(var, [])
                if any(check.isChecked() for check, _ in checks if
                       not isinstance(check, str)):
                    continue
                if any(isinstance(check, QtWidgets.QLineEdit) and check.text().strip()
                       for check, _ in checks):
                    continue
            label = str(field.get("label", "") or var)
            return tr("form_required", label=label)
        return None

    def _field_value(self, field):
        """Current widget value for *field* (falls back to its form value)."""
        var = str(field["var"] or "")
        widget = self._fields.get(var)
        if widget is None:
            return field["value"]
        if isinstance(widget, QtWidgets.QLineEdit):
            return widget.text()
        if isinstance(widget, QtWidgets.QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QtWidgets.QComboBox):
            return str(widget.currentData() or "")
        checks = self._multi_fields.get(var, [])
        chosen = [value for check, value in checks
                  if not isinstance(check, str) and check.isChecked()]
        for check, value in checks:
            if isinstance(check, QtWidgets.QLineEdit) and check.text().strip():
                chosen = [part.strip() for part in check.text().split(",")]
                break
        return chosen if chosen else ""

    def values(self) -> dict:
        """Return the current ``{var: value}`` for every form field."""
        return {str(field["var"] or ""): self._field_value(field)
                for field in self._form["fields"]}

    def apply_to_form(self) -> None:
        """Copy widget values back onto the form's fields."""
        for field in self._form["fields"]:
            if self._fields.get(str(field["var"] or "")) is None:
                continue
            field["value"] = self._field_value(field)
        try:
            self._form["type"] = "submit"
        except KeyError:
            self._form.xml.attrib["type"] = "submit"

    def attach_button(self, button: QtWidgets.QPushButton) -> bool:
        """Place *button* next to the first editable field.

        Returns ``True`` when the button was attached to a field row.
        """
        for var in self._fields:
            widget = self._fields[var]
            if not isinstance(widget, QtWidgets.QWidget):
                continue
            _place_button_in_row(self._form_layout, widget, button)
            return True
        return False

    def first_edit(self) -> QtWidgets.QLineEdit | None:
        """Return the first line-edit field widget, if any."""
        for var in self._fields:
            widget = self._fields[var]
            if isinstance(widget, QtWidgets.QLineEdit):
                return widget
        return None


class LegacyFormWidget(QtWidgets.QWidget):
    """Render a legacy (XEP-0077/XEP-0055) field list into line edits."""

    def __init__(self, fields: dict[str, str], password_keys=(), parent=None):
        super().__init__(parent)
        self._edits: dict[str, QtWidgets.QLineEdit] = {}
        form_layout = QtWidgets.QFormLayout(self)
        self._form_layout = form_layout
        form_layout.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for key, default in fields.items():
            label = key.replace("_", " ").replace(":", "").capitalize()
            edit = QtWidgets.QLineEdit()
            edit.setText(str(default or ""))
            if key in password_keys:
                edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            self._edits[key] = edit
            form_layout.addRow(label, edit)

    def values(self) -> dict[str, str]:
        return {key: edit.text() for key, edit in self._edits.items()}

    def attach_button(self, button: QtWidgets.QPushButton) -> bool:
        """Place *button* next to the first field."""
        widget = next(iter(self._edits.values()), None)
        if widget is None:
            return False
        _place_button_in_row(self._form_layout, widget, button)
        return True

    def first_edit(self) -> QtWidgets.QLineEdit | None:
        return next(iter(self._edits.values()), None)