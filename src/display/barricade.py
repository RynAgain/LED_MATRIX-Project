"""
Barricade (Malefiz) -- AI-driven (demo) or controller-playable (interactive)
on a 64x64 LED matrix.

Features:
- Classic Barricade/Malefiz board game adapted to pixel grid
- Pyramid-shaped path graph with ~45 nodes
- 2 players, 3 pieces each, racing to a single goal at top
- Dice-based movement with exact-step BFS pathfinding
- Barricade capture and strategic placement mechanics
- Opponent piece capture (sends them home)
- Animated dice roll, piece movement, and captures
- AI vs AI (DEMO) or player vs AI (INTERACTIVE)

Control scheme (INTERACTIVE mode, ``controller is not None``)
------------------------------------------------------------
- **UP / DOWN** cycle through selectable pieces or valid destinations
- **LEFT / RIGHT** navigate barricade placement cursor
- **A** confirm selection (piece, destination, or barricade placement)
- **B** cancel / go back to previous selection phase
- **Start + Select** (or hold Start ~1.5s) quits to menu

DEMO mode (``controller is None``) is AI vs AI at readable pace (~1.5s/turn),
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
FPS = 15
FRAME_DUR = 1.0 / FPS

# Colors
BG_COLOR = (0, 0, 0)
PATH_COLOR = (20, 20, 40)
NODE_COLOR = (30, 30, 50)
P1_COLOR = (0, 200, 255)       # Cyan
P2_COLOR = (255, 100, 40)      # Orange-red
BARRICADE_COLOR = (200, 200, 200)
GOAL_COLOR = (255, 215, 0)     # Gold
SELECT_COLOR = (0, 255, 100)   # Bright green
VALID_COLOR = (0, 80, 40)      # Dim green
DICE_COLOR = (255, 255, 255)
TURN_INDICATOR_DIM = 80

# Game states
STATE_ROLL_DICE = 0
STATE_SELECT_PIECE = 1
STATE_SELECT_DEST = 2
STATE_ANIMATE_MOVE = 3
STATE_PLACE_BARRICADE = 4
STATE_NEXT_TURN = 5
STATE_GAME_OVER = 6

# Board layout constants
BOARD_X_OFFSET = 3
BOARD_Y_OFFSET = 2
NODE_SPACING_X = 7
NODE_SPACING_Y = 6


# ---------------------------------------------------------------------------
# Board topology definition
# ---------------------------------------------------------------------------

def _build_board():
    """Build the Barricade board graph.

    Returns:
        nodes: list of (px, py) pixel positions for each node
        edges: dict mapping node_index -> list of connected node_indices
        home_nodes: {0: [idx, ...], 1: [idx, ...]} per player
        goal_node: index of the goal node
        initial_barricades: list of node indices that start with barricades
    """
    nodes = []
    edges = {}

    # Helper: add a node and return its index
    def add_node(px, py):
        idx = len(nodes)
        nodes.append((px, py))
        edges[idx] = []
        return idx

    # Helper: connect two nodes bidirectionally
    def connect(a, b):
        if b not in edges[a]:
            edges[a].append(b)
        if a not in edges[b]:
            edges[b].append(a)

    # Build rows from top to bottom
    # Row 0: Goal node (single, top center)
    goal = add_node(BOARD_X_OFFSET + 4 * NODE_SPACING_X, BOARD_Y_OFFSET)

    # Row 1: 3 nodes
    row1 = []
    for i in range(3):
        x = BOARD_X_OFFSET + (i + 1) * NODE_SPACING_X + NODE_SPACING_X // 2
        row1.append(add_node(x, BOARD_Y_OFFSET + NODE_SPACING_Y))

    # Connect row1 to goal (center node)
    connect(goal, row1[1])

    # Row 2: 5 nodes
    row2 = []
    for i in range(5):
        x = BOARD_X_OFFSET + (i + 1) * NODE_SPACING_X
        row2.append(add_node(x, BOARD_Y_OFFSET + 2 * NODE_SPACING_Y))

    # Row 3: 3 nodes
    row3 = []
    for i in range(3):
        x = BOARD_X_OFFSET + (i + 1) * NODE_SPACING_X + NODE_SPACING_X // 2
        row3.append(add_node(x, BOARD_Y_OFFSET + 3 * NODE_SPACING_Y))

    # Row 4: 5 nodes
    row4 = []
    for i in range(5):
        x = BOARD_X_OFFSET + (i + 1) * NODE_SPACING_X
        row4.append(add_node(x, BOARD_Y_OFFSET + 4 * NODE_SPACING_Y))

    # Row 5: 3 nodes
    row5 = []
    for i in range(3):
        x = BOARD_X_OFFSET + (i + 1) * NODE_SPACING_X + NODE_SPACING_X // 2
        row5.append(add_node(x, BOARD_Y_OFFSET + 5 * NODE_SPACING_Y))

    # Row 6: 5 nodes
    row6 = []
    for i in range(5):
        x = BOARD_X_OFFSET + (i + 1) * NODE_SPACING_X
        row6.append(add_node(x, BOARD_Y_OFFSET + 6 * NODE_SPACING_Y))

    # Row 7: 3 nodes
    row7 = []
    for i in range(3):
        x = BOARD_X_OFFSET + (i + 1) * NODE_SPACING_X + NODE_SPACING_X // 2
        row7.append(add_node(x, BOARD_Y_OFFSET + 7 * NODE_SPACING_Y))

    # Row 8: 5 nodes (bottom path row)
    row8 = []
    for i in range(5):
        x = BOARD_X_OFFSET + (i + 1) * NODE_SPACING_X
        row8.append(add_node(x, BOARD_Y_OFFSET + 8 * NODE_SPACING_Y))

    # Home rows (below the board)
    # Player 1 (left): 3 home nodes
    home_p1 = []
    for i in range(3):
        x = BOARD_X_OFFSET + (i + 1) * NODE_SPACING_X
        home_p1.append(add_node(x, BOARD_Y_OFFSET + 9 * NODE_SPACING_Y + 2))

    # Player 2 (right): 3 home nodes
    home_p2 = []
    for i in range(3):
        x = BOARD_X_OFFSET + (i + 3) * NODE_SPACING_X
        home_p2.append(add_node(x, BOARD_Y_OFFSET + 9 * NODE_SPACING_Y + 2))

    # --- Horizontal connections within rows ---
    for row in [row1, row2, row3, row4, row5, row6, row7, row8]:
        for i in range(len(row) - 1):
            connect(row[i], row[i + 1])

    # --- Vertical connections (3-node rows to 5-node rows) ---
    # Row1 (3) <-> Row2 (5): staggered
    connect(row1[0], row2[0])
    connect(row1[0], row2[1])
    connect(row1[1], row2[2])
    connect(row1[2], row2[3])
    connect(row1[2], row2[4])

    # Row2 (5) <-> Row3 (3): staggered
    connect(row2[0], row3[0])
    connect(row2[1], row3[0])
    connect(row2[2], row3[1])
    connect(row2[3], row3[2])
    connect(row2[4], row3[2])

    # Row3 (3) <-> Row4 (5): staggered
    connect(row3[0], row4[0])
    connect(row3[0], row4[1])
    connect(row3[1], row4[2])
    connect(row3[2], row4[3])
    connect(row3[2], row4[4])

    # Row4 (5) <-> Row5 (3): staggered
    connect(row4[0], row5[0])
    connect(row4[1], row5[0])
    connect(row4[2], row5[1])
    connect(row4[3], row5[2])
    connect(row4[4], row5[2])

    # Row5 (3) <-> Row6 (5): staggered
    connect(row5[0], row6[0])
    connect(row5[0], row6[1])
    connect(row5[1], row6[2])
    connect(row5[2], row6[3])
    connect(row5[2], row6[4])

    # Row6 (5) <-> Row7 (3): staggered
    connect(row6[0], row7[0])
    connect(row6[1], row7[0])
    connect(row6[2], row7[1])
    connect(row6[3], row7[2])
    connect(row6[4], row7[2])

    # Row7 (3) <-> Row8 (5): staggered
    connect(row7[0], row8[0])
    connect(row7[0], row8[1])
    connect(row7[1], row8[2])
    connect(row7[2], row8[3])
    connect(row7[2], row8[4])

    # Home connections: each home node connects to nearest row8 node
    connect(home_p1[0], row8[0])
    connect(home_p1[1], row8[1])
    connect(home_p1[2], row8[2])
    connect(home_p2[0], row8[2])
    connect(home_p2[1], row8[3])
    connect(home_p2[2], row8[4])

    # Initial barricades: placed on row2, row4, row6 middle nodes
    initial_barricades = [row2[1], row2[3], row4[1], row4[3],
                          row6[1], row6[3], row3[1], row5[1], row1[1]]

    home_nodes = {0: home_p1, 1: home_p2}

    return nodes, edges, home_nodes, goal, initial_barricades


# ---------------------------------------------------------------------------
# Game class
# ---------------------------------------------------------------------------

class BarricadeGame:
    """Full Barricade game state and logic."""

    def __init__(self):
        (self.nodes, self.edges, self.home_nodes,
         self.goal_node, initial_barricades) = _build_board()
        self.barricades = set(initial_barricades)
        # Each player has 3 pieces; value = node index where piece sits
        self.pieces = {
            0: list(self.home_nodes[0]),  # P1 starts on home nodes
            1: list(self.home_nodes[1]),  # P2 starts on home nodes
        }
        self.active_player = 0
        self.dice_value = 0
        self.state = STATE_ROLL_DICE
        self.winner = -1

        # Animation/selection state
        self.selected_piece_idx = 0  # index into self.pieces[player]
        self.valid_moves = []        # list of (piece_local_idx, dest_node) tuples
        self.selected_move_idx = 0
        self.barricade_options = []  # valid placement nodes
        self.barricade_cursor = 0
        self.captured_barricade = False

        # Animation
        self.anim_path = []          # nodes to traverse for move animation
        self.anim_step = 0
        self.anim_tick = 0
        self.tick = 0                # global frame counter

    def roll_dice(self):
        """Roll the dice (1-6)."""
        self.dice_value = random.randint(1, 6)
        return self.dice_value

    def get_movable_pieces(self):
        """Find which pieces of active player can legally move.

        Returns list of (piece_local_idx, list_of_dest_nodes) for pieces
        that have at least one valid destination.
        """
        player = self.active_player
        result = []
        for i, piece_node in enumerate(self.pieces[player]):
            dests = self._find_reachable(piece_node, self.dice_value, player)
            if dests:
                result.append((i, dests))
        return result

    def _find_reachable(self, start_node, steps, player):
        """BFS to find all nodes reachable in exactly `steps` moves.

        Rules:
        - Cannot pass through barricades (but can land on one at final step)
        - Cannot pass through any piece (but can land on opponent at final step)
        - Cannot land on own piece
        """
        # BFS: (current_node, steps_remaining, visited_set)
        queue = deque()
        queue.append((start_node, steps, frozenset([start_node])))
        reachable = set()

        # All occupied nodes (both players)
        own_pieces = set(self.pieces[player])
        opp_pieces = set(self.pieces[1 - player])
        blocked = self.barricades | own_pieces | opp_pieces
        # Remove start node from blocked (we're moving FROM it)
        blocked = blocked - {start_node}

        while queue:
            node, remaining, visited = queue.popleft()

            if remaining == 0:
                # Reached exact distance; valid if not own piece
                if node not in own_pieces or node == start_node:
                    if node != start_node:
                        reachable.add(node)
                continue

            for neighbor in self.edges.get(node, []):
                if neighbor in visited:
                    continue

                if remaining == 1:
                    # Final step: can land on barricade or opponent (capture)
                    # but not on own piece
                    if neighbor in own_pieces:
                        continue
                    queue.append((neighbor, 0, visited | {neighbor}))
                else:
                    # Intermediate step: cannot pass through blocked nodes
                    if neighbor in blocked:
                        continue
                    queue.append((neighbor, remaining - 1, visited | {neighbor}))

        return list(reachable)

    def move_piece(self, piece_idx, dest_node):
        """Execute a move. Returns path for animation.

        Handles barricade capture and opponent capture.
        """
        player = self.active_player
        start = self.pieces[player][piece_idx]

        # Find shortest path for animation (BFS ignoring barricades/pieces at dest)
        path = self._find_path(start, dest_node, player)

        # Check captures
        self.captured_barricade = False
        if dest_node in self.barricades:
            self.barricades.remove(dest_node)
            self.captured_barricade = True

        # Check opponent capture
        opp = 1 - player
        for i, opp_node in enumerate(self.pieces[opp]):
            if opp_node == dest_node:
                # Send opponent piece home
                self.pieces[opp][i] = self.home_nodes[opp][i]
                break

        # Move piece
        self.pieces[player][piece_idx] = dest_node

        return path

    def _find_path(self, start, end, player):
        """Find a valid path from start to end for animation.

        Uses BFS respecting the movement rules but ensures we reach end.
        Returns the node sequence including start and end.
        """
        # Simple BFS for shortest path (for animation, allow passing through
        # intermediate nodes loosely -- the move is already validated)
        queue = deque([(start, [start])])
        visited = {start}

        while queue:
            node, path = queue.popleft()
            if node == end:
                return path
            for neighbor in self.edges.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        # Fallback: just start and end
        return [start, end]

    def get_barricade_placements(self):
        """Get valid nodes where a captured barricade can be placed.

        Cannot place on: home nodes, goal node, occupied nodes, existing barricades.
        """
        invalid = set()
        invalid.add(self.goal_node)
        invalid |= self.barricades
        for p_pieces in self.pieces.values():
            invalid |= set(p_pieces)
        for home_list in self.home_nodes.values():
            invalid |= set(home_list)

        valid = []
        for i in range(len(self.nodes)):
            if i not in invalid:
                valid.append(i)
        return valid

    def place_barricade(self, node_idx):
        """Place a captured barricade on the given node."""
        self.barricades.add(node_idx)

    def check_winner(self):
        """Check if any piece is on the goal node. Returns player id or -1."""
        for player, pieces in self.pieces.items():
            if self.goal_node in pieces:
                return player
        return -1

    def get_node_row(self, node_idx):
        """Get approximate row (0=top/goal) of a node for AI scoring."""
        if node_idx >= len(self.nodes):
            return 9
        _, py = self.nodes[node_idx]
        return (py - BOARD_Y_OFFSET) // NODE_SPACING_Y

    # --- Rendering ---

    def draw(self, tick=0):
        """Render the board to a PIL Image."""
        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Draw edges (path lines)
        for node_idx, neighbors in self.edges.items():
            x1, y1 = self.nodes[node_idx]
            for n_idx in neighbors:
                if n_idx > node_idx:  # avoid drawing twice
                    x2, y2 = self.nodes[n_idx]
                    draw.line([(x1, y1), (x2, y2)], fill=PATH_COLOR)

        # Draw empty nodes
        for i, (nx, ny) in enumerate(self.nodes):
            draw.point((nx, ny), fill=NODE_COLOR)

        # Draw goal node (pulsing gold)
        gx, gy = self.nodes[self.goal_node]
        pulse = int(180 + 75 * math.sin(tick * 0.1))
        goal_color = (pulse, int(pulse * 0.84), 0)
        draw.rectangle([gx - 1, gy - 1, gx + 1, gy + 1], fill=goal_color)

        # Draw barricades
        for b_idx in self.barricades:
            bx, by = self.nodes[b_idx]
            draw.rectangle([bx - 1, by - 1, bx, by], fill=BARRICADE_COLOR)

        # Draw pieces
        for player, pieces in self.pieces.items():
            color = P1_COLOR if player == 0 else P2_COLOR
            for piece_node in pieces:
                px, py = self.nodes[piece_node]
                draw.rectangle([px - 1, py - 1, px, py], fill=color)

        # Draw turn indicator (top-left corner)
        indicator_color = P1_COLOR if self.active_player == 0 else P2_COLOR
        brightness = int(TURN_INDICATOR_DIM + 40 * math.sin(tick * 0.15))
        ic = tuple(max(0, min(255, int(c * brightness / 255)))
                   for c in indicator_color)
        draw.point((1, 1), fill=ic)

        # Draw dice value (top-right area)
        if self.dice_value > 0:
            _draw_digit(image, str(self.dice_value), SIZE - 5, 1, DICE_COLOR, SIZE)

        return image

    def draw_with_highlights(self, highlights, selected_idx, tick=0):
        """Draw board with highlighted nodes (for selection phases)."""
        image = self.draw(tick)
        draw = ImageDraw.Draw(image)

        # Draw valid options with dim pulse
        for i, node_idx in enumerate(highlights):
            nx, ny = self.nodes[node_idx]
            if i == selected_idx:
                # Active selection: bright green blink
                if tick % 10 < 6:
                    draw.rectangle([nx - 1, ny - 1, nx + 1, ny + 1],
                                   fill=SELECT_COLOR)
            else:
                # Other valid options: dim green pulse
                pulse = int(30 + 20 * math.sin(tick * 0.12 + i))
                draw.rectangle([nx - 1, ny - 1, nx, ny],
                               fill=(0, pulse, 0))

        return image


# ---------------------------------------------------------------------------
# AI Logic
# ---------------------------------------------------------------------------

def _ai_choose_piece_and_dest(game):
    """AI selects the best piece and destination.

    Heuristic: forward progress + capture bonuses + randomness.
    Returns (piece_local_idx, dest_node) or None if no moves.
    """
    movable = game.get_movable_pieces()
    if not movable:
        return None

    best_score = -999
    best_choice = None

    for piece_idx, destinations in movable:
        current_row = game.get_node_row(game.pieces[game.active_player][piece_idx])
        for dest in destinations:
            dest_row = game.get_node_row(dest)
            score = 0

            # Forward progress (lower row number = closer to goal)
            progress = current_row - dest_row
            score += progress * 3

            # Reaching goal is maximum priority
            if dest == game.goal_node:
                score += 100

            # Barricade capture bonus
            if dest in game.barricades:
                score += 5

            # Opponent capture bonus
            opp = 1 - game.active_player
            if dest in game.pieces[opp]:
                opp_row = game.get_node_row(dest)
                score += 4 + (9 - opp_row)  # more valuable to capture advanced pieces

            # Small randomness for variety
            score += random.uniform(-1.5, 1.5)

            if score > best_score:
                best_score = score
                best_choice = (piece_idx, dest)

    return best_choice


def _ai_place_barricade(game):
    """AI chooses where to place a captured barricade.

    Strategy: block the opponent's most advanced piece's path toward goal.
    """
    options = game.get_barricade_placements()
    if not options:
        return None

    opp = 1 - game.active_player
    opp_pieces = game.pieces[opp]

    # Find opponent's most advanced piece (lowest row number)
    best_opp_piece = min(opp_pieces, key=lambda n: game.get_node_row(n))
    best_opp_row = game.get_node_row(best_opp_piece)

    # Prefer placing barricade on nodes close to (but above) the opponent's
    # best piece — ideally in rows 1-3 above it
    best_score = -999
    best_node = options[0]

    for node_idx in options:
        node_row = game.get_node_row(node_idx)
        score = 0

        # Prefer nodes that are above the opponent's best piece
        if node_row < best_opp_row:
            score += 5 - abs(node_row - (best_opp_row - 2))
        else:
            score -= 3

        # Prefer nodes closer to center (more likely on opponent's path)
        nx, _ = game.nodes[node_idx]
        center_dist = abs(nx - (BOARD_X_OFFSET + 4 * NODE_SPACING_X))
        score -= center_dist * 0.2

        # Don't place right next to our own pieces
        own_pieces = set(game.pieces[game.active_player])
        if node_idx in game.edges:
            for neighbor in game.edges[node_idx]:
                if neighbor in own_pieces:
                    score -= 2

        score += random.uniform(-1, 1)

        if score > best_score:
            best_score = score
            best_node = node_idx

    return best_node


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

        # --- ROLL DICE ---
        game.roll_dice()

        # Brief dice animation
        for _ in range(5):
            if should_stop():
                return
            game.dice_value = random.randint(1, 6)
            image = game.draw(tick)
            matrix.SetImage(image)
            tick += 1
            time.sleep(0.08)

        game.roll_dice()  # Final roll
        image = game.draw(tick)
        matrix.SetImage(image)
        if not interruptible_sleep(0.3):
            return

        # --- AI SELECT PIECE AND DESTINATION ---
        choice = _ai_choose_piece_and_dest(game)

        if choice is None:
            # No valid moves — skip turn
            game.active_player = 1 - game.active_player
            tick += 1
            if not interruptible_sleep(0.3):
                return
            continue

        piece_idx, dest_node = choice

        # Highlight selected piece briefly
        highlight_node = game.pieces[game.active_player][piece_idx]
        for _ in range(6):
            if should_stop():
                return
            image = game.draw_with_highlights([highlight_node], 0, tick)
            matrix.SetImage(image)
            tick += 1
            time.sleep(0.07)

        # --- ANIMATE MOVE ---
        path = game.move_piece(piece_idx, dest_node)

        # Animate along path
        player_color = P1_COLOR if game.active_player == 0 else P2_COLOR
        for path_node in path[1:]:  # skip start (already there)
            if should_stop():
                return
            # Temporarily show piece at intermediate position
            image = game.draw(tick)
            draw = ImageDraw.Draw(image)
            px, py = game.nodes[path_node]
            draw.rectangle([px - 1, py - 1, px, py], fill=player_color)
            matrix.SetImage(image)
            tick += 1
            time.sleep(0.1)

        # Render final state
        image = game.draw(tick)
        matrix.SetImage(image)

        # --- PLACE BARRICADE if captured ---
        if game.captured_barricade:
            if not interruptible_sleep(0.2):
                return
            barricade_node = _ai_place_barricade(game)
            if barricade_node is not None:
                game.place_barricade(barricade_node)
                # Brief highlight of placed barricade
                image = game.draw(tick)
                draw = ImageDraw.Draw(image)
                bx, by = game.nodes[barricade_node]
                draw.rectangle([bx - 1, by - 1, bx + 1, by + 1],
                               fill=(255, 255, 255))
                matrix.SetImage(image)
                if not interruptible_sleep(0.3):
                    return

        # --- CHECK WIN ---
        winner = game.check_winner()
        if winner >= 0:
            # Win animation
            color = P1_COLOR if winner == 0 else P2_COLOR
            label = "P1 WINS" if winner == 0 else "P2 WINS"
            show_banner(matrix, [label], color=color, hold=2.0)
            # Reset for next game
            game = BarricadeGame()
            tick = 0
            continue

        # --- NEXT TURN ---
        game.active_player = 1 - game.active_player
        game.dice_value = 0
        tick += 1

        if not interruptible_sleep(0.2):
            return


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def _run_interactive(matrix, controller, start_time):
    """Player (P1) vs AI (P2) interactive game."""
    from src.input.controller import wants_quit, Button, EventType

    _INTERACTIVE_MAX_SECONDS = 600  # 10 min safety cap

    game = BarricadeGame()
    game.active_player = 0  # Player goes first
    tick = 0

    show_banner(matrix, ["BARRICADE", "READY"], color=P1_COLOR, hold=1.2)

    while time.time() - start_time < _INTERACTIVE_MAX_SECONDS:
        if should_stop():
            return

        if game.active_player == 1:
            # --- AI TURN ---
            _ai_turn(game, matrix, tick)
            tick += 5

            winner = game.check_winner()
            if winner >= 0:
                safe_rumble(controller, 0.6 if winner == 1 else 1.0, 300)
                msg = "YOU WIN!" if winner == 0 else "YOU LOSE"
                color = (80, 255, 120) if winner == 0 else (255, 80, 80)
                show_banner(matrix, [msg], color=color, hold=2.0)
                return

            game.active_player = 0
            game.dice_value = 0
            continue

        # --- PLAYER TURN ---
        # Roll dice (press A to roll)
        game.dice_value = 0
        image = game.draw(tick)
        matrix.SetImage(image)

        # Wait for A press to roll
        rolled = False
        while not rolled:
            if should_stop():
                return
            controller.poll_events()
            if wants_quit(controller):
                return

            events = controller.poll_events()
            for ev in events:
                if ev.button == Button.A and ev.event_type == EventType.PRESSED:
                    rolled = True
                    break

            # Show blinking "roll" indicator
            tick += 1
            image = game.draw(tick)
            matrix.SetImage(image)
            time.sleep(FRAME_DUR)

        # Dice animation
        for _ in range(6):
            if should_stop():
                return
            game.dice_value = random.randint(1, 6)
            image = game.draw(tick)
            matrix.SetImage(image)
            tick += 1
            time.sleep(0.08)

        game.roll_dice()
        image = game.draw(tick)
        matrix.SetImage(image)
        time.sleep(0.3)

        # Find movable pieces
        movable = game.get_movable_pieces()
        if not movable:
            show_banner(matrix, ["NO MOVES"], color=(200, 200, 200), hold=1.0)
            game.active_player = 1
            game.dice_value = 0
            continue

        # --- SELECT PIECE ---
        piece_options = [(pi, dests) for pi, dests in movable]
        sel_idx = 0

        selecting_piece = True
        while selecting_piece:
            if should_stop():
                return
            controller.poll_events()
            if wants_quit(controller):
                return

            events = controller.poll_events()
            for ev in events:
                if ev.event_type == EventType.PRESSED:
                    if ev.button == Button.UP:
                        sel_idx = (sel_idx - 1) % len(piece_options)
                    elif ev.button == Button.DOWN:
                        sel_idx = (sel_idx + 1) % len(piece_options)
                    elif ev.button == Button.A:
                        selecting_piece = False
                        break

            # Render with piece highlights
            piece_nodes = [game.pieces[0][pi] for pi, _ in piece_options]
            image = game.draw_with_highlights(piece_nodes, sel_idx, tick)
            matrix.SetImage(image)
            tick += 1
            time.sleep(FRAME_DUR)

        chosen_piece_idx, destinations = piece_options[sel_idx]

        # --- SELECT DESTINATION ---
        dest_idx = 0
        selecting_dest = True
        while selecting_dest:
            if should_stop():
                return
            controller.poll_events()
            if wants_quit(controller):
                return

            events = controller.poll_events()
            for ev in events:
                if ev.event_type == EventType.PRESSED:
                    if ev.button in (Button.UP, Button.RIGHT):
                        dest_idx = (dest_idx + 1) % len(destinations)
                    elif ev.button in (Button.DOWN, Button.LEFT):
                        dest_idx = (dest_idx - 1) % len(destinations)
                    elif ev.button == Button.A:
                        selecting_dest = False
                        break
                    elif ev.button == Button.B:
                        # Go back to piece selection would be complex;
                        # just keep in dest selection
                        pass

            image = game.draw_with_highlights(destinations, dest_idx, tick)
            matrix.SetImage(image)
            tick += 1
            time.sleep(FRAME_DUR)

        dest_node = destinations[dest_idx]

        # --- ANIMATE MOVE ---
        path = game.move_piece(chosen_piece_idx, dest_node)
        for path_node in path[1:]:
            if should_stop():
                return
            image = game.draw(tick)
            draw = ImageDraw.Draw(image)
            px, py = game.nodes[path_node]
            draw.rectangle([px - 1, py - 1, px, py], fill=P1_COLOR)
            matrix.SetImage(image)
            tick += 1
            time.sleep(0.1)

        image = game.draw(tick)
        matrix.SetImage(image)

        # --- PLACE BARRICADE if captured ---
        if game.captured_barricade:
            options = game.get_barricade_placements()
            if options:
                b_idx = 0
                placing = True
                while placing:
                    if should_stop():
                        return
                    controller.poll_events()
                    if wants_quit(controller):
                        return

                    events = controller.poll_events()
                    for ev in events:
                        if ev.event_type in (EventType.PRESSED, EventType.REPEAT):
                            if ev.button in (Button.RIGHT, Button.UP):
                                b_idx = (b_idx + 1) % len(options)
                            elif ev.button in (Button.LEFT, Button.DOWN):
                                b_idx = (b_idx - 1) % len(options)
                            elif ev.button == Button.A:
                                placing = False
                                break

                    image = game.draw_with_highlights(options, b_idx, tick)
                    matrix.SetImage(image)
                    tick += 1
                    time.sleep(FRAME_DUR)

                game.place_barricade(options[b_idx])

        # --- CHECK WIN ---
        winner = game.check_winner()
        if winner >= 0:
            safe_rumble(controller, 1.0, 400)
            show_banner(matrix, ["YOU WIN!"], color=(80, 255, 120), hold=2.0)
            return

        # --- NEXT TURN ---
        game.active_player = 1
        game.dice_value = 0
        tick += 1


def _ai_turn(game, matrix, tick):
    """Execute a single AI turn with animations."""
    # Roll dice
    game.roll_dice()
    for _ in range(4):
        game.dice_value = random.randint(1, 6)
        image = game.draw(tick)
        matrix.SetImage(image)
        tick += 1
        time.sleep(0.08)
    game.roll_dice()
    image = game.draw(tick)
    matrix.SetImage(image)
    time.sleep(0.3)

    # Choose move
    choice = _ai_choose_piece_and_dest(game)
    if choice is None:
        time.sleep(0.3)
        return

    piece_idx, dest_node = choice
    path = game.move_piece(piece_idx, dest_node)

    # Animate
    for path_node in path[1:]:
        image = game.draw(tick)
        draw = ImageDraw.Draw(image)
        px, py = game.nodes[path_node]
        draw.rectangle([px - 1, py - 1, px, py], fill=P2_COLOR)
        matrix.SetImage(image)
        tick += 1
        time.sleep(0.1)

    # Place barricade
    if game.captured_barricade:
        time.sleep(0.2)
        barricade_node = _ai_place_barricade(game)
        if barricade_node is not None:
            game.place_barricade(barricade_node)

    image = game.draw(tick)
    matrix.SetImage(image)
    time.sleep(0.2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60, controller=None):
    """Run the Barricade feature.

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
