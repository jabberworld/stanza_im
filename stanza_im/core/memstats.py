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
import logging
import os
import resource
import sys
import threading
import tracemalloc

logger = logging.getLogger("stanza_im.memstats")

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
#: Every Nth report also takes the (expensive) deep snapshot and the gc scan.
_deep_every = 5
_report_count = 0
#: Package -> (bytes, objects) of the previous deep snapshot, for the growth
#: diff.  A few hundred entries, so no snapshot has to be kept alive.
_last_packages: dict[str, tuple[int, int]] = {}
#: The "no WebEngine view" hint is printed once per process, not every minute.
_no_view_logged = False

#: Adaptive housekeeping: hand freed heap back to the OS when the process grew
#: by this much since the last trim (rate-limited), or immediately on a big
#: jump (a runaway snapshot/leak must not double the footprint).
TRIM_THRESHOLD_KB = 200 * 1024
TRIM_URGENT_KB = 600 * 1024
TRIM_MIN_INTERVAL_S = 300.0

_libc = None


def start_tracking(nframe: int = 1) -> None:
    """Enable the deep Python-allocation tracing (``tracemalloc``).

    Called only for the deep (``-mm``) level; ``nframe=1`` keeps the overhead
    low (the default 12 frames is an order of magnitude slower).
    """
    global _deep, _report_count, _last_packages
    _deep = True
    _report_count = 0
    _last_packages = {}
    if not tracemalloc.is_tracing():
        tracemalloc.start(max(1, int(nframe)))


def is_deep() -> bool:
    """True when the deep (``tracemalloc``) level is enabled."""
    return _deep


def rss_kb() -> int | None:
    """The main process RSS in KiB (None when ``/proc`` is unavailable)."""
    return _proc_mem(os.getpid()).get("rss")


def trim_heap() -> bool:
    """Run ``gc.collect()`` and return freed pages to the OS (malloc_trim)."""
    global _libc
    try:
        gc.collect()
    except Exception:  # noqa: BLE001 - diagnostics must never crash
        pass
    try:
        if _libc is None:
            import ctypes
            _libc = ctypes.CDLL("libc.so.6")
        return bool(_libc.malloc_trim(0))
    except Exception:  # noqa: BLE001
        return False


def should_trim(now: float, last_trim: float | None,
                last_rss_kb: int | None, rss: int | None) -> bool:
    """Decide whether the freed heap should be returned to the OS now.

    *last_rss_kb* is the RSS measured right after the previous trim and
    *last_trim* its ``time.monotonic()`` stamp.  Trims are rate-limited to one
    per :data:`TRIM_MIN_INTERVAL_S`; growth of :data:`TRIM_URGENT_KB` is
    trimmed regardless.
    """
    if not rss:
        return False
    growth = int(rss) - int(last_rss_kb or 0)
    if growth >= TRIM_URGENT_KB:
        return True
    if growth < TRIM_THRESHOLD_KB:
        return False
    if last_trim is None:
        return True
    return (float(now) - float(last_trim)) >= TRIM_MIN_INTERVAL_S


# ── Process memory (cheap, from /proc) ────────────────────────────

def _proc_mem(pid: int) -> dict[str, int | None]:
    """Return memory figures (KiB) for *pid* from ``/proc``.

    ``rss``/``pss`` come from ``statm``/``smaps_rollup``; ``private_dirty``,
    ``anonymous`` and ``shared_clean`` help tell heap growth (private/anonymous)
    apart from shared-library growth (shared_clean).
    """
    info: dict[str, int | None] = {
        "rss": None, "pss": None, "private_dirty": None,
        "anonymous": None, "shared_clean": None,
    }
    try:
        with open(f"/proc/{pid}/statm", "r", encoding="ascii") as fh:
            info["rss"] = int(fh.read().split()[1]) * _PAGE_SIZE // 1024
    except (OSError, ValueError, IndexError):
        pass
    keys = {"Pss:": "pss", "Private_Dirty:": "private_dirty",
            "Anonymous:": "anonymous", "Shared_Clean:": "shared_clean"}
    try:
        with open(f"/proc/{pid}/smaps_rollup", "r", encoding="ascii") as fh:
            for line in fh:
                field = keys.get(line.split(":", 1)[0] + ":")
                if field is not None and info[field] is None:
                    info[field] = int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return info


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


