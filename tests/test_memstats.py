"""Tests for the memory statistics (cheap ``-m`` vs deep ``-mm``).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_memstats.py
"""
import logging
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = os.path.join("/tmp", "stanza_memstats")
os.environ.setdefault("XDG_CONFIG_HOME", os.path.join(_SCRATCH, "config"))
os.environ.setdefault("XDG_DATA_HOME", os.path.join(_SCRATCH, "data"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core import memstats

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _logger():
    logger = logging.getLogger("test.memstats")
    logger.handlers[:] = []
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = _Capture()
    logger.addHandler(handler)
    return logger, handler


# 1. the cheap level does not touch tracemalloc ------------------------------
import tracemalloc  # noqa: E402

check("importing memstats does not start tracemalloc",
      not tracemalloc.is_tracing())
check("the cheap level is not deep", memstats.is_deep() is False)

# 2. package grouping --------------------------------------------------------
check("stanza_im subpackages are grouped",
      memstats._package_of("/x/stanza_im/ui/chat_widget.py")
      == "stanza_im.ui"
      and memstats._package_of("/x/stanza_im/core/client.py")
      == "stanza_im.core")
check("site-packages are grouped by distribution",
      memstats._package_of("/x/site-packages/av/audio/frame.py") == "av"
      and memstats._package_of("/x/site-packages/PyQt6/QtCore.pyi")
      == "PyQt6")
check("stdlib files are grouped by basename",
      memstats._package_of("/usr/lib/python3.11/os.py") == "os")

# 2b. child process classification ------------------------------------------
def _cmdline(*args):
    return b"\x00".join(a.encode() for a in args) + b"\x00"


check("renderer children are classified",
      memstats._classify_child(
          _cmdline("QtWebEngineProcess", "--type=renderer")) == "renderer")
check("gpu children are classified",
      memstats._classify_child(_cmdline("x", "--type=gpu-process"))
      == "gpu-process")
check("utility network children are classified",
      memstats._classify_child(_cmdline(
          "x", "--type=utility",
          "--utility-sub-type=network.mojom.NetworkService")) == "network")
check("plain utility children are classified",
      memstats._classify_child(_cmdline("x", "--type=utility")) == "utility")
check("zygote children are classified",
      memstats._classify_child(_cmdline("x", "--type=zygote")) == "zygote")
check("a generic --type value is returned",
      memstats._classify_child(_cmdline("x", "--type=ppapi")) == "ppapi")
check("no --type falls back to the process name",
      memstats._classify_child(b"", "QtWebEngineProc\n") == "QtWebEngineProc")
check("a gpu-ish name is detected",
      memstats._classify_child(b"", "gpu-thing") == "gpu-process")
check("an unknown child is 'other'",
      memstats._classify_child(b"", "") == "other")

# 2c. gc object-type counts --------------------------------------------------
# (Only GC-tracked objects are counted; plain atomic dicts may be untracked,
# so use instances, which are always tracked.)
class _Obj:
    def __init__(self):
        self.x = 1


_keep = [_Obj() for _ in range(5000)]
_counts = dict(memstats._gc_counts(20))
check("gc counts include the tracked instances",
      _counts.get("_Obj", 0) >= 5000)

# 2d. descendant walk (renderer/GPU are grandchildren of the zygote) ---------
_tree = {1: [10, 11], 10: [100, 101], 100: [1000], 11: [110]}
check("the descendant walk includes grandchildren",
      sorted(memstats._descendants_from(_tree, 1))
      == [10, 11, 100, 101, 110, 1000])
check("the descendant walk is cycle-safe",
      memstats._descendants_from({1: [2], 2: [1]}, 1) == [2])
check("no children yields an empty list",
      memstats._descendants_from({1: []}, 1) == [])

# 2e. qt counts never crash and return ints ----------------------------------
_widgets, _views = memstats._qt_counts()
check("qt counts return ints",
      isinstance(_widgets, int) and isinstance(_views, int))

# 2f. the deep snapshot / gc scan cadence -----------------------------------
check("the first report takes the deep snapshot", memstats._deep_due(1))
check("the deep snapshot runs every fifth report",
      all(memstats._deep_due(n) for n in (5, 10, 15, 20))
      and not any(memstats._deep_due(n) for n in (2, 3, 4, 6, 9, 14)))

memstats._gc_in_flight = False
memstats._schedule_gc(logging.getLogger("test.memstats"), 5)
_deadline = time.monotonic() + 5.0
while memstats._gc_in_flight and time.monotonic() < _deadline:
    time.sleep(0.05)
check("the gc scan finishes", not memstats._gc_in_flight)

# 2g. the adaptive trim policy ----------------------------------------------
_now = 1000.0
_RSS = 500_000
check("below the threshold nothing is trimmed",
      not memstats.should_trim(_now, None, _RSS, _RSS + 50_000))
check("a threshold growth after the interval trims",
      memstats.should_trim(_now, _now - 400, _RSS, _RSS + 250_000))
check("a threshold growth inside the interval waits",
      not memstats.should_trim(_now, _now - 10, _RSS, _RSS + 250_000))
check("a big jump trims regardless of the interval",
      memstats.should_trim(_now, _now - 10, _RSS, _RSS + 700_000))
check("the first measurement trims once",
      memstats.should_trim(_now, None, 0, 900_000))
check("an unknown rss does not trim",
      not memstats.should_trim(_now, None, 0, None))
check("a shrinking process does not trim",
      not memstats.should_trim(_now, _now - 400, _RSS, _RSS - 10_000))
check("trim_heap returns a bool", isinstance(memstats.trim_heap(), bool))

# 2g. per-process memory fields ----------------------------------------------
_mem = memstats._proc_mem(os.getpid())
check("_proc_mem reports an integer rss", isinstance(_mem.get("rss"), int))
check("_proc_mem exposes the smaps fields",
      {"rss", "pss", "private_dirty", "anonymous", "shared_clean"}
      <= set(_mem))

# 3. cheap report ------------------------------------------------------------
logger, handler = _logger()
memstats.report(logger)
text = "\n".join(handler.messages)
check("the report mentions the main process",
      "rss=" in text and "peak=" in text)
check("the report lists children", "children:" in text)
check("the report lists Qt counts", "qt: widgets=" in text)
check("the report lists python modules/stacks", "python: modules=" in text)
check("the cheap report did not enable tracemalloc",
      not tracemalloc.is_tracing())

# 4. deep level enables a single-frame tracing -------------------------------
memstats.start_tracking()
check("deep mode is reported", memstats.is_deep() is True)
check("deep mode starts tracemalloc", tracemalloc.is_tracing())
check("deep mode uses a single frame",
      tracemalloc.get_traceback_limit() == 1)

# 5. the deep snapshot runs in a worker thread and logs a package breakdown --
handler.messages.clear()
memstats._report_count = 0          # the first report is deep-due
memstats.report(logger, deep=True)
deadline = time.monotonic() + 5.0
while memstats._snapshot_in_flight and time.monotonic() < deadline:
    time.sleep(0.05)
deep_text = "\n".join(handler.messages)
check("the deep snapshot logs a package breakdown",
      "python heap by package" in deep_text)
check("the deep snapshot reports its own RSS cost",
      "rss " in deep_text and "->" in deep_text)

# 5b. the growth diff compares against the previous snapshot -----------------
memstats._last_packages = {"stanza_im.ui": (1, 1)}
handler.messages.clear()
memstats._log_deep(logger, 5)
diff_text = "\n".join(handler.messages)
check("the deep snapshot logs growth against the previous run",
      "growth since the previous snapshot" in diff_text)
check("the snapshot records the packages for the next diff",
      isinstance(memstats._last_packages, dict)
      and bool(memstats._last_packages))

# 5c. a non-deep report skips the snapshot ----------------------------------
memstats._report_count = 1          # next report is #2 (not deep-due)
memstats._last_packages = {"x": (1, 1)}
handler.messages.clear()
memstats.report(logger, deep=True)
time.sleep(0.2)
check("a non-due report does not take a snapshot",
      "python heap by package" not in "\n".join(handler.messages)
      and memstats._last_packages == {"x": (1, 1)})

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All memstats tests passed.")
