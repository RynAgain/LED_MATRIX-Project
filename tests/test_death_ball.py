"""Death Ball input, match rules, collision, and demo regressions."""

import math
import random
from unittest.mock import create_autospec

import pytest

from src.display import death_ball as db
from src.input.controller import Button, Controller, EventType, InputEvent
from src.simulator.matrix import RGBMatrix


@pytest.fixture(autouse=True)
def isolated_random():
    state = random.getstate()
    random.seed(7)
    yield
    random.setstate(state)


@pytest.mark.parametrize("wall", [db.DEFENSE_WALL_LEFT_X, db.DEFENSE_WALL_RIGHT_X])
@pytest.mark.parametrize("side", [-1, 1])
@pytest.mark.parametrize("speed_mult", [1, 2])
def test_ball_bounces_on_both_faces_without_tunneling(wall, side, speed_mult):
    ball = db.Ball()
    ball.x, ball.y = wall + side * 3, 30
    ball.speed_mult = speed_mult
    ball.vx = -side * 5 * speed_mult
    ball.update_physics()
    assert (ball.x - wall) * side >= 1.5
    assert ball.vx * side > 0


@pytest.mark.parametrize("y", [10, 52])
def test_ball_can_pass_above_and_below_defensive_wall(y):
    ball = db.Ball()
    ball.x, ball.y, ball.vx = 13, y, -5
    ball.update_physics()
    assert ball.x < db.DEFENSE_WALL_LEFT_X
    assert ball.vx < 0


@pytest.mark.parametrize("mult", [1, 2])
def test_speed_limit_applies_before_motion(mult):
    ball = db.Ball()
    ball.x, ball.y, ball.vx, ball.vy = 32, 10, 30, 0
    ball.speed_mult = mult
    ball.update_physics()
    assert math.hypot(ball.x - 32, ball.y - 10) <= db.BALL_MAX_SPEED * mult + 1e-9
    assert ball.get_speed() <= db.BALL_MAX_SPEED * mult


@pytest.mark.parametrize("x,vx,scorer", [(1, -5, 1), (62, 5, 0)])
def test_goal_crossing_scores_once(x, vx, scorer):
    game = db.DeathBallGame()
    game.ball.x, game.ball.y, game.ball.vx = x, 32, vx
    game.update()
    assert game.scores[scorer] == 1
    assert sum(game.scores) == 1
    for _ in range(db.FPS):
        game.update()
    assert sum(game.scores) == 1
    assert game.round_pause == 0


@pytest.mark.parametrize("x,vx", [(2.1, -5), (60.9, 5)])
def test_outer_wall_outside_goal_reflects(x, vx):
    ball = db.Ball()
    ball.x, ball.y, ball.vx = x, 10, vx
    ball.update_physics()
    assert ball.check_goal() == -1
    assert ball.vx * vx < 0
    assert 2 <= ball.x <= 61


@pytest.mark.parametrize("y,vy", [(1.1, -5), (60.9, 5)])
def test_vertical_boundaries_reflect(y, vy):
    ball = db.Ball()
    ball.y, ball.vy = y, vy
    ball.update_physics()
    assert ball.vy * vy < 0
    assert 1 <= ball.y <= 61


def test_platform_collision_uses_crossing(monkeypatch):
    monkeypatch.setattr(db, "PLATFORMS", [(25, 40, 30)])
    ball = db.Ball()
    ball.y, ball.vy = 25, 5
    ball.update_physics()
    assert ball.y <= 28
    assert ball.vy < 0


@pytest.mark.parametrize("scores,winner", [([1, 0], 0), ([0, 2], 1)])
def test_timeout_awards_leader_and_stops_updates(scores, winner):
    game = db.DeathBallGame()
    game.scores, game.timer = scores, 1
    game.update()
    assert game.timer == 0
    assert game.check_winner() == winner
    snapshot = (game.tick, game.ball.x, game.ball.y, game.timer)
    for _ in range(5):
        game.update()
    assert (game.tick, game.ball.x, game.ball.y, game.timer) == snapshot


