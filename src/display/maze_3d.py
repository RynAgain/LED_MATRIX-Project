#!/usr/bin/env python3
"""First-person 3D maze raycaster for 64x64 LED matrix.

Wolfenstein 3D-style rendering of a procedurally generated maze.
An AI agent navigates using left-hand wall-following with smooth
camera interpolation. Regenerates a new maze when solved.
"""

import math
import random
import time
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop, interruptible_sleep

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30
FOV = math.pi / 3          # 60-degree field of view
HALF_FOV = FOV / 2
MAX_DEPTH = 16.0            # Maximum ray cast distance
MOVE_SPEED = 2.5            # Grid cells per second for smooth interpolation
TURN_SPEED = math.pi * 2.0  # Radians per second for smooth turning

# Wall colours indexed by wall type (1-4)
WALL_COLORS = [
    (80, 40, 40),    # Type 0 fallback -- dark red
    (60, 120, 200),  # Type 1 -- blue
    (200, 80, 50),   # Type 2 -- orange-red
    (50, 180, 80),   # Type 3 -- green
    (180, 140, 50),  # Type 4 -- gold
]

# Ceiling / floor colours
CEIL_COLOR = (8, 8, 20)
FLOOR_COLOR = (20, 16, 12)

# Pre-compute floor gradient for performance (near=bright, far=dark)
_FLOOR_GRADIENT = []
for _row in range(HEIGHT):
    if _row <= HEIGHT // 2:
        _FLOOR_GRADIENT.append(CEIL_COLOR)
    else:
        # Distance from horizon: 0 (at horizon) to 1 (at bottom)
        _norm = (_row - HEIGHT // 2) / (HEIGHT // 2)
        # Near floor (bottom of screen) is bright, horizon is dark
        _shade = max(0.2, min(1.0, _norm))
        _FLOOR_GRADIENT.append((
            int(FLOOR_COLOR[0] * _shade),
            int(FLOOR_COLOR[1] * _shade),
            int(FLOOR_COLOR[2] * _shade),
        ))


# ---------------------------------------------------------------------------
# Maze generation  (recursive back-tracker / DFS)
# ---------------------------------------------------------------------------

def _generate_maze(cols, rows):
    """Generate a maze grid. Returns 2D list where 0=path, 1-4=wall type.

    The grid has dimensions (2*rows+1) x (2*cols+1) so that walls occupy
    their own cells between path cells.
    """
    grid_h = 2 * rows + 1
    grid_w = 2 * cols + 1
    # Start with all walls -- assign random wall types 1-4
    grid = [[random.randint(1, 4) for _ in range(grid_w)] for _ in range(grid_h)]

    # Carve paths
    def _cell(r, c):
        return 2 * r + 1, 2 * c + 1

    visited = [[False] * cols for _ in range(rows)]
    stack = [(0, 0)]
    visited[0][0] = True
    r0, c0 = _cell(0, 0)
    grid[r0][c0] = 0

    while stack:
        cr, cc = stack[-1]
        neighbours = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = cr + dr, cc + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc]:
                neighbours.append((nr, nc, dr, dc))

        if not neighbours:
            stack.pop()
            continue

        nr, nc, dr, dc = random.choice(neighbours)
        visited[nr][nc] = True

        # Carve the wall between current and neighbour
        wr, wc = _cell(cr, cc)
        grid[wr + dr][wc + dc] = 0
        # Carve the neighbour cell
        nr2, nc2 = _cell(nr, nc)
        grid[nr2][nc2] = 0

        stack.append((nr, nc))

    return grid, grid_h, grid_w


def _find_start_end(grid, grid_h, grid_w):
    """Find a start position (top-left area) and end (bottom-right area)."""
    start = None
    end = None
    # Start: first open cell from top-left
    for r in range(grid_h):
        for c in range(grid_w):
            if grid[r][c] == 0:
                start = (r, c)
                break
        if start:
            break
    # End: first open cell from bottom-right
    for r in range(grid_h - 1, -1, -1):
        for c in range(grid_w - 1, -1, -1):
            if grid[r][c] == 0:
                end = (r, c)
                break
        if end:
            break
    return start, end


