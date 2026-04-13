"""Day/night cycle computation -- pure functions, no mutation."""

import math

from .constants import (
    DAY_CYCLE_SECONDS,
    SKY_NIGHT, SKY_DAWN_EARLY, SKY_DAWN_LATE, SKY_DAY,
    SKY_DUSK_EARLY, SKY_DUSK_LATE,
    SEASON_CYCLE_DAYS, SEASONS,
    MOON_CYCLE_DAYS, MOON_PHASES,
    SOLAR_ECLIPSE_PERIOD, SOLAR_ECLIPSE_DURATION,
    LUNAR_ECLIPSE_PERIOD, LUNAR_ECLIPSE_DURATION,
    ECLIPSE_AMBIENT_MIN,
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


def _compute_season(elapsed):
    """Return the current season name for a given elapsed time."""
    full_cycle = SEASON_CYCLE_DAYS * DAY_CYCLE_SECONDS
    time_in_cycle = elapsed % full_cycle
    season_index = int(time_in_cycle / DAY_CYCLE_SECONDS) % 4
    return SEASONS[season_index]


def _compute_season_transition(elapsed):
    """Return (current_season, next_season, blend_factor) for smooth transitions.

    blend_factor 0.0 = fully current, 1.0 = fully next.
    Transition happens in the last 10% of each season period.
    """
    full_cycle = SEASON_CYCLE_DAYS * DAY_CYCLE_SECONDS
    season_length = DAY_CYCLE_SECONDS
    time_in_cycle = elapsed % full_cycle
    season_index = int(time_in_cycle / season_length) % 4
    time_in_season = time_in_cycle % season_length
    transition_start = season_length * 0.9  # Last 10% is transition

    current = SEASONS[season_index]
    next_season = SEASONS[(season_index + 1) % 4]

    if time_in_season >= transition_start:
        blend = (time_in_season - transition_start) / (season_length - transition_start)
    else:
        blend = 0.0

    return current, next_season, blend


def _compute_moon_phase(elapsed):
    """Return the current moon phase name based on elapsed time.

    The moon cycles through 8 phases over MOON_CYCLE_DAYS day/night periods.
    Each phase lasts one full day/night cycle (DAY_CYCLE_SECONDS).
    """
    full_cycle = MOON_CYCLE_DAYS * DAY_CYCLE_SECONDS
    phase_index = int((elapsed % full_cycle) / DAY_CYCLE_SECONDS) % len(MOON_PHASES)
    return MOON_PHASES[phase_index]


def _check_solar_eclipse(elapsed, day_phase):
    """Check if a solar eclipse is happening right now.

    Solar eclipses occur every SOLAR_ECLIPSE_PERIOD day/night cycles,
    at mid-day (day_phase ~0.25).  Returns a float 0.0-1.0 indicating
    eclipse intensity (0=none, 1=full darkness).
    """
    day_index = int(elapsed / DAY_CYCLE_SECONDS)
    if day_index % SOLAR_ECLIPSE_PERIOD != 0 or day_index == 0:
        return 0.0
    # Eclipse window: mid-day (phase 0.2 to 0.35)
    if 0.2 <= day_phase <= 0.35:
        center = 0.275
        dist = abs(day_phase - center) / 0.075
        return max(0.0, 1.0 - dist)
    return 0.0


def _check_lunar_eclipse(elapsed, day_phase):
    """Check if a lunar eclipse is happening right now.

    Lunar eclipses occur every LUNAR_ECLIPSE_PERIOD day/night cycles,
    at mid-night (day_phase ~0.8).  Returns a float 0.0-1.0 indicating
    eclipse intensity (0=none, 1=blood moon).
    """
    day_index = int(elapsed / DAY_CYCLE_SECONDS)
    if day_index % LUNAR_ECLIPSE_PERIOD != 0 or day_index == 0:
        return 0.0
    # Eclipse window: mid-night (phase 0.75 to 0.9)
    if 0.75 <= day_phase <= 0.9:
        center = 0.825
        dist = abs(day_phase - center) / 0.075
        return max(0.0, 1.0 - dist)
    return 0.0
