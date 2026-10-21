"""JID input fields that normalise what the user types or pastes.

A JID copied from a vCard or a chat is usually an ``xmpp:`` URI and may carry
a resource; these line edits turn it into a bare JID (or, for a room field,
split it into the room and its server) so the same value can be pasted into
any form.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from stanza_im.include.xmpp_uri import normalize_jid, split_jid


class JidLineEdit(QtWidgets.QLineEdit):
    """A line edit whose value is a JID.

    Pasting (Ctrl+V, middle click, drag and drop — Qt funnels all of them
    through ``insertFromMimeData``) normalises the URI; :meth:`jid` returns the
    normalised value of whatever was typed.
    """

    def __init__(self, *args, resource: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        #: Whether the resource part is meaningful for this field.
        self._allow_resource = bool(resource)

    def insertFromMimeData(self, source):  # noqa: N802 - Qt override
        text = (source.text()
                if source is not None and source.hasText() else "")
        if not text:
            super().insertFromMimeData(source)
            return
        self.insert(normalize_jid(text, resource=self._allow_resource))

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def insertFromMimeData(self, source):  # noqa: N802 - Qt override
        text = (source.text()
                if source is not None and source.hasText() else "")
        room, server = split_jid(text)
        if room and server:
            self.setText(room)
            self.split.emit(room, server)
            return
        super().insertFromMimeData(source)

    def room(self) -> tuple[str, str]:
        """``(localpart, server)`` of the current text (server may be "")."""
        return split_jid(self.text())
