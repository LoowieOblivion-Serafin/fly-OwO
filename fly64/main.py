from __future__ import annotations

import argparse
import asyncio
import os
import struct
import subprocess
import tempfile
import threading
import time
import webbrowser
import json
import signal
import resource
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from websockets.asyncio.server import serve

from .bridge import CHANNELS, HEIGHT, WIDTH, SharedBridge
from .model import FlyModel

DASH_HEADER = struct.Struct("<4sIdbbBffIIIHH")


class DashboardHTTP(BaseHTTPRequestHandler):
    html = b""
    positions = b""
    metadata = b"{}"
    bridge = None

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            body, mime = self.html, "text/html; charset=utf-8"
        elif path == "/positions.bin":
            body, mime = self.positions, "application/octet-stream"
        elif path == "/metadata.json":
            body, mime = self.metadata, "application/json"
        elif path == "/bridge-status.json" and self.bridge is not None:
            body, mime = json.dumps(self.bridge.game_status()).encode(), "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class LocalHTTPServer(ThreadingHTTPServer):
    """HTTP server that avoids macOS's blocking reverse-DNS lookup at bind time."""

    def server_bind(self):
        self.socket.setsockopt(__import__("socket").SOL_SOCKET, __import__("socket").SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


class SyntheticWorld:
    """ROM-free closed-loop visual source used for integration tests."""

    def __init__(self):
        self.heading = 0.0
        self.distance = 0.0
        self.jump_phase = 0.0

    def frame(self, x: int, y: int, jump: bool) -> np.ndarray:
        self.heading += x / 70.0 * 0.035
        self.distance += y / 70.0 * 0.05
        if jump and self.jump_phase == 0:
            self.jump_phase = 0.01
        if self.jump_phase:
            self.jump_phase += 0.12
            if self.jump_phase > np.pi:
                self.jump_phase = 0
        yy, xx = np.mgrid[0:HEIGHT, 0:WIDTH]
        sky = np.zeros((HEIGHT, WIDTH, 3), np.float32)
        horizon = 25 + int(3 * np.sin(self.heading))
        sky[:horizon, :, :] = (80, 165, 245)
        sky[horizon:, :, :] = (70, 155, 72)
        # Moving high-contrast scenery makes temporal visual input causal.
        center = int(WIDTH / 2 + 19 * np.sin(self.heading + self.distance * 0.2))
        tree = (np.abs(xx - center) < 3) & (yy > 10) & (yy < horizon + 10)
        sky[tree] = (82, 48, 25)
        crown = (xx - center) ** 2 + (yy - 10) ** 2 < 55
        sky[crown] = (30, 112, 35)
        stripe = ((xx + int(self.distance * 7)) % 22 < 3) & (yy > horizon)
        sky[stripe] = (205, 190, 95)
        lift = int(5 * np.sin(self.jump_phase)) if self.jump_phase else 0
        mario = (np.abs(xx - WIDTH // 2) < 3) & (yy > 31 - lift) & (yy < 42 - lift)
        sky[mario] = (225, 35, 35)
        return sky.astype(np.uint8)


class Replay:
    def __init__(self, path: Path, seed=64, fixture=False, parameters=None):
        self.path = path
        self.seed = seed
        self.fixture = fixture
        self.parameters = parameters or dict(tonic_current=.180, synaptic_gain=1.50)
        self.chunks = []
        self.writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="replay")
        self.writes = []
        self.times: list[float] = []
        self.frames: list[np.ndarray] = []
        self.controls: list[tuple[int, int, int]] = []
        self.spikes: list[np.ndarray] = []

    def add(self, timestamp, frame, control, spikes):
        self.times.append(timestamp)
        self.frames.append(frame.copy())
        self.controls.append((control.x, control.y, int(control.jump)))
        self.spikes.append(spikes.astype(np.uint32))
        if len(self.frames) >= 500:
            self.save()

    def save(self):
        if not self.frames:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        offsets = np.zeros(len(self.spikes) + 1, np.uint64)
        for i, values in enumerate(self.spikes):
            offsets[i + 1] = offsets[i] + len(values)
        flat = np.concatenate(self.spikes) if offsets[-1] else np.empty(0, np.uint32)
        target = self.path.with_name(f"{self.path.stem}-{len(self.chunks):05d}.npz")
        self.writes.append(self.writer.submit(np.savez_compressed,
            target, timestamps=np.asarray(self.times), frames=np.asarray(self.frames),
            controls=np.asarray(self.controls, np.int8), spike_offsets=offsets, spikes=flat,
            seed=np.int64(self.seed), fixture=np.bool_(self.fixture), schema=np.int64(2),
        ))
        self.chunks.append(target.name)
        self.path.with_suffix(".index.json").write_text(json.dumps(dict(schema=2,
            seed=self.seed, fixture=self.fixture, parameters=self.parameters,
            chunks=self.chunks), indent=2))
        self.times.clear(); self.frames.clear(); self.controls.clear(); self.spikes.clear()

    def close(self):
        self.save()
        self.writer.shutdown(wait=True)
        for future in self.writes:
            future.result()


def start_http(project: Path, model, port: int, ws_port: int) -> ThreadingHTTPServer:
    DashboardHTTP.html = (project / "web" / "index.html").read_bytes()
    DashboardHTTP.positions = model.positions.astype("<f4", copy=False).tobytes()
    DashboardHTTP.metadata = json.dumps(dict(n=model.n, ws=ws_port, label=model.label,
        region_names=model.region_names.tolist())).encode()
    server = LocalHTTPServer(("127.0.0.1", port), DashboardHTTP)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def open_dashboard(url: str, project: Path):
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.exists(chrome):
        profile = Path(tempfile.mkdtemp(prefix="chrome-dashboard-", dir=project / "runtime"))
        process = subprocess.Popen([
            chrome, f"--app={url}", f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check",
            "--window-size=840,900", "--window-position=620,38",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (project / "runtime/dashboard.pid").write_text(str(process.pid))
        return process
    else:
        webbrowser.open(url)
        return None


async def run(args) -> None:
    project = Path(__file__).resolve().parent.parent
    cache = project / ".cache" / "malecns"
    model = FlyModel(cache, demo=args.demo_model)
    bridge = SharedBridge(args.bridge, create=True)
    DashboardHTTP.bridge = bridge
    replay = Replay(args.record, model.seed, args.demo_model,
                    dict(tonic_current=model.tonic_current, synaptic_gain=model.synaptic_gain))
    clients: set = set()
    packet_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
    started = time.monotonic()
    synthetic = SyntheticWorld() if args.synthetic else None
    latest_control = None
    last_frame_seq = -1
    dropped = 0
    pending_spikes = []
    pending_jump = False
    dash_seq = 0

    async def ws_handler(socket):
        clients.add(socket)
        try:
            await socket.wait_closed()
        finally:
            clients.discard(socket)

    async def broadcaster():
        while True:
            packet = await packet_queue.get()
            if clients:
                await asyncio.gather(*(c.send(packet) for c in tuple(clients)), return_exceptions=True)

    http = start_http(project, model, args.http_port, args.ws_port)
    ws_server = await serve(ws_handler, "127.0.0.1", args.ws_port, max_size=None)
    url = f"http://127.0.0.1:{args.http_port}/"
    print(f"Fly64 dashboard: {url}")
    print(f"Fly64 model: {model.label}; {model.n:,} neurons; {model.w.nnz:,} edges")
    dashboard_process = open_dashboard(url, project) if not args.no_browser else None
    broadcast_task = asyncio.create_task(broadcaster())
    stopping = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stopping.set)
    log_path = args.record.with_suffix(".jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w", buffering=1)
    region_sizes = np.bincount(model.regions, minlength=len(model.region_names))

    try:
        next_tick = time.monotonic()
        last_publish = 0.0
        frame = np.zeros((HEIGHT, WIDTH, CHANNELS), np.uint8)
        while not stopping.is_set() and (args.duration <= 0 or time.monotonic() - started < args.duration):
            tick_start = time.monotonic()
            if synthetic is not None:
                x = latest_control.x if latest_control else 0
                y = latest_control.y if latest_control else 0
                jump = latest_control.jump if latest_control else False
                frame = synthetic.frame(x, y, jump)
                bridge.write_frame(frame.tobytes())
            seq, pixels = bridge.read_frame()
            if seq != last_frame_seq:
                frame = np.frombuffer(pixels, np.uint8).reshape(HEIGHT, WIDTH, CHANNELS).copy()
                last_frame_seq = seq
            control, spikes = model.step(frame, model.step_count * model.dt)
            latest_control = control
            bridge.write_control(control.x, control.y, control.jump)
            replay.add((model.step_count - 1) * model.dt, frame, control, spikes)
            pending_spikes.append(spikes)
            pending_jump |= control.jump
            latency_ms = (time.monotonic() - tick_start) * 1000
            rtf = model.step_count * model.dt / max(time.monotonic() - started, .02)

            if tick_start - last_publish >= (0.2 if rtf < 0.95 else 0.1):
                publish_ticks = len(pending_spikes)
                all_spikes = np.concatenate(pending_spikes).astype("<u4")
                pending_spikes.clear()
                last_publish = tick_start
                dash_seq += 1
                activity = np.clip((np.clip(model.v, 0, 1) * 0.35 + model.activity * 0.65) * 255, 0, 255).astype(np.uint8)
                header = DASH_HEADER.pack(
                    b"F64D", dash_seq, tick_start, control.x, control.y, int(pending_jump),
                    rtf, latency_ms,
                    dropped, model.n, len(all_spikes), WIDTH, HEIGHT,
                )
                rates = (np.bincount(model.regions[all_spikes], minlength=len(region_sizes)) /
                         np.maximum(region_sizes * publish_ticks * model.dt, 1)).astype("<f4")
                packet = header + frame.tobytes() + activity.tobytes() + all_spikes.tobytes() + rates.tobytes()
                if packet_queue.full():
                    try:
                        packet_queue.get_nowait()
                        dropped += 1
                    except asyncio.QueueEmpty:
                        pass
                packet_queue.put_nowait(packet)
                log.write(json.dumps(dict(wall_s=tick_start-started, steps=model.step_count, rtf=rtf,
                    latency_ms=latency_ms, rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6,
                    x=control.x, y=control.y, jump=pending_jump, frame_seq=last_frame_seq,
                    dropped=dropped, visual_contrast=model.temporal_energy)) + "\n")
                pending_jump = False

            next_tick += model.dt
            delay = next_tick - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                next_tick = time.monotonic()
                await asyncio.sleep(0)
    finally:
        bridge.write_control(0, 0, False, enabled=False)
        replay.close()
        log.close()
        broadcast_task.cancel()
        ws_server.close()
        await ws_server.wait_closed()
        http.shutdown()
        bridge.close()
        if dashboard_process and dashboard_process.poll() is None:
            dashboard_process.terminate()


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Fly64 neural closed loop")
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--demo-model", action="store_true")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--duration", type=float, default=0, help="seconds; zero runs until interrupted")
    parser.add_argument("--http-port", type=int, default=8765)
    parser.add_argument("--ws-port", type=int, default=8766)
    return parser.parse_args()


def main():
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
