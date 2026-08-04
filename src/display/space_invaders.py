#!/usr/bin/env python3
"""Space Invaders for 64x64 LED matrix.

DEMO mode (controller is None): smart AI plays. INTERACTIVE mode:
- D-pad LEFT/RIGHT moves the cannon
- A fires (max 2 shots in flight, classic-style)
- Start+Select (or hold Start) quits to menu
"""

import time
import random
import logging
from PIL import Image, ImageDraw, ImageFont

_DEFAULT_FONT = ImageFont.load_default()
from src.display._shared import should_stop, read_direction, safe_rumble, show_banner
from src.input import Button, EventType, wants_quit

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 15

# Classic invader shapes (5x3 pixel art)
INVADER_SHAPES = [
    # Type 1: squid
    [[0,1,0,1,0], [1,1,1,1,1], [1,0,1,0,1]],
    # Type 2: crab
    [[1,0,1,0,1], [0,1,1,1,0], [1,0,1,0,1]],
    # Type 3: octopus  
    [[0,1,1,1,0], [1,1,1,1,1], [1,0,0,0,1]],
]

INVADER_COLORS = [
    (255, 50, 50),   # Red
    (50, 255, 50),   # Green
    (255, 200, 50),  # Yellow
]


class Invader:
    def __init__(self, x, y, shape_idx):
        self.x = x
        self.y = y
        self.shape = INVADER_SHAPES[shape_idx % len(INVADER_SHAPES)]
        self.color = INVADER_COLORS[shape_idx % len(INVADER_COLORS)]
        self.alive = True

    def draw(self, draw):
        if not self.alive:
            return
        for row_idx, row in enumerate(self.shape):
            for col_idx, pixel in enumerate(row):
                if pixel:
                    px = self.x + col_idx
                    py = self.y + row_idx
                    if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                        draw.point((px, py), fill=self.color)


