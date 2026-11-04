import math
from unittest.mock import Mock

import pytest
from PIL import ImageChops

from src.display import _shared, snake, snake_scene
from tests.test_playable_games import FakeController


@pytest.fixture
def game():
    result = snake.SnakeGame()
    result.food = (40, 32)
    result.food_is_gold = False
    return result


@pytest.mark.parametrize('direction', snake.DIRECTIONS)
def test_camera_tracks_all_headings(direction):
    camera = snake_scene.ChaseCamera((32, 32), direction)
    head = camera.project((32, 0.7, 32))
    forward = camera.project((32 + direction[0] * 5, 0.7, 32 + direction[1] * 5))
    right = camera.project((32 - direction[1], 0.7, 32 + direction[0]))
    assert head[0] == pytest.approx(32)
    assert forward[1] < head[1]
    assert right[0] > head[0]
    assert camera.project((32 - direction[0] * 20, 0, 32 - direction[1] * 20)) is None


def test_near_plane_clips_crossing_polygon():
    points = snake_scene._clip_polygon([(-1, 0, -1), (1, 0, 2), (1, 1, 2), (-1, 1, -1)])
    assert len(points) == 4
    assert all(p[2] >= snake_scene.NEAR for p in points)
    assert all(math.isfinite(v) for p in points for v in p)
    assert snake_scene._clip_polygon([(0, 0, -2), (1, 0, -2), (0, 1, -2)]) == []


@pytest.mark.parametrize('direction', snake.DIRECTIONS)
@pytest.mark.parametrize('head', [(32, 32), (0, 0), (63, 63)])
def test_render_headings_and_arena_edges(game, direction, head):
    game.snake = [head]
    game.direction = direction
    image = snake_scene.render(game)
    assert image.size == (64, 64)
    assert image.mode == 'RGB'
    assert snake_scene.HEAD_COLOR in image.crop((0, 18, 64, 64)).getdata()


def test_food_behind_camera_visible_on_overview(game):
    game.food = (4, 32)
    assert snake_scene.ChaseCamera(game.snake[0], game.direction).project((4, 1, 32)) is None
    image = snake_scene.render(game)
    assert image.getpixel((48, 9)) == snake_scene.FOOD_RED
    game.food_is_gold = True
    assert snake_scene.render(game).getpixel((48, 9)) == snake_scene.FOOD_GOLD


def test_food_pulses_and_death_changes_scene(game):
    dark = snake_scene.render(game, -math.pi / 2)
    bright = snake_scene.render(game, math.pi / 2)
    assert ImageChops.difference(dark, bright).getbbox() is not None
    dead = snake_scene.render(game, red_count=len(game.snake))
    assert snake_scene.DEATH_COLOR in dead.getdata()
    assert ImageChops.difference(bright, dead).getbbox() is not None


def test_draw_uses_real_renderer_without_mutating_state(game):
    matrix = Mock()
    before = (list(game.snake), game.direction, game.food, game.score)
    game.draw(matrix)
    image = matrix.SetImage.call_args.args[0]
    assert image.tobytes() == snake_scene.render(game).tobytes()
    assert (game.snake, game.direction, game.food, game.score) == before


@pytest.mark.parametrize('gold,points', [(False, 1), (True, 2)])
def test_food_grows_snake_and_scores(game, gold, points):
    game.food = (33, 32)
    game.food_is_gold = gold
    game.step(direction=snake.RIGHT)
    assert len(game.snake) == 4
    assert game.score == points
    assert game.food not in game.snake


