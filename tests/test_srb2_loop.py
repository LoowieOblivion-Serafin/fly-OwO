"""Headless closed-loop test against the real patched SRB2 build.

Skipped unless ``python run_flysonic.py --build-only`` has produced the game
binary and data files. Uses SDL's dummy video/audio drivers, so it runs on CI
and in terminals without a display.
"""
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from flysonic import srb2
from flysonic.bridge import (HEIGHT, SRB2_BT_JUMP, STATE_APPLIED, STATE_DISABLED, STATE_NOT_CONNECTED, STATE_PAUSED,
                             STATE_STALE, WIDTH, SharedBridge)

ROOT = Path(__file__).resolve().parent.parent
EXE = srb2.executable(ROOT / ".cache" / "srb2")
DATA = ROOT / ".cache" / "srb2-data"

pytestmark = pytest.mark.skipif(not EXE.exists() or not (DATA / "srb2.pk3").exists(),
                                reason="patched SRB2 build or data files missing (run_flysonic.py --build-only)")


def wait_for(predicate, timeout, bridge, x=0, y=0, jump=False):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        bridge.write_control(x, y, jump)
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_headless_closed_loop(tmp_path):
    home = srb2.prepare_home(tmp_path / "home")
    bridge_path = tmp_path / "bridge.bin"
    env = srb2.game_environment(srb2.build_environment(), bridge_path, DATA)
    env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    command = srb2.game_command(EXE, home, 1, "sonic", no_audio=True,
                                extra=["-logfile", str(tmp_path / "srb2.log")])
    with SharedBridge(bridge_path) as bridge:
        game = subprocess.Popen(command, env=env, cwd=str(EXE.parent),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            # 1. the game connects, reports itself alive and reaches the level
            assert wait_for(lambda: bridge.game_status()["state"] == STATE_APPLIED, 60, bridge), \
                f"game never applied controls: {bridge.game_status()} log={ (tmp_path / 'srb2.log').read_text()[-2000:] }"
            telemetry = bridge.telemetry()
            assert telemetry["in_level"] and telemetry["map"] == 1 and telemetry["lives"] == 127

            # 2. thumbnails arrive at ~10 Hz and look like a rendered scene
            first_seq = bridge.read_frame()[0]
            wait_for(lambda: False, 1.0, bridge)
            seq, pixels = bridge.read_frame()
            assert seq >= first_seq + 2 * 6, "expected at least six new thumbnails in a second"
            frame = np.frombuffer(pixels, np.uint8).reshape(HEIGHT, WIDTH, 3)
            assert frame.std() > 10

            # 3. forward drive moves Sonic; the game echoes the applied stick
            start = bridge.telemetry()
            assert wait_for(lambda: bridge.game_status()["y"] == 60, 5, bridge, x=0, y=60)
            wait_for(lambda: False, 2.5, bridge, x=0, y=60)
            moved = bridge.telemetry()
            assert (moved["x"] - start["x"]) ** 2 + (moved["y"] - start["y"]) ** 2 > 40 ** 2
            assert bridge.game_status()["state"] == STATE_APPLIED

            # 4. a jump event holds BT_JUMP for a few tics
            seen_jump = wait_for(lambda: bridge.game_status()["jump"], 1.0, bridge, x=0, y=60, jump=True)
            assert seen_jump

            # 5. silence releases the controls (stale), F6-style disable reports disabled
            time.sleep(0.6)
            assert bridge.game_status()["state"] in (STATE_STALE, STATE_PAUSED)
            bridge.write_control(0, 0, False, enabled=False)
            assert wait_for(lambda: bridge.game_status()["state"] == STATE_DISABLED, 2, bridge)
            status = bridge.game_status()
            assert status["state"] == STATE_DISABLED and status["x"] == 0 and not status["enabled"]
        finally:
            game.terminate()
            try:
                game.wait(10)
            except subprocess.TimeoutExpired:
                game.kill()
        # Two samples: the first may still observe the final tic, the second must not.
        time.sleep(0.4)
        bridge.game_status()
        time.sleep(0.3)
        assert bridge.game_status()["state"] == STATE_NOT_CONNECTED
