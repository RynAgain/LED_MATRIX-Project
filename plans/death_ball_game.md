# Death Ball - LED Matrix Game Architecture

## Overview
for my love of deathball
A DeathBall-inspired 2D wizard soccer platformer for the 64×64 LED matrix. Two wizards jump and platform around a small arena, kicking a magical ball into the opponent's goal. Features double-jump, magic blast (redirects ball), and increasing intensity.

## Core Mechanics

1. **Movement**: Left/right walk + double-jump (platforming)
2. **Kick**: When touching the ball, wizard kicks it in facing direction
3. **Magic Blast**: Area-of-effect explosion that pushes the ball away from wizard (costs mana, recharges)
4. **Goal**: Ball entering opponent's goal zone scores a point
5. **Sudden Death**: After time runs out, ball speed doubles, next goal wins

## Arena Layout (64×64)

```
Score: 2        Score: 1
|============CEILING============|
|                               |
|GOAL|                     |GOAL|
|ZONE|    [platforms]      |ZONE|
|    |                     |    |
|    |  [W1]  (ball) [W2]  |    |
|    |     [platform]      |    |
|GOAL|                     |GOAL|
|ZONE|                     |ZONE|
|================================|
         FLOOR
```

### Pixel Layout

| Element | Position | Size |
|---------|----------|------|
| Arena bounds | full 64×64 | 1px walls |
| Floor | y=60-63 | 4px tall (textured) |
| Ceiling | y=0-1 | 2px |
| Left goal zone | x=0-4, y=20-44 | 5×25 px opening |
| Right goal zone | x=59-63, y=20-44 | 5×25 px opening |
| Platform (center) | x=22-41, y=40 | 20×2 px |
| Platform (upper-left) | x=8-20, y=28 | 13×2 px |
| Platform (upper-right) | x=43-55, y=28 | 13×2 px |
| Platform (top-center) | x=26-37, y=16 | 12×2 px |
| Wizard sprite | - | 3×5 px |
| Ball | - | 3×3 px |

### Goals

Goals are open sections in the side walls. The ball passing through = point scored. Goal zones have a colored glow (dim pulse matching player color).

## Physics

### Wizard Physics
- **Gravity**: 0.4 px/frame downward
- **Walk speed**: 1.5 px/frame
- **Jump velocity**: -3.5 px/frame (initial upward)
- **Double jump**: second jump at -3.0 (slightly weaker)
- **Air control**: 70% of ground walk speed while airborne
- **Platform collision**: land on top only (pass through from below)

### Ball Physics
- **Gravity**: 0.25 px/frame (lighter than wizard)
- **Bounce coefficient**: 0.7 (off walls/floor/ceiling)
- **Friction**: 0.98 per frame (slight air drag)
- **Max speed**: 5.0 px/frame (capped)
- **Kick velocity**: 3.5 in facing direction + upward angle
- **Magic blast**: pushes ball 4.0 away from wizard center

### Collision
- Wizard-ball: if within 4px, wizard "has possession" and next kick input launches it
- Ball-wall: bounce with coefficient
- Ball-goal: if ball center enters goal zone, score point
- Wizard-platform: one-way (land on top, pass through below/sides)

## Scoring & Timing

| Phase | Duration | Rule |
|-------|----------|------|
| Normal play | 60 seconds | First to 3 wins, or... |
| Sudden death | after 60s if tied | Ball speed ×2, next goal wins |
| Round reset | 1.5s pause | Ball respawns center, wizards reset |

Score shown at top: P1 left, P2 right (small 3×5 digit font).

## Visual Effects

| Effect | Description |
|--------|-------------|
| Ball trail | Last 4 positions drawn with fading brightness |
| Magic blast | Expanding ring of particles (4 frames) |
| Goal scored | Flash goal zone white, brief screen shake |
| Sudden death | Arena walls pulse red, ball glows brighter |
| Wizard jump | Small dust particles below on launch |
| Ball kick | Directional spark particles |
| Ball glow | Ball pulses brightness based on speed |

## Color Palette

| Element | RGB |
|---------|-----|
| Background | (0, 0, 0) |
| Arena walls | (40, 40, 60) |
| Floor | (50, 50, 70) |
| Platforms | (60, 50, 80) |
| Wizard 1 | (80, 150, 255) - blue wizard |
| Wizard 2 | (255, 80, 150) - pink/red wizard |
| Ball | (255, 220, 50) - golden orb |
| Ball trail | fading gold |
| Goal zone P1 | dim blue pulse (20, 40, 80) |
| Goal zone P2 | dim red pulse (80, 20, 40) |
| Magic blast | (200, 100, 255) - purple explosion |
| Score text | (255, 255, 255) |
| Sudden death glow | (255, 40, 40) pulsing walls |
| Mana bar | (100, 200, 255) -> (40, 60, 80) when empty |

## Controls (Interactive Mode)

| Input | Action |
|-------|--------|
| LEFT/RIGHT | Move wizard horizontally |
| UP or A | Jump (press again in air for double-jump) |
| B | Magic blast (if mana available) |
| DOWN | Fast-fall (accelerate downward) |
| Start+Select | Quit to menu |

### Mana System
- Blast costs 50 mana
- Max mana: 100
- Recharge rate: 2/frame
- Visual: tiny bar below wizard or at screen edge

## AI Design (Demo Mode)

### AI Priorities (evaluated each frame):
1. **If ball near own goal**: rush to defend (intercept ball)
2. **If ball near opponent goal**: push advantage, kick toward goal
3. **If has possession**: aim kick toward opponent's goal
4. **If ball high**: jump to reach it
5. **Use blast strategically**: when ball is heading toward own goal at high speed

### AI Personality Variation:
- Slight reaction delay (3-5 frames) to feel human
- Occasional missed blast timing
- Varied aggression: sometimes plays defensive, sometimes rushes

## Demo Mode
- AI vs AI with both sides playing competitively
- Matches reset on win (brief "P1 WINS" or "P2 WINS" banner)
- Very visually dynamic: fast ball, jumps, blasts, goals

## Interactive Mode
- Player controls Wizard 1 (left/blue)
- AI controls Wizard 2 (right/pink)
- First to 3 goals wins
- "YOU WIN!" or "YOU LOSE" banner

## Module Structure

```
src/display/death_ball.py    # Single file (~600-700 lines)
```

### Key Classes

| Class | Purpose |
|-------|---------|
| `Wizard` | Position, velocity, facing, jump state, mana |
| `Ball` | Position, velocity, trail history, speed glow |
| `Arena` | Platform positions, goal zones, bounds |
| `DeathBallGame` | Full game state, physics, scoring, timer |
| `Particle` | Brief visual effect (sparks, dust, blast ring) |

## Integration

- Feature registry: `"death_ball": "src.display.death_ball"`
- PLAYABLE_GAMES: add `"death_ball"`
- Menu label: `"DEATHBALL"`
- Config sequence: `{"name": "death_ball", "type": "game", "enabled": true}`
