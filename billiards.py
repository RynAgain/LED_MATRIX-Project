from rgbmatrix import RGBMatrix, RGBMatrixOptions, FrameCanvas
import math
import random

# Constants
WIDTH, HEIGHT = 64, 64  # LED matrix dimensions
BALL_RADIUS = 2
POCKET_RADIUS = 3
FRICTION = 0.99
AI_STRENGTH_MIN = 0.5
AI_STRENGTH_MAX = 1.5

# Colors
BLACK = (0, 0, 0)
GREEN = (0, 128, 0)
BLUE = (0, 0, 255)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)

# Ball class
class Ball:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color
        self.vx = 0
        self.vy = 0

    def draw(self, canvas):
        for dx in range(-BALL_RADIUS, BALL_RADIUS + 1):
            for dy in range(-BALL_RADIUS, BALL_RADIUS + 1):
                if dx**2 + dy**2 <= BALL_RADIUS**2:
                    canvas.SetPixel(self.x + dx, self.y + dy, *self.color)

    def move(self):
        # Update position with velocity
        self.x += self.vx
        self.y += self.vy

        # Apply friction
        self.vx *= FRICTION
        self.vy *= FRICTION

        # Boundary conditions
        if self.x < BALL_RADIUS:
            self.x = BALL_RADIUS
            self.vx = -self.vx
        elif self.x > WIDTH - BALL_RADIUS:
            self.x = WIDTH - BALL_RADIUS
            self.vx = -self.vx

        if self.y < BALL_RADIUS:
            self.y = BALL_RADIUS
            self.vy = -self.vy
        elif self.y > HEIGHT - BALL_RADIUS:
            self.y = HEIGHT - BALL_RADIUS
            self.vy = -self.vy

    def check_collision(self, other):
        dx = self.x - other.x
        dy = self.y - other.y
        distance = math.hypot(dx, dy)
        if distance < 2 * BALL_RADIUS:
            angle = math.atan2(dy, dx)
            total_vx = self.vx + other.vx
            total_vy = self.vy + other.vy
            self.vx = total_vx * math.cos(angle)
            self.vy = total_vy * math.sin(angle)
            other.vx = total_vx * -math.cos(angle)
            other.vy = total_vy * -math.sin(angle)

    def is_in_pocket(self, pockets):
        for pocket in pockets:
            if math.hypot(self.x - pocket[0], self.y - pocket[1]) <= POCKET_RADIUS:
                return True
        return False

def ai_play(balls):
    cue_ball = balls[0]
    target_ball = min(balls[1:], key=lambda b: math.hypot(cue_ball.x - b.x, cue_ball.y - b.y))
    dx = target_ball.x - cue_ball.x
    dy = target_ball.y - cue_ball.y
    angle = math.atan2(dy, dx)
    strength = random.uniform(AI_STRENGTH_MIN, AI_STRENGTH_MAX)
    cue_ball.vx = math.cos(angle) * strength
    cue_ball.vy = math.sin(angle) * strength

def draw_table_edges(canvas):
    for x in range(WIDTH):
        canvas.SetPixel(x, 0, *GREEN)
        canvas.SetPixel(x, HEIGHT - 1, *GREEN)
    for y in range(HEIGHT):
        canvas.SetPixel(0, y, *GREEN)
        canvas.SetPixel(WIDTH - 1, y, *GREEN)

def draw_pockets(canvas, pockets):
    for pocket in pockets:
        for dx in range(-POCKET_RADIUS, POCKET_RADIUS + 1):
            for dy in range(-POCKET_RADIUS, POCKET_RADIUS + 1):
                if dx**2 + dy**2 <= POCKET_RADIUS**2:
                    canvas.SetPixel(pocket[0] + dx, pocket[1] + dy, *BLUE)

def main(matrix):
    canvas = matrix.CreateFrameCanvas()
    balls = [
        Ball(WIDTH // 2, HEIGHT // 2, WHITE),  # Cue ball
        Ball(WIDTH // 4, HEIGHT // 4, RED),
        Ball(3 * WIDTH // 4, HEIGHT // 4, YELLOW),
        Ball(WIDTH // 4, 3 * HEIGHT // 4, BLUE),
        Ball(3 * WIDTH // 4, 3 * HEIGHT // 4, GREEN)
    ]
    pockets = [(0, 0), (WIDTH - 1, 0), (0, HEIGHT - 1), (WIDTH - 1, HEIGHT - 1)]

    running = True
    while running:
        canvas.Fill(*BLACK)
        ai_play(balls)
        draw_table_edges(canvas)
        draw_pockets(canvas, pockets)

        for ball in balls:
            if ball.is_in_pocket(pockets):
                ball.vx = 0
                ball.vy = 0
            ball.move()
            ball.draw(canvas)

        for i, ball in enumerate(balls):
            for other in balls[i+1:]:
                ball.check_collision(other)

        canvas = matrix.SwapOnVSync(canvas)
