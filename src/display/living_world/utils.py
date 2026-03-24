"""Pure utility functions with no side effects."""

import math


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)

def _lerp_color(c1, c2, t):
    return (int(c1[0]+(c2[0]-c1[0])*t), int(c1[1]+(c2[1]-c1[1])*t), int(c1[2]+(c2[2]-c1[2])*t))

def _cosine_interp(t):
    return (1 - math.cos(t * math.pi)) / 2

def _apply_ambient(color, factor):
    return (_clamp(int(color[0]*factor),0,255), _clamp(int(color[1]*factor),0,255), _clamp(int(color[2]*factor),0,255))
