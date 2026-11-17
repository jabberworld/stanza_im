"""Bounded XEP-0490/MAM reconciliation (startup CPU guard).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_startup_mds.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.ui.main_window import MainWindow, _MDS_CONCURRENCY


FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Probe:
    def __init__(self):
        self._mds_semaphore = asyncio.Semaphore(_MDS_CONCURRENCY)
        self.active = 0
        self.peak = 0
        self.done = 0

    def _mds_foreground(self, _key):
        return True

    async def _clamp_read_state(self, _key, _sid, *, force=False):
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        self.done += 1


async def _run_many():
    probe = _Probe()
    await asyncio.gather(*[
        MainWindow._run_mds_clamp(probe, f"chat{i}@example.com", f"sid{i}")
        for i in range(12)
    ])
    return probe


probe = asyncio.run(_run_many())
check("the MDS pool is bounded", _MDS_CONCURRENCY >= 1)
check("every scheduled clamp ran", probe.done == 12)
check("no more than the configured number run at once",
      probe.peak <= _MDS_CONCURRENCY)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All startup-MDS tests passed.")
