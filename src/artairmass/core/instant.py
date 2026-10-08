"""Everything JSkyCalc's main window reports, for one site, instant and target.

Uses the full astropy chain (no interpolation): this is the reference-precision path.
Altitudes are geometric (unrefracted) like JSkyCalc unless ``refraction=True``.
"""

from __future__ import annotations

import astropy.units as u
import numpy as np
from astropy.coordinates import (FK5, TETE, AltAz, Galactic, GeocentricTrueEcliptic,
                                 SkyCoord, get_body, get_body_barycentric,
                                 get_constellation)
from astropy.time import Time

from . import kernel, moon as moonmod
from .airmass import airmass as airmass_fn
from .sites import Site
from .skybright import lunar_sky_brightness, zenith_twilight
from .targets import Target
from .timeutil import format_hms, to_local, zone_abbrev

PLANETS = ("mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune")
BRIGHT_PLANETS = ("venus", "mars", "jupiter", "saturn")


def sky_state(sun_alt: float) -> str:
    if sun_alt > -0.8333:
        return "day"
    if sun_alt > -6:
        return "civil twilight"
    if sun_alt > -12:
        return "nautical twilight"
    if sun_alt > -18:
        return "astronomical twilight"
    return "night"


def _radec(c) -> dict:
    return {"ra_deg": float(c.ra.deg), "dec_deg": float(c.dec.deg),
            "ra_hms": format_hms(c.ra.hour, decimals=2), "dec_dms": format_hms(c.dec.deg, signed=True, decimals=1)}


def _altaz_frame(t: Time, site: Site, refraction: bool) -> AltAz:
    if refraction:
        # standard atmosphere scaled to site elevation
        p = 1013.25 * np.exp(-site.elevation / 8400.0)
        return AltAz(obstime=t, location=site.location, pressure=p * u.hPa,
                     temperature=5 * u.deg_C, relative_humidity=0.2, obswl=0.55 * u.micron)
    return AltAz(obstime=t, location=site.location)


def target_coord(target: Target, t: Time, site: Site) -> SkyCoord:
    """Target as an astropy coordinate at time t (bodies: topocentric GCRS)."""
    if target.is_body:
        return get_body(target.body, t, site.location)
    return target.icrs_at(t)


