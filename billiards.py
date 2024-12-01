from rgbmatrix import RGBMatrix, RGBMatrixOptions, FrameCanvas
import math

# Constants
WIDTH, HEIGHT = 64, 64  # LED matrix dimensions
BALL_RADIUS = 2
POCKET_RADIUS = 3

# Colors
BLACK = (0, 0, 0)
GREEN = (0, 128, 0)
BLUE = (0, 0, 255)
WHITE = (255, 255, 255)

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

# Initialize matrix
options = RGBMatrixOptions()
options.rows = 64
options.cols = 64
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'regular'  # If you have an Adafruit HAT: 'adafruit-hat'
matrix = RGBMatrix(options=options)

# Create balls
balls = [Ball(WIDTH // 2, HEIGHT // 2, WHITE)]

# Pockets
pockets = [(0, 0), (WIDTH - 1, 0), (0, HEIGHT - 1), (WIDTH - 1, HEIGHT - 1)]

# Main game loop
running = True
while running:
    canvas = matrix.CreateFrameCanvas()
    canvas.Fill(*BLACK)

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
