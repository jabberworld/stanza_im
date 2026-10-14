"""Shared helper for opening dialogs non-modally.

Blocking (`exec()`/`open()`) dialogs prevent copying data from another window
(e.g. a room name from a chat) into the dialog, so dialogs that hold editable
fields or copyable data are shown modeless.  A dialog must keep a live
reference: parent it to a long-lived widget (or store it on the owner), since
``show()`` does not block.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets


def show_modeless(dialog: QtWidgets.QDialog, on_finished=None,
                  delete_on_close: bool = False) -> QtWidgets.QDialog:
    """Show *dialog* non-modally; returns it.

    ``on_finished(result)`` runs when the dialog is accepted or rejected.
    """
    dialog.setModal(False)
    if delete_on_close:
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
    if on_finished is not None:
        dialog.finished.connect(on_finished)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog
