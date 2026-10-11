"""Memory statistics — RSS/PSS and a per-component breakdown.

Two levels, selected on the command line:

* ``-m`` (cheap): no tracing, near-zero overhead.  Reports the main process'
  RSS/PSS/peak, the Chromium child processes grouped by type, the Qt widget /
  WebEngine view counts and which heavy optional stacks are loaded.
* ``-mm`` (deep): additionally enables ``tracemalloc`` with a **single** frame
  and logs a package-grouped Python-heap breakdown.  The snapshot is taken in a
  worker thread, so the Qt event loop is never blocked by it.
"""
from __future__ import annotations

import gc
import os
import resource
import sys
import threading
import time
import tracemalloc

_PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") or 4096

#: Heavy optional stacks worth reporting when loaded (label -> import module).
_HEAVY_STACKS = (
    ("aiortc", "aiortc"),
    ("av", "av"),
    ("oldmemo", "oldmemo"),
    ("twomemo", "twomemo"),
    ("slixmpp_omemo", "slixmpp_omemo"),
    ("xmlschema", "xmlschema"),
)

_deep = False
_snapshot_in_flight = False


def start_tracking(nframe: int = 1) -> None:
    """Enable the deep Python-allocation tracing (``tracemalloc``).

    Called only for the deep (``-mm``) level; ``nframe=1`` keeps the overhead
    low (the default 12 frames is an order of magnitude slower).
    """
    global _deep
    _deep = True
    if not tracemalloc.is_tracing():
        tracemalloc.start(max(1, int(nframe)))


def is_deep() -> bool:
    """True when the deep (``tracemalloc``) level is enabled."""
    return _deep


# ── Process memory (cheap, from /proc) ────────────────────────────

