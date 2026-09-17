#!/usr/bin/env python3
"""Fly Sonic launcher: MaleCNS fly brain model driving Sonic Robo Blast 2.

    python run_flysonic.py                 # full run: data + SRB2 build + game + model + dashboard
    python run_flysonic.py --synthetic     # game-free integration demo (4,096-cell fixture)
    python run_flysonic.py --prepare-data  # only download/prepare the MaleCNS model
    python run_flysonic.py --build-only    # only fetch/patch/build SRB2 and its data files

Works on Windows (MSYS2 UCRT64 toolchain), Linux and macOS with Python 3.11+.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
VENV = PROJECT / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--synthetic", action="store_true", help="no game: synthetic world + demo fixture model")
    parser.add_argument("--demo-model", action="store_true", help="4,096-cell fixture instead of MaleCNS")
    parser.add_argument("--prepare-data", action="store_true", help="download and prepare MaleCNS, then exit")
    parser.add_argument("--build-only", action="store_true", help="fetch, patch and build SRB2, then exit")
    parser.add_argument("--no-browser", action="store_true", help="do not open the dashboard window")
    parser.add_argument("--duration", type=float, default=0, help="stop after N seconds (0 = until closed)")
    parser.add_argument("--map", type=int, default=1, help="SRB2 map number to warp to (1 = Greenflower Zone 1)")
    parser.add_argument("--skin", default="sonic", help="SRB2 character skin")
    parser.add_argument("--opengl", action="store_true", help="run SRB2 with the OpenGL renderer")
    parser.add_argument("--fullscreen", action="store_true", help="run SRB2 fullscreen instead of windowed")
    parser.add_argument("--no-audio", action="store_true", help="mute SRB2")
    parser.add_argument("--start-disabled", action="store_true", help="start with neural control off (F6 toggles)")
    parser.add_argument("--headless", action="store_true", help="SDL dummy video/audio drivers (CI and tests)")
    parser.add_argument("--jobs", type=int, default=None, help="parallel build jobs")
    parser.add_argument("--http-port", type=int, default=8765)
    parser.add_argument("--ws-port", type=int, default=8766)
    return parser.parse_args(argv)


def ensure_venv() -> None:
    """Re-exec inside the project virtualenv with the pinned requirements."""
    if os.environ.get("FLYSONIC_VENV") == "1" or Path(sys.prefix) == VENV:
        return
    if sys.version_info < (3, 11):
        sys.exit(f"Fly Sonic needs Python 3.11 or newer (found {sys.version.split()[0]})")
    if not VENV_PYTHON.exists():
        print(f"[flysonic] creating virtualenv in {VENV}", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
        subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(PROJECT / "requirements.txt")], check=True)
    env = dict(os.environ, FLYSONIC_VENV="1", PYTHONPATH=str(PROJECT))
    result = subprocess.run([str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]], env=env)
    sys.exit(result.returncode)


class SingleInstance:
    """Non-blocking lock so two demos never share the bridge file."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(path, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.exit("Fly Sonic is already running. Close the game before starting another instance.")


def terminate(process: subprocess.Popen | None, name: str) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(10)
    except subprocess.TimeoutExpired:
        print(f"[flysonic] {name} did not exit, killing it", flush=True)
        process.kill()


def main(argv=None) -> int:
    args = parse_args(argv)
    from flysonic import srb2
    # Fail before downloading the connectome or installing Python dependencies.
    if not args.synthetic and (not args.prepare_data or args.build_only):
        try:
            srb2.require_tools(srb2.build_environment())
        except srb2.SetupError as error:
            sys.exit(f"[flysonic] {error}")
    ensure_venv()
    from flysonic.bridge import SharedBridge  # noqa: F401  (import check)

    for name in ("runtime", "artifacts", ".cache"):
        (PROJECT / name).mkdir(exist_ok=True)
    lock = SingleInstance(PROJECT / "runtime" / "launcher.lock")

    cache = PROJECT / ".cache" / "malecns"
    if args.prepare_data or (not args.demo_model and not args.synthetic and not args.build_only
                             and not (cache / "manifest.json").exists()):
        print("[flysonic] preparing MaleCNS (first run can take several minutes)", flush=True)
        subprocess.run([sys.executable, "-u", "-m", "flysonic.data", "--prepare", "--cache", str(cache)], check=True)
        if args.prepare_data and not args.build_only:
            return 0

    game_exe = None
    data_dir = None
    env = None
    if not args.synthetic:
        try:
            env = srb2.build_environment()
            srb2.require_tools(env)
            data_dir = srb2.ensure_assets(PROJECT)
            game_exe = srb2.ensure_build(PROJECT, env, opengl=True, jobs=args.jobs)
        except srb2.SetupError as error:
            sys.exit(f"[flysonic] {error}")
        except subprocess.CalledProcessError as error:
            sys.exit(f"[flysonic] command failed ({error.returncode}): {' '.join(map(str, error.cmd))}")
        if args.build_only:
            print(f"[flysonic] SRB2 ready: {game_exe}", flush=True)
            return 0

    bridge = PROJECT / "runtime" / "fly_bridge.bin"
    if bridge.exists():
        try:
            bridge.unlink()
        except OSError:  # Windows: still mapped by a dying game; the model reinitialises it in place
            pass
    model_args = [sys.executable, "-m", "flysonic.main", "--bridge", str(bridge),
                  "--record", str(PROJECT / "artifacts" / "latest-replay.npz"),
                  "--http-port", str(args.http_port), "--ws-port", str(args.ws_port)]
    if args.demo_model or args.synthetic:
        model_args.append("--demo-model")
    if args.synthetic:
        model_args.append("--synthetic")
    if args.no_browser:
        model_args.append("--no-browser")
    if args.start_disabled:
        model_args.append("--start-disabled")
    if args.duration:
        model_args += ["--duration", str(args.duration)]

    model_env = dict(os.environ, PYTHONPATH=str(PROJECT))
    model = subprocess.Popen(model_args, env=model_env)
    (PROJECT / "runtime" / "simulator.pid").write_text(str(model.pid))
    game = None
    try:
        if not args.synthetic:
            for _ in range(200):  # wait for the model to create the bridge file
                if bridge.exists() or model.poll() is not None:
                    break
                time.sleep(0.05)
            if model.poll() is not None:
                return model.returncode or 1
            home = srb2.prepare_home(PROJECT / "runtime" / "srb2home")
            command = srb2.game_command(game_exe, home, args.map, args.skin, windowed=not args.fullscreen,
                                        no_audio=args.no_audio, opengl=args.opengl,
                                        extra=["-logfile", str(PROJECT / "runtime" / "srb2.log")])
            game_env = srb2.game_environment(env, bridge, data_dir)
            if args.headless:
                game_env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
                if "-noaudio" not in command:
                    command.append("-noaudio")
            print("[flysonic] launching SRB2: " + " ".join(command), flush=True)
            game = subprocess.Popen(command, env=game_env, cwd=str(game_exe.parent))
            (PROJECT / "runtime" / "game.pid").write_text(str(game.pid))
            print("[flysonic] F6 in the game toggles neural control; Escape/F10 quits; Ctrl+C here stops everything",
                  flush=True)
        while model.poll() is None and (game is None or game.poll() is None):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        terminate(game, "SRB2")
        terminate(model, "model")
        lock.handle.close()
    return model.returncode or 0


if __name__ == "__main__":
    sys.exit(main())
