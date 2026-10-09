"""Stanza IM XMPP Client."""
# QtWebEngine must share OpenGL contexts; the attribute has to be set before
# the QApplication is created.  Setting it here (the package is always imported
# before the app/tests build their QApplication) lets the chat/media views
# import QtWebEngine lazily — after the login window is already up — instead of
# pulling the heavy WebEngine module onto the startup path.
try:
    from PyQt6 import QtCore
    QtCore.QCoreApplication.setAttribute(
        QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
except Exception:  # pragma: no cover - PyQt6 is a hard dependency of the app
    pass
