"""Low-poly Arwing and Corneria scenery for the 64-pixel rail shooter."""

import math


def draw_arwing(draw, x, y, angle, frame, boost=0.0, scale=1.0):
    cosine, sine = math.cos(angle), math.sin(angle)

    def point(px, py):
        return (round(x + (px * cosine - py * sine * 0.35) * scale),
                round(y + (py + px * sine * 0.55) * scale))

    for side in (-1, 1):
        exhaust = 4 + frame % 3 + int(boost * 5)
        draw.polygon([point(side * 4 - 1, 3), point(side * 4 + 1, 3),
                      point(side * 4, 3 + exhaust)], fill=(40, 110, 230))
        draw.line([point(side * 4, 3), point(side * 4, 5 + boost * 3)],
                  fill=(150, 235, 255))
        root = point(side * 2, -3)
        tip = point(side * 11, 2)
        heel = point(side * 4, 3)
        shade = (175, 197, 220) if side * sine < 0.2 else (95, 120, 165)
        draw.polygon([root, tip, heel], fill=shade)
        draw.line([root, tip], fill=(232, 241, 250))
        draw.polygon([point(side * 4, 0), point(side * 6, -4),
                      point(side * 7, 2)], fill=(45, 95, 205))
        draw.line([point(side * 4, 1), point(side * 4, 3)], fill=(220, 230, 240))
    draw.polygon([point(0, -7), point(-2, 1), point(0, 4)], fill=(230, 238, 248))
    draw.polygon([point(0, -7), point(2, 1), point(0, 4)], fill=(130, 156, 195))
    draw.line([point(0, -3), point(0, 0)], fill=(55, 180, 250))


def draw_corneria(draw, scroll, bank, width, height, horizon):
    center = width // 2
    for y in range(horizon + 1):
        t = y / horizon
        draw.line((0, y, width - 1, y),
                  fill=(int(12 + 40 * t), int(34 + 53 * t), int(80 + 40 * t)))
    draw.ellipse((46, 12, 51, 17), fill=(205, 216, 158))
    for layer, color in enumerate(((51, 89, 112), (41, 99, 83))):
        points = [(0, horizon)]
        for x in range(-8, width + 9, 8):
            ridge = math.sin(x * 0.12 + bank * 0.015 + layer * 2)
            points.append((x, horizon - 3 - int((ridge + 1) * (3 + layer))))
        points.append((width, horizon))
        draw.polygon(points, fill=color)

    vanish = center + bank * 0.25
    previous = None
    for y in range(horizon + 1, height):
        depth = (y - horizon) / (height - horizon)
        world_z = 2.0 / depth + scroll * 6
        color = (26, 71, 39) if int(world_z * 0.35) % 2 else (32, 83, 44)
        shade = 0.5 + depth * 0.5
        draw.line((0, y, width - 1, y), fill=tuple(int(c * shade) for c in color))
        river = vanish + math.sin(world_z * 0.08) * 13 * depth - 13 * depth
        river_width = 1 + 7 * depth
        draw.line((river - river_width, y, river + river_width, y), fill=(29, 91, 130))
        draw.point((int(river - river_width), y), fill=(77, 125, 96))
        road = vanish + 19 * depth
        draw.line((road - 3 * depth, y, road + 3 * depth, y), fill=(83, 89, 85))
        if int(world_z) % 4 == 0:
            draw.point((int(road), y), fill=(173, 179, 134))
        if previous and int(world_z * 0.35) != previous:
            draw.line((0, y, max(0, river - river_width - 1), y), fill=(42, 91, 48))
        previous = int(world_z * 0.35)

    # Scenery stays outside the flight corridor; collision pylons are separate.
    structures = []
    for index in range(10):
        z = 1.0 + (index * 2.1 - scroll * 2.6) % 21
        side = -1 if index % 2 else 1
        factor = 30 / z
        x = vanish + side * (5.5 + index % 3) * factor
        base = horizon + 3.4 * factor
        structures.append((z, x, base, factor, index))
    for z, x, base, factor, index in sorted(structures, reverse=True):
        if x < -12 or x > width + 12:
            continue
        half = max(1, int(factor * 0.6))
        top = base - factor * (1.5 + index % 3 * 0.7)
        draw.polygon([(x - half, base), (x - half, top), (x, top - half),
                      (x + half, top), (x + half, base)], fill=(121, 147, 149))
        draw.polygon([(x, top), (x + half, top), (x + half, base),
                      (x, base)], fill=(68, 95, 111))
        draw.line((x - half, top, x, top - half, x + half, top), fill=(185, 198, 176))
