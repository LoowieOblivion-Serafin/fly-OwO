# Technical notes

For the short run/build instructions, see [the README](../README.md).

Measured connectome wiring does **not** establish recovered fly physiology,
behavior, experience, or consciousness. Dynamics, visual projection and Mario
motor mappings are engineered approximations. No trained policy, scripted
gameplay, or direct image-to-motor shortcut is used.

## Developer commands

Run these from your project folder after the first successful build.
Replace the ROM path with your own file:

```sh
./run-fly64 --synthetic             # explicitly labeled 4,096-cell test fixture
./run-fly64 --rom "/path/to/baserom.us.z64" --duration 90
.venv/bin/pytest -q
PYTHONPATH=. .venv/bin/python scripts/validate_causality.py
.venv/bin/python -m fly64.replay artifacts/latest-replay.index.json
```

Stop the existing demo before launching another. The synthetic fixture does not
use the full MaleCNS graph or SM64.

Tested with project-local Python 3.14; the launcher also supports selecting
Python 3.12. Tested package versions are in `requirements-lock.txt`.

## Data and limitations

- Official [MaleCNS v1.0](https://male-cns.janelia.org/download/) minimum-confidence
  0.5 tables. Exactly **166,700** cells with non-empty superclass annotations,
  including the 94 `tbc` annotations. Status-only filtering would incorrectly
  remove many photoreceptors; no such filter is used.
- **25,582,938** directed weighted connections with both endpoints in the retained
  cells. No connection-strength threshold or speed-driven pruning. The source's
  151,856,684 rows also include unannotated segments/fragments.
- Weight = original synapse count × presynaptic sign / incoming absolute-weight
  sum. GABA, glutamate and histamine are modeled as inhibitory; other or unknown
  transmitters as excitatory. Receptor-dependent and neuromodulatory effects are
  omitted; these signs are approximations, not universal biological rules.
- The cache manifest includes source URLs, SHA-256 hashes, exact counts and
  preprocessing rules. Float32 CSR is cached; runtime CSC spike-event propagation
  visits every outgoing edge of every spiking neuron. Zero-spike columns
  contribute exactly zero: sparse evaluation is not graph pruning.
- 6,006 R1–R8 photoreceptors receive 64×48 RGB input. The authors'
  [optic-column assignments](https://github.com/flyconnectome/2025malecns) map
  2,628 cells directly. Another 3,242 have connectivity-derived column estimates.
  **136 still use a deterministic within-eye proxy.** Planar column projection
  is not a calibrated fly-eye field of view.
- **140,638 measured soma/to-soma positions** are displayed; **26,062** missing
  locations use a deterministic fallback layout. All cells are displayed, but
  not all locations are measured. Rate summaries are by annotated **superclass**,
  not anatomical neuropil ROI. The spike raster bins every received spike.
- The model can collide, get stuck, or die. No star-completion or natural
  fly-behavior claim is made.

## Dynamics and controller

Every 20 ms:
`v ← exp(-dt/0.1)·v + 1.5·W·spikes + 0.180 + noise + retina`.

Noise is seeded Bernoulli background activity (1.2 Hz, amplitude 0.22); default
seed 64. Voltage threshold 1 resets to 0. Retinal current is injected **only**
into photoreceptors. Global tonic current and synaptic gain were calibrated to
make visual perturbations observable downstream; they are not measured
physiological parameters. Luminance, green opponency and absolute temporal
contrast form the retinal drive.

A 13-tick (~260 ms) descending-neuron spike window controls Mario:

- DNg100 forward activity; right-minus-left DNa02/DNg13 steering.
- DNp01/DNp10 burst threshold >0.04 spikes/cell/tick, 800 ms simulation-time
  cooldown. The native game holds A for exactly two game frames per event.
- EMA 0.78/0.22, 8-unit dead zone, stick bounds ±70/127.

Neural updates target 50 Hz, framebuffer capture 10 Hz. Dashboard publishing
drops from 10 to 5 Hz below 0.95 real-time factor. Neural updates and graph edges
are never discarded to catch up. Real-time factor is simulated / elapsed time.

The dashboard shows retinal input, membrane/spike activity, spike density,
superclass rates, intent avatar and requested controls. **Game received**
independently reports the game-applied controller state. A moving dashboard
stick alone does not prove the game accepted it.

## Bridge and replay

`runtime/fly64_bridge.bin`: 64-byte little-endian header then 9,216 RGB bytes.
Magic/version: offsets 0/8; frame/control seqlocks: 12/16; game-owned enable: 20;
heartbeat: 24; signed stick x/y: 32/33; buttons: 34; jump event: 36. Game
acknowledgements occupy 40–63. Both processes use POSIX `CLOCK_MONOTONIC`.
Python's macOS `monotonic_ns()` uses a different clock and must not be substituted.
Readers reject odd/changed sequences. Reads are bounded; neural controls release
after 250 ms stale heartbeat.

Replay schema 2 is a JSON index plus compressed NPZ chunks. **Every neural tick**
records timestamp, exact retinal frame, spikes and requested controls; the index
includes seed and dynamics parameters. Background compression bounds memory.
Replay verification recomputes every spike and controller output without SM64,
on the same code/runtime. Floating-point ordering may differ across architectures.
This does not promise bit-identical replay of the game engine.

## Validation

Tests cover normalization, signed propagation, dense/event equivalence, retinal
response, all-tick deterministic replay, steering signs, jump debounce, torn
packets, native two-frame A, stale release and a **real Python-to-C clock test**.
Causality compares live/frozen/disconnected frames with the same seed and requires
different motor outputs for the connected trials.

Local results are written to `artifacts/causality.json`,
`artifacts/soak-report.json`, replay chunks, logs and recordings when those
runs complete. The soak checks execution stability, not biological validity.

## Attribution and private assets

MaleCNS: Berg et al., *Sexual dimorphism in the complete connectome of the
Drosophila male central nervous system*,
[data and CC-BY terms](https://male-cns.janelia.org/download/).
Optic assignments pinned to supplemental commit
`67767d2233657983993ff6c2be48e836a935863c`.

SM64: [sm64pc/sm64ex](https://github.com/sm64pc/sm64ex/tree/d7ca2c04364a6dd0dac58b47151e04e26887e6f0),
pinned commit `d7ca2c04364a6dd0dac58b47151e04e26887e6f0`.

The supplied ROM, extracted Nintendo assets, native binary, dataset caches,
browser profiles and recordings are gitignored. The US ROM SHA-1 is
`9bef1128717f958171a4afac3ed78ee2bb4e86ce`. It is copied only into the private
build cache for extraction, never into source deliverables or distributed.
