"""Regression tests for Rubik's cube state (src/display/rubiks_cube.py).

Bug history: apply_move used hand-written per-face edge cycles (commented
"simplified") that were wrong for several faces, producing impossible
sticker states.  Moves are now geometry-derived permutations (TURN_PERMS);
these tests pin the group-theoretic invariants a real cube obeys.
"""
import itertools
import math
import random

import pytest

from src.display.rubiks_cube import (
    RubiksCube, FACE_DEFS, TURN_PERMS, _sticker_center, _turn_rot90)

FACES = list(FACE_DEFS.keys())
MOVES = [(f, cw) for f in FACES for cw in (True, False)]


def flatten(cube):
    return tuple(cube.faces[f][r][c]
                 for f in FACES for r in range(3) for c in range(3))


def solved_cubies():
    """Set of frozensets of sticker colors per physical cubie of the
    solved cube, keyed by which cubie (corner/edge) they sit on."""
    by_cubie = {}
    for fname, fdef in FACE_DEFS.items():
        for r in range(3):
            for c in range(3):
                center = _sticker_center(fdef, r, c)
                # Cubie position: clamp each coord to {-2,0,2} -> the small
                # cube this sticker is glued to.
                cubie = tuple(max(-2, min(2, v)) for v in center)
                by_cubie.setdefault(cubie, []).append(fname)
    return by_cubie


def cubie_multiset(cube):
    """Multiset of color-tuples per physical cubie for a cube state."""
    by_cubie = {}
    for fname, fdef in FACE_DEFS.items():
        for r in range(3):
            for c in range(3):
                center = _sticker_center(fdef, r, c)
                cubie = tuple(max(-2, min(2, v)) for v in center)
                by_cubie.setdefault(cubie, []).append(cube.faces[fname][r][c])
    return sorted(tuple(sorted(v)) for v in by_cubie.values())


SOLVED_CUBIES = None


def setup_module():
    global SOLVED_CUBIES
    SOLVED_CUBIES = cubie_multiset(RubiksCube())


def test_perm_tables_are_bijections():
    for (face, cw), mapping in TURN_PERMS.items():
        assert len(mapping) == 21, (face, cw)
        assert len(set(mapping.values())) == 21, (face, cw)
        # dst and src slot sets are identical (layer maps onto itself)
        assert set(mapping.keys()) == set(mapping.values()), (face, cw)


@pytest.mark.parametrize("face,cw", MOVES)
def test_move_preserves_color_counts(face, cw):
    cube = RubiksCube()
    cube.apply_move(face, cw)
    flat = flatten(cube)
    for color in FACES:
        assert flat.count(color) == 9


@pytest.mark.parametrize("face", FACES)
def test_move_then_inverse_is_identity(face):
    cube = RubiksCube()
    before = flatten(cube)
    cube.apply_move(face, True)
    assert flatten(cube) != before  # the move must actually do something
    cube.apply_move(face, False)
    assert flatten(cube) == before


@pytest.mark.parametrize("face,cw", MOVES)
def test_quarter_turn_has_order_four(face, cw):
    cube = RubiksCube()
    before = flatten(cube)
    seen = []
    for _ in range(4):
        cube.apply_move(face, cw)
        seen.append(flatten(cube))
    assert seen[-1] == before
    assert len(set(seen[:3])) == 3  # intermediate states all distinct


def test_scramble_then_reverse_returns_to_solved():
    random.seed(7)
    cube = RubiksCube()
    before = flatten(cube)
    moves = [(random.choice(FACES), random.choice([True, False]))
             for _ in range(40)]
    for f, cw in moves:
        cube.apply_move(f, cw)
    for f, cw in reversed(moves):
        cube.apply_move(f, not cw)
    assert flatten(cube) == before


def test_centers_never_move():
    random.seed(3)
    cube = RubiksCube()
    for _ in range(50):
        cube.apply_move(random.choice(FACES), random.choice([True, False]))
    for f in FACES:
        assert cube.faces[f][1][1] == f


def test_cubie_integrity_after_scramble():
    """THE impossible-state test: every corner triple and edge pair must
    remain a valid physical cubie of the solved cube.  The old hand-rolled
    cycles failed this (stickers migrated between cubies)."""
    random.seed(11)
    cube = RubiksCube()
    for _ in range(100):
        cube.apply_move(random.choice(FACES), random.choice([True, False]))
    assert cubie_multiset(cube) == SOLVED_CUBIES


def test_demo_cycle_returns_to_solved():
    """Drive update() through a full scramble+solve cycle and confirm the
    cube ends solved (the demo's solve replays history reversed)."""
    random.seed(5)
    cube = RubiksCube()
    before = flatten(cube)
    for _ in range(24 * 120):  # plenty of frames for a full cycle
        cube.update()
        if cube.mode == 'rotate' and cube.mode_timer == 1:
            break
    assert cube.mode == 'rotate'
    assert flatten(cube) == before


def test_turning_slice_is_rendered_rotated():
    """The turn animation must actually move sticker quads (previously the
    animation state was ignored by the renderer and stickers teleported)."""
    cube = RubiksCube()
    base = {i: q[0] for i, q in enumerate(cube.get_sticker_quads())}
    cube.turning_face = 'U'
    cube.turning_cw = True
    cube.turn_angle = math.pi / 4
    moved = 0
    for i, (corners, _c) in enumerate(cube.get_sticker_quads()):
        if any(math.dist(a, b) > 1e-6 for a, b in zip(corners, base[i])):
            moved += 1
    assert moved == 21  # 9 U-face stickers + 12 band stickers, nothing else


def test_animation_end_matches_state_snap():
    """At turn_angle = 90 deg the animated slice must occupy exactly the
    slots the permutation writes to -- no visual pop on completion."""
    cube = RubiksCube()
    cube.turning_face = 'F'
    cube.turning_cw = True
    cube.turn_angle = math.pi / 2
    animated = cube.get_sticker_quads()

    snapped = RubiksCube()
    snapped.apply_move('F', True)
    final = snapped.get_sticker_quads()

    def keyed(quads):
        # center of quad -> color, with rounding to kill float noise
        out = {}
        for corners, color in quads:
            cx = round(sum(p[0] for p in corners) / 4, 6)
            cy = round(sum(p[1] for p in corners) / 4, 6)
            cz = round(sum(p[2] for p in corners) / 4, 6)
            out[(cx, cy, cz)] = color
        return out

    assert keyed(animated) == keyed(final)
