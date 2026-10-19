"""Tests for the client-ping target helper (no Qt needed).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_client_ping.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core.client import JabberClient

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Contact:
    def __init__(self, resources):
        self.resources = resources


class _Fake:
    def __init__(self, resources, groupchats=None):
        self._contact = _Contact(resources)
        self.groupchats = groupchats or {}

    def get_contact(self, bare):
        return self._contact


def best(resources, groupchats=None, bare="bob@example.com"):
    return JabberClient.best_full_jid(_Fake(resources, groupchats), bare)


# Highest-priority online resource wins.
check("picks the highest-priority online resource",
      best({"laptop": {"show": "online", "priority": 5},
            "phone": {"show": "online", "priority": 10}})
      == "bob@example.com/phone")

# A single online resource.
check("single online resource",
      best({"laptop": {"show": "away", "priority": 1}})
      == "bob@example.com/laptop")

# All resources offline -> no target (ping skipped).
check("offline resources yield no target",
      best({"laptop": {"show": "offline", "priority": 99},
            "phone": {"show": "unavailable", "priority": 1}}) == "")

# No resources at all.
check("no resources yields no target", best({}) == "")

# A conference never gets a client target.
check("a conference is never a ping target",
      best({"laptop": {"show": "online"}},
           groupchats={"bob@example.com": object()}) == "")

# A resource with no name is skipped.
check("nameless resource is skipped",
      best({"": {"show": "online", "priority": 50}}) == "")


# ── probe_resource_versions forces a fresh lookup for every resource ────────
import asyncio  # noqa: E402


class _VerClient:
    def __init__(self, resources):
        self._contact = _Contact(resources)
        self.calls = []

    def get_contact(self, bare):
        return self._contact

    async def _prefetch_version(self, full_jid):
        self.calls.append(full_jid)


vc = _VerClient({"laptop": {}, "phone": {}, "": {}})
asyncio.run(JabberClient.probe_resource_versions(vc, "bob@example.com"))
check("probe_resource_versions hits every named resource",
      sorted(vc.calls) == ["bob@example.com/laptop", "bob@example.com/phone"])
check("probe_resource_versions tolerates an empty bare",
      asyncio.run(JabberClient.probe_resource_versions(vc, "")) is None)


# ── ensure_contact_version re-looks up resources missing client/time ───────
class _VerClient2:
    groupchats: dict = {}

    def __init__(self, resources):
        self._contact = _Contact(resources)
        self.calls = []

    def get_contact(self, bare):
        return self._contact

    def _prefetch_version(self, full_jid):   # eager: _start_task is a no-op
        self.calls.append(full_jid)

    def _start_task(self, coro):
        return None


vc2 = _VerClient2({"laptop": {"client": "Gajim", "client_tzo": "+03:00"},
                   "phone": {}, "": {}})
JabberClient.ensure_contact_version(vc2, "bob@example.com")
check("ensure_contact_version skips resources with client+time",
      "bob@example.com/laptop" not in vc2.calls)
check("ensure_contact_version looks up a resource missing client/time",
      vc2.calls == ["bob@example.com/phone"])
vc2.calls.clear()
JabberClient.ensure_contact_version(vc2, "")
check("ensure_contact_version ignores an empty bare", vc2.calls == [])


# ── a failed lookup clears the once-per-session guard ──────────────────────
class _PrefetchClient:
    groupchats: dict = {}

    def __init__(self):
        self.presences = {}
        self._version_inflight = set()
        self._version_probed = {"bob@example.com/phone"}
        self._contact = _Contact({"phone": {}})
        self.emitted = []

    def get_contact(self, bare):
        return self._contact

    async def get_entity_version(self, jid):
        return {}

    async def _entity_tzo(self, jid):
        return ""

    def emit(self, name, *args):
        self.emitted.append((name, args))


pc = _PrefetchClient()
asyncio.run(JabberClient._prefetch_version(pc, "bob@example.com/phone"))
check("a failed version lookup clears the guard so a later presence retries",
      "bob@example.com/phone" not in pc._version_probed)
check("a failed lookup still notifies the vCard",
      ("contact_client_updated", ("bob@example.com",)) in pc.emitted)

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All client-ping tests passed.")
