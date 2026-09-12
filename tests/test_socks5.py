"""SOCKS5 connector tests (no network; fake loop and socket).

Run with:
    python3 tests/test_socks5.py
"""
import asyncio
import os
import struct
import sys
import tempfile
import types
from unittest import mock

_SCRATCH = tempfile.mkdtemp(prefix="stanza_socks_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.xmpp import socks5

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class FakeSocket:
    def __init__(self, *args, **kwargs):
        self.sent = []
        self.closed = False
        self.blocking = None

    def setblocking(self, value):
        self.blocking = value

    def close(self):
        self.closed = True


class FakeLoop:
    """Streams pre-seeded bytes and records sent data."""

    def __init__(self, replies):
        self.buffer = b"".join(replies)
        self.addr = None
        self.proxy = None
        self.socks = []

    async def getaddrinfo(self, host, port, type=None):
        self.proxy = (host, port)
        return [(2, 1, 6, "", ("127.0.0.1", port))]

    async def sock_connect(self, sock, addr):
        self.addr = addr
        self.socks.append(sock)

    async def sock_sendall(self, sock, data):
        sock.sent.append(data)

    async def sock_recv(self, sock, count):
        chunk = self.buffer[:count]
        self.buffer = self.buffer[count:]
        return chunk


def run_connector(replies, target_host="example.org", target_port=5222):
    loop = FakeLoop(replies)
    fake_socket_module = types.SimpleNamespace(
        socket=FakeSocket, AF_INET=2, SOCK_STREAM=1)
    with mock.patch.object(socks5, "socket", fake_socket_module):
        async def main():
            return await socks5.connect_via_socks5(
                loop, "proxy.example.net", 1080, target_host, target_port)
        try:
            sock = asyncio.run(main())
            return loop, sock, None
        except Exception as exc:  # noqa: BLE001 - reported by the caller
            return loop, None, exc


# ── Successful CONNECT ─────────────────────────────────────────────

loop, sock, err = run_connector([
    b"\x05\x00",                                  # no-auth accepted
    b"\x05\x00\x00\x01",                          # success, IPv4 bound
    b"\x7f\x00\x00\x01\x1f\x90",                 # 127.0.0.1:8080
])
check("success: returns a socket", sock is not None and err is None)
check("success: connects to proxy", loop.proxy == ("proxy.example.net", 1080))
check("success: greeting offers no-auth",
      sock is not None and sock.sent[0] == b"\x05\x01\x00")
expected_request = (b"\x05\x01\x00\x03" + bytes([len(b"example.org")])
                    + b"example.org" + struct.pack("!H", 5222))
check("success: CONNECT request well-formed",
      sock is not None and len(sock.sent) == 2
      and sock.sent[1] == expected_request)
check("success: socket left open", sock is not None and not sock.closed)
check("success: non-blocking socket", sock is not None and sock.blocking is False)


# ── Proxy requires authentication ─────────────────────────────────

loop, sock, err = run_connector([b"\x05\xff"])
check("auth-required: raises Socks5Error", isinstance(err, socks5.Socks5Error))
check("auth-required: socket closed",
      bool(loop.socks) and loop.socks[0].closed)


# ── Connection refused by proxy ───────────────────────────────────

loop, sock, err = run_connector([
    b"\x05\x00",
    b"\x05\x05\x00\x01",                          # rep = connection refused
])
check("refused: raises Socks5Error", isinstance(err, socks5.Socks5Error))


# ── Domain reply address consumed ─────────────────────────────────

loop, sock, err = run_connector([
    b"\x05\x00",
    b"\x05\x00\x00\x03",                          # success, domain bound
    bytes([11]) + b"bound.local" + b"\x00\x50",
])
check("domain-bound: returns a socket", sock is not None and err is None)


# ── CONNECT request address types ─────────────────────────────────

req4 = socks5._connect_request("1.2.3.4", 5222)
check("ipv4 literal -> ATYP ipv4",
      req4 == b"\x05\x01\x00\x01" + bytes([1, 2, 3, 4]) + struct.pack("!H", 5222))
req6 = socks5._connect_request("::1", 5222)
check("ipv6 literal -> ATYP ipv6",
      req6 == b"\x05\x01\x00\x04" + bytes(15) + b"\x01"
      + struct.pack("!H", 5222))
req_name = socks5._connect_request("example.org", 5222)
check("hostname -> ATYP domain", req_name[3] == 0x03)


print("\nAll tests passed ✓" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)
