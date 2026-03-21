#!/usr/bin/env python3
"""Galaga-style space shooter for 64x64 LED matrix. AI-controlled."""

import time
import random
import math
import logging
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 20


class Ship:
    def __init__(self):
        self.x = WIDTH // 2
        self.y = HEIGHT - 5
        self.color = (0, 255, 200)
        self.bullets = []
        self.cooldown = 0

    def draw(self, draw):
        # Simple ship shape: triangle-ish
        draw.rectangle([self.x - 1, self.y, self.x + 1, self.y], fill=self.color)
        draw.rectangle([self.x, self.y - 1, self.x, self.y - 1], fill=self.color)
        draw.rectangle([self.x - 2, self.y + 1, self.x + 2, self.y + 1], fill=(0, 150, 120))

    def shoot(self):
        if self.cooldown <= 0:
            self.bullets.append([self.x, self.y - 2])
            self.cooldown = 5

    def update(self, aliens):
        self.cooldown -= 1
        # AI: move toward nearest alien column
        if aliens:
            nearest = min(aliens, key=lambda a: abs(a.x - self.x))
            if nearest.x < self.x:
                self.x = max(2, self.x - 1)
            elif nearest.x > self.x:
                self.x = min(WIDTH - 3, self.x + 1)
            # Shoot when roughly aligned
            if abs(nearest.x - self.x) < 3:
                self.shoot()

        # Update bullets
        for b in self.bullets[:]:
            b[1] -= 2
            if b[1] < 0:
                self.bullets.remove(b)


class Alien:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color
        self.alive = True

    def draw(self, draw):
        if self.alive:
            draw.rectangle([self.x - 1, self.y, self.x + 1, self.y], fill=self.color)
            draw.rectangle([self.x, self.y - 1, self.x, self.y + 1], fill=self.color)


def _create_aliens():
    aliens = []
    colors = [(255, 50, 50), (255, 200, 0), (50, 255, 50), (50, 150, 255)]
    for row in range(4):
        for col in range(8):
            x = 6 + col * 7
            y = 4 + row * 6
            aliens.append(Alien(x, y, colors[row % len(colors)]))
    return aliens


def run(matrix, duration=60):
    """Run the Galaga game."""
    start_time = time.time()
    ship = Ship()
    aliens = _create_aliens()
    alien_dx = 1
    alien_move_timer = 0
    score = 0
    explosions = []  # [(x, y, timer)]

    try:
        while time.time() - start_time < duration:
            frame_start = time.time()

            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 5))
            draw = ImageDraw.Draw(image)

            # Stars background
            random.seed(42)
            for _ in range(30):
                sx = random.randint(0, WIDTH - 1)
                sy = random.randint(0, HEIGHT - 1)
                draw.point((sx, sy), fill=(40, 40, 60))
            random.seed()

            # Move aliens
            alien_move_timer += 1
            if alien_move_timer >= 3:
                alien_move_timer = 0
                live_aliens = [a for a in aliens if a.alive]

                # Check edges
                move_down = False
                for a in live_aliens:
                    a.x += alien_dx
                    if a.x <= 2 or a.x >= WIDTH - 3:
                        move_down = True

                if move_down:
                    alien_dx *= -1
                    for a in live_aliens:
                        a.y += 2

            # Check bullet-alien collisions
            for b in ship.bullets[:]:
                for a in aliens:
                    if a.alive and abs(b[0] - a.x) <= 1 and abs(b[1] - a.y) <= 1:
                        a.alive = False
                        if b in ship.bullets:
                            ship.bullets.remove(b)
                        score += 10
                        explosions.append([a.x, a.y, 5])
                        break

            # Update ship AI
            live_aliens = [a for a in aliens if a.alive]
            ship.update(live_aliens)

            # Reset if all aliens dead
            if not live_aliens:
                aliens = _create_aliens()
                alien_dx = 1

            # Draw everything
            for a in aliens:
                a.draw(draw)

            ship.draw(draw)

            # Draw bullets
            for b in ship.bullets:
                draw.rectangle([b[0], b[1], b[0], b[1] + 1], fill=(255, 255, 100))

            # Draw explosions
            for exp in explosions[:]:
                ex, ey, et = exp
                c = int(255 * et / 5)
                draw.rectangle([ex - 1, ey - 1, ex + 1, ey + 1], fill=(c, c // 2, 0))
                exp[2] -= 1
                if exp[2] <= 0:
                    explosions.remove(exp)

            # Score
            try:
                from PIL import ImageFont
                font = ImageFont.load_default()
                draw.text((1, HEIGHT - 8), str(score), fill=(100, 100, 100), font=font)
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
