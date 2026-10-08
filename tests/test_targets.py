import astropy.units as u
import pytest
from astropy.coordinates import SkyCoord
from astropy.time import Time

from artairmass.core.targets import (Target, apparent_radec, body_target, galactic_to_icrs,
                                     parse_equinox, to_icrs)
from artairmass.core.sites import get_site


@pytest.mark.parametrize("value,expected", [
    (2000, ("fk5", 2000.0)), ("J2000", ("fk5", 2000.0)), ("2000.0", ("fk5", 2000.0)),
    (1950, ("fk4", 1950.0)), ("B1950", ("fk4", 1950.0)), ("ICRS", ("icrs", None)),
    (-1, ("date", None)), ("date", ("date", None)), ("J2015.5", ("fk5", 2015.5)),
    (None, ("icrs", None)), ("", ("icrs", None)),
])
def test_parse_equinox(value, expected):
    assert parse_equinox(value) == expected


def test_parse_equinox_rejects():
    with pytest.raises(ValueError):
        parse_equinox("galactic-ish")


def test_b1950_to_icrs_3c273():
    # 3C 273: B1950 12 26 33.25 +02 19 43.3  →  J2000 12 29 06.70 +02 03 08.6
    ra, dec = to_icrs(15 * (12 + 26 / 60 + 33.25 / 3600), 2 + 19 / 60 + 43.3 / 3600, "B1950")
    ref = SkyCoord("12h29m06.70s +02d03m08.6s")
    assert SkyCoord(ra * u.deg, dec * u.deg).separation(ref).arcsec < 1.0


def test_galactic_roundtrip():
    ra, dec = galactic_to_icrs(0.0, 0.0)
    assert SkyCoord(ra * u.deg, dec * u.deg).separation(SkyCoord("17h45m37.2s -28d56m10s")).arcsec < 2


def test_proper_motion_barnards_star():
    tg = Target("Barnard", 269.452, 4.6934, pm_ra_cosdec=-801.551, pm_dec=10362.394, epoch=2016.0)
    c = tg.icrs_at(Time(2026.0, format="jyear"))
    assert (c.dec.deg - 4.6934) * 3600 == pytest.approx(103.6, abs=0.2)


def test_apparent_radec_mixed_list():
    site = get_site("lco")
    tl = [Target("a", 10, -30), body_target("Moon"), Target("pm", 10, -30, pm_dec=1000.0)]
    ra, dec = apparent_radec(tl, Time("2026-10-08T04:00"), site)
    assert ra.shape == (3,) and not any(map(lambda v: v != v, ra))
    with pytest.raises(ValueError):
        body_target("vulcan")