def run(matrix, duration=60, controller=None):
    """Run Space Invaders.

    :param controller: if provided, human plays. If None, AI demo mode.
    """
    interactive = controller is not None
    if interactive:
        show_banner(matrix, ["INVADERS", "READY!"], color=(50, 255, 50), hold=1.5)
    start_time = time.time()

    # Create invader grid
    invaders = []
    for row in range(5):
        for col in range(8):
            x = 3 + col * 7
            y = 3 + row * 5
            invaders.append(Invader(x, y, row))

    player_x = WIDTH // 2
    bullets = []
    enemy_bullets = []
    direction = 1
    move_timer = 0
    score = 0
    lives = 3
    invincible = 0
    shields = [[x, HEIGHT - 14] for x in range(10, 55, 15)]
    shield_health = {i: 3 for i in range(len(shields))}

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()

            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 2))
            draw = ImageDraw.Draw(image)

            live_invaders = [inv for inv in invaders if inv.alive]

            # --- Input (interactive) ---
            want_fire = False
            if interactive:
                if wants_quit(controller):
                    break
                events = controller.poll_events()
                for ev in events:
                    if ev.type is EventType.PRESSED and ev.button is Button.A:
                        want_fire = True
                d = read_direction(controller, cardinal_only=False)
                if d:
                    player_x = max(2, min(WIDTH - 3, player_x + d[0] * 2))
                try:
                    if controller.is_pressed(Button.A):
                        want_fire = True
                except Exception:
                    pass
                # Classic constraint: at most 2 player shots in flight
                if want_fire and len(bullets) < 2:
                    bullets.append([player_x, HEIGHT - 6])
                if invincible > 0:
                    invincible -= 1

            # --- Smart AI: dodge enemy bullets, target lowest invaders, fire constantly ---
            # Phase 1: Check for incoming enemy bullets in danger zone
            if interactive:
                pass  # player drives; AI below is demo-only
            danger_x_range = 4   # Horizontal danger zone (pixels from player center)
            danger_y_threshold = 15  # Only worry about bullets this close vertically
            nearest_threat = None
            nearest_threat_dist = float('inf')

            for b in (() if interactive else enemy_bullets):
                bx, by = b[0], b[1]
                # Is this bullet heading toward us (in our column, above us)?
                if abs(bx - player_x) <= danger_x_range and 0 < (HEIGHT - 4 - by) <= danger_y_threshold:
                    dist = HEIGHT - 4 - by  # Smaller = more urgent
                    if dist < nearest_threat_dist:
                        nearest_threat_dist = dist
                        nearest_threat = b

            if interactive:
                pass
            elif nearest_threat is not None:
                # Phase 1 active: DODGE — move away from the threatening bullet
                bx = nearest_threat[0]
                if bx <= player_x:
                    # Bullet is to our left or center — move right
                    player_x = min(WIDTH - 3, player_x + 2)
                else:
                    # Bullet is to our right — move left
                    player_x = max(2, player_x - 2)
            elif live_invaders:
                # Phase 2: Offensive — target the lowest invader in nearest column
                # Find the lowest invader (most dangerous / closest to ground)
                lowest_y = max(inv.y for inv in live_invaders)
                # Among the lowest row (within 5px), pick the one nearest horizontally
                lowest_invaders = [inv for inv in live_invaders if inv.y >= lowest_y - 5]
                target = min(lowest_invaders, key=lambda i: abs(i.x + 2 - player_x))

                if target.x + 2 < player_x:
                    player_x = max(2, player_x - 1)
                elif target.x + 2 > player_x:
                    player_x = min(WIDTH - 3, player_x + 1)

            # Phase 3 (demo): fire as fast as the cooldown allows
            if not interactive and (not bullets or bullets[-1][1] < HEIGHT - 8):
                bullets.append([player_x, HEIGHT - 6])

            # Move invaders
            move_timer += 1
            if move_timer >= 4:
                move_timer = 0
                hit_edge = False
                for inv in live_invaders:
                    inv.x += direction
                    if inv.x <= 0 or inv.x + 5 >= WIDTH:
                        hit_edge = True

                if hit_edge:
                    direction *= -1
                    for inv in live_invaders:
                        inv.y += 2

                # Enemy shooting
                if live_invaders and random.random() > 0.6:
                    shooter = random.choice(live_invaders)
                    enemy_bullets.append([shooter.x + 2, shooter.y + 3])

            # Update bullets
            for b in bullets[:]:
                b[1] -= 2
                if b[1] < 0:
                    bullets.remove(b)
                    continue
                # Check hit on invaders
                hit_something = False
                for inv in invaders:
                    if inv.alive and inv.x <= b[0] <= inv.x + 4 and inv.y <= b[1] <= inv.y + 2:
                        inv.alive = False
                        if b in bullets:
                            bullets.remove(b)
                        score += 10
                        hit_something = True
                        break
                if hit_something:
                    continue
                # Check hit on shields (player bullets degrade shields too)
                for i, (sx, sy) in enumerate(shields):
                    if shield_health.get(i, 0) > 0:
                        if sx <= b[0] <= sx + 6 and sy <= b[1] <= sy + 2:
                            shield_health[i] -= 1
                            if b in bullets:
                                bullets.remove(b)
                            break

            for b in enemy_bullets[:]:
                b[1] += 1
                if b[1] >= HEIGHT:
                    enemy_bullets.remove(b)
                    continue
                # Player hit (interactive only; the demo AI dodges instead)
                if (interactive and invincible <= 0
                        and abs(b[0] - player_x) <= 2 and b[1] >= HEIGHT - 6):
                    enemy_bullets.remove(b)
                    lives -= 1
                    invincible = 30
                    safe_rumble(controller, 0.8, 200)
                    continue
                # Check enemy bullets hitting shields (shields absorb fire)
                hit_shield = False
                for i, (sx, sy) in enumerate(shields):
                    if shield_health.get(i, 0) > 0:
                        if sx <= b[0] <= sx + 6 and sy <= b[1] <= sy + 2:
                            shield_health[i] -= 1
                            enemy_bullets.remove(b)
                            hit_shield = True
                            break
                if hit_shield:
                    continue

            # Invaders reaching the ground / player out of lives
            landed = any(inv.y + 3 >= HEIGHT - 6 for inv in live_invaders)
            if interactive and (lives <= 0 or landed):
                show_banner(matrix, ["GAME OVER", f"SCORE {score}"],
                            color=(255, 80, 80), hold=3.0)
                return
            if not interactive and landed:
                # Demo: invaders won — reset the board
                invaders = []
                for row in range(5):
                    for col in range(8):
                        invaders.append(Invader(3 + col * 7, 3 + row * 5, row))
                direction = 1
                enemy_bullets.clear()
                shield_health = {i: 3 for i in range(len(shields))}
                continue

            # Reset if all dead
            if not live_invaders:
                invaders = []
                for row in range(5):
                    for col in range(8):
                        x = 3 + col * 7
                        y = 3 + row * 5
                        invaders.append(Invader(x, y, row))
                direction = 1
                # Restore shields on new wave
                shield_health = {i: 3 for i in range(len(shields))}

            # Draw invaders
            for inv in invaders:
                inv.draw(draw)

            # Draw player ship (blinks while invincible)
            if not (interactive and invincible > 0 and invincible % 4 < 2):
                draw.rectangle([player_x - 2, HEIGHT - 4, player_x + 2, HEIGHT - 4], fill=(0, 200, 255))
                draw.rectangle([player_x - 1, HEIGHT - 5, player_x + 1, HEIGHT - 5], fill=(0, 200, 255))
                draw.rectangle([player_x, HEIGHT - 6, player_x, HEIGHT - 6], fill=(0, 255, 255))

            # Draw shields
            for i, (sx, sy) in enumerate(shields):
                if shield_health.get(i, 0) > 0:
                    c = shield_health[i] * 40
                    draw.rectangle([sx, sy, sx + 6, sy + 2], fill=(0, c, 0))

            # Draw bullets
            for b in bullets:
                draw.rectangle([b[0], b[1], b[0], b[1] + 1], fill=(255, 255, 100))

            for b in enemy_bullets:
                draw.rectangle([b[0], b[1], b[0], b[1] + 1], fill=(255, 80, 80))

            # Score
            try:
                font = _DEFAULT_FONT
                draw.text((1, 0), str(score), fill=(80, 80, 80), font=font)
            except Exception:
                pass

            # Lives (interactive; top-right dots)
            if interactive:
                for i in range(lives):
                    draw.point((WIDTH - 2 - i * 3, 1), fill=(0, 255, 200))

            # Ground line
            draw.rectangle([0, HEIGHT - 2, WIDTH - 1, HEIGHT - 2], fill=(0, 80, 0))

            matrix.SetImage(image)

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in space invaders: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
