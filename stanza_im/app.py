"""Application entry point and asyncio+Qt event loop integration (via qasync)."""
import asyncio
import argparse
import sys
import logging
import os

from PyQt6 import QtWidgets

from stanza_im.include.constants import APP_NAME, VERSION, APP_LOG_FILE

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None


def build_parser(argv: list[str] | None = None) -> argparse.ArgumentParser:
    prog = os.path.basename((argv or sys.argv)[0] or "stanza-im")
    parser = argparse.ArgumentParser(
        prog=prog,
        description="%s %s — XMPP/Jabber desktop client" % (APP_NAME, VERSION))
    parser.add_argument("-d", "--debug", action="store_true",
                        help="show debug messages in the console")
    parser.add_argument("-x", "--xml", action="store_true",
                        help="dump raw SEND/RECV XML to the console")
    parser.add_argument("-l", "--log", action="store_true",
                        help="write a full debug log (messages and XML) to a file")
    parser.add_argument("-m", "--memstat", action="store_true",
                        help="print periodic memory statistics to the console")
    return parser


def parse_args(argv: list[str] | None = None):
    """Parse the command line; returns ``(options, leftover_argv)``.

    ``-h``/``--help`` prints the option list and raises ``SystemExit(0)``.
    The leftover argv (original order, our flags removed) is meant for Qt.
    """
    return build_parser(argv).parse_known_args(argv)


class _ConsoleFilter(logging.Filter):
    """Route DEBUG output to the console only for the enabled keys.

    INFO/WARNING/ERROR records are always shown (as before); DEBUG records
    from the ``slixmpp.xmlstream`` logger (the SEND/RECV raw dump) appear
    only with ``-x``, any other DEBUG only with ``-d``.  ``-l`` never widens
    the console output — it only fills the log file.
    """

    def __init__(self, debug: bool, xml_dump: bool):
        super().__init__()
        self._debug = debug
        self._xml_dump = xml_dump

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING or record.levelno == logging.INFO:
            return True
        if record.name.startswith("slixmpp.xmlstream"):
            return self._xml_dump
        return self._debug


def configure_logging(debug: bool, xml_dump: bool, file_log: bool = False) -> None:
    """Set up logging levels and destinations.

    ``debug`` enables slixmpp/plugin debug output to the console; ``xml_dump``
    enables the raw SEND/RECV XML stream output to the console.  ``file_log``
    mirrors ALL debug output (messages and XML) into ``APP_LOG_FILE``,
    regardless of ``debug``/``xml_dump``.
    """
    # What gets generated: the full debug/message width needed by the file or
    # by a console switch.  Per-logger levels gate record creation; handler
    # filters below decide where each record is shown.
    root_level = logging.DEBUG if (debug or file_log) else logging.INFO
    if debug or file_log:
        logging.getLogger("slixmpp").setLevel(logging.DEBUG)
    if xml_dump or file_log:
        logging.getLogger("slixmpp.xmlstream").setLevel(logging.DEBUG)
    else:
        # Keep the raw stream quiet even when slixmpp debug is on.
        logging.getLogger("slixmpp.xmlstream").setLevel(logging.INFO)

    handlers: list[logging.Handler] = []
    console = logging.StreamHandler()
    console.addFilter(_ConsoleFilter(debug, xml_dump))
    handlers.append(console)

    if file_log:
        try:
            os.unlink(APP_LOG_FILE)
        except FileNotFoundError:
            pass
        handlers.append(logging.FileHandler(APP_LOG_FILE, encoding="utf-8"))

    logging.basicConfig(
        level=root_level,
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

    args, leftover = parse_args()
    sys.argv = leftover
    debug = args.debug
    xml_dump = args.xml
    file_log = args.log
    memstat = args.memstat

    from stanza_im.core import memstats
    if memstat:
        memstats.start_tracking()

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

    from stanza_im.ui.main_window import MainWindow

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
