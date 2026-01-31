import pytest

from rstmdb.errors import ProtocolError
from rstmdb.protocol import (
    FLAG_CRC_PRESENT,
    HEADER_SIZE,
    MAGIC,
    PROTOCOL_VERSION,
    Frame,
    crc32c,
)


class TestCrc32c:
    """Tests for CRC32C implementation."""

    def test_empty(self) -> None:
        """CRC of empty data."""
        assert crc32c(b"") == 0

    def test_simple(self) -> None:
        """CRC of simple string."""
        result = crc32c(b"hello")
        assert isinstance(result, int)
        assert result > 0

    def test_deterministic(self) -> None:
        """Same input produces same output."""
        data = b"test data for crc"
        assert crc32c(data) == crc32c(data)

    def test_different_inputs(self) -> None:
        """Different inputs produce different outputs."""
        assert crc32c(b"hello") != crc32c(b"world")


class TestFrameEncode:
    """Tests for Frame encoding."""

    def test_encode_with_crc(self) -> None:
        """Encode frame with CRC enabled."""
        payload = b'{"type":"request"}'
        frame = Frame(payload, use_crc=True)
        encoded = frame.encode()

        # Check header (18 bytes)
        assert encoded[:4] == MAGIC
        # Version is 2 bytes big-endian
        version = int.from_bytes(encoded[4:6], "big")
        assert version == PROTOCOL_VERSION
        # Flags is 2 bytes big-endian
        flags = int.from_bytes(encoded[6:8], "big")
        assert flags == FLAG_CRC_PRESENT
        # Header extension length is 2 bytes
        header_len = int.from_bytes(encoded[8:10], "big")
        assert header_len == 0
        # Payload length is 4 bytes
        payload_len = int.from_bytes(encoded[10:14], "big")
        assert payload_len == len(payload)
        # CRC is 4 bytes (non-zero when enabled)
        crc_value = int.from_bytes(encoded[14:18], "big")
        assert crc_value == crc32c(payload)

        # Check payload follows header
        assert encoded[HEADER_SIZE:] == payload
        assert len(encoded) == HEADER_SIZE + len(payload)

    def test_encode_without_crc(self) -> None:
        """Encode frame without CRC."""
        payload = b'{"type":"request"}'
        frame = Frame(payload, use_crc=False)
        encoded = frame.encode()

        assert encoded[:4] == MAGIC
        # Flags should be 0
        flags = int.from_bytes(encoded[6:8], "big")
        assert flags == 0
        # CRC should be 0
        crc_value = int.from_bytes(encoded[14:18], "big")
        assert crc_value == 0

        assert encoded[HEADER_SIZE:] == payload
        assert len(encoded) == HEADER_SIZE + len(payload)

    def test_encode_empty_payload(self) -> None:
        """Encode frame with empty payload."""
        frame = Frame(b"", use_crc=True)
        encoded = frame.encode()

        payload_len = int.from_bytes(encoded[10:14], "big")
        assert payload_len == 0
        assert len(encoded) == HEADER_SIZE

    def test_encode_with_header_extension(self) -> None:
        """Encode frame with header extension."""
        payload = b'{"test":"data"}'
        header_ext = b"extra-header"
        frame = Frame(payload, use_crc=True, header_extension=header_ext)
        encoded = frame.encode()

        # Header extension length
        header_len = int.from_bytes(encoded[8:10], "big")
        assert header_len == len(header_ext)

        # Header extension follows header
        assert encoded[HEADER_SIZE : HEADER_SIZE + len(header_ext)] == header_ext

        # Payload follows header extension
        assert encoded[HEADER_SIZE + len(header_ext) :] == payload


