"""Pinball physics, scoring, lifecycle, and control regressions."""
import math
from unittest.mock import create_autospec

import pytest

import src.display.pinball as pb
from src.input.controller import Button, Controller, EventType, InputEvent
from tests.test_pinball_sim import _field_ball


def test_substeps_follow_reflected_velocity():
    game = pb.PinballGame()
    ball = _field_ball(game, 64, 320, vx=8)
    positions = []

    def collide():
        positions.append(ball.x)
        if len(positions) == 1:
            ball.vx = -ball.vx

    ball.update(collide)
    assert len(positions) > 1
    assert positions[1] < positions[0]


def test_substeps_stay_small_after_a_collision_accelerates_ball():
    game = pb.PinballGame()
    ball = _field_ball(game, 64, 320, vx=4)
    positions = [(ball.x, ball.y)]

    def collide():
        positions.append((ball.x, ball.y))
        ball.vx = 12

    ball.update(collide)
    assert all(math.dist(a, b) <= 2.000001
               for a, b in zip(positions, positions[1:]))


def test_weak_launch_redocks_without_remaining_substep_motion():
    game = pb.PinballGame()
    ball = _field_ball(game, pb.PLUNGER_LANE_X, pb.PF_H - 63, vy=8)
    game.update()
    assert ball.in_plunger
    assert (ball.x, ball.y) == (pb.PLUNGER_LANE_X, pb.PF_H - 60)
    assert (ball.vx, ball.vy) == (0, 0)


def test_spinner_scores_once_per_ball_entry():
    game = pb.PinballGame()
    ball = _field_ball(game, *pb.SPINNER_POS)
    for _ in range(10):
        game._collide_spinner(ball)
    assert game.score == pb.SPINNER_PTS
    ball.y += 20
    game._collide_spinner(ball)
    ball.y -= 20
    game._collide_spinner(ball)
    assert game.score == 2 * pb.SPINNER_PTS


def test_multiball_spinner_contacts_are_independent():
    game = pb.PinballGame()
    ball = _field_ball(game, *pb.SPINNER_POS)
    other = pb.Ball()
    other.x, other.y = pb.SPINNER_POS
    game.balls.append(other)
    game._collide_spinner(ball)
    game._collide_spinner(other)
    game._collide_spinner(ball)
    assert game.score == 4 * pb.SPINNER_PTS


def test_multiball_cannot_complete_another_balls_orbit():
    game = pb.PinballGame()
    ball = _field_ball(game, *pb.ORBIT_ENTRY_L, vx=2)
    other = pb.Ball()
    other.x, other.y = pb.ORBIT_EXIT_R
    other.vx = 2
    game.balls.append(other)
    game._collide_orbit(ball)
    game._collide_orbit(other)
    assert game.score == 0
    assert game.orbit_active
    ball.x, ball.y = pb.ORBIT_EXIT_R
    game._collide_orbit(ball)
    assert game.score == 2 * pb.ORBIT_PTS
    assert not game.orbit_active


@pytest.mark.parametrize("entry,exit_,velocity", [
    (pb.ORBIT_ENTRY_L, pb.ORBIT_EXIT_R, 2),
    (pb.ORBIT_EXIT_R, pb.ORBIT_ENTRY_L, -2),
])
def test_orbit_expires_by_frames_not_collision_calls(entry, exit_, velocity):
    game = pb.PinballGame()
    ball = _field_ball(game, *entry, vx=velocity)
    game._collide_orbit(ball)
    for _ in range(pb.ORBIT_WINDOW + 1):
        game._collide_orbit(ball)
    assert game.orbit_active
    ball.x, ball.y = 64, 320
    ball.vx = ball.vy = 0
    for _ in range(pb.ORBIT_WINDOW):
        game.update()
    ball.x, ball.y = exit_
    ball.vx = velocity
    score_before = game.score
    game._collide_orbit(ball)
    assert game.score == score_before
    assert not game.orbit_active


