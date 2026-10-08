"""Smaller planning tools: slit-angle planner, coordinate conversion, radio LST ranges,
solar elongation for space observatories."""

from __future__ import annotations

from datetime import date, timedelta

import astropy.units as u
import numpy as np
from astropy.coordinates import (FK5, Galactic, GeocentricTrueEcliptic, SkyCoord,
                                 get_body)
from astropy.time import Time

from . import kernel
from .airmass import airmass as airmass_fn
from .night import make_model
from .sites import Site
from .targets import Target, apparent_radec, to_icrs
from .timeutil import format_hms


# ----------------------------------------------------------------------------- slit angle
def parallactic_plan(site: Site, t_start: Time, dwell_min: float, target: Target,
                     current_pa: float | None = None, n: int = 60) -> dict:
    """Optimal slit PA for an exposure (JSkyCalc's Parallactic Angle Predictor).

    Differential refraction across the slit ∝ tan z · sin(PA − q). The optimum minimises
    Σ [tan z_i sin(PA − q_i)]², i.e. PA = ½ atan2(Σ w sin 2q, Σ w cos 2q) with w = tan² z —
    a refraction-weighted axial mean of the parallactic angle.
    """
    jd = t_start.utc.jd + np.linspace(0, max(dwell_min, 0.1), n) / 1440.0
    model = make_model(site, jd[0] - 0.05, jd[-1] + 0.05, [target], knot_hours=0.5)
    ra, dec = apparent_radec([target], Time(jd.mean(), format="jd"), site)
    if target.is_body:
        ra_t, dec_t, _ = model.radec(target.body, jd)
    else:
        ra_t, dec_t = np.full(n, ra[0]), np.full(n, dec[0])
    alt, az, ha, q = model.target_altaz(ra_t, dec_t, jd)
    sun_alt = model.sun_alt(jd)
    z = np.radians(90 - alt)
    up = alt > 0
    tanz = np.where(up, np.tan(np.clip(z, 0, np.radians(89))), np.nan)
    w = np.where(up, tanz ** 2, 0.0)
    if w.sum() == 0:
        opt = None
    else:
        opt = 0.5 * np.degrees(np.arctan2(np.sum(w * np.sin(2 * q)), np.sum(w * np.cos(2 * q))))
    def factor(pa):
        return tanz * np.sin(np.radians(pa) - q)
    curves = {}
    if opt is not None:
        for d in (-30, -15, 0, 15, 30):
            curves[f"{d:+d}" if d else "optimal"] = factor(opt + d)
        if current_pa is not None:
            curves["current"] = factor(current_pa)
    am = airmass_fn(alt, "hardie")
    return {
        "minutes": (jd - jd[0]) * 1440.0, "alt": alt, "parallactic": np.degrees(q), "sun_alt": sun_alt,
        "optimal_pa": None if opt is None else float(((opt + 90) % 180) - 90),
        "airmass_start": float(am[0]) if up[0] else None, "airmass_end": float(am[-1]) if up[-1] else None,
        "max_factor_optimal": None if opt is None else float(np.nanmax(np.abs(factor(opt)))),
        "max_factor_current": None if (opt is None or current_pa is None) else float(np.nanmax(np.abs(factor(current_pa)))),
        "curves": curves, "below_horizon": bool((~up).any()),
    }


