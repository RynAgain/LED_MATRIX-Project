"""
Headless simulation tests for the pinball game (src/display/pinball.py).

No matrix, no controller, no draw() calls in the hot loop: these tests drive
PinballGame.update() directly and assert physics/gameplay invariants.

Covers:
- No wall clipping / out-of-bounds / runaway speed across seeded sims
- Gameplay stays alive (launches happen, score accrues)
- Flipper impulse (active stroke launches up; passive arm adds no energy)
- Swept wall test (fast ball cannot tunnel through an interior wall)
- Kickback (fires once when armed, ignores when disarmed)
- Lock saucer -> two locks -> MULTIBALL spawns 3 balls
- Multiball drain removes a ball without consuming balls_left
- End-of-ball bonus tally (units x 100 x mult, mult resets)
- TILT after nudge limit
- Haptic impact flag set on bumper hits
- score_mult doubles during multiball
"""

import math
import random

import src.display.pinball as pb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _field_ball(g, x=64.0, y=300.0, vx=0.0, vy=0.0):
    """Put the primary ball live on the playfield at (x, y)."""
    b = g.ball
    b.active = True
    b.in_plunger = False
    b.x, b.y = float(x), float(y)
    b.vx, b.vy = float(vx), float(vy)
    b.sub_px = b.sub_py = None
    return b


def _wall_overlap(b):
    """True if the ball centre is embedded (<1px) inside any wall segment."""
    for x1, y1, x2, y2 in pb.WALLS:
        dx, dy = x2 - x1, y2 - y1
        seg_sq = dx * dx + dy * dy
        if seg_sq < 1:
            continue
        t = max(0, min(1, ((b.x - x1) * dx + (b.y - y1) * dy) / seg_sq))
        cx, cy = x1 + t * dx, y1 + t * dy
        if (b.x - cx) ** 2 + (b.y - cy) ** 2 < 1.0:
            return True
    return False


def run_sim(seed, frames=4000):
    """Seeded autonomous sim: launch, AI-flip, relaunch, restart on game over.

    Returns an invariant-violation stats dict; all counters must stay 0.
    """
    random.seed(seed)
    g = pb.PinballGame()
    g.plunger_power = pb.PLUNGER_MAX * 0.95
    g.release_plunger()
    stats = {"launches": 1, "overlaps": 0, "oob": 0, "speed": 0,
             "max_score": 0, "games": 1}
    for _ in range(frames):
        flip_l = flip_r = False
        for b in g.balls:
            if (b.active and not b.in_plunger and b.vy > 0
                    and pb.FLIP_Y - 30 < b.y < pb.FLIP_Y + 5):
                if b.x < pb.PF_W / 2:
                    flip_l = True
                else:
                    flip_r = True
        g.update(flip_l, flip_r)
        for b in g.balls:
            if not b.active or b.in_plunger:
                continue
            if not (pb.WALL_L - 3 <= b.x <= pb.PF_W + 2):
                stats["oob"] += 1
            if not (pb.WALL_TOP - 3 <= b.y <= pb.PF_H + 5):
                stats["oob"] += 1
            sp = math.hypot(b.vx, b.vy)
            if sp > pb.BALL_MAX_SPEED * 2.5 and b.x < pb.PF_W - 20:
                stats["speed"] += 1
            if _wall_overlap(b):
                stats["overlaps"] += 1
        stats["max_score"] = max(stats["max_score"], g.score)
        if g.game_over:
            g = pb.PinballGame()
            stats["games"] += 1
        if g.ball.in_plunger and g.ball.active:
            g.plunger_power = pb.PLUNGER_MAX * random.uniform(0.88, 1.0)
            g.release_plunger()
            stats["launches"] += 1
    return stats


# ---------------------------------------------------------------------------
# Simulation invariants
# ---------------------------------------------------------------------------

def test_no_clipping_across_seeds():
    for seed in (1, 2, 3):
        stats = run_sim(seed, frames=4000)
        assert stats["overlaps"] == 0, (seed, stats)
        assert stats["oob"] == 0, (seed, stats)
        assert stats["speed"] == 0, (seed, stats)


