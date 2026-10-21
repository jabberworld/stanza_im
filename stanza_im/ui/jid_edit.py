"""JID input fields that normalise what the user types or pastes.

A JID copied from a vCard or a chat is usually an ``xmpp:`` URI and may carry
a resource; these line edits turn it into a bare JID (or, for a room field,
split it into the room and its server) so the same value can be pasted into
any form.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.include.xmpp_uri import normalize_jid, split_jid


class JidLineEdit(QtWidgets.QLineEdit):
    """A line edit whose value is a JID.

    ``QLineEdit`` has no ``insertFromMimeData`` virtual and handles the paste
    shortcut, the context menu and drops in C++, so the field normalises the
    text at those entry points itself instead of relying on an override that
    Qt would never call.
    """

    def __init__(self, *args, resource: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        #: Whether the resource part is meaningful for this field.
        self._allow_resource = bool(resource)

    # ── Editing helpers ───────────────────────────────────────────

    def _insert_text(self, text: str) -> None:
        """Insert *text* normalised, replacing the selection."""
        if not text:
            return
        self.insert(normalize_jid(text, resource=self._allow_resource))

    def _normalise_in_place(self) -> None:
        """Rewrite the current text (used after a context-menu paste)."""
        text = self.jid()
        if text and text != self.text():
            self.setText(text)

    def _paste_clipboard(self) -> None:
        self._insert_text(QtWidgets.QApplication.clipboard().text())

    # ── Qt overrides ──────────────────────────────────────────────

    def keyPressEvent(self, event):  # noqa: N802 - Qt override
        if event.matches(QtGui.QKeySequence.StandardKey.Paste):
            self._paste_clipboard()
            event.accept()
            return
        super().keyPressEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt override
        mime = event.mimeData()
        if mime is not None and mime.hasText():
            self._insert_text(mime.text())
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802 - Qt override
        # The standard menu's Paste action is wired to QLineEdit::paste() in
        # C++, so it cannot be replaced: normalise right after the menu closes.
        menu = self.createStandardContextMenu()
        menu.exec(event.globalPos())
        self._normalise_in_place()

    def jid(self) -> str:
        """The normalised JID of the field ("" when empty)."""
        return normalize_jid(self.text(), resource=self._allow_resource)


class RoomJidEdit(JidLineEdit):
    """A room field: pasting ``room@conf[/nick]`` fills the server too.

    The localpart stays in the field and :attr:`split` carries the domain, so
    the dialog can put it into its separate server widget.  A pasted value
    without a domain is handled like any other JID.
    """

    split = QtCore.pyqtSignal(str, str)   # room, server

    def _insert_text(self, text: str) -> None:
        room, server = split_jid(text)
        if room and server:
            self.setText(room)
            self.split.emit(room, server)
            return
        super()._insert_text(text)

    def _normalise_in_place(self) -> None:
        room, server = split_jid(self.text())
        if room and server:
            self.setText(room)
            self.split.emit(room, server)
            return
        super()._normalise_in_place()

    def room(self) -> tuple[str, str]:
        """``(localpart, server)`` of the current text (server may be "")."""
        return split_jid(self.text())
