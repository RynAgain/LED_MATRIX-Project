#!/usr/bin/env python3
"""Space Invaders for 64x64 LED matrix. AI-controlled."""

import time
import random
import logging
from PIL import Image, ImageDraw, ImageFont
from src.display._shared import should_stop

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


def run(matrix, duration=60):
    """Run Space Invaders."""
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

            # --- Smart AI: dodge enemy bullets, target lowest invaders, fire constantly ---
            # Phase 1: Check for incoming enemy bullets in danger zone
            danger_x_range = 4   # Horizontal danger zone (pixels from player center)
            danger_y_threshold = 15  # Only worry about bullets this close vertically
            nearest_threat = None
            nearest_threat_dist = float('inf')

            for b in enemy_bullets:
                bx, by = b[0], b[1]
                # Is this bullet heading toward us (in our column, above us)?
                if abs(bx - player_x) <= danger_x_range and 0 < (HEIGHT - 4 - by) <= danger_y_threshold:
                    dist = HEIGHT - 4 - by  # Smaller = more urgent
                    if dist < nearest_threat_dist:
                        nearest_threat_dist = dist
                        nearest_threat = b

            if nearest_threat is not None:
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

            # Phase 3: Fire as fast as cooldown allows (every frame if possible)
            if not bullets or bullets[-1][1] < HEIGHT - 8:
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

            # Draw player ship
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
                font = ImageFont.load_default()
                draw.text((1, 0), str(score), fill=(80, 80, 80), font=font)
            except Exception:
                pass

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