def compute_instant(site: Site, t: Time, target: Target, airmass_model: str = "hardie",
                    refraction: bool = False) -> dict:
    t = t.utc
    loc = site.location
    lat = np.radians(site.lat)
    local = to_local(t, site.tz)
    lmst = t.sidereal_time("mean", longitude=site.lon * u.deg).hour
    last = t.sidereal_time("apparent", longitude=site.lon * u.deg).hour

    out: dict = {
        "time": {
            "utc": t.isot[:22], "local": local.isoformat(timespec="seconds"),
            "local_str": local.strftime("%a %Y-%m-%d %H:%M:%S"), "zone": zone_abbrev(t, site.tz),
            "utc_offset_h": local.utcoffset().total_seconds() / 3600.0,
            "jd": float(t.jd), "mjd": float(t.mjd), "epoch": float(t.jyear),
            "lmst_h": float(lmst), "last_h": float(last),
            "lmst": format_hms(lmst, decimals=1), "last": format_hms(last, decimals=1),
        },
        "site": site.to_dict(),
    }

    # --- target ---------------------------------------------------------------------
    c = target_coord(target, t, site)
    tete = c.transform_to(TETE(obstime=t, location=loc if target.is_body else None))
    aa = c.transform_to(_altaz_frame(t, site, refraction))
    alt, az = float(aa.alt.deg), float(aa.az.deg)
    ha = float(kernel.wrap_pi(np.radians(last * 15.0) - tete.ra.rad))
    q = float(kernel.parallactic_angle(ha, tete.dec.rad, lat))
    icrs = c.icrs if not target.is_body else SkyCoord(c.ra, c.dec, frame="icrs")
    mean_date = icrs.transform_to(FK5(equinox=t))
    gal = icrs.transform_to(Galactic)
    ecl = icrs.transform_to(GeocentricTrueEcliptic(equinox=t, obstime=t))
    am = float(airmass_fn(alt, airmass_model))

    out["target"] = {
        "name": target.name, "body": target.body, "url": target.url,
        "icrs": _radec(icrs), "mean_of_date": _radec(mean_date), "apparent": _radec(tete),
        "galactic": {"l_deg": float(gal.l.deg), "b_deg": float(gal.b.deg)},
        "ecliptic": {"lon_deg": float(ecl.lon.deg), "lat_deg": float(ecl.lat.deg)},
        "constellation": get_constellation(icrs),
        "constellation_abbr": get_constellation(icrs, short_name=True),
        "ha_h": ha * 12 / np.pi, "ha": format_hms(ha * 12 / np.pi, signed=True),
        "alt_deg": alt, "az_deg": az,
        "airmass": am if np.isfinite(am) else None,
        "parallactic_deg": float(np.degrees(q)),
        "pm": {"ra_cosdec": target.pm_ra_cosdec, "dec": target.pm_dec, "epoch": target.epoch},
    }

    # --- Sun & Moon -----------------------------------------------------------------
    sun = get_body("sun", t, loc)
    moon = get_body("moon", t, loc)
    sun_aa = sun.transform_to(AltAz(obstime=t, location=loc))
    moon_aa = moon.transform_to(AltAz(obstime=t, location=loc))
    sun_tete = sun.transform_to(TETE(obstime=t, location=loc))
    moon_tete = moon.transform_to(TETE(obstime=t, location=loc))
    illum, elong = moonmod.illumination(t, loc)
    moon_obj = float(moon_aa.separation(aa).deg) if not (target.is_body and target.body == "moon") else 0.0
    sun_obj = float(sun_aa.separation(aa).deg)
    moon_alt = float(moon_aa.alt.deg)
    moon_dist = float(moon_tete.distance.to_value(u.AU))
    if moon_alt > 0 and alt > 0:
        lsb = lunar_sky_brightness(float(elong), moon_obj, moon_alt, alt, moon_dist)
    else:
        lsb = None
    sun_alt = float(sun_aa.alt.deg)
    out["sun"] = {**_radec(sun_tete), "alt_deg": sun_alt, "az_deg": float(sun_aa.az.deg),
                  "state": sky_state(sun_alt), "ztwilight_mag": zenith_twilight(sun_alt),
                  "sun_obj_deg": sun_obj}
    out["moon"] = {**_radec(moon_tete), "alt_deg": moon_alt, "az_deg": float(moon_aa.az.deg),
                   "illum": float(illum), "elongation_deg": float(elong),
                   "phase": moonmod.phase_description(float(t.jd)),
                   "moon_obj_deg": moon_obj, "distance_km": float(moon_tete.distance.to_value(u.km)),
                   "sky_brightness_v": lsb if (lsb is None or lsb < 90) else None,
                   "bright_limb_pa_deg": float(np.degrees(moonmod.bright_limb_pa(
                       sun_tete.ra.rad, sun_tete.dec.rad, moon_tete.ra.rad, moon_tete.dec.rad)))}

    # --- barycentric ----------------------------------------------------------------
    if not target.is_body:
        ltt_b = t.light_travel_time(icrs, "barycentric", location=loc)
        ltt_h = t.light_travel_time(icrs, "heliocentric", location=loc)
        rv = icrs.radial_velocity_correction(kind="barycentric", obstime=t, location=loc)
        out["bary"] = {
            "bjd_tdb": float((t.tdb + ltt_b).jd),
            "ltt_bary_s": float(ltt_b.to_value(u.s)),
            "bjd_utc": float(t.jd + ltt_b.to_value(u.day)),   # JSkyCalc's "Bary. JD"
            "hjd_utc": float(t.jd + ltt_h.to_value(u.day)),
            "rv_corr_kms": float(rv.to_value(u.km / u.s)),
        }
        out["parallax_factors"] = parallax_factors(icrs, t)
    else:
        out["bary"] = None
        out["parallax_factors"] = None

    out["planets"] = planet_warnings(icrs, t)
    return out


def parallax_factors(c: SkyCoord, t: Time) -> dict:
    """E and N displacement (arcsec) of a star with 1″ parallax at time t."""
    x, y, z = get_body_barycentric("earth", t).xyz.to_value(u.AU)
    a, d = c.ra.rad, c.dec.rad
    return {"east": float(x * np.sin(a) - y * np.cos(a)),
            "north": float(x * np.cos(a) * np.sin(d) + y * np.sin(a) * np.sin(d) - z * np.cos(d))}


def planet_warnings(c: SkyCoord, t: Time) -> list[dict]:
    """JSkyCalc's 'Planet Warning?': bright planets within 3° (red < 1°), others within 1°."""
    out = []
    for p in PLANETS:
        sep = float(get_body(p, t).separation(SkyCoord(c.ra, c.dec, frame="icrs"), origin_mismatch="ignore").deg)
        limit = 3.0 if p in BRIGHT_PLANETS else 1.0
        if sep < limit:
            level = "red" if (p in BRIGHT_PLANETS and sep < 1.0) else "orange"
            out.append({"planet": p.capitalize(), "sep_deg": sep, "level": level})
    return out
