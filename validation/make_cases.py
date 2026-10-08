"""Generate the JSkyCalc validation matrix → validation/fixtures/cases.json.

Sites use JSkyCalc's own site parameters (skycalcsites.dat) so both programs see the same
geography; our side adds the IANA zone. Instants are local evenings/nights chosen around
DST transitions in both hemispheres, solstices and an equinox. Targets: galaxy-cluster
fields, circumpolar / near-pole sources, a B1950 position, and synthetic targets placed
3–8° above the horizon at that instant (east and west).
"""

import json
from datetime import datetime
from pathlib import Path

import astropy.units as u
from astropy.coordinates import AltAz, SkyCoord

from artairmass.core.sites import Site
from artairmass.core.timeutil import local_to_time

HERE = Path(__file__).parent

# name, lon (h W), lat, stdz, dstcode, zone, abbrev, elev, horizon-elev ; IANA tz
SITES = {
    "lco": (["Las Campanas", "4.7133", "-29.0083", "4.", "-1", "Chilean", "C", "2282.", "2282."], "America/Santiago"),
    "paranal": (["VLT, Paranal", "4.69356", "-24.625", "4.", "-1", "Chilean", "C", "1706.", "1706."], "America/Santiago"),
    "maunakea": (["Mauna Kea", "10.36478", "19.8267", "10.", "0", "Hawaiian", "H", "4215.", "4215."], "Pacific/Honolulu"),
    "kpno": (["Kitt Peak [MDM Obs.]", "7.44111", "31.9533", "7.", "0", "Mountain", "M", "1925", "700."], "America/Phoenix"),
    "palomar": (["Palomar Mountain", "7.79089", "33.35667", "8.", "1", "Pacific", "P", "1706.", "1706."], "America/Los_Angeles"),
    "aat": (["Anglo-Australian Tel.", "-9.937739", "-31.277039", "-10", "-2", "Australian", "A", "1149.", "670."], "Australia/Sydney"),
    "lapalma": (["La Palma", "1.192", "28.75833", "0.", "2", "Spanish", "S", "2326.", "2326."], "Atlantic/Canary"),
    "dao": (["DAO, Victoria, BC", "8.22778", "48.52", "8", "1", "Pacific", "P", "74.", "74."], "America/Vancouver"),
}

# Local wall-clock instants per site (DST changes: US 2026-03-08 & 11-01; Chile 2026-04-05 &
# 09-06; Australia 2026-04-05 & 10-04; EU 2026-03-29 & 10-25).
DATES = {
    "lco": ["2026-04-04 21:30", "2026-04-05 22:00", "2026-09-05 23:00", "2026-09-06 21:15", "2026-06-21 02:00", "2026-12-21 23:30"],
    "paranal": ["2026-03-20 21:00", "2026-10-07 22:45"],
    "maunakea": ["2026-03-08 20:30", "2026-07-15 23:00", "2026-12-01 04:30"],
    "kpno": ["2026-03-08 21:00", "2026-11-01 01:30", "2026-06-21 22:00"],
    "palomar": ["2026-03-07 22:00", "2026-03-08 22:00", "2026-10-31 23:00", "2026-11-01 23:00"],
    "aat": ["2026-04-04 21:00", "2026-04-05 21:00", "2026-10-03 22:00", "2026-10-04 22:00"],
    "lapalma": ["2026-03-29 22:00", "2026-10-25 21:00", "2026-01-15 03:00"],
    "dao": ["2026-06-21 23:30", "2026-12-21 20:00"],
}

FIXED = [
    ("A1795", "13 48 52.5", "26 35 34", "2000"),
    ("Perseus", "03 19 48.16", "41 30 42.1", "2000"),
    ("Phoenix_cl", "23 44 43.9", "-42 43 12", "2000"),
    ("Hydra_A", "09 18 05.65", "-12 05 43.9", "2000"),
    ("SPole85", "06 00 00", "-85 00 00", "2000"),
    ("NPole85", "18 00 00", "85 00 00", "2000"),
    ("SPole89", "13 00 00", "-89 10 00", "2000"),
    ("3C273_B1950", "12 26 33.25", "02 19 43.3", "1950"),
]


def sexa(x: float, ndp: int, signed: bool) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    d = int(x)
    m = int((x - d) * 60)
    s = (x - d - m / 60) * 3600
    return f"{sign}{d:02d} {m:02d} {s:0{3 + ndp}.{ndp}f}"


def horizon_targets(site: Site, t):
    out = []
    for name, alt, az in (("LowEast", 4.0, 100.0), ("LowWest", 6.5, 250.0), ("LowNorth", 3.0, 10.0), ("LowSouth", 8.0, 185.0)):
        aa = SkyCoord(alt=alt * u.deg, az=az * u.deg, frame=AltAz(obstime=t, location=site.location))
        c = aa.icrs
        out.append((name, sexa(c.ra.hour, 2, False), sexa(c.dec.deg, 1, True), "2000"))
    return out


def main():
    cases = []
    for key, (jsk, tz) in SITES.items():
        site = Site(key=key, name=jsk[0], lat=float(jsk[2]), lon=-15.0 * float(jsk[1]),
                    elevation=float(jsk[7]), tz=tz, horizon_height=float(jsk[8]))
        for k, when in enumerate(DATES[key]):
            t = local_to_time(datetime.strptime(when, "%Y-%m-%d %H:%M"), tz)
            targets = [dict(name=n, ra=r, dec=d, equinox=e, seasonal=(k == 0 and n == "A1795"))
                       for n, r, d, e in FIXED + horizon_targets(site, t)]
            cases.append(dict(id=f"{key}-{k}", site=site.to_dict(), jsk_site=jsk, local=when,
                              jd=float(t.jd), targets=targets))
    path = HERE / "fixtures" / "cases.json"
    path.write_text(json.dumps(cases, indent=1))
    print(f"wrote {len(cases)} cases, {sum(len(c['targets']) for c in cases)} target evaluations → {path}")


if __name__ == "__main__":
    main()
