"""Application entry point and asyncio+Qt event loop integration (via qasync)."""
import asyncio
import sys
import logging
import os

from PyQt6 import QtWidgets

from jabbim.include.constants import APP_NAME, VERSION, APP_LOG_FILE

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None

_DEBUG_FLAGS = ("-d", "--debug")
_XML_FLAGS = ("-x", "--xml")
_MEMSTAT_FLAGS = ("-m", "--memstat")
_LOG_FLAGS = ("-l", "--log")


def _clean_flags(found: bool, flags) -> list[str]:
    return [] if found else [a for a in sys.argv if a not in flags]


def configure_logging(debug: bool, xml_dump: bool, file_log: bool = False) -> None:
    """Set up logging levels.

    ``debug`` enables slixmpp's plugin-level debugging; ``xml_dump`` toggles
    the raw SEND/RECV XML stream output independently (``-x/--xml``).
    """
    level = logging.DEBUG if (debug or file_log) else logging.INFO

    if xml_dump:
        # Dump SEND/RECV XML regardless of the general debug level.
        logging.getLogger("slixmpp.xmlstream").setLevel(logging.DEBUG)
    if debug or file_log:
        logging.getLogger("slixmpp").setLevel(logging.DEBUG)
        if not xml_dump and not file_log:
            # Debug without XML noise: keep the raw stream at INFO.
            logging.getLogger("slixmpp.xmlstream").setLevel(logging.INFO)

    handlers = [logging.StreamHandler()]
    if file_log:
        try:
            os.unlink(APP_LOG_FILE)
        except FileNotFoundError:
            pass
        handlers.append(logging.FileHandler(APP_LOG_FILE, encoding="utf-8"))
        logging.getLogger("slixmpp.xmlstream").setLevel(logging.DEBUG)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
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
    file_log = any(f in sys.argv for f in _LOG_FLAGS)

    from jabbim.core import memstats
    if memstat:
        memstats.start_tracking()

    if debug:
        sys.argv = [a for a in sys.argv if a not in _DEBUG_FLAGS]
    if xml_dump:
        sys.argv = [a for a in sys.argv if a not in _XML_FLAGS]
    if memstat:
        sys.argv = [a for a in sys.argv if a not in _MEMSTAT_FLAGS]
    if file_log:
        sys.argv = [a for a in sys.argv if a not in _LOG_FLAGS]

    configure_logging(debug, xml_dump, file_log)
    if debug:
        logger.info("Debug logging enabled (-d)")
    if xml_dump:
        logger.info("Raw XML message dump enabled (-x)")
    if memstat:
        logger.info("Memory statistics enabled (-m)")
    if file_log:
        logger.info("Detailed file logging enabled (-l): %s", APP_LOG_FILE)

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