# ---------------------------------------------------------------------------
# Raycasting engine
# ---------------------------------------------------------------------------

def _cast_ray(grid, grid_h, grid_w, px, py, angle):
    """Cast a single ray and return (distance, wall_type, hit_side).

    Uses DDA (Digital Differential Analysis) for precise and efficient
    ray-grid intersection.

    hit_side: 0 = vertical wall face (NS), 1 = horizontal wall face (EW)
    """
    sin_a = math.sin(angle)
    cos_a = math.cos(angle)

    # Avoid division by zero
    if abs(cos_a) < 1e-9:
        cos_a = 1e-9 if cos_a >= 0 else -1e-9
    if abs(sin_a) < 1e-9:
        sin_a = 1e-9 if sin_a >= 0 else -1e-9

    # DDA setup
    # Step direction
    step_x = 1 if cos_a > 0 else -1
    step_y = 1 if sin_a > 0 else -1

    # Current map cell
    map_x = int(px)
    map_y = int(py)

    # Distance to next x/y boundary
    if cos_a > 0:
        t_max_x = (map_x + 1.0 - px) / cos_a
    else:
        t_max_x = (map_x - px) / cos_a

    if sin_a > 0:
        t_max_y = (map_y + 1.0 - py) / sin_a
    else:
        t_max_y = (map_y - py) / sin_a

    # Distance between x/y boundaries
    t_delta_x = abs(1.0 / cos_a)
    t_delta_y = abs(1.0 / sin_a)

    hit_side = 0
    dist = 0.0

    for _ in range(int(MAX_DEPTH * 2) + 2):
        if t_max_x < t_max_y:
            dist = t_max_x
            t_max_x += t_delta_x
            map_x += step_x
            hit_side = 0
        else:
            dist = t_max_y
            t_max_y += t_delta_y
            map_y += step_y
            hit_side = 1

        if dist > MAX_DEPTH:
            return MAX_DEPTH, 1, 0

        # Check bounds
        if map_x < 0 or map_x >= grid_w or map_y < 0 or map_y >= grid_h:
            return dist, 1, hit_side

        # Check wall hit
        if grid[map_y][map_x] != 0:
            return dist, grid[map_y][map_x], hit_side

    return MAX_DEPTH, 1, 0


