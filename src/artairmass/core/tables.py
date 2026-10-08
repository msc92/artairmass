"""JSkyCalc's tabular windows: Hourly Circumstances and Seasonal Observability."""

from __future__ import annotations

from datetime import date

import numpy as np
from astropy.time import Time

from .airmass import alt_for_airmass
from .almanac import compute_night
from .moon import lunar_phases
from .night import compute_tracks, make_model
from .sites import Site
from .targets import Target
from .timeutil import SYNODIC_MONTH_D, format_hms, night_of, night_window, to_local


def _airmass_str(alt: float, am: float) -> str:
    if alt < 0:
        return "(down)"
    if not np.isfinite(am) or am > 10:
        return "> 10."
    return f"{am:5.2f}"


def hourly_table(site: Site, d: date, target: Target, airmass_model: str = "hardie") -> list[dict]:
    """One row per whole local hour from the hour of sunset to the hour after sunrise."""
    start, end = night_window(d, site.tz)
    model = make_model(site, start.jd, end.jd, [target])
    night = compute_night(site, d, model)
    a = night.sunset if night.sunset is not None else night.start
    b = night.sunrise if night.sunrise is not None else night.end
    # whole local hours: step in local wall-clock via UTC offset at sunset (DST-safe below)
    t_a = to_local(Time(a, format="jd"), site.tz)
    first = t_a.replace(minute=0, second=0, microsecond=0)
    jd0 = Time(first).utc.jd
    jds = jd0 + np.arange(0, int((b - jd0) * 24) + 2) / 24.0
    tr = compute_tracks(site, jds, [target], model, airmass_model)
    rows = []
    for k, jd in enumerate(jds):
        t = Time(jd, format="jd", scale="utc")
        loc = to_local(t, site.tz)
        alt = float(tr.alt[0, k])
        rows.append({
            "jd": float(jd), "local": loc.strftime("%H:%M"), "local_date": loc.strftime("%a %m-%d"),
            "ut": t.datetime.strftime("%H:%M"), "lst": format_hms(tr.last_h[k])[:5],
            "ha": format_hms(tr.ha_h[0, k], signed=True)[:6], "ha_h": float(tr.ha_h[0, k]),
            "alt": alt, "airmass": float(tr.airmass[0, k]) if alt > 0 else None,
            "airmass_str": _airmass_str(alt, float(tr.airmass[0, k])),
            "moon_alt": float(tr.moon_alt[k]), "sun_alt": float(tr.sun_alt[k]),
            "moon_sep": float(tr.moon_sep[0, k]),
        })
    return rows


# Altitudes at which JSkyCalc's (Hardie) airmass is 3, 2, 1.5 — the hrs<X columns.
SEASONAL_LIMITS = (3.0, 2.0, 1.5)


def seasonal_table(site: Site, t: Time, target: Target, airmass_model: str = "hardie",
                   twilight: str = "astronomical") -> list[dict]:
    """JSkyCalc's Seasonal Observability: each New and Full moon for 8 lunations
    (starting 3 before the current one): HA & airmass at evening twilight, night centre,
    morning twilight, and hours between twilights with airmass < 3, 2, 1.5."""
    jd = float(t.utc.jd)
    phases = lunar_phases(jd - 4.2 * SYNODIC_MONTH_D, jd + 5.5 * SYNODIC_MONTH_D)
    news = [p for p, k in phases if k == 0]
    i0 = max(i for i, p in enumerate(news) if p <= jd)
    rows_in = []
    for p in news[i0 - 3:i0 + 5]:
        full = next(q for q, k in phases if k == 2 and q > p)
        rows_in += [("New", p), ("Full", full)]

    model = make_model(site, rows_in[0][1] - 1.5, rows_in[-1][1] + 1.5, [target], knot_hours=1.0)
    limits_alt = [alt_for_airmass(x, airmass_model) for x in SEASONAL_LIMITS]
    rows = []
    for label, pjd in rows_in:
        d = night_of(Time(pjd, format="jd", scale="utc"), site.tz)
        night = compute_night(site, d, model)
        win = night.dark_window(twilight)
        eve, morn = (win if win else (night.night_center, night.night_center))
        when = np.array([eve, night.night_center, morn])
        tr = compute_tracks(site, when, [target], model, airmass_model)
        row = {"moon": label, "phase_jd": pjd, "evening_date": d.isoformat()}
        for k, key in enumerate(("eve", "ctr", "morn")):
            row[f"ha_{key}"] = format_hms(tr.ha_h[0, k], signed=True)[:6]
            row[f"airmass_{key}"] = _airmass_str(float(tr.alt[0, k]), float(tr.airmass[0, k]))
        if win:
            grid = np.arange(win[0], win[1], 1 / 1440.0)
            alt = compute_tracks(site, grid, [target], model, airmass_model).alt[0]
            for x, a in zip(SEASONAL_LIMITS, limits_alt):
                row[f"hrs_lt_{x:g}"] = round(float(np.count_nonzero(alt > a)) / 60.0, 2)
        else:
            for x in SEASONAL_LIMITS:
                row[f"hrs_lt_{x:g}"] = 0.0
        rows.append(row)
    return rows
