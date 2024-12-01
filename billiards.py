from rgbmatrix import RGBMatrix, RGBMatrixOptions, FrameCanvas
import math
import random

# Constants
WIDTH, HEIGHT = 64, 64  # LED matrix dimensions
BALL_RADIUS = 2
POCKET_RADIUS = 3

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
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.99  # Friction
        self.vy *= 0.99

    def check_collision(self, other):
        dx = self.x - other.x
        dy = self.y - other.y
        distance = math.hypot(dx, dy)
        if distance < 2 * BALL_RADIUS:
            angle = math.atan2(dy, dx)
            self.vx, self.vy = -math.cos(angle), -math.sin(angle)
            other.vx, other.vy = math.cos(angle), math.sin(angle)

def ai_play(balls):
    # Simple AI to hit the cue ball towards a random direction
    cue_ball = balls[0]
    angle = random.uniform(0, 2 * math.pi)
    strength = random.uniform(0.5, 1.5)
    cue_ball.vx = math.cos(angle) * strength
    cue_ball.vy = math.sin(angle) * strength

def main(matrix):
    # Create an offscreen canvas
    canvas = matrix.CreateFrameCanvas()

    # Create balls
    balls = [
        Ball(WIDTH // 2, HEIGHT // 2, WHITE),  # Cue ball
        Ball(WIDTH // 4, HEIGHT // 4, RED),
        Ball(3 * WIDTH // 4, HEIGHT // 4, YELLOW),
        Ball(WIDTH // 4, 3 * HEIGHT // 4, BLUE),
        Ball(3 * WIDTH // 4, 3 * HEIGHT // 4, GREEN)
    ]

    # Pockets
    pockets = [(0, 0), (WIDTH - 1, 0), (0, HEIGHT - 1), (WIDTH - 1, HEIGHT - 1)]

    # Main game loop
    running = True
    while running:
        canvas.Fill(*BLACK)

        # AI makes a move
        ai_play(balls)

        # Draw table edges
        for x in range(WIDTH):
            canvas.SetPixel(x, 0, *GREEN)
            canvas.SetPixel(x, HEIGHT - 1, *GREEN)
        for y in range(HEIGHT):
            canvas.SetPixel(0, y, *GREEN)
            canvas.SetPixel(WIDTH - 1, y, *GREEN)

        # Draw pockets
        for pocket in pockets:
            for dx in range(-POCKET_RADIUS, POCKET_RADIUS + 1):
                for dy in range(-POCKET_RADIUS, POCKET_RADIUS + 1):
                    if dx**2 + dy**2 <= POCKET_RADIUS**2:
                        canvas.SetPixel(pocket[0] + dx, pocket[1] + dy, *BLUE)

        # Move and draw balls
        for ball in balls:
            ball.move()
            ball.draw(canvas)

        # Check collisions
        for i, ball in enumerate(balls):
            for other in balls[i+1:]:
                ball.check_collision(other)

        canvas = matrix.SwapOnVSync(canvas)