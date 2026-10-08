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


# ----------------------------------------------------------------------------- summaries
def _crossings(jd: np.ndarray, y: np.ndarray, level: float):
    """Linear-interpolated crossings of y through level: [(jd, rising)]."""
    d = y - level
    out = []
    for k in np.nonzero(np.sign(d[:-1]) * np.sign(d[1:]) < 0)[0]:
        f = d[k] / (d[k] - d[k + 1])
        out.append((float(jd[k] + f * (jd[k + 1] - jd[k])), bool(d[k + 1] > d[k])))
    return out


def summarize(night: Night, tr: Tracks, targets: list[Target], limit: float = 2.0,
              twilight: str = "astronomical", airmass_model: str = "hardie",
              lat_deg: float | None = None) -> list[dict]:
    """Per-target night summary: limit crossings, transit, max altitude, dark hours, Moon."""
    from .airmass import alt_for_airmass

    alt_lim = alt_for_airmass(limit, airmass_model)
    jd = tr.jd
    dt_h = float(np.median(np.diff(jd))) * 24.0 if jd.size > 1 else 0.0
    win = night.dark_window(twilight)
    dark = (jd >= win[0]) & (jd <= win[1]) if win else np.zeros(jd.size, bool)
    out = []
    for i, tg in enumerate(targets):
        alt = tr.alt[i]
        ok = (alt > alt_lim) & dark
        cr = _crossings(jd, alt, alt_lim)
        rise = next((t for t, up in cr if up), None)
        set_ = next((t for t, up in cr if not up and (rise is None or t > rise)), None)
        if set_ is None:
            set_ = next((t for t, up in cr if not up), None)
        # transit: HA crossing 0 from east to west within the grid, else extrapolate
        ha = tr.ha_h[i]
        tcross = [t for t, up in _crossings(jd, ha, 0.0) if up]
        if tcross:
            transit = tcross[0]
        else:
            k = int(np.argmin(np.abs(ha)))
            transit = float(jd[k] - ha[k] / 24.0 / 1.00273790935)
        if jd[0] <= transit <= jd[-1]:
            t_alt = float(np.interp(transit, jd, alt))
        elif lat_deg is not None and not tg.is_body:
            t_alt = 90.0 - abs(lat_deg - tg.dec)  # meridian altitude (geometric, ICRS dec: ≲ 0.3° off)
        else:
            t_alt = None
        if dark.any():
            kmax = int(np.argmax(np.where(dark, alt, -99)))
            max_alt, max_alt_jd = float(alt[kmax]), float(jd[kmax])
        else:
            max_alt, max_alt_jd = None, None
        sep_win = tr.moon_sep[i][ok] if ok.any() else tr.moon_sep[i][dark] if dark.any() else tr.moon_sep[i]
        moon_up = tr.moon_alt > 0
        sep_up = tr.moon_sep[i][(ok if ok.any() else dark) & moon_up] if moon_up.any() else np.array([])
        out.append({
            "name": tg.name,
            "rise_jd": rise, "set_jd": set_,
            "always_above": bool(np.all(alt > alt_lim)), "never_above": bool(np.all(alt <= alt_lim)),
            "transit_jd": transit, "transit_alt": t_alt,
            "transit_in_night": bool(night.sunset is not None and night.sunrise is not None
                                     and night.sunset <= transit <= night.sunrise),
            "max_alt_dark": max_alt, "max_alt_jd": max_alt_jd,
            "min_airmass_dark": float(airmass_fn(max_alt, airmass_model)) if max_alt and max_alt > 0 else None,
            "dark_hours": round(float(ok.sum()) * dt_h, 2),
            "window_start": float(jd[ok][0]) if ok.any() else None,
            "window_end": float(jd[ok][-1]) if ok.any() else None,
            "min_moon_sep": float(np.min(sep_win)) if sep_win.size else None,
            "min_moon_sep_moon_up": float(np.min(sep_up)) if sep_up.size else None,
        })
    return out
