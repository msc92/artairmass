import socket

import pytest

from artairmass.io import resolver

XML = """<?xml version="1.0"?><Sesame><Target><name>NGC 1275</name>
<Resolver name="Sc=Simbad (CDS, via client/server)"><otype>Bla</otype>
<jradeg>49.95066663</jradeg><jdedeg>41.5116969</jdedeg>
<pm><pmRA>0.112</pmRA><pmDE>-0.198</pmDE></pm><z><v>0.0168</v></z><oname>NGC  1275</oname></Resolver>
</Target></Sesame>"""


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTAIRMASS_CACHE_DIR", str(tmp_path))


def test_parse_sesame_xml():
    r = resolver._parse_sesame(XML, "NGC 1275")
    assert r["ra"] == pytest.approx(49.9506666) and r["oname"] == "NGC 1275" and r["z"] == 0.0168
    with pytest.raises(LookupError):
        resolver._parse_sesame("<Sesame><Target><name>x</name></Target></Sesame>", "x")


def test_offline_fails_gracefully(monkeypatch):
    monkeypatch.setattr(resolver, "MIRRORS", ("http://127.0.0.1:9/{q}",))
    monkeypatch.setattr(resolver, "TIMEOUT_S", 0.5)
    out = resolver.resolve(["NGC 1275", ""])
    assert "offline" in out[0]["error"] and out[1]["error"] == "empty name"


def test_cache_hit_avoids_network(monkeypatch):
    calls = []
    monkeypatch.setattr(resolver, "_fetch", lambda n: calls.append(n) or resolver._parse_sesame(XML, n))
    a = resolver.resolve(["NGC 1275"])[0]
    b = resolver.resolve(["ngc   1275"])[0]   # normalised key → cached
    assert calls == ["NGC 1275"] and b["cached"] and b["ra"] == a["ra"]


def _online():
    try:
        socket.create_connection(("cds.unistra.fr", 443), timeout=3).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _online(), reason="network not available")
def test_live_sesame():
    r = resolver.resolve(["Abell 1795", "this is not an object 12345"])
    assert r[0]["ra"] == pytest.approx(207.25, abs=0.1) and "error" in r[1]


def test_service_labels():
    assert resolver._service("Sc=Simbad (CDS, via client/server)") == "SIMBAD"
    assert resolver._service("N=NED") == "NED"
