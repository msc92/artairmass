"""Parsing of single RA / Dec values in the many formats astronomers actually type.

RA:  ``13:48:52.5``, ``13 48 52.5``, ``13h48m52.5s``, ``13h 48m``, ``207.21875``,
     ``207.21875d``, ``207.2°``, ``13.81458h``.  A bare decimal is ambiguous (hours or
     degrees); the caller decides via ``ra_unit`` — ``"auto"`` treats values > 24 as
     degrees and otherwise reports the ambiguity instead of guessing silently.
Dec: ``+26:35:34``, ``26 35 34``, ``-00 12 03`` (sign kept on a zero degree field),
     ``26d35m34s``, ``26°35′34″``, ``26°35'34"``, ``26.5928``, unicode minus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_UNICODE = str.maketrans({
    "\u2212": "-", "\u2013": "-", "\u2014": "-", "\uff0b": "+",   # minus, dashes, fullwidth plus
    "\u2032": "'", "\u2019": "'", "\u2033": '"', "\u201d": '"', "\u201c": '"',  # primes, quotes
    "\u00ba": "\u00b0", "\u02da": "\u00b0", "\u00a0": " ",              # degree look-alikes, nbsp
})


class CoordError(ValueError):
    pass


@dataclass
class Parsed:
    deg: float
    how: str            # human-readable description of the interpretation used
    ambiguous: bool = False


def _normalize(text: str) -> str:
    s = str(text).strip().translate(_UNICODE).replace("''", '"')
    return re.sub(r"\s+", " ", s)


_NUM = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"


def _sexagesimal(s: str, units: str) -> tuple[float, int] | None:
    """Parse '[+-]A[sep]B[sep]C' with separators ':' / ' ' / unit letters. Returns (value, ncomp)."""
    sign = -1.0 if s.startswith("-") else 1.0
    body = s.lstrip("+-").strip()
    if units == "hms":
        body = re.sub(r"(?i)\s*([hms])\s*", lambda m: {"h": ":", "m": ":", "s": ""}[m.group(1).lower()], body)
    else:
        body = re.sub(r"(?i)\s*(°|deg|d|'|m|\"|s)\s*",
                      lambda m: "" if m.group(1) in ('"', "s", "S") else ":", body)
    body = body.strip(": ")
    parts = [p for p in re.split(r"[:\s]+", body) if p]
    if not 2 <= len(parts) <= 3 or not all(re.fullmatch(r"\d+\.?\d*|\.\d+", p) for p in parts):
        return None
    vals = [float(p) for p in parts]
    if any(v != int(v) for v in vals[:-1]):
        raise CoordError(f"only the last sexagesimal field may have a fraction: {s!r}")
    for v in vals[1:]:
        if v >= 60:
            raise CoordError(f"minutes/seconds must be < 60 in {s!r}")
    value = vals[0] + vals[1] / 60 + (vals[2] / 3600 if len(vals) == 3 else 0.0)
    return sign * value, len(vals)


def parse_ra(text: str, ra_unit: str = "auto") -> Parsed:
    """Right ascension → degrees. ``ra_unit``: auto | hours | deg."""
    s = _normalize(text)
    if not s:
        raise CoordError("empty RA")
    if s.startswith("-"):
        raise CoordError(f"RA cannot be negative: {text!r}")
    has_h_letters = re.search(r"(?i)\d\s*h", s) is not None
    deg_mark = re.search(r"(?i)(°|\bdeg\b|\d\s*d\b|\d\s*d\s*\d)", s) is not None

    # decimal with explicit unit
    m = re.fullmatch(rf"({_NUM})\s*(h|hr|hours?)", s, re.I)
    if m:
        return _ra_hours(float(m.group(1)), "decimal hours")
    m = re.fullmatch(rf"({_NUM})\s*(d|deg|degrees?|°)", s, re.I)
    if m:
        return _ra_deg(float(m.group(1)), "decimal degrees")

    # sexagesimal
    if has_h_letters or (not deg_mark and re.search(r"[:\s]", s)):
        r = _sexagesimal(s, "hms")
        if r:
            if ra_unit == "deg":
                return _ra_deg(r[0], "sexagesimal degrees (forced)")
            return _ra_hours(r[0], "sexagesimal hours")
    if deg_mark:
        r = _sexagesimal(s, "dms")
        if r:
            return _ra_deg(r[0], "sexagesimal degrees")

    # bare decimal
    if re.fullmatch(_NUM, s):
        v = float(s)
        if ra_unit == "hours":
            return _ra_hours(v, "decimal hours")
        if ra_unit == "deg" or v > 24:
            return _ra_deg(v, "decimal degrees")
        p = _ra_hours(v, "decimal hours (ambiguous: ≤ 24 could be degrees)")
        p.ambiguous = True
        return p
    raise CoordError(f"can't read RA {text!r}")


def _ra_hours(h: float, how: str) -> Parsed:
    if not 0 <= h < 24 + 1e-9:
        raise CoordError(f"RA {h} h out of range 0–24")
    return Parsed(15.0 * (h % 24.0), how)


def _ra_deg(d: float, how: str) -> Parsed:
    if not 0 <= d < 360 + 1e-9:
        raise CoordError(f"RA {d}° out of range 0–360")
    return Parsed(d % 360.0, how)


def parse_dec(text: str) -> Parsed:
    """Declination → degrees."""
    s = _normalize(text)
    if not s:
        raise CoordError("empty Dec")
    m = re.fullmatch(rf"({_NUM})\s*(d|deg|degrees?|°)?", s, re.I)
    if m:
        v, how = float(m.group(1)), "decimal degrees"
    else:
        r = _sexagesimal(s, "dms")
        if not r:
            raise CoordError(f"can't read Dec {text!r}")
        v, how = r[0], "sexagesimal degrees"
    if not -90 <= v <= 90:
        raise CoordError(f"Dec {v}° out of range ±90")
    return Parsed(v, how)


def format_ra(deg: float, decimals: int = 2) -> str:
    from ..core.timeutil import format_hms
    return format_hms(deg / 15.0, decimals=decimals)


def format_dec(deg: float, decimals: int = 1) -> str:
    from ..core.timeutil import format_hms
    return format_hms(deg, signed=True, decimals=decimals)
