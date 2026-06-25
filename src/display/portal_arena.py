#!/usr/bin/env python3
"""
Portal Arena -- Top-down 2-player portal shooter on 64x64 LED matrix.

Each player has:
- A portal gun that places Portal A (orange) and Portal B (blue)
- A damage gun that fires projectiles
- Portals teleport the OWNER (or owner's shots) from A->B or B->A
- Opponent's portals do nothing to you
- Each player can have max 2 portals active (A and B)

Features:
- Top-down arena with walls
- Portals placed on walls glow and animate
- Shots that enter your own portal exit from the other
- Walk into your own portal to teleport
- Health bars, respawn system
- AI vs AI demo or Player vs AI interactive

Control scheme (INTERACTIVE):
- D-pad: move (8-directional)
- A: fire damage gun (in facing direction)
- B: place portal (alternates A/B)
- Start+Select: quit
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw
from src.display._shared import should_stop, interruptible_sleep, show_banner, safe_rumble
from src.display._fonts import _draw_text, _text_width
from src.display._utils import _scale_color

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
FPS = 20
FRAME_DUR = 1.0 / FPS

# Physics
MOVE_SPEED = 1.5
BULLET_SPEED = 3.0
BULLET_DAMAGE = 25
MAX_HP = 100
RESPAWN_TIME = 40  # frames
SHOOT_COOLDOWN = 6  # frames between shots
MAX_BULLETS_PER_PLAYER = 3  # Max active bullets at once (prevents spam)
PORTAL_COOLDOWN = 20  # frames between portal placements

# Colors
BG_COLOR = (5, 5, 10)
WALL_COLOR = (40, 40, 60)
P1_COLOR = (80, 180, 255)  # Blue player
P2_COLOR = (255, 100, 80)  # Red player
P1_PORTAL_A = (255, 140, 0)   # Orange portal
P1_PORTAL_B = (0, 140, 255)   # Blue portal
P2_PORTAL_A = (255, 50, 200)  # Pink portal
P2_PORTAL_B = (50, 255, 150)  # Green portal
BULLET_P1 = (150, 220, 255)
BULLET_P2 = (255, 150, 100)
HP_COLOR = (0, 255, 80)
HP_BG = (40, 20, 20)
PORTAL_GLOW = 40

# Arena map (1 = wall, 0 = empty)
# 64x64 pixels, walls are single pixels but we use a coarser grid
GRID_SIZE = 4  # Each grid cell = 4x4 pixels
GRID_W = SIZE // GRID_SIZE
GRID_H = SIZE // GRID_SIZE

ARENA = [
    "################",
    "#..............#",
    "#..##....##..#.#",
    "#..##....##....#",
    "#..............#",
    "#....##..##....#",
    "#....##..##....#",
    "#..............#",
    "#..............#",
    "#....##..##....#",
    "#....##..##....#",
    "#..............#",
    "#..##....##..#.#",
    "#..##....##....#",
    "#..............#",
    "################",
]


def _is_wall(gx, gy):
    """Check if grid position is a wall."""
    if gx < 0 or gx >= GRID_W or gy < 0 or gy >= GRID_H:
        return True
    row = ARENA[gy] if gy < len(ARENA) else "#" * GRID_W
    return row[gx] == '#' if gx < len(row) else True


def _grid_to_pixel(gx, gy):
    """Convert grid coords to pixel center."""
    return gx * GRID_SIZE + GRID_SIZE // 2, gy * GRID_SIZE + GRID_SIZE // 2


def _pixel_to_grid(px, py):
    """Convert pixel coords to grid."""
    return int(px) // GRID_SIZE, int(py) // GRID_SIZE


def _is_wall_at_pixel(px, py):
    """Check if a pixel position is inside a wall."""
    gx, gy = _pixel_to_grid(px, py)
    return _is_wall(gx, gy)


# ---------------------------------------------------------------------------
# Game entities
# ---------------------------------------------------------------------------

class Portal:
    """A portal placed on a wall surface."""

    def __init__(self, x, y, owner_id, portal_type):
        self.x = float(x)
        self.y = float(y)
        self.owner_id = owner_id  # 0 or 1
        self.portal_type = portal_type  # 'A' or 'B'
        self.tick = 0

    def get_color(self):
        if self.owner_id == 0:
            return P1_PORTAL_A if self.portal_type == 'A' else P1_PORTAL_B
        else:
            return P2_PORTAL_A if self.portal_type == 'A' else P2_PORTAL_B


class Bullet:
    """A projectile fired by a player."""

    def __init__(self, x, y, vx, vy, owner_id):
        self.x = float(x)
        self.y = float(y)
        self.vx = vx
        self.vy = vy
        self.owner_id = owner_id
        self.life = 60  # Max travel frames
        self.teleported = False  # Can only teleport once

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        return self.life > 0 and 0 <= self.x < SIZE and 0 <= self.y < SIZE


class Player:
    """A player character."""

    def __init__(self, x, y, player_id):
        self.x = float(x)
        self.y = float(y)
        self.player_id = player_id
        self.hp = MAX_HP
        self.facing_x = 0.0
        self.facing_y = -1.0  # Default facing up
        self.shoot_cooldown = 0
        self.portal_cooldown = 0
        self.next_portal = 'A'  # Alternates between A and B
        self.respawn_timer = 0
        self.alive = True
        self.score = 0

    def move(self, dx, dy):
        """Move player with wall collision."""
        if not self.alive:
            return

        # Normalize diagonal movement
        length = math.sqrt(dx * dx + dy * dy)
        if length > 0:
            dx = dx / length * MOVE_SPEED
            dy = dy / length * MOVE_SPEED
            self.facing_x = dx / MOVE_SPEED
            self.facing_y = dy / MOVE_SPEED

        # Try X movement
        new_x = self.x + dx
        if not _is_wall_at_pixel(new_x, self.y):
            self.x = new_x

        # Try Y movement
        new_y = self.y + dy
        if not _is_wall_at_pixel(self.x, new_y):
            self.y = new_y

        # Clamp to arena
        self.x = max(GRID_SIZE, min(SIZE - GRID_SIZE - 1, self.x))
        self.y = max(GRID_SIZE, min(SIZE - GRID_SIZE - 1, self.y))

    def can_shoot(self):
        return self.alive and self.shoot_cooldown <= 0

    def can_place_portal(self):
        return self.alive and self.portal_cooldown <= 0

    def update(self):
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1
        if self.portal_cooldown > 0:
            self.portal_cooldown -= 1
        if not self.alive:
            self.respawn_timer -= 1
            if self.respawn_timer <= 0:
                self.alive = True
                self.hp = MAX_HP


class Particle:
    """Visual effect particle."""

    def __init__(self, x, y, vx, vy, color, life=8):
        self.x = float(x)
        self.y = float(y)
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = life

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        return self.life > 0


# ---------------------------------------------------------------------------
# Main game
# ---------------------------------------------------------------------------

class PortalArenaGame:
    """Full Portal Arena game state."""

    def __init__(self):
        # Spawn positions
        p1_pos = _grid_to_pixel(3, 3)
        p2_pos = _grid_to_pixel(12, 12)
        self.player1 = Player(p1_pos[0], p1_pos[1], 0)
        self.player2 = Player(p2_pos[0], p2_pos[1], 1)
        self.bullets = []
        self.portals = []  # All active portals
        self.particles = []
        self.tick = 0
        self.win_score = 5

    def _get_player_portals(self, player_id):
        """Get portal A and B for a player."""
        portal_a = None
        portal_b = None
        for p in self.portals:
            if p.owner_id == player_id:
                if p.portal_type == 'A':
                    portal_a = p
                elif p.portal_type == 'B':
                    portal_b = p
        return portal_a, portal_b

    def place_portal(self, player):
        """Place a portal in front of the player on the nearest wall."""
        if not player.can_place_portal():
            return

        # Cast a ray in facing direction to find a wall
        fx, fy = player.facing_x, player.facing_y
        length = math.sqrt(fx * fx + fy * fy)
        if length < 0.1:
            return
        fx, fy = fx / length, fy / length

        # Scan forward to find wall
        px, py = player.x, player.y
        for _ in range(20):
            px += fx * 2
            py += fy * 2
            if _is_wall_at_pixel(px, py):
                # Place portal just before the wall
                portal_x = px - fx * 2
                portal_y = py - fy * 2
                break
        else:
            return  # No wall found in range

        # Remove existing portal of same type
        portal_type = player.next_portal
        self.portals = [p for p in self.portals
                        if not (p.owner_id == player.player_id and
                                p.portal_type == portal_type)]

        # Place new portal
        self.portals.append(Portal(portal_x, portal_y, player.player_id, portal_type))
        player.next_portal = 'B' if portal_type == 'A' else 'A'
        player.portal_cooldown = PORTAL_COOLDOWN

        # Particles
        color = P1_PORTAL_A if player.player_id == 0 else P2_PORTAL_A
        for _ in range(5):
            self.particles.append(Particle(
                portal_x, portal_y,
                random.uniform(-1, 1), random.uniform(-1, 1),
                color, life=8
            ))

    def shoot(self, player):
        """Fire a bullet in the player's facing direction.

        Each player can only have MAX_BULLETS_PER_PLAYER active bullets
        at once to prevent spam.
        """
        if not player.can_shoot():
            return

        # Check bullet limit per player
        active_count = sum(1 for b in self.bullets if b.owner_id == player.player_id)
        if active_count >= MAX_BULLETS_PER_PLAYER:
            return

        fx, fy = player.facing_x, player.facing_y
        length = math.sqrt(fx * fx + fy * fy)
        if length < 0.1:
            fy = -1  # Default up
            length = 1

        fx, fy = fx / length, fy / length
        bx = player.x + fx * 4
        by = player.y + fy * 4

        self.bullets.append(Bullet(bx, by, fx * BULLET_SPEED, fy * BULLET_SPEED,
                                   player.player_id))
        player.shoot_cooldown = SHOOT_COOLDOWN

    def _check_portal_teleport_entity(self, entity_x, entity_y, owner_id):
        """Check if an entity position overlaps a portal. Returns new pos or None."""
        portal_a, portal_b = self._get_player_portals(owner_id)
        if not portal_a or not portal_b:
            return None

        # Check portal A
        dx = entity_x - portal_a.x
        dy = entity_y - portal_a.y
        if dx * dx + dy * dy < 16:  # Within 4px
            return portal_b.x, portal_b.y

        # Check portal B
        dx = entity_x - portal_b.x
        dy = entity_y - portal_b.y
        if dx * dx + dy * dy < 16:
            return portal_a.x, portal_a.y

        return None

    def update(self):
        """Update one game frame."""
        self.tick += 1

        self.player1.update()
        self.player2.update()

        # Respawn dead players
        if not self.player1.alive and self.player1.respawn_timer <= 0:
            pos = _grid_to_pixel(3, 3)
            self.player1.x, self.player1.y = pos
        if not self.player2.alive and self.player2.respawn_timer <= 0:
            pos = _grid_to_pixel(12, 12)
            self.player2.x, self.player2.y = pos

        # Portal teleport for players (own portals only)
        for player in [self.player1, self.player2]:
            if not player.alive:
                continue
            result = self._check_portal_teleport_entity(
                player.x, player.y, player.player_id)
            if result:
                player.x, player.y = result
                # Brief invulnerability flash
                for _ in range(4):
                    self.particles.append(Particle(
                        player.x, player.y,
                        random.uniform(-2, 2), random.uniform(-2, 2),
                        P1_COLOR if player.player_id == 0 else P2_COLOR, life=6
                    ))

        # Update bullets
        active_bullets = []
        for bullet in self.bullets:
            if not bullet.update():
                continue

            # Wall collision
            if _is_wall_at_pixel(bullet.x, bullet.y):
                # Spawn impact particles
                color = BULLET_P1 if bullet.owner_id == 0 else BULLET_P2
                for _ in range(3):
                    self.particles.append(Particle(
                        bullet.x, bullet.y,
                        random.uniform(-1, 1), random.uniform(-1, 1),
                        color, life=5
                    ))
                continue

            # Portal teleport for bullets (owner's portals only)
            if not bullet.teleported:
                result = self._check_portal_teleport_entity(
                    bullet.x, bullet.y, bullet.owner_id)
                if result:
                    bullet.x, bullet.y = result
                    bullet.teleported = True
                    # Particle burst at exit
                    for _ in range(3):
                        self.particles.append(Particle(
                            bullet.x, bullet.y,
                            random.uniform(-1, 1), random.uniform(-1, 1),
                            (255, 255, 200), life=5
                        ))

            # Hit detection against opponent
            for player in [self.player1, self.player2]:
                if player.player_id == bullet.owner_id:
                    continue
                if not player.alive:
                    continue
                dx = bullet.x - player.x
                dy = bullet.y - player.y
                if dx * dx + dy * dy < 16:  # Hit radius ~4px
                    player.hp -= BULLET_DAMAGE
                    # Hit particles
                    p_color = P1_COLOR if player.player_id == 0 else P2_COLOR
                    for _ in range(5):
                        self.particles.append(Particle(
                            player.x, player.y,
                            random.uniform(-2, 2), random.uniform(-2, 2),
                            p_color, life=8
                        ))
                    if player.hp <= 0:
                        player.alive = False
                        player.respawn_timer = RESPAWN_TIME
                        # Score for killer
                        if bullet.owner_id == 0:
                            self.player1.score += 1
                        else:
                            self.player2.score += 1
                    break
            else:
                active_bullets.append(bullet)
                continue
            # Bullet was consumed by hit
            continue

        self.bullets = active_bullets

        # Update portal ticks
        for portal in self.portals:
            portal.tick += 1

        # Update particles
        self.particles = [p for p in self.particles if p.update()]

    def check_winner(self):
        """Returns winner player_id or -1."""
        if self.player1.score >= self.win_score:
            return 0
        if self.player2.score >= self.win_score:
            return 1
        return -1

    def draw(self):
        """Render the game."""
        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Draw walls
        for gy in range(GRID_H):
            for gx in range(GRID_W):
                if _is_wall(gx, gy):
                    x1 = gx * GRID_SIZE
                    y1 = gy * GRID_SIZE
                    draw.rectangle([(x1, y1), (x1 + GRID_SIZE - 1, y1 + GRID_SIZE - 1)],
                                   fill=WALL_COLOR)

        # Draw portals (with glow animation)
        for portal in self.portals:
            px, py = int(portal.x), int(portal.y)
            color = portal.get_color()
            pulse = 0.6 + 0.4 * math.sin(portal.tick * 0.2)
            c = tuple(int(v * pulse) for v in color)
            # Glow ring
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                gx = px + int(2 * math.cos(rad))
                gy = py + int(2 * math.sin(rad))
                if 0 <= gx < SIZE and 0 <= gy < SIZE:
                    dim = tuple(v // 3 for v in c)
                    draw.point((gx, gy), fill=dim)
            # Core
            if 0 <= px < SIZE and 0 <= py < SIZE:
                draw.point((px, py), fill=c)
            # Label (A or B tiny)
            if 0 <= px + 2 < SIZE and 0 <= py - 2 < SIZE:
                label_c = tuple(v // 2 for v in color)
                draw.point((px + 1, py - 1), fill=label_c)

        # Draw bullets
        for bullet in self.bullets:
            bx, by = int(bullet.x), int(bullet.y)
            color = BULLET_P1 if bullet.owner_id == 0 else BULLET_P2
            if bullet.teleported:
                color = (255, 255, 200)  # Bright after teleport
            if 0 <= bx < SIZE and 0 <= by < SIZE:
                draw.point((bx, by), fill=color)

        # Draw players
        for player in [self.player1, self.player2]:
            if not player.alive:
                # Respawn countdown flash
                if player.respawn_timer % 6 < 3:
                    continue
            px, py = int(player.x), int(player.y)
            color = P1_COLOR if player.player_id == 0 else P2_COLOR
            if 0 <= px < SIZE - 1 and 0 <= py < SIZE - 1:
                # 3x3 body
                draw.rectangle([(px - 1, py - 1), (px + 1, py + 1)], fill=color)
                # Facing indicator (1px in facing direction)
                fx = px + int(player.facing_x * 2)
                fy = py + int(player.facing_y * 2)
                if 0 <= fx < SIZE and 0 <= fy < SIZE:
                    draw.point((fx, fy), fill=(255, 255, 255))

        # Draw particles
        for p in self.particles:
            ppx, ppy = int(p.x), int(p.y)
            if 0 <= ppx < SIZE and 0 <= ppy < SIZE:
                alpha = p.life / 8.0
                c = tuple(int(v * alpha) for v in p.color)
                draw.point((ppx, ppy), fill=c)

        # HUD: HP bars at top
        # P1 HP (left side)
        bar_w = 20
        hp_pct1 = max(0, self.player1.hp / MAX_HP)
        draw.rectangle([(1, 1), (bar_w, 2)], fill=HP_BG)
        if hp_pct1 > 0:
            draw.rectangle([(1, 1), (int(1 + (bar_w - 1) * hp_pct1), 2)], fill=P1_COLOR)

        # P2 HP (right side)
        hp_pct2 = max(0, self.player2.hp / MAX_HP)
        draw.rectangle([(SIZE - bar_w - 1, 1), (SIZE - 2, 2)], fill=HP_BG)
        if hp_pct2 > 0:
            x_start = SIZE - bar_w - 1
            draw.rectangle([(x_start, 1),
                            (int(x_start + (bar_w - 1) * hp_pct2), 2)], fill=P2_COLOR)

        # Scores (center top)
        score_str = f"{self.player1.score}-{self.player2.score}"
        sw = _text_width(score_str, scale=1, spacing=0)
        _draw_text(draw, score_str, (SIZE - sw) // 2, 1, (180, 180, 180), scale=1, spacing=0)

        return image


# ---------------------------------------------------------------------------
# AI Logic
# ---------------------------------------------------------------------------

def _ai_control(game, player, opponent):
    """AI for a player. Returns (dx, dy, shoot, place_portal)."""
    dx, dy = 0.0, 0.0
    do_shoot = False
    do_portal = False

    if not player.alive:
        return dx, dy, do_shoot, do_portal

    # Distance to opponent
    if opponent.alive:
        ox = opponent.x - player.x
        oy = opponent.y - player.y
        dist = math.sqrt(ox * ox + oy * oy)

        # Face opponent
        if dist > 0:
            player.facing_x = ox / dist
            player.facing_y = oy / dist

        # If close, shoot
        if dist < 30 and player.can_shoot():
            # Check if there's a clear line of sight (no walls)
            clear = True
            check_steps = int(dist / 3)
            for step in range(1, check_steps):
                t = step / check_steps
                cx = player.x + ox * t
                cy = player.y + oy * t
                if _is_wall_at_pixel(cx, cy):
                    clear = False
                    break
            if clear:
                do_shoot = True

        # Movement: strafe and approach
        if dist > 20:
            # Move toward opponent
            dx = ox / dist
            dy = oy / dist
        elif dist < 12:
            # Back away
            dx = -ox / dist
            dy = -oy / dist
        else:
            # Strafe (perpendicular movement)
            strafe_dir = 1 if (game.tick + player.player_id * 50) % 100 < 50 else -1
            dx = -oy / dist * strafe_dir
            dy = ox / dist * strafe_dir

        # Place portals strategically (occasionally)
        if player.can_place_portal() and random.random() < 0.02:
            do_portal = True

    else:
        # Opponent dead, move to center and place portals
        cx = SIZE / 2 - player.x
        cy = SIZE / 2 - player.y
        dist = math.sqrt(cx * cx + cy * cy)
        if dist > 5:
            dx = cx / dist
            dy = cy / dist

        if player.can_place_portal() and random.random() < 0.03:
            do_portal = True

    # Dodge bullets (react to nearby enemy bullets)
    for bullet in game.bullets:
        if bullet.owner_id == player.player_id:
            continue
        bx = bullet.x - player.x
        by = bullet.y - player.y
        bdist = math.sqrt(bx * bx + by * by)
        if bdist < 10:
            # Dodge perpendicular to bullet direction
            dodge_x = -bullet.vy
            dodge_y = bullet.vx
            dx += dodge_x * 0.5
            dy += dodge_y * 0.5

    # Add slight randomness
    if random.random() < 0.05:
        dx += random.uniform(-0.5, 0.5)
        dy += random.uniform(-0.5, 0.5)

    return dx, dy, do_shoot, do_portal


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------

def _run_demo(matrix, duration, start_time):
    """AI vs AI demo."""
    game = PortalArenaGame()

    while time.time() - start_time < duration:
        if should_stop():
            return
        frame_start = time.time()

        # AI for both players
        dx1, dy1, s1, p1 = _ai_control(game, game.player1, game.player2)
        dx2, dy2, s2, p2 = _ai_control(game, game.player2, game.player1)

        game.player1.move(dx1, dy1)
        game.player2.move(dx2, dy2)
        if s1:
            game.shoot(game.player1)
        if s2:
            game.shoot(game.player2)
        if p1:
            game.place_portal(game.player1)
        if p2:
            game.place_portal(game.player2)

        game.update()

        winner = game.check_winner()
        if winner >= 0:
            color = P1_COLOR if winner == 0 else P2_COLOR
            label = "P1 WINS" if winner == 0 else "P2 WINS"
            show_banner(matrix, [label, f"{game.player1.score}-{game.player2.score}"],
                        color=color, hold=1.5)
            game = PortalArenaGame()
            continue

        image = game.draw()
        matrix.SetImage(image)
        time.sleep(FRAME_DUR)


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def _run_interactive(matrix, controller, start_time):
    """Player (P1) vs AI (P2)."""
    from src.input.controller import wants_quit, Button, EventType

    game = PortalArenaGame()
    show_banner(matrix, ["PORTAL ARENA", "A:SHOOT B:PORTAL"],
                color=P1_PORTAL_A, hold=1.5)

    while True:
        if should_stop():
            return
        frame_start = time.time()

        events = controller.poll_events()
        if wants_quit(controller):
            return

        # Player 1 input
        dx, dy = 0.0, 0.0
        d = controller.get_direction()
        if d:
            dx, dy = float(d[0]), float(d[1])

        for ev in events:
            if ev.type is EventType.PRESSED:
                if ev.button is Button.A:
                    game.shoot(game.player1)
                elif ev.button is Button.B:
                    game.place_portal(game.player1)

        game.player1.move(dx, dy)

        # AI for P2
        dx2, dy2, s2, p2 = _ai_control(game, game.player2, game.player1)
        game.player2.move(dx2, dy2)
        if s2:
            game.shoot(game.player2)
        if p2:
            game.place_portal(game.player2)

        game.update()

        winner = game.check_winner()
        if winner >= 0:
            player_won = winner == 0
            safe_rumble(controller, 1.0 if player_won else 0.5, 300)
            msg = "YOU WIN!" if player_won else "YOU LOSE"
            color = (80, 255, 120) if player_won else (255, 80, 80)
            show_banner(matrix, [msg, f"{game.player1.score}-{game.player2.score}"],
                        color=color, hold=2.0)
            return

        image = game.draw()
        matrix.SetImage(image)

        elapsed = time.time() - frame_start
        sleep_time = FRAME_DUR - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60, controller=None):
    """Run Portal Arena.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds (DEMO mode).
        controller: optional Controller. None -> DEMO, not-None -> INTERACTIVE.
    """
    start_time = time.time()
    try:
        if controller is None:
            _run_demo(matrix, duration, start_time)
        else:
            _run_interactive(matrix, controller, start_time)
    except Exception as e:
        logger.error("Error in portal_arena: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
