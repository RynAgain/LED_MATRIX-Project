"""Single-stone pressure plate, solved through legal pushes rather than scripted movement."""
from collections import deque

from .game import DIRECTIONS


STONE_START = (4, 10)
STONE_PLATE = (7, 10)


def walking_route(start, goal, stone, passable):
    queue = deque([(start, [])])
    seen = {start}
    while queue:
        cell, route = queue.popleft()
        if cell == goal:
            return route
        for dx, dy in DIRECTIONS:
            neighbor = cell[0] + dx, cell[1] + dy
            if neighbor not in seen and neighbor != stone and passable(neighbor):
                seen.add(neighbor)
                queue.append((neighbor, route + [neighbor]))
    return None


def next_stone_action(hero, stone, plate, passable):
    queue = deque([(hero, stone, None)])
    seen = {(hero, stone)}
    while queue:
        current, block, first_action = queue.popleft()
        if block == plate:
            return first_action
        for dx, dy in DIRECTIONS:
            behind = block[0] - dx, block[1] - dy
            ahead = block[0] + dx, block[1] + dy
            if not passable(ahead):
                continue
            route = walking_route(current, behind, block, passable)
            if route is None:
                continue
            state = block, ahead
            if state in seen:
                continue
            seen.add(state)
            action = first_action or (("walk", route[0]) if route else ("push", ahead))
            queue.append((block, ahead, action))
    return None
