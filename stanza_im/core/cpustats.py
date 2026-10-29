"""Periodic CPU statistics for the ``-C``/``--cpustat`` diagnostic mode.

The cheap ``-m`` report only covers memory.  This module deliberately lives
beside it and uses the same periodicity, but reads ``/proc`` CPU counters
instead of RSS/PSS.  ``-C`` reports the process and its busiest threads;
``-CC`` additionally lists every child process (WebEngine renderer/GPU/utility
and other helpers).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

logger = logging.getLogger("stanza_im.cpustats")

CLOCK_TICKS = int(os.sysconf("SC_CLK_TCK") or 100)


@dataclass(frozen=True)
class _CpuSnapshot:
    at: float
    total: int
    threads: dict[int, tuple[str, int]]
    children: dict[int, tuple[str, int]]


_last: _CpuSnapshot | None = None
_started_at: float | None = None


def _parse_stat(raw: str) -> tuple[str, int]:
    """Return ``(comm, utime+stime)`` from a ``/proc/<pid>/stat`` line."""
    raw = str(raw or "").strip()
    end = raw.rfind(")")
    start = raw.find("(")
    if start < 0 or end <= start:
        raise ValueError("invalid /proc stat")
    comm = raw[start + 1:end]
    fields = raw[end + 1:].split()
    # fields[0] is state (field 3); utime/stime are fields 14/15.
    return comm, int(fields[11]) + int(fields[12])


def _read_stat(path: str) -> tuple[str, int] | None:
    try:
        with open(path, "r", encoding="ascii", errors="replace") as fh:
            return _parse_stat(fh.read())
    except (OSError, ValueError, IndexError):
        return None


def _read_comm(path: str, fallback: str = "") -> str:
    try:
        with open(path, "r", encoding="ascii", errors="replace") as fh:
            name = fh.read().strip()
        if name:
            return name
    except OSError:
        pass
    return fallback


def _threads(pid: int, root: str) -> dict[int, tuple[str, int]]:
    directory = os.path.join(root, str(pid), "task")
    out: dict[int, tuple[str, int]] = {}
    try:
        entries = os.listdir(directory)
    except OSError:
        return out
    for entry in entries:
        if not entry.isdigit():
            continue
        tid = int(entry)
        path = os.path.join(directory, entry, "stat")
        parsed = _read_stat(path)
        if parsed is None:
            continue
        comm, ticks = parsed
        comm = _read_comm(os.path.join(directory, entry, "comm"), comm)
        out[tid] = (comm, ticks)
    return out


def _proc_tree(root: str) -> dict[int, list[int]]:
    tree: dict[int, list[int]] = {}
    try:
        entries = os.listdir(root)
    except OSError:
        return tree
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        parsed = _read_stat(os.path.join(root, entry, "stat"))
        if parsed is None:
            continue
        try:
            with open(os.path.join(root, entry, "stat"), "r",
                      encoding="ascii", errors="replace") as fh:
                raw = fh.read()
            end = raw.rfind(")")
            fields = raw[end + 1:].split()
            ppid = int(fields[1])
        except (OSError, ValueError, IndexError):
            continue
        tree.setdefault(ppid, []).append(pid)
    return tree


def _descendants(tree: dict[int, list[int]], root: int) -> list[int]:
    seen: set[int] = {root}
    queue = list(tree.get(root, []))
    out: list[int] = []
    while queue:
        pid = queue.pop()
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
        queue.extend(tree.get(pid, []))
    return out


def _children(pid: int, root: str) -> dict[int, tuple[str, int]]:
    out: dict[int, tuple[str, int]] = {}
    tree = _proc_tree(root)
    for child in _descendants(tree, pid):
        parsed = _read_stat(os.path.join(root, str(child), "stat"))
        if parsed is None:
            continue
        comm, ticks = parsed
        out[child] = (comm, ticks)
    return out


def _read_snapshot(pid: int | None = None,
                   root: str = "/proc") -> _CpuSnapshot | None:
    pid = int(pid or os.getpid())
    parsed = _read_stat(os.path.join(root, str(pid), "stat"))
    if parsed is None:
        return None
    _comm, total = parsed
    return _CpuSnapshot(
        at=time.monotonic(),
        total=total,
        threads=_threads(pid, root),
        children=_children(pid, root),
    )


def _percent(delta: int, interval: float) -> float:
    if interval <= 0:
        return 0.0
    return max(0, int(delta)) / CLOCK_TICKS / interval * 100.0


def start(pid: int | None = None, root: str = "/proc") -> None:
    """Take the baseline used by the first periodic report."""
    global _last, _started_at
    _last = _read_snapshot(pid, root)
    _started_at = time.monotonic()


def _delta(previous, current) -> int:
    return max(0, int(current) - int(previous or 0))


def report(logger=logger, top: int = 12, detailed: bool = False,
           pid: int | None = None, root: str = "/proc") -> None:
    """Log one CPU snapshot; safe to call before :func:`start`."""
    global _last
    current = _read_snapshot(pid, root)
    previous = _last
    _last = current
    if current is None:
        logger.info("--- cpu: unavailable")
        return
    if previous is None:
        previous = current
        interval = 0.0
        first = True
    else:
        interval = max(0.001, current.at - previous.at)
        first = _started_at is not None and previous.at <= _started_at + 0.1

    total = _percent(_delta(previous.total, current.total), interval)
    thread_rows = []
    for tid, (comm, ticks) in current.threads.items():
        before = previous.threads.get(tid, (comm, 0))[1]
        value = _percent(_delta(before, ticks), interval)
        if value > 0 or detailed:
            thread_rows.append((value, tid, comm))
    thread_rows.sort(key=lambda row: row[0], reverse=True)
    active = sum(1 for value, _tid, _comm in thread_rows if value > 0)
    label = "since start" if first else "%.1fs" % interval
    lines = [
        "--- cpu: total=%.1f%% interval=%s threads=%d active=%d" % (
            total, label, len(current.threads), active),
    ]
    if thread_rows:
        lines.append("    threads:")
        shown = thread_rows if detailed else thread_rows[:max(1, int(top))]
        for value, tid, comm in shown:
            lines.append("      tid=%s comm=%s cpu=%.1f%%" % (
                tid, comm or "?", value))
    child_rows = []
    for child, (comm, ticks) in current.children.items():
        before = previous.children.get(child, (comm, 0))[1]
        value = _percent(_delta(before, ticks), interval)
        child_rows.append((value, child, comm))
    child_rows.sort(key=lambda row: row[0], reverse=True)
    child_total = sum(value for value, _pid, _comm in child_rows)
    lines.append("    children: %d procs cpu=%.1f%%" % (
        len(child_rows), child_total))
    if detailed:
        for value, child, comm in child_rows:
            lines.append("      child pid=%s comm=%s cpu=%.1f%%" % (
                child, comm or "?", value))
    logger.info("\n".join(lines))
