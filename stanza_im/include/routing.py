"""Local source-address selection based on the kernel routing table.

ICE candidate gathering in ``aioice`` enumerates every adapter address with
``ifaddr``.  That includes addresses on link-down bridges (Docker, LXC,
host-only adapters, ...), although the routing table would never use them for
the peer.  The helpers here ask the kernel which source address it selects for
the default route, without sending any packets.
"""
from __future__ import annotations

import ipaddress
import socket

#: Public destinations used only for a route lookup; ``SOCK_DGRAM.connect``
#: does not send a packet and returns the local source address.
_IPV4_PROBE = ("1.1.1.1", 80)
_IPV6_PROBE = ("2606:4700:4700::1111", 80)


def _version(address: str) -> int:
    try:
        return ipaddress.ip_address(str(address)).version
    except ValueError:
        return 0


def route_source(family: int) -> str:
    """The local source address chosen for the default route of *family*.

    Returns an empty string when the family has no usable default route.  A
    UDP ``connect`` only performs the kernel route lookup; it sends no traffic.
    """
    target = _IPV4_PROBE if family == socket.AF_INET else _IPV6_PROBE
    sock = None
    try:
        sock = socket.socket(family, socket.SOCK_DGRAM)
        sock.settimeout(0.25)
        sock.connect(target)
        address = str(sock.getsockname()[0] or "")
        if not address or address.startswith("127.") or address == "::1":
            return ""
        return address
    except OSError:
        return ""
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def select_host_addresses(addresses, source_ipv4: str = "",
                          source_ipv6: str = "") -> list[str]:
    """Prefer the route-selected source; fall back to the original list.

    A preferred IPv4 source intentionally removes other IPv4 candidates.  A
    missing IPv6 default route removes link-local IPv6 candidates.  If no
    source can be determined at all, the original list is returned unchanged
    so LAN-only/offline setups keep working.
    """
    original = [str(address) for address in addresses if address]
    if not original:
        return []
    if not source_ipv4 and not source_ipv6:
        return original
    ipv4 = [address for address in original if _version(address) == 4]
    ipv6 = [address for address in original if _version(address) == 6]
    selected: list[str] = []
    if source_ipv4:
        selected.append(source_ipv4)
    elif ipv4:
        selected.extend(ipv4)
    if source_ipv6:
        selected.append(source_ipv6)
    # No IPv6 default route: do not advertise link-local IPv6 addresses.
    if selected:
        return list(dict.fromkeys(selected))
    return original
