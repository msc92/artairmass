"""Target tracks across a night, on a regular time grid (the engine behind plots & tables)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from astropy.time import Time

from . import kernel
from .airmass import airmass as airmass_fn
from .almanac import Night, compute_night
from .sites import Site
from .skymodel import SkyModel
from .targets import Target, apparent_radec
from .timeutil import night_window


@dataclass
class Tracks:
    jd: np.ndarray          # (T,) UTC JD
    last_h: np.ndarray      # (T,) local apparent sidereal time, hours
    sun_alt: np.ndarray     # (T,) deg
    moon_alt: np.ndarray    # (T,) deg
    alt: np.ndarray         # (N, T) deg, geometric
    az: np.ndarray          # (N, T) deg
    ha_h: np.ndarray        # (N, T) hours, west +
    airmass: np.ndarray     # (N, T) NaN below horizon
    parallactic: np.ndarray # (N, T) deg
    moon_sep: np.ndarray    # (N, T) deg (topocentric)


def make_model(site: Site, start: float, end: float, targets: list[Target] = (),
               knot_hours: float = 1.0) -> SkyModel:
    bodies = {"sun", "moon"} | {t.body for t in targets if t.is_body}
    return SkyModel(site, start, end, knot_hours=knot_hours, bodies=tuple(sorted(bodies)))


def compute_tracks(site: Site, jd: np.ndarray, targets: list[Target], model: SkyModel,
                   airmass_model: str = "hardie") -> Tracks:
    jd = np.asarray(jd, dtype=float)
    mid = Time(0.5 * (jd[0] + jd[-1]), format="jd", scale="utc")
    ra, dec = apparent_radec(targets, mid, site)
    ra_g = np.repeat(ra[:, None], jd.size, axis=1)
    dec_g = np.repeat(dec[:, None], jd.size, axis=1)
    for i, tg in enumerate(targets):  # bodies move: use the model's track
        if tg.is_body:
            ra_g[i], dec_g[i], _ = model.radec(tg.body, jd)
    alt, az, ha, q = model.target_altaz(ra_g, dec_g, jd)
    mra, mdec, _ = model.radec("moon", jd)
    malt, _, _ = model.body_altaz("moon", jd)
    sun_alt = model.sun_alt(jd)
    sep = np.degrees(kernel.separation(ra_g, dec_g, mra[None, :], mdec[None, :]))
    return Tracks(jd=jd, last_h=model.last(jd) * 12 / np.pi, sun_alt=sun_alt, moon_alt=malt,
                  alt=alt, az=az, ha_h=ha * 12 / np.pi,
                  airmass=airmass_fn(alt, airmass_model),
                  parallactic=np.degrees(q), moon_sep=sep)


def night_grid(night: Night, step_min: float = 2.0, pad_h: float = 0.5) -> np.ndarray:
    """Times from (sunset − pad) to (sunrise + pad); the noon window if the Sun doesn't set."""
    a = night.sunset if night.sunset is not None else night.start
    b = night.sunrise if night.sunrise is not None else night.end
    a, b = a - pad_h / 24, b + pad_h / 24
    n = int(np.ceil((b - a) * 1440 / step_min)) + 1
    return np.linspace(a, b, n)


def plan_night(site: Site, d: date, targets: list[Target], step_min: float = 2.0,
               airmass_model: str = "hardie") -> tuple[Night, Tracks]:
    start, end = night_window(d, site.tz)
    model = make_model(site, start.jd, end.jd, targets)
    night = compute_night(site, d, model)
    tracks = compute_tracks(site, night_grid(night, step_min), targets, model, airmass_model)
    return night, tracks
