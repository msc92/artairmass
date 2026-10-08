"""The fast interpolating model must agree with astropy's full AltAz chain."""

from datetime import date

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import AltAz, SkyCoord, get_body
from astropy.time import Time

from artairmass.core.night import compute_tracks, make_model
from artairmass.core.sites import get_site
from artairmass.core.targets import Target
from artairmass.core.timeutil import night_window

ARCSEC = 1 / 3600


@pytest.mark.parametrize("site_key,d", [("lco", date(2026, 10, 7)), ("maunakea", date(2027, 1, 15)),
                                        ("atca", date(2026, 6, 21))])
def test_tracks_vs_astropy(site_key, d):
    site = get_site(site_key)
    a, b = night_window(d, site.tz)
    targets = [Target("A1795", 207.2187, 26.5928), Target("Phoenix", 356.1829, -42.72),
               Target("NCP-ish", 30.0, 87.0), Target("SCP-ish", 200.0, -87.5),
               Target("Barnard", 269.452, 4.6934, pm_ra_cosdec=-801.551, pm_dec=10362.394, epoch=2016.0),
               Target("Jupiter", body="jupiter")]
    model = make_model(site, a.jd, b.jd, targets)
    jd = np.linspace(a.jd + 0.2, b.jd - 0.2, 37)
    tr = compute_tracks(site, jd, targets, model)
    t = Time(jd, format="jd", scale="utc")
    frame = AltAz(obstime=t, location=site.location)
    for i, tg in enumerate(targets):
        if tg.is_body:
            ref = get_body(tg.body, t, site.location).transform_to(frame)
            tol = 3.0  # planet motion within a night handled by the model's spline
        else:
            ref = SkyCoord([tg.icrs_at(tt) for tt in t]).transform_to(frame)
            tol = 1.0
        dalt = np.abs(tr.alt[i] - ref.alt.deg) / ARCSEC
        daz = np.abs(((tr.az[i] - ref.az.deg + 180) % 360 - 180) * np.cos(ref.alt.rad)) / ARCSEC
        assert dalt.max() < tol, (tg.name, dalt.max())
        assert daz.max() < tol, (tg.name, daz.max())
    for body in ("sun", "moon"):
        ref = get_body(body, t, site.location).transform_to(frame)
        alt, az, _ = model.body_altaz(body, jd)
        assert np.abs(alt - ref.alt.deg).max() / ARCSEC < 1.5, body
        assert (np.abs(((az - ref.az.deg + 180) % 360 - 180) * np.cos(ref.alt.rad)).max() / ARCSEC) < 1.5, body


def test_last_interpolation_is_exact():
    site = get_site("paranal")
    model = make_model(site, 2461320.0, 2461321.0)
    jd = np.linspace(2461320.05, 2461320.95, 101)
    exact = Time(jd, format="jd").sidereal_time("apparent", longitude=site.lon * u.deg).rad
    diff = np.abs((model.last(jd) - exact + np.pi) % (2 * np.pi) - np.pi)
    assert diff.max() * 12 / np.pi * 3600 < 1e-3  # < 1 ms of sidereal time
