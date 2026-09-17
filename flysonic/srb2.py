"""Fetch, patch, build and launch Sonic Robo Blast 2 for Fly Sonic.

Everything lives under ``.cache/`` in the project folder:

* ``.cache/srb2``        pinned SRB2 source tree with ``patches/srb2-flysonic.patch`` applied
* ``.cache/srb2/build``  CMake/Ninja build (``bin/flysonic-srb2[.exe]``)
* ``.cache/srb2-data``   the freely distributed SRB2 data files (srb2.pk3, zones.pk3, ...)

Nothing here touches the user's own SRB2 installation or config: the game
runs with ``-home runtime/srb2home`` so its config.cfg and saves stay private.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

SRB2_REPO = "https://github.com/STJr/SRB2.git"
SRB2_TAG = "SRB2_release_2.2.15"
SRB2_COMMIT = "8701ef41f617c06e23a7b8ccd2199c160c5d1dd1"
ASSETS_URL = "https://github.com/STJr/SRB2/releases/download/SRB2_release_2.2.15/SRB2-v2215-Full.zip"
ASSETS_SHA256 = "3eda3080ab87940fca5e4dcd22b8e041dc1d9e65bfe9177bff68383e9bd58a10"
ASSET_FILES = ("srb2.pk3", "zones.pk3", "characters.pk3", "music.pk3", "models.dat",
               "README.txt", "LICENSE.txt", "LICENSE-3RD-PARTY.txt")
EXE_NAME = "flysonic-srb2"

MSYS2_ROOTS = ("C:\\msys64", "C:\\msys2", "D:\\msys64")
MSYS2_PACKAGES = ("mingw-w64-ucrt-x86_64-toolchain", "mingw-w64-ucrt-x86_64-cmake", "mingw-w64-ucrt-x86_64-ninja",
                  "mingw-w64-ucrt-x86_64-SDL2", "mingw-w64-ucrt-x86_64-SDL2_mixer", "mingw-w64-ucrt-x86_64-libpng",
                  "mingw-w64-ucrt-x86_64-zlib", "mingw-w64-ucrt-x86_64-curl", "mingw-w64-ucrt-x86_64-libgme",
                  "mingw-w64-ucrt-x86_64-libopenmpt", "git")
ARCH_PACKAGES = ("base-devel", "cmake", "ninja", "git", "sdl2", "sdl2_mixer", "libpng", "zlib", "curl", "libgme", "libopenmpt")
DEBIAN_PACKAGES = ("build-essential", "cmake", "ninja-build", "git", "libsdl2-dev", "libsdl2-mixer-dev", "libpng-dev",
                   "zlib1g-dev", "libcurl4-openssl-dev", "libgme-dev", "libopenmpt-dev")


class SetupError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[flysonic] {message}", flush=True)


def run(command, **kwargs) -> None:
    command = [str(c) for c in command]
    # Windows resolves executables using the parent PATH, not env['PATH'].
    # Select the requested MSYS2 tools explicitly instead of another MinGW.
    if sys.platform == "win32" and "env" in kwargs:
        command[0] = shutil.which(command[0], path=kwargs["env"].get("PATH")) or command[0]
    log("$ " + " ".join(str(c) for c in command))
    try:
        subprocess.run(command, check=True, **kwargs)
    except subprocess.CalledProcessError as error:
        # Windows may report NTSTATUS as either a signed or unsigned integer.
        if error.returncode & 0xFFFFFFFF == 0xC0E90002:
            raise SetupError(
                f"Windows bloqueo {command[0]} o una de sus DLL "
                "por una politica de integridad de codigo (0xC0E90002).\n"
                "Consulta el Visor de eventos > Registros de aplicaciones y servicios > "
                "Microsoft > Windows > CodeIntegrity > Operational para identificar el archivo.\n"
                "La instalacion debe ser revisada por su proveedor o administrador. "
                "Reintentar la compilacion no resuelve este bloqueo."
            ) from error
        raise


# --------------------------------------------------------------------- Windows
def msys2_root() -> Path | None:
    for candidate in (os.environ.get("FLYSONIC_MSYS2"), *MSYS2_ROOTS):
        if candidate and (Path(candidate) / "ucrt64" / "bin" / "gcc.exe").exists():
            return Path(candidate)
    return None


def build_environment() -> dict:
    """Environment for cmake/ninja/gcc (and for running the game) on this platform."""
    env = dict(os.environ)
    if sys.platform == "win32":
        root = msys2_root()
        if root is None:
            raise SetupError(
                "MSYS2 UCRT64 not found. Install https://www.msys2.org (default folder C:\\msys64), open the\n"
                "'MSYS2 UCRT64' shell and run:\n    pacman -S --needed " + " ".join(MSYS2_PACKAGES) +
                "\nor point FLYSONIC_MSYS2 at your MSYS2 folder.")
        env["PATH"] = str(root / "ucrt64" / "bin") + os.pathsep + str(root / "usr" / "bin") + os.pathsep + env.get("PATH", "")
        env["MSYSTEM"] = "UCRT64"
        env.setdefault("CC", "gcc")
        env.setdefault("CXX", "g++")
    return env


def require_tools(env: dict) -> None:
    missing = [tool for tool in ("git", "cmake", "ninja") if shutil.which(tool, path=env.get("PATH")) is None]
    if sys.platform == "win32":
        if shutil.which("gcc", path=env.get("PATH")) is None:
            missing.append("gcc")
    elif shutil.which("cc", path=env.get("PATH")) is None and shutil.which("gcc", path=env.get("PATH")) is None:
        missing.append("gcc")
    if missing:
        hint = {
            "win32": "MSYS2 UCRT64: pacman -S --needed " + " ".join(MSYS2_PACKAGES),
            "linux": "Arch: sudo pacman -S --needed " + " ".join(ARCH_PACKAGES) +
                     "\nDebian/Ubuntu: sudo apt install " + " ".join(DEBIAN_PACKAGES),
            "darwin": "Homebrew: brew install cmake ninja sdl2 sdl2_mixer libpng game-music-emu libopenmpt",
        }.get(sys.platform, "")
        raise SetupError(f"missing build tools: {', '.join(missing)}\n{hint}")


# ---------------------------------------------------------------------- source
def ensure_source(project: Path, env: dict) -> Path:
    source = project / ".cache" / "srb2"
    if not (source / ".git").exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--depth", "1", "--branch", SRB2_TAG, SRB2_REPO, source], env=env)
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], env=env, text=True).strip()
    if head != SRB2_COMMIT:
        run(["git", "-C", source, "fetch", "--depth", "1", "origin", "tag", SRB2_TAG], env=env)
        run(["git", "-C", source, "checkout", "--detach", SRB2_COMMIT], env=env)
    patch = project / "patches" / "srb2-flysonic.patch"
    check = subprocess.run(["git", "-C", str(source), "apply", "--check", str(patch)], env=env,
                           capture_output=True, text=True)
    if check.returncode == 0:
        run(["git", "-C", source, "apply", patch], env=env)
        log("applied patches/srb2-flysonic.patch")
    else:
        reverse = subprocess.run(["git", "-C", str(source), "apply", "--reverse", "--check", str(patch)], env=env,
                                 capture_output=True, text=True)
        if reverse.returncode == 0:
            log("SRB2 patch already applied")
        else:
            # The cached tree is disposable: an older version of the patch is
            # probably applied. Reset the tracked files and apply the current one.
            log("resetting .cache/srb2 to apply the current patch")
            run(["git", "-C", source, "checkout", "--", "."], env=env)
            retry = subprocess.run(["git", "-C", str(source), "apply", str(patch)], env=env,
                                   capture_output=True, text=True)
            if retry.returncode != 0:
                raise SetupError(f"patches/srb2-flysonic.patch does not apply to SRB2 {SRB2_TAG}:\n{retry.stderr}")
    return source


# ---------------------------------------------------------------------- assets
def sha256(path: Path) -> str:
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    log(f"downloading {url}")
    if shutil.which("curl"):
        run(["curl", "--fail", "--location", "--continue-at", "-", "--output", partial, url])
    else:
        from urllib.request import urlopen
        with urlopen(url) as response, open(partial, "wb") as out:
            shutil.copyfileobj(response, out, length=1 << 20)
    partial.replace(destination)


def ensure_assets(project: Path) -> Path:
    data = project / ".cache" / "srb2-data"
    if all((data / name).exists() for name in ("srb2.pk3", "zones.pk3", "characters.pk3")):
        return data
    archive = project / ".cache" / "downloads" / Path(ASSETS_URL).name
    if not archive.exists() or sha256(archive) != ASSETS_SHA256:
        if archive.exists():
            archive.unlink()
        download(ASSETS_URL, archive)
    digest = sha256(archive)
    if digest != ASSETS_SHA256:
        raise SetupError(f"{archive.name} sha256 {digest} does not match {ASSETS_SHA256}")
    data.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        for name in ASSET_FILES:
            if name in names:
                bundle.extract(name, data)
        for name in names:
            if name.startswith("models/") and not name.endswith("/"):
                bundle.extract(name, data)
    log(f"SRB2 data files ready in {data}")
    return data


# ----------------------------------------------------------------------- build
def executable(source: Path) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return source / "build" / "bin" / (EXE_NAME + suffix)


def ensure_build(project: Path, env: dict, opengl: bool = True, jobs: int | None = None) -> Path:
    source = ensure_source(project, env)
    build = source / "build"
    exe = executable(source)
    configure = [
        "cmake", "-S", source, "-B", build, "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        # SRB2 2.2.15 uses pre-C23 function declarations; GCC 15+ defaults to C23.
        "-DCMAKE_C_STANDARD=17", "-DCMAKE_C_STANDARD_REQUIRED=ON",
        f"-DSRB2_SDL2_EXE_NAME={EXE_NAME}",
        "-DSRB2_CONFIG_STATIC_STDLIB=OFF",
        "-DSRB2_CONFIG_USE_GME=ON",
        f"-DSRB2_CONFIG_HWRENDER={'ON' if opengl else 'OFF'}",
    ]
    if sys.platform == "win32":
        configure += ["-DCMAKE_C_COMPILER=gcc", "-DCMAKE_CXX_COMPILER=g++", "-DSRB2_CONFIG_SYSTEM_LIBRARIES=ON"]
    # Refresh cached configuration when launcher flags or toolchains change.
    run(configure, env=env)
    command = ["cmake", "--build", build]
    if jobs:
        command += ["--parallel", str(jobs)]
    run(command, env=env)
    if not exe.exists():
        raise SetupError(f"build finished but {exe} is missing")
    return exe


# ---------------------------------------------------------------------- launch
def game_command(exe: Path, home: Path, map_number: int, skin: str, windowed: bool = True,
                 no_audio: bool = False, opengl: bool = False, extra: list[str] | None = None) -> list[str]:
    # -nofork: on Unix SRB2 normally forks a crash-reporting supervisor whose
    # child would outlive our terminate(); run the game in the process we own.
    command = [str(exe), "-home", str(home), "-warp", str(map_number), "-nojoy", "-nofork"]
    if windowed:
        command.append("-win")
    if no_audio:
        command.append("-noaudio")
    command.append("-opengl" if opengl else "-software")
    # Keep playing while the dashboard window has focus, and start as Sonic.
    command += ["+pauseifunfocused", "0", "+skin", skin]
    command += extra or []
    return command


def game_environment(env: dict, bridge: Path, data: Path, window_pos: str = "20,120") -> dict:
    game_env = dict(env)
    game_env["FLY_BRIDGE"] = str(bridge)
    game_env["SRB2WADDIR"] = str(data)
    game_env.setdefault("SDL_VIDEO_WINDOW_POS", window_pos)
    return game_env


def prepare_home(home: Path) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    for name in (".srb2", "srb2"):  # SRB2 picks one per platform; create both
        (home / name).mkdir(exist_ok=True)
    return home
