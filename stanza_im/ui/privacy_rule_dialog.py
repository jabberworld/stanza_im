"""Add/edit dialog for one XEP-0016 privacy-list rule.

Also holds the localized description of a rule used by the list editor.
"""
from __future__ import annotations

from PyQt6 import QtWidgets

from stanza_im.i18n import tr

_TYPE_KEYS = (("privacy_type_jid", "jid"),
              ("privacy_type_group", "group"),
              ("privacy_type_subscription", "subscription"),
              ("privacy_type_all", ""))

_SUBSCRIPTIONS = (("privacy_sub_none", "none"),
                  ("privacy_sub_to", "to"),
                  ("privacy_sub_from", "from"),
                  ("privacy_sub_both", "both"))

_STANZAS = (("privacy_stanza_message", "message"),
            ("privacy_stanza_iq", "iq"),
            ("privacy_stanza_presence_in", "presence_in"),
            ("privacy_stanza_presence_out", "presence_out"))


def subscription_label(value: str) -> str:
    for key, data in _SUBSCRIPTIONS:
        if data == value:
            return tr(key)
    return value


def describe_item(item: dict) -> str:
    """Localized ``If <type> "x", then deny messages, …`` for one rule."""
    itype = str(item.get("type") or "")
    value = str(item.get("value") or "")
    if itype == "jid":
        subject = '%s "%s"' % (tr("privacy_type_jid"), value)
    elif itype == "group":
        subject = '%s "%s"' % (tr("privacy_type_group"), value)
    elif itype == "subscription":
        subject = "%s: %s" % (tr("privacy_type_subscription"),
                              subscription_label(value))
    else:
        subject = tr("privacy_all")
    action = tr("privacy_action_deny" if item.get("action") == "deny"
                else "privacy_action_allow")
    stanzas = [tr(key) for key, field in _STANZAS if item.get(field)]
    return tr("privacy_rule", subject=subject, action=action,
              stanzas=", ".join(stanzas) if stanzas else tr("privacy_all"))


class PrivacyRuleDialog(QtWidgets.QDialog):
    """Build (or edit) a single privacy-list rule."""

    def __init__(self, jids: list[str], groups: list[str], item: dict | None = None,
                 parent=None):
        super().__init__(parent)
        self._jids = list(jids)
        self._groups = list(groups)
        self.setWindowTitle(tr("privacy_rule_title_edit" if item
                               else "privacy_rule_title_add"))
        self.setMinimumWidth(420)
        layout = QtWidgets.QFormLayout(self)
        layout.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._type = QtWidgets.QComboBox(self)
        for key, data in _TYPE_KEYS:
            self._type.addItem(tr(key), data)
        self._type.currentIndexChanged.connect(self._sync_value_widget)
        self._value = QtWidgets.QComboBox(self)
        layout.addRow(tr("privacy_rule_if"), self._row(self._type, self._value))

        self._action = QtWidgets.QComboBox(self)
        self._action.addItem(tr("privacy_action_deny"), "deny")
        self._action.addItem(tr("privacy_action_allow"), "allow")
        layout.addRow(tr("privacy_rule_then"), self._action)

        self._checks: dict[str, QtWidgets.QCheckBox] = {}
        for key, field in _STANZAS:
            check = QtWidgets.QCheckBox(tr(key), self)
            self._checks[field] = check
            layout.addRow("", check)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(
            tr("dialog_ok"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
            tr("dialog_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        if item:
            self._load(item)
        else:
            self._sync_value_widget()

    @staticmethod
    def _row(*widgets) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for widget in widgets:
            layout.addWidget(widget)
        layout.addStretch(1)
        return row

    def _set_type(self, itype: str) -> None:
        index = self._type.findData(itype)
        self._type.setCurrentIndex(max(index, 0))

    def _sync_value_widget(self) -> None:
        itype = self._type.currentData()
        self._value.blockSignals(True)
        self._value.clear()
        if itype in ("jid", "group"):
            self._value.setEditable(True)
            self._value.setEnabled(True)
            self._value.addItems(self._jids if itype == "jid" else self._groups)
            self._value.setCurrentText("")
        elif itype == "subscription":
            self._value.setEditable(False)
            self._value.setEnabled(True)
            for key, data in _SUBSCRIPTIONS:
                self._value.addItem(tr(key), data)
        else:
            self._value.setEditable(False)
            self._value.setEnabled(False)
        self._value.blockSignals(False)

    def _load(self, item: dict) -> None:
        self._set_type(str(item.get("type") or ""))
        itype = self._type.currentData()
        self._sync_value_widget()
        value = str(item.get("value") or "")
        if itype == "subscription":
            index = self._value.findData(value)
            self._value.setCurrentIndex(max(index, 0))
        elif itype in ("jid", "group"):
            self._value.setCurrentText(value)
        self._action.setCurrentIndex(
            0 if item.get("action", "deny") == "deny" else 1)
        for field, check in self._checks.items():
            check.setChecked(bool(item.get(field)))

    def result_item(self) -> dict:
        """The rule described by the dialog (order is set by the caller)."""
        itype = self._type.currentData()
        if itype == "subscription":
            value = str(self._value.currentData() or "")
        elif itype in ("jid", "group"):
            value = self._value.currentText().strip()
        else:
            value = ""
        return {
            "type": itype,
            "value": value,
            "action": self._action.currentData(),
            "order": 0,
            "message": self._checks["message"].isChecked(),
            "iq": self._checks["iq"].isChecked(),
            "presence_in": self._checks["presence_in"].isChecked(),
            "presence_out": self._checks["presence_out"].isChecked(),
        }
