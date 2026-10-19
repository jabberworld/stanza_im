"""Application entry point and asyncio+Qt event loop integration (via qasync)."""
import asyncio
import argparse
import sys
import logging
import os

from PyQt6 import QtWidgets

from stanza_im.include.constants import (APP_NAME, APP_LOG_FILE,
                                         VERSION_DISPLAY)

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None

#: Chromium memory-tuning flag sets for ``QTWEBENGINE_CHROMIUM_FLAGS`` (see
#: Preferences → «Stanza IM» → «Производительность» → «Веб-движок»).
_CHROMIUM_MODERATE = (
    "--renderer-process-limit=1",
    "--js-flags=--max-old-space-size=128",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-sync",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=OptimizationHints,MediaRouter,Translate,"
    "CalculateNativeWinOcclusion",
)
_CHROMIUM_AGGRESSIVE = _CHROMIUM_MODERATE + (
    "--disable-gpu", "--disable-gpu-compositing",
)
_CHROMIUM_MODES = {
    "off": (),
    "moderate": _CHROMIUM_MODERATE,
    "aggressive": _CHROMIUM_AGGRESSIVE,
}


def chromium_flags_for(mode: str) -> tuple[str, ...]:
    """Return the Chromium flag tuple for *mode* (defaults to moderate)."""
    return _CHROMIUM_MODES.get(str(mode or "moderate").lower(),
                               _CHROMIUM_MODERATE)


def apply_chromium_flags(mode: str) -> None:
    """Set ``QTWEBENGINE_CHROMIUM_FLAGS`` for *mode* (before QApplication).

    An already-set environment variable (the user's own choice) is respected
    and never overwritten.
    """
    if os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS"):
        return
    flags = chromium_flags_for(mode)
    if flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)
        logger.info("WebEngine flags (%s): %s", mode, " ".join(flags))


def build_parser(argv: list[str] | None = None) -> argparse.ArgumentParser:
    prog = os.path.basename((argv or sys.argv)[0] or "stanza-im")
    parser = argparse.ArgumentParser(
        prog=prog,
        description="%s %s — XMPP/Jabber desktop client" % (
            APP_NAME, VERSION_DISPLAY))
    parser.add_argument("-d", "--debug", action="store_true",
                        help="show debug messages in the console")
    parser.add_argument("-x", "--xml", action="store_true",
                        help="dump raw SEND/RECV XML to the console")
    parser.add_argument("-l", "--log", action="store_true",
                        help="write a full debug log (messages and XML) to a file")
    parser.add_argument("-m", "--memstat", action="count", default=0,
                        help="print periodic memory statistics (repeat: -mm "
                             "for the deep Python-heap breakdown)")
    return parser


def parse_args(argv: list[str] | None = None):
    """Parse the command line; returns ``(options, leftover_argv)``.

    ``-h``/``--help`` prints the option list and raises ``SystemExit(0)``.
    The leftover argv (original order, our flags removed) is meant for Qt.
    """
    return build_parser(argv).parse_known_args(argv)


def prepare_qt_argv(leftover: list[str]) -> list[str]:
    """Return the argv handed to Qt, keeping the program name.

    ``parse_args()`` strips the program name, but QWebEngine refuses to start
    when the argument list is empty (``base::CommandLine``).  Re-prepend it so
    Qt flags and positionals (``-platform``, ``-style``, …) still pass through.
    """
    return ([sys.argv[0]] + leftover) if sys.argv else leftover


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


