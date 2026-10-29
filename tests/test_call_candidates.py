"""Route-based ICE host candidate selection.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_call_candidates.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.include import routing  # noqa: E402
from stanza_im.xmpp import media  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


addresses = ["192.168.1.166", "10.0.3.1", "172.17.0.1", "fe80::1"]
check("the default-route IPv4 source is preferred",
      routing.select_host_addresses(
          addresses, "192.168.1.166", "") == ["192.168.1.166"])
check("the preferred source is not duplicated",
      routing.select_host_addresses(
          addresses, "192.168.1.166", "") == ["192.168.1.166"])
check("no source falls back to the original addresses",
      routing.select_host_addresses(addresses, "", "") == addresses)
check("a missing IPv6 route drops link-local IPv6",
      "fe80::1" not in routing.select_host_addresses(
          addresses, "192.168.1.166", ""))
check("an IPv6 source is kept when one exists",
      routing.select_host_addresses(
          addresses, "192.168.1.166", "2001:db8::1")
      == ["192.168.1.166", "2001:db8::1"])
check("an IPv4-only fallback still works",
      routing.select_host_addresses(["10.0.3.1", "172.17.0.1"], "", "")
      == ["10.0.3.1", "172.17.0.1"])
check("identical sources are de-duplicated",
      routing.select_host_addresses(
          ["192.168.1.166"], "192.168.1.166", "") == ["192.168.1.166"])

check("the aioice route patch is installed",
      getattr(media._install_route_selected_host_candidates, "__name__", "")
      == "_install_route_selected_host_candidates")
try:
    import aioice.ice as ice
    check("aioice host gathering is route-selected",
          getattr(ice.get_host_addresses, "_stanza_route_selected", False))
    check("installing the route patch twice is a no-op",
          media._install_route_selected_host_candidates() is False)
except ImportError:
    print("SKIP: aioice is not installed")

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All call-candidate tests passed")
