"""Time handling: instants, local time via IANA zones, JD/MJD, timesteps, night selection.

All instants are astropy ``Time`` objects in the UTC scale. Local civil time is derived
from the site's IANA zone (``zoneinfo``), so DST rules are whatever the tz database says —
not hard-coded rule tables.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
from astropy.time import Time

SIDEREAL_DAY_D = 0.99726956633   # mean sidereal day in solar days (JSkyCalc 't' step)
SYNODIC_MONTH_D = 29.530588853   # mean lunation (JSkyCalc 'l' step)

_STEP_UNITS = {
    "s": 1 / 86400, "sec": 1 / 86400,
    "m": 1 / 1440, "min": 1 / 1440,
    "h": 1 / 24, "hr": 1 / 24,
    "d": 1.0, "day": 1.0,
    "t": SIDEREAL_DAY_D,   # sidereal day: successive transits
    "l": SYNODIC_MONTH_D,  # lunation
    "w": 7.0,
}


def parse_step(text: str) -> float:
    """Parse a JSkyCalc-style timestep (``'1 h'``, ``'-30m'``, ``'1 t'``, ``'2 l'``) into days.

    A bare number is hours (JSkyCalc's default unit).
    """
    m = re.fullmatch(r"\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Z]*)\s*", text or "")
    if not m:
        raise ValueError(f"can't parse timestep {text!r}; use e.g. '1 h', '30 m', '1 t', '1 l'")
    value, unit = float(m.group(1)), (m.group(2).lower() or "h")
    if unit not in _STEP_UNITS:
        unit = unit[0]
    if unit not in _STEP_UNITS:
        raise ValueError(f"unknown timestep unit {m.group(2)!r} (use s, m, h, d, t, l)")
    return value * _STEP_UNITS[unit]


def now() -> Time:
    return Time.now()


def to_time(value) -> Time:
    """Coerce JD floats, ISO strings, datetimes and Times into a UTC ``Time``."""
    if isinstance(value, Time):
        return value.utc
    if isinstance(value, (int, float, np.floating)):
        return Time(float(value), format="jd", scale="utc")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return Time(value.astimezone(timezone.utc), scale="utc")
    return Time(value, scale="utc")


def to_local(t: Time, tz: str) -> datetime:
    """Aware local datetime for a scalar Time."""
    return t.utc.to_datetime(timezone=timezone.utc).astimezone(ZoneInfo(tz))


def local_to_time(dt: datetime, tz: str) -> Time:
    """Interpret a naive local wall-clock time in ``tz``.

    Ambiguous times (DST fall-back) resolve to the first occurrence; non-existent times
    (spring-forward gap) are moved forward by the gap, as a wall clock would read.
    """
    # PEP 495: with fold=0 a gap time uses the pre-transition offset, which lands it
    # past the gap, exactly like a wall clock that jumped forward.
    aware = dt.replace(tzinfo=ZoneInfo(tz), fold=0)
    return Time(aware.astimezone(timezone.utc), scale="utc")


def utc_offset_hours(t: Time, tz: str) -> float:
    return to_local(t, tz).utcoffset().total_seconds() / 3600.0


def zone_abbrev(t: Time, tz: str) -> str:
    return to_local(t, tz).tzname() or tz


def night_of(t: Time, tz: str) -> date:
    """The local calendar date on which the night containing ``t`` begins.

    Same rule as JSkyCalc: before local noon you are in the previous evening's night.
    """
    loc = to_local(t, tz)
    d = loc.date()
    return d - timedelta(days=1) if loc.hour < 12 else d


def local_noon(d: date, tz: str) -> Time:
    return local_to_time(datetime.combine(d, time(12, 0)), tz)


def night_window(d: date, tz: str) -> tuple[Time, Time]:
    """Local noon on ``d`` to local noon the next day (handles 23/25 h DST days)."""
    return local_noon(d, tz), local_noon(d + timedelta(days=1), tz)


def jd_to_mjd(jd):
    return jd - 2400000.5


def format_hms(hours: float, signed: bool = False, decimals: int = 0) -> str:
    """Hours (or degrees) to ``[+-]HH:MM:SS[.s]`` with correct rounding carry."""
    if hours is None or not np.isfinite(hours):
        return "—"
    sign = "-" if hours < 0 else ("+" if signed else "")
    scale = 10 ** decimals
    total = round(abs(hours) * 3600 * scale)
    whole, frac = divmod(total, scale)
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    out = f"{sign}{h:02d}:{m:02d}:{s:02d}"
    if decimals:
        out += f".{frac:0{decimals}d}"
    return out


def format_hm(hours: float, signed: bool = False) -> str:
    """Hours to ``[+-]HH:MM`` rounded to the nearest minute."""
    if hours is None or not np.isfinite(hours):
        return "—"
    return format_hms(round(hours * 60) / 60, signed=signed)[:-3]


def hm_local(t: Time, tz: str) -> str:
    """Local wall-clock HH:MM rounded to the nearest minute."""
    return to_local(Time(t.jd + 0.5 / 1440, format="jd", scale="utc"), tz).strftime("%H:%M")


def hm_utc(t: Time) -> str:
    return Time(t.jd + 0.5 / 1440, format="jd", scale="utc").datetime.strftime("%H:%M")
