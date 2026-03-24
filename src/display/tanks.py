#!/usr/bin/env python3
"""Tank duel game for 64x64 LED matrix. Two AI tanks battle it out."""

import time
import random
import math
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 20
GROUND_Y = 52  # Ground level


class Bullet:
    def __init__(self, x, y, vx, vy, color):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.alive = True
    
    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.15  # Gravity
        if self.x < 0 or self.x >= WIDTH or self.y >= HEIGHT:
            self.alive = False


class Tank:
    def __init__(self, x, facing_right, color, turret_color):
        self.x = x
        self.y = 0  # Will be placed on terrain
        self.facing_right = facing_right
        self.color = color
        self.turret_color = turret_color
        self.angle = 45 if facing_right else 135  # Turret angle in degrees
        self.power = 3.0
        self.health = 3
        self.cooldown = 0
        self.speed = 0.3
    
    def place_on_terrain(self, terrain):
        """Place tank on the terrain surface."""
        ix = int(self.x)
        if 0 <= ix < WIDTH:
            self.y = terrain[ix] - 3  # Sit on top of terrain
    
    def draw(self, draw):
        if self.health <= 0:
            return
        x, y = int(self.x), int(self.y)
        
        # Tank body (4x3 pixels)
        draw.rectangle([x - 2, y, x + 2, y + 2], fill=self.color)
        
        # Treads
        draw.rectangle([x - 2, y + 3, x + 2, y + 3], fill=(80, 80, 80))
        
        # Turret (line from center)
        angle_rad = math.radians(self.angle)
        tx = x + int(4 * math.cos(angle_rad))
        ty = y - int(4 * math.sin(angle_rad))
        draw.line([(x, y), (tx, ty)], fill=self.turret_color, width=1)
        
        # Health bar
        for i in range(self.health):
            draw.point((x - 1 + i, y - 2), fill=(0, 255, 0))
    
    def shoot(self):
        if self.cooldown > 0:
            return None
        self.cooldown = 20
        
        angle_rad = math.radians(self.angle)
        bx = self.x + 5 * math.cos(angle_rad)
        by = self.y - 5 * math.sin(angle_rad)
        vx = self.power * math.cos(angle_rad)
        vy = -self.power * math.sin(angle_rad)
        
        return Bullet(bx, by, vx, vy, self.turret_color)
    
    def _calc_firing_angle(self, target_x, target_y):
        """Calculate the firing angle to hit a target using ballistic physics.
        
        Uses the projectile motion equation to find the correct launch angle.
        """
        dx = target_x - self.x
        dy = self.y - target_y  # Positive = target is higher
        g = 0.15  # Gravity constant (must match Bullet.update)
        v = self.power
        
        # Ballistic equation: angle = atan((v^2 +/- sqrt(v^4 - g*(g*dx^2 + 2*dy*v^2))) / (g*dx))
        v2 = v * v
        v4 = v2 * v2
        discriminant = v4 - g * (g * dx * dx + 2 * dy * v2)
        
        if discriminant < 0:
            # Can't reach - increase power or use 45 degrees
            return 45 if self.facing_right else 135
        
        sqrt_disc = math.sqrt(discriminant)
        
        # Two solutions - pick the lower angle (flatter trajectory) for faster hits
        angle1 = math.degrees(math.atan2(v2 - sqrt_disc, g * abs(dx)))
        angle2 = math.degrees(math.atan2(v2 + sqrt_disc, g * abs(dx)))
        
        # Pick angle based on strategy
        if random.random() < 0.7:
            angle = angle1  # Flat shot (faster, more direct)
        else:
            angle = angle2  # High arc (lob shot)
        
        # Clamp to valid range
        angle = max(15, min(80, angle))
        
        # Mirror for left-facing tank
        if not self.facing_right or dx < 0:
            angle = 180 - angle
        
        return angle
    
    def ai_update(self, other_tank, terrain):
        """Smart AI: calculates trajectories, moves strategically, shoots accurately."""
        if self.health <= 0:
            return None
        
        self.cooldown = max(0, self.cooldown - 1)
        
        if other_tank.health <= 0:
            return None
        
        # Calculate distance to enemy
        dx = other_tank.x - self.x
        dist = abs(dx)
        
        # --- Movement AI ---
        # Move if too close or to get better angle
        if random.random() < 0.05:
            if dist < 15:
                # Too close - back away
                move_dir = -1 if dx > 0 else 1
            elif dist > 45:
                # Too far - get closer
                move_dir = 1 if dx > 0 else -1
            else:
                # Random repositioning
                move_dir = random.choice([-1, 1])
            
            new_x = self.x + move_dir * self.speed
            if 4 < new_x < WIDTH - 4:
                self.x = new_x
                self.place_on_terrain(terrain)
        
        # --- Aiming AI ---
        # Calculate proper firing solution
        self.power = max(2.5, min(5.5, dist * 0.1 + random.uniform(-0.3, 0.3)))
        target_angle = self._calc_firing_angle(other_tank.x, other_tank.y)
        
        # Smooth angle adjustment (faster than before)
        angle_diff = target_angle - self.angle
        if abs(angle_diff) > 1:
            self.angle += angle_diff * 0.3  # Converge quickly
        else:
            self.angle = target_angle
        
        # --- Shooting AI ---
        if self.cooldown <= 0:
            # Shoot when aim is close enough
            if abs(self.angle - target_angle) < 5:
                bullet = self.shoot()
                if bullet:
                    self.cooldown = 15 + random.randint(0, 10)  # Faster fire rate
                return bullet
        
        return None


