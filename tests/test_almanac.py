from datetime import date

import astropy.units as u
import pytest
from astropy.time import Time

from artairmass.core.almanac import compute_night, dark_hours
from artairmass.core.sites import Site, get_site


@pytest.mark.parametrize("site_key,d", [("lco", date(2026, 10, 7)), ("maunakea", date(2026, 3, 8)),
                                        ("atca", date(2026, 4, 4)), ("orm", date(2026, 10, 24))])
def test_vs_astroplan(site_key, d):
    astroplan = pytest.importorskip("astroplan")
    site = get_site(site_key)
    n = compute_night(site, d)
    obs = astroplan.Observer(location=site.location)
    mid = Time(n.midnight, format="jd")
    def ap(fn, which, h):
        return fn(mid, which=which, horizon=h * u.deg, n_grid_points=300).jd
    pairs = [
        (n.sunset, ap(obs.sun_set_time, "previous", site.rise_set_alt_deg)),
        (n.sunrise, ap(obs.sun_rise_time, "next", site.rise_set_alt_deg)),
        (n.twilight["astronomical"][0], ap(obs.sun_set_time, "previous", -18)),
        (n.twilight["astronomical"][1], ap(obs.sun_rise_time, "next", -18)),
        (n.twilight["nautical"][0], ap(obs.sun_set_time, "previous", -12)),
        (n.twilight["civil"][1], ap(obs.sun_rise_time, "next", -6)),
    ]
    for ours, theirs in pairs:
        # astroplan interpolates linearly on its grid (~5 min spacing): good to ~10 s
        assert abs(ours - theirs) * 86400 < 15


def test_polar_cases_do_not_crash():
    svalbard = Site(key="sv", name="Svalbard", lat=78.2, lon=15.6, elevation=500, tz="Arctic/Longyearbyen")
    summer = compute_night(svalbard, date(2026, 6, 21))
    assert summer.sun_status == "sun_never_sets"
    assert summer.dark_window("astronomical") is None and dark_hours(summer) == 0.0
    winter = compute_night(svalbard, date(2026, 12, 21))
    assert winter.sun_status == "sun_never_rises"
    # noon Sun reaches only −11.6°: always below −6° (24 h civil dark), ~22 h nautical
    assert dark_hours(winter, "civil") == pytest.approx(24.0, abs=0.01)
    assert 21 < dark_hours(winter, "nautical") < 23


def test_marginal_astronomical_darkness():
    """At 48.5°N on the June solstice the Sun dips to only −18.04°: a short real window."""
    dao = Site(key="dao", name="DAO", lat=48.52, lon=-123.4167, elevation=74, tz="America/Vancouver")
    n = compute_night(dao, date(2026, 6, 21))
    eve, morn = n.twilight["astronomical"]
    assert eve is not None and morn is not None
    assert 0 < (morn - eve) * 24 < 1.0


def test_moon_illumination_and_events():
    n = compute_night(get_site("lco"), date(2026, 10, 7))
    assert 0 <= n.moon_illum <= 0.15  # new moon 2026-10-10
    assert {k for _, k in n.moon_events} <= {"rise", "set"}
    assert "new moon" in n.moon_phase
