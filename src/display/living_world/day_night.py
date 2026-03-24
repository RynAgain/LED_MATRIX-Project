"""Day/night cycle computation -- pure functions, no mutation."""

import math

from .constants import (
    DAY_CYCLE_SECONDS,
    SKY_NIGHT, SKY_DAWN_EARLY, SKY_DAWN_LATE, SKY_DAY,
    SKY_DUSK_EARLY, SKY_DUSK_LATE,
)
from .utils import _lerp_color, _cosine_interp


def _compute_day_phase(elapsed):
    return (elapsed % DAY_CYCLE_SECONDS) / DAY_CYCLE_SECONDS

def _compute_ambient(day_phase):
    p = day_phase
    if p < 0.125:
        t = p / 0.125
        return 0.15 + 0.85 * _cosine_interp(t)
    elif p < 0.5:
        return 1.0
    elif p < 0.625:
        t = (p - 0.5) / 0.125
        return 1.0 - 0.85 * _cosine_interp(t)
    else:
        return 0.15

def _get_day_cycle_phase(day_phase):
    if day_phase < 0.125:
        return "dawn"
    elif day_phase < 0.5:
        return "day"
    elif day_phase < 0.625:
        return "dusk"
    else:
        return "night"

def _compute_sky_colors(day_phase):
    p = day_phase
    if p < 0.0625:
        t = p / 0.0625
        return (_lerp_color(SKY_NIGHT[0], SKY_DAWN_EARLY[0], _cosine_interp(t)),
                _lerp_color(SKY_NIGHT[1], SKY_DAWN_EARLY[1], _cosine_interp(t)))
    elif p < 0.125:
        t = (p - 0.0625) / 0.0625
        return (_lerp_color(SKY_DAWN_EARLY[0], SKY_DAWN_LATE[0], _cosine_interp(t)),
                _lerp_color(SKY_DAWN_EARLY[1], SKY_DAWN_LATE[1], _cosine_interp(t)))
    elif p < 0.15:
        t = (p - 0.125) / 0.025
        return (_lerp_color(SKY_DAWN_LATE[0], SKY_DAY[0], _cosine_interp(t)),
                _lerp_color(SKY_DAWN_LATE[1], SKY_DAY[1], _cosine_interp(t)))
    elif p < 0.5:
        return SKY_DAY
    elif p < 0.5625:
        t = (p - 0.5) / 0.0625
        return (_lerp_color(SKY_DAY[0], SKY_DUSK_EARLY[0], _cosine_interp(t)),
                _lerp_color(SKY_DAY[1], SKY_DUSK_EARLY[1], _cosine_interp(t)))
    elif p < 0.625:
        t = (p - 0.5625) / 0.0625
        return (_lerp_color(SKY_DUSK_EARLY[0], SKY_DUSK_LATE[0], _cosine_interp(t)),
                _lerp_color(SKY_DUSK_EARLY[1], SKY_DUSK_LATE[1], _cosine_interp(t)))
    elif p < 0.67:
        t = (p - 0.625) / 0.045
        return (_lerp_color(SKY_DUSK_LATE[0], SKY_NIGHT[0], _cosine_interp(t)),
                _lerp_color(SKY_DUSK_LATE[1], SKY_NIGHT[1], _cosine_interp(t)))
    else:
        return SKY_NIGHT

def _seasonal_color_offset(day_phase):
    phase = _get_day_cycle_phase(day_phase)
    if phase == "dawn":
        return (10, 0, -5)
    elif phase == "day":
        return (0, 0, 0)
    elif phase == "dusk":
        return (15, 10, -15)
    else:
        return (-10, -10, 5)