def test_tie_enters_overtime_and_next_goal_wins():
    game = db.DeathBallGame()
    game.scores, game.timer = [1, 1], 1
    game.update()
    assert game.sudden_death
    assert game.ball.speed_mult == 2
    assert game.check_winner() == -1
    game.ball.x, game.ball.y, game.ball.vx = 62, 32, 5
    game.update()
    assert game.scores == [2, 1]
    assert game.check_winner() == 0
    assert game.ball.speed_mult == 2


def test_reset_and_pause_preserve_resources_and_freeze_actions():
    game = db.DeathBallGame()
    for wizard in (game.wizard1, game.wizard2):
        wizard.jumps_left = 0
        wizard.on_ground = False
        wizard.mana = 20
        wizard.blast_cooldown = 4
        wizard.facing *= -1
    game.reset_round()
    for wizard, x, facing in ((game.wizard1, 16, 1), (game.wizard2, 48, -1)):
        assert (wizard.x, wizard.y, wizard.facing) == (x, 62, facing)
        assert wizard.on_ground and wizard.jumps_left == 2
        assert (wizard.mana, wizard.blast_cooldown) == (20, 4)
        game.apply_controls((1, True, True, True), (1, True, True, True))
        assert (wizard.vx, wizard.vy, wizard.jumps_left, wizard.mana) == (0, 0, 2, 20)
    timer = game.timer
    game.update()
    assert game.timer == timer
    assert game.round_pause == db.FPS - 1


@pytest.mark.parametrize("action", ["kick", "blast"])
def test_impulses_obey_speed_cap(action):
    game = db.DeathBallGame()
    wizard = game.wizard1
    game.ball.x, game.ball.y = wizard.x + 2, wizard.y
    game.ball.vx = 5
    wizard.vx = 8
    if action == "kick":
        assert game.kick_ball(wizard)
    else:
        assert game.magic_blast(wizard)
    assert game.ball.get_speed() <= db.BALL_MAX_SPEED + 1e-9


def test_attack_ai_is_mirrored(monkeypatch):
    monkeypatch.setattr(db.random, "random", lambda: 1)
    game = db.DeathBallGame()
    game.wizard1.x, game.wizard1.y = 28, 30
    game.ball.x, game.ball.y = 32, 30
    p1 = db._ai_control(game, game.wizard1, game.wizard2)
    game.wizard2.x, game.wizard2.y = 35, 30
    game.ball.x = 31
    p2 = db._ai_control(game, game.wizard2, game.wizard1)
    assert p1[0] == 1 and p2[0] == -1
    assert p1[1:] == p2[1:]


def _run_frames(monkeypatch, game, frames, quit_requested=False):
    controller = create_autospec(Controller, instance=True)
    controller.poll_events.side_effect = frames
    controller.is_pressed.return_value = quit_requested
    controller.start_hold_seconds.return_value = 0
    controller.get_direction.return_value = (1, 0)
    matrix = create_autospec(RGBMatrix, instance=True)
    monkeypatch.setattr(db, "DeathBallGame", lambda: game)
    monkeypatch.setattr(db, "show_banner", lambda *args, **kwargs: None)
    stops = iter([False] * len(frames) + [True])
    monkeypatch.setattr(db, "should_stop", lambda: next(stops))
    monkeypatch.setattr(db.time, "time", lambda: 0)
    monkeypatch.setattr(db.time, "sleep", lambda _: None)
    monkeypatch.setattr(db, "_ai_control", lambda *args: (0, False, False, False))
    db._run_interactive(matrix, controller, 0)
    return controller, matrix


