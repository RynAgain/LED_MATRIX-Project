"""
Tic-Tac-Toe -- AI vs AI with visual effects on 64x64 LED matrix.

Features:
- Colored board grid lines (dark blue/purple)
- X pieces in red with glow effect
- O pieces in cyan/blue with glow effect
- Smooth piece placement animation (fade-in ~0.3s)
- Win detection with winning line highlighted in gold
- Board drawn with 2px thick lines
- Score counter shown briefly between games
- AI vs AI gameplay
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
CELL = SIZE // 3  # ~21 pixels per cell
FPS = 30
FRAME_DUR = 1.0 / FPS

# Colors
GRID_COLOR = (40, 20, 100)          # dark blue/purple grid
X_COLOR = (255, 30, 30)             # red X
X_GLOW = (80, 10, 10)               # dim red glow
O_COLOR = (30, 200, 255)            # cyan O
O_GLOW = (10, 60, 80)               # dim cyan glow
GOLD = (255, 215, 0)                # winning line
BG_COLOR = (0, 0, 0)
SCORE_COLOR_X = (255, 80, 80)
SCORE_COLOR_O = (80, 200, 255)
DRAW_COLOR = (180, 180, 180)

WIN_CONDITIONS = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # cols
    (0, 4, 8), (2, 4, 6),             # diagonals
]


def _cell_center(index):
    """Return (cx, cy) pixel center of given cell index (0-8)."""
    col = index % 3
    row = index // 3
    cx = col * CELL + CELL // 2
    cy = row * CELL + CELL // 2
    return cx, cy


def _draw_grid(draw):
    """Draw 2px thick grid lines in dark blue/purple."""
    for i in range(1, 3):
        # Vertical lines
        x = i * CELL
        draw.line([(x - 1, 0), (x - 1, SIZE - 1)], fill=GRID_COLOR)
        draw.line([(x, 0), (x, SIZE - 1)], fill=GRID_COLOR)
        # Horizontal lines
        y = i * CELL
        draw.line([(0, y - 1), (SIZE - 1, y - 1)], fill=GRID_COLOR)
        draw.line([(0, y), (SIZE - 1, y)], fill=GRID_COLOR)


def _blend(color, alpha):
    """Scale a color tuple by alpha (0.0-1.0)."""
    return tuple(int(c * alpha) for c in color)


def _draw_x(draw, cx, cy, alpha=1.0):
    """Draw an X piece at center (cx, cy) with glow and fade alpha."""
    margin = 5
    # Glow: draw slightly larger, dimmer cross behind
    glow_col = _blend(X_GLOW, alpha)
    main_col = _blend(X_COLOR, alpha)
    for offset in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        ox, oy = offset
        draw.line(
            [(cx - margin + ox, cy - margin + oy), (cx + margin + ox, cy + margin + oy)],
            fill=glow_col, width=1
        )
        draw.line(
            [(cx + margin + ox, cy - margin + oy), (cx - margin + ox, cy + margin + oy)],
            fill=glow_col, width=1
        )
    # Main X
    draw.line([(cx - margin, cy - margin), (cx + margin, cy + margin)], fill=main_col, width=2)
    draw.line([(cx + margin, cy - margin), (cx - margin, cy + margin)], fill=main_col, width=2)


def _draw_o(draw, cx, cy, alpha=1.0):
    """Draw an O piece at center (cx, cy) with glow and fade alpha."""
    r = 6
    glow_col = _blend(O_GLOW, alpha)
    main_col = _blend(O_COLOR, alpha)
    # Glow: slightly larger circle behind
    draw.ellipse(
        [(cx - r - 1, cy - r - 1), (cx + r + 1, cy + r + 1)],
        outline=glow_col, width=1
    )
    # Main O
    draw.ellipse(
        [(cx - r, cy - r), (cx + r, cy + r)],
        outline=main_col, width=2
    )


def _draw_board(matrix, board, animating_cell=-1, anim_alpha=1.0,
                win_line=None, scores=None, show_score=False):
    """Render the full board state to the matrix."""
    image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
    draw = ImageDraw.Draw(image)

    _draw_grid(draw)

    # Draw placed pieces
    for i, cell in enumerate(board):
        if cell == ' ':
            continue
        cx, cy = _cell_center(i)
        alpha = anim_alpha if i == animating_cell else 1.0
        if cell == 'X':
            _draw_x(draw, cx, cy, alpha)
        else:
            _draw_o(draw, cx, cy, alpha)

    # Draw winning line highlight
    if win_line is not None:
        a, b, c = win_line
        ax, ay = _cell_center(a)
        cx_end, cy_end = _cell_center(c)
        draw.line([(ax, ay), (cx_end, cy_end)], fill=GOLD, width=3)

    # Draw score overlay
    if show_score and scores is not None:
        x_score, o_score, draws = scores
        # Draw small score indicators at top
        # X score on left
        for i in range(x_score):
            draw.rectangle([(2 + i * 4, 1), (4 + i * 4, 3)], fill=SCORE_COLOR_X)
        # O score on right
        for i in range(o_score):
            draw.rectangle([(SIZE - 4 - i * 4, 1), (SIZE - 2 - i * 4, 3)], fill=SCORE_COLOR_O)
        # Draw count in center
        for i in range(draws):
            draw.rectangle([(SIZE // 2 - 1 + i * 4 - (draws * 2), 1),
                            (SIZE // 2 + 1 + i * 4 - (draws * 2), 3)], fill=DRAW_COLOR)

    matrix.SetImage(image)


def _find_winner(board):
    """Return ('X'/'O', winning_condition_tuple) or (None, None)."""
    for cond in WIN_CONDITIONS:
        cells = [board[i] for i in cond]
        if cells[0] != ' ' and cells[0] == cells[1] == cells[2]:
            return cells[0], cond
    return None, None


def _is_draw(board):
    return all(c != ' ' for c in board)


def _ai_move(board, player):
    """Simple AI: try to win, then block, then center, then random."""
    opponent = 'O' if player == 'X' else 'X'
    available = [i for i, c in enumerate(board) if c == ' ']
    if not available:
        return -1

    # Try to win
    for move in available:
        test = board[:]
        test[move] = player
        winner, _ = _find_winner(test)
        if winner == player:
            return move

    # Try to block
    for move in available:
        test = board[:]
        test[move] = opponent
        winner, _ = _find_winner(test)
        if winner == opponent:
            return move

    # Take center
    if 4 in available:
        return 4

    # Take a corner
    corners = [i for i in [0, 2, 6, 8] if i in available]
    if corners:
        return random.choice(corners)

    # Random
    return random.choice(available)


def run(matrix, duration=60):
    """Run the Tic-Tac-Toe display feature for the specified duration.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    start_time = time.time()
    scores = [0, 0, 0]  # X wins, O wins, draws

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            board = [' '] * 9
            current_player = 'X'
            game_over = False
            win_line = None

            # Show empty board briefly
            _draw_board(matrix, board, scores=scores, show_score=True)
            time.sleep(0.5)

            while not game_over and time.time() - start_time < duration:
                if should_stop():
                    break
                # AI picks a move
                move = _ai_move(board, current_player)
                if move < 0:
                    break

                board[move] = current_player

                # Animate piece fading in (~0.3s at 30fps = ~9 frames)
                fade_frames = 9
                for f in range(1, fade_frames + 1):
                    alpha = f / fade_frames
                    _draw_board(matrix, board, animating_cell=move,
                                anim_alpha=alpha, scores=scores, show_score=False)
                    time.sleep(FRAME_DUR)

                # Check for winner
                winner, wcond = _find_winner(board)
                if winner:
                    win_line = wcond
                    logger.info("Player %s wins!", winner)
                    if winner == 'X':
                        scores[0] += 1
                    else:
                        scores[1] += 1
                    # Show winning line highlighted for 2 seconds
                    _draw_board(matrix, board, win_line=win_line, scores=scores, show_score=True)
                    time.sleep(2.0)
                    game_over = True
                elif _is_draw(board):
                    logger.info("Game ended in a draw")
                    scores[2] += 1
                    _draw_board(matrix, board, scores=scores, show_score=True)
                    time.sleep(2.0)
                    game_over = True
                else:
                    # Pause before next move
                    time.sleep(0.3)
                    current_player = 'O' if current_player == 'X' else 'X'

            # Show score briefly between games
            _draw_board(matrix, board, win_line=win_line, scores=scores, show_score=True)
            time.sleep(1.0)

    except Exception as e:
        logger.error("Error in tic_tac_toe: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
