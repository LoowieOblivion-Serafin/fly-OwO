"""Shared-memory bridge between the neural model and the patched SRB2 build.

Layout (little-endian, 128-byte header followed by a 64x48 RGB thumbnail).
Every field is also documented in ``patches/srb2-flysonic.patch``
(``src/fly_bridge.c``); the two must stay in sync.

Offsets 0-39 and 24-39 are written by the model, 40-127 by the game::

    0   8s  magic "FLYSONIC"          8   I  version (2)
    12  I   frame_seq   (game seqlock, even = stable thumbnail)
    16  I   control_seq (model seqlock, even = stable controls)
    20  I   enabled     (game-owned neural control toggle)
    24  I   control_count (model increments per control write; liveness)
    28  b   stick_x     29 b stick_y     30 H buttons (bit0 jump, bit1 spin)
    32  I   jump_event  36 I spin_event  (model increments per event)
    40  I   applied_seq 44 b applied_x  45 b applied_y  46 H applied_buttons
    48  I   game_tick   (game increments per local tic; liveness)
    52  I   game_status (0 disabled, 1 applied, 2 stale, 3 torn, 5 paused)
    56  I   telemetry_seq (game seqlock for the block below)
    60  i   rings  64 i lives  68 i score  72 i map  76 I leveltime
    80  i   x      84 i y      88 i z     92 i speed
    96  i   gamestate  100 i playerstate (bit 8 = exiting)
    104 I   capture_count  108 I render_mode
    112 i   applied_angleturn  116 i applied_forwardmove
    128     RGB thumbnail (9,216 bytes)

Both processes are only required to share the same file: liveness is derived
from counters observed with each process's own monotonic clock, so no clock
has to be shared across runtimes or operating systems.
"""
from __future__ import annotations

import ctypes
import mmap
import os
import struct
import sys
import time
from pathlib import Path

MAGIC = b"FLYSONIC"
VERSION = 2
WIDTH = 64
HEIGHT = 48
CHANNELS = 3
FRAME_BYTES = WIDTH * HEIGHT * CHANNELS
HEADER_SIZE = 128
FILE_SIZE = HEADER_SIZE + FRAME_BYTES

BUTTON_JUMP = 0x0001
BUTTON_SPIN = 0x0002
# SRB2 ticcmd button bits, echoed back in applied_buttons.
SRB2_BT_SPIN = 1 << 7
SRB2_BT_JUMP = 1 << 11

OFF_FRAME_SEQ = 12
OFF_CONTROL_SEQ = 16
OFF_ENABLED = 20
OFF_CONTROL_COUNT = 24
OFF_STICK = 28
OFF_JUMP_EVENT = 32
OFF_SPIN_EVENT = 36
OFF_APPLIED = 40
OFF_GAME_TICK = 48
OFF_GAME_STATUS = 52
OFF_TELEMETRY_SEQ = 56
OFF_TELEMETRY = 60

STICK = struct.Struct("<bbH")
APPLIED = struct.Struct("<IbbH")
TELEMETRY = struct.Struct("<iiiiIiiiiiiIIii")
TELEMETRY_FIELDS = ("rings", "lives", "score", "map", "leveltime", "x", "y", "z", "speed",
                    "gamestate", "playerstate", "captures", "render_mode", "angleturn", "forwardmove")

STATE_DISABLED = 0
STATE_APPLIED = 1
STATE_STALE = 2
STATE_TORN = 3
STATE_NOT_CONNECTED = 4
STATE_PAUSED = 5
STATE_NAMES = {0: "disabled", 1: "applied", 2: "stale", 3: "torn", 4: "not connected", 5: "paused"}

STALE_MS = 250.0

if sys.platform == "darwin":
    _memory_barrier = ctypes.CDLL(None).OSMemoryBarrier
    _memory_barrier.argtypes = []
    _memory_barrier.restype = None
else:
    def _memory_barrier() -> None:
        # x86-64 (Windows/Linux) is strongly ordered for these single-writer
        # seqlocks; every read below is validated by its before/after sequence
        # anyway, so a torn read can only be rejected, never accepted.
        return None


