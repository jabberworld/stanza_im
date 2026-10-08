"""Minimal pure-Python QR Code encoder (byte mode, ECC level L).

Enough for the OMEMO fingerprint (a short ASCII string): versions 1–5, one
Reed-Solomon block per symbol, a fixed mask.  The mask reference is written to
the format information, so any decoder can read it back.

Reference: ISO/IEC 18004.  This is a small self-contained implementation so the
client needs no third-party QR dependency.
"""
from __future__ import annotations

# Total codewords and ECC codewords per version (ECC level L, single block).
_TOTAL_CODEWORDS = {1: 26, 2: 44, 3: 70, 4: 100, 5: 134}
_ECC_CODEWORDS = {1: 7, 2: 10, 3: 15, 4: 20, 5: 26}
_ALIGNMENT = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30]}

_MASK = 0  # fixed mask pattern (reference is encoded in the format info)


# ── GF(256) / Reed-Solomon ──────────────────────────────────────────────────

def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z & 0xFF


def _rs_generator(degree: int) -> list[int]:
    result = [1]
    root = 1
    for _ in range(degree):
        # multiply result by (x - root)
        new = [0] * (len(result) + 1)
        for i, coeff in enumerate(result):
            new[i] ^= coeff
            new[i + 1] ^= _gf_mul(coeff, root)
        result = new
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data: list[int], degree: int) -> list[int]:
    gen = _rs_generator(degree)
    rem = [0] * degree
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        for i in range(degree):
            rem[i] ^= _gf_mul(gen[i + 1], factor)
    return rem


# ── bit buffer ──────────────────────────────────────────────────────────────

class _Bits:
    def __init__(self) -> None:
        self.bits: list[int] = []

    def append(self, value: int, length: int) -> None:
        for i in range(length - 1, -1, -1):
            self.bits.append((value >> i) & 1)

    def to_bytes(self) -> list[int]:
        out = []
        for i in range(0, len(self.bits), 8):
            chunk = self.bits[i:i + 8]
            byte = 0
            for bit in chunk:
                byte = (byte << 1) | bit
            out.append(byte)
        return out


# ── encoding ────────────────────────────────────────────────────────────────

def _pick_version(nbytes: int) -> int:
    for version in range(1, 6):
        data_codewords = _TOTAL_CODEWORDS[version] - _ECC_CODEWORDS[version]
        # 4 bits mode + 8 bits count + payload, rounded up to whole codewords.
        needed = (4 + 8 + nbytes * 8 + 7) // 8
        if needed <= data_codewords:
            return version
    raise ValueError("QR: data too long for supported versions (max 108 bytes)")


def _codewords(data: bytes, version: int) -> list[int]:
    data_codewords = _TOTAL_CODEWORDS[version] - _ECC_CODEWORDS[version]
    bits = _Bits()
    bits.append(0b0100, 4)               # byte mode
    bits.append(len(data), 8)            # char count (V1-9: 8 bits)
    for byte in data:
        bits.append(byte, 8)
    # terminator + pad to a codeword boundary
    capacity = data_codewords * 8
    bits.append(0, min(4, capacity - len(bits.bits)))
    while len(bits.bits) % 8:
        bits.bits.append(0)
    codewords = bits.to_bytes()
    pad = (0xEC, 0x11)
    i = 0
    while len(codewords) < data_codewords:
        codewords.append(pad[i % 2])
        i += 1
    ecc = _rs_remainder(codewords, _ECC_CODEWORDS[version])
    return codewords + ecc


# ── matrix construction ─────────────────────────────────────────────────────

def _new_matrix(size: int):
    return [[None] * size for _ in range(size)]


def _place_finder(m, row: int, col: int) -> None:
    for dr in range(-1, 8):
        for dc in range(-1, 8):
            r, c = row + dr, col + dc
            if 0 <= r < len(m) and 0 <= c < len(m):
                dark = (0 <= dr <= 6 and dc in (0, 6)) or \
                       (0 <= dc <= 6 and dr in (0, 6)) or \
                       (2 <= dr <= 4 and 2 <= dc <= 4)
                m[r][c] = dark


def _place_alignment(m, centers: list[int]) -> None:
    size = len(m)
    for r in centers:
        for c in centers:
            if m[r][c] is not None:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    dark = max(abs(dr), abs(dc)) != 1
                    m[r + dr][c + dc] = dark


def _place_timing(m) -> None:
    size = len(m)
    for i in range(8, size - 8):
        bit = i % 2 == 0
        if m[6][i] is None:
            m[6][i] = bit
        if m[i][6] is None:
            m[i][6] = bit


def _reserve_format(m) -> None:
    size = len(m)
    for i in range(9):
        if i != 6:
            if m[8][i] is None:
                m[8][i] = False
            if m[i][8] is None:
                m[i][8] = False
    for i in range(8):
        m[8][size - 1 - i] = False
        m[size - 1 - i][8] = False
    m[size - 8][8] = True  # dark module


def _format_bits(ecc_level: int, mask: int) -> int:
    data = (ecc_level << 3) | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return ((data << 10) | rem) ^ 0x5412


def _place_format(m, ecc_level: int = 1) -> None:
    size = len(m)
    bits = _format_bits(ecc_level, _MASK)

    def bit(i: int) -> bool:
        return (bits >> i) & 1 == 1

    # First copy (around the top-left finder).
    for i in range(6):
        m[8][i] = bit(i)
    m[8][7] = bit(6)
    m[8][8] = bit(7)
    m[7][8] = bit(8)
    for i in range(9, 15):
        m[14 - i][8] = bit(i)
    # Second copy (below the top-right / right of the bottom-left finder).
    for i in range(7):
        m[size - 1 - i][8] = bit(i)
    for i in range(7, 15):
        m[8][size - 15 + i] = bit(i)
    m[size - 8][8] = True  # always dark


def _mask_bit(mask: int, r: int, c: int) -> bool:
    if mask == 0:
        return (r + c) % 2 == 0
    if mask == 1:
        return r % 2 == 0
    if mask == 2:
        return c % 3 == 0
    if mask == 3:
        return (r + c) % 3 == 0
    if mask == 4:
        return (r // 2 + c // 3) % 2 == 0
    if mask == 5:
        return (r * c) % 2 + (r * c) % 3 == 0
    if mask == 6:
        return ((r * c) % 2 + (r * c) % 3) % 2 == 0
    return ((r + c) % 2 + (r * c) % 3) % 2 == 0


def _place_data(m, codewords: list[int]) -> None:
    size = len(m)
    bits: list[int] = []
    for byte in codewords:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    idx = 0
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for c in (col, col - 1):
                if m[row][c] is None:
                    bit = bool(bits[idx]) if idx < len(bits) else False
                    m[row][c] = bit ^ _mask_bit(_MASK, row, c)
                    idx += 1
        upward = not upward
        col -= 2


def encode(data, version: int | None = None) -> list[list[bool]]:
    """Encode *data* (str or bytes) into a QR module matrix (list of rows)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if version is None:
        version = _pick_version(len(data))
    if version not in _TOTAL_CODEWORDS:
        raise ValueError(f"QR: unsupported version {version}")
    size = 17 + 4 * version
    m = _new_matrix(size)
    _place_finder(m, 0, 0)
    _place_finder(m, 0, size - 7)
    _place_finder(m, size - 7, 0)
    _place_timing(m)
    _place_alignment(m, _ALIGNMENT[version])
    _reserve_format(m)
    _place_data(m, _codewords(data, version))
    _place_format(m, ecc_level=1)  # level L = 01
    return [[bool(cell) for cell in row] for row in m]
