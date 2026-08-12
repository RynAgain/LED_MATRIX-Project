"""Regression tests for flipper physics (src/display/pinball.py).

Bug history: Flipper.hit_ball gated its minimum-launch power on
abs(omega) > 0.05, but the up-stroke only lasts ~2.3 frames, so any press
more than a couple frames early produced a dead rebound (measured 0.00
upward vy).  Separately, the 0.45 rad/frame up-stroke could rotate clean
past the ball between collision substeps (tunneling), trapping it under
the arm (the lead-2 dead spot).  These tests pin the fixed behaviour with
a deterministic drop harness.
"""
import math
import random

import pytest

from src.display.pinball import PinballGame, Flipper, FLIP_Y, FLIP_LENGTH


def drop_onto_left_flipper(lead_frames, drop_x=48, drop_h=40, tail=120):
    """Drop a ball from rest onto the left flipper; press flip (and hold)
    `lead_frames` before predicted contact.  Returns (best_upward_vy,
    rise_px above contact height)."""
    random.seed(1)
    g = PinballGame()
    b = g.ball
    b.in_plunger = False
    b.x, b.y = drop_x, FLIP_Y - drop_h
    b.vx = b.vy = 0.0
    # Predict frames to contact under gravity 0.12.
    ftc, sy, svy = 0, b.y, 0.0
    while sy < FLIP_Y - 4 and ftc < 300:
        svy += 0.12
        sy += svy
        ftc += 1
    best, min_y = 0.0, b.y
    for f in range(ftc + tail):
        g.update(f >= ftc - lead_frames, False)
        if b.in_plunger:  # drained and respawned; stop measuring
            break
        if f > ftc - lead_frames - 1:
            best = min(best, b.vy)
            min_y = min(min_y, b.y)
    return best, (FLIP_Y - 4) - min_y


def test_perfectly_timed_flip_launches_hard():
    vy, rise = drop_onto_left_flipper(0)
    assert vy <= -9.0
    assert rise >= 100


@pytest.mark.parametrize("lead", [1, 2, 3, 4])
def test_mid_stroke_contact_has_no_dead_spot(lead):
    # lead=2 used to tunnel: the stroke swept past the ball between
    # substeps and smacked it downward from above (best vy -2.4).
    vy, rise = drop_onto_left_flipper(lead)
    assert vy <= -8.0, f"lead={lead} launch too weak (vy={vy:.2f})"
    assert rise >= 50


@pytest.mark.parametrize("lead", [8, 12, 20, 30])
def test_held_flipper_still_launches(lead):
    # Pressing early (flipper already fully raised at contact) used to give
    # a dead rebound (0.00 upward vy).  A held flipper must still deliver a
    # firm push back into the playfield.
    vy, rise = drop_onto_left_flipper(lead)
    assert vy <= -3.5, f"lead={lead} held launch too weak (vy={vy:.2f})"
    assert rise >= 25


def test_live_stroke_beats_held_flipper():
    timed, _ = drop_onto_left_flipper(0)
    held, _ = drop_onto_left_flipper(20)
    assert timed < held  # more negative = stronger launch


def test_swept_stroke_launches_upward_not_downward():
    """Direct unit test of the swept-wedge branch: place a ball just above
    a flipper mid-up-stroke position, sweep the arm past it in one update,
    and confirm the synthesized hit pushes the ball up (vy < 0)."""
    random.seed(1)
    g = PinballGame()
    fl = g.flip_l
    b = g.ball
    b.in_plunger = False
    # Park the ball where the arm will sweep through this frame.
    fl.angle = fl.rest_angle
    fl.prev_angle = fl.rest_angle
    fl.set_active(True)
    ang = fl.rest_angle - 0.2  # inside the coming sweep window
    r = FLIP_LENGTH * 0.8
    b.x = fl.px + r * math.cos(ang)
    b.y = fl.py + r * math.sin(ang)
    b.vx, b.vy = 0.0, 1.0
    fl.update()  # sweeps 0.45 rad up, past the ball
    assert fl.hit_ball(b)
    assert b.vy < -3.0
