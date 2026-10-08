import pytest

from artairmass import config
from artairmass.core.sites import all_sites, get_site


@pytest.fixture(autouse=True)
def tmp_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTAIRMASS_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_settings_roundtrip(tmp_config):
    assert config.load_settings()["site"] == "lco"
    config.save_settings({"site": "paranal", "bogus": 1})
    s = config.load_settings()
    assert s["site"] == "paranal" and "bogus" not in s


def test_corrupt_settings_fall_back(tmp_config):
    (tmp_config / "settings.json").write_text("{not json")
    assert config.load_settings() == config.DEFAULTS
    assert (tmp_config / "settings.corrupt.json").exists()


def test_user_sites_override_and_validate():
    config.save_user_sites([{"key": "home", "name": "Backyard", "lat": -33.4, "lon": -70.6,
                             "elevation": 600, "tz": "America/Santiago"}])
    sites = all_sites(config.load_user_sites())
    assert get_site("home", config.load_user_sites()).user
    assert len({s.key for s in sites}) == len(sites)
    with pytest.raises(Exception):
        all_sites([{"key": "x", "name": "x", "lat": 0, "lon": 0, "elevation": 0, "tz": "Mars/Olympus"}])


def test_predictive_mjd_without_metadata():
    """astropy < 7 tables carry no 'predictive_mjd' meta: derive it from the row flags."""
    from astropy.table import Table

    from artairmass.astro_setup import predictive_mjd
    t = Table({"MJD": [60000.0, 60001.0, 60002.0], "UT1Flag": ["I", "I", "P"]})
    assert predictive_mjd(t) == 60002.0
    t.meta["predictive_mjd"] = 60001.5
    assert predictive_mjd(t) == 60001.5
