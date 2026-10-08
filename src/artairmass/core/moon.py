"""Moon phase quantities: illuminated fraction, elongation, phase events, JSkyCalc-style text."""

from __future__ import annotations

from functools import lru_cache

import astropy.units as u
import numpy as np
from astropy.coordinates import GeocentricTrueEcliptic, get_body
from astropy.time import Time
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq

from .timeutil import SYNODIC_MONTH_D

PHASE_NAMES = ("New Moon", "First Quarter", "Full Moon", "Last Quarter")


def _vectors(t: Time, location=None):
    sun = get_body("sun", t, location).cartesian.xyz.to_value(u.AU)
    moon = get_body("moon", t, location).cartesian.xyz.to_value(u.AU)
    return sun, moon


def illumination(t: Time, location=None):
    """Illuminated fraction of the Moon's disc and Sun–Moon elongation (deg).

    With ``location`` both are topocentric (what the observer sees; the Moon's ~1°
    parallax changes the fraction by up to ~1%) — JSkyCalc's convention. Without it,
    geocentric.
    """
    sun, moon = _vectors(t, location)
    rs, rm = np.linalg.norm(sun, axis=0), np.linalg.norm(moon, axis=0)
    cos_elong = np.sum(sun * moon, axis=0) / (rs * rm)
    elong = np.arccos(np.clip(cos_elong, -1, 1))
    phase_angle = np.arctan2(rs * np.sin(elong), rm - rs * np.cos(elong))
    k = (1.0 + np.cos(phase_angle)) / 2.0
    return k, np.degrees(elong)


def _lon_diff(jd: np.ndarray) -> np.ndarray:
    """Moon − Sun geocentric apparent ecliptic longitude (deg, unwrapped)."""
    t = Time(jd, format="jd", scale="utc")
    frame = GeocentricTrueEcliptic(equinox=t)
    lm = get_body("moon", t).transform_to(frame).lon.deg
    ls = get_body("sun", t).transform_to(frame).lon.deg
    return np.degrees(np.unwrap(np.radians(lm - ls)))


def lunar_phases(jd_start: float, jd_end: float) -> list[tuple[float, int]]:
    """Principal phases in [jd_start, jd_end] as (jd_utc, k), k = 0 new, 1 FQ, 2 full, 3 LQ.

    Times good to ~1 s (cubic spline on 6-hour knots of the exact longitude difference).
    """
    step = 0.25
    knots = np.arange(jd_start - 1.0, jd_end + 1.0 + step, step)
    d = _lon_diff(knots)
    spl = CubicSpline(knots, d)
    out = []
    lo, hi = np.floor(d.min() / 90.0), np.ceil(d.max() / 90.0)
    for m in np.arange(lo, hi + 1):
        level = 90.0 * m
        idx = np.nonzero((d[:-1] - level) * (d[1:] - level) <= 0)[0]
        for i in idx[:1]:
            if d[i] == d[i + 1]:
                continue
            jd = brentq(lambda x: spl(x) - level, knots[i], knots[i + 1], xtol=1e-7)
            if jd_start <= jd <= jd_end:
                out.append((float(jd), int(m) % 4))
    return sorted(out)


def phases_around(jd: float, before: int = 1, after: int = 1) -> list[tuple[float, int]]:
    """Principal phases covering at least ``before``/``after`` lunations around ``jd``."""
    return _phases_cached(int(np.floor(jd)), before, after)


@lru_cache(maxsize=256)
def _phases_cached(day: int, before: int, after: int) -> list[tuple[float, int]]:
    return lunar_phases(day - before * SYNODIC_MONTH_D - 2, day + after * SYNODIC_MONTH_D + 2)


def phase_description(jd: float) -> str:
    """Verbal phase in JSkyCalc's wording (e.g. '3.2 days after full moon.')."""
    ph = phases_around(jd, 1, 1)
    news = [p for p, k in ph if k == 0]
    last_new = max(p for p in news if p <= jd)
    since = jd - last_new
    bucket = int(since / 3.69134)
    named = {k: [p for p, kk in ph if kk == k and p > last_new - 0.5] for k in (1, 2, 3)}

    def rel(k: int, label: str) -> str:
        t = min(named[k], key=lambda p: abs(p - jd))
        dd = jd - t
        return (f"{-dd:.1f} days before {label}." if dd < 0 else f"{dd:.1f} days after {label}.")

    if bucket == 0:
        return f"{since:.1f} days since new moon."
    if bucket <= 2:
        return rel(1, "1st quarter")
    if bucket <= 4:
        return rel(2, "full moon")
    if bucket <= 6:
        return rel(3, "last quarter")
    next_new = min(p for p in news if p > jd)
    return f"{next_new - jd:.1f} days before new moon."


def bright_limb_pa(sun_ra, sun_dec, moon_ra, moon_dec):
    """Position angle (rad, N through E) of the Moon's bright limb midpoint."""
    dra = sun_ra - moon_ra
    return np.arctan2(np.cos(sun_dec) * np.sin(dra),
                      np.sin(sun_dec) * np.cos(moon_dec) - np.cos(sun_dec) * np.sin(moon_dec) * np.cos(dra))
