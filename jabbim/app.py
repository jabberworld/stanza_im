"""Application entry point and asyncio+Qt event loop integration (via qasync)."""
import asyncio
import sys
import logging

from PyQt6 import QtWidgets

from jabbim.include.constants import APP_NAME, VERSION

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None

_DEBUG_FLAGS = ("-d", "--debug")
_XML_FLAGS = ("-x", "--xml")
_MEMSTAT_FLAGS = ("-m", "--memstat")


def _clean_flags(found: bool, flags) -> list[str]:
    return [] if found else [a for a in sys.argv if a not in flags]


def configure_logging(debug: bool, xml_dump: bool) -> None:
    """Set up logging levels.

    ``debug`` enables slixmpp's plugin-level debugging; ``xml_dump`` toggles
    the raw SEND/RECV XML stream output independently (``-x/--xml``).
    """
    level = logging.DEBUG if debug else logging.INFO

    if xml_dump:
        # Dump SEND/RECV XML regardless of the general debug level.
        logging.getLogger("slixmpp.xmlstream").setLevel(logging.DEBUG)
    if debug:
        logging.getLogger("slixmpp").setLevel(logging.DEBUG)
        if not xml_dump:
            # Debug without XML noise: keep the raw stream at INFO.
            logging.getLogger("slixmpp.xmlstream").setLevel(logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def get_event_loop() -> asyncio.AbstractEventLoop:
    """Return the shared asyncio event loop (qasync QEventLoop)."""
    if _loop is None:
        raise RuntimeError("Application not initialised yet")
    return _loop


def run() -> int:
    """Initialise Qt, install the qasync event loop, show the main window and
    enter the event loop.  Returns the exit code."""
    global _loop

    debug = any(f in sys.argv for f in _DEBUG_FLAGS)
    xml_dump = any(f in sys.argv for f in _XML_FLAGS)
    memstat = any(f in sys.argv for f in _MEMSTAT_FLAGS)

    from jabbim.core import memstats
    if memstat:
        memstats.start_tracking()

    if debug:
        sys.argv = [a for a in sys.argv if a not in _DEBUG_FLAGS]
    if xml_dump:
        sys.argv = [a for a in sys.argv if a not in _XML_FLAGS]
    if memstat:
        sys.argv = [a for a in sys.argv if a not in _MEMSTAT_FLAGS]

    configure_logging(debug, xml_dump)
    if debug:
        logger.info("Debug logging enabled (-d)")
    if xml_dump:
        logger.info("Raw XML message dump enabled (-x)")
    if memstat:
        logger.info("Memory statistics enabled (-m)")

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setQuitOnLastWindowClosed(False)

    import qasync
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    _loop = loop

    from jabbim.ui.main_window import MainWindow

    window = MainWindow(app)
    window.show()

    if memstat:
        from PyQt6 import QtCore
        memstats.report(logger)
        timer = QtCore.QTimer()
        timer.timeout.connect(lambda: memstats.report(logger))
        timer.start(30_000)

    logger.info("%s %s started", APP_NAME, VERSION)

    with loop:
        exit_code = loop.run_forever()

    logger.info("Shutting down (exit code %d)", exit_code)
    return exit_code
