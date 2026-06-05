#!/usr/bin/env python3
"""Galaga-style space shooter for 64x64 LED matrix. AI-controlled.

Features inspired by the original Galaga:
- Aliens in formation that dive-bomb the player
- Boss aliens (top row) that take 2 hits and can capture the ship
- Dive attack patterns (swooping curves)
- Increasing difficulty per wave
- Bonus challenge stages
- Explosion animations
- Tractor beam visual from boss aliens
"""

import time
import random
import math
import logging
from PIL import Image, ImageDraw, ImageFont
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 20

# Alien types
ALIEN_GRUNT = 0    # Bottom rows - 1 hit, 50 pts
ALIEN_GUARD = 1    # Middle rows - 1 hit, 80 pts
ALIEN_BOSS = 2     # Top row - 2 hits, 150 pts

ALIEN_COLORS = {
    ALIEN_GRUNT: [(50, 255, 50), (50, 200, 50)],      # Green (2 animation frames)
    ALIEN_GUARD: [(255, 200, 0), (255, 150, 0)],      # Yellow/Orange
    ALIEN_BOSS: [(50, 100, 255), (200, 50, 255)],     # Blue/Purple (hit = color change)
}

ALIEN_POINTS = {ALIEN_GRUNT: 50, ALIEN_GUARD: 80, ALIEN_BOSS: 150}

# Dive attack path types
DIVE_SWOOP_LEFT = 0
DIVE_SWOOP_RIGHT = 1
DIVE_STRAIGHT = 2
DIVE_ZIGZAG = 3


class Alien:
    def __init__(self, x, y, alien_type, grid_x, grid_y):
        self.x = x
        self.y = y
        self.home_x = x  # Formation position
        self.home_y = y
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.alien_type = alien_type
        self.alive = True
        self.hp = 2 if alien_type == ALIEN_BOSS else 1
        self.diving = False
        self.dive_path = []
        self.dive_step = 0
        self.dive_cooldown = 0
        self.anim_frame = 0

    def get_color(self):
        colors = ALIEN_COLORS[self.alien_type]
        if self.alien_type == ALIEN_BOSS and self.hp == 1:
            # Damaged boss changes color
            return (200, 50, 50)
        return colors[self.anim_frame % len(colors)]

    def draw(self, draw_ctx):
        if not self.alive:
            return
        color = self.get_color()
        # Different shapes per type
        if self.alien_type == ALIEN_BOSS:
            # Larger boss: 5x3
            draw_ctx.rectangle([self.x - 2, self.y - 1, self.x + 2, self.y + 1], fill=color)
            draw_ctx.point((self.x - 1, self.y - 1), fill=(255, 255, 255))
            draw_ctx.point((self.x + 1, self.y - 1), fill=(255, 255, 255))
        elif self.alien_type == ALIEN_GUARD:
            # Medium: 3x3 with wings
            draw_ctx.rectangle([self.x - 1, self.y - 1, self.x + 1, self.y + 1], fill=color)
            draw_ctx.point((self.x - 2, self.y), fill=color)
            draw_ctx.point((self.x + 2, self.y), fill=color)
        else:
            # Grunt: 3x2
            draw_ctx.rectangle([self.x - 1, self.y, self.x + 1, self.y], fill=color)
            draw_ctx.rectangle([self.x - 1, self.y + 1, self.x + 1, self.y + 1], fill=color)
            draw_ctx.point((self.x, self.y - 1), fill=color)

    def start_dive(self, ship_x, dive_type=None):
        """Begin a dive attack toward the player."""
        if self.diving or not self.alive:
            return
        self.diving = True
        self.dive_step = 0

        if dive_type is None:
            dive_type = random.choice([DIVE_SWOOP_LEFT, DIVE_SWOOP_RIGHT, DIVE_STRAIGHT, DIVE_ZIGZAG])

        # Generate dive path (list of (x, y) offsets from start)
        self.dive_path = self._generate_dive_path(ship_x, dive_type)

    def _generate_dive_path(self, target_x, dive_type):
        """Generate a curved dive path."""
        path = []
        steps = 40
        start_x, start_y = self.x, self.y

        if dive_type == DIVE_STRAIGHT:
            for i in range(steps):
                t = i / steps
                px = start_x + (target_x - start_x) * t * 0.5
                py = start_y + (HEIGHT + 5 - start_y) * t
                path.append((int(px), int(py)))

        elif dive_type == DIVE_SWOOP_LEFT:
            for i in range(steps):
                t = i / steps
                curve = math.sin(t * math.pi) * 15
                px = start_x - curve
                py = start_y + (HEIGHT + 5 - start_y) * t
                path.append((int(px), int(py)))

        elif dive_type == DIVE_SWOOP_RIGHT:
            for i in range(steps):
                t = i / steps
                curve = math.sin(t * math.pi) * 15
                px = start_x + curve
                py = start_y + (HEIGHT + 5 - start_y) * t
                path.append((int(px), int(py)))

        elif dive_type == DIVE_ZIGZAG:
            for i in range(steps):
                t = i / steps
                zigzag = math.sin(t * math.pi * 4) * 8
                px = start_x + zigzag
                py = start_y + (HEIGHT + 5 - start_y) * t
                path.append((int(px), int(py)))

        # Return path back to formation
        for i in range(20):
            t = i / 20
            last_x = path[-1][0] if path else start_x
            px = last_x + (self.home_x - last_x) * t
            py = (HEIGHT + 5) - (HEIGHT + 5 - self.home_y) * t
            path.append((int(px), int(py)))

        return path

    def update_dive(self):
        """Update position during dive attack."""
        if not self.diving:
            return
        if self.dive_step < len(self.dive_path):
            self.x, self.y = self.dive_path[self.dive_step]
            self.dive_step += 1
        else:
            # Dive complete, return to formation
            self.diving = False
            self.x = self.home_x
            self.y = self.home_y
            self.dive_cooldown = random.randint(60, 150)