# ----------------------------------------------------------------------------- conversions
def convert(system: str, a: float, b: float, equinox="2000", when: Time | None = None) -> dict:
    """Convert a position given in 'equatorial' (deg, any equinox), 'galactic' or 'ecliptic'
    (geocentric true ecliptic of date) to every other system."""
    when = when or Time.now()
    if system == "equatorial":
        ra, dec = to_icrs(a, b, equinox, when=when)
        c = SkyCoord(ra * u.deg, dec * u.deg)
    elif system == "galactic":
        c = SkyCoord(l=a * u.deg, b=b * u.deg, frame=Galactic).icrs
    elif system == "ecliptic":
        c = SkyCoord(lon=a * u.deg, lat=b * u.deg, frame=GeocentricTrueEcliptic(equinox=when, obstime=when)).icrs
    else:
        raise ValueError("system must be equatorial, galactic or ecliptic")
    g = c.galactic
    e = c.transform_to(GeocentricTrueEcliptic(equinox=when, obstime=when))
    b1950 = c.fk4
    date_ = c.transform_to(FK5(equinox=when))
    fmt = lambda s: {"ra_deg": float(s.ra.deg), "dec_deg": float(s.dec.deg),  # noqa: E731
                     "ra_hms": format_hms(s.ra.hour, decimals=2), "dec_dms": format_hms(s.dec.deg, True, 1)}
    return {"icrs": fmt(c), "b1950": fmt(b1950), "of_date": fmt(date_), "epoch": float(when.jyear),
            "galactic": {"l": float(g.l.deg), "b": float(g.b.deg)},
            "ecliptic": {"lon": float(e.lon.deg), "lat": float(e.lat.deg)}}


# ----------------------------------------------------------------------------- radio
def lst_ranges(site: Site, targets: list[Target], min_elev: float, t: Time) -> list[dict]:
    """LST range above an elevation limit (no twilight: radio/mm arrays), plus Sun distance."""
    lat = np.radians(site.lat)
    sun = get_body("sun", t)
    out = []
    ra, dec = apparent_radec(targets, t, site)
    for i, tg in enumerate(targets):
        h = float(kernel.ha_at_altitude(np.radians(min_elev), dec[i], lat)) * 12 / np.pi
        ra_h = float(ra[i]) * 12 / np.pi
        transit_el = 90 - abs(site.lat - np.degrees(dec[i]))
        sun_sep = float(SkyCoord(ra[i] * u.rad, dec[i] * u.rad).separation(
            SkyCoord(sun.ra, sun.dec)).deg)
        if h <= 0:
            rng = None
        elif h >= 12:
            rng = (0.0, 24.0)
        else:
            rng = ((ra_h - h) % 24, (ra_h + h) % 24)
        out.append({"name": tg.name, "ra_h": ra_h, "hours": 2 * h if 0 < h < 12 else (24.0 if h >= 12 else 0.0),
                    "lst_start": None if rng is None else rng[0], "lst_end": None if rng is None else rng[1],
                    "transit_elev": transit_el, "sun_sep": sun_sep})
    return out


# ----------------------------------------------------------------------------- space
SPACE_PRESETS = {
    "JWST": {"min": 85.0, "max": 135.0, "note": "field of regard: solar elongation 85°–135°"},
    "HST": {"min": 50.0, "max": 180.0, "note": "Sun avoidance ≈ 50° (approximate)"},
    "Chandra": {"min": 46.0, "max": 180.0, "note": "Sun avoidance ≈ 46° (approximate; pitch/thermal limits are more complex)"},
}


def solar_elongation(targets: list[Target], start: date, days: int, lo: float, hi: float) -> dict:
    """Sun–target angle (geocentric) per day and the windows where it lies in [lo, hi]."""
    dates = [start + timedelta(days=k) for k in range(days)]
    t = Time([d.isoformat() for d in dates], scale="utc")
    sun = get_body("sun", t)
    sun_c = SkyCoord(sun.ra, sun.dec)
    out = []
    for tg in targets:
        c = tg.icrs_at(t[len(t) // 2])
        el = sun_c.separation(SkyCoord(c.ra, c.dec)).deg
        ok = (el >= lo) & (el <= hi)
        wins, k = [], 0
        while k < days:
            if ok[k]:
                j = k
                while j + 1 < days and ok[j + 1]:
                    j += 1
                wins.append([dates[k].isoformat(), dates[j].isoformat(), j - k + 1])
                k = j + 1
            else:
                k += 1
        out.append({"name": tg.name, "elongation": np.round(el, 2), "windows": wins, "days_visible": int(ok.sum())})
    return {"dates": [d.isoformat() for d in dates], "targets": out, "lo": lo, "hi": hi}