def _generate_terrain():
    """Generate a random terrain heightmap."""
    terrain = [GROUND_Y] * WIDTH
    
    # Add some hills
    for _ in range(3):
        cx = random.randint(10, WIDTH - 10)
        h = random.randint(5, 15)
        w = random.randint(8, 20)
        for x in range(WIDTH):
            dist = abs(x - cx)
            if dist < w:
                bump = int(h * (1 - dist / w))
                terrain[x] = min(terrain[x], GROUND_Y - bump)
    
    # Smooth
    for _ in range(3):
        new_terrain = terrain[:]
        for x in range(1, WIDTH - 1):
            new_terrain[x] = (terrain[x - 1] + terrain[x] + terrain[x + 1]) // 3
        terrain = new_terrain
    
    return terrain


def _destroy_terrain(terrain, x, y, radius=4):
    """Create a crater in the terrain."""
    for tx in range(max(0, int(x) - radius), min(WIDTH, int(x) + radius)):
        dist = abs(tx - int(x))
        depth = int(radius - dist)
        if depth > 0:
            terrain[tx] = min(HEIGHT - 1, terrain[tx] + depth)


def run(matrix, duration=60):
    """Run the tank duel game."""
    start_time = time.time()
    
    terrain = _generate_terrain()
    
    tank1 = Tank(10, True, (50, 50, 200), (100, 100, 255))   # Blue
    tank2 = Tank(54, False, (200, 50, 50), (255, 100, 100))   # Red
    tank1.place_on_terrain(terrain)
    tank2.place_on_terrain(terrain)
    
    bullets = []
    explosions = []  # [(x, y, radius, timer)]
    scores = [0, 0]
    
    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            
            image = Image.new("RGB", (WIDTH, HEIGHT), (5, 5, 15))
            draw = ImageDraw.Draw(image)
            
            # Stars
            random.seed(99)
            for _ in range(15):
                draw.point((random.randint(0, WIDTH-1), random.randint(0, 20)), fill=(30, 30, 50))
            random.seed()
            
            # AI updates
            b1 = tank1.ai_update(tank2, terrain)
            b2 = tank2.ai_update(tank1, terrain)
            if b1:
                bullets.append(b1)
            if b2:
                bullets.append(b2)
            
            # Update bullets
            for bullet in bullets[:]:
                bullet.update()
                if not bullet.alive:
                    # Hit terrain - create explosion
                    _destroy_terrain(terrain, bullet.x, bullet.y)
                    explosions.append([bullet.x, bullet.y, 4, 6])
                    bullets.remove(bullet)
                    continue
                
                # Check terrain collision
                bx, by = int(bullet.x), int(bullet.y)
                if 0 <= bx < WIDTH and 0 <= by < HEIGHT and by >= terrain[bx]:
                    _destroy_terrain(terrain, bullet.x, bullet.y)
                    explosions.append([bullet.x, bullet.y, 4, 6])
                    bullets.remove(bullet)
                    continue
                
                # Check tank hits
                for tank, score_idx in [(tank1, 1), (tank2, 0)]:
                    if tank.health > 0 and abs(bullet.x - tank.x) < 3 and abs(bullet.y - tank.y) < 3:
                        tank.health -= 1
                        explosions.append([tank.x, tank.y, 5, 8])
                        if bullet in bullets:
                            bullets.remove(bullet)
                        if tank.health <= 0:
                            scores[score_idx] += 1
                            explosions.append([tank.x, tank.y, 8, 15])
                        break
            
            # Reset if both tanks dead
            if tank1.health <= 0 and tank2.health <= 0:
                time.sleep(1)
                terrain = _generate_terrain()
                tank1 = Tank(10, True, (50, 50, 200), (100, 100, 255))
                tank2 = Tank(54, False, (200, 50, 50), (255, 100, 100))
                tank1.place_on_terrain(terrain)
                tank2.place_on_terrain(terrain)
                bullets.clear()
            elif tank1.health <= 0 or tank2.health <= 0:
                # Respawn dead tank after delay
                dead = tank1 if tank1.health <= 0 else tank2
                if not any(e[3] > 0 for e in explosions):
                    dead.health = 3
                    dead.place_on_terrain(terrain)
            
            # Draw terrain
            for x in range(WIDTH):
                ty = terrain[x]
                if ty < HEIGHT:
                    # Grass top
                    draw.point((x, ty), fill=(30, 120, 30))
                    # Dirt below
                    for y in range(ty + 1, min(HEIGHT, ty + 8)):
                        draw.point((x, y), fill=(80, 50, 20))
                    for y in range(ty + 8, HEIGHT):
                        draw.point((x, y), fill=(60, 40, 15))
            
            # Draw tanks
            tank1.draw(draw)
            tank2.draw(draw)
            
            # Draw bullets
            for bullet in bullets:
                bx, by = int(bullet.x), int(bullet.y)
                if 0 <= bx < WIDTH and 0 <= by < HEIGHT:
                    draw.point((bx, by), fill=bullet.color)
            
            # Draw explosions
            for exp in explosions[:]:
                ex, ey, er, et = exp
                brightness = int(255 * et / max(exp[3], 1))
                for angle in range(0, 360, 30):
                    rad = math.radians(angle)
                    r = er * (1 - et / 15) if exp[3] > 8 else er
                    px = int(ex + r * math.cos(rad))
                    py = int(ey + r * math.sin(rad))
                    if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                        draw.point((px, py), fill=(brightness, brightness // 2, 0))
                exp[3] -= 1
                if exp[3] <= 0:
                    explosions.remove(exp)
            
            # Score display
            try:
                from PIL import ImageFont
                font = ImageFont.load_default()
                draw.text((1, 0), str(scores[0]), fill=(100, 100, 255), font=font)
                draw.text((WIDTH - 8, 0), str(scores[1]), fill=(255, 100, 100), font=font)
            except Exception:
                pass
            
            matrix.SetImage(image)
            
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    except Exception as e:
        logger.error("Error in tanks: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