class TestFrameDecode:
    """Tests for Frame decoding."""

    def test_decode_with_crc(self) -> None:
        """Decode frame with CRC."""
        payload = b'{"id":"1","type":"request"}'
        original = Frame(payload, use_crc=True)
        encoded = original.encode()

        decoded, remaining = Frame.decode(encoded)

        assert decoded is not None
        assert decoded.payload == payload
        assert decoded.use_crc is True
        assert decoded.header_extension == b""
        assert remaining == b""

    def test_decode_without_crc(self) -> None:
        """Decode frame without CRC."""
        payload = b'{"id":"1","type":"request"}'
        original = Frame(payload, use_crc=False)
        encoded = original.encode()

        decoded, remaining = Frame.decode(encoded)

        assert decoded is not None
        assert decoded.payload == payload
        assert decoded.use_crc is False
        assert remaining == b""

    def test_decode_with_header_extension(self) -> None:
        """Decode frame with header extension."""
        payload = b'{"test":"data"}'
        header_ext = b"metadata"
        original = Frame(payload, use_crc=True, header_extension=header_ext)
        encoded = original.encode()

        decoded, remaining = Frame.decode(encoded)

        assert decoded is not None
        assert decoded.payload == payload
        assert decoded.header_extension == header_ext
        assert remaining == b""

    def test_decode_incomplete_header(self) -> None:
        """Decode with incomplete header returns None."""
        buffer = MAGIC + b"\x00\x01"  # Only 6 bytes, need 18

        decoded, remaining = Frame.decode(buffer)

        assert decoded is None
        assert remaining == buffer

    def test_decode_incomplete_payload(self) -> None:
        """Decode with incomplete payload returns None."""
        payload = b'{"test":"data"}'
        frame = Frame(payload, use_crc=True)
        encoded = frame.encode()

        # Cut off some bytes
        partial = encoded[:-5]
        decoded, remaining = Frame.decode(partial)

        assert decoded is None
        assert remaining == partial

    def test_decode_with_remaining(self) -> None:
        """Decode returns remaining buffer."""
        payload = b'{"test":"data"}'
        frame = Frame(payload, use_crc=True)
        encoded = frame.encode()
        extra = b"extra bytes"
        buffer = encoded + extra

        decoded, remaining = Frame.decode(buffer)

        assert decoded is not None
        assert decoded.payload == payload
        assert remaining == extra

    def test_decode_multiple_frames(self) -> None:
        """Decode multiple frames from buffer."""
        frame1 = Frame(b'{"id":"1"}', use_crc=True)
        frame2 = Frame(b'{"id":"2"}', use_crc=True)
        buffer = frame1.encode() + frame2.encode()

        decoded1, remaining = Frame.decode(buffer)
        assert decoded1 is not None
        assert decoded1.payload == b'{"id":"1"}'

        decoded2, remaining = Frame.decode(remaining)
        assert decoded2 is not None
        assert decoded2.payload == b'{"id":"2"}'
        assert remaining == b""

    def test_decode_invalid_magic(self) -> None:
        """Decode with invalid magic raises ProtocolError."""
        # Create a buffer with wrong magic
        buffer = b"XXXX" + b"\x00" * 14 + b"hello"

        with pytest.raises(ProtocolError, match="Invalid magic"):
            Frame.decode(buffer)

    def test_decode_invalid_version(self) -> None:
        """Decode with unsupported version raises ProtocolError."""
        # Create header with wrong version (0xFF)
        import struct

        header = struct.pack(">4sHHHII", MAGIC, 0xFF, 0, 0, 5, 0)
        buffer = header + b"hello"

        with pytest.raises(ProtocolError, match="Unsupported version"):
            Frame.decode(buffer)

    def test_decode_crc_mismatch(self) -> None:
        """Decode with CRC mismatch raises ProtocolError."""
        payload = b'{"test":"data"}'
        frame = Frame(payload, use_crc=True)
        encoded = bytearray(frame.encode())

        # Corrupt the CRC (bytes 14-18)
        encoded[14] ^= 0xFF

        with pytest.raises(ProtocolError, match="CRC mismatch"):
            Frame.decode(bytes(encoded))


class TestRoundTrip:
    """Round-trip encoding/decoding tests."""

    @pytest.mark.parametrize("use_crc", [True, False])
    def test_roundtrip(self, use_crc: bool) -> None:
        """Frame survives encode/decode round trip."""
        payload = b'{"complex":{"nested":"data"},"array":[1,2,3]}'
        original = Frame(payload, use_crc=use_crc)

        encoded = original.encode()
        decoded, _ = Frame.decode(encoded)

        assert decoded is not None
        assert decoded.payload == original.payload
        assert decoded.use_crc == original.use_crc

    def test_roundtrip_with_header_extension(self) -> None:
        """Frame with header extension survives round trip."""
        payload = b'{"data":"value"}'
        header_ext = b"custom-header-data"
        original = Frame(payload, use_crc=True, header_extension=header_ext)

        encoded = original.encode()
        decoded, _ = Frame.decode(encoded)

        assert decoded is not None
        assert decoded.payload == original.payload
        assert decoded.header_extension == original.header_extension

    def test_roundtrip_large_payload(self) -> None:
        """Large payload survives round trip."""
        payload = b"x" * 100000
        original = Frame(payload, use_crc=True)

        encoded = original.encode()
        decoded, _ = Frame.decode(encoded)

        assert decoded is not None
        assert decoded.payload == original.payload

    def test_roundtrip_binary_payload(self) -> None:
        """Binary payload with all byte values survives round trip."""
        payload = bytes(range(256))
        original = Frame(payload, use_crc=True)

        encoded = original.encode()
        decoded, _ = Frame.decode(encoded)

        assert decoded is not None
        assert decoded.payload == original.payload
