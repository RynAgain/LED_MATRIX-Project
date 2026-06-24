"""
Tic-Tac-Toe 4x4 -- AI vs AI with visual effects on 64x64 LED matrix.

Features:
- 4x4 grid with 4-in-a-row to win (more strategic than 3x3)
- Colored board grid lines (dark blue/purple)
- X pieces in red with glow effect
- O pieces in cyan/blue with glow effect
- Smooth piece placement animation (fade-in ~0.3s)
- Win detection with winning line highlighted in gold
- Board drawn with 2px thick lines
- Score counter shown briefly between games
- AI vs AI gameplay with minimax-lite strategy
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw
from src.display._shared import should_stop, interruptible_sleep

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
GRID_SIZE = 4
CELL = SIZE // GRID_SIZE  # 16 pixels per cell
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

# Generate all 4-in-a-row win conditions for a 4x4 board
WIN_CONDITIONS = []

# Rows
for row in range(GRID_SIZE):
    WIN_CONDITIONS.append(tuple(row * GRID_SIZE + col for col in range(GRID_SIZE)))

# Columns
for col in range(GRID_SIZE):
    WIN_CONDITIONS.append(tuple(row * GRID_SIZE + col for row in range(GRID_SIZE)))

# Diagonals
WIN_CONDITIONS.append(tuple(i * GRID_SIZE + i for i in range(GRID_SIZE)))  # top-left to bottom-right
WIN_CONDITIONS.append(tuple(i * GRID_SIZE + (GRID_SIZE - 1 - i) for i in range(GRID_SIZE)))  # top-right to bottom-left


def _cell_center(index):
    """Return (cx, cy) pixel center of given cell index (0-15)."""
    col = index % GRID_SIZE
    row = index // GRID_SIZE
    cx = col * CELL + CELL // 2
    cy = row * CELL + CELL // 2
    return cx, cy


def _draw_grid(draw):
    """Draw 2px thick grid lines in dark blue/purple."""
    for i in range(1, GRID_SIZE):
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
    margin = 4  # Smaller margin for 4x4 cells
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
    r = 4  # Smaller radius for 4x4 cells
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
        start_idx = win_line[0]
        end_idx = win_line[-1]
        sx, sy = _cell_center(start_idx)
        ex, ey = _cell_center(end_idx)
        draw.line([(sx, sy), (ex, ey)], fill=GOLD, width=3)

    # Draw score overlay
    if show_score and scores is not None:
        x_score, o_score, draws = scores
        # Draw small score indicators at top
        # X score on left
        for i in range(min(x_score, 8)):
            draw.rectangle([(2 + i * 4, 1), (4 + i * 4, 3)], fill=SCORE_COLOR_X)
        # O score on right
        for i in range(min(o_score, 8)):
            draw.rectangle([(SIZE - 4 - i * 4, 1), (SIZE - 2 - i * 4, 3)], fill=SCORE_COLOR_O)
        # Draw count in center
        for i in range(min(draws, 4)):
            draw.rectangle([(SIZE // 2 - 1 + i * 4 - (draws * 2), 1),
                            (SIZE // 2 + 1 + i * 4 - (draws * 2), 3)], fill=DRAW_COLOR)

    matrix.SetImage(image)


def _find_winner(board):
    """Return ('X'/'O', winning_condition_tuple) or (None, None)."""
    for cond in WIN_CONDITIONS:
        cells = [board[i] for i in cond]
        if cells[0] != ' ' and all(c == cells[0] for c in cells):
            return cells[0], cond
    return None, None


def _is_draw(board):
    return all(c != ' ' for c in board)


def _count_in_line(board, player, line):
    """Count how many of player's pieces are in a given line, and how many empty."""
    player_count = sum(1 for i in line if board[i] == player)
    empty_count = sum(1 for i in line if board[i] == ' ')
    return player_count, empty_count


def _score_position(board, player):
    """Score the board from player's perspective for AI evaluation."""
    opponent = 'O' if player == 'X' else 'X'
    score = 0

    for line in WIN_CONDITIONS:
        p_count, empty = _count_in_line(board, player, line)
        o_count, _ = _count_in_line(board, opponent, line)

        # Only score lines that aren't blocked by opponent
        if o_count == 0:
            if p_count == 4:
                score += 1000  # Win!
            elif p_count == 3 and empty == 1:
                score += 50   # One away from win
            elif p_count == 2 and empty == 2:
                score += 10   # Building potential

        # Penalize opponent threats
        if p_count == 0:
            if o_count == 3 and empty == 1:
                score -= 80   # Must block!
            elif o_count == 2 and empty == 2:
                score -= 8    # Opponent building

    # Slight preference for center positions
    center_positions = [5, 6, 9, 10]
    for pos in center_positions:
        if board[pos] == player:
            score += 3

    return score


def _ai_move(board, player):
    """Smart AI for 4x4: evaluates positions using a scoring heuristic.

    Strategy priority:
    1. Win immediately if possible
    2. Block opponent's winning move
    3. Choose the highest-scoring position
    """
    opponent = 'O' if player == 'X' else 'X'
    available = [i for i, c in enumerate(board) if c == ' ']
    if not available:
        return -1

    # Try to win immediately
    for move in available:
        test = board[:]
        test[move] = player
        winner, _ = _find_winner(test)
        if winner == player:
            return move

    # Try to block opponent's win
    for move in available:
        test = board[:]
        test[move] = opponent
        winner, _ = _find_winner(test)
        if winner == opponent:
            return move

    # Score all available moves and pick the best
    best_score = -9999
    best_moves = []
    for move in available:
        test = board[:]
        test[move] = player
        score = _score_position(test, player)

        if score > best_score:
            best_score = score
            best_moves = [move]
        elif score == best_score:
            best_moves.append(move)

    # Among best-scoring moves, add some randomness for variety
    if best_moves:
        return random.choice(best_moves)

    return random.choice(available)


def run(matrix, duration=60):
    """Run the 4x4 Tic-Tac-Toe display feature for the specified duration.

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
            board = [' '] * (GRID_SIZE * GRID_SIZE)
            current_player = 'X'
            game_over = False
            win_line = None

            # Show empty board briefly
            _draw_board(matrix, board, scores=scores, show_score=True)
            if not interruptible_sleep(0.5):
                break

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
                    interruptible_sleep(2.0)
                    game_over = True
                elif _is_draw(board):
                    logger.info("Game ended in a draw")
                    scores[2] += 1
                    _draw_board(matrix, board, scores=scores, show_score=True)
                    interruptible_sleep(2.0)
                    game_over = True
                else:
                    # Pause before next move (shorter for 4x4 since more moves)
                    if not interruptible_sleep(0.25):
                        break
                    current_player = 'O' if current_player == 'X' else 'X'

            # Show score briefly between games
            _draw_board(matrix, board, win_line=win_line, scores=scores, show_score=True)
            interruptible_sleep(1.0)

    except Exception as e:
        logger.error("Error in tic_tac_toe: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
