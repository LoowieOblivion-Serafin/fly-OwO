"""Sample the running demo (model log + game acknowledgements) and write artifacts/soak-report.json."""
import argparse
import json
import time
from pathlib import Path

from flysonic.bridge import STATE_APPLIED, SharedBridge

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--seconds", type=float, default=610)
args = p.parse_args()
root = Path(__file__).resolve().parent.parent
samples = []
with SharedBridge(root / "runtime/fly_bridge.bin", create=False) as bridge:
    while True:
        lines = (root / "artifacts/latest-replay.jsonl").read_text().splitlines()
        if not lines:
            time.sleep(1); continue
        last = json.loads(lines[-1])
        status = bridge.game_status()
        telemetry = bridge.telemetry()
        samples.append(dict(wall_s=last["wall_s"], state=status["state"], rings=telemetry["rings"],
                            pos=(telemetry["x"], telemetry["y"], telemetry["z"]), captures=telemetry["captures"]))
        if last["wall_s"] >= args.seconds:
            logs = [json.loads(line) for line in lines]
            steady = [r for r in logs if r["wall_s"] > 10]
            report = dict(duration_s=last["wall_s"], neural_steps=last["steps"],
                final_real_time_factor=last["rtf"],
                minimum_steady_real_time_factor=min(r["rtf"] for r in steady),
                simulator_peak_rss_mb=max(r["rss_mb"] for r in logs),
                dropped_dashboard_updates=last["dropped"],
                requested_jump_updates=sum(r["jump"] for r in logs),
                forward_updates=sum(r["y"] > 0 for r in logs),
                steering_range=[min(r["x"] for r in logs), max(r["x"] for r in logs)],
                game_ack_samples=len(samples),
                game_live_samples=sum(s["state"] == STATE_APPLIED for s in samples),
                frames_captured=telemetry["captures"],
                distinct_positions=len({s["pos"] for s in samples}),
                passed=last["wall_s"] >= 600 and telemetry["captures"] > 5000 and status["state"] == STATE_APPLIED)
            (root / "artifacts/soak-report.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2)); break
        time.sleep(1)
