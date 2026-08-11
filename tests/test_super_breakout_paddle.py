"""
Tests for Super Breakout paddle continuity across Fez rotations.

The cube rotation slides the whole world one face-width sideways. The paddle
must ride that slide (eased, frame by frame) instead of freezing at its old
screen x, so a player chasing a ball across a rotation finds the paddle where
the ball re-enters.
"""

import pytest
from src.display.super_breakout import (
    SuperBreakoutGame, SIZE, PADDLE_WIDTH, ROTATION_FRAMES,
)


def _rotate_to_completion(game):
    """Step the game until the rotation animation finishes."""
    steps = 0
    while game.rotating and steps < ROTATION_FRAMES * 3:
        game.step(ai_mode=False)
        steps += 1
    assert not game.rotating, "rotation never completed"


class TestPaddleRidesRotation:
    def test_rotate_right_lands_paddle_at_left_edge(self):
        """Rotating right shifts the world left; paddle clamps at x=0,
        exactly where a ball that exited the right edge re-enters."""
        game = SuperBreakoutGame()
        game.paddle_x = 40.0
        game.start_rotation(1)
        _rotate_to_completion(game)
        assert game.paddle_x == 0.0

    def test_rotate_left_lands_paddle_at_right_edge(self):
        game = SuperBreakoutGame()
        game.paddle_x = 10.0
        game.start_rotation(-1)
        _rotate_to_completion(game)
        assert game.paddle_x == float(SIZE - PADDLE_WIDTH)

    def test_paddle_slides_smoothly_not_teleports(self):
        """Paddle position must change gradually over the rotation frames:
        monotonic toward the target, with no single-frame jump bigger than
        half the travel distance."""
        game = SuperBreakoutGame()
        game.paddle_x = 40.0
        game.start_rotation(1)
        positions = [game.paddle_x]
        while game.rotating:
            game.step(ai_mode=False)
            positions.append(game.paddle_x)
        # Monotonically non-increasing toward 0
        for a, b in zip(positions, positions[1:]):
            assert b <= a + 1e-9
        travel = positions[0] - positions[-1]
        max_jump = max(a - b for a, b in zip(positions, positions[1:]))
        assert max_jump < travel * 0.5
        # And it takes more than 2 frames to get there
        moving_frames = sum(1 for a, b in zip(positions, positions[1:]) if a != b)
        assert moving_frames >= 3

    def test_stuck_ball_follows_paddle_through_rotation(self):
        game = SuperBreakoutGame()  # ball starts stuck
        assert game.ball.stuck
        game.paddle_x = 40.0
        game.ball.x = game.paddle_x + PADDLE_WIDTH / 2.0
        game.start_rotation(1)
        _rotate_to_completion(game)
        assert game.ball.x == pytest.approx(game.paddle_x + PADDLE_WIDTH / 2.0)

    def test_rotation_still_changes_face(self):
        """Regression: the paddle work must not break face switching."""
        game = SuperBreakoutGame()
        assert game.current_face == 0
        game.start_rotation(1)
        _rotate_to_completion(game)
        assert game.current_face == 1
        game.start_rotation(-1)
        _rotate_to_completion(game)
        assert game.current_face == 0

    def test_move_paddle_still_clamped_after_rotation(self):
        game = SuperBreakoutGame()
        game.start_rotation(1)
        _rotate_to_completion(game)
        game.move_paddle(-100)
        assert game.paddle_x == 0.0
        game.move_paddle(1000)
        assert game.paddle_x == float(SIZE - PADDLE_WIDTH)
