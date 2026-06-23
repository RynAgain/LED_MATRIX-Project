"""
Barricade (Quoridor-style) -- AI-driven (demo) or controller-playable
(interactive) on a 64x64 LED matrix.

Features:
- 9x9 grid-based race game
- 2 players start on opposite sides, race to reach the other side
- Each turn: move your pawn 1 step OR place a 2-cell wall
- Walls block movement but can never fully seal off a path to goal
- Each player has 10 walls to place
- Pawn jumping: if adjacent to opponent, can jump over them
- AI vs AI (DEMO) or player vs AI (INTERACTIVE)
- Path validation (BFS) ensures walls never completely block

Control scheme (INTERACTIVE mode, ``controller is not None``)
------------------------------------------------------------
- **D-pad** moves the cursor / selects direction to move pawn
- **A** confirm: move pawn to cursor position
- **B** toggle between MOVE mode and WALL PLACEMENT mode
- In wall mode: **D-pad** positions wall, **A** places, **B** cancels
- **LEFT/RIGHT** in wall mode rotates wall (horizontal/vertical)
- **Start + Select** (or hold Start ~1.5s) quits to menu

DEMO mode (``controller is None``) is AI vs AI at readable pace,
auto-restarts on game end, runs until ``duration`` elapses or ``should_stop()``.
"""

import random
import logging
import time
import math
from collections import deque
from PIL import Image, ImageDraw
from src.display._shared import (
    should_stop,
    interruptible_sleep,
    safe_rumble,
    show_banner,
)
from src.display._utils import _draw_digit, _draw_number, _scale_color

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
FPS = 10
FRAME_DUR = 1.0 / FPS

# Board dimensions
GRID_SIZE = 9      # 9x9 grid
CELL_PX = 5        # pixels per cell
GAP_PX = 2         # gap between cells (where walls live)
BOARD_OFFSET_X = 2  # left margin
BOARD_OFFSET_Y = 2  # top margin
# Total board: 9*5 + 8*2 = 61px; offset 2 -> ends at 63

# Wall budget per player
MAX_WALLS = 10

# Colors
BG_COLOR = (0, 0, 0)
GRID_COLOR = (15, 15, 30)        # dim grid lines
CELL_COLOR = (8, 8, 16)          # cell fill
P1_COLOR = (0, 200, 255)         # Cyan (starts bottom, goes to top)
P2_COLOR = (255, 100, 40)        # Orange (starts top, goes to bottom)
# Wall colors per player (dimmer than pawn color to distinguish)
P1_WALL_COLOR = (0, 120, 160)    # Dim cyan wall
P2_WALL_COLOR = (160, 60, 20)    # Dim orange wall
CURSOR_COLOR = (0, 255, 100)     # Bright green cursor
VALID_MOVE_COLOR = (0, 60, 30)   # Dim green for valid moves
GOAL_ROW_P1 = (0, 40, 60)       # Dim cyan tint for P1's goal row
GOAL_ROW_P2 = (40, 20, 0)       # Dim orange tint for P2's goal row
WALL_PREVIEW_OK = (80, 180, 40)  # Green preview (valid placement)
WALL_PREVIEW_BAD = (180, 40, 40) # Red preview (invalid placement)
WALLS_LEFT_COLOR = (120, 120, 120)


# ---------------------------------------------------------------------------
# Game class
# ---------------------------------------------------------------------------

