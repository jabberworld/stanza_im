"""Minimal dependency-free SOCKS5 client (RFC 1928).

Used to route the XMPP connection through a SOCKS5 proxy.  Only the
``CONNECT`` command with the "no authentication" method is implemented, which
covers ordinary SOCKS5 proxies offered to end users.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import struct

SOCKS_VERSION = 5
_AUTH_NONE = 0x00
_AUTH_NO_ACCEPTABLE = 0xFF
_CMD_CONNECT = 0x01
_ATYP_IPV4 = 0x01
_ATYP_DOMAIN = 0x03
_ATYP_IPV6 = 0x04
_REP_SUCCESS = 0x00


class Socks5Error(OSError):
    """Raised when the SOCKS5 handshake or connect request fails."""


async def _recv_exact(loop: asyncio.AbstractEventLoop, sock: socket.socket,
                      count: int) -> bytes:
    """Read exactly *count* bytes from a non-blocking socket."""
    chunks = bytearray()
    while len(chunks) < count:
        chunk = await loop.sock_recv(sock, count - len(chunks))
        if not chunk:
            raise Socks5Error("SOCKS5 proxy closed the connection")
        chunks.extend(chunk)
    return bytes(chunks)


def _connect_request(target_host: str, target_port: int) -> bytes:
    """Build a SOCKS5 CONNECT request, using an IP literal when possible."""
    try:
        ip = ipaddress.ip_address(target_host)
    except ValueError:
        ip = None
    header = bytes([SOCKS_VERSION, _CMD_CONNECT, 0x00])
    if ip is not None:
        atyp = _ATYP_IPV4 if ip.version == 4 else _ATYP_IPV6
        return header + bytes([atyp]) + ip.packed + struct.pack("!H", target_port)
    host_bytes = target_host.encode("idna")
    if len(host_bytes) > 255:
        raise Socks5Error("Target host name is too long")
    return (header + bytes([_ATYP_DOMAIN, len(host_bytes)]) + host_bytes
            + struct.pack("!H", target_port))


async def connect_via_socks5(loop: asyncio.AbstractEventLoop,
                             proxy_host: str, proxy_port: int,
                             target_host: str, target_port: int,
                             timeout: float = 20.0) -> socket.socket:
    """Open a TCP connection to *target_host:target_port* through a SOCKS5
    proxy and return the connected, non-blocking socket.

    The caller is responsible for wrapping the socket with TLS if needed
    (e.g. ``loop.create_connection(..., sock=sock, ssl=...)``).
    """
    target_port = int(target_port)
    proxy_port = int(proxy_port)
    sock: socket.socket | None = None

    async def _handshake() -> None:
        # Method negotiation: offer "no authentication".
        await loop.sock_sendall(sock, bytes([SOCKS_VERSION, 1, _AUTH_NONE]))
        reply = await _recv_exact(loop, sock, 2)
        if reply[0] != SOCKS_VERSION:
            raise Socks5Error("Unsupported SOCKS version from proxy")
        if reply[1] == _AUTH_NO_ACCEPTABLE:
            raise Socks5Error("SOCKS5 proxy requires authentication")
        if reply[1] != _AUTH_NONE:
            raise Socks5Error(f"Unsupported SOCKS5 auth method: {reply[1]:#x}")

        await loop.sock_sendall(sock, _connect_request(target_host, target_port))

        head = await _recv_exact(loop, sock, 4)
        if head[0] != SOCKS_VERSION:
            raise Socks5Error("Unsupported SOCKS version in reply")
        if head[1] != _REP_SUCCESS:
            raise Socks5Error(
                f"SOCKS5 proxy refused the connection (code {head[1]})")
        atyp = head[3]
        if atyp == _ATYP_IPV4:
            await _recv_exact(loop, sock, 4 + 2)
        elif atyp == _ATYP_IPV6:
            await _recv_exact(loop, sock, 16 + 2)
        elif atyp == _ATYP_DOMAIN:
            length = (await _recv_exact(loop, sock, 1))[0]
            await _recv_exact(loop, sock, length + 2)
        else:
            raise Socks5Error(f"Unknown SOCKS5 address type: {atyp:#x}")

    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(proxy_host, proxy_port,
                             type=socket.SOCK_STREAM), timeout)
        family = infos[0][0]
        sockaddr = infos[0][4]
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.setblocking(False)
        await asyncio.wait_for(loop.sock_connect(sock, sockaddr), timeout)
        await asyncio.wait_for(_handshake(), timeout)
    except Exception:
        if sock is not None:
            sock.close()
        raise
    return sock
