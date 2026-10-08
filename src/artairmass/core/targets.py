"""Targets: fixed (sidereal) objects with optional proper motion, and solar-system bodies.

Coordinates are stored as ICRS at ``epoch`` (Julian year). Input in other frames is
converted once at construction:

* ``equinox`` ≥ 1984 (or a ``J`` prefix) → FK5 mean equator & equinox of that date;
* ``equinox`` < 1984 (or a ``B`` prefix) → FK4 (Besselian, with E-terms), e.g. B1950;
* ``"icrs"`` → ICRS; ``"date"`` / a negative number (JSkyCalc convention) → FK5 mean
  equinox of the observation date, resolved by the caller;
* galactic l, b → via astropy's Galactic frame.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import asdict, dataclass, field

import astropy.units as u
import numpy as np
from astropy.coordinates import (FK4, FK5, ICRS, TETE, Galactic, SkyCoord,
                                 get_body)
from astropy.time import Time

from .sites import Site

SOLAR_SYSTEM = ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
                "uranus", "neptune")


def parse_equinox(value) -> tuple[str, float | None]:
    """Normalize an equinox spec to (frame, year). frame ∈ {icrs, fk5, fk4, date}."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "icrs", None
    if isinstance(value, (int, float, np.floating)):
        year = float(value)
        if year < 0:
            return "date", None
        return ("fk4", year) if year < 1984.0 else ("fk5", year)
    s = str(value).strip().upper()
    if s in ("ICRS", "ICRF"):
        return "icrs", None
    if s in ("DATE", "NOW", "APPARENT", "OF DATE"):
        return "date", None
    if s in ("FK5", "J2000.0"):
        return "fk5", 2000.0
    if s in ("FK4",):
        return "fk4", 1950.0
    m = re.fullmatch(r"([JB])?\s*(-?\d+(?:\.\d*)?)", s)
    if not m:
        raise ValueError(f"unrecognised equinox {value!r}")
    prefix, year = m.group(1), float(m.group(2))
    if year < 0:
        return "date", None
    if prefix == "J":
        return "fk5", year
    if prefix == "B":
        return "fk4", year
    return ("fk4", year) if year < 1984.0 else ("fk5", year)


def to_icrs(ra_deg: float, dec_deg: float, equinox=2000.0, when: Time | None = None) -> tuple[float, float]:
    """Convert a mean position in the given equinox to ICRS (deg)."""
    frame, year = parse_equinox(equinox)
    if frame == "icrs":
        return float(ra_deg), float(dec_deg)
    if frame == "date":
        if when is None:
            when = Time.now()
        fr = FK5(equinox=when)
    elif frame == "fk5":
        fr = FK5(equinox=Time(year, format="jyear"))
    else:
        fr = FK4(equinox=Time(year, format="byear"), obstime=Time(year, format="byear"))
    c = SkyCoord(ra_deg * u.deg, dec_deg * u.deg, frame=fr).icrs
    return float(c.ra.deg), float(c.dec.deg)


def galactic_to_icrs(l_deg: float, b_deg: float) -> tuple[float, float]:
    c = SkyCoord(l=l_deg * u.deg, b=b_deg * u.deg, frame=Galactic).icrs
    return float(c.ra.deg), float(c.dec.deg)


@dataclass
class Target:
    name: str
    ra: float = 0.0           # ICRS deg at `epoch`
    dec: float = 0.0
    pm_ra_cosdec: float = 0.0  # mas/yr
    pm_dec: float = 0.0        # mas/yr
    epoch: float = 2000.0      # Julian year of the position
    body: str | None = None    # solar-system body name instead of fixed coords
    url: str = ""
    notes: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def is_body(self) -> bool:
        return self.body is not None

    @property
    def has_pm(self) -> bool:
        return bool(self.pm_ra_cosdec or self.pm_dec)

    def skycoord(self) -> SkyCoord:
        if self.has_pm:
            return SkyCoord(ra=self.ra * u.deg, dec=self.dec * u.deg,
                            pm_ra_cosdec=self.pm_ra_cosdec * u.mas / u.yr,
                            pm_dec=self.pm_dec * u.mas / u.yr,
                            obstime=Time(self.epoch, format="jyear"), frame=ICRS)
        return SkyCoord(ra=self.ra * u.deg, dec=self.dec * u.deg, frame=ICRS)

    def icrs_at(self, t: Time) -> SkyCoord:
        """ICRS position at time ``t`` (proper motion applied; bodies: geocentric)."""
        if self.is_body:
            raise ValueError("icrs_at is for fixed targets")
        c = self.skycoord()
        if self.has_pm:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # no distance → astropy assumes infinite
                c = c.apply_space_motion(new_obstime=t)
            c = SkyCoord(ra=c.ra, dec=c.dec, frame=ICRS)
        return c

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Target":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in allowed})


def body_target(name: str) -> Target:
    name = name.lower()
    if name not in SOLAR_SYSTEM:
        raise ValueError(f"unknown body {name!r}")
    return Target(name=name.capitalize(), body=name)


def apparent_radec(targets: list[Target], t: Time, site: Site) -> tuple[np.ndarray, np.ndarray]:
    """Apparent TETE RA/Dec (rad) of each target at a single time ``t``.

    Fixed targets are geocentric apparent places (precession, nutation, aberration, light
    deflection, proper motion); bodies are topocentric. Returns arrays of shape (N,).
    """
    n = len(targets)
    ra = np.full(n, np.nan)
    dec = np.full(n, np.nan)
    fixed = [i for i, tg in enumerate(targets) if not tg.is_body]
    if fixed:
        pm_idx = [i for i in fixed if targets[i].has_pm]
        plain = [i for i in fixed if not targets[i].has_pm]
        if plain:
            c = SkyCoord(ra=[targets[i].ra for i in plain] * u.deg,
                         dec=[targets[i].dec for i in plain] * u.deg, frame=ICRS)
            a = c.transform_to(TETE(obstime=t))
            ra[plain], dec[plain] = a.ra.rad, a.dec.rad
        for i in pm_idx:
            a = targets[i].icrs_at(t).transform_to(TETE(obstime=t))
            ra[i], dec[i] = a.ra.rad, a.dec.rad
    for i, tg in enumerate(targets):
        if tg.is_body:
            c = get_body(tg.body, t, site.location).transform_to(TETE(obstime=t, location=site.location))
            ra[i], dec[i] = c.ra.rad, c.dec.rad
    return ra, dec
