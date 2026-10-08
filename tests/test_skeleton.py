"""Tests for the dancing skeleton screensaver.

All behaviour (beat clock, move choreography, pose easing) lives in
``SkeletonState`` and the pure ``joints()`` kinematics, so the invariants
that matter -- every move producing a finite pose, moves never repeating
immediately, every bone staying on the panel, feet staying below the hips
and out of the ground -- are checked headlessly over a long soak.
"""

import math
import random

from PIL import Image

from src.display.skeleton import (
    BEAT,
    GROUND_Y,
    HEIGHT,
    MOVES,
    MOVE_BEATS,
    SkeletonState,
    WIDTH,
    _build_base,
    _render,
    _rest_pose,
    joints,
)

DT = 1 / 24


def _soak(seed, frames):
    state = SkeletonState(rng=random.Random(seed))
    for _ in range(frames):
        state.update(DT)
        yield state


def test_every_move_produces_a_complete_finite_pose():
    keys = set(_rest_pose())
    for move in MOVES:
        for beats in (0.0, 0.37, 1.0, 2.5, 7.9, 15.0):
            pose = move(beats)
            assert set(pose) == keys
            assert all(math.isfinite(v) for v in pose.values())
            assert 0.0 <= pose["jaw"] <= 1.0


def test_all_joints_stay_on_the_panel_over_a_long_soak():
    for state in _soak(1, 20000):
        for name, (x, y) in joints(state.pose).items():
            assert 0 <= x <= WIDTH - 1, (name, x)
            assert 0 <= y <= HEIGHT - 1, (name, y)


def test_feet_stay_below_the_hips_and_out_of_the_ground():
    for state in _soak(2, 20000):
        j = joints(state.pose)
        for tag in ("l", "r"):
            assert j["foot_" + tag][1] > j["hip"][1]
            assert j["foot_" + tag][1] <= GROUND_Y + 2


def test_moves_change_on_schedule_and_never_repeat_immediately():
    state = SkeletonState(rng=random.Random(3))
    seen = {state.move}
    previous = state.move
    changes = 0
    for _ in range(20000):
        state.update(DT)
        if state.move != previous:
            previous = state.move
            seen.add(state.move)
            changes += 1
    assert changes > 5
    assert len(seen) > 1


def test_a_move_never_overruns_its_declared_length():
    state = SkeletonState(rng=random.Random(4))
    for _ in range(20000):
        state.update(DT)
        # The clock is checked once per frame, so a move can only overrun
        # by the beats covered by a single frame.
        assert state.beats - state.move_start <= state.move_beats + DT / BEAT
        assert state.move_beats in MOVE_BEATS


def test_pose_eases_instead_of_snapping_to_the_target():
    state = SkeletonState(rng=random.Random(5))
    state.move = [m.__name__ for m in MOVES].index("_move_hop")
    state.pose = _rest_pose()
    before = state.pose["bob"]
    state.update(DT)
    target = state.target_pose()["bob"]
    moved = state.pose["bob"] - before
    assert moved != 0.0
    assert abs(moved) < abs(target - before)


def test_render_returns_a_full_frame_and_leaves_the_base_untouched():
    base = _build_base()
    reference = base.copy()
    state = SkeletonState(rng=random.Random(6))
    for _ in range(120):
        state.update(DT)
        frame = _render(base, state)
        assert isinstance(frame, Image.Image)
        assert frame.size == (WIDTH, HEIGHT)
        assert frame.mode == "RGB"
    assert list(base.getdata()) == list(reference.getdata())


def test_bones_are_drawn_over_the_background():
    base = _build_base()
    state = SkeletonState(rng=random.Random(7))
    state.update(DT)
    frame = _render(base, state)
    changed = sum(1 for a, b in zip(base.getdata(), frame.getdata()) if a != b)
    assert changed > 60