def _proc_kb(pid: int) -> tuple[int | None, int | None]:
    """Return ``(rss_kb, pss_kb)`` for *pid*.

    PSS (proportional set size) accounts for shared pages, so it is a fairer
    per-process figure than RSS; it comes from ``smaps_rollup`` when available.
    """
    rss = None
    pss = None
    try:
        with open(f"/proc/{pid}/statm", "r", encoding="ascii") as fh:
            rss = int(fh.read().split()[1]) * _PAGE_SIZE // 1024
    except (OSError, ValueError, IndexError):
        pass
    try:
        with open(f"/proc/{pid}/smaps_rollup", "r", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("Pss:"):
                    pss = int(line.split()[1])
                    break
    except (OSError, ValueError, IndexError):
        pass
    return rss, pss


def _rss_kb() -> int | None:
    """Resident set size of the current process in KiB."""
    return _proc_kb(os.getpid())[0]


def _classify_child(raw: bytes, comm: str = "") -> str:
    """Classify a Chromium child from its ``cmdline`` bytes and process name.

    QtWebEngine passes the process role as ``--type=renderer|gpu-process|
    utility|zygote`` (the network service is a ``utility`` with a
    ``--utility-sub-type=…network…``).  When no ``--type=`` is present the
    short process name (``/proc/<pid>/comm``) is used as a fallback.
    """
    if raw:
        if b"--type=renderer" in raw:
            return "renderer"
        if b"--type=gpu-process" in raw:
            return "gpu-process"
        if b"--type=zygote" in raw:
            return "zygote"
        if b"--type=utility" in raw:
            return "network" if b"network" in raw else "utility"
        marker = b"--type="
        index = raw.find(marker)
        if index >= 0:
            value = raw[index + len(marker):].split(b"\x00", 1)[0]
            value = value.decode("ascii", "replace").strip()
            if value:
                return value
    name = (comm or "").strip()
    if not name:
        return "other"
    lowered = name.lower()
    if "gpu" in lowered:
        return "gpu-process"
    if "renderer" in lowered:
        return "renderer"
    return name


def _child_type(pid: int) -> str:
    """Read ``cmdline`` + ``comm`` of *pid* and classify the child."""
    raw = b""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            raw = fh.read()
    except OSError:
        raw = b""
    comm = ""
    try:
        with open(f"/proc/{pid}/comm", "r", encoding="ascii",
                  errors="replace") as fh:
            comm = fh.read()
    except OSError:
        comm = ""
    return _classify_child(raw, comm)


def _children() -> list[tuple[int, str, int | None, int | None]]:
    """``(pid, type, rss_kb, pss_kb)`` for every direct child process."""
    out: list[tuple[int, str, int | None, int | None]] = []
    my_pid = os.getpid()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return out
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            with open(f"/proc/{pid}/stat", "r", encoding="ascii") as fh:
                stat = fh.read().split(") ")[-1].split()
            # stat fields after the comm): state(1) ppid(2) … rss(23)
            if len(stat) <= 23 or int(stat[1]) != my_pid:
                continue
        except (OSError, ValueError, IndexError):
            continue
        rss, pss = _proc_kb(pid)
        out.append((pid, _child_type(pid), rss, pss))
    return out


def _qt_counts() -> tuple[int, int]:
    """``(widget_count, webengine_view_count)``; widget count is -1 if no app."""
    try:
        from PyQt6 import QtWidgets
        app = QtWidgets.QApplication.instance()
        if app is None:
            return -1, 0
        widgets = app.allWidgets()
        views = 0
        try:
            from PyQt6 import QtWebEngineWidgets
            views = sum(1 for w in widgets
                        if isinstance(w, QtWebEngineWidgets.QWebEngineView))
        except Exception:  # noqa: BLE001 - WebEngine not loaded
            views = 0
        return len(widgets), views
    except Exception:  # noqa: BLE001
        return -1, 0


def _loaded_stacks() -> list[str]:
    """Labels of the heavy optional stacks currently imported."""
    return [label for label, module in _HEAVY_STACKS if module in sys.modules]


# ── Deep (tracemalloc) breakdown ──────────────────────────────────

def _package_of(filename: str) -> str:
    """Map a source filename to a report group (package)."""
    if not filename:
        return "?"
    if filename.startswith("<"):
        return filename  # e.g. <frozen importlib._bootstrap>
    norm = filename.replace("\\", "/")
    if "/stanza_im/" in norm:
        tail = norm.split("/stanza_im/", 1)[1]
        parts = tail.split("/")
        return f"stanza_im.{parts[0]}" if len(parts) >= 2 else "stanza_im"
    if "/site-packages/" in norm:
        tail = norm.split("/site-packages/", 1)[1]
        return os.path.splitext(tail.split("/", 1)[0])[0]
    base = os.path.basename(norm)
    return os.path.splitext(base)[0] or "?"


def _log_deep(logger, top: int) -> None:
    """Take a snapshot (worker thread) and log the heap grouped by package."""
    global _snapshot_in_flight
    try:
        snapshot = tracemalloc.take_snapshot()
        stats = snapshot.statistics("filename")
        groups: dict[str, list[int]] = {}
        for stat in stats:
            filename = stat.traceback[0].filename if stat.traceback else ""
            agg = groups.setdefault(_package_of(filename), [0, 0])
            agg[0] += stat.size
            agg[1] += stat.count
        ordered = sorted(groups.items(), key=lambda kv: kv[1][0], reverse=True)
        lines = ["    python heap by package (tracemalloc nframe=1):"]
        for package, (size, count) in ordered[:top]:
            lines.append(f"      {_fmt_bytes(size)} x{count} {package}")
        logger.info("\n".join(lines))
    except Exception as exc:  # noqa: BLE001 - diagnostics must never crash
        logger.debug("Memory snapshot failed: %s", exc)
    finally:
        _snapshot_in_flight = False


def _schedule_deep(logger, top: int) -> None:
    """Start a background snapshot unless one is already running."""
    global _snapshot_in_flight
    if _snapshot_in_flight:
        return
    _snapshot_in_flight = True
    threading.Thread(target=_log_deep, args=(logger, top), daemon=True,
                     name="memstat-snapshot").start()


# ── gc object counts (cheap component view, no tracemalloc) ───────

#: The gc scan walks every tracked object, so it is throttled and threaded.
_GC_MIN_INTERVAL_S = 300.0
_gc_in_flight = False
_last_gc_report = 0.0


def _gc_counts(top: int = 15) -> list[tuple[str, int]]:
    """Return the *top* object types by live count (from the garbage collector).

    Only **GC-tracked** objects are counted (instances, containers holding
    other containers, …); plain dicts/lists of atomic values may be untracked
    by CPython and are therefore missing.  It is still a good leak indicator
    for widgets, message objects and other complex types — and it never
    inflates memory the way ``tracemalloc`` does.
    """
    try:
        objects = gc.get_objects()
    except Exception:  # noqa: BLE001 - diagnostics must never crash
        return []
    counts: dict[str, int] = {}
    for obj in objects:
        try:
            name = type(obj).__name__
        except Exception:  # noqa: BLE001
            name = "?"
        counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:top]