class Ship:
    def __init__(self):
        self.x = WIDTH // 2
        self.y = HEIGHT - 5
        self.color = (0, 255, 200)
        self.bullets = []
        self.cooldown = 0
        self.lives = 3
        self.invincible = 0  # Frames of invincibility after respawn
        self.double_shot = False  # Captured ship bonus

    def draw(self, draw_ctx):
        if self.invincible > 0 and self.invincible % 4 < 2:
            return  # Blink during invincibility

        # Ship shape
        draw_ctx.rectangle([self.x - 1, self.y, self.x + 1, self.y], fill=self.color)
        draw_ctx.point((self.x, self.y - 1), fill=(0, 255, 255))
        draw_ctx.rectangle([self.x - 2, self.y + 1, self.x + 2, self.y + 1], fill=(0, 150, 120))

        # Double ship indicator
        if self.double_shot:
            draw_ctx.point((self.x - 3, self.y), fill=(0, 200, 150))
            draw_ctx.point((self.x + 3, self.y), fill=(0, 200, 150))

    def shoot(self):
        if self.cooldown <= 0:
            self.bullets.append([self.x, self.y - 2])
            if self.double_shot:
                self.bullets.append([self.x - 2, self.y - 1])
                self.bullets.append([self.x + 2, self.y - 1])
            self.cooldown = 4
        self.cooldown -= 1

    def update(self, aliens, enemy_bullets, diving_aliens):
        """Smart AI with awareness of diving aliens."""
        if self.invincible > 0:
            self.invincible -= 1

        # --- Phase 1: Dodge incoming threats ---
        danger_x_range = 5
        danger_y_range = 20
        nearest_threat = None
        nearest_threat_dist = float('inf')

        # Check enemy bullets
        for b in enemy_bullets:
            bx, by = b[0], b[1]
            if abs(bx - self.x) <= danger_x_range and 0 < (self.y - by) <= danger_y_range:
                dist = self.y - by
                if dist < nearest_threat_dist:
                    nearest_threat_dist = dist
                    nearest_threat = (bx, by)

        # Check diving aliens (they're threats too!)
        for a in diving_aliens:
            if abs(a.x - self.x) <= danger_x_range and 0 < (self.y - a.y) <= danger_y_range:
                dist = self.y - a.y
                if dist < nearest_threat_dist:
                    nearest_threat_dist = dist
                    nearest_threat = (a.x, a.y)

        if nearest_threat is not None:
            bx = nearest_threat[0]
            if bx <= self.x:
                self.x = min(WIDTH - 3, self.x + 2)
            else:
                self.x = max(2, self.x - 2)
        elif aliens:
            # --- Phase 2: Target lowest/diving alien ---
            # Prefer targeting diving aliens (they're more dangerous)
            if diving_aliens:
                target = min(diving_aliens, key=lambda a: abs(a.x - self.x))
            else:
                lowest_y = max(a.y for a in aliens)
                lowest_aliens = [a for a in aliens if a.y >= lowest_y - 4]
                target = min(lowest_aliens, key=lambda a: abs(a.x - self.x))

            if target.x < self.x:
                self.x = max(2, self.x - 1)
            elif target.x > self.x:
                self.x = min(WIDTH - 3, self.x + 1)

        # --- Phase 3: Fire ---
        self.shoot()

        # Update bullets
        for b in self.bullets[:]:
            b[1] -= 3
            if b[1] < 0:
                self.bullets.remove(b)


