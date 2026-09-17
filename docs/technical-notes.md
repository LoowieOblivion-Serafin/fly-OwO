# Technical notes

For the short install/run instructions, see [the README](../README.md) (Spanish).

Measured connectome wiring does **not** establish recovered fly physiology,
behavior, experience, or consciousness. Dynamics, visual projection and the
Sonic motor mapping are engineered approximations. No trained policy, scripted
gameplay, or direct image-to-motor shortcut is used.

## Developer commands

Run these from the project folder after the first successful `run_flysonic.py`:

```sh
python run_flysonic.py --synthetic                 # explicitly labeled 4,096-cell test fixture, no game
python run_flysonic.py --duration 90 --no-browser  # timed run
python run_flysonic.py --headless --demo-model     # SDL dummy drivers (CI / servers)
.venv/bin/pytest -q
PYTHONPATH=. .venv/bin/python scripts/validate_causality.py
.venv/bin/python -m flysonic.replay artifacts/latest-replay.index.json
```

Stop the existing demo before launching another (`runtime/launcher.lock` refuses a
second instance). The synthetic fixture does not use the full MaleCNS graph or SRB2.

Python 3.11+ is required (`hashlib.file_digest`, `websockets.asyncio`). Tested package
versions are in `requirements-lock.txt`.

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
  locations use a deterministic fallback layout. Rate summaries are by annotated
  **superclass**, not anatomical neuropil ROI.
- The model can collide, get stuck, fall into pits or die. Lives are pinned to
  infinite (`fly_infinitelives`) so a death only respawns Sonic at the last checkpoint;
  no level-completion or natural fly-behavior claim is made.

## Dynamics and controller

Every 20 ms:
`v ← exp(-dt/0.1)·v + 1.5·W·spikes + 0.180 + noise + retina`.

Noise is seeded Bernoulli background activity (1.2 Hz, amplitude 0.22); default
seed 64. Voltage threshold 1 resets to 0. Retinal current is injected **only**
into photoreceptors. Global tonic current and synaptic gain were calibrated (by the
Fly64 author) to make visual perturbations observable downstream; they are not
measured physiological parameters. Luminance, green opponency and absolute temporal
contrast form the retinal drive. The model code is unchanged from Fly64.

A 13-tick (~260 ms) descending-neuron spike window produces a game-agnostic
motor state `Control(x, y, jump)`:

- DNg100 forward activity → `y` (0…70); right-minus-left DNa02/DNg13 → `x` (−70…70).
- DNp01/DNp10 burst threshold >0.04 spikes/cell/tick, 800 ms simulation-time
  cooldown → `jump` event.
- EMA 0.78/0.22, 8-unit dead zone, bounds ±70.

The SRB2 side (`src/fly_bridge.c`, patched into `G_BuildTiccmd`) maps that state as if
it came from an analog gamepad, after SRB2's own dead-zone handling:

- turn axis = `x · 1023 / 70` (positive = right); move axis = `−y · 1023 / 70`
  (negative = forward), so `forwardmove` reaches SRB2's maximum of 50 at `y = 70`;
- each jump event holds `BT_JUMP` for `fly_jumptics` tics (default 8 of 35 per second);
  a second event while airborne triggers Sonic's thok, as for any player;
- `BT_SPIN` is wired (`spin_event`, `fly_spintics`) but the model never emits it;
- the mapping only applies to the local player, in a level, when not paused, when
  neural control is enabled (F6 / `fly_neural`) and when the control packet is fresh.

Neural updates target 50 Hz, framebuffer capture 10 Hz, SRB2 ticks at 35 Hz.
Dashboard publishing drops from 10 to 5 Hz below 0.95 real-time factor. Neural
updates and graph edges are never discarded to catch up.

The dashboard shows retinal input, membrane/spike activity, spike density,
superclass rates, intent avatar and requested controls. **Game received**
independently reports the game-applied controller state (and SRB2 telemetry:
rings, lives, map, level time, speed, position). A moving dashboard stick alone
does not prove the game accepted it.

## Bridge

`runtime/fly_bridge.bin`: 128-byte little-endian header then 9,216 RGB bytes
(64×48×3). The Python side (`flysonic/bridge.py`) and the C side
(`src/fly_bridge.c` in the patch) document the same layout:

