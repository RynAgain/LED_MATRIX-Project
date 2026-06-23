# Barricade (Quoridor-style) - LED Matrix Game Architecture

## Overview

A Quoridor-style grid race game adapted for the 64×64 LED matrix. Two players race pawns from opposite sides of a 9×9 grid to reach the other side. Each turn, a player either moves their pawn one step OR places a 2-cell wall to block the opponent. Walls cannot fully seal off a player's path.

## Game Rules

1. **Board**: 9×9 grid. P1 starts at bottom-center (row 8), P2 at top-center (row 0)
2. **Objective**: P1 races to row 0, P2 races to row 8
3. **Turn options**: MOVE pawn one step (up/down/left/right) OR PLACE a 2-cell wall
4. **Walls**: Each player has 10 walls. A wall spans 2 cells and sits in the gap between cells
5. **Wall constraint**: A placement is invalid if it completely blocks either player's path to goal (BFS validation)
6. **Pawn jumping**: If adjacent to opponent, you can jump over them
7. **Walls don't overlap**: No crossing or stacking

## Board Layout (64×64 pixels)

```
Cell size: 5×5 pixels
Gap between cells: 2px (where walls live)
Grid: 9 cells * 5px + 8 gaps * 2px = 61px
Offset: 2px margin -> fits perfectly in 64px

Board area: 61×61 pixels (with 2px offset)
Bottom row: wall count indicators + turn indicator
```

### Color Palette

| Element | Color | RGB |
|---------|-------|-----|
| Background | Black | (0, 0, 0) |
| Cells | Very dark blue | (8, 8, 16) |
| P1 pawn | Cyan | (0, 200, 255) |
| P2 pawn | Orange-red | (255, 100, 40) |
| Walls (placed) | Warm gold | (180, 140, 60) |
| Wall preview (valid) | Green | (80, 180, 40) |
| Wall preview (invalid) | Red | (180, 40, 40) |
| P1 goal row tint | Dark cyan | (0, 40, 60) |
| P2 goal row tint | Dark orange | (40, 20, 0) |
| Cursor | Bright green | (0, 255, 100) |
| Valid moves | Pulsing green | (0, 30-55, 0) |

## Data Model

```python
class BarricadeGame:
    pawns: dict[int, tuple[int, int]]       # player -> (row, col)
    walls_remaining: dict[int, int]         # player -> count (starts at 10)
    walls: set[tuple[tuple[int,int], str]]  # ((row,col), 'H'|'V')
    active_player: int                      # 0 or 1
```

### Wall Encoding

- `((r, c), 'H')`: Horizontal wall blocking vertical movement between rows r and r+1, spanning columns c and c+1
- `((r, c), 'V')`: Vertical wall blocking horizontal movement between columns c and c+1, spanning rows r and r+1

## AI Strategy

1. **BFS distance** to goal computed for both players
2. **Move** if we're farther from goal than opponent (close the gap)
3. **Place wall** if opponent is closer (probability-based):
   - Samples walls near opponent
   - Picks the one that maximally increases opponent's BFS distance
   - Only places if it increases distance by ≥1
4. **Move choice**: always toward shortest BFS path to goal
5. **Randomness**: ties broken randomly for variety

## Interactive Controls

| Mode | Input | Action |
|------|-------|--------|
| Move | D-pad | Move cursor over grid |
| Move | A | Move pawn to cursor (if valid) |
| Move | B | Switch to Wall mode |
| Wall | D-pad | Position wall on grid |
| Wall | A | Place wall (if valid) |
| Wall | B | Cancel (back to Move mode) |
| Wall | Select | Rotate wall H↔V |
| Any | Start+Select | Quit to menu |

## Module Structure

Single file: `src/display/barricade.py` (~500 lines)

### Key Components

| Name | Purpose |
|------|---------|
| `BarricadeGame` | Full game state, board, walls, validation |
| `BarricadeGame.can_move_between(r1,c1,r2,c2)` | Check wall blocking |
| `BarricadeGame.get_valid_moves(player)` | Adjacent moves + jumps |
| `BarricadeGame.is_wall_valid(pos, orient, player)` | Full validation including BFS path check |
| `BarricadeGame.draw(...)` | Render to 64×64 PIL Image |
| `_bfs_distance(game, start, goal_row)` | Shortest path length |
| `_ai_decide(game)` | AI move/wall decision |
| `_run_demo(matrix, duration, start_time)` | AI vs AI loop |
| `_run_interactive(matrix, controller, start_time)` | Player vs AI |
| `run(matrix, duration=60, controller=None)` | Entry point |

## Integration

- [`src/feature_registry.py`](src/feature_registry.py:50): `"barricade": "src.display.barricade"`
- [`src/app_state.py`](src/app_state.py:88): in `PLAYABLE_GAMES`
- [`src/menu/menu_data.py`](src/menu/menu_data.py:123): in `_GAME_LABELS` and `_GAME_ORDER`
- [`config/config.json`](config/config.json:219): in sequence as `"type": "game", "enabled": true`