def test_docking_clears_orbit_and_spinner_contacts():
    game = pb.PinballGame()
    ball = _field_ball(game, *pb.ORBIT_ENTRY_L, vx=2)
    game._collide_orbit(ball)
    ball.x, ball.y = pb.SPINNER_POS
    game._collide_spinner(ball)
    ball.reset_to_plunger()
    assert not game.orbit_active
    ball.x, ball.y = pb.SPINNER_POS
    game._collide_spinner(ball)
    assert game.score == 2 * pb.SPINNER_PTS


def test_game_over_is_terminal():
    game = pb.PinballGame()
    game.balls_left = 1
    _field_ball(game, 64, pb.DRAIN_Y + 5)
    game.update()
    assert game.game_over
    score = game.score
    for _ in range(5):
        game.update(True, True)
        game.nudge(1, 0)
    assert game.balls_left == 0
    assert game.score == score
    assert game.nudge_count == 0


def _run_control_frames(monkeypatch, game, events, held=()):
    controller = create_autospec(Controller, instance=True)
    controller.poll_events.side_effect = events
    controller.get_direction.return_value = None
    controller.is_pressed.side_effect = lambda button: button in held
    controller.start_hold_seconds.return_value = 0
    frames = iter([False] * len(events) + [True])
    monkeypatch.setattr(pb, "should_stop", lambda: next(frames))
    monkeypatch.setattr(pb, "PinballGame", lambda: game)
    monkeypatch.setattr(pb, "show_banner", lambda *args, **kwargs: None)
    monkeypatch.setattr(pb.time, "sleep", lambda seconds: None)
    from src.simulator.matrix import RGBMatrix
    matrix = create_autospec(RGBMatrix, instance=True)
    pb._run_interactive(matrix, controller, 0)
    return controller, matrix


def test_both_flippers_remain_held_between_press_events(monkeypatch):
    game = pb.PinballGame()
    _, matrix = _run_control_frames(
        monkeypatch, game, [[], []], held=(Button.LEFT, Button.RIGHT))
    assert game.flip_l.active and game.flip_r.active
    assert matrix.SetImage.call_count == 2
    assert matrix.SetImage.call_args.args[0].size == (64, 64)


def test_tilt_rumble_survives_update_and_is_not_repeated(monkeypatch):
    game = pb.PinballGame()
    _field_ball(game, 64, 320)
    game.nudge_count = pb.TILT_LIMIT - 1
    event = InputEvent(Button.B, EventType.PRESSED, 0)
    controller, _ = _run_control_frames(monkeypatch, game, [[event], []])
    controller.rumble.assert_called_once_with(1.0, 80)


@pytest.mark.parametrize("entry,exit_,velocity", [
    (pb.ORBIT_ENTRY_L, pb.ORBIT_EXIT_R, 2),
    (pb.ORBIT_EXIT_R, pb.ORBIT_ENTRY_L, -2),
])
def test_orbit_scores_in_either_direction_before_deadline(entry, exit_, velocity):
    game = pb.PinballGame()
    ball = _field_ball(game, *entry, vx=velocity)
    game._collide_orbit(ball)
    game.tick += pb.ORBIT_WINDOW - 1
    ball.x, ball.y = exit_
    game._collide_orbit(ball)
    assert game.score == pb.ORBIT_PTS
    assert game.bonus_units == 5
    assert not game.orbit_active


def test_substeps_stop_if_collision_deactivates_ball():
    game = pb.PinballGame()
    ball = _field_ball(game, 64, 320, vx=8)
    positions = []

    def collide():
        positions.append(ball.x)
        ball.active = False

    ball.update(collide)
    assert len(positions) == 1
    assert ball.x == positions[0]


def test_substeps_integrate_one_frame_without_contacts():
    game = pb.PinballGame()
    ball = _field_ball(game, 64, 320, vx=8, vy=-3)
    ball.update()
    assert ball.x == pytest.approx(64 + 8 * pb.BALL_FRICTION)
    assert ball.y == pytest.approx(320 + (-3 + pb.GRAVITY) * pb.BALL_FRICTION)


def test_reflected_ball_moves_away_from_interior_wall_in_same_frame():
    game = pb.PinballGame()
    ball = _field_ball(game, 44, 270, vx=8)
    game.update()
    assert ball.vx < 0
    assert ball.x < 50 - pb.BALL_RADIUS - 1.5