| offset | field | owner |
|---:|---|---|
| 0 | magic `FLYSONIC`, 8: version 2 | model (creates the file) |
| 12 | `frame_seq` seqlock (even = stable thumbnail) | game |
| 16 | `control_seq` seqlock (even = stable controls) | model |
| 20 | `enabled` (F6 / `fly_neural`; cleared by the model on shutdown) | game |
| 24 | `control_count`, +1 per control write | model |
| 28 | `stick_x`, 29 `stick_y`, 30 `buttons` (bit0 jump, bit1 spin) | model |
| 32 | `jump_event`, 36 `spin_event` (+1 per event) | model |
| 40 | `applied_seq`, 44 `applied_x`, 45 `applied_y`, 46 `applied_buttons` (SRB2 `BT_*`) | game |
| 48 | `game_tick`, +1 per local tic | game |
| 52 | `game_status`: 0 disabled, 1 applied, 2 stale, 3 torn, 5 paused/not in level | game |
| 56 | `telemetry_seq` seqlock | game |
| 60 | rings, lives, score, map, leveltime, x, y, z, speed, gamestate, playerstate, captures, render_mode, angleturn, forwardmove | game |
| 128 | RGB thumbnail | game |

Liveness never compares clocks across processes (Python on Windows, C on
Windows/Linux and macOS all use different monotonic sources): the game releases
neural controls when `control_count` has not changed for 250 ms of *its* clock,
and the dashboard reports **GAME NOT CONNECTED** (state 4) when `game_tick` has
not changed for 250 ms of the model's clock. Readers reject odd or changed
sequences and keep the last consistent value; every read is bounded (three
attempts), so neither process can hang on the other.

On Windows the file is mapped with `CreateFileMapping`/`MapViewOfFile`, on POSIX
with `mmap`; Python uses `mmap.mmap` on both. Memory ordering: the C side uses
GCC/Clang atomics (or `MemoryBarrier()` with MSVC); the Python side relies on
x86-64's ordering plus sequence validation (macOS keeps `OSMemoryBarrier`).

## Replay

Replay schema 2 is a JSON index plus compressed NPZ chunks. **Every neural tick**
records timestamp, exact retinal frame, spikes and requested controls; the index
includes seed and dynamics parameters. Background compression bounds memory.
Replay verification recomputes every spike and controller output without SRB2,
on the same code/runtime. Floating-point ordering may differ across architectures.
This does not promise bit-identical replay of the game engine.

## Validation

`pytest` covers the bridge layout and seqlocks, liveness, telemetry, normalization,
signed propagation, dense/event equivalence, retinal response, all-tick
deterministic replay, steering signs, jump debounce and the dashboard packet.
`tests/test_srb2_loop.py` runs the real patched SRB2 headless (SDL dummy drivers)
and checks: connection and level entry, ~10 Hz thumbnails with real content,
forward drive echoed and Sonic actually moving, `BT_JUMP` applied for a jump
event, stale release after silence, disable acknowledgement, and disconnection
detection. `scripts/validate_causality.py` compares live/frozen/disconnected
frames with the same seed on the full model and requires different motor outputs
for the connected trials.

Verified so far: Linux x86-64 (Ubuntu 24.04 container, headless). The Windows
build path (MSYS2 UCRT64) is scripted and the Windows branch of `fly_bridge.c`
compiles with MinGW, but a full Windows run is still to be confirmed on a real PC.

## Attribution and private assets

Fly64: Jessica Paquette, https://github.com/barrelshifter/fly64 (model, data
pipeline, dashboard and bridge design).

MaleCNS: Berg et al., *Sexual dimorphism in the complete connectome of the
Drosophila male central nervous system*,
[data and CC-BY terms](https://male-cns.janelia.org/download/).
Optic assignments pinned to supplemental commit
`67767d2233657983993ff6c2be48e836a935863c`.

SRB2: [STJr/SRB2](https://github.com/STJr/SRB2), tag `SRB2_release_2.2.15`,
commit `8701ef41f617c06e23a7b8ccd2199c160c5d1dd1`, GPLv2. Data files from the
official `SRB2-v2215-Full.zip`
(sha256 `3eda3080ab87940fca5e4dcd22b8e041dc1d9e65bfe9177bff68383e9bd58a10`), which
Sonic Team Junior distributes freely but which are not open source and are not
part of this repository. Sonic the Hedgehog and related characters are SEGA
trademarks. The SRB2 source, build, data files, dataset caches, browser profiles
and recordings are gitignored.