@pytest.mark.parametrize('directions,expected', [
    ([snake.LEFT] * 3, [snake.UP] * 3),
    ([snake.RIGHT] * 3, [snake.DOWN] * 3),
    ([snake.LEFT, None, snake.LEFT], [snake.UP, snake.UP, snake.LEFT]),
    ([snake.RIGHT, None, snake.RIGHT], [snake.DOWN, snake.DOWN, snake.LEFT]),
    ([snake.DOWN, snake.UP, None], [snake.RIGHT] * 3),
])
def test_real_interactive_loop_relative_steering(game, monkeypatch, directions, expected):
    monkeypatch.setattr(snake, 'SnakeGame', lambda: game)
    monkeypatch.setattr(snake, 'show_banner', lambda *a, **k: None)
    ticks = iter(i * snake.FRAME_DUR for i in range(20))
    monkeypatch.setattr(snake.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(snake.time, 'sleep', lambda *a: None)
    _shared.clear_stop()
    headings = []
    matrix = Mock()
    matrix.SetImage.side_effect = lambda image: headings.append(game.direction)
    controller = FakeController(directions=directions, quit_after=len(directions) + 1)
    snake.run(matrix, controller=controller)
    assert headings == expected
    matrix.Clear.assert_called_once()
    assert game.alive


def test_death_animation_stops_promptly(game, monkeypatch):
    matrix = Mock()
    monkeypatch.setattr(snake, 'interruptible_sleep', lambda *a: None)
    monkeypatch.setattr(snake, 'should_stop', lambda: True)
    game.draw_death(matrix)
    matrix.SetImage.assert_not_called()
    monkeypatch.setattr(snake, 'should_stop', lambda: False)
    game.draw_death(matrix)
    assert matrix.SetImage.call_count == len(game.snake)
    assert snake_scene.DEATH_COLOR in matrix.SetImage.call_args.args[0].getdata()


@pytest.mark.parametrize('food', [(36, 32), (33, 33), (30, 33)])
@pytest.mark.parametrize('gold', [False, True])
def test_minimap_food_wins_over_heading_head_and_body(game, food, gold):
    game.food = food
    game.food_is_gold = gold
    image = snake_scene.render(game)
    pixel = (47 + food[0] // 4, 1 + food[1] // 4)
    assert image.getpixel(pixel) == (snake_scene.FOOD_GOLD if gold else snake_scene.FOOD_RED)


@pytest.fixture
def timed_play(game, monkeypatch):
    from tests.test_input import FakeClock

    clock = FakeClock()
    frames = []
    monkeypatch.setattr(snake.time, 'monotonic', clock)
    monkeypatch.setattr(snake.time, 'sleep', clock.advance)
    monkeypatch.setattr(snake, 'SnakeGame', lambda: game)
    monkeypatch.setattr(snake, 'show_banner', lambda *a, **k: None)
    matrix = Mock()
    matrix.SetImage.side_effect = lambda image: frames.append((clock.t, game.direction))
    _shared.clear_stop()
    yield clock, frames, matrix
    _shared.clear_stop()


@pytest.mark.parametrize('directions,expected', [
    ([None, snake.LEFT, None], [snake.RIGHT, snake.UP, snake.UP]),
    ([None, snake.RIGHT, None], [snake.RIGHT, snake.DOWN, snake.DOWN]),
    ([None, snake.LEFT, None, snake.RIGHT, None], [snake.RIGHT, snake.UP, snake.RIGHT]),
    ([None, snake.LEFT, None, snake.LEFT, None], [snake.RIGHT, snake.UP, snake.LEFT]),
    ([None] + [snake.LEFT] * 24, [snake.RIGHT, snake.UP, snake.UP]),
    ([None, snake.LEFT, None, snake.RIGHT, None, snake.LEFT, None],
     [snake.RIGHT, snake.UP, snake.RIGHT]),
])
def test_short_taps_queue_once_per_movement_tick(timed_play, directions, expected):
    clock, frames, matrix = timed_play
    controller = FakeController(directions=directions, quit_after=25)
    snake._run_interactive(matrix, controller, snake.time.time())
    assert [direction for _, direction in frames][:3] == expected
    assert all(b[0] - a[0] >= snake.FRAME_DUR - 1e-9 for a, b in zip(frames, frames[1:]))
    assert controller.poll_count > len(frames) * 4
    assert clock.t < 0.25


def test_real_controller_captures_keyboard_tap_between_movement_ticks(timed_play, monkeypatch):
    from tests.test_input import FakeEvent, FakePygame, make_controller
    from src.simulator.matrix import _SimulatorWindow

    clock, frames, matrix = timed_play
    monkeypatch.setattr(_SimulatorWindow, '_instance', None)
    pg = FakePygame()
    controller, _ = make_controller(pygame_obj=pg, clock=clock)
    poll = controller.poll_events
    count = 0

    def scripted_poll():
        nonlocal count
        count += 1
        if count == 2:
            pg.event.post(FakeEvent(pg.KEYDOWN, key=pg.K_LEFT))
        elif count == 4:
            pg.event.post(FakeEvent(pg.KEYUP, key=pg.K_LEFT))
        elif count == 20:
            pg.event.post(FakeEvent(pg.QUIT))
        return poll()

    monkeypatch.setattr(controller, 'poll_events', scripted_poll)
    snake._run_interactive(matrix, controller, snake.time.time())
    assert [direction for _, direction in frames][:2] == [snake.RIGHT, snake.UP]
    assert controller.is_quitting()


def test_third_buffered_turn_is_dropped_not_delayed(timed_play):
    clock, frames, matrix = timed_play
    controller = FakeController(
        directions=[None, snake.LEFT, None, snake.RIGHT, None, snake.LEFT, None],
        quit_after=41,
    )
    snake._run_interactive(matrix, controller, snake.time.time())
    assert len(frames) >= 4
    assert [direction for _, direction in frames[:3]] == [snake.RIGHT, snake.UP, snake.RIGHT]
    assert all(direction == snake.RIGHT for _, direction in frames[3:])


def test_render_time_is_within_movement_deadline(timed_play):
    clock, frames, matrix = timed_play

    def slow_render(image):
        frames.append((clock.t, snake.RIGHT))
        clock.advance(0.020)

    matrix.SetImage.side_effect = slow_render
    controller = FakeController(quit_after=25)
    snake._run_interactive(matrix, controller, snake.time.time())
    assert len(frames) >= 3
    for index, (timestamp, _) in enumerate(frames):
        assert timestamp == pytest.approx(index * snake.FRAME_DUR, abs=snake.INPUT_INTERVAL)
