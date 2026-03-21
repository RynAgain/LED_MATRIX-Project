#!/usr/bin/env python3
"""Conway's Game of Life for 64x64 LED matrix."""

import time
import random
import logging
from PIL import Image

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 10  # Slower to appreciate the patterns


def _random_grid(density=0.3):
    """Create a random initial state."""
    return [[1 if random.random() < density else 0 for _ in range(WIDTH)] for _ in range(HEIGHT)]


def _count_neighbors(grid, x, y):
    """Count live neighbors (wrapping at edges)."""
    count = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx = (x + dx) % WIDTH
            ny = (y + dy) % HEIGHT
            count += grid[ny][nx]
    return count


def _next_generation(grid):
    """Compute the next generation."""
    new_grid = [[0] * WIDTH for _ in range(HEIGHT)]
    for y in range(HEIGHT):
        for x in range(WIDTH):
            neighbors = _count_neighbors(grid, x, y)
            if grid[y][x]:
                # Alive: survive with 2 or 3 neighbors
                new_grid[y][x] = 1 if neighbors in (2, 3) else 0
            else:
                # Dead: born with exactly 3 neighbors
                new_grid[y][x] = 1 if neighbors == 3 else 0
    return new_grid


def _grid_to_image(grid, age_map):
    """Convert grid to colored image. Older cells are warmer colors."""
    image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    pixels = image.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if grid[y][x]:
                age = min(age_map[y][x], 50)
                # Young cells are cyan, aging cells turn green, old cells are yellow
                if age < 5:
                    pixels[x, y] = (0, 200, 255)
                elif age < 15:
                    pixels[x, y] = (0, 255, 100)
                elif age < 30:
                    pixels[x, y] = (200, 255, 0)
                else:
                    pixels[x, y] = (255, 200, 0)
    return image


def run(matrix, duration=60):
    """Run the Game of Life for the specified duration."""
    start_time = time.time()
    grid = _random_grid(0.35)
    age_map = [[0] * WIDTH for _ in range(HEIGHT)]
    stale_count = 0
    prev_alive = -1
    
    try:
        while time.time() - start_time < duration:
            frame_start = time.time()
            
            # Render
            image = _grid_to_image(grid, age_map)
            matrix.SetImage(image)
            
            # Update
            new_grid = _next_generation(grid)
            
            # Update age map
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    if new_grid[y][x]:
                        age_map[y][x] += 1
                    else:
                        age_map[y][x] = 0
            
            # Detect stale states and reset
            alive = sum(sum(row) for row in new_grid)
            if alive == prev_alive:
                stale_count += 1
            else:
                stale_count = 0
            prev_alive = alive
            
            if stale_count > 30 or alive < 10:
                # Inject some random life
                for _ in range(WIDTH * HEIGHT // 4):
                    x = random.randint(0, WIDTH - 1)
                    y = random.randint(0, HEIGHT - 1)
                    new_grid[y][x] = 1
                    age_map[y][x] = 0
                stale_count = 0
            
            grid = new_grid
            
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    except Exception as e:
        logger.error("Error in Game of Life: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
