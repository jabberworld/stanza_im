"""Discovery/auto-detection tests: 4-variant logic, cache TTL, SRV order.

Run with:
    python3 tests/test_discovery.py
"""
import asyncio
import os
import sys
import tempfile
import time
import types

_SCRATCH = tempfile.mkdtemp(prefix="stanza_disc_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core import discovery

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── effective_endpoint: the four variants ─────────────────────────

auto = {"jid": "proxy.example.org", "host": "proxy.example.org", "port": 7777}
check("auto + found -> discovered endpoint",
      discovery.effective_endpoint("auto", "", auto)
      == "proxy.example.org:7777")
check("auto + not found -> direct",
      discovery.effective_endpoint("auto", "", None) is None)
check("manual + filled -> manual value wins over auto",
      discovery.effective_endpoint("manual", "proxy.local:1080", auto)
      == "proxy.local:1080")
check("manual + empty -> direct",
      discovery.effective_endpoint("manual", "   ", auto) is None)


# ── DiscoveryCache: freshness and negative results ────────────────

cache = discovery.DiscoveryCache(os.path.join(_SCRATCH, "disc.json"))
check("cache: miss before any write", cache.get("file_proxy") == (False, None))
cache.put("file_proxy", auto)
fresh, value = cache.get("file_proxy")
check("cache: fresh hit", fresh and value == auto)
cache.put("stun_turn", [])
fresh, value = cache.get("stun_turn")
check("cache: cached negative result is fresh", fresh and value == [])

cache._data["file_proxy"] = {"fetched_at": time.time() - 1000, "value": auto}
check("cache: stale entry expires",
      cache.get("file_proxy", max_age=10) == (False, None))

reloaded = discovery.DiscoveryCache(os.path.join(_SCRATCH, "disc.json"))
check("cache: persisted to disk", reloaded.get("stun_turn") == (True, []))


# ── STUN/TURN SRV ordering ────────────────────────────────────────

class Record:
    def __init__(self, host, port, priority=0, weight=0):
        self.host = host
        self.port = port
        self.priority = priority
        self.weight = weight


class FakeResolver:
    def __init__(self, loop=None, nameservers=None, **kwargs):
        pass

    async def query(self, name, rtype):
        if name.startswith("_turns"):
            return [Record("turn.example.org.", 5349)]
        if name.startswith("_turn._udp"):
            return [Record("turn-a.example.org.", 3478, priority=20),
                    Record("turn-b.example.org.", 3478, priority=10)]
        if name.startswith("_stun._udp"):
            return [Record("stun.example.org.", 3478)]
        raise OSError("no such record")


original_aiodns = discovery.aiodns
original_has = discovery.HAS_AIODNS
discovery.aiodns = types.SimpleNamespace(DNSResolver=FakeResolver)
discovery.HAS_AIODNS = True
try:
    result = asyncio.run(discovery.discover_stun_turn("example.org"))
finally:
    discovery.aiodns = original_aiodns
    discovery.HAS_AIODNS = original_has

services = [entry["service"] for entry in result]
check("srv: encrypted queried before plain",
      services[:2] == ["_turns._tcp", "_turn._udp"])
check("srv: tls flag on turns", result[0]["tls"] is True)
check("srv: turn sorted by DNS priority",
      [e["host"] for e in result if e["service"] == "_turn._udp"]
      == ["turn-b.example.org", "turn-a.example.org"])
check("srv: stun last", services[-1] == "_stun._udp")

check("srv: query order constant",
      discovery.SRV_SERVICES == ("_turns._tcp", "_stuns._tcp", "_turn._tcp",
                                 "_turn._udp", "_stun._tcp", "_stun._udp"))


# ── refresh uses a fresh cache without touching the network ───────

cache2 = discovery.DiscoveryCache(os.path.join(_SCRATCH, "disc2.json"))
cache2.put("file_proxy", {"jid": "proxy.example.org",
                          "host": "proxy.example.org", "port": 7777})
cache2.put("stun_turn", [{"service": "_stuns._tcp",
                          "host": "stun.example.org", "port": 5349}])


class BoomXmpp:
    def __getitem__(self, key):
        raise AssertionError("disco must not run on a fresh cache")


result = asyncio.run(discovery.refresh(BoomXmpp(), "example.org", cache2))
check("refresh: file proxy from cache",
      result["file_proxy"]["jid"] == "proxy.example.org")
check("refresh: stun/turn from cache",
      result["stun_turn"][0]["service"] == "_stuns._tcp")


print("\nAll tests passed ✓" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)
