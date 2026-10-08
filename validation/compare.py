"""Compare artairmass against the JSkyCalc reference fixtures.

    python validation/compare.py            # prints a summary table
    python validation/compare.py --markdown # table for VALIDATION.md

Units of the reported differences: time in seconds, angles in arcsec unless noted.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.time import Time

from artairmass.core.almanac import compute_night
from artairmass.core.instant import compute_instant
from artairmass.core.moon import phase_description
from artairmass.core.sites import Site
from artairmass.core.tables import seasonal_table
from artairmass.core.targets import Target, to_icrs
from artairmass.core.timeutil import night_of

FIX = Path(__file__).parent / "fixtures"


def load():
    cases = json.loads((FIX / "cases.json").read_text())
    ref = {r["id"]: r for r in json.loads((FIX / "jskycalc_reference.json").read_text())}
    return cases, ref


def parse_sexa(s: str) -> float:
    neg = s.strip().startswith("-")
    parts = [abs(float(p)) for p in s.replace(":", " ").split()]
    v = parts[0] + parts[1] / 60 + parts[2] / 3600
    return -v if neg else v


def target_from_case(tg: dict) -> Target:
    ra, dec = to_icrs(parse_sexa(tg["ra"]) * 15.0, parse_sexa(tg["dec"]), float(tg["equinox"]))
    return Target(name=tg["name"], ra=ra, dec=dec)


def angdiff_deg(a, b):
    """Signed a−b wrapped to (−180, 180]."""
    return float((a - b + 180.0) % 360.0 - 180.0)


def hours_diff(a, b):
    return float((a - b + 12.0) % 24.0 - 12.0)


@lru_cache(maxsize=None)
def _night(site_json: str, d):
    return compute_night(Site(**json.loads(site_json)), d)


def compare():
    """Return {quantity: [(case_id, target, ours, theirs, diff)]}."""
    cases, ref = load()
    out = defaultdict(list)
    for cs in cases:
        r = ref[cs["id"]]
        site = Site(**{k: v for k, v in cs["site"].items()})
        t = Time(cs["jd"], format="jd", scale="utc")
        cid = cs["id"]

        # --- per-instant (site/time) quantities, via the first target's instant ----
        inst0 = compute_instant(site, t, target_from_case(cs["targets"][0]))
        out["LMST [s]"].append((cid, "", inst0["time"]["lmst_h"], r["sidereal"],
                                hours_diff(inst0["time"]["lmst_h"], r["sidereal"]) * 3600))
        out["LAST vs JSkyCalc LMST [s]"].append((cid, "", inst0["time"]["last_h"], r["sidereal"],
                                                 hours_diff(inst0["time"]["last_h"], r["sidereal"]) * 3600))
        sun, moon = inst0["sun"], inst0["moon"]
        out["Sun alt [arcsec]"].append((cid, "", sun["alt_deg"], r["sun_alt"], (sun["alt_deg"] - r["sun_alt"]) * 3600))
        out["Sun az [arcsec]"].append((cid, "", sun["az_deg"], r["sun_az"], angdiff_deg(sun["az_deg"], r["sun_az"]) * 3600 * np.cos(np.radians(r["sun_alt"]))))
        out["Moon alt [arcsec]"].append((cid, "", moon["alt_deg"], r["moon_alt"], (moon["alt_deg"] - r["moon_alt"]) * 3600))
        out["Moon az [arcsec]"].append((cid, "", moon["az_deg"], r["moon_az"], angdiff_deg(moon["az_deg"], r["moon_az"]) * 3600 * np.cos(np.radians(r["moon_alt"]))))
        out["Moon illuminated fraction"].append((cid, "", moon["illum"], r["moon_illum"], moon["illum"] - r["moon_illum"]))
        out["Zenith twilight [mag]"].append((cid, "", sun["ztwilight_mag"], r["ztwilight"], sun["ztwilight_mag"] - r["ztwilight"]))
        ours_ph, theirs_ph = phase_description(cs["jd"]), r["phase_descr"]
        same_kind = ours_ph.split(" ", 1)[1] == theirs_ph.split(" ", 1)[1]
        out["Moon phase text [days]"].append((cid, "", ours_ph, theirs_ph,
                                              (float(ours_ph.split()[0]) - float(theirs_ph.split()[0])) if same_kind else np.inf))

        # --- almanac -----------------------------------------------------------------
        d = night_of(t, site.tz)
        n = _night(json.dumps(cs["site"]), d)
        alm = r["almanac"]
        pairs = [("Sunset", n.sunset, alm["sunset"]), ("Sunrise", n.sunrise, alm["sunrise"]),
                 ("18° twilight (evening)", n.twilight["astronomical"][0], alm["eveningTwilight"]),
                 ("18° twilight (morning)", n.twilight["astronomical"][1], alm["morningTwilight"]),
                 ("Night centre", n.night_center, alm["nightcenter"])]
        degenerate = alm["eveningTwilight"] == alm["morningTwilight"]
        for label, ours, theirs in pairs:
            if degenerate and "twilight" in label:
                out["18° twilight: JSkyCalc degenerate cases"].append((cid, str(d), ours, theirs, 0.0))
                continue
            out[f"{label} [s]"].append((cid, str(d), ours, theirs, (ours - theirs) * 86400 if ours else np.inf))
        for label, kind in (("Moonrise", "rise"), ("Moonset", "set")):
            theirs = alm["moon" + kind]
            evs = [tt for tt, k in n.moon_events if k == kind]
            if evs and abs(min(evs, key=lambda x: abs(x - theirs)) - theirs) < 0.5:
                ours = min(evs, key=lambda x: abs(x - theirs))
                out[f"{label} [s]"].append((cid, str(d), ours, theirs, (ours - theirs) * 86400))

        # --- per-target ----------------------------------------------------------------
        for tg, rt in zip(cs["targets"], r["targets"]):
            target = target_from_case(tg)
            inst = compute_instant(site, t, target)
            T = inst["target"]
            name = tg["name"]
            dha = hours_diff(T["ha_h"], rt["ha"])
            out["Hour angle × cos δ [arcsec]"].append((cid, name, T["ha_h"], rt["ha"], dha * 54000 * np.cos(np.radians(T["icrs"]["dec_deg"]))))
            if abs(T["icrs"]["dec_deg"]) < 80:
                out["Hour angle, |δ| < 80° [s]"].append((cid, name, T["ha_h"], rt["ha"], dha * 3600))
            out["Altitude [arcsec]"].append((cid, name, T["alt_deg"], rt["alt"], (T["alt_deg"] - rt["alt"]) * 3600))
            out["Azimuth × cos(alt) [arcsec]"].append((cid, name, T["az_deg"], rt["az"], angdiff_deg(T["az_deg"], rt["az"]) * 3600 * np.cos(np.radians(rt["alt"]))))
            if rt["alt"] > 10 and T["alt_deg"] > 10:
                out["Airmass (relative, alt > 10°)"].append((cid, name, T["airmass"], rt["airmass"], (T["airmass"] - rt["airmass"]) / rt["airmass"]))
            elif rt["alt"] > 0 and T["alt_deg"] > 0:
                out["Airmass (relative, 0° < alt < 10°)"].append((cid, name, T["airmass"], rt["airmass"], (T["airmass"] - rt["airmass"]) / rt["airmass"]))
            if 90 - abs(T["alt_deg"]) > 1 and abs(T["icrs"]["dec_deg"]) < 80:  # ill-conditioned at zenith/pole
                out["Parallactic angle [arcsec]"].append((cid, name, T["parallactic_deg"], rt["parallactic"],
                                                          angdiff_deg(T["parallactic_deg"], rt["parallactic"]) * 3600))
            md = T["mean_of_date"]
            mc = SkyCoord(md["ra_deg"] * u.deg, md["dec_deg"] * u.deg)
            jc = SkyCoord(rt["ra_date"] * 15 * u.deg, rt["dec_date"] * u.deg)
            out["Mean place of date [arcsec]"].append((cid, name, "", "", mc.separation(jc).arcsec))
            gal = SkyCoord(l=T["galactic"]["l_deg"] * u.deg, b=T["galactic"]["b_deg"] * u.deg, frame="galactic")
            jg = SkyCoord(l=rt["gal_l"] * u.deg, b=rt["gal_b"] * u.deg, frame="galactic")
            out["Galactic l,b [arcsec]"].append((cid, name, "", "", gal.separation(jg).arcsec))
            out["Constellation (mismatches)"].append((cid, name, T["constellation_abbr"], rt["constel"],
                                                      0.0 if T["constellation_abbr"] == rt["constel"] else 1.0))
            out["Moon–object angle [arcsec]"].append((cid, name, inst["moon"]["moon_obj_deg"], rt["moonobj"], (inst["moon"]["moon_obj_deg"] - rt["moonobj"]) * 3600))
            if inst["moon"]["sky_brightness_v"] is not None and rt["moonlight"] < 90:
                out["Lunar sky brightness [mag]"].append((cid, name, inst["moon"]["sky_brightness_v"], rt["moonlight"], inst["moon"]["sky_brightness_v"] - rt["moonlight"]))
            b = inst["bary"]
            out["Bary. JD (UTC-based, JSkyCalc def.) [s]"].append((cid, name, b["bjd_utc"], rt["baryjd"], (b["bjd_utc"] - rt["baryjd"]) * 86400))
            out["Bary. light-time [s]"].append((cid, name, b["ltt_bary_s"], rt["barytcor"], b["ltt_bary_s"] - rt["barytcor"]))
            out["Bary. RV correction [m/s]"].append((cid, name, b["rv_corr_kms"], rt["baryvcor"], (b["rv_corr_kms"] - rt["baryvcor"]) * 1000))
            pf = inst["parallax_factors"]
            out["Parallax factors"].append((cid, name, "", "", max(abs(pf["east"] - rt["pifac_e"]), abs(pf["north"] - rt["pifac_n"]))))

            if tg.get("seasonal"):
                _compare_seasonal(out, cid, site, t, target, rt)
    return out


def _compare_seasonal(out, cid, site, t, target, rt):
    ours = seasonal_table(site, t, target)
    for orow, jrow in zip(ours, rt["seasonal"]):
        out["Seasonal: evening date (mismatches)"].append((cid, orow["moon"], orow["evening_date"], jrow[1],
                                                           0.0 if Time(orow["evening_date"]).strftime("%Y %b %d") == jrow[1] else 1.0))
        for k, key in enumerate(("eve", "ctr", "morn")):
            ha_o, ha_j = orow[f"ha_{key}"], jrow[2 + 2 * k]
            out["Seasonal: HA [min]"].append((cid, f"{orow['moon']} {key}", ha_o, ha_j,
                                              hours_diff(_hm(ha_o), _hm(ha_j)) * 60))
        for x, col in zip(("3", "2", "1.5"), (8, 9, 10)):
            out["Seasonal: hours observable [h]"].append((cid, f"{orow['moon']} <{x}", orow[f"hrs_lt_{x}"], float(jrow[col]),
                                                          orow[f"hrs_lt_{x}"] - float(jrow[col])))


def _hm(s: str) -> float:
    neg = s.strip().startswith("-")
    h, m = s.strip().lstrip("+-").split(":")
    v = int(h) + int(m) / 60
    return -v if neg else v


def summarize(out):
    rows = []
    for q, recs in out.items():
        d = np.array([abs(r[4]) for r in recs], dtype=float)
        worst = recs[int(np.nanargmax(d))]
        rows.append((q, len(d), float(np.median(d)), float(np.percentile(d, 95)), float(d.max()), worst))
    return rows


if __name__ == "__main__":
    md = "--markdown" in sys.argv
    rows = summarize(compare())
    if md:
        print("| Quantity | N | median abs Δ | 95th pct | max abs Δ | worst case |")
        print("|---|---:|---:|---:|---:|---|")
        for q, n, med, p95, mx, w in rows:
            label = q.replace("|", "\\|")
            print(f"| {label} | {n} | {med:.3g} | {p95:.3g} | {mx:.3g} | {w[0]} {w[1]} |")
    else:
        for q, n, med, p95, mx, w in rows:
            print(f"{q:42s} N={n:4d}  med={med:10.4g}  p95={p95:10.4g}  max={mx:10.4g}  worst={w[0]} {w[1]} ours={w[2]} jsk={w[3]}")
