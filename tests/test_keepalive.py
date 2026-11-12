"""Whitespace keepalive must stay below common server idle timeouts.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_keepalive.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_keepalive_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core.client import JabberClient

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


client = JabberClient("u@example.org", "p")
check("keepalive is enabled by default",
      client.xmpp.whitespace_keepalive is True)
check("keepalive interval is 60 seconds",
      client.xmpp.whitespace_keepalive_interval == 60)
check("keepalive interval is below the 2-minute idle timeout",
      client.xmpp.whitespace_keepalive_interval < 120)
check("keepalive interval is the shared constant",
      client.xmpp.whitespace_keepalive_interval
      == JabberClient.KEEPALIVE_INTERVAL_S)

quiet = JabberClient("u@example.org", "p", keepalive=False)
check("keepalive can still be disabled",
      quiet.xmpp.whitespace_keepalive is False)
check("interval is configured even when keepalive is off",
      quiet.xmpp.whitespace_keepalive_interval
      == JabberClient.KEEPALIVE_INTERVAL_S)

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All tests passed")