class TractorBeam:
    """Visual effect for boss alien capture attempt."""
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.timer = 30
        self.width = 1

    def update(self):
        self.timer -= 1
        self.width = min(6, self.width + 0.3)
        return self.timer > 0

    def draw(self, draw_ctx):
        w = int(self.width)
        for dy in range(self.y, min(self.y + 20, HEIGHT)):
            alpha = max(0, 255 - (dy - self.y) * 8)
            spread = int(w * (dy - self.y) / 20)
            draw_ctx.rectangle(
                [self.x - spread, dy, self.x + spread, dy],
                fill=(0, alpha, alpha // 2)
            )


def _create_formation(wave):
    """Create alien formation. More aliens and tougher in later waves."""
    aliens = []
    cols = min(8, 6 + wave // 2)
    boss_count = min(cols, 2 + wave // 3)

    # Top row: bosses
    for col in range(boss_count):
        x = 8 + col * (48 // boss_count)
        aliens.append(Alien(x, 4, ALIEN_BOSS, col, 0))

    # Middle rows: guards
    guard_rows = min(2, 1 + wave // 4)
    for row in range(guard_rows):
        for col in range(cols):
            x = 4 + col * 7
            y = 10 + row * 5
            aliens.append(Alien(x, y, ALIEN_GUARD, col, row + 1))

    # Bottom rows: grunts
    grunt_rows = min(3, 2 + wave // 3)
    for row in range(grunt_rows):
        for col in range(cols):
            x = 4 + col * 7
            y = 10 + guard_rows * 5 + row * 5
            aliens.append(Alien(x, y, ALIEN_GRUNT, col, row + 1 + guard_rows))

    return aliens


def run(matrix, duration=60):
    """Run the Galaga game."""
    start_time = time.time()
    ship = Ship()
    wave = 1
    aliens = _create_formation(wave)
    alien_dx = 1
    alien_move_timer = 0
    score = 0
    explosions = []       # [(x, y, timer, color)]
    enemy_bullets = []    # [[x, y, speed], ...]
    tractor_beams = []    # [TractorBeam, ...]
    dive_timer = 0        # Countdown to next dive attack
    anim_tick = 0
    wave_transition = 0   # Countdown for wave transition display
    challenge_stage = False
    challenge_timer = 0

    # Difficulty scaling
    dive_interval = max(20, 60 - wave * 5)  # Frames between dive attacks
    bullet_speed = min(3, 1 + wave * 0.3)
    max_enemy_bullets = min(8, 3 + wave)

    # Star field (parallax layers)
    stars_far = [(random.randint(0, WIDTH - 1), random.randint(0, HEIGHT - 1)) for _ in range(20)]
    stars_near = [(random.randint(0, WIDTH - 1), random.randint(0, HEIGHT - 1)) for _ in range(10)]

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            anim_tick += 1

            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 5))
            draw = ImageDraw.Draw(image)

            # --- Scrolling star background ---
            for i, (sx, sy) in enumerate(stars_far):
                sy = (sy + 1) % HEIGHT
                stars_far[i] = (sx, sy)
                draw.point((sx, sy), fill=(30, 30, 50))

            for i, (sx, sy) in enumerate(stars_near):
                sy = (sy + 2) % HEIGHT
                stars_near[i] = (sx, sy)
                draw.point((sx, sy), fill=(60, 60, 80))

            # --- Wave transition ---
            if wave_transition > 0:
                wave_transition -= 1
                # Flash "WAVE X" text
                if wave_transition > 20:
                    try:
                        font = ImageFont.load_default()
                        text = f"WAVE {wave}"
                        draw.text((WIDTH // 2 - 15, HEIGHT // 2 - 4), text,
                                  fill=(255, 255, 0), font=font)
                    except Exception:
                        pass
                matrix.SetImage(image)
                elapsed = time.time() - frame_start
                sleep_time = FRAME_INTERVAL - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                continue

            live_aliens = [a for a in aliens if a.alive]
            diving_aliens = [a for a in live_aliens if a.diving]

            # --- Formation movement (only non-diving aliens) ---
            alien_move_timer += 1
            formation_aliens = [a for a in live_aliens if not a.diving]
            if alien_move_timer >= 3:
                alien_move_timer = 0

                # Animate sprites
                for a in live_aliens:
                    a.anim_frame = (anim_tick // 10) % 2

                # Move formation
                move_down = False
                for a in formation_aliens:
                    a.x += alien_dx
                    a.home_x += alien_dx
                    if a.x <= 2 or a.x >= WIDTH - 3:
                        move_down = True

                if move_down:
                    alien_dx *= -1
                    for a in formation_aliens:
                        a.y += 1
                        a.home_y += 1

            # --- Dive attacks ---
            dive_timer -= 1
            if dive_timer <= 0 and formation_aliens:
                dive_timer = dive_interval

                # Pick an alien to dive (prefer front-row aliens)
                # Weight toward lower rows (more dramatic dives)
                candidates = [a for a in formation_aliens if a.dive_cooldown <= 0]
                if candidates:
                    # Sort by y (lower = more likely to dive)
                    candidates.sort(key=lambda a: -a.y)
                    # Pick from top 50% of candidates
                    pick_pool = candidates[:max(1, len(candidates) // 2)]
                    diver = random.choice(pick_pool)
                    diver.start_dive(ship.x)

                    # Boss aliens sometimes bring escorts
                    if diver.alien_type == ALIEN_BOSS:
                        escorts = [a for a in candidates
                                   if a.alien_type != ALIEN_BOSS
                                   and abs(a.grid_x - diver.grid_x) <= 1
                                   and a is not diver]
                        for escort in escorts[:2]:
                            escort.start_dive(ship.x, DIVE_STRAIGHT)

            # Update diving aliens
            for a in live_aliens:
                if a.diving:
                    a.update_dive()
                if a.dive_cooldown > 0:
                    a.dive_cooldown -= 1

            # --- Enemy shooting (from diving aliens primarily) ---
            if len(enemy_bullets) < max_enemy_bullets:
                shooters = diving_aliens if diving_aliens else formation_aliens
                if shooters and random.random() > 0.6:
                    shooter = random.choice(shooters)
                    speed = bullet_speed + (0.5 if shooter.diving else 0)
                    enemy_bullets.append([shooter.x, shooter.y + 2, speed])

            # --- Tractor beam (boss special attack) ---
            if random.random() < 0.003 * wave:
                boss_aliens = [a for a in formation_aliens if a.alien_type == ALIEN_BOSS]
                if boss_aliens:
                    boss = random.choice(boss_aliens)
                    tractor_beams.append(TractorBeam(boss.x, boss.y + 2))

            # Update tractor beams
            for tb in tractor_beams[:]:
                if not tb.update():
                    tractor_beams.remove(tb)
                    # Small chance to grant double shot (simulating "captured ship rescued")
                    if random.random() < 0.3:
                        ship.double_shot = True

            # --- Update enemy bullets ---
            for b in enemy_bullets[:]:
                b[1] += b[2]
                if b[1] >= HEIGHT:
                    enemy_bullets.remove(b)

            # --- Collision: player bullets vs aliens ---
            for b in ship.bullets[:]:
                for a in aliens:
                    if a.alive and abs(b[0] - a.x) <= 2 and abs(b[1] - a.y) <= 2:
                        a.hp -= 1
                        if a.hp <= 0:
                            a.alive = False
                            score += ALIEN_POINTS[a.alien_type]
                            # Bigger explosion for bosses
                            exp_size = 8 if a.alien_type == ALIEN_BOSS else 5
                            explosions.append([a.x, a.y, exp_size, a.get_color()])
                        else:
                            # Hit but not dead (boss)
                            explosions.append([a.x, a.y, 3, (255, 255, 255)])
                        if b in ship.bullets:
                            ship.bullets.remove(b)
                        break

            # --- Collision: enemy bullets vs player ---
            if ship.invincible <= 0:
                for b in enemy_bullets[:]:
                    if abs(b[0] - ship.x) <= 2 and abs(b[1] - ship.y) <= 2:
                        enemy_bullets.remove(b)
                        ship.lives -= 1
                        ship.invincible = 40
                        ship.double_shot = False
                        explosions.append([ship.x, ship.y, 8, (0, 255, 255)])
                        break

                # Collision: diving aliens vs player
                for a in diving_aliens:
                    if abs(a.x - ship.x) <= 3 and abs(a.y - ship.y) <= 3:
                        a.alive = False
                        ship.lives -= 1
                        ship.invincible = 40
                        ship.double_shot = False
                        explosions.append([ship.x, ship.y, 8, (0, 255, 255)])
                        explosions.append([a.x, a.y, 6, a.get_color()])
                        score += ALIEN_POINTS[a.alien_type]
                        break

            # --- Respawn / game over ---
            if ship.lives <= 0:
                # Game over — reset
                ship.lives = 3
                ship.x = WIDTH // 2
                ship.invincible = 60
                score = 0
                wave = 1
                aliens = _create_formation(wave)
                enemy_bullets.clear()
                dive_interval = 60
                bullet_speed = 1
                max_enemy_bullets = 3
                wave_transition = 40
                continue

            # --- Wave complete ---
            if not live_aliens:
                wave += 1
                aliens = _create_formation(wave)
                alien_dx = 1
                enemy_bullets.clear()
                tractor_beams.clear()
                wave_transition = 40

                # Increase difficulty
                dive_interval = max(15, 60 - wave * 5)
                bullet_speed = min(4, 1 + wave * 0.3)
                max_enemy_bullets = min(10, 3 + wave)
                continue

            # --- Update ship AI ---
            ship.update(live_aliens, enemy_bullets, diving_aliens)

            # --- Draw everything ---
            # Tractor beams (behind aliens)
            for tb in tractor_beams:
                tb.draw(draw)

            # Aliens
            for a in aliens:
                a.draw(draw)

            # Ship
            ship.draw(draw)

            # Player bullets
            for b in ship.bullets:
                draw.rectangle([b[0], b[1], b[0], b[1] + 1], fill=(255, 255, 100))

            # Enemy bullets (different colors for speed)
            for b in enemy_bullets:
                color = (255, 60, 60) if b[2] < 2 else (255, 150, 50)
                draw.rectangle([b[0], b[1], b[0], b[1] + 1], fill=color)

            # Explosions (expanding rings)
            for exp in explosions[:]:
                ex, ey, et, ec = exp
                radius = (8 - et) * 0.8
                brightness = int(255 * et / 8)
                r = min(255, int(ec[0] * brightness / 255))
                g = min(255, int(ec[1] * brightness / 255))
                b_val = min(255, int(ec[2] * brightness / 255))
                # Draw expanding ring
                for angle in range(0, 360, 45):
                    px = int(ex + radius * math.cos(math.radians(angle)))
                    py = int(ey + radius * math.sin(math.radians(angle)))
                    if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                        draw.point((px, py), fill=(r, g, b_val))
                # Center flash
                if et > 5:
                    draw.point((ex, ey), fill=(brightness, brightness, brightness))
                exp[2] -= 1
                if exp[2] <= 0:
                    explosions.remove(exp)

            # --- HUD ---
            # Score (top-left)
            try:
                font = ImageFont.load_default()
                draw.text((1, 0), str(score), fill=(100, 100, 100), font=font)
            except Exception:
                pass

            # Lives (bottom-right, small dots)
            for i in range(ship.lives):
                draw.point((WIDTH - 2 - i * 3, HEIGHT - 2), fill=(0, 255, 200))

            # Wave indicator (bottom-left)
            try:
                draw.text((1, HEIGHT - 8), f"W{wave}", fill=(80, 80, 80), font=font)
            except Exception:
                pass

            matrix.SetImage(image)

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in galaga: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