class BarricadeGame:
    """Quoridor-style barricade game on a 9x9 grid."""

    def __init__(self):
        # Player positions: (row, col), 0-indexed
        # P1 starts at bottom center (row 8), P2 at top center (row 0)
        self.pawns = {
            0: (8, 4),  # P1 bottom center
            1: (0, 4),  # P2 top center
        }
        # Walls remaining per player
        self.walls_remaining = {0: MAX_WALLS, 1: MAX_WALLS}
        # Placed walls: dict mapping ((row, col), orientation) -> player_id
        # Wall position is the top-left gap intersection where it starts
        # orientation: 'H' = horizontal (blocks vertical movement), spans 2 cols
        # orientation: 'V' = vertical (blocks horizontal movement), spans 2 rows
        # For H wall at (r, c): blocks passage between row r and r+1, at columns c and c+1
        # For V wall at (r, c): blocks passage between col c and c+1, at rows r and r+1
        self.walls = {}
        self.active_player = 0
        self.winner = -1
        self.tick = 0

    def get_goal_row(self, player):
        """Player's target row."""
        return 0 if player == 0 else 8

    def check_winner(self):
        """Check if either player reached their goal row."""
        if self.pawns[0][0] == 0:
            return 0
        if self.pawns[1][0] == 8:
            return 1
        return -1

    def can_move_between(self, r1, c1, r2, c2):
        """Check if a pawn can move between two adjacent cells.

        Considers walls that block the passage.
        """
        # Must be adjacent (Manhattan distance 1)
        dr = r2 - r1
        dc = c2 - c1
        if abs(dr) + abs(dc) != 1:
            return False
        # Bounds check
        if not (0 <= r2 < GRID_SIZE and 0 <= c2 < GRID_SIZE):
            return False

        # Check if a wall blocks this movement
        if dr == 1:  # Moving down (r1 -> r1+1)
            # Horizontal wall at gap row r1 blocks this
            # Check H walls at (r1, c1) and (r1, c1-1)
            if ((r1, c1), 'H') in self.walls:
                return False
            if c1 > 0 and ((r1, c1 - 1), 'H') in self.walls:
                return False
        elif dr == -1:  # Moving up (r1 -> r1-1)
            # Horizontal wall at gap row r1-1 blocks this
            if ((r1 - 1, c1), 'H') in self.walls:
                return False
            if c1 > 0 and ((r1 - 1, c1 - 1), 'H') in self.walls:
                return False
        elif dc == 1:  # Moving right (c1 -> c1+1)
            # Vertical wall at gap col c1 blocks this
            if ((r1, c1), 'V') in self.walls:
                return False
            if r1 > 0 and ((r1 - 1, c1), 'V') in self.walls:
                return False
        elif dc == -1:  # Moving left (c1 -> c1-1)
            # Vertical wall at gap col c1-1 blocks this
            if ((r1, c1 - 1), 'V') in self.walls:
                return False
            if r1 > 0 and ((r1 - 1, c1 - 1), 'V') in self.walls:
                return False

        return True

    def get_valid_moves(self, player):
        """Get all valid pawn moves for a player.

        Includes: adjacent moves and jumps over opponent.
        """
        r, c = self.pawns[player]
        opp_r, opp_c = self.pawns[1 - player]
        moves = []

        # Check all 4 directions
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE):
                continue
            if not self.can_move_between(r, c, nr, nc):
                continue

            if (nr, nc) == (opp_r, opp_c):
                # Opponent is adjacent — try to jump over
                jr, jc = nr + dr, nc + dc
                if (0 <= jr < GRID_SIZE and 0 <= jc < GRID_SIZE and
                        self.can_move_between(nr, nc, jr, jc)):
                    moves.append((jr, jc))
                else:
                    # Can't jump straight — try diagonal jumps
                    for sdr, sdc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        if (sdr, sdc) == (-dr, -dc):
                            continue  # Don't go back
                        sr, sc = nr + sdr, nc + sdc
                        if (0 <= sr < GRID_SIZE and 0 <= sc < GRID_SIZE and
                                self.can_move_between(nr, nc, sr, sc) and
                                (sr, sc) != (r, c)):
                            moves.append((sr, sc))
            else:
                moves.append((nr, nc))

        return moves

    def move_pawn(self, player, dest):
        """Move a player's pawn to destination."""
        self.pawns[player] = dest

    def is_wall_valid(self, pos, orientation, player=None):
        """Check if a wall placement is valid.

        Conditions:
        1. Within bounds
        2. Doesn't overlap existing walls
        3. Doesn't completely block either player's path to goal
        4. Player has walls remaining (if player specified)
        """
        r, c = pos
        if player is not None and self.walls_remaining[player] <= 0:
            return False

        # Bounds check
        if orientation == 'H':
            if r < 0 or r >= GRID_SIZE - 1 or c < 0 or c >= GRID_SIZE - 2:
                return False
        else:  # 'V'
            if r < 0 or r >= GRID_SIZE - 2 or c < 0 or c >= GRID_SIZE - 1:
                return False

        # Overlap check
        if (pos, orientation) in self.walls:
            return False

        # Check crossing walls
        if orientation == 'H':
            # Can't overlap with H wall shifted by 1
            if ((r, c + 1), 'H') in self.walls:
                return False
            if c > 0 and ((r, c - 1), 'H') in self.walls:
                return False
            # Can't cross a V wall at same intersection
            if ((r, c), 'V') in self.walls:
                # Only conflicts if they share the center point
                # H at (r,c) occupies gap-row r, cols c and c+1
                # V at (r,c) occupies gap-col c, rows r and r+1
                # They cross at the intersection (r, c)
                return False
        else:  # 'V'
            if ((r + 1, c), 'V') in self.walls:
                return False
            if r > 0 and ((r - 1, c), 'V') in self.walls:
                return False
            # Can't cross H wall at same intersection
            if ((r, c), 'H') in self.walls:
                return False

        # Path validation: both players must still be able to reach their goals
        # Temporarily place wall
        self.walls[(pos, orientation)] = -1  # temp marker
        p1_can_reach = self._can_reach_goal(0)
        p2_can_reach = self._can_reach_goal(1)
        del self.walls[(pos, orientation)]

        if not p1_can_reach or not p2_can_reach:
            return False

        return True

    def _can_reach_goal(self, player):
        """BFS check: can player reach their goal row?"""
        goal_row = self.get_goal_row(player)
        start = self.pawns[player]
        visited = {start}
        queue = deque([start])

        while queue:
            r, c = queue.popleft()
            if r == goal_row:
                return True
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if (0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE and
                        (nr, nc) not in visited and
                        self.can_move_between(r, c, nr, nc)):
                    visited.add((nr, nc))
                    queue.append((nr, nc))

        return False

    def place_wall(self, pos, orientation, player):
        """Place a wall and decrement player's wall count."""
        self.walls[(pos, orientation)] = player
        self.walls_remaining[player] -= 1

    def get_all_valid_walls(self, player):
        """Get all valid wall placements for a player."""
        if self.walls_remaining[player] <= 0:
            return []
        valid = []
        for r in range(GRID_SIZE - 1):
            for c in range(GRID_SIZE - 2):
                if self.is_wall_valid((r, c), 'H', player):
                    valid.append(((r, c), 'H'))
        for r in range(GRID_SIZE - 2):
            for c in range(GRID_SIZE - 1):
                if self.is_wall_valid((r, c), 'V', player):
                    valid.append(((r, c), 'V'))
        return valid

    # --- Rendering ---

    def _cell_px(self, row, col):
        """Get the top-left pixel position of a cell."""
        x = BOARD_OFFSET_X + col * (CELL_PX + GAP_PX)
        y = BOARD_OFFSET_Y + row * (CELL_PX + GAP_PX)
        return x, y

    def _cell_center(self, row, col):
        """Get the center pixel of a cell."""
        x, y = self._cell_px(row, col)
        return x + CELL_PX // 2, y + CELL_PX // 2

    def draw(self, tick=0, cursor=None, valid_moves=None,
             wall_preview=None, wall_valid=None, mode='move'):
        """Render the board to a PIL Image.

        Args:
            tick: animation frame counter
            cursor: (row, col) of cursor highlight (interactive mode)
            valid_moves: list of (row, col) to highlight as valid
            wall_preview: ((row, col), orientation) wall being previewed
            wall_valid: bool, whether the preview wall is valid
            mode: 'move' or 'wall' for UI indicator
        """
        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Draw goal row tints
        for c in range(GRID_SIZE):
            # P1 goal (row 0)
            x, y = self._cell_px(0, c)
            draw.rectangle([x, y, x + CELL_PX - 1, y + CELL_PX - 1],
                           fill=GOAL_ROW_P1)
            # P2 goal (row 8)
            x, y = self._cell_px(8, c)
            draw.rectangle([x, y, x + CELL_PX - 1, y + CELL_PX - 1],
                           fill=GOAL_ROW_P2)

        # Draw cells
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                x, y = self._cell_px(r, c)
                if r == 0:
                    fill = GOAL_ROW_P1
                elif r == 8:
                    fill = GOAL_ROW_P2
                else:
                    fill = CELL_COLOR
                draw.rectangle([x, y, x + CELL_PX - 1, y + CELL_PX - 1],
                               fill=fill)

        # Draw valid moves
        if valid_moves:
            for r, c in valid_moves:
                x, y = self._cell_px(r, c)
                pulse = int(30 + 25 * math.sin(tick * 0.2))
                draw.rectangle([x, y, x + CELL_PX - 1, y + CELL_PX - 1],
                               fill=(0, pulse, 0))

        # Draw placed walls (colored by player who placed them)
        for ((wr, wc), orient), owner in self.walls.items():
            color = P1_WALL_COLOR if owner == 0 else P2_WALL_COLOR
            self._draw_wall(draw, wr, wc, orient, color)

        # Draw wall preview
        if wall_preview is not None:
            (wr, wc), orient = wall_preview
            color = WALL_PREVIEW_OK if wall_valid else WALL_PREVIEW_BAD
            # Blink the preview
            if tick % 8 < 5:
                self._draw_wall(draw, wr, wc, orient, color)

        # Draw pawns
        for player, (pr, pc) in self.pawns.items():
            color = P1_COLOR if player == 0 else P2_COLOR
            x, y = self._cell_px(pr, pc)
            # Pawn: filled 3x3 centered in 5x5 cell
            draw.rectangle([x + 1, y + 1, x + 3, y + 3], fill=color)

        # Draw cursor
        if cursor is not None:
            cr, cc = cursor
            x, y = self._cell_px(cr, cc)
            # Blinking border
            if tick % 6 < 4:
                draw.rectangle([x - 1, y - 1, x + CELL_PX, y + CELL_PX],
                               outline=CURSOR_COLOR)

        # Draw walls remaining (bottom area if space, or tiny indicators)
        # P1 wall count (bottom-left)
        p1_walls = self.walls_remaining[0]
        p2_walls = self.walls_remaining[1]
        _draw_digit(image, str(p1_walls % 10), 1, SIZE - 6, P1_COLOR, SIZE)
        _draw_digit(image, str(p2_walls % 10), SIZE - 4, SIZE - 6, P2_COLOR, SIZE)

        # Turn indicator
        indicator_color = P1_COLOR if self.active_player == 0 else P2_COLOR
        brightness = int(150 + 105 * math.sin(tick * 0.15))
        ic = tuple(max(0, min(255, int(c * brightness / 255)))
                   for c in indicator_color)
        draw.rectangle([SIZE // 2 - 1, SIZE - 3, SIZE // 2 + 1, SIZE - 1],
                       fill=ic)

        return image

    def _draw_wall(self, draw, wr, wc, orient, color):
        """Draw a single wall on the board."""
        if orient == 'H':
            # Horizontal wall between rows wr and wr+1, spanning cols wc and wc+1
            # It sits in the horizontal gap below row wr
            x1, _ = self._cell_px(0, wc)
            _, y1_base = self._cell_px(wr, 0)
            y = y1_base + CELL_PX  # start of gap
            x_end, _ = self._cell_px(0, wc + 1)
            x_end += CELL_PX - 1
            draw.rectangle([x1, y, x_end, y + GAP_PX - 1], fill=color)
        else:  # 'V'
            # Vertical wall between cols wc and wc+1, spanning rows wr and wr+1
            x1_base, _ = self._cell_px(0, wc)
            x = x1_base + CELL_PX  # start of gap
            _, y1 = self._cell_px(wr, 0)
            _, y_end = self._cell_px(wr + 1, 0)
            y_end += CELL_PX - 1
            draw.rectangle([x, y1, x + GAP_PX - 1, y_end], fill=color)


# ---------------------------------------------------------------------------
# AI Logic
# ---------------------------------------------------------------------------

def _bfs_distance(game, start, goal_row):
    """BFS shortest distance from start to any cell in goal_row."""
    visited = {start}
    queue = deque([(start, 0)])
    while queue:
        (r, c), dist = queue.popleft()
        if r == goal_row:
            return dist
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if (0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE and
                    (nr, nc) not in visited and
                    game.can_move_between(r, c, nr, nc)):
                visited.add((nr, nc))
                queue.append(((nr, nc), dist + 1))
    return 999  # unreachable (shouldn't happen with valid boards)


def _ai_decide(game):
    """AI decides: move pawn or place wall.

    Strategy:
    - If we're closer to goal than opponent, move forward
    - If opponent is closer, consider placing a wall to slow them
    - Always move if no walls remaining
    - Move toward shortest path to goal

    Returns: ('move', (row, col)) or ('wall', ((row, col), orient))
    """
    player = game.active_player
    opp = 1 - player
    my_pos = game.pawns[player]
    opp_pos = game.pawns[opp]
    my_goal = game.get_goal_row(player)
    opp_goal = game.get_goal_row(opp)

    my_dist = _bfs_distance(game, my_pos, my_goal)
    opp_dist = _bfs_distance(game, opp_pos, opp_goal)

    # Consider wall placement if opponent is close and we have walls
    place_wall = False
    if (game.walls_remaining[player] > 0 and
            opp_dist <= my_dist and
            opp_dist < 6 and
            random.random() < 0.6):
        place_wall = True

    # Also consider wall if opponent is much closer
    if (game.walls_remaining[player] > 0 and
            opp_dist < my_dist - 2 and
            random.random() < 0.8):
        place_wall = True

    if place_wall:
        wall_choice = _ai_choose_wall(game, player)
        if wall_choice is not None:
            return ('wall', wall_choice)

    # Move pawn toward goal via shortest path
    move_choice = _ai_choose_move(game, player)
    if move_choice is not None:
        return ('move', move_choice)

    # Fallback: if somehow no moves (shouldn't happen), skip
    return None


def _ai_choose_move(game, player):
    """AI chooses the best pawn move (toward goal)."""
    moves = game.get_valid_moves(player)
    if not moves:
        return None

    goal_row = game.get_goal_row(player)
    best_dist = 999
    best_moves = []

    for dest in moves:
        dist = _bfs_distance(game, dest, goal_row)
        if dist < best_dist:
            best_dist = dist
            best_moves = [dest]
        elif dist == best_dist:
            best_moves.append(dest)

    return random.choice(best_moves) if best_moves else moves[0]


def _ai_choose_wall(game, player):
    """AI chooses a wall that maximally increases opponent's path length.

    Samples a subset of valid walls and picks the one that increases
    the opponent's distance the most.
    """
    opp = 1 - player
    opp_pos = game.pawns[opp]
    opp_goal = game.get_goal_row(opp)
    current_opp_dist = _bfs_distance(game, opp_pos, opp_goal)

    # Sample walls (checking all is expensive)
    candidates = []

    # Generate walls near the opponent's position
    opp_r, opp_c = opp_pos
    for dr in range(-3, 4):
        for dc in range(-3, 4):
            wr, wc = opp_r + dr, opp_c + dc
            for orient in ['H', 'V']:
                if game.is_wall_valid((wr, wc), orient, player):
                    candidates.append(((wr, wc), orient))

    if not candidates:
        return None

    # Score each candidate by how much it increases opponent's distance
    best_score = 0
    best_wall = None

    # Limit evaluation to avoid lag
    sample = random.sample(candidates, min(20, len(candidates)))

    for (wr, wc), orient in sample:
        game.walls[((wr, wc), orient)] = player  # temp
        new_dist = _bfs_distance(game, opp_pos, opp_goal)
        del game.walls[((wr, wc), orient)]

        score = new_dist - current_opp_dist
        # Small bonus for not hurting our own path
        if score > best_score:
            best_score = score
            best_wall = ((wr, wc), orient)

    # Only place wall if it actually helps
    if best_score >= 1:
        return best_wall
    return None


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------

def _run_demo(matrix, duration, start_time):
    """AI vs AI demo loop."""
    game = BarricadeGame()
    tick = 0

    while time.time() - start_time < duration:
        if should_stop():
            return

        # AI decides
        decision = _ai_decide(game)

        if decision is None:
            # No valid action (shouldn't happen); switch turn
            game.active_player = 1 - game.active_player
            continue

        action_type, action_data = decision

        if action_type == 'move':
            # Animate pawn move
            dest = action_data
            old_pos = game.pawns[game.active_player]

            # Flash the move
            for i in range(4):
                if should_stop():
                    return
                valid = game.get_valid_moves(game.active_player)
                image = game.draw(tick, cursor=dest, valid_moves=valid)
                matrix.SetImage(image)
                tick += 1
                time.sleep(0.08)

            game.move_pawn(game.active_player, dest)
            image = game.draw(tick)
            matrix.SetImage(image)

        elif action_type == 'wall':
            pos, orient = action_data

            # Show wall preview briefly
            for i in range(5):
                if should_stop():
                    return
                image = game.draw(tick, wall_preview=(pos, orient),
                                  wall_valid=True)
                matrix.SetImage(image)
                tick += 1
                time.sleep(0.08)

            game.place_wall(pos, orient, game.active_player)
            image = game.draw(tick)
            matrix.SetImage(image)

        # Check winner
        winner = game.check_winner()
        if winner >= 0:
            color = P1_COLOR if winner == 0 else P2_COLOR
            label = "P1 WINS" if winner == 0 else "P2 WINS"
            show_banner(matrix, [label], color=color, hold=2.0)
            # Reset
            game = BarricadeGame()
            tick = 0
            continue

        # Next turn
        game.active_player = 1 - game.active_player
        tick += 1

        if not interruptible_sleep(0.4):
            return

        # Render idle frame
        image = game.draw(tick)
        matrix.SetImage(image)


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def _run_interactive(matrix, controller, start_time):
    """Player (P1) vs AI (P2) interactive game."""
    from src.input.controller import wants_quit, Button, EventType

    _INTERACTIVE_MAX_SECONDS = 600  # 10 min cap

    game = BarricadeGame()
    game.active_player = 0
    tick = 0

    show_banner(matrix, ["BARRICADE", "A:MOVE B:WALL"], color=P1_COLOR, hold=1.5)

    while time.time() - start_time < _INTERACTIVE_MAX_SECONDS:
        if should_stop():
            return

        if game.active_player == 1:
            # AI turn
            if not interruptible_sleep(0.3):
                return
            decision = _ai_decide(game)
            if decision:
                action_type, action_data = decision
                if action_type == 'move':
                    game.move_pawn(1, action_data)
                elif action_type == 'wall':
                    pos, orient = action_data
                    # Brief preview
                    for _ in range(4):
                        if should_stop():
                            return
                        image = game.draw(tick, wall_preview=(pos, orient),
                                          wall_valid=True)
                        matrix.SetImage(image)
                        tick += 1
                        time.sleep(0.08)
                    game.place_wall(pos, orient, 1)

            image = game.draw(tick)
            matrix.SetImage(image)

            winner = game.check_winner()
            if winner >= 0:
                safe_rumble(controller, 0.6, 300)
                show_banner(matrix, ["YOU LOSE"], color=(255, 80, 80), hold=2.0)
                return

            game.active_player = 0
            if not interruptible_sleep(0.2):
                return
            continue

        # --- PLAYER TURN ---
        mode = 'move'  # 'move' or 'wall'
        cursor_r, cursor_c = game.pawns[0]
        wall_orient = 'H'
        wall_r, wall_c = cursor_r, cursor_c
        valid_moves = game.get_valid_moves(0)

        turn_done = False
        while not turn_done:
            if should_stop():
                return
            controller.poll_events()
            if wants_quit(controller):
                return

            events = controller.poll_events()
            for ev in events:
                if ev.event_type not in (EventType.PRESSED, EventType.REPEAT):
                    continue

                if ev.button == Button.B:
                    # Toggle mode
                    if mode == 'move':
                        if game.walls_remaining[0] > 0:
                            mode = 'wall'
                            wall_r = max(0, cursor_r - 1)
                            wall_c = max(0, cursor_c - 1)
                    else:
                        mode = 'move'

                elif mode == 'move':
                    if ev.button == Button.UP:
                        cursor_r = max(0, cursor_r - 1)
                    elif ev.button == Button.DOWN:
                        cursor_r = min(GRID_SIZE - 1, cursor_r + 1)
                    elif ev.button == Button.LEFT:
                        cursor_c = max(0, cursor_c - 1)
                    elif ev.button == Button.RIGHT:
                        cursor_c = min(GRID_SIZE - 1, cursor_c + 1)
                    elif ev.button == Button.A:
                        if (cursor_r, cursor_c) in valid_moves:
                            game.move_pawn(0, (cursor_r, cursor_c))
                            turn_done = True

                elif mode == 'wall':
                    if ev.button == Button.UP:
                        wall_r = max(0, wall_r - 1)
                    elif ev.button == Button.DOWN:
                        max_r = GRID_SIZE - 2 if wall_orient == 'H' else GRID_SIZE - 3
                        wall_r = min(max_r, wall_r + 1)
                    elif ev.button == Button.LEFT:
                        wall_c = max(0, wall_c - 1)
                    elif ev.button == Button.RIGHT:
                        max_c = GRID_SIZE - 3 if wall_orient == 'H' else GRID_SIZE - 2
                        wall_c = min(max_c, wall_c + 1)
                    elif ev.button == Button.A:
                        if game.is_wall_valid((wall_r, wall_c), wall_orient, 0):
                            game.place_wall((wall_r, wall_c), wall_orient, 0)
                            turn_done = True
                    elif ev.button == Button.SELECT:
                        # Rotate wall orientation
                        wall_orient = 'V' if wall_orient == 'H' else 'H'
                        # Clamp position
                        if wall_orient == 'H':
                            wall_c = min(wall_c, GRID_SIZE - 3)
                            wall_r = min(wall_r, GRID_SIZE - 2)
                        else:
                            wall_r = min(wall_r, GRID_SIZE - 3)
                            wall_c = min(wall_c, GRID_SIZE - 2)

            # Render
            tick += 1
            if mode == 'move':
                image = game.draw(tick, cursor=(cursor_r, cursor_c),
                                  valid_moves=valid_moves)
            else:
                is_valid = game.is_wall_valid((wall_r, wall_c), wall_orient, 0)
                image = game.draw(tick,
                                  wall_preview=((wall_r, wall_c), wall_orient),
                                  wall_valid=is_valid, mode='wall')
            matrix.SetImage(image)
            time.sleep(FRAME_DUR)

        # End of player turn
        image = game.draw(tick)
        matrix.SetImage(image)

        winner = game.check_winner()
        if winner >= 0:
            safe_rumble(controller, 1.0, 400)
            show_banner(matrix, ["YOU WIN!"], color=(80, 255, 120), hold=2.0)
            return

        game.active_player = 1
        tick += 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60, controller=None):
    """Run the Barricade (Quoridor) feature.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds (DEMO mode only; INTERACTIVE play
            runs until the game is decided or the quit gesture).
        controller: optional :class:`src.input.Controller`. ``None`` -> DEMO
            (AI vs AI). Not-None -> INTERACTIVE (player vs AI).
    """
    start_time = time.time()
    try:
        if controller is None:
            _run_demo(matrix, duration, start_time)
        else:
            _run_interactive(matrix, controller, start_time)
    except Exception as e:
        logger.error("Error in barricade: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
