"""Ported formulae must reproduce JSkyCalc to rounding error given JSkyCalc's own inputs."""

import numpy as np
import pytest

from artairmass.core.airmass import airmass, alt_for_airmass, hardie, secz, young
from artairmass.core.skybright import lunar_sky_brightness, zenith_twilight


def test_hardie_matches_jskycalc(jsk_cases):
    _, ref = jsk_cases
    n = 0
    for r in ref.values():
        for t in r["targets"]:
            if t["alt"] > 0:
                assert float(hardie(t["alt"])) == pytest.approx(t["airmass"], rel=1e-12)
                n += 1
            else:
                assert np.isnan(hardie(t["alt"]))
    assert n > 100


def test_ztwilight_matches_jskycalc(jsk_cases):
    _, ref = jsk_cases
    for r in ref.values():
        assert zenith_twilight(r["sun_alt"]) == pytest.approx(r["ztwilight"], abs=1e-12)


def test_lunar_sky_brightness_matches_jskycalc(jsk_cases):
    _, ref = jsk_cases
    n = 0
    for r in ref.values():
        for t in r["targets"]:
            ours = lunar_sky_brightness(r["sunmoon"], t["moonobj"], r["moon_alt"], t["alt"], r["moon_dist"])
            assert ours == pytest.approx(t["moonlight"], abs=1e-9)
            n += 1
    assert n > 300


def test_airmass_models():
    alt = np.array([90.0, 60.0, 45.0, 30.0, 15.0])
    # Hardie and Young are both curvature-corrected: within 0.15 % above 15° (0.26 % at 10°)
    assert np.allclose(hardie(alt), young(alt), rtol=1.6e-3)
    # ... and both sit below the plane-parallel sec z
    assert np.all(hardie(alt[1:]) < secz(alt[1:]))
    assert float(hardie(90.0)) == pytest.approx(1.0)
    assert np.isnan(young(-1.0)) and np.isnan(secz(0.0))


@pytest.mark.parametrize("x", [1.0, 1.5, 2.0, 3.0])
def test_alt_for_airmass_inverts(x):
    assert float(airmass(alt_for_airmass(x))) == pytest.approx(x, abs=1e-6)


def test_jskycalc_seasonal_altitudes():
    # JSkyCalc hard-codes 19.2786, 29.8796, 41.7592 deg for airmass 3, 2, 1.5. We invert
    # Hardie exactly instead; JSkyCalc's 1.5 entry is 0.03 deg off its own formula.
    assert alt_for_airmass(3.0) == pytest.approx(19.2786, abs=2e-3)
    assert alt_for_airmass(2.0) == pytest.approx(29.8796, abs=2e-3)
    assert alt_for_airmass(1.5) == pytest.approx(41.7592, abs=0.05)
