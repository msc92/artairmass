"""Name resolution via CDS Sesame (SIMBAD → NED → VizieR), with an on-disk cache.

This is the only feature that needs the network. Failures are reported per name, never
raised: offline, timeouts and unknown names each come back with a clear ``error``.
Successful lookups are cached forever in ``<cache dir>/names.json``; failures are not cached.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import cache_dir

MIRRORS = (
    "https://cds.unistra.fr/cgi-bin/nph-sesame/-ox/SNV?{q}",
    "https://vizier.cfa.harvard.edu/viz-bin/nph-sesame/-ox/SNV?{q}",
)
TIMEOUT_S = 6.0
_lock = threading.Lock()


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _cache_path() -> Path:
    return cache_dir() / "names.json"


def _load_cache() -> dict:
    try:
        return json.loads(_cache_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    p = _cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, indent=0, ensure_ascii=False), "utf-8")
    os.replace(tmp, p)


def _service(label: str) -> str:
    """'Sc=Simbad (CDS, via client/server)' → 'SIMBAD'; 'N=NED' → 'NED'."""
    core = label.split("(")[0].split("=")[-1].strip()
    return {"simbad": "SIMBAD", "ned": "NED", "vizier": "VizieR"}.get(core.lower(), core or "Sesame")


def _parse_sesame(xml: str, name: str) -> dict:
    root = ET.fromstring(xml)
    for res in root.iter("Resolver"):
        ra, de = res.findtext("jradeg"), res.findtext("jdedeg")
        if ra is None or de is None:
            continue
        out = {"name": name, "ra": float(ra), "dec": float(de),
               "resolver": _service(res.get("name") or ""),
               "otype": res.findtext("otype") or "", "oname": " ".join((res.findtext("oname") or "").split())}
        pm = res.find("pm")
        if pm is not None and pm.findtext("pmRA") and pm.findtext("pmDE"):
            out["pm_ra_cosdec"] = float(pm.findtext("pmRA"))
            out["pm_dec"] = float(pm.findtext("pmDE"))
            out["epoch"] = 2000.0  # Sesame positions are J2000 at epoch J2000
        z = res.find("z")
        if z is not None and z.findtext("v"):
            out["z"] = float(z.findtext("v"))
        return out
    raise LookupError("not found by SIMBAD, NED or VizieR")


def _fetch(name: str) -> dict:
    q = urllib.parse.quote(name.strip())
    last_err = None
    for url in MIRRORS:
        try:
            req = urllib.request.Request(url.format(q=q), headers={"User-Agent": "artairmass"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                return _parse_sesame(r.read().decode("utf-8", "replace"), name)
        except LookupError:
            raise
        except Exception as err:  # network trouble: try the mirror
            last_err = err
    raise ConnectionError(f"name service unreachable ({type(last_err).__name__}) — offline?")


def resolve(names: list[str], use_cache: bool = True) -> list[dict]:
    """Resolve names; returns one dict per name with either coordinates or ``error``."""
    with _lock:
        cache = _load_cache() if use_cache else {}
    results: dict[str, dict] = {}
    todo = []
    for n in names:
        k = _key(n)
        if not k:
            results[n] = {"name": n, "error": "empty name"}
        elif k in cache:
            results[n] = {**cache[k], "name": n, "cached": True}
        else:
            todo.append(n)

    def work(n):
        try:
            return n, _fetch(n)
        except LookupError as e:
            return n, {"name": n, "error": f"unknown name: {e}"}
        except Exception as e:
            return n, {"name": n, "error": str(e)}

    if todo:
        with ThreadPoolExecutor(max_workers=min(8, len(todo))) as ex:
            fetched = list(ex.map(work, todo))
        new = {}
        for n, res in fetched:
            results[n] = res
            if "error" not in res:
                new[_key(n)] = {k: v for k, v in res.items() if k != "name"}
        if new and use_cache:
            with _lock:
                cache = _load_cache()
                cache.update(new)
                _save_cache(cache)
    return [results[n] for n in names]
