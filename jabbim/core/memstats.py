"""Memory statistics — RSS, peak usage, Python allocation traces.

Enabled by the ``--memstat`` / ``-m`` command-line flag.  Reports are
written to the given logger; ``tracemalloc`` gives Python-level insight
while raw RSS (via /proc) also covers native/Chromium (QtWebEngine)
memory of the own process.
"""
from __future__ import annotations

import os
import resource
import tracemalloc

_PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") or 4096


def start_tracking(nframe: int = 12) -> None:
    """Begin tracing Python allocations (cheap enough for opt-in mode)."""
    if not tracemalloc.is_tracing():
        tracemalloc.start(nframe)


def _rss_kb() -> int | None:
    """Resident set size of the current process in KiB, from /proc/statm."""
    try:
        with open("/proc/self/statm", "r", encoding="ascii") as fh:
            resident_pages = int(fh.read().split()[1])
        return resident_pages * _PAGE_SIZE // 1024
    except (OSError, ValueError, IndexError):
        return None


def _child_rss_kb() -> list[tuple[int, int]]:
    """(pid, rss_kb) for direct child processes (WebEngine's Chromium)."""
    children: list[tuple[int, int]] = []
    my_pid = os.getpid()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return children
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "r", encoding="ascii") as fh:
                fields = fh.read().split(") ")
                stat = fields[-1].split()
                # stat fields after the comm): state(1) ppid(2) ... rss(23)
                if len(stat) > 23 and int(stat[1]) == my_pid:
                    rss_pages = int(stat[22])
                    children.append((int(entry), rss_pages * _PAGE_SIZE // 1024))
        except (OSError, ValueError, IndexError):
            continue
    return sorted(children, key=lambda p: p[1], reverse=True)


def report(logger, top: int = 12) -> None:
    """Log a compact memory snapshot."""
    try:
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (OSError, AttributeError):
        peak_kb = None

    rss = _rss_kb()
    traced, traced_peak = (tracemalloc.get_traced_memory()
                           if tracemalloc.is_tracing() else (0, 0))
    children = _child_rss_kb()
    child_kb = sum(kb for _, kb in children)

    lines = [f"--- memory: rss={_fmt(rss)}B"
             f" peak={_fmt(peak_kb)}B"
             f" traced={_fmt(traced)}B"
             f" traced_peak={_fmt(traced_peak)}B"
             f" widgets={_widget_count()}"
             f" children={len(children)}"]
    if children:
        joined = ", ".join(f"pid {pid}: {_fmt(kb)}B" for pid, kb in children[:5])
        lines.append(f"    child total={_fmt(child_kb)}B [{joined}]")

    if tracemalloc.is_tracing():
        snapshot = tracemalloc.take_snapshot()
        stats = snapshot.statistics("traceback")
        lines.append("    top Python allocations:")
        for stat in stats[:top]:
            frame = stat.traceback[0]
            lines.append(f"      {_fmt(stat.size)}B "
                         f"{os.path.basename(frame.filename)}:{frame.lineno} "
                         f"x{stat.count}")
    logger.info("\n".join(lines))


def _fmt(kb):
    if kb is None:
        return "?"
    mb = kb / 1024
    return f"{mb:.1f}M"


def _widget_count() -> int:
    try:
        from PyQt6 import QtWidgets
        app = QtWidgets.QApplication.instance()
        return len(app.allWidgets()) if app is not None else -1
    except Exception:
        return -1