@pytest.mark.parametrize("button", [Button.A, Button.UP, Button.B])
def test_interactive_loop_preserves_first_poll_edges(monkeypatch, button):
    game = db.DeathBallGame()
    event = InputEvent(button, EventType.PRESSED, 0)
    controller, matrix = _run_frames(monkeypatch, game, [[event], []])
    assert controller.poll_events.call_count == 2
    assert matrix.SetImage.call_count == 2
    assert matrix.SetImage.call_args.args[0].size == (64, 64)
    assert matrix.SetImage.call_args.args[0].getbbox() is not None
    if button == Button.B:
        assert game.wizard1.mana == 54
    else:
        assert game.wizard1.jumps_left == 1
        assert game.wizard1.y < 62


def test_up_and_a_together_do_not_consume_double_jump(monkeypatch):
    game = db.DeathBallGame()
    events = [InputEvent(b, EventType.PRESSED, 0) for b in (Button.UP, Button.A)]
    _run_frames(monkeypatch, game, [events])
    assert game.wizard1.jumps_left == 1


def test_interactive_pause_ignores_actions_but_quit_works(monkeypatch):
    game = db.DeathBallGame()
    game.reset_round()
    events = [InputEvent(b, EventType.PRESSED, 0) for b in (Button.A, Button.B)]
    _run_frames(monkeypatch, game, [events])
    assert (game.wizard1.x, game.wizard1.jumps_left, game.wizard1.mana) == (16, 2, 100)
    _, matrix = _run_frames(monkeypatch, game, [[]], quit_requested=True)
    matrix.SetImage.assert_not_called()


@pytest.mark.parametrize("seed", range(5))
def test_seeded_demo_invariants(seed):
    random.seed(seed)
    game = db.DeathBallGame()
    goals = matches = 0
    for frame in range(6000):
        controls = [db._ai_control(game, game.wizard1, game.wizard2),
                    db._ai_control(game, game.wizard2, game.wizard1)]
        game.apply_controls(*controls)
        old_score = sum(game.scores)
        game.update()
        goals += sum(game.scores) - old_score
        ball = game.ball
        assert 0 <= ball.x <= 63 and 1 <= ball.y <= 61
        assert ball.get_speed() <= db.BALL_MAX_SPEED * ball.speed_mult + 1e-9
        if db.DEFENSE_WALL_TOP <= ball.y <= db.DEFENSE_WALL_BOTTOM:
            for wall in (db.DEFENSE_WALL_LEFT_X, db.DEFENSE_WALL_RIGHT_X):
                assert abs(ball.x - wall) >= 1.5 - 1e-9
        if frame % 100 == 0:
            assert game.draw().size == (64, 64)
        if game.check_winner() >= 0:
            matches += 1
            game = db.DeathBallGame()
    assert goals > 0
    assert matches > 0


@pytest.mark.parametrize("interactive", [False, True])
def test_run_renders_and_clears_matrix(monkeypatch, interactive):
    matrix = create_autospec(RGBMatrix, instance=True)
    controller = create_autospec(Controller, instance=True) if interactive else None
    if controller is not None:
        controller.poll_events.return_value = []
        controller.is_pressed.return_value = False
        controller.start_hold_seconds.return_value = 0
        controller.get_direction.return_value = None
    stops = iter([False, False, True])
    monkeypatch.setattr(db, "should_stop", lambda: next(stops))
    monkeypatch.setattr(db.time, "time", lambda: 0)
    monkeypatch.setattr(db.time, "sleep", lambda _: None)
    monkeypatch.setattr(db, "show_banner", lambda *args, **kwargs: None)
    db.run(matrix, duration=10, controller=controller)
    assert matrix.SetImage.call_count == 2
    assert matrix.SetImage.call_args.args[0].getbbox() is not None
    matrix.Clear.assert_called_once()


