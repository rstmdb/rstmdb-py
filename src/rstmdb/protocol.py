"""
RCP protocol frame encoding and decoding.

Frame layout (18 bytes header + optional header extension + payload):

+--------+---------+--------+------------+-------------+--------+
| magic  | version | flags  | header_len | payload_len | crc32c |
| 4 bytes| 2 bytes |2 bytes |  2 bytes   |   4 bytes   | 4 bytes|
+--------+---------+--------+------------+-------------+--------+
| [header_ext] | payload                                        |
| header_len   | payload_len bytes                              |
+--------------+------------------------------------------------+
"""

from __future__ import annotations

import struct

from .errors import ProtocolError

MAGIC = b"RCPX"
PROTOCOL_VERSION = 1
FLAG_CRC_PRESENT = 0x0001
HEADER_SIZE = 18  # 4 + 2 + 2 + 2 + 4 + 4

# CRC32C (Castagnoli) polynomial and lookup table
_CRC32C_POLY = 0x82F63B78
_CRC32C_TABLE: list[int] = []


def _init_crc32c_table() -> None:
    """Initialize the CRC32C lookup table."""
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ _CRC32C_POLY
            else:
                crc >>= 1
        _CRC32C_TABLE.append(crc)


_init_crc32c_table()


def crc32c(data: bytes) -> int:
    """Calculate CRC32C (Castagnoli) checksum."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc = (crc >> 8) ^ _CRC32C_TABLE[(crc ^ byte) & 0xFF]
    return crc ^ 0xFFFFFFFF


class Frame:
    """RCP protocol frame."""

    def __init__(
        self,
        payload: bytes,
        use_crc: bool = True,
        header_extension: bytes = b"",
    ) -> None:
        self.payload = payload
        self.use_crc = use_crc
        self.header_extension = header_extension

    def encode(self) -> bytes:
        """Encode frame to bytes.

        Layout:
        - magic (4 bytes): "RCPX"
        - version (2 bytes): protocol version (1)
        - flags (2 bytes): bit flags (0x0001 = CRC present)
        - header_len (2 bytes): length of header extension
        - payload_len (4 bytes): length of payload
        - crc32c (4 bytes): CRC of payload (0 if not used)
        - header_extension (header_len bytes)
        - payload (payload_len bytes)
        """
        flags = FLAG_CRC_PRESENT if self.use_crc else 0
        header_len = len(self.header_extension)
        payload_len = len(self.payload)

        # Calculate CRC of payload
        crc = crc32c(self.payload) if self.use_crc else 0

        # Pack header: magic(4) + version(2) + flags(2) + header_len(2) + payload_len(4) + crc(4)
        header = struct.pack(
            ">4sHHHII",
            MAGIC,
            PROTOCOL_VERSION,
            flags,
            header_len,
            payload_len,
            crc,
        )

        return header + self.header_extension + self.payload

    @classmethod
    def decode(cls, buffer: bytes) -> tuple[Frame | None, bytes]:
        """
        Decode a frame from buffer.

        Returns (frame, remaining_buffer) or (None, buffer) if incomplete.
        """
        if len(buffer) < HEADER_SIZE:
            return None, buffer

        # Unpack header
        magic, version, flags, header_len, payload_len, crc_expected = struct.unpack(
            ">4sHHHII", buffer[:HEADER_SIZE]
        )

        if magic != MAGIC:
            raise ProtocolError(f"Invalid magic: {magic!r}, expected {MAGIC!r}")
        if version != PROTOCOL_VERSION:
            raise ProtocolError(f"Unsupported version: {version}")

        has_crc = bool(flags & FLAG_CRC_PRESENT)
        total_size = HEADER_SIZE + header_len + payload_len

        if len(buffer) < total_size:
            return None, buffer

        # Extract header extension and payload
        header_ext_start = HEADER_SIZE
        header_ext_end = header_ext_start + header_len
        payload_start = header_ext_end
        payload_end = payload_start + payload_len

        header_extension = buffer[header_ext_start:header_ext_end]
        payload = buffer[payload_start:payload_end]

        # Validate CRC
        if has_crc:
            crc_actual = crc32c(payload)
            if crc_expected != crc_actual:
                raise ProtocolError(f"CRC mismatch: expected {crc_expected}, got {crc_actual}")

        return (
            cls(payload, use_crc=has_crc, header_extension=header_extension),
            buffer[total_size:],
        )
