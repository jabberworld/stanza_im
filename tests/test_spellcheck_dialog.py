"""Offscreen tests for the spell-check language picker."""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_spell_dialog_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets  # noqa: E402

from stanza_im.ui.spellcheck_dialog import SpellCheckLanguagesDialog  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

dialog = SpellCheckLanguagesDialog([], ["en_US", "ru_RU"])
check("automatic mode is selected for an empty list", dialog._auto.isChecked())
check("the dictionary list is disabled in automatic mode",
      not dialog._list.isEnabled())
dialog._auto.setChecked(False)
check("unchecking automatic mode enables the list", dialog._list.isEnabled())
check("OK is disabled with no selected language",
      dialog._buttons.button(
          QtWidgets.QDialogButtonBox.StandardButton.Ok).isEnabled() is False)
dialog._list.item(1).setCheckState(QtCore.Qt.CheckState.Checked)
check("a selected language is returned",
      dialog.languages() == ["ru_RU"])
check("OK is enabled once a language is selected",
      dialog._buttons.button(
          QtWidgets.QDialogButtonBox.StandardButton.Ok).isEnabled())
dialog.deleteLater()

explicit = SpellCheckLanguagesDialog(["ru_RU"], ["en_US", "ru_RU"])
check("an explicit list starts with automatic mode off",
      not explicit._auto.isChecked() and explicit._list.isEnabled())
check("the explicit language is preselected",
      explicit.languages() == ["ru_RU"])
explicit.deleteLater()

if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll spell-check dialog tests passed.")
