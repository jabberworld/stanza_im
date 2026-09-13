"""SOCKS5 bytestream data transport (XEP-0065 / XEP-0260 / XEP-0261).

Two roles are implemented on top of the RFC 1928 handshake:

* **client** — connect to a streamhost (a proxy or a peer offering a ``direct``
  candidate) and perform the SOCKS5 ``CONNECT`` with
  ``DST.ADDR = SHA1(SID + Requester + Target)`` and ``DST.PORT = 0`` as required
  by XEP-0065.  The returned stream carries the raw bytestream.
* **server** — listen for an incoming ``direct`` candidate connection, accept
  the SOCKS5 handshake and hand the verified stream to the session.

Everything is asyncio-stream based so callers can ``read``/``write`` the file
data directly.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import socket
import struct

from stanza_im.xmpp import socks5

logger = logging.getLogger(__name__)

SOCKS_VERSION = 5
_AUTH_NONE = 0x00
_AUTH_NO_ACCEPTABLE = 0xFF
_CMD_CONNECT = 0x01
_ATYP_IPV4 = 0x01
_ATYP_DOMAIN = 0x03
_ATYP_IPV6 = 0x04
_REP_SUCCESS = 0x00


class BytestreamError(OSError):
    """Raised when the SOCKS5 bytestream handshake fails."""


def sha1_dst(sid: str, requester: str, target: str) -> str:
    """Hex ``SHA1(SID + Requester JID + Target JID)`` used as ``DST.ADDR``."""
    digest = hashlib.sha1()
    digest.update(str(sid).encode("utf-8"))
    digest.update(str(requester).encode("utf-8"))
    digest.update(str(target).encode("utf-8"))
    return digest.hexdigest()


def local_host_candidates() -> list[str]:
    """Best-effort list of this machine's non-loopback IPv4 addresses.

    Used to advertise ``direct`` candidates.  Never raises; an empty list just
    means no direct candidate can be offered.
    """
    hosts: list[str] = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None,
                                   socket.AF_INET, socket.SOCK_STREAM)
        for info in infos:
            addr = info[4][0]
            if addr and not addr.startswith("127.") and addr not in hosts:
                hosts.append(addr)
    except OSError:
        pass
    # Fallback: discover the outbound interface without sending any packet.
    if not hosts:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            addr = probe.getsockname()[0]
            if addr and not addr.startswith("127."):
                hosts.append(addr)
        except OSError:
            pass
        finally:
            probe.close()
    return hosts


async def _read_exact(reader: asyncio.StreamReader, count: int) -> bytes:
    try:
        return await reader.readexactly(count)
    except asyncio.IncompleteReadError as exc:
        raise BytestreamError("SOCKS5 peer closed the connection") from exc


async def connect_bytestream(proxy_host: str, proxy_port: int, dst_addr: str,
                             timeout: float = 20.0, loop=None
                             ) -> tuple[asyncio.StreamReader,
                                        asyncio.StreamWriter]:
    """Open a SOCKS5 bytestream to *proxy_host:proxy_port* for *dst_addr*.

    *dst_addr* is the hex SHA1 value; it is sent as a domain name with port 0.
    Returns the ``(reader, writer)`` pair ready for raw bytestream data.
    """
    proxy_port = int(proxy_port)
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(proxy_host, proxy_port), timeout)
    try:
        writer.write(bytes([SOCKS_VERSION, 1, _AUTH_NONE]))
        await writer.drain()
        reply = await asyncio.wait_for(_read_exact(reader, 2), timeout)
        if reply[0] != SOCKS_VERSION:
            raise BytestreamError("Unsupported SOCKS version from proxy")
        if reply[1] == _AUTH_NO_ACCEPTABLE:
            raise BytestreamError("SOCKS5 proxy requires authentication")
        if reply[1] != _AUTH_NONE:
            raise BytestreamError(
                f"Unsupported SOCKS5 auth method: {reply[1]:#x}")

        writer.write(socks5._connect_request(dst_addr, 0))
        await writer.drain()

        head = await asyncio.wait_for(_read_exact(reader, 4), timeout)
        if head[0] != SOCKS_VERSION:
            raise BytestreamError("Unsupported SOCKS version in reply")
        if head[1] != _REP_SUCCESS:
            raise BytestreamError(
                f"SOCKS5 proxy refused the connection (code {head[1]})")
        atyp = head[3]
        if atyp == _ATYP_IPV4:
            await _read_exact(reader, 4 + 2)
        elif atyp == _ATYP_IPV6:
            await _read_exact(reader, 16 + 2)
        elif atyp == _ATYP_DOMAIN:
            length = (await _read_exact(reader, 1))[0]
            await _read_exact(reader, length + 2)
        else:
            raise BytestreamError(f"Unknown SOCKS5 address type: {atyp:#x}")
        return reader, writer
    except Exception:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        raise


async def _server_handshake(reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter,
                            expected_dsts: set[str],
                            timeout: float = 20.0) -> str:
    """Accept a SOCKS5 ``CONNECT`` from a peer offering us a direct candidate.

    Returns the requested ``DST.ADDR`` after replying success.  Raises
    :class:`BytestreamError` (and the caller closes the stream) otherwise.
    """
    greeting = await asyncio.wait_for(_read_exact(reader, 2), timeout)
    if greeting[0] != SOCKS_VERSION:
        raise BytestreamError("Unsupported SOCKS version from peer")
    nmethods = greeting[1]
    methods = await asyncio.wait_for(_read_exact(reader, nmethods), timeout)
    if _AUTH_NONE not in methods:
        writer.write(bytes([SOCKS_VERSION, _AUTH_NO_ACCEPTABLE]))
        await writer.drain()
        raise BytestreamError("SOCKS5 peer offered no supported auth method")
    writer.write(bytes([SOCKS_VERSION, _AUTH_NONE]))
    await writer.drain()

    head = await asyncio.wait_for(_read_exact(reader, 4), timeout)
    if head[0] != SOCKS_VERSION or head[1] != _CMD_CONNECT:
        raise BytestreamError("Unsupported SOCKS5 command")
    atyp = head[3]
    if atyp == _ATYP_IPV4:
        dst = socket.inet_ntoa(await _read_exact(reader, 4))
    elif atyp == _ATYP_IPV6:
        dst = socket.inet_ntop(socket.AF_INET6,
                               await _read_exact(reader, 16))
    elif atyp == _ATYP_DOMAIN:
        length = (await _read_exact(reader, 1))[0]
        dst = (await _read_exact(reader, length)).decode("utf-8", "replace")
    else:
        raise BytestreamError(f"Unknown SOCKS5 address type: {atyp:#x}")
    await _read_exact(reader, 2)  # DST.PORT (always 0 for bytestreams)

    if dst not in expected_dsts:
        writer.write(bytes([SOCKS_VERSION, 0x02, 0x00, _ATYP_IPV4,
                            0, 0, 0, 0, 0, 0]))
        await writer.drain()
        raise BytestreamError("Unexpected SOCKS5 destination address")
    # Reply success with a dummy BND.ADDR/BND.PORT.
    writer.write(bytes([SOCKS_VERSION, _REP_SUCCESS, 0x00, _ATYP_IPV4,
                        0, 0, 0, 0, 0, 0]))
    await writer.drain()
    return dst


async def listen_for_bytestream(expected_dsts: set[str], on_connected,
                                host: str = "0.0.0.0",
                                ) -> tuple[asyncio.AbstractServer, int]:
    """Start a listener accepting a SOCKS5 bytestream for a direct candidate.

    *on_connected* is awaited with ``(reader, writer)`` once the handshake is
    verified.  Returns ``(server, port)``; the caller closes the server when the
    session is over.
    """
    async def _handler(reader: asyncio.StreamReader,
                       writer: asyncio.StreamWriter) -> None:
        try:
            await _server_handshake(reader, writer, expected_dsts)
        except Exception as exc:  # noqa: BLE001 - bad peer, just drop it
            logger.debug("Rejected bytestream connection: %s", exc)
            writer.close()
            return
        try:
            await on_connected(reader, writer)
        except Exception:
            logger.exception("Bytestream handler failed")
            writer.close()

    server = await asyncio.start_server(_handler, host, 0)
    port = server.sockets[0].getsockname()[1]
    return server, int(port)


def is_local_address(host: str) -> bool:
    """True when *host* is a usable non-loopback address for a candidate."""
    try:
        return ipaddress.ip_address(host).is_loopback is False
    except ValueError:
        return bool(host)
