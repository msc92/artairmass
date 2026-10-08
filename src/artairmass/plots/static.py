"""Publication-quality static airmass charts (matplotlib): PNG, PDF, SVG.

Conventions match the interactive plot: airmass on the left (inverted, 1 at top), the same
axis labelled in altitude on the right, local time below, UT and LST above, twilight shaded,
Moon altitude drawn on the same axis, and per-target minimum Moon separation in the legend.
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from astropy.time import Time  # noqa: E402

from ..core.airmass import airmass as airmass_fn  # noqa: E402
from ..core.timeutil import format_hm, hm_local, hm_utc  # noqa: E402

# CVD-validated categorical order (light surface), then neutral grey for overflow.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
LINESTYLES = ["-", "--", "-.", ":", (0, (5, 1, 1, 1)), (0, (3, 1, 1, 1, 1, 1)), (0, (1, 1)), (0, (5, 3))]


def airmass_figure(site, night, tracks, names, summary, ticks, limit=2.0, y_max=3.0,
                   airmass_model="hardie", title=None, slots=None, mono=False):
    jd_mid = night.midnight
    x = (tracks.jd - jd_mid) * 24.0
    nleg = len(names) + 1
    ncol = 2 if nleg > 4 else 1
    rows = int(np.ceil(nleg / ncol))
    fig, ax = plt.subplots(figsize=(8.0, 5.0 + 0.18 * rows), dpi=150)
    fig.subplots_adjust(left=0.09, right=0.9, top=0.84, bottom=0.14 + 0.035 * rows)

    def band(a, b, alpha):
        if a is not None and b is not None:
            ax.axvspan((a - jd_mid) * 24, (b - jd_mid) * 24, color="#3b5998", alpha=alpha, lw=0, zorder=0)

    x0, x1 = x[0], x[-1]
    tw = night.twilight
    sunset = night.sunset or tracks.jd[0]
    sunrise = night.sunrise or tracks.jd[-1]
    band(tracks.jd[0], sunset, 0.32)
    band(sunrise, tracks.jd[-1], 0.32)
    band(sunset, tw["civil"][0], 0.22)
    band(tw["civil"][1], sunrise, 0.22)
    band(tw["civil"][0], tw["nautical"][0], 0.13)
    band(tw["nautical"][1], tw["civil"][1], 0.13)
    band(tw["nautical"][0], tw["astronomical"][0], 0.06)
    band(tw["astronomical"][1], tw["nautical"][1], 0.06)

    def ytrans(alt):
        am = airmass_fn(alt, airmass_model)
        return np.where((alt > 0) & (am <= y_max + 0.3), am, np.nan)

    moon = ytrans(tracks.moon_alt)
    ax.plot(x, moon, color="#8a7f55", lw=1.2, alpha=0.9, zorder=2,
            label=f"Moon ({night.moon_illum * 100:.0f}% illum.)")
    for i, name in enumerate(names):
        slot = slots[i] if slots else i
        color = "#222222" if mono else (SERIES[slot] if slot is not None and slot < len(SERIES) else "#9a9a9a")
        ls = LINESTYLES[i % len(LINESTYLES)] if mono else "-"
        s = summary[i] if summary else {}
        sep = s.get("min_moon_sep")
        label = name + (f"  (Moon ≥ {sep:.0f}°)" if sep is not None else "")
        ax.plot(x, ytrans(tracks.alt[i]), color=color, ls=ls, lw=1.8, zorder=3, label=label)
    ax.axhline(limit, color="#555555", lw=0.8, ls=(0, (4, 3)), zorder=1)
    ax.text(x0 + 0.08, limit - 0.015 * (y_max - 1), f"airmass limit {limit:g}", va="bottom", ha="left",
            fontsize=7, color="#555555")

    ax.set_xlim(x0, x1)
    ax.set_ylim(y_max, 1.0)
    ax.set_ylabel("Airmass")
    tv = [t["x"] for t in ticks]
    ax.set_xticks(tv, [t["local"] for t in ticks], fontsize=8)
    ax.set_xlabel(f"Local time ({zone_label(ticks[0]['zone']) if ticks else ''}) — night of {night.date.isoformat()}")
    top = ax.secondary_xaxis("top")
    top.set_xticks(tv, [f"{t['ut']}\n{t['lst']}" for t in ticks], fontsize=7)
    top.set_xlabel("UT  /  LST", fontsize=8)
    right = ax.secondary_yaxis("right", functions=(lambda v: v, lambda v: v))
    alts = [a for a in (90, 60, 50, 40, 30, 25, 20, 15) if airmass_fn(a, airmass_model) <= y_max]
    right.set_yticks([float(airmass_fn(a, airmass_model)) for a in alts], [f"{a}°" for a in alts], fontsize=8)
    right.set_ylabel("Altitude")
    ax.grid(axis="y", color="#e3e2db", lw=0.6)
    for sp in ("top", "right"):
        ax.spines[sp].set_color("#c3c2b7")
    ax.tick_params(labelsize=8)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=ncol, fontsize=7.5, frameon=False,
              handlelength=2.6, columnspacing=2.0)
    ttl = title or site.name
    fig.suptitle(ttl, x=0.09, ha="left", fontsize=11, fontweight="bold", y=0.985)
    fig.text(0.09, 0.935, f"{site.lat:.4f}°, {site.lon:.4f}°, {site.elevation:.0f} m · Moon {night.moon_illum * 100:.0f}% · "
             f"airmass: {airmass_model} · shading: day, civil, nautical, astronomical twilight · artairmass",
             fontsize=7, color="#555555")
    return fig


def zone_label(z: str) -> str:
    """tzdata gives numeric names like '-03' for some zones: show them as 'UTC−3'."""
    import re
    m = re.fullmatch(r"([+-])(\d\d)(\d\d)?", z or "")
    if not m:
        return z
    h = int(m.group(2))
    mins = f":{m.group(3)}" if m.group(3) and m.group(3) != "00" else ""
    return f"UTC{'−' if m.group(1) == '-' else '+'}{h}{mins}"


def render(fig, fmt: str) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, metadata={"Creator": "artairmass"} if fmt in ("pdf", "svg") else None)
    plt.close(fig)
    return buf.getvalue()


def night_ticks(site, night, jd0: float, jd1: float, every_h: int = 1) -> list[dict]:
    """Tick positions at whole local hours across [jd0, jd1], with local, UT and LST labels."""
    import astropy.units as u
    from datetime import timedelta
    from ..core.timeutil import local_to_time, to_local

    start = to_local(Time(jd0, format="jd"), site.tz).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    out = []
    t = start
    while True:
        tt = local_to_time(t.replace(tzinfo=None), site.tz)
        if tt.jd > jd1:
            break
        if t.hour % every_h == 0:
            lst = tt.sidereal_time("apparent", longitude=site.lon * u.deg).hour
            out.append({"x": (tt.jd - night.midnight) * 24.0, "jd": float(tt.jd),
                        "local": hm_local(tt, site.tz), "ut": hm_utc(tt), "lst": format_hm(float(lst)),
                        "zone": to_local(tt, site.tz).tzname()})
        t = t + timedelta(hours=1)
    return out