def test_gameplay_stays_alive():
    stats = run_sim(7, frames=3000)
    # Ball must drain and relaunch (game keeps cycling) and scoring must work.
    assert stats["launches"] > 1, stats
    assert stats["max_score"] > 0, stats


# ---------------------------------------------------------------------------
# Flippers
# ---------------------------------------------------------------------------

def test_active_flipper_launches_ball_upward():
    g = pb.PinballGame()
    flip = g.flip_l
    flip.set_active(True)
    flip.update()  # mid up-stroke: omega is at full FLIP_UP_SPEED
    t = 0.8  # near the tip: strongest part of the power gradient
    cx = flip.px + t * pb.FLIP_LENGTH * math.cos(flip.angle)
    cy = flip.py + t * pb.FLIP_LENGTH * math.sin(flip.angle)
    b = _field_ball(g, cx, cy - 3, vx=0.0, vy=2.0)
    assert flip.hit_ball(b)
    assert b.vy < -3.0, (b.vx, b.vy)  # solid upward launch


def test_passive_flipper_adds_no_energy():
    g = pb.PinballGame()
    flip = g.flip_l
    flip.set_active(False)
    for _ in range(10):
        flip.update()  # settle at rest, omega ~ 0
    t = 0.5
    cx = flip.px + t * pb.FLIP_LENGTH * math.cos(flip.angle)
    cy = flip.py + t * pb.FLIP_LENGTH * math.sin(flip.angle)
    b = _field_ball(g, cx, cy - 3, vx=0.0, vy=3.0)
    speed_before = math.hypot(b.vx, b.vy)
    flip.hit_ball(b)
    speed_after = math.hypot(b.vx, b.vy)
    assert speed_after <= speed_before + 0.01, (speed_before, speed_after)


# ---------------------------------------------------------------------------
# Walls
# ---------------------------------------------------------------------------

def test_fast_ball_cannot_tunnel_interior_wall():
    # Vertical lane-divider wall at x=50, y 240..300. A ball moving at 8px/f
    # from x=44 would cross it in a single frame without the swept test.
    g = pb.PinballGame()
    b = _field_ball(g, 44, 270, vx=8.0, vy=0.0)
    g.update()
    assert b.x < 51.5, (b.x, b.y)  # stayed on the left side (allow contact slop)


# ---------------------------------------------------------------------------
# Kickback
# ---------------------------------------------------------------------------

def test_kickback_fires_once_and_disarms():
    g = pb.PinballGame()
    assert g.kickback  # armed at game start
    b = _field_ball(g, 18, pb.FLIP_Y + 20, vx=0.0, vy=3.0)
    g._kickback_check(b)
    assert not g.kickback
    assert b.vy == -pb.KICKBACK_POWER
    assert g.banner_text == "KICKBACK"
    assert g.impact >= 0.8


def test_kickback_inert_when_disarmed():
    g = pb.PinballGame()
    g.kickback = False
    b = _field_ball(g, 18, pb.FLIP_Y + 20, vx=0.0, vy=3.0)
    g._kickback_check(b)
    assert b.vy == 3.0  # untouched: ball keeps falling to the drain


# ---------------------------------------------------------------------------
# Lock saucer / multiball
# ---------------------------------------------------------------------------

def _enter_lock(g):
    g.lock_cooldown = 0
    b = _field_ball(g, pb.LOCK_POS[0], pb.LOCK_POS[1], vx=0.0, vy=1.0)
    g._collide_lock(b)
    return b


def test_lock_two_balls_then_multiball():
    g = pb.PinballGame()
    _enter_lock(g)
    assert g.locked == 1
    assert g.ball.in_plunger  # captured ball re-docks on the plunger
    _enter_lock(g)
    assert g.locked == 2
    assert len(g.balls) == 1
    _enter_lock(g)  # third entry releases everything
    assert g.locked == 0
    assert len(g.balls) == pb.MULTIBALL_BALLS
    assert g.banner_text == "MULTIBALL"
    assert all(b.active and not b.in_plunger for b in g.balls)


