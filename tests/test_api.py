"""API smoke tests through FastAPI's TestClient (no browser)."""

import pytest
from fastapi.testclient import TestClient

from artairmass.api.app import create_app

A1795 = {"name": "A1795", "ra": 207.2187, "dec": 26.5928}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ["ARTAIRMASS_CONFIG_DIR"] = str(tmp_path_factory.mktemp("cfg"))
    return TestClient(create_app())


def test_status_and_sites(client):
    st = client.get("/api/status").json()
    assert st["iers"]["ephemeris"] == "builtin"
    keys = {s["key"] for s in client.get("/api/sites").json()}
    assert {"lco", "pachon", "ctio", "paranal", "lasilla", "alma", "atca", "mro", "maunakea", "kpno",
            "mmt", "palomar", "salt", "orm"} <= keys


def test_instant_defaults_to_zenith(client):
    r = client.post("/api/instant", json={"site": "lco", "time": "2026-10-08T04:00"}).json()
    assert r["target"]["name"] == "zenith" and r["target"]["alt_deg"] > 89.9


def test_instant_target(client):
    r = client.post("/api/instant", json={"site": "lco", "time": 2461321.6667, "target": A1795}).json()
    assert r["target"]["constellation_abbr"] == "Boo"
    assert r["bary"]["bjd_tdb"] - r["bary"]["bjd_utc"] == pytest.approx(69.184 / 86400, abs=0.01 / 86400)


def test_time_steps(client):
    base = client.post("/api/time", json={"site": "lco", "local": "2026-10-07 22:00"}).json()
    assert base["local"] == "2026-10-07 22:00:00" and base["night_of"] == "2026-10-07"
    t = client.post("/api/time", json={"site": "lco", "jd": base["jd"], "step": "1 t"}).json()
    assert (t["jd"] - base["jd"]) == pytest.approx(0.99726956633)
    # sidereal step keeps LST fixed
    assert t["last_h"] == pytest.approx(base["last_h"], abs=1e-3)
    assert client.post("/api/time", json={"site": "lco", "step": "1 q"}).status_code == 422


def test_night_and_tables(client):
    r = client.post("/api/night", json={"site": "lco", "date": "2026-10-07", "targets": [A1795, {"name": "Jupiter", "body": "jupiter"}]}).json()
    assert r["night"]["twilight"]["astronomical"]["evening"]["local"] == "21:08"
    assert len(r["tracks"]["alt"]) == 2
    assert client.post("/api/hourly", json={"site": "lco", "time": "2026-10-08T04:00", "target": A1795}).json()["rows"][0]["local"] == "19:00"
    assert len(client.post("/api/seasonal", json={"site": "lco", "time": "2026-10-08T04:00", "target": A1795}).json()["rows"]) == 16


def test_sky_and_planets(client):
    sky = client.post("/api/sky", json={"site": "lco", "time": "2026-10-08T04:00", "targets": [A1795]}).json()
    assert len(sky["stars"]) > 500 and "moon" in sky["bodies"] and "equator" in sky["arcs"]
    rows = client.post("/api/planets", json={"site": "lco", "time": "2026-10-08T04:00", "target": A1795}).json()["rows"]
    assert [r["name"] for r in rows][:2] == ["Mercury", "Venus"]


def test_coords_and_errors(client):
    r = client.post("/api/coords", json={"ra": "13:48:52.5", "dec": "+26:35:34", "equinox": "2000"}).json()
    assert r["ra"] == pytest.approx(207.21875, abs=2e-5)
    assert client.post("/api/coords", json={"ra": "13:61:00", "dec": "0"}).status_code == 422
    assert client.post("/api/instant", json={"site": "nowhere"}).status_code == 404
    bad = client.post("/api/instant", json={"site": "lco", "target": {"name": "x", "ra": 1, "dec": 95}})
    assert bad.status_code == 422 and "out of range" in bad.json()["detail"]


def test_user_site_roundtrip(client):
    s = {"key": "home", "name": "Home", "lat": -33.45, "lon": -70.66, "elevation": 570, "tz": "America/Santiago"}
    assert client.post("/api/sites", json=s).status_code == 200
    assert any(x["key"] == "home" and x["user"] for x in client.get("/api/sites").json())
    assert client.post("/api/sites", json={**s, "tz": "Mars/Olympus"}).status_code == 422
    assert client.delete("/api/sites/home").status_code == 200
    assert client.delete("/api/sites/lco").status_code == 404


def test_static_ui(client):
    assert "artairmass" in client.get("/").text
    assert client.get("/vendor/plotly.min.js").status_code == 200
