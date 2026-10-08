from datetime import date

import numpy as np
import pytest
from astropy.time import Time

from artairmass.core import tools
from artairmass.core.sites import get_site
from artairmass.core.targets import Target

A1795 = Target("A1795", 207.2187, 26.5928)


def test_parallactic_short_exposure_matches_instant():
    site = get_site("kpno")
    t = Time("2026-04-20T06:00")
    r = tools.parallactic_plan(site, t, 1.0, A1795)
    q_mid = r["parallactic"][len(r["parallactic"]) // 2]
    d = ((r["optimal_pa"] - q_mid + 90) % 180) - 90
    assert abs(d) < 0.5  # axial agreement
    assert r["max_factor_optimal"] < 1e-2


def test_parallactic_long_exposure_beats_fixed_angles():
    site = get_site("lco")
    r = tools.parallactic_plan(site, Time("2026-10-08T01:00"), 120, Target("Phx", 356.18, -42.72), current_pa=0.0)
    assert r["max_factor_optimal"] <= min(np.nanmax(np.abs(c)) for c in r["curves"].values()) + 1e-9


def test_convert_roundtrip():
    out = tools.convert("galactic", 0.0, 0.0)
    back = tools.convert("equatorial", out["icrs"]["ra_deg"], out["icrs"]["dec_deg"], "ICRS")
    assert back["galactic"]["l"] % 360 == pytest.approx(0, abs=1e-6) or back["galactic"]["l"] == pytest.approx(360, abs=1e-6)
    assert out["b1950"]["ra_deg"] == pytest.approx(265.6, abs=0.1)


def test_lst_ranges():
    site = get_site("alma")
    rows = tools.lst_ranges(site, [A1795, Target("SCP", 0, -88), Target("NCP", 0, 88)], 20, Time("2026-10-08"))
    a, scp, ncp = rows
    assert 0 < a["hours"] < 12 and a["lst_start"] < a["ra_h"] < a["lst_end"]
    assert scp["hours"] == 24.0 and ncp["hours"] == 0.0


def test_jwst_windows():
    r = tools.solar_elongation([A1795], date(2027, 1, 1), 365, 85, 135)
    t = r["targets"][0]
    assert 2 <= len(t["windows"]) <= 3 and 80 < t["days_visible"] < 220
