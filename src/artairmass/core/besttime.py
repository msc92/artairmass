"""Best time of year: observable hours per night over a year, for one target or a list.

For each night (local evening date) the hours are counted on a 5-minute grid where

* the target is above the altitude/airmass limit,
* the Sun is below the chosen twilight (nautical −12° or astronomical −18°), and
* the Moon constraint holds: Moon below the horizon, or (illumination ≤ max_illum and
  Moon–target separation ≥ min_sep).

Moon presets: dark = 0.35, grey = 0.70, bright = 1.0 maximum illumination when the Moon is up.

Samples every 5 minutes. One year-long ``SkyModel`` (2-hour knots) serves every target, and apparent target places are
interpolated from monthly knots, so 50 targets × 365 nights stays at about a second.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
from astropy.time import Time

from . import kernel
from .airmass import alt_for_airmass
from .sites import Site
from .skymodel import SkyModel
from .targets import Target, apparent_radec
from .timeutil import local_to_time, night_window

MOON_PRESETS = {"dark": 0.35, "grey": 0.70, "bright": 1.0}
TWILIGHT_ALT = {"civil": -6.0, "nautical": -12.0, "astronomical": -18.0}
STEP_MIN = 5.0
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class YearGrid:
    dates: list[date]
    jd: np.ndarray            # (D, S) sample times (UTC JD), NaN-padded
    last: np.ndarray          # (D, S) rad
    sun_alt: np.ndarray       # (D, S) deg
    moon_alt: np.ndarray      # (D, S) deg
    moon_ra: np.ndarray       # (D, S) rad
    moon_dec: np.ndarray
    moon_illum: np.ndarray    # (D, S)
    midnight_jd: np.ndarray   # (D,)
    midnight_last: np.ndarray  # (D,) rad


@lru_cache(maxsize=8)
def year_grid(site: Site, start: date, days: int) -> YearGrid:
    dates = [start + timedelta(days=k) for k in range(days)]
    t0 = night_window(dates[0], site.tz)[0].jd
    t1 = night_window(dates[-1], site.tz)[1].jd
    model = SkyModel(site, t0, t1, knot_hours=2.0)
    n_s = int(25 * 60 / STEP_MIN) + 2  # DST fall-back nights are 25 h long
    jd = np.full((days, n_s), np.nan)
    mid = np.empty(days)
    for k, d in enumerate(dates):
        a, b = night_window(d, site.tz)
        m = int(round((b.jd - a.jd) * 1440 / STEP_MIN))
        jd[k, :m] = a.jd + (np.arange(m) + 0.5) * STEP_MIN / 1440.0
        mid[k] = local_to_time(_midnight(d), site.tz).jd
    ok = np.isfinite(jd)
    flat = jd[ok]
    sun_alt = np.full(jd.shape, np.nan)
    moon_alt = np.full(jd.shape, np.nan)
    mra = np.full(jd.shape, np.nan)
    mdec = np.full(jd.shape, np.nan)
    illum = np.full(jd.shape, np.nan)
    last = np.full(jd.shape, np.nan)
    sun_alt[ok] = model.sun_alt(flat)
    malt, _, _ = model.body_altaz("moon", flat)
    moon_alt[ok] = malt
    ra_m, dec_m, dist_m = model.radec("moon", flat)
    ra_s, dec_s, dist_s = model.radec("sun", flat)
    mra[ok], mdec[ok] = ra_m, dec_m
    elong = kernel.separation(ra_s, dec_s, ra_m, dec_m)
    phase = np.arctan2(dist_s * np.sin(elong), dist_m - dist_s * np.cos(elong))
    illum[ok] = (1 + np.cos(phase)) / 2
    last[ok] = model.last(flat)
    return YearGrid(dates, jd, last, sun_alt, moon_alt, mra, mdec, illum, mid, model.last(mid))


def _midnight(d: date):
    from datetime import datetime, time
    return datetime.combine(d + timedelta(days=1), time(0, 0))


def _apparent_year(targets: list[Target], site: Site, jd0: float, jd1: float):
    """Apparent RA/Dec (rad) for each target at monthly knots → (knots, ra[N,K], dec[N,K])."""
    knots = np.linspace(jd0 - 1, jd1 + 1, max(3, int((jd1 - jd0) / 30) + 3))
    ra = np.empty((len(targets), knots.size))
    dec = np.empty_like(ra)
    for j, k in enumerate(knots):
        r, d = apparent_radec(targets, Time(k, format="jd", scale="utc"), site)
        ra[:, j], dec[:, j] = r, d
    return knots, np.unwrap(ra, axis=1), dec


def best_time(site: Site, targets: list[Target], start: date, days: int = 365,
              limit: float = 2.0, limit_kind: str = "airmass", twilight: str = "astronomical",
              moon: str = "bright", max_illum: float | None = None, min_sep: float = 0.0,
              airmass_model: str = "hardie") -> dict:
    if not targets:
        raise ValueError("no targets")
    if any(t.is_body for t in targets):
        raise ValueError("best-time analysis is for fixed targets (not solar-system bodies)")
    g = year_grid(site, start, days)
    alt_lim = alt_for_airmass(limit, airmass_model) if limit_kind == "airmass" else float(limit)
    sun_lim = TWILIGHT_ALT[twilight]
    illum_lim = MOON_PRESETS.get(moon, 1.0) if max_illum is None else float(max_illum)
    lat = np.radians(site.lat)

    knots, kra, kdec = _apparent_year(targets, site, float(np.nanmin(g.jd)), float(np.nanmax(g.jd)))
    dark = g.sun_alt < sun_lim                                  # (D, S)
    moon_up = g.moon_alt > 0
    dt_h = STEP_MIN / 60.0

    out_targets = []
    for i, tg in enumerate(targets):
        ra = np.interp(g.jd, knots, kra[i])
        dec = np.interp(g.jd, knots, kdec[i])
        ha = kernel.wrap_pi(g.last - ra)
        alt, _ = kernel.altaz(ha, dec, lat)
        alt = np.degrees(alt)
        up = alt > alt_lim
        sep = np.degrees(kernel.separation(ra, dec, g.moon_ra, g.moon_dec))
        moon_ok = ~moon_up | ((g.moon_illum <= illum_lim) & (sep >= min_sep))
        hours = np.nansum(up & dark & moon_ok, axis=1) * dt_h
        hours_nomoon = np.nansum(up & dark, axis=1) * dt_h
        # HA at local midnight → the date it transits at midnight (HA crosses 0 going − to +)
        ra_mid = np.interp(g.midnight_jd, knots, kra[i])
        ha_mid = kernel.wrap_pi(g.midnight_last - ra_mid) * 12 / np.pi
        k_mid = int(np.argmin(np.abs(ha_mid)))
        out_targets.append({
            "name": tg.name,
            "hours": np.round(hours, 3),
            "hours_no_moon": np.round(hours_nomoon, 3),
            "midnight_transit": g.dates[k_mid].isoformat() if abs(ha_mid[k_mid]) < 0.3 else None,
            "ha_midnight": np.round(ha_mid, 3),
            **describe(g.dates, hours, start),
        })
    dark_avail = np.nansum(dark, axis=1) * dt_h
    illum_mid = np.array([np.nanmean(g.moon_illum[k][np.isfinite(g.jd[k])]) for k in range(days)])
    return {
        "dates": [d.isoformat() for d in g.dates],
        "dark_hours": np.round(dark_avail, 3),
        "moon_illum": np.round(illum_mid, 3),
        "targets": out_targets,
        "monthly": monthly(g.dates, [t["hours"] for t in out_targets]),
        "settings": {"limit": limit, "limit_kind": limit_kind, "alt_limit": alt_lim, "twilight": twilight,
                     "moon": moon, "max_illum": illum_lim, "min_sep": min_sep},
    }


def monthly(dates: list[date], series: list[np.ndarray]) -> dict:
    """Mean hours/night per calendar month (in the order the months occur)."""
    keys = []
    for d in dates:
        k = (d.year, d.month)
        if k not in keys:
            keys.append(k)
    idx = {k: [j for j, d in enumerate(dates) if (d.year, d.month) == k] for k in keys}
    return {"months": [f"{MONTHS[m - 1]} {y}" for y, m in keys],
            "mean_hours": [[round(float(np.mean(s[idx[k]])), 2) for k in keys] for s in series]}


def _phrase(d: date) -> str:
    part = "early" if d.day <= 10 else "mid" if d.day <= 20 else "late"
    return f"{part} {MONTHS[d.month - 1]}"


def semester_of(d: date) -> str:
    """A = Feb–Jul, B = Aug–Jan (January belongs to the previous year's B)."""
    if 2 <= d.month <= 7:
        return f"{d.year}A"
    return f"{d.year if d.month >= 8 else d.year - 1}B"


def next_semester(after: date, kind: str) -> str:
    """The first semester of ``kind`` ('A' or 'B') that has not started before ``after``."""
    y = after.year
    for cand in (f"{y - 1}B", f"{y}A", f"{y}B", f"{y + 1}A", f"{y + 1}B"):
        s_year, s_kind = int(cand[:4]), cand[-1]
        begins = date(s_year, 2, 1) if s_kind == "A" else date(s_year, 8, 1)
        if s_kind == kind and begins >= after:
            return cand
    return f"{y + 1}{kind}"


def describe(dates: list[date], hours: np.ndarray, start: date) -> dict:
    """Plain-language summary: best period, observable season, semester split."""
    h = np.asarray(hours, float)
    n = h.size
    kern = np.ones(7) / 7
    smooth = np.convolve(np.concatenate([h[-3:], h, h[:3]]), kern, mode="valid") if n >= 7 else h
    peak = float(smooth.max()) if n else 0.0
    sem: dict[str, float] = {}
    for d, x in zip(dates, h):
        sem[semester_of(d)] = sem.get(semester_of(d), 0.0) + float(x)
    if peak < 0.25:
        return {"best_date": None, "peak_hours": round(peak, 2), "best_ranges": [], "observable_ranges": [],
                "summary": "Not observable under these constraints at any time in this period.",
                "semesters": {k: round(v, 1) for k, v in sem.items()}, "semester_type_hours": {"A": 0.0, "B": 0.0},
                "recommended_type": None, "recommended_semester": None}
    best_k = int(np.argmax(smooth))
    good = smooth >= 0.75 * peak
    obs = smooth >= min(1.0, 0.5 * peak)

    def runs(mask):
        out, k = [], 0
        while k < n:
            if mask[k]:
                j = k
                while j + 1 < n and mask[j + 1]:
                    j += 1
                out.append((dates[k], dates[j]))
                k = j + 1
            else:
                k += 1
        # a run touching both ends wraps around the year
        if len(out) > 1 and mask[0] and mask[-1] and (dates[-1] - dates[0]).days >= 360:
            out = [(out[-1][0], out[0][1])] + out[1:-1]
        return out

    best_ranges = runs(good)
    obs_ranges = runs(obs)
    def span(r):  # days covered, allowing a range that wraps past the end of the period
        d = (r[1] - r[0]).days
        return d if d >= 0 else d + n

    def rng(r):
        return f"{_phrase(r[0])} to {_phrase(r[1])}" if span(r) > 12 else f"around {_phrase(r[0])}"

    whole_year = len(obs_ranges) == 1 and span(obs_ranges[0]) >= n - 3
    parts = [f"Best {', '.join(rng(r) for r in best_ranges)} — peak ≈ {peak:.1f} h/night around {dates[best_k].strftime('%d %b')}."]
    if whole_year:
        parts.append("Observable all year (≥ 1 h/night).")
    elif obs_ranges:
        parts.append(f"Usefully observable {', '.join(rng(r) for r in obs_ranges)}.")
    # Proposals are per semester *type*: compare all A-type (Feb–Jul) with all B-type (Aug–Jan) hours.
    a_h = sum(v for k, v in sem.items() if k.endswith("A"))
    b_h = sum(v for k, v in sem.items() if k.endswith("B"))
    kind = "A" if a_h >= b_h else "B"
    share = (a_h if kind == "A" else b_h) / (a_h + b_h) if (a_h + b_h) else 0
    upcoming = next_semester(start, kind)
    if share > 0.995:
        parts.append(f"All observable hours fall in {kind} semesters (Feb–Jul)." if kind == "A"
                     else f"All observable hours fall in {kind} semesters (Aug–Jan).")
    else:
        parts.append(f"{kind} semesters ({'Feb–Jul' if kind == 'A' else 'Aug–Jan'}) hold {share * 100:.0f}% of the hours.")
    best_sem = upcoming
    return {"best_date": dates[best_k].isoformat(), "peak_hours": round(peak, 2),
            "best_ranges": [[a.isoformat(), b.isoformat()] for a, b in best_ranges],
            "observable_ranges": [[a.isoformat(), b.isoformat()] for a, b in obs_ranges],
            "summary": " ".join(parts), "semesters": {k: round(v, 1) for k, v in sem.items()},
            "semester_type_hours": {"A": round(a_h, 1), "B": round(b_h, 1)},
            "recommended_type": kind, "recommended_semester": best_sem}