class _SlixmppNoiseFilter(logging.Filter):
    """Downgrade slixmpp's "Unknown stanza interface" notices to DEBUG.

    slixmpp logs them through the root logger when an IQ matcher is tested
    against a stanza with no ``from``/``id`` interface (e.g. the
    stream-management ``<r/>``/``<a/>``), which floods the log at login.  The
    information stays available with ``-d``/``-l`` without the warning noise.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        if message.startswith("Unknown stanza interface"):
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
        return True


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
    root = logging.getLogger()
    for existing in list(root.filters):
        if isinstance(existing, _SlixmppNoiseFilter):
            root.removeFilter(existing)
    root.addFilter(_SlixmppNoiseFilter())


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
    sys.argv = prepare_qt_argv(leftover)
    debug = args.debug
    xml_dump = args.xml
    file_log = args.log
    memstat = args.memstat

    from stanza_im.core import memstats
    # Level 1 (-m) is the cheap report; level 2 (-mm) adds tracemalloc.  The
    # deep tracing must start early to capture the whole session's allocations,
    # but it is only enabled when explicitly requested.
    if memstat >= 2:
        memstats.start_tracking()

    configure_logging(debug, xml_dump, file_log)
    # Read the [performance] tuning before Qt/WebEngine initialise (the flags
    # must be in the environment before the first QWebEngineProfile is used).
    from stanza_im.core.storage import Config
    perf = Config().performance
    apply_chromium_flags(getattr(perf, "webengine_memory_mode", "moderate"))
    defer_build = bool(getattr(perf, "defer_ui_build", True))
    omemo_mode = str(getattr(perf, "omemo_load_mode", "lazy") or "lazy")
    # Turn the heavy subsystems off entirely before anything imports them.
    webengine_mode = str(getattr(perf, "webengine_mode", "full") or "full")
    from stanza_im.include import constants
    constants.set_webengine_enabled(webengine_mode != "off")
    if omemo_mode == "off":
        from stanza_im.xmpp.omemo import availability
        availability.set_disabled(True)
    if debug:
        logger.info("Debug logging enabled (-d)")
    if xml_dump:
        logger.info("Raw XML message dump enabled (-x)")
    if memstat >= 2:
        logger.info("Memory statistics enabled (-mm, deep tracemalloc)")
    elif memstat:
        logger.info("Memory statistics enabled (-m)")
    if file_log:
        logger.info("Detailed file logging enabled (-l): %s", APP_LOG_FILE)

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION_DISPLAY)
    app.setQuitOnLastWindowClosed(False)

    import qasync
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    _loop = loop

    from PyQt6 import QtCore
    from stanza_im.ui.main_window import MainWindow

    window = MainWindow(app, defer=defer_build)
    window.show()
    if defer_build:
        # Build the heavy widgets only after the login window is on screen.
        QtCore.QTimer.singleShot(0, window.build_deferred)

    # Ctrl+C: run the same graceful shutdown as the tray/menu Quit (flush the
    # unread/roster state, disconnect, cancel tasks, quit) instead of letting
    # KeyboardInterrupt escape the Qt/qasync loop (which printed a traceback in
    # eventFilter and aborted Qt).  add_signal_handler is available because
    # qasync.QEventLoop subclasses the Unix selector loop.
    import signal

    def _on_sigint():
        if getattr(window, "_shutting_down", False):
            # A second Ctrl+C during a slow shutdown forces an immediate exit.
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            os._exit(130)
        window._quit()

    try:
        loop.add_signal_handler(signal.SIGINT, _on_sigint)
    except (NotImplementedError, RuntimeError, ValueError):
        # Fallback: a plain handler plus a keep-alive timer, so Python gets a
        # chance to run it while the Qt loop is otherwise idle.
        signal.signal(signal.SIGINT, lambda *_: _on_sigint())
        _sigint_timer = QtCore.QTimer()
        _sigint_timer.timeout.connect(lambda: None)
        _sigint_timer.start(200)

    def _probe_omemo():
        # Importing the OMEMO backends pulls in xmlschema/oldmemo/twomemo
        # (hundreds of ms up to a few seconds cold).  Run it after the window
        # is up so it never starves the login window's construction/paint; in
        # the "load at startup" mode it also does the real import now, in the
        # default "lazy" mode the real import happens at login.
        from stanza_im.xmpp.omemo import availability
        if omemo_mode == "startup":
            availability.verify()
        availability.log_availability()

    QtCore.QTimer.singleShot(200, _probe_omemo)

    if memstat:
        # Report off the startup path, then periodically.  The cheap report is
        # near-free; the deep (tracemalloc) snapshot runs in a worker thread.
        QtCore.QTimer.singleShot(1000, lambda: memstats.report(logger))
        timer = QtCore.QTimer()
        timer.timeout.connect(lambda: memstats.report(logger))
        timer.start(60_000)

    logger.info("%s %s started", APP_NAME, VERSION_DISPLAY)

    with loop:
        exit_code = loop.run_forever()

    logger.info("Shutting down (exit code %d)", exit_code)
    return exit_code
