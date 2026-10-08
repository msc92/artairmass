"""Data for the all-sky (alt-az) display: stars, Sun, Moon, planets, targets, reference arcs."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

import astropy.units as u
import numpy as np
from astropy.coordinates import TETE, get_body
from astropy.time import Time

from . import kernel
from . import moon as moonmod
from .instant import PLANETS
from .sites import Site
from .targets import Target, apparent_radec

# Approximate V magnitudes for symbol sizing only.
PLANET_MAG = {"mercury": 0.0, "venus": -4.2, "mars": 0.5, "jupiter": -2.3, "saturn": 0.6,
              "uranus": 5.7, "neptune": 7.8}


@lru_cache(maxsize=1)
def bright_stars() -> dict:
    text = resources.files("artairmass.data").joinpath("bright_stars.json").read_text("utf-8")
    return json.loads(text)


@lru_cache(maxsize=8)
def _star_apparent(year_bucket: float):
    """Apparent places of the catalogue at a given epoch (cached; drift ≪ 1″/day)."""
    cat = np.array([s[:2] for s in bright_stars()["stars"]], dtype=float)
    from astropy.coordinates import SkyCoord
    t = Time(year_bucket, format="jyear")
    c = SkyCoord(cat[:, 0] * u.deg, cat[:, 1] * u.deg).transform_to(TETE(obstime=t))
    return c.ra.rad, c.dec.rad


def _altaz(ra, dec, last, lat):
    ha = kernel.wrap_pi(last - ra)
    alt, az = kernel.altaz(ha, dec, lat)
    return np.degrees(alt), np.degrees(az), ha


def sky_snapshot(site: Site, t: Time, targets: list[Target]) -> dict:
    lat = np.radians(site.lat)
    last = float(t.sidereal_time("apparent", longitude=site.lon * u.deg).rad)
    # stars: recompute apparent places every ~10 days (cache bucket)
    ra, dec = _star_apparent(round(float(t.jyear) * 36) / 36)
    alt, az, _ = _altaz(ra, dec, last, lat)
    stars = bright_stars()["stars"]
    up = alt > -2
    # [alt, az, V, B-V, HR, designation, proper name, RA_icrs, Dec_icrs]
    star_out = [[round(float(alt[i]), 3), round(float(az[i]), 3), s[2], s[3], s[4], s[5], s[6], s[0], s[1]]
                for i, s in enumerate(stars) if up[i]]

    loc = site.location
    bodies = {}
    for b in ("sun", "moon") + PLANETS:
        c = get_body(b, t, loc).transform_to(TETE(obstime=t, location=loc))
        a, z, h = _altaz(c.ra.rad, c.dec.rad, last, lat)
        bodies[b] = {"alt": float(a), "az": float(z), "ha_h": float(h * 12 / np.pi),
                     "ra": float(c.ra.rad), "dec": float(c.dec.rad), "mag": PLANET_MAG.get(b)}
    illum, elong = moonmod.illumination(t, loc)
    s, m = bodies["sun"], bodies["moon"]
    limb = moonmod.bright_limb_pa(s["ra"], s["dec"], m["ra"], m["dec"])
    # PA (from celestial north) → angle on the alt-az display: subtract the parallactic angle
    q_moon = kernel.parallactic_angle(np.radians(m["ha_h"] * 15), m["dec"], lat)
    m.update(illum=float(illum), elongation=float(elong),
             limb_pa_deg=float(np.degrees(limb)), limb_vs_zenith_deg=float(np.degrees(limb - q_moon)))

    tgt_out = []
    if targets:
        tra, tdec = apparent_radec(targets, t, site)
        talt, taz, tha = _altaz(tra, tdec, last, lat)
        for i, tg in enumerate(targets):
            tgt_out.append({"name": tg.name, "alt": float(talt[i]), "az": float(taz[i]),
                            "ha_h": float(tha[i] * 12 / np.pi)})
    return {"last_h": last * 12 / np.pi, "stars": star_out, "bodies": bodies, "targets": tgt_out}


@lru_cache(maxsize=64)
def reference_arcs(lat_deg: float) -> dict:
    """Meridian, celestial equator, HA lines every 2 h to ±6 h (fixed in alt-az for a site)."""
    lat = np.radians(lat_deg)

    def polyline(ha, dec):
        alt, az = kernel.altaz(ha, dec, lat)
        keep = alt > -0.5
        alt, az = np.degrees(alt), np.degrees(az)
        return [[round(float(a), 2), round(float(z), 2)] if k else None for a, z, k in zip(alt, az, keep)]

    decs = np.radians(np.linspace(-90, 90, 181))
    arcs = {"equator": polyline(np.radians(np.linspace(-180, 180, 361)), np.zeros(361))}
    for h in (-6, -4, -2, 0, 2, 4, 6):
        arcs[f"ha{h:+d}"] = polyline(np.full(decs.size, np.radians(15 * h)), decs)
    pole_alt = abs(lat_deg)
    arcs["pole"] = [[round(pole_alt, 2), 0.0 if lat_deg >= 0 else 180.0]]
    return arcs
