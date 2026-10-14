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

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All client-ping tests passed.")
