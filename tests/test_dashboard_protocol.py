import struct

from flysonic.main import DASH_HEADER, DASH_MAGIC


def test_dashboard_header_is_stable_and_packed():
    packet = DASH_HEADER.pack(DASH_MAGIC, 3, 1.5, -2, 42, 1, 0.9, 4.2, 7, 4096, 12, 64, 48)
    assert len(packet) == 43
    assert packet[:4] == b"FLYS"
    assert struct.unpack_from("<I", packet, 31)[0] == 4096
    assert struct.unpack_from("<bb", packet, 16) == (-2, 42)