def _render_frame(image, grid, grid_h, grid_w, px, py, angle):
    """Render the 3D view into the PIL image using column-based raycasting."""
    pixels = image.load()

    for col in range(WIDTH):
        # Ray angle for this column
        ray_angle = angle - HALF_FOV + (col / WIDTH) * FOV
        dist, wall_type, hit_side = _cast_ray(grid, grid_h, grid_w, px, py, ray_angle)

        # Fix fish-eye distortion
        perp_dist = dist * math.cos(ray_angle - angle)
        if perp_dist < 0.05:
            perp_dist = 0.05

        # Wall height on screen
        wall_h = min(HEIGHT, int(HEIGHT / perp_dist))
        top = max(0, (HEIGHT - wall_h) // 2)
        bottom = min(HEIGHT - 1, top + wall_h)

        # Base colour from wall type
        wt = wall_type if 0 <= wall_type < len(WALL_COLORS) else 0
        base_r, base_g, base_b = WALL_COLORS[wt]

        # Distance shading (closer = brighter)
        shade = max(0.15, 1.0 - perp_dist / MAX_DEPTH)
        # Side shading (horizontal face hits are darker for depth cue)
        if hit_side == 1:
            shade *= 0.65

        r = int(base_r * shade)
        g = int(base_g * shade)
        b = int(base_b * shade)

        wall_color = (r, g, b)

        # Draw column: ceiling, wall, floor
        for row in range(HEIGHT):
            if row < top:
                pixels[col, row] = CEIL_COLOR
            elif row <= bottom:
                pixels[col, row] = wall_color
            else:
                pixels[col, row] = _FLOOR_GRADIENT[row]


# ---------------------------------------------------------------------------
# Mini-map overlay
# ---------------------------------------------------------------------------

_MAP_OFFSET = 2  # Pixel offset from top-left corner (padding)

# Minimap color constants
_MAP_WALL = (50, 50, 75)
_MAP_PATH_VISITED = (30, 80, 30)
_MAP_PATH_UNVISITED = (15, 15, 15)
_MAP_BORDER = (70, 70, 100)
_MAP_PLAYER = (255, 255, 0)
_MAP_DIRECTION = (255, 180, 0)
_MAP_END = (255, 50, 50)


def _draw_minimap(image, grid, grid_h, grid_w, px, py, angle, visited_cells):
    """Draw a small minimap in the top-left corner.

    Uses 1:1 mapping (one pixel per grid cell) so walls and paths are
    always distinguishable. The grid for a 6x6 maze is 13x13, fitting
    cleanly in the corner with a 1px border.
    """
    pixels = image.load()
    ox, oy = _MAP_OFFSET, _MAP_OFFSET  # top-left origin of the map area

    # Total minimap size: grid + 2px border
    map_w = grid_w + 2
    map_h = grid_h + 2

    # Clamp to screen (shouldn't be an issue for 6x6 maze = 15x15 minimap)
    draw_w = min(map_w, WIDTH - ox)
    draw_h = min(map_h, HEIGHT - oy)

    # Draw border (1px around the grid)
    for i in range(draw_w):
        pixels[ox + i, oy] = _MAP_BORDER
        if oy + draw_h - 1 < HEIGHT:
            pixels[ox + i, oy + draw_h - 1] = _MAP_BORDER
    for i in range(draw_h):
        pixels[ox, oy + i] = _MAP_BORDER
        if ox + draw_w - 1 < WIDTH:
            pixels[ox + draw_w - 1, oy + i] = _MAP_BORDER

    # Draw grid cells (1 pixel each, inside the border)
    for r in range(grid_h):
        for c in range(grid_w):
            sx = ox + 1 + c  # +1 for border
            sy = oy + 1 + r
            if sx >= WIDTH or sy >= HEIGHT:
                continue
            if grid[r][c] != 0:
                pixels[sx, sy] = _MAP_WALL
            elif (r, c) in visited_cells:
                pixels[sx, sy] = _MAP_PATH_VISITED
            else:
                pixels[sx, sy] = _MAP_PATH_UNVISITED

    # Player dot -- position is in grid-world coords (column=px, row=py)
    # Map directly: 1 grid unit = 1 pixel
    dot_x = ox + 1 + int(px)
    dot_y = oy + 1 + int(py)
    if ox < dot_x < ox + draw_w - 1 and oy < dot_y < oy + draw_h - 1:
        pixels[dot_x, dot_y] = _MAP_PLAYER

    # Direction indicator (1-2 pixels ahead of player)
    dir_x = dot_x + int(round(math.cos(angle) * 1.5))
    dir_y = dot_y + int(round(math.sin(angle) * 1.5))
    if ox < dir_x < ox + draw_w - 1 and oy < dir_y < oy + draw_h - 1:
        pixels[dir_x, dir_y] = _MAP_DIRECTION


# ---------------------------------------------------------------------------
# AI Navigator  (left-hand wall-following)
# ---------------------------------------------------------------------------

# Directions: 0=North(-y), 1=East(+x), 2=South(+y), 3=West(-x)
_DIR_DELTA = [(0, -1), (1, 0), (0, 1), (-1, 0)]
_DIR_ANGLE = [3 * math.pi / 2, 0, math.pi / 2, math.pi]


def _can_walk(grid, grid_h, grid_w, cx, cy, direction):
    """Check if AI can move one step in direction from (cx,cy)."""
    dx, dy = _DIR_DELTA[direction]
    nx, ny = cx + dx, cy + dy
    if 0 <= nx < grid_w and 0 <= ny < grid_h:
        return grid[ny][nx] == 0
    return False


def _angle_diff(a, b):
    """Compute signed angular difference from a to b, normalized to [-pi, pi]."""
    d = b - a
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    return d


class _AINavigator:
    """Left-hand wall-following maze solver with smooth interpolation.

    The AI operates in distinct states to prevent overlapping movements:
    - IDLE: ready for next decision
    - TURNING: rotating to face new direction
    - MOVING: sliding forward to next cell
    """

    STATE_IDLE = 0
    STATE_TURNING = 1
    STATE_MOVING = 2

    def __init__(self, start_x, start_y, direction=1):
        self.gx = start_x  # Grid position (column)
        self.gy = start_y  # Grid position (row)
        self.dir = direction  # 0-3 cardinal direction index
        # Smooth world position (center of cell)
        self.px = start_x + 0.5
        self.py = start_y + 0.5
        self.angle = _DIR_ANGLE[self.dir]
        # Interpolation targets
        self.target_px = self.px
        self.target_py = self.py
        self.target_angle = self.angle
        # State machine
        self.state = self.STATE_IDLE
        self.idle_timer = 0.0  # Brief pause between moves for readability
        self.visited = {(start_y, start_x)}

    def _left(self):
        return (self.dir - 1) % 4

    def _right(self):
        return (self.dir + 1) % 4

    def decide_next(self, grid, grid_h, grid_w):
        """Decide next movement using left-hand wall-following rule.

        The algorithm:
        1. Try turning left and stepping forward
        2. Try stepping forward (current direction)
        3. Try turning right and stepping forward
        4. Turn around (180°) if completely blocked
        """
        left = self._left()

        if _can_walk(grid, grid_h, grid_w, self.gx, self.gy, left):
            # Turn left, then move forward
            self.dir = left
            self.target_angle = _DIR_ANGLE[self.dir]
            self.state = self.STATE_TURNING
        elif _can_walk(grid, grid_h, grid_w, self.gx, self.gy, self.dir):
            # Move forward (no turn needed)
            self._begin_move()
        elif _can_walk(grid, grid_h, grid_w, self.gx, self.gy, self._right()):
            # Turn right, then move forward
            self.dir = self._right()
            self.target_angle = _DIR_ANGLE[self.dir]
            self.state = self.STATE_TURNING
        else:
            # Dead end: turn around
            self.dir = (self.dir + 2) % 4
            self.target_angle = _DIR_ANGLE[self.dir]
            self.state = self.STATE_TURNING

    def _begin_move(self):
        """Start moving forward in the current direction."""
        dx, dy = _DIR_DELTA[self.dir]
        self.gx += dx
        self.gy += dy
        self.target_px = self.gx + 0.5
        self.target_py = self.gy + 0.5
        self.visited.add((self.gy, self.gx))
        self.state = self.STATE_MOVING

    def update(self, dt, grid, grid_h, grid_w):
        """Update smooth interpolation each frame. Uses real delta time."""
        if self.state == self.STATE_IDLE:
            # Brief pause between actions for visual clarity
            self.idle_timer += dt
            if self.idle_timer >= 0.12:
                self.idle_timer = 0.0
                self.decide_next(grid, grid_h, grid_w)
            return

        if self.state == self.STATE_TURNING:
            # Smoothly rotate toward target angle
            da = _angle_diff(self.angle, self.target_angle)
            turn = TURN_SPEED * dt

            if abs(da) <= turn + 0.01:
                # Finished turning
                self.angle = self.target_angle
                # After turning, try to move forward
                if _can_walk(grid, grid_h, grid_w, self.gx, self.gy, self.dir):
                    self._begin_move()
                else:
                    # Can't move after turn (dead end turnaround), go idle
                    self.state = self.STATE_IDLE
            else:
                # Continue turning
                if da > 0:
                    self.angle += turn
                else:
                    self.angle -= turn
                # Keep angle normalized
                self.angle = self.angle % (2 * math.pi)
            return

        if self.state == self.STATE_MOVING:
            # Smoothly slide toward target position
            dx = self.target_px - self.px
            dy = self.target_py - self.py
            dist = math.sqrt(dx * dx + dy * dy)
            speed = MOVE_SPEED * dt

            if dist <= speed + 0.01:
                # Arrived
                self.px = self.target_px
                self.py = self.target_py
                self.state = self.STATE_IDLE
            else:
                # Slide forward
                factor = speed / dist
                self.px += dx * factor
                self.py += dy * factor
            return

    def reached(self, end_x, end_y):
        """Check if AI has reached the goal cell."""
        return self.gx == end_x and self.gy == end_y


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60):
    """Run the 3D maze raycaster display."""
    start_time = time.time()
    maze_cols, maze_rows = 6, 6  # Maze complexity (cells, not grid size)

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break

            # Generate a new maze
            grid, grid_h, grid_w = _generate_maze(maze_cols, maze_rows)
            start, end = _find_start_end(grid, grid_h, grid_w)
            if not start or not end or start == end:
                continue

            sr, sc = start
            er, ec = end

            nav = _AINavigator(sc, sr, direction=1)
            last_frame_time = time.time()

            maze_start = time.time()
            maze_timeout = 45  # Max seconds per maze before regenerating

            while time.time() - start_time < duration:
                if should_stop():
                    break
                frame_start = time.time()

                # Compute actual delta time for smooth interpolation
                dt = frame_start - last_frame_time
                last_frame_time = frame_start
                # Clamp dt to avoid huge jumps on lag spikes
                dt = min(dt, 0.1)

                # Check if maze is solved
                if nav.reached(ec, er) and nav.state == nav.STATE_IDLE:
                    _flash_solved(matrix)
                    break

                # Update AI with real elapsed time
                nav.update(dt, grid, grid_h, grid_w)

                # Timeout -- regenerate
                if time.time() - maze_start > maze_timeout:
                    break

                # Render frame
                image = Image.new("RGB", (WIDTH, HEIGHT), CEIL_COLOR)
                _render_frame(image, grid, grid_h, grid_w,
                              nav.px, nav.py, nav.angle)

                # Draw minimap overlay
                _draw_minimap(image, grid, grid_h, grid_w,
                              nav.px, nav.py, nav.angle, nav.visited)

                # End marker on minimap (red dot) using 1:1 grid mapping
                emx = _MAP_OFFSET + 1 + ec
                emy = _MAP_OFFSET + 1 + er
                if 0 <= emx < WIDTH and 0 <= emy < HEIGHT:
                    pixels = image.load()
                    pixels[emx, emy] = _MAP_END

                matrix.SetImage(image)

                frame_elapsed = time.time() - frame_start
                sleep_time = FRAME_INTERVAL - frame_elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in maze_3d: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass


def _flash_solved(matrix):
    """Brief green flash when maze is solved."""
    for brightness in [80, 160, 255, 200, 120, 60, 0]:
        if should_stop():
            return
        image = Image.new("RGB", (WIDTH, HEIGHT), (0, brightness, 0))
        try:
            draw = ImageDraw.Draw(image)
            # Draw "SOLVED" text centered
            draw.text((14, 28), "SOLVED", fill=(255, 255, 255))
        except Exception:
            pass
        matrix.SetImage(image)
        time.sleep(0.1)
    # Brief black pause before next maze
    if not should_stop():
        image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        matrix.SetImage(image)
        time.sleep(0.5)
