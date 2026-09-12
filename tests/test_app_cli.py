"""CLI keys and logging routing tests for stanza_im.app.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_app_cli.py
"""
import contextlib
import io
import logging
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im import app

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── parse_args: flag extraction and leftover argv ──────────────────

opts, leftover = app.parse_args(["stanza-im", "-d", "-x", "-l", "-m"])
check("parse_args: all flags recognised", all(
    (opts.debug, opts.xml, opts.log, opts.memstat)))
check("parse_args: leftover keeps only prog", leftover == ["stanza-im"])

opts, leftover = app.parse_args(["stanza-im"])
check("parse_args: no flags by default", not any(
    (opts.debug, opts.xml, opts.log, opts.memstat)))
check("parse_args: plain leftover", leftover == ["stanza-im"])

opts, leftover = app.parse_args(["stanza-im", "--debug", "--xml", "=extra"])
check("parse_args: long flags + unknown positional",
      opts.debug and opts.xml and leftover == ["stanza-im", "=extra"])


# ── -h / --help prints the option list and exits 0 ─────────────────

def help_text(flag):
    out = io.StringIO()
    code = None
    try:
        with contextlib.redirect_stdout(out):
            app.parse_args(["stanza-im", flag])
    except SystemExit as e:
        code = e.code
    return code, out.getvalue()


for flag in ("-h", "--help"):
    code, text = help_text(flag)
    check(f"{flag}: SystemExit(0)", code == 0)
    check(f"{flag}: lists all keys",
          all(a in text for a in ("-d", "-x", "-l", "-m", "--help")))


# ── configure_logging routing matrix ───────────────────────────────

def fresh_logging():
    for name in list(logging.Logger.manager.loggerDict):
        if name == "slixmpp" or name.startswith("slixmpp."):
            logging.getLogger(name).setLevel(logging.NOTSET)
    root = logging.getLogger()
    root.setLevel(logging.NOTSET)
    for h in list(root.handlers):
        root.removeHandler(h)


def run_case(debug, xml, flog):
    """Configure logging, emit debug/info/xml/warning records and return
    (console_text, file_text_or_None)."""
    fresh_logging()
    log_path = tempfile.mktemp(prefix="stanza_log_", suffix=".log")
    app.APP_LOG_FILE = log_path

    console = io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = console
    try:
        app.configure_logging(debug, xml, flog)
    finally:
        sys.stderr = real_stderr

    logging.getLogger("slixmpp.testplugin").debug("CONSOLE_DBGMARK")
    logging.getLogger("slixmpp.testplugin").info("CONSOLE_INFOMARK")
    logging.getLogger("slixmpp.xmlstream.xmlstream").debug("CONSOLE_XMLMARK <t/>")
    logging.getLogger("slixmpp.xmlstream.xmlstream").warning("CONSOLE_WARNMARK")

    file_text = None
    if flog:
        with open(log_path, encoding="utf-8") as fh:
            file_text = fh.read()
        os.unlink(log_path)
    return console.getvalue(), file_text


def has(text, marker):
    return marker in (text or "")


# expected console flags / file behaviour per (debug, xml, log)
_CASES = [
    ((0, 0, 0), (0, 0), (False, False)),
    ((1, 0, 0), (1, 0), (False, False)),
    ((0, 1, 0), (0, 1), (False, False)),
    ((1, 1, 0), (1, 1), (False, False)),
    ((0, 0, 1), (0, 0), (True, True)),
    ((1, 0, 1), (1, 0), (True, True)),
    ((0, 1, 1), (0, 1), (True, True)),
    ((1, 1, 1), (1, 1), (True, True)),
]

for (debug, xml, flog), (want_dbg, want_xml), (file_dbg, file_xml) in _CASES:
    con, fl = run_case(debug, xml, flog)
    tag = f"d={debug} x={xml} l={flog}"
    check(f"{tag}: console debug -> {want_dbg}",
          has(con, "CONSOLE_DBGMARK") == bool(want_dbg))
    check(f"{tag}: console xml -> {want_xml}",
          has(con, "CONSOLE_XMLMARK") == bool(want_xml))
    check(f"{tag}: console info always",
          has(con, "CONSOLE_INFOMARK"))
    check(f"{tag}: console warning always",
          has(con, "CONSOLE_WARNMARK"))
    if flog:
        check(f"{tag}: file has debug ({file_dbg})",
              has(fl, "CONSOLE_DBGMARK") == file_dbg)
        check(f"{tag}: file has xml ({file_xml})",
              has(fl, "CONSOLE_XMLMARK") == file_xml)
        check(f"{tag}: file has info+warning",
              has(fl, "CONSOLE_INFOMARK") and has(fl, "CONSOLE_WARNMARK"))
    else:
        check(f"{tag}: no file written", fl is None)

print("\nAll tests passed ✓" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)