"""Observatory sites: bundled list + user-defined sites."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from functools import cached_property
from importlib import resources
from zoneinfo import ZoneInfo

import astropy.units as u
from astropy.coordinates import EarthLocation

EARTH_RADIUS_M = 6378136.6  # value JSkyCalc uses for the horizon dip


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    lat: float                 # geodetic latitude, deg (north +)
    lon: float                 # longitude, deg (east +)
    elevation: float           # m above sea level
    tz: str                    # IANA zone, e.g. "America/Santiago"
    horizon_height: float = 0.0  # m above the horizon-forming terrain (rise/set dip)
    telescopes: str = ""
    user: bool = False

    def __post_init__(self):
        if not -90 <= self.lat <= 90:
            raise ValueError(f"latitude {self.lat} out of range")
        if not -180 <= self.lon <= 360:
            raise ValueError(f"longitude {self.lon} out of range")
        if self.horizon_height < 0:
            raise ValueError("horizon height must be >= 0 (it is a height above the terrain)")
        ZoneInfo(self.tz)  # raises if unknown

    @cached_property
    def location(self) -> EarthLocation:
        return EarthLocation.from_geodetic(self.lon * u.deg, self.lat * u.deg, self.elevation * u.m)

    @property
    def horizon_dip_deg(self) -> float:
        """Geometric dip of the horizon for an observer above the surrounding terrain."""
        return math.degrees(math.sqrt(2.0 * self.horizon_height / EARTH_RADIUS_M))

    @property
    def rise_set_alt_deg(self) -> float:
        """Altitude of the Sun/Moon centre at rise/set: refraction 34' + semidiameter 16' + dip."""
        return -(0.8333 + self.horizon_dip_deg)

    def to_dict(self) -> dict:
        return asdict(self)


def _load_builtin() -> list[Site]:
    text = resources.files("artairmass.data").joinpath("sites.json").read_text("utf-8")
    return [Site(**s) for s in json.loads(text)["sites"]]


BUILTIN_SITES: list[Site] = _load_builtin()


def site_from_dict(d: dict) -> Site:
    allowed = Site.__dataclass_fields__.keys()
    return Site(**{k: v for k, v in d.items() if k in allowed})


def all_sites(user_sites: list[dict] | None = None) -> list[Site]:
    """Built-in sites followed by user sites; a user site with the same key overrides."""
    users = [site_from_dict({**d, "user": True}) for d in (user_sites or [])]
    keys = {s.key for s in users}
    return [s for s in BUILTIN_SITES if s.key not in keys] + users


def get_site(key: str, user_sites: list[dict] | None = None) -> Site:
    for s in all_sites(user_sites):
        if s.key == key:
            return s
    raise KeyError(f"unknown site {key!r}")