def _log_gc(logger, top: int) -> None:
    """Log the gc object-type counts (worker thread)."""
    global _gc_in_flight, _last_gc_report
    try:
        counts = _gc_counts(top)
        if counts:
            joined = ", ".join(f"{name} x{count}" for name, count in counts)
            logger.info("    gc objects: %s", joined)
    except Exception as exc:  # noqa: BLE001
        logger.debug("gc object scan failed: %s", exc)
    finally:
        _last_gc_report = time.monotonic()
        _gc_in_flight = False


def _schedule_gc(logger, top: int) -> None:
    """Run the gc scan in a worker thread, at most every ``_GC_MIN_INTERVAL_S``."""
    global _gc_in_flight
    if _gc_in_flight or (time.monotonic() - _last_gc_report) < _GC_MIN_INTERVAL_S:
        return
    _gc_in_flight = True
    threading.Thread(target=_log_gc, args=(logger, top), daemon=True,
                     name="memstat-gc").start()


# ── Report ────────────────────────────────────────────────────────

def report(logger, top: int = 12, deep: bool | None = None) -> None:
    """Log a compact memory snapshot (cheap; the deep part is threaded)."""
    if deep is None:
        deep = _deep
    try:
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (OSError, AttributeError):
        peak_kb = None

    rss, pss = _proc_kb(os.getpid())
    children = _children()
    widgets, views = _qt_counts()
    stacks = _loaded_stacks()
    traced, _peak = (tracemalloc.get_traced_memory()
                     if tracemalloc.is_tracing() else (0, 0))

    lines = [f"--- memory: rss={_fmt(rss)} pss={_fmt(pss)}"
             f" peak={_fmt(peak_kb)} traced={_fmt_bytes(traced)}"]

    by_type: dict[str, list[int]] = {}
    for _pid, ctype, crss, cpss in children:
        agg = by_type.setdefault(ctype, [0, 0])
        agg[0] += 1
        agg[1] += cpss if cpss is not None else (crss or 0)
    total_child = sum(kb for _count, kb in by_type.values())
    lines.append(f"    children: {len(children)} procs"
                 f" total={_fmt(total_child)}")
    for ctype, (count, kb) in sorted(by_type.items(),
                                     key=lambda kv: kv[1][1], reverse=True):
        lines.append(f"      {ctype}: {count} proc {_fmt(kb)}")
    lines.append(f"    qt: widgets={widgets} webengine_views={views}")
    lines.append(f"    python: modules={len(sys.modules)}"
                 f" heavy=[{', '.join(stacks)}]")
    logger.info("\n".join(lines))

    if deep and tracemalloc.is_tracing():
        _schedule_deep(logger, top)
    # A gc object-type breakdown is useful in both levels and does not inflate
    # memory; it is throttled and runs in a worker thread.
    _schedule_gc(logger, top)


def _fmt(kb):
    """Format a KiB value as MiB."""
    if kb is None:
        return "?"
    return f"{kb / 1024:.1f}M"


def _fmt_bytes(nbytes: int) -> str:
    """Format a byte value as MiB."""
    return f"{nbytes / (1024 * 1024):.1f}M"