@pytest.mark.parametrize("interactive", [False, True])
def test_run_handles_match_winner(monkeypatch, interactive):
    game = db.DeathBallGame()
    game.scores, game.timer = [1, 0], 1
    matrix = create_autospec(RGBMatrix, instance=True)
    controller = create_autospec(Controller, instance=True) if interactive else None
    if controller is not None:
        controller.poll_events.return_value = []
        controller.is_pressed.return_value = False
        controller.start_hold_seconds.return_value = 0
        controller.get_direction.return_value = None
    factory = create_autospec(db.DeathBallGame, side_effect=[game, db.DeathBallGame()])
    monkeypatch.setattr(db, "DeathBallGame", factory)
    banners = []
    monkeypatch.setattr(db, "show_banner", lambda matrix, lines, **kwargs: banners.append(lines))
    stops = iter([False, True])
    monkeypatch.setattr(db, "should_stop", lambda: next(stops))
    monkeypatch.setattr(db.time, "time", lambda: 0)
    db.run(matrix, duration=10, controller=controller)
    assert banners[-1] == (["YOU WIN!", "1-0"] if interactive else ["P1 WINS", "1-0"])
    assert factory.call_count == (1 if interactive else 2)
    if interactive:
        controller.rumble.assert_called_once_with(1.0, 300)
    matrix.Clear.assert_called_once()


@pytest.mark.parametrize("pause,finished", [(True, False), (False, True)])
def test_actions_cannot_mutate_paused_or_finished_game(pause, finished):
    game = db.DeathBallGame()
    if pause:
        game.reset_round()
    if finished:
        game.scores = [db.WIN_SCORE, 0]
    before = vars(game.wizard1).copy()
    assert not game.magic_blast(game.wizard1)
    game.apply_controls((1, True, True, True), (1, True, True, True))
    assert vars(game.wizard1) == before


def test_wizard_platform_landing_restores_jumps(monkeypatch):
    monkeypatch.setattr(db, "PLATFORMS", [(25, 40, 30)])
    wizard = db.Wizard(32, 28, 1, 0)
    wizard.jumps_left = 0
    wizard.vy = 1
    wizard.update_physics()
    assert (wizard.y, wizard.vy, wizard.jumps_left) == (29, 0, 2)
    assert wizard.on_ground


def test_ball_reflection_uses_updated_velocity_in_remaining_substeps():
    ball = db.Ball()
    ball.x, ball.y, ball.vx = 12, 30, -5
    ball.update_physics()
    assert ball.vx > 0
    assert ball.x > 13


def test_separate_jump_edges_allow_double_jump(monkeypatch):
    game = db.DeathBallGame()
    press = InputEvent(Button.A, EventType.PRESSED, 0)
    release = InputEvent(Button.A, EventType.RELEASED, 0)
    _run_frames(monkeypatch, game, [[press], [release], [press]])
    assert game.wizard1.jumps_left == 0
    assert game.wizard1.vy == pytest.approx(db.DOUBLE_JUMP_VEL + db.GRAVITY)


@pytest.mark.parametrize("caster", [0, 1])
def test_both_players_retain_horizontal_blast_knockback(caster):
    game = db.DeathBallGame()
    game.wizard1.x, game.wizard1.y = 30, 40
    game.wizard2.x, game.wizard2.y = 35, 40
    controls = [(0, False, False, False), (0, False, False, False)]
    controls[caster] = (0, False, True, False)
    game.apply_controls(*controls)
    opponent = game.wizard2 if caster == 0 else game.wizard1
    assert opponent.vx == pytest.approx(2.7 if caster == 0 else -2.7)
    old_x = opponent.x
    game.update()
    assert (opponent.x - old_x) * (1 if caster == 0 else -1) > 0


@pytest.mark.parametrize("caster", [0, 1])
def test_simultaneous_jump_cannot_erase_blast_knockback(caster):
    game = db.DeathBallGame()
    game.wizard1.x, game.wizard1.y = 30, 40
    game.wizard2.x, game.wizard2.y = 35, 40
    controls = [(0, True, False, False), (0, True, False, False)]
    controls[caster] = (0, False, True, False)
    game.apply_controls(*controls)
    opponent = game.wizard2 if caster == 0 else game.wizard1
    assert opponent.vy == pytest.approx(db.JUMP_VEL - 1.5)
