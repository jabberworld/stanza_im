"""Rendering of XEP-0004 data forms into a Qt widget."""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr

_TEXT_TYPES = {"text-single", "text-private", "jid-single", "text-multi",
               "jid-multi"}


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

    def __init__(self, form, parent=None):
        super().__init__(parent)
        self._form = form
        self._fields: dict[str, object] = {}
        self._multi_fields: dict[str, list] = {}
        form_layout = QtWidgets.QFormLayout(self)
        self._form_layout = form_layout
        form_layout.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        if form["title"]:
            title = QtWidgets.QLabel(str(form["title"]))
            title.setStyleSheet("font-weight: bold;")
            form_layout.addRow(title)
        for instruction in form["instructions"] or ():
            label = QtWidgets.QLabel(str(instruction))
            label.setWordWrap(True)
            form_layout.addRow(label)
        for field in form["fields"]:
            if not self._build_field(form_layout, field):
                continue

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
            fixed = QtWidgets.QLabel(str(field["value"] or ""))
            fixed.setWordWrap(True)
            fixed.setTextInteractionFlags(
                fixed.textInteractionFlags()
                | QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addRow(label, fixed)
            return True

        if ftype in _TEXT_TYPES or ftype in ("", "text-single"):
            edit = QtWidgets.QLineEdit()
            if ftype == "text-private":
                edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            initial = value if isinstance(value, str) else (
                value[0] if isinstance(value, list) and value else "")
            edit.setText(initial)
            if ftype == "text-multi":
                edit.setPlaceholderText("line1\\nline2")
            self._fields[var] = edit
            layout.addRow(label, edit)
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

    def validate(self) -> str | None:
        """Return a translated message for the first missing required field."""
        for field in self._form["fields"]:
            if not field["required"]:
                continue
            var = str(field["var"] or "")
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