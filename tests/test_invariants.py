from pathlib import Path
import numpy as np
import pytest
from scipy import sparse
from flysonic.model import FlyModel
from flysonic.main import Replay, SyntheticWorld
from flysonic.replay import verify

ROOT = Path(__file__).resolve().parent.parent


def test_signed_event_propagation_matches_dense():
    m = FlyModel(demo=True)
    m.spikes[m.rng.choice(m.n, 200, replace=False)] = 1
    expected = m.w @ m.spikes
    actual = np.asarray(m.w[:, np.flatnonzero(m.spikes)].sum(axis=1)).ravel()
    np.testing.assert_allclose(actual, expected, atol=1e-6)
    assert m.w.data.min() < 0 < m.w.data.max()


def test_no_visual_motor_shortcut():
    a, b = FlyModel(demo=True), FlyModel(demo=True)
    a.w = sparse.csc_matrix((a.n, a.n), dtype=np.float32)
    b.w = a.w.copy()
    for i in range(50):
        ca, _ = a.step(np.zeros((48, 64, 3), np.uint8))
        cb, _ = b.step(np.full((48, 64, 3), 255, np.uint8))
        assert ca == cb


def test_bilateral_decoder_and_jump():
    m = FlyModel(demo=True)
    m.v[m.turn_right] = 1.5
    m.v[m.jump_nodes] = 1.5
    control, _ = m.step(np.zeros((48, 64, 3), np.uint8), 0)
    assert control.x > 0 and control.jump
    m.v[m.jump_nodes] = 1.5
    assert not m.step(np.zeros((48, 64, 3), np.uint8), .1)[0].jump


def test_replay_all_ticks(tmp_path):
    m = FlyModel(demo=True, seed=23)
    r = Replay(tmp_path / "test.npz", 23, True)
    for i in range(30):
        frame = np.full((48, 64, 3), i * 7, np.uint8)
        c, s = m.step(frame, i * .02)
        r.add(i * .02, frame, c, s)
    r.close()
    assert verify(tmp_path / "test.index.json", tmp_path) == 30


def test_synthetic_world_reacts_to_controls():
    world = SyntheticWorld()
    still = world.frame(0, 0, False)
    assert still.shape == (48, 64, 3) and still.dtype == np.uint8
    for _ in range(10):
        moved = world.frame(70, 70, True)
    assert not np.array_equal(still, moved)


@pytest.mark.skipif(not (ROOT / ".cache/malecns/weights.npz").exists(), reason="MaleCNS cache not prepared")
def test_full_graph_incoming_normalization():
    w = sparse.load_npz(ROOT / ".cache/malecns/weights.npz")
    assert w.shape == (166700, 166700)
    sums = np.asarray(abs(w).sum(axis=1)).ravel()
    np.testing.assert_allclose(sums[sums > 0], 1, atol=2e-6)
