import struct

from fly64.main import DASH_HEADER


def test_dashboard_header_is_stable_and_packed():
    packet = DASH_HEADER.pack(b"F64D", 3, 1.5, -2, 42, 1, 0.9, 4.2, 7, 4096, 12, 64, 48)
    assert len(packet) == 43
    assert packet[:4] == b"F64D"
    assert struct.unpack_from("<I", packet, 31)[0] == 4096
