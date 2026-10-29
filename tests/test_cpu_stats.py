"""CPU statistics helpers and /proc parsing.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_cpu_stats.py
"""
import logging
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core import cpustats  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _stat(pid, comm, ppid=1, utime=0, stime=0, state="S"):
    fields = [state, str(ppid)] + ["0"] * 9 + [str(utime), str(stime)]
    return "%d (%s) %s" % (pid, comm, " ".join(fields))


raw = _stat(42, "python 3", ppid=1, utime=7, stime=5)
comm, ticks = cpustats._parse_stat(raw)
check("a /proc stat line keeps a comm with spaces", comm == "python 3")
check("utime and stime are summed", ticks == 12)
check("100% is one core",
      cpustats._percent(cpustats.CLOCK_TICKS, 1.0) == 100.0)
check("CPU percent scales with the interval",
      cpustats._percent(cpustats.CLOCK_TICKS * 2, 2.0) == 100.0)
check("negative deltas are clamped",
      cpustats._delta(10, 3) == 0)

root = tempfile.mkdtemp(prefix="stanza_cpu_proc_")
main = os.path.join(root, "100")
child = os.path.join(root, "200")
os.makedirs(os.path.join(main, "task", "100"))
os.makedirs(os.path.join(main, "task", "101"))
os.makedirs(child)
open(os.path.join(main, "stat"), "w").write(_stat(100, "python3", utime=20))
open(os.path.join(main, "task", "100", "stat"), "w").write(
    _stat(100, "python3", utime=20))
open(os.path.join(main, "task", "100", "comm"), "w").write("main\n")
open(os.path.join(main, "task", "101", "stat"), "w").write(
    _stat(101, "worker", utime=10))
open(os.path.join(main, "task", "101", "comm"), "w").write("_QThreadWorker\n")
open(os.path.join(child, "stat"), "w").write(
    _stat(200, "QtWebEngineProc", ppid=100, utime=3))
# A second child with another parent must not be counted.
os.makedirs(os.path.join(root, "300"))
open(os.path.join(root, "300", "stat"), "w").write(
    _stat(300, "other", ppid=1, utime=9))

snap = cpustats._read_snapshot(pid=100, root=root)
check("the snapshot reads the main process",
      snap is not None and snap.total == 20)
check("the snapshot reads named threads",
      snap.threads[101] == ("_QThreadWorker", 10))
check("the snapshot reads descendants only",
      list(snap.children) == [200])

_lines = []


class _Logger:
    def info(self, msg, *args):
        _lines.append(msg % args if args else msg)


cpustats.start(pid=100, root=root)
cpustats.report(_Logger(), detailed=True, pid=100, root=root)
text = "\n".join(_lines)
check("the report has a CPU header", "--- cpu:" in text)
check("the report lists worker threads", "_QThreadWorker" in text)
check("-CC lists each child process", "child pid=200" in text)
check("unrelated processes are not listed", "other" not in text)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All CPU-stat tests passed")
