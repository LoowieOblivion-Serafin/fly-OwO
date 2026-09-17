import struct

import numpy as np

from flysonic.bridge import (APPLIED, BUTTON_JUMP, FILE_SIZE, FRAME_BYTES, HEADER_SIZE, MAGIC, OFF_CONTROL_COUNT,
                             OFF_CONTROL_SEQ, OFF_ENABLED, OFF_FRAME_SEQ, OFF_GAME_STATUS, OFF_GAME_TICK,
                             OFF_JUMP_EVENT, OFF_STICK, OFF_TELEMETRY, OFF_TELEMETRY_SEQ, SRB2_BT_JUMP,
                             STATE_APPLIED, STATE_NOT_CONNECTED, STICK, TELEMETRY, SharedBridge)


def test_layout_constants_match_the_c_side():
    # Mirrors the struct FlyHeader offsets in patches/srb2-flysonic.patch.
    assert HEADER_SIZE == 128 and FRAME_BYTES == 9216 and FILE_SIZE == 9344
    assert (OFF_FRAME_SEQ, OFF_CONTROL_SEQ, OFF_ENABLED, OFF_CONTROL_COUNT) == (12, 16, 20, 24)
    assert (OFF_STICK, OFF_JUMP_EVENT, OFF_GAME_TICK, OFF_GAME_STATUS) == (28, 32, 48, 52)
    assert (OFF_TELEMETRY_SEQ, OFF_TELEMETRY) == (56, 60)
    assert OFF_TELEMETRY + TELEMETRY.size <= 128


def test_bridge_round_trip(tmp_path):
    path = tmp_path / "bridge.bin"
    with SharedBridge(path) as bridge:
        assert bridge.mm[:8] == MAGIC and struct.unpack_from("<I", bridge.mm, 8)[0] == 2
        assert bridge.enabled
        pixels = bytes(np.arange(FRAME_BYTES, dtype=np.uint8))
        bridge.write_frame(pixels)
        seq, observed = bridge.read_frame()
        assert seq % 2 == 0
        assert observed == pixels
        bridge.write_control(-40, 65, True)
        assert STICK.unpack_from(bridge.mm, OFF_STICK) == (-40, 65, BUTTON_JUMP)
        assert struct.unpack_from("<I", bridge.mm, OFF_CONTROL_SEQ)[0] % 2 == 0
        assert struct.unpack_from("<I", bridge.mm, OFF_CONTROL_COUNT)[0] == 1
        assert struct.unpack_from("<I", bridge.mm, OFF_JUMP_EVENT)[0] == 1
        bridge.write_control(0, 0, False)
        assert struct.unpack_from("<I", bridge.mm, OFF_CONTROL_COUNT)[0] == 2
        assert struct.unpack_from("<I", bridge.mm, OFF_JUMP_EVENT)[0] == 1  # events only count jumps


def test_simulator_does_not_override_game_toggle(tmp_path):
    with SharedBridge(tmp_path / "bridge.bin") as bridge:
        struct.pack_into("<I", bridge.mm, OFF_ENABLED, 0)
        bridge.write_control(10, 20, False)
        assert bridge.enabled is False
        struct.pack_into("<I", bridge.mm, OFF_ENABLED, 1)
        bridge.write_control(10, 20, False, enabled=False)  # shutdown releases controls
        assert bridge.enabled is False


def test_start_disabled_flag(tmp_path):
    with SharedBridge(tmp_path / "bridge.bin", enabled=False) as bridge:
        assert bridge.enabled is False


def test_torn_frames_return_last_good_frame(tmp_path):
    with SharedBridge(tmp_path / "bridge") as b:
        b.write_frame(bytes([41]) * FRAME_BYTES)
        expected = b.read_frame()
        struct.pack_into("<I", b.mm, OFF_FRAME_SEQ, 3)
        b.mm[HEADER_SIZE:] = bytes([99]) * FRAME_BYTES
        assert b.read_frame() == expected


def test_game_status_liveness_uses_the_tick_counter(tmp_path):
    with SharedBridge(tmp_path / "bridge") as b:
        assert b.game_status()["state"] == STATE_NOT_CONNECTED
        struct.pack_into("<I", b.mm, OFF_GAME_TICK, 7)
        struct.pack_into("<I", b.mm, OFF_GAME_STATUS, STATE_APPLIED)
        APPLIED.pack_into(b.mm, 40, 12, -33, 60, SRB2_BT_JUMP)
        status = b.game_status()
        assert status["state"] == STATE_APPLIED and status["state_name"] == "applied"
        assert (status["x"], status["y"], status["jump"], status["spin"]) == (-33, 60, True, False)
        b._last_tick_at -= 1.0  # a second without a new tic: the game is gone
        assert b.game_status()["state"] == STATE_NOT_CONNECTED


def test_telemetry_seqlock(tmp_path):
    with SharedBridge(tmp_path / "bridge") as b:
        TELEMETRY.pack_into(b.mm, OFF_TELEMETRY, 5, 127, 900, 1, 350, -48, 120, 33, 12, 1, 0x100, 42, 0, -100, 43)
        struct.pack_into("<I", b.mm, OFF_TELEMETRY_SEQ, 2)
        t = b.telemetry()
        assert (t["rings"], t["lives"], t["score"], t["map"], t["leveltime"]) == (5, 127, 900, 1, 350)
        assert (t["x"], t["y"], t["z"], t["speed"]) == (-48, 120, 33, 12)
        assert t["in_level"] and t["exiting"] and t["playerstate"] == 0
        struct.pack_into("<I", b.mm, OFF_TELEMETRY_SEQ, 3)  # torn: keep the last consistent block
        TELEMETRY.pack_into(b.mm, OFF_TELEMETRY, 999, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        assert b.telemetry()["rings"] == 5