class SharedBridge:
    """Versioned single-producer/single-consumer mmap shared with SRB2."""

    def __init__(self, path: str | os.PathLike[str], create: bool = True, enabled: bool = True):
        self.path = Path(path)
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
            os.ftruncate(fd, FILE_SIZE)
        else:
            fd = os.open(self.path, os.O_RDWR)
        self._file = os.fdopen(fd, "r+b", buffering=0)
        self.mm = mmap.mmap(self._file.fileno(), FILE_SIZE)
        self._last_frame = (0, bytes(FRAME_BYTES))
        self._last_tick = None
        self._last_tick_at = time.monotonic()
        self._telemetry = dict.fromkeys(TELEMETRY_FIELDS, 0)
        if create:
            self.mm[:FILE_SIZE] = bytes(FILE_SIZE)
            self.mm[:8] = MAGIC
            struct.pack_into("<I", self.mm, 8, VERSION)
            struct.pack_into("<I", self.mm, OFF_ENABLED, 1 if enabled else 0)
        elif self.mm[:8] != MAGIC or struct.unpack_from("<I", self.mm, 8)[0] != VERSION:
            self.close()
            raise ValueError("incompatible Fly Sonic bridge")

    # ----------------------------------------------------------------- frames
    def read_frame(self) -> tuple[int, bytes]:
        for _ in range(3):
            before = struct.unpack_from("<I", self.mm, OFF_FRAME_SEQ)[0]
            _memory_barrier()
            pixels = self.mm[HEADER_SIZE:HEADER_SIZE + FRAME_BYTES]
            _memory_barrier()
            after = struct.unpack_from("<I", self.mm, OFF_FRAME_SEQ)[0]
            if before == after and before % 2 == 0:
                self._last_frame = before, pixels
                return self._last_frame
        return self._last_frame

    def write_frame(self, pixels: bytes) -> None:
        """Synthetic mode only: the game normally owns the thumbnail."""
        if len(pixels) != FRAME_BYTES:
            raise ValueError(f"expected {FRAME_BYTES} RGB bytes, got {len(pixels)}")
        seq = struct.unpack_from("<I", self.mm, OFF_FRAME_SEQ)[0]
        odd = (seq + 1) | 1
        struct.pack_into("<I", self.mm, OFF_FRAME_SEQ, odd)
        _memory_barrier()
        self.mm[HEADER_SIZE:HEADER_SIZE + FRAME_BYTES] = pixels
        _memory_barrier()
        struct.pack_into("<I", self.mm, OFF_FRAME_SEQ, (odd + 1) & 0xFFFFFFFF)

    # --------------------------------------------------------------- controls
    def write_control(self, x: int, y: int, jump: bool, spin: bool = False, enabled: bool | None = None) -> None:
        x = max(-127, min(127, int(x)))
        y = max(-127, min(127, int(y)))
        buttons = (BUTTON_JUMP if jump else 0) | (BUTTON_SPIN if spin else 0)
        control_seq = struct.unpack_from("<I", self.mm, OFF_CONTROL_SEQ)[0] | 1
        struct.pack_into("<I", self.mm, OFF_CONTROL_SEQ, control_seq)
        _memory_barrier()
        count = struct.unpack_from("<I", self.mm, OFF_CONTROL_COUNT)[0]
        struct.pack_into("<I", self.mm, OFF_CONTROL_COUNT, (count + 1) & 0xFFFFFFFF)
        STICK.pack_into(self.mm, OFF_STICK, x, y, buttons)
        if jump:
            event = struct.unpack_from("<I", self.mm, OFF_JUMP_EVENT)[0]
            struct.pack_into("<I", self.mm, OFF_JUMP_EVENT, (event + 1) & 0xFFFFFFFF)
        if spin:
            event = struct.unpack_from("<I", self.mm, OFF_SPIN_EVENT)[0]
            struct.pack_into("<I", self.mm, OFF_SPIN_EVENT, (event + 1) & 0xFFFFFFFF)
        _memory_barrier()
        struct.pack_into("<I", self.mm, OFF_CONTROL_SEQ, (control_seq + 1) & 0xFFFFFFFF)
        # The game owns the enabled flag (F6), so it is only ever cleared here,
        # when the model shuts down and wants its controls released.
        if enabled is False:
            struct.pack_into("<I", self.mm, OFF_ENABLED, 0)

    @property
    def enabled(self) -> bool:
        return bool(struct.unpack_from("<I", self.mm, OFF_ENABLED)[0])

    # ------------------------------------------------------- game feedback
    def game_status(self) -> dict:
        seq, x, y, buttons = APPLIED.unpack_from(self.mm, OFF_APPLIED)
        tick = struct.unpack_from("<I", self.mm, OFF_GAME_TICK)[0]
        status = struct.unpack_from("<I", self.mm, OFF_GAME_STATUS)[0]
        now = time.monotonic()
        if tick != self._last_tick:
            self._last_tick = tick
            self._last_tick_at = now
        age_ms = (now - self._last_tick_at) * 1000.0
        connected = tick != 0 and age_ms < STALE_MS
        state = status if connected else STATE_NOT_CONNECTED
        if state not in STATE_NAMES:
            state = STATE_TORN
        return dict(seq=seq, x=x, y=y, jump=bool(buttons & SRB2_BT_JUMP), spin=bool(buttons & SRB2_BT_SPIN),
                    buttons=buttons, age_ms=age_ms, tick=tick, state=state, state_name=STATE_NAMES[state],
                    enabled=self.enabled)

    def telemetry(self) -> dict:
        for _ in range(3):
            before = struct.unpack_from("<I", self.mm, OFF_TELEMETRY_SEQ)[0]
            if before % 2:
                continue
            _memory_barrier()
            values = TELEMETRY.unpack_from(self.mm, OFF_TELEMETRY)
            _memory_barrier()
            after = struct.unpack_from("<I", self.mm, OFF_TELEMETRY_SEQ)[0]
            if before == after:
                self._telemetry = dict(zip(TELEMETRY_FIELDS, values))
                break
        result = dict(self._telemetry)
        result["exiting"] = bool(result["playerstate"] & 0x100) if result["playerstate"] >= 0 else False
        result["playerstate"] = result["playerstate"] & 0xFF if result["playerstate"] >= 0 else -1
        result["in_level"] = result["gamestate"] == 1
        return result

    def close(self) -> None:
        self.mm.close()
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
