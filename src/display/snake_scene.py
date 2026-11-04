"""Pillow-only third-person rendering for the 64x64 Snake display."""

import math

from PIL import Image, ImageDraw

from src.display._utils import _draw_number, _lerp_color, _scale_color

SIZE = 64
NEAR = 0.5
HEAD_COLOR = (220, 255, 235)
BODY_COLOR = (30, 235, 85)
TAIL_COLOR = (10, 90, 45)
FOOD_RED = (255, 55, 35)
FOOD_GOLD = (255, 215, 0)
DEATH_COLOR = (230, 35, 25)


class ChaseCamera:
    def __init__(self, head, direction):
        self.head = head
        self.forward = direction
        self.right = (-direction[1], direction[0])

    def transform(self, point):
        x, height, z = point
        x -= self.head[0]
        z -= self.head[1]
        side = x * self.right[0] + z * self.right[1]
        forward = x * self.forward[0] + z * self.forward[1] + 6.0
        height -= 5.0
        return side, height * 0.94 + forward * 0.342, forward * 0.94 - height * 0.342

    def project(self, point):
        point = self.transform(point)
        return _perspective(point) if point[2] >= NEAR else None


def _perspective(point):
    x, y, depth = point
    return (32 + 40 * x / depth, 26 - 40 * y / depth)


def _intersection(a, b):
    fraction = (NEAR - a[2]) / (b[2] - a[2])
    return (a[0] + fraction * (b[0] - a[0]),
            a[1] + fraction * (b[1] - a[1]), NEAR)


def _clip_polygon(points):
    clipped = []
    previous = points[-1]
    for point in points:
        if (point[2] >= NEAR) != (previous[2] >= NEAR):
            clipped.append(_intersection(previous, point))
        if point[2] >= NEAR:
            clipped.append(point)
        previous = point
    return clipped


def _line(draw, camera, a, b, color):
    a, b = camera.transform(a), camera.transform(b)
    if a[2] < NEAR and b[2] < NEAR:
        return
    if a[2] < NEAR:
        a = _intersection(a, b)
    elif b[2] < NEAR:
        b = _intersection(b, a)
    draw.line([_perspective(a), _perspective(b)], fill=color)


def _ground(draw, camera, board_size):
    low, high = -0.5, board_size - 0.5
    for cell in range(0, board_size, 2):
        edge = cell - 0.5
        _line(draw, camera, (low, 0, edge), (high, 0, edge), (16, 47, 57))
        _line(draw, camera, (edge, 0, low), (edge, 0, high), (16, 47, 57))
    corners = [(low, 0, low), (high, 0, low), (high, 0, high), (low, 0, high)]
    for a, b in zip(corners, corners[1:] + corners[:1]):
        _line(draw, camera, a, b, (245, 70, 50))


def _cube_faces(camera, position, color, height=0.7, radius=0.46):
    x, z = position
    vertices = [camera.transform((x + dx * radius, y, z + dz * radius))
                for y in (0.04, height)
                for dx, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    faces = []
    for indices, light in (((0, 1, 5, 4), 0.55), ((1, 2, 6, 5), 0.7),
                           ((2, 3, 7, 6), 0.65), ((3, 0, 4, 7), 0.8),
                           ((4, 5, 6, 7), 1.0)):
        points = _clip_polygon([vertices[i] for i in indices])
        if len(points) < 3:
            continue
        depth = sum(p[2] for p in points) / len(points)
        fog = max(0.35, min(1.0, 16.0 / max(depth, NEAR)))
        faces.append((depth, [_perspective(p) for p in points], _scale_color(color, light * fog)))
    return faces


def _overview(image, draw, game, board_size):
    draw.rectangle((46, 0, 63, 17), fill=(3, 8, 15), outline=(65, 100, 110))

    def point(position):
        return (47 + min(15, int(position[0] * 16 / board_size)),
                1 + min(15, int(position[1] * 16 / board_size)))

    for segment in reversed(game.snake[1:]):
        image.putpixel(point(segment), BODY_COLOR)
    hx, hy = point(game.snake[0])
    dx, dy = game.direction
    draw.line((hx, hy, max(47, min(62, hx + dx * 2)), max(1, min(16, hy + dy * 2))),
              fill=HEAD_COLOR)
    if game.food is not None:
        image.putpixel(point(game.food), FOOD_GOLD if game.food_is_gold else FOOD_RED)


def render(game, pulse_phase=0.0, red_count=0, board_size=SIZE):
    image = Image.new("RGB", (SIZE, SIZE), (5, 12, 22))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 12, 63, 63), fill=(5, 20, 25))
    draw.line((0, 11, 63, 11), fill=(30, 65, 80))
    camera = ChaseCamera(game.snake[0], game.direction)
    _ground(draw, camera, board_size)
    faces = []
    for index, segment in enumerate(game.snake):
        color = HEAD_COLOR if index == 0 else _lerp_color(
            BODY_COLOR, TAIL_COLOR, index / max(1, len(game.snake) - 1))
        if index < red_count:
            color = DEATH_COLOR
        faces.extend(_cube_faces(camera, segment, color))
    if game.food is not None:
        color = FOOD_GOLD if game.food_is_gold else FOOD_RED
        color = _scale_color(color, 0.75 + 0.25 * math.sin(pulse_phase))
        faces.extend(_cube_faces(camera, game.food, color, height=1.2, radius=0.35))
    for _, points, color in sorted(faces, key=lambda face: face[0], reverse=True):
        draw.polygon(points, fill=color)
    draw.rectangle((0, 0, 44, 7), fill=(3, 8, 15))
    _draw_number(image, game.score, 1, 1, HEAD_COLOR)
    _overview(image, draw, game, board_size)
    return image