def test_lock_debounce_blocks_immediate_recapture():
    g = pb.PinballGame()
    _enter_lock(g)
    assert g.locked == 1
    b = _field_ball(g, pb.LOCK_POS[0], pb.LOCK_POS[1], vx=0.0, vy=1.0)
    g._collide_lock(b)  # cooldown still hot: no second capture
    assert g.locked == 1


def test_multiball_drain_does_not_consume_balls_left():
    g = pb.PinballGame()
    _enter_lock(g)
    _enter_lock(g)
    _enter_lock(g)
    assert len(g.balls) == 3
    balls_left_before = g.balls_left
    # Park two balls safely mid-field, drain the third
    _field_ball(g, 64, 300)
    g.balls[1].x, g.balls[1].y = 40.0, 300.0
    g.balls[1].vx = g.balls[1].vy = 0.0
    g.balls[2].y = float(pb.PF_H + 5)  # past the drain line
    g.update()
    assert len(g.balls) == 2
    assert g.balls_left == balls_left_before
    # Drain one more: back to single-ball play, banner announces it
    g.balls[1].y = float(pb.PF_H + 5)
    g.update()
    assert len(g.balls) == 1
    assert g.balls_left == balls_left_before
    assert g.banner_text == "MULTIBALL OVER"


def test_score_mult_doubles_during_multiball():
    g = pb.PinballGame()
    g.bonus_mult = 3
    assert g.score_mult == 3
    g.balls.append(pb.Ball())
    assert g.score_mult == 6
    g.balls.pop()
    assert g.score_mult == 3


# ---------------------------------------------------------------------------
# End-of-ball bonus
# ---------------------------------------------------------------------------

def test_end_of_ball_bonus_tally():
    g = pb.PinballGame()
    g.bonus_units = 7
    g.bonus_mult = 2
    score_before = g.score
    g._award_end_of_ball_bonus()
    assert g.score - score_before == 7 * 100 * 2
    assert g.bonus_units == 0
    assert g.bonus_mult == 1  # multiplier must be re-earned each ball


def test_bonus_awarded_on_real_drain():
    g = pb.PinballGame()
    g.ball_save_timer = 0
    g.bonus_units = 4
    g.bonus_mult = 2
    balls_before = g.balls_left
    score_before = g.score
    b = _field_ball(g, 64, pb.PF_H + 5)  # already past the drain line
    g.update()
    assert g.score - score_before == 4 * 100 * 2
    assert g.balls_left == balls_before - 1
    assert g.bonus_mult == 1
    assert b.in_plunger  # next ball served


def test_ball_save_skips_bonus():
    g = pb.PinballGame()
    g.ball_save_timer = pb.FPS
    g.bonus_units = 4
    balls_before = g.balls_left
    score_before = g.score
    _field_ball(g, 64, pb.PF_H + 5)
    g.update()
    assert g.score == score_before  # no bonus on a saved ball
    assert g.balls_left == balls_before
    assert g.bonus_units == 4  # units carry on with the saved ball


# ---------------------------------------------------------------------------
# Tilt + haptics
# ---------------------------------------------------------------------------

def test_tilt_after_nudge_limit():
    g = pb.PinballGame()
    _field_ball(g, 64, 300)
    for _ in range(pb.TILT_LIMIT):
        g.nudge(1, 0)
    assert g.tilt
    assert g.tilt_timer > 0
    assert g.impact >= 1.0  # tilt slams the rumble


def test_impact_set_on_bumper_hit():
    g = pb.PinballGame()
    bx, by, br = pb.BUMPERS[0]
    b = _field_ball(g, bx, by - br, vx=0.0, vy=2.0)
    g.impact = 0.0
    g._collide_bumpers(b)
    assert g.impact >= 0.5
    assert b.vy < 0  # bumper kicks the ball away
