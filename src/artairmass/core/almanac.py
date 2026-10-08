"""Nightly almanac: Sun/Moon rise & set, civil/nautical/astronomical twilight, dark time.

The night of local date D runs from local noon on D to local noon on D+1 (JSkyCalc's
convention). Events are found on the interpolating ``SkyModel`` (sampled every 10 min,
then refined with Brent's method to ~0.01 s); the model itself is good to ≲ 1″, i.e. well
under a second of time for these crossings.

Rise/set use the altitude of the disc centre: −(0.8333° + horizon dip), as JSkyCalc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np
from astropy.time import Time
from scipy.optimize import brentq

from . import moon as moonmod
from .skymodel import SkyModel
from .sites import Site
from .timeutil import local_to_time, night_window

TWILIGHTS = {"civil": -6.0, "nautical": -12.0, "astronomical": -18.0}


def find_crossings(f, a: float, b: float, level: float, step: float = 10 / 1440):
    """All times in [a, b] where f crosses ``level``: list of (jd, rising)."""
    n = max(int(np.ceil((b - a) / step)), 1)
    x = np.linspace(a, b, n + 1)
    y = f(x) - level
    out = []
    for i in np.nonzero(np.sign(y[:-1]) * np.sign(y[1:]) < 0)[0]:
        r = brentq(lambda z: float(f(np.array([z]))[0] - level), x[i], x[i + 1], xtol=1e-7)
        out.append((float(r), bool(y[i + 1] > y[i])))
    return out


@dataclass
class Night:
    date: date
    site_key: str
    start: float                     # local noon (UTC JD)
    end: float                       # next local noon
    midnight: float                  # local midnight
    sunset: float | None = None
    sunrise: float | None = None
    twilight: dict = field(default_factory=dict)   # name -> (evening_jd|None, morning_jd|None)
    night_center: float | None = None
    moon_events: list = field(default_factory=list)  # [(jd, 'rise'|'set')]
    moon_illum: float = 0.0          # at local midnight
    moon_phase: str = ""
    sun_status: str = "normal"       # normal | sun_never_sets | sun_never_rises

    @property
    def moonrise(self) -> float | None:
        return next((t for t, k in self.moon_events if k == "rise"), None)

    @property
    def moonset(self) -> float | None:
        return next((t for t, k in self.moon_events if k == "set"), None)

    always_dark: dict = field(default_factory=dict)  # name -> Sun below that level all window

    def dark_window(self, kind: str = "astronomical") -> tuple[float, float] | None:
        """Evening→morning twilight for ``kind`` (None if it never gets that dark).

        At high latitude a missing crossing means the window edge (noon) is used.
        """
        if self.always_dark.get(kind):
            return self.start, self.end
        eve, morn = self.twilight.get(kind, (None, None))
        if eve is None and morn is None:
            return None
        return (eve if eve is not None else self.start, morn if morn is not None else self.end)


def compute_night(site: Site, d: date, model: SkyModel | None = None,
                  describe_moon: bool = True) -> Night:
    t0, t1 = night_window(d, site.tz)
    a, b = t0.jd, t1.jd
    if model is None:
        model = SkyModel(site, a, b, knot_hours=1.0)
    midnight = local_to_time(datetime.combine(d + timedelta(days=1), time(0, 0)), site.tz).jd
    night = Night(date=d, site_key=site.key, start=a, end=b, midnight=midnight)

    sun = model.sun_alt
    probe = sun(np.linspace(a, b, 289))

    rs = site.rise_set_alt_deg
    ev = find_crossings(sun, a, b, rs)
    night.sunset = next((t for t, up in ev if not up), None)
    night.sunrise = next((t for t, up in ev if up and (night.sunset is None or t > night.sunset)), None)
    if night.sunset is None and night.sunrise is None:
        night.sun_status = "sun_never_rises" if probe.max() < rs else "sun_never_sets"

    for name, level in TWILIGHTS.items():
        cr = find_crossings(sun, a, b, level)
        eve = next((t for t, up in cr if not up), None)
        morn = next((t for t, up in cr if up and (eve is None or t > eve)), None)
        night.twilight[name] = (eve, morn)
        night.always_dark[name] = bool(probe.max() < level)

    if night.sunset is not None and night.sunrise is not None:
        night.night_center = 0.5 * (night.sunset + night.sunrise)
    else:
        night.night_center = midnight

    mev = find_crossings(model.moon_alt, a, b, rs)
    night.moon_events = [(t, "rise" if up else "set") for t, up in mev]

    if describe_moon:
        tm = Time(midnight, format="jd", scale="utc")
        k, _ = moonmod.illumination(tm, site.location)
        night.moon_illum = float(k)
        night.moon_phase = moonmod.phase_description(midnight)
    return night


def dark_hours(night: Night, kind: str = "astronomical") -> float:
    w = night.dark_window(kind)
    return 0.0 if w is None else 24.0 * (w[1] - w[0])