def _read_cmdline(pid: int) -> bytes:
    """Raw ``/proc/<pid>/cmdline`` (empty when unreadable)."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return fh.read()
    except OSError:
        return b""


def _read_comm(pid: int) -> str:
    """Short process name from ``/proc/<pid>/comm`` (``Name:`` fallback)."""
    try:
        with open(f"/proc/{pid}/comm", "r", encoding="ascii",
                  errors="replace") as fh:
            name = fh.read().strip()
            if name:
                return name
    except OSError:
        pass
    try:
        with open(f"/proc/{pid}/status", "r", encoding="ascii",
                  errors="replace") as fh:
            for line in fh:
                if line.startswith("Name:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def _descendants_from(ppid_map: dict[int, list[int]], root: int) -> list[int]:
    """All descendants of *root* (breadth-first) from a ``ppid -> [pid]`` map.

    Chromium forks its renderer/GPU/network processes from a zygote, so they
    are *grandchildren* of the browser process; walking the whole tree (not
    only the direct children) is required to see the real WebEngine memory.
    """
    out: list[int] = []
    seen: set[int] = {root}  # the root is not its own descendant
    queue = list(ppid_map.get(root, []))
    while queue:
        pid = queue.pop()
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
        queue.extend(ppid_map.get(pid, []))
    return out


def _proc_tree() -> dict[int, list[int]]:
    """Build a ``ppid -> [pid]`` map for every readable process."""
    tree: dict[int, list[int]] = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return tree
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            with open(f"/proc/{pid}/stat", "r", encoding="ascii") as fh:
                stat = fh.read().split(") ")[-1].split()
            ppid = int(stat[1])
        except (OSError, ValueError, IndexError):
            continue
        tree.setdefault(ppid, []).append(pid)
    return tree


def _children() -> list[tuple[int, str, str, int | None, int | None]]:
    """``(pid, type, comm, rss_kb, pss_kb)`` for every descendant process."""
    pids = _descendants_from(_proc_tree(), os.getpid())
    out: list[tuple[int, str, str, int | None, int | None]] = []
    for pid in pids:
        comm = _read_comm(pid)
        ctype = _classify_child(_read_cmdline(pid), comm)
        mem = _proc_mem(pid)
        out.append((pid, ctype, comm, mem["rss"], mem["pss"]))
    return out


def _qt_counts() -> tuple[int, int]:
    """``(widget_count, webengine_view_count)``; widget count is -1 if no app."""
    try:
        from PyQt6 import QtWidgets
        app = QtWidgets.QApplication.instance()
        if app is None:
            return -1, 0
        widgets = app.allWidgets()
    except Exception as exc:  # noqa: BLE001
        logger.debug("widget count failed: %s", exc)
        return -1, 0
    views = 0
    try:
        from PyQt6 import QtWebEngineWidgets
        views = sum(1 for w in widgets
                    if isinstance(w, QtWebEngineWidgets.QWebEngineView))
    except Exception as exc:  # noqa: BLE001 - WebEngine not loaded
        logger.debug("WebEngine view count via isinstance failed: %s", exc)
        # Fall back to a class-name match so the count never silently reads 0.
        views = sum(1 for w in widgets
                    if "WebEngineView" in type(w).__name__)
    if views == 0:
        # isinstance can miss a subclass in an odd import layout; a name match
        # is a safe second opinion.
        views = sum(1 for w in widgets
                    if "WebEngineView" in type(w).__name__)
    if views == 0 and widgets:
        # Diagnostic: no WebEngine view found in allWidgets() although widgets
        # exist — log the classes that could be a chat view once per process
        # (an idle app legitimately has no views).
        global _no_view_logged
        if _no_view_logged:
            return len(widgets), views
        _no_view_logged = True
        interesting = sorted({
            type(w).__name__ for w in widgets
            if any(tag in type(w).__name__
                   for tag in ("View", "Chat", "Engine", "Web"))})
        logger.debug("no WebEngine view in allWidgets (%d widgets); "
                     "candidates=%s", len(widgets), interesting or "none")
    return len(widgets), views


def _pixmap_cache_limit() -> int | None:
    """``QPixmapCache`` limit in KiB (None when Qt is unavailable)."""
    try:
        from PyQt6 import QtGui
        return int(QtGui.QPixmapCache.cacheLimit())
    except Exception:  # noqa: BLE001
        return None


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
    global _snapshot_in_flight, _last_packages
    try:
        rss_before = _proc_mem(os.getpid())["rss"]
        snapshot = tracemalloc.take_snapshot()
        stats = snapshot.statistics("filename")
        groups: dict[str, list[int]] = {}
        for stat in stats:
            filename = stat.traceback[0].filename if stat.traceback else ""
            agg = groups.setdefault(_package_of(filename), [0, 0])
            agg[0] += stat.size
            agg[1] += stat.count
        rss_after = _proc_mem(os.getpid())["rss"]
        ordered = sorted(groups.items(), key=lambda kv: kv[1][0], reverse=True)
        lines = [f"    python heap by package (tracemalloc nframe=1;"
                 f" rss {_fmt(rss_before)} -> {_fmt(rss_after)}):"]
        for package, (size, count) in ordered[:top]:
            lines.append(f"      {_fmt_bytes(size)} x{count} {package}")
        if _last_packages:
            growth = []
            for package, (size, _count) in ordered:
                before = _last_packages.get(package, (0, 0))[0]
                if size > before:
                    growth.append((size - before, package, size))
            growth.sort(reverse=True)
            if growth:
                lines.append("    growth since the previous snapshot:")
                for delta, package, size in growth[:max(5, top // 2)]:
                    lines.append(f"      +{_fmt_bytes(delta)} -> "
                                 f"{_fmt_bytes(size)} {package}")
        _last_packages = {pkg: (size, count)
                          for pkg, (size, count) in groups.items()}
        del stats, snapshot, groups, ordered
        logger.info("\n".join(lines))
    except Exception as exc:  # noqa: BLE001 - diagnostics must never crash
        logger.debug("Memory snapshot failed: %s", exc)
    finally:
        _snapshot_in_flight = False
        # The snapshot itself churns tens of MB: give them back right away
        # instead of waiting for the periodic housekeeping.
        trim_heap()


def _schedule_deep(logger, top: int) -> None:
    """Start a background snapshot unless one is already running."""
    global _snapshot_in_flight
    if _snapshot_in_flight:
        return
    _snapshot_in_flight = True
    threading.Thread(target=_log_deep, args=(logger, top), daemon=True,
                     name="memstat-snapshot").start()


# ── gc object counts (cheap component view, no tracemalloc) ───────

#: The gc scan walks every tracked object; it runs on every report, in a
#: worker thread, guarded so two scans never overlap.
_gc_in_flight = False


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
    global _gc_in_flight
    try:
        counts = _gc_counts(top)
        if counts:
            joined = ", ".join(f"{name} x{count}" for name, count in counts)
            logger.info("    gc objects: %s", joined)
    except Exception as exc:  # noqa: BLE001
        logger.debug("gc object scan failed: %s", exc)
    finally:
        _gc_in_flight = False
        trim_heap()


def _schedule_gc(logger, top: int) -> None:
    """Run the gc scan in a worker thread (skipped while one is in flight)."""
    global _gc_in_flight
    if _gc_in_flight:
        return
    _gc_in_flight = True
    threading.Thread(target=_log_gc, args=(logger, top), daemon=True,
                     name="memstat-gc").start()


# ── Report ────────────────────────────────────────────────────────

def _deep_due(count: int) -> bool:
    """True when the *count*-th report should take the deep snapshot."""
    return count <= 1 or count % max(1, _deep_every) == 0


def report(logger, top: int = 12, deep: bool | None = None) -> None:
    """Log a compact memory snapshot (cheap; the deep part is threaded)."""
    global _report_count
    _report_count += 1
    deep_due = _deep_due(_report_count)
    if deep is None:
        deep = _deep
    try:
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (OSError, AttributeError):
        peak_kb = None

    main = _proc_mem(os.getpid())
    children = _children()
    widgets, views = _qt_counts()
    pixmap_limit = _pixmap_cache_limit()
    stacks = _loaded_stacks()
    traced, _peak = (tracemalloc.get_traced_memory()
                     if tracemalloc.is_tracing() else (0, 0))

    lines = [f"--- memory: rss={_fmt(main['rss'])} pss={_fmt(main['pss'])}"
             f" peak={_fmt(peak_kb)} traced={_fmt_bytes(traced)}"]
    lines.append(f"    main: private_dirty={_fmt(main['private_dirty'])}"
                 f" anonymous={_fmt(main['anonymous'])}"
                 f" shared_clean={_fmt(main['shared_clean'])}")

    by_type: dict[str, list[int]] = {}
    for _pid, ctype, _comm, crss, cpss in children:
        agg = by_type.setdefault(ctype, [0, 0])
        agg[0] += 1
        agg[1] += cpss if cpss is not None else (crss or 0)
    total_child = sum(kb for _count, kb in by_type.values())
    lines.append(f"    children: {len(children)} procs"
                 f" total={_fmt(total_child)}")
    for ctype, (count, kb) in sorted(by_type.items(),
                                     key=lambda kv: kv[1][1], reverse=True):
        lines.append(f"      {ctype}: {count} proc {_fmt(kb)}")
    # Per-process lines (top by memory) so a zygote fork's role and name are
    # visible even when the cmdline is inherited from the zygote.
    ranked = sorted(children,
                    key=lambda c: (c[4] if c[4] is not None else (c[3] or 0)),
                    reverse=True)
    for pid, ctype, comm, crss, cpss in ranked[:top]:
        lines.append(f"      child pid={pid} type={ctype}"
                     f" comm={comm or '?'} rss={_fmt(crss)} pss={_fmt(cpss)}")
    lines.append(f"    qt: widgets={widgets} webengine_views={views}"
                 f" pixmap_cache_limit={pixmap_limit}K")
    lines.append(f"    python: modules={len(sys.modules)}"
                 f" heavy=[{', '.join(stacks)}]")
    logger.info("\n".join(lines))

    if deep_due and deep and tracemalloc.is_tracing():
        _schedule_deep(logger, top)
    # A gc object-type breakdown is useful in both levels and does not inflate
    # memory; it follows the deep cadence and runs in a worker thread.
    if deep_due:
        _schedule_gc(logger, top)


def _fmt(kb):
    """Format a KiB value as MiB."""
    if kb is None:
        return "?"
    return f"{kb / 1024:.1f}M"


def _fmt_bytes(nbytes: int) -> str:
    """Format a byte value as MiB."""
    return f"{nbytes / (1024 * 1024):.1f}M"
