"""
Tetris -- AI-driven (demo) or controller-playable (interactive) on a 64x64 LED
matrix.

Features:
- Standard 7 tetrominoes (I, O, T, S, Z, J, L) with correct rotations
- 10-wide playfield centered on the 64px display
- Autonomous AI that evaluates placements by height + hole count (DEMO)
- Gamepad control (INTERACTIVE)
- Line clear animation with flash effect
- Next piece preview
- Score and level display
- Increasing speed with level
- Game over animation; auto-restart in DEMO only

Control scheme (INTERACTIVE mode, ``controller is not None``)
------------------------------------------------------------
- **LEFT / RIGHT** move the active piece (honors REPEAT for smooth held shift).
- **DOWN** soft-drops (honors REPEAT so holding drops faster).
- **UP** or **A** rotate clockwise (PRESSED edge only -- no accidental spinning).
- **B** rotates counter-clockwise (PRESSED edge).
- **SELECT** (tapped alone) hard-drops the piece. (Start+Select is the quit
  gesture, so we use a *tap* of Select without Start; we also accept it only
  when Start is not held to avoid clashing with quit.)
- **Start + Select** held (or hold Start ~1.5s) quits to the menu, via
  :func:`src.input.controller.wants_quit`.
- Gravity still applies on a timer; soft-drop just advances it sooner.
- On **game over** (the stack tops out) the fill animation plays, a brief
  banner is shown, then ``run()`` returns to the menu (no auto-restart).

Rotate convention: **UP/A = clockwise, B = counter-clockwise**. Hard-drop is a
Select tap (chosen so the four directions stay free for movement/rotate).

DEMO mode (``controller is None``) is unchanged: the placement-evaluating AI
plays and rounds auto-restart until ``duration`` elapses. Existing tests calling
``run(matrix, duration)`` behave exactly as before.
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw
from src.display._shared import (
    should_stop,
    interruptible_sleep,
    safe_rumble,
    show_banner,
)
from src.display._utils import _draw_digit, _draw_number

logger = logging.getLogger(__name__)

SIZE = 64

# Playfield dimensions (cells)
FIELD_W = 10
FIELD_H = 20
CELL_SIZE = 3  # 3x3 pixels per cell

# Playfield pixel offset (centered horizontally, bottom-aligned)
FIELD_X = (SIZE - FIELD_W * CELL_SIZE) // 2  # (64 - 30) / 2 = 17
FIELD_Y = SIZE - FIELD_H * CELL_SIZE - 1      # 64 - 60 - 1 = 3

BG_COLOR = (0, 0, 0)
GRID_COLOR = (12, 12, 18)
BORDER_COLOR = (30, 30, 45)
FLASH_COLOR = (255, 255, 255)

# Tetromino definitions: each is a list of rotations, each rotation a list of (row, col) offsets
# Standard Tetris rotation system (SRS-like)
PIECES = {
    'I': {
        'color': (0, 240, 240),
        'rotations': [
            [(0, 0), (0, 1), (0, 2), (0, 3)],
            [(0, 1), (1, 1), (2, 1), (3, 1)],
            [(1, 0), (1, 1), (1, 2), (1, 3)],
            [(0, 2), (1, 2), (2, 2), (3, 2)],
        ],
    },
    'O': {
        'color': (240, 240, 0),
        'rotations': [
            [(0, 0), (0, 1), (1, 0), (1, 1)],
            [(0, 0), (0, 1), (1, 0), (1, 1)],
            [(0, 0), (0, 1), (1, 0), (1, 1)],
            [(0, 0), (0, 1), (1, 0), (1, 1)],
        ],
    },
    'T': {
        'color': (160, 0, 240),
        'rotations': [
            [(0, 0), (0, 1), (0, 2), (1, 1)],
            [(0, 0), (1, 0), (2, 0), (1, 1)],
            [(1, 0), (1, 1), (1, 2), (0, 1)],
            [(0, 1), (1, 1), (2, 1), (1, 0)],
        ],
    },
    'S': {
        'color': (0, 240, 0),
        'rotations': [
            [(0, 1), (0, 2), (1, 0), (1, 1)],
            [(0, 0), (1, 0), (1, 1), (2, 1)],
            [(0, 1), (0, 2), (1, 0), (1, 1)],
            [(0, 0), (1, 0), (1, 1), (2, 1)],
        ],
    },
    'Z': {
        'color': (240, 0, 0),
        'rotations': [
            [(0, 0), (0, 1), (1, 1), (1, 2)],
            [(0, 1), (1, 0), (1, 1), (2, 0)],
            [(0, 0), (0, 1), (1, 1), (1, 2)],
            [(0, 1), (1, 0), (1, 1), (2, 0)],
        ],
    },
    'J': {
        'color': (0, 0, 240),
        'rotations': [
            [(0, 0), (1, 0), (1, 1), (1, 2)],
            [(0, 0), (0, 1), (1, 0), (2, 0)],
            [(0, 0), (0, 1), (0, 2), (1, 2)],
            [(0, 1), (1, 1), (2, 0), (2, 1)],
        ],
    },
    'L': {
        'color': (240, 160, 0),
        'rotations': [
            [(0, 2), (1, 0), (1, 1), (1, 2)],
            [(0, 0), (1, 0), (2, 0), (2, 1)],
            [(0, 0), (0, 1), (0, 2), (1, 0)],
            [(0, 0), (0, 1), (1, 1), (2, 1)],
        ],
    },
}

PIECE_NAMES = list(PIECES.keys())


class TetrisGame:
    """Self-playing Tetris game engine."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Initialize / reset the game state."""
        # Field: 2D grid, None = empty, otherwise RGB tuple
        self.field = [[None] * FIELD_W for _ in range(FIELD_H)]
        self.score = 0
        self.lines_cleared = 0
        self.level = 0
        self.game_over = False
        self.clearing_rows = []  # rows currently being cleared (for animation)
        self.clear_flash_frames = 0

        # Piece bag (7-bag randomizer for fair distribution)
        self._bag = []
        self._refill_bag()

        self.current_piece = None
        self.current_rot = 0
        self.current_x = 0
        self.current_y = 0
        self.next_piece = self._bag.pop()
        self._spawn_piece()

        # Timing
        self.drop_interval = 0.5  # seconds between gravity drops
        self.last_drop = time.time()

    def _refill_bag(self):
        """Refill the piece bag with one of each tetromino, shuffled."""
        bag = list(PIECE_NAMES)
        random.shuffle(bag)
        self._bag.extend(bag)

    def _spawn_piece(self):
        """Spawn the next piece at the top of the field."""
        self.current_piece = self.next_piece
        self.current_rot = 0
        self.current_x = FIELD_W // 2 - 1
        self.current_y = 0

        if not self._bag:
            self._refill_bag()
        self.next_piece = self._bag.pop()

        # Check if spawn position is valid
        if not self._is_valid(self.current_piece, self.current_rot,
                              self.current_x, self.current_y):
            self.game_over = True

    def _get_cells(self, piece, rot, px, py):
        """Get the absolute cell positions for a piece at position (px, py)."""
        offsets = PIECES[piece]['rotations'][rot % 4]
        return [(py + r, px + c) for r, c in offsets]

    def _is_valid(self, piece, rot, px, py):
        """Check if a piece placement is valid (in bounds, no overlap)."""
        for row, col in self._get_cells(piece, rot, px, py):
            if col < 0 or col >= FIELD_W:
                return False
            if row < 0 or row >= FIELD_H:
                return False
            if self.field[row][col] is not None:
                return False
        return True

    def _lock_piece(self):
        """Lock the current piece onto the field."""
        color = PIECES[self.current_piece]['color']
        for row, col in self._get_cells(self.current_piece, self.current_rot,
                                         self.current_x, self.current_y):
            if 0 <= row < FIELD_H and 0 <= col < FIELD_W:
                self.field[row][col] = color

        # Check for line clears
        self.clearing_rows = []
        for r in range(FIELD_H):
            if all(self.field[r][c] is not None for c in range(FIELD_W)):
                self.clearing_rows.append(r)

        if self.clearing_rows:
            self.clear_flash_frames = 6  # flash for 6 frames
        else:
            self._spawn_piece()

    def _clear_lines(self):
        """Remove completed lines and shift everything down."""
        for r in sorted(self.clearing_rows, reverse=True):
            del self.field[r]
            self.field.insert(0, [None] * FIELD_W)

        count = len(self.clearing_rows)
        # Standard Tetris scoring
        points = {1: 100, 2: 300, 3: 500, 4: 800}.get(count, count * 200)
        self.score += points * (self.level + 1)
        self.lines_cleared += count
        self.level = self.lines_cleared // 10

        # Speed increases with level
        self.drop_interval = max(0.05, 0.5 - self.level * 0.04)

        self.clearing_rows = []
        self._spawn_piece()

    def _drop_position(self, piece, rot, px, py):
        """Find the lowest valid Y for a piece (hard drop position)."""
        y = py
        while self._is_valid(piece, rot, px, y + 1):
            y += 1
        return y

    def _ai_decide(self):
        """AI: evaluate all possible placements and pick the best one.

        Heuristic: minimize aggregate height + holes, reward line clears.
        """
        piece = self.current_piece
        best_score = -999999
        best_move = (self.current_x, 0)  # (x, rotation)

        for rot in range(4):
            # Determine x range for this rotation
            offsets = PIECES[piece]['rotations'][rot % 4]
            min_c = min(c for _, c in offsets)
            max_c = max(c for _, c in offsets)

            for x in range(-min_c, FIELD_W - max_c):
                if not self._is_valid(piece, rot, x, 0):
                    # If invalid at top, might still work slightly lower
                    if not self._is_valid(piece, rot, x, 1):
                        continue

                drop_y = self._drop_position(piece, rot, x, 0)

                # Simulate placement
                test_field = [row[:] for row in self.field]
                color = PIECES[piece]['color']
                cells = self._get_cells(piece, rot, x, drop_y)
                valid = True
                for r, c in cells:
                    if 0 <= r < FIELD_H and 0 <= c < FIELD_W:
                        test_field[r][c] = color
                    else:
                        valid = False
                        break

                if not valid:
                    continue

                # Count completed lines
                lines = sum(1 for r in range(FIELD_H)
                            if all(test_field[r][c] is not None
                                   for c in range(FIELD_W)))

                # Calculate aggregate height
                agg_height = 0
                for c in range(FIELD_W):
                    for r in range(FIELD_H):
                        if test_field[r][c] is not None:
                            agg_height += FIELD_H - r
                            break

                # Count holes (empty cells below a filled cell)
                holes = 0
                for c in range(FIELD_W):
                    found_block = False
                    for r in range(FIELD_H):
                        if test_field[r][c] is not None:
                            found_block = True
                        elif found_block:
                            holes += 1

                # Bumpiness (height difference between adjacent columns)
                col_heights = []
                for c in range(FIELD_W):
                    h = 0
                    for r in range(FIELD_H):
                        if test_field[r][c] is not None:
                            h = FIELD_H - r
                            break
                    col_heights.append(h)

                bumpiness = sum(abs(col_heights[i] - col_heights[i + 1])
                                for i in range(len(col_heights) - 1))

                # Heuristic score
                score = (lines * 760
                         - agg_height * 5.1
                         - holes * 7.6
                         - bumpiness * 1.8)

                if score > best_score:
                    best_score = score
                    best_move = (x, rot)

        return best_move

    def step(self):
        """Advance the game by one logical step."""
        if self.game_over:
            return

        # Handle line clear animation
        if self.clear_flash_frames > 0:
            self.clear_flash_frames -= 1
            if self.clear_flash_frames == 0:
                self._clear_lines()
            return

        now = time.time()
        if now - self.last_drop >= self.drop_interval:
            self.last_drop = now

            # AI decides target position
            target_x, target_rot = self._ai_decide()

            # Rotate towards target
            if self.current_rot != target_rot:
                new_rot = (self.current_rot + 1) % 4
                if self._is_valid(self.current_piece, new_rot,
                                  self.current_x, self.current_y):
                    self.current_rot = new_rot

            # Move towards target x
            if self.current_x < target_x:
                if self._is_valid(self.current_piece, self.current_rot,
                                  self.current_x + 1, self.current_y):
                    self.current_x += 1
            elif self.current_x > target_x:
                if self._is_valid(self.current_piece, self.current_rot,
                                  self.current_x - 1, self.current_y):
                    self.current_x -= 1

            # Gravity: drop one row
            if self._is_valid(self.current_piece, self.current_rot,
                              self.current_x, self.current_y + 1):
                self.current_y += 1
            else:
                self._lock_piece()

    # ----- INTERACTIVE controls (Phase 5) -------------------------------------
    # These share the same physics primitives (_is_valid / _lock_piece /
    # _drop_position) the demo AI uses; only the *decision* of what to do each
    # frame differs (player input vs. _ai_decide). Each returns True if the
    # action changed state, for optional feedback.

    def move(self, dx):
        """Shift the active piece horizontally by ``dx`` if valid."""
        if self.game_over or self.clear_flash_frames > 0:
            return False
        if self._is_valid(self.current_piece, self.current_rot,
                           self.current_x + dx, self.current_y):
            self.current_x += dx
            return True
        return False

    def rotate(self, cw=True):
        """Rotate the active piece (clockwise by default) if valid."""
        if self.game_over or self.clear_flash_frames > 0:
            return False
        new_rot = (self.current_rot + (1 if cw else -1)) % 4
        if self._is_valid(self.current_piece, new_rot,
                          self.current_x, self.current_y):
            self.current_rot = new_rot
            return True
        # Simple wall-kick: try nudging left/right by one cell.
        for kick in (-1, 1):
            if self._is_valid(self.current_piece, new_rot,
                              self.current_x + kick, self.current_y):
                self.current_x += kick
                self.current_rot = new_rot
                return True
        return False

    def soft_drop(self):
        """Advance the piece down one row (player-initiated). Locks on landing."""
        if self.game_over or self.clear_flash_frames > 0:
            return False
        if self._is_valid(self.current_piece, self.current_rot,
                          self.current_x, self.current_y + 1):
            self.current_y += 1
            self.last_drop = time.time()  # reset gravity so it doesn't double-step
            return True
        self._lock_piece()
        return True

    def hard_drop(self):
        """Drop the piece straight down to its landing row and lock it."""
        if self.game_over or self.clear_flash_frames > 0:
            return False
        self.current_y = self._drop_position(self.current_piece, self.current_rot,
                                              self.current_x, self.current_y)
        self._lock_piece()
        self.last_drop = time.time()
        return True

    def apply_gravity(self):
        """Apply timed gravity (one row per ``drop_interval``) and the line-clear
        animation. This is the player-facing analogue of :meth:`step` minus the
        AI's move/rotate decision -- the player supplies those via the methods
        above. Safe to call every frame.
        """
        if self.game_over:
            return
        if self.clear_flash_frames > 0:
            self.clear_flash_frames -= 1
            if self.clear_flash_frames == 0:
                self._clear_lines()
            return
        now = time.time()
        if now - self.last_drop >= self.drop_interval:
            self.last_drop = now
            if self._is_valid(self.current_piece, self.current_rot,
                              self.current_x, self.current_y + 1):
                self.current_y += 1
            else:
                self._lock_piece()

    def draw(self, image):
        """Render the game state onto a PIL Image."""
        # Draw playfield border
        bx = FIELD_X - 1
        by = FIELD_Y - 1
        bw = FIELD_W * CELL_SIZE + 1
        bh = FIELD_H * CELL_SIZE + 1
        draw = ImageDraw.Draw(image)
        draw.rectangle([bx, by, bx + bw, by + bh], outline=BORDER_COLOR)

        # Draw grid background
        for r in range(FIELD_H):
            for c in range(FIELD_W):
                px = FIELD_X + c * CELL_SIZE
                py = FIELD_Y + r * CELL_SIZE
                cell = self.field[r][c]

                if r in self.clearing_rows and self.clear_flash_frames > 0:
                    # Flash animation for clearing rows
                    if self.clear_flash_frames % 2 == 0:
                        color = FLASH_COLOR
                    else:
                        color = cell if cell else BG_COLOR
                elif cell is not None:
                    color = cell
                else:
                    color = GRID_COLOR

                # Draw 3x3 cell with 1px inner border for depth
                if cell is not None or r in self.clearing_rows:
                    # Filled cell: draw with highlight
                    draw.rectangle([px, py, px + CELL_SIZE - 1,
                                   py + CELL_SIZE - 1], fill=color)
                    # Darken bottom-right edge for 3D look
                    if cell is not None and r not in self.clearing_rows:
                        dark = tuple(max(0, c // 3) for c in color)
                        for i in range(CELL_SIZE):
                            ex, ey = px + CELL_SIZE - 1, py + i
                            if 0 <= ex < SIZE and 0 <= ey < SIZE:
                                image.putpixel((ex, ey), dark)
                            ex, ey = px + i, py + CELL_SIZE - 1
                            if 0 <= ex < SIZE and 0 <= ey < SIZE:
                                image.putpixel((ex, ey), dark)

        # Draw current piece
        if self.current_piece and not self.game_over:
            color = PIECES[self.current_piece]['color']

            # Draw ghost piece (drop shadow)
            ghost_y = self._drop_position(self.current_piece, self.current_rot,
                                          self.current_x, self.current_y)
            if ghost_y != self.current_y:
                ghost_color = tuple(c // 6 for c in color)
                for r, c_pos in self._get_cells(self.current_piece,
                                                 self.current_rot,
                                                 self.current_x, ghost_y):
                    if 0 <= r < FIELD_H and 0 <= c_pos < FIELD_W:
                        px = FIELD_X + c_pos * CELL_SIZE
                        py_g = FIELD_Y + r * CELL_SIZE
                        draw.rectangle([px, py_g, px + CELL_SIZE - 2,
                                       py_g + CELL_SIZE - 2],
                                      fill=ghost_color)

            # Draw active piece
            for r, c_pos in self._get_cells(self.current_piece,
                                             self.current_rot,
                                             self.current_x,
                                             self.current_y):
                if 0 <= r < FIELD_H and 0 <= c_pos < FIELD_W:
                    px = FIELD_X + c_pos * CELL_SIZE
                    py_p = FIELD_Y + r * CELL_SIZE
                    draw.rectangle([px, py_p, px + CELL_SIZE - 1,
                                   py_p + CELL_SIZE - 1], fill=color)

        # Draw next piece preview (top-right area)
        if self.next_piece:
            next_color = PIECES[self.next_piece]['color']
            preview_x = FIELD_X + FIELD_W * CELL_SIZE + 3
            preview_y = FIELD_Y + 2
            # "N" label
            _draw_digit(image, '0', preview_x, preview_y - 1,
                        (40, 40, 60))  # placeholder
            offsets = PIECES[self.next_piece]['rotations'][0]
            for r, c in offsets:
                px = preview_x + c * 2
                py_n = preview_y + 4 + r * 2
                if 0 <= px < SIZE - 1 and 0 <= py_n < SIZE - 1:
                    image.putpixel((px, py_n), next_color)
                    image.putpixel((px + 1, py_n), next_color)
                    image.putpixel((px, py_n + 1), next_color)
                    image.putpixel((px + 1, py_n + 1), next_color)

        # Draw score (left side, vertical)
        score_x = 1
        score_y = FIELD_Y + 2
        _draw_number(image, self.score, score_x, score_y, (150, 150, 180))

        # Draw level
        _draw_number(image, self.level, score_x, score_y + 8, (100, 100, 140))

        # Draw lines cleared count
        _draw_number(image, self.lines_cleared, score_x, score_y + 16,
                     (80, 80, 120))

    def draw_game_over(self, matrix):
        """Animate game over: fill field from bottom with gray."""
        for r in range(FIELD_H - 1, -1, -1):
            if should_stop():
                return
            for c in range(FIELD_W):
                self.field[r][c] = (40, 40, 50)
            image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
            self.draw(image)
            # Draw "GG" text centered
            gg_y = FIELD_Y + FIELD_H * CELL_SIZE // 2 - 3
            gg_x = FIELD_X + FIELD_W * CELL_SIZE // 2 - 5
            # Only show when bottom half is filled
            if r < FIELD_H // 2:
                _draw_number(image, self.score, gg_x - 4, gg_y,
                             (200, 200, 220))
            matrix.SetImage(image)
            time.sleep(0.03)

        interruptible_sleep(1.0)


_FPS = 20
_FRAME_DUR = 1.0 / _FPS
# Generous safety cap (seconds) for INTERACTIVE play; the player normally exits
# via game-over (top-out) or the quit gesture.
_INTERACTIVE_MAX_SECONDS = 3600


def _run_demo(matrix, duration, start_time):
    """Autonomous DEMO loop (unchanged behavior)."""
    while time.time() - start_time < duration:
        if should_stop():
            break

        game = TetrisGame()

        while not game.game_over and time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()

            game.step()

            image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
            game.draw(image)
            matrix.SetImage(image)

            elapsed = time.time() - frame_start
            sleep_time = _FRAME_DUR - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Game over animation
        if game.game_over and time.time() - start_time < duration:
            game.draw_game_over(matrix)

        interruptible_sleep(0.5)


def _run_interactive(matrix, controller, start_time):
    """INTERACTIVE loop: the player drops one game; see module docstring."""
    from src.input.controller import wants_quit, Button, EventType

    show_banner(matrix, ["TETRIS", "READY"], hold=0.8)

    game = TetrisGame()

    while not game.game_over and time.time() - start_time < _INTERACTIVE_MAX_SECONDS:
        if should_stop():
            return
        frame_start = time.time()

        events = controller.poll_events()
        if wants_quit(controller):
            return

        for ev in events:
            b = ev.button
            # Movement + soft-drop honor PRESSED *and* REPEAT (held auto-shift).
            if ev.type in (EventType.PRESSED, EventType.REPEAT):
                if b is Button.LEFT:
                    game.move(-1)
                elif b is Button.RIGHT:
                    game.move(1)
                elif b is Button.DOWN:
                    game.soft_drop()
            # Rotate + hard-drop are edge-only (PRESSED) to avoid spamming.
            if ev.type is EventType.PRESSED:
                if b is Button.UP or b is Button.A:
                    game.rotate(cw=True)
                elif b is Button.B:
                    game.rotate(cw=False)
                elif b is Button.SELECT and not controller.is_pressed(Button.START):
                    # Select tapped alone = hard-drop (Start+Select = quit).
                    game.hard_drop()

        game.apply_gravity()

        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        game.draw(image)
        matrix.SetImage(image)

        elapsed = time.time() - frame_start
        sleep_time = _FRAME_DUR - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Game over: animation + feedback, then return to the menu (no auto-restart).
    if game.game_over:
        game.draw_game_over(matrix)
        safe_rumble(controller, 0.8, 300)
        show_banner(matrix, ["GAME OVER", f"SCORE {game.score}"],
                    color=(255, 80, 80), hold=1.5)


def run(matrix, duration=60, controller=None):
    """Run the Tetris feature.

    Args:
        matrix: RGBMatrix instance (or simulator mock).
        duration: How long to run in seconds (DEMO mode only; INTERACTIVE play
            is bounded by top-out / the quit gesture, with a generous safety cap
            of :data:`_INTERACTIVE_MAX_SECONDS`).
        controller: optional :class:`src.input.Controller`. ``None`` -> DEMO
            (autonomous AI, unchanged). Not-None -> INTERACTIVE (player control).
    """
    start_time = time.time()
    try:
        if controller is None:
            _run_demo(matrix, duration, start_time)
        else:
            _run_interactive(matrix, controller, start_time)
    except Exception as e:
        logger.error("Error in tetris: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
