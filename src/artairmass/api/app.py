"""FastAPI application: a stateless JSON API over artairmass.core + the static web UI."""

from __future__ import annotations

import math
from datetime import date, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import astropy.units as u
import numpy as np
from astropy.coordinates import AltAz, SkyCoord
from astropy.time import Time
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__, astro_setup, config
from ..core import timeutil as tu
from ..core.almanac import Night, dark_hours
from ..core.instant import PLANETS, compute_instant
from ..core.night import plan_night
from ..core.sites import Site, all_sites, get_site
from ..core.sky import reference_arcs, sky_snapshot
from ..core.tables import hourly_table, seasonal_table
from ..core.targets import Target, body_target, to_icrs
from ..io.coords import CoordError, parse_dec, parse_ra
from ..io.parser import parse_text, write_jskycalc
from ..io.resolver import resolve

WEB_DIR = Path(str(resources.files("artairmass").joinpath("web")))


# --------------------------------------------------------------------------- models
class TargetIn(BaseModel):
    name: str = "target"
    ra: float = 0.0
    dec: float = 0.0
    pm_ra_cosdec: float = 0.0
    pm_dec: float = 0.0
    epoch: float = 2000.0
    body: str | None = None
    url: str = ""
    notes: str = ""

    def to_target(self) -> Target:
        if self.body:
            t = body_target(self.body)
            t.name = self.name or t.name
            return t
        if not (-90 <= self.dec <= 90):
            raise HTTPException(422, f"{self.name}: declination {self.dec} out of range")
        return Target(name=self.name, ra=self.ra % 360.0, dec=self.dec,
                      pm_ra_cosdec=self.pm_ra_cosdec, pm_dec=self.pm_dec, epoch=self.epoch,
                      url=self.url, notes=self.notes)


class Common(BaseModel):
    site: str = "lco"
    airmass_model: str = "hardie"


class InstantReq(Common):
    time: str | float = "now"     # ISO UTC, JD, or "now"
    target: TargetIn | None = None
    refraction: bool = False


class TimeReq(BaseModel):
    site: str = "lco"
    utc: str | None = None
    jd: float | None = None
    mjd: float | None = None
    local: str | None = None      # "YYYY-MM-DD HH:MM[:SS]" wall clock at the site
    step: str | None = None       # JSkyCalc-style step, e.g. "1 h", "1 t", "-1 l"
    steps: float = 1.0


class NightReq(Common):
    date: str | None = None       # local evening date (YYYY-MM-DD); default: night of `time`
    time: str | float = "now"
    targets: list[TargetIn] = Field(default_factory=list)
    step_min: float = 2.0


class SkyReq(Common):
    time: str | float = "now"
    targets: list[TargetIn] = Field(default_factory=list)


class CoordsReq(BaseModel):
    name: str = "target"
    ra: str
    dec: str
    equinox: str | float | None = "2000"
    ra_unit: str = "auto"
    time: str | float = "now"     # for equinox-of-date input


class ParseReq(BaseModel):
    text: str
    ra_unit: str = "auto"          # auto | hours | deg  (for bare-decimal RAs)
    equinox: str = "2000"          # default when a row has none
    delimiter: str = "auto"
    header: str = "auto"           # auto | yes | no
    coord_system: str = "auto"     # auto | equatorial | galactic
    time: str | float = "now"


class ResolveReq(BaseModel):
    names: list[str]


class ListReq(BaseModel):
    targets: list[dict]


class ExportReq(BaseModel):
    targets: list[TargetIn]
    format: str = "csv"            # csv | jskycalc


class SiteIn(BaseModel):
    key: str
    name: str
    lat: float
    lon: float
    elevation: float = 0.0
    tz: str
    horizon_height: float = 0.0
    telescopes: str = ""


# --------------------------------------------------------------------------- helpers
def _site(key: str) -> Site:
    try:
        return get_site(key, config.load_user_sites())
    except KeyError:
        raise HTTPException(404, f"unknown site {key!r}")


def _time(value) -> Time:
    if value in (None, "", "now"):
        return Time.now()
    try:
        return tu.to_time(value)
    except Exception:
        raise HTTPException(422, f"can't interpret time {value!r}")


def clean(obj: Any):
    """JSON-safe conversion: numpy → python, NaN/inf → None, rounded floats."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return clean(obj.tolist())
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def time_info(t: Time, site: Site) -> dict:
    loc = tu.to_local(t, site.tz)
    return {
        "utc": t.utc.isot[:23] + "Z", "jd": float(t.jd), "mjd": float(t.mjd),
        "local": loc.strftime("%Y-%m-%d %H:%M:%S"), "weekday": loc.strftime("%a"),
        "zone": loc.tzname(), "utc_offset_h": loc.utcoffset().total_seconds() / 3600,
        "last_h": float(t.sidereal_time("apparent", longitude=site.lon * u.deg).hour),
        "night_of": tu.night_of(t, site.tz).isoformat(),
    }


def night_json(n: Night, site: Site) -> dict:
    def ev(jd):
        if jd is None:
            return None
        t = Time(jd, format="jd", scale="utc")
        return {"jd": jd, "local": tu.hm_local(t, site.tz), "ut": tu.hm_utc(t),
                "lst": tu.format_hm(float(t.sidereal_time("apparent", longitude=site.lon * u.deg).hour))}
    return {
        "date": n.date.isoformat(), "sun_status": n.sun_status,
        "start": n.start, "end": n.end, "midnight": ev(n.midnight),
        "sunset": ev(n.sunset), "sunrise": ev(n.sunrise),
        "twilight": {k: {"evening": ev(e), "morning": ev(m)} for k, (e, m) in n.twilight.items()},
        "night_center": ev(n.night_center),
        "moon_events": [{"kind": k, **ev(t)} for t, k in n.moon_events],
        "moon_illum": n.moon_illum, "moon_phase": n.moon_phase,
        "dark_hours": {k: dark_hours(n, k) for k in ("nautical", "astronomical")},
    }


# --------------------------------------------------------------------------- app
def create_app() -> FastAPI:
    astro_setup.configure()
    app = FastAPI(title="artairmass", version=__version__)

    @app.exception_handler(ValueError)
    async def _value_error(_, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/api/status")
    def status():
        return clean({"version": __version__, "iers": astro_setup.iers_status().as_dict(),
                      "settings": config.load_settings()})

    @app.get("/api/settings")
    def get_settings():
        return config.load_settings()

    @app.put("/api/settings")
    def put_settings(updates: dict):
        return config.save_settings(updates)

    @app.get("/api/sites")
    def sites():
        return [s.to_dict() for s in all_sites(config.load_user_sites())]

    @app.post("/api/sites")
    def add_site(site: SiteIn):
        try:
            s = Site(**site.model_dump(), user=True)
        except Exception as err:
            raise HTTPException(422, str(err))
        users = [u for u in config.load_user_sites() if u.get("key") != s.key]
        users.append({k: v for k, v in s.to_dict().items() if k != "user"})
        config.save_user_sites(users)
        return s.to_dict()

    @app.delete("/api/sites/{key}")
    def delete_site(key: str):
        users = config.load_user_sites()
        kept = [u for u in users if u.get("key") != key]
        if len(kept) == len(users):
            raise HTTPException(404, "only user-defined sites can be deleted")
        config.save_user_sites(kept)
        return {"deleted": key}

    @app.post("/api/time")
    def resolve_time(req: TimeReq):
        site = _site(req.site)
        if req.local:
            try:
                fmt = "%Y-%m-%d %H:%M:%S" if req.local.count(":") == 2 else "%Y-%m-%d %H:%M"
                t = tu.local_to_time(datetime.strptime(req.local.strip().replace("T", " "), fmt), site.tz)
            except ValueError:
                raise HTTPException(422, f"local time must be YYYY-MM-DD HH:MM[:SS], got {req.local!r}")
        elif req.jd is not None:
            t = Time(req.jd, format="jd", scale="utc")
        elif req.mjd is not None:
            t = Time(req.mjd, format="mjd", scale="utc")
        else:
            t = _time(req.utc)
        if req.step:
            t = Time(t.jd + req.steps * tu.parse_step(req.step), format="jd", scale="utc")
        return clean(time_info(t, site))

    @app.post("/api/coords")
    def coords(req: CoordsReq):
        """Parse a typed RA/Dec/equinox into an ICRS target (the 'white fields' of JSkyCalc)."""
        try:
            ra, dec = parse_ra(req.ra, req.ra_unit), parse_dec(req.dec)
            ira, idec = to_icrs(ra.deg, dec.deg, req.equinox, when=_time(req.time))
        except CoordError as err:
            raise HTTPException(422, str(err))
        return {"name": req.name, "ra": ira, "dec": idec, "ra_how": ra.how, "dec_how": dec.how,
                "ambiguous": ra.ambiguous}

    @app.post("/api/parse")
    def parse(req: ParseReq):
        if len(req.text) > 5_000_000:
            raise HTTPException(413, "list too large (5 MB max)")
        res = parse_text(req.text, req.ra_unit, req.equinox, req.delimiter, req.header,
                         req.coord_system, when=_time(req.time))
        return clean(res.to_dict())

    @app.post("/api/resolve")
    def resolve_names(req: ResolveReq):
        if len(req.names) > 500:
            raise HTTPException(413, "at most 500 names per request")
        return {"results": clean(resolve(req.names))}

    @app.get("/api/lists")
    def lists():
        return config.list_names()

    @app.get("/api/lists/{name}")
    def get_list(name: str):
        try:
            return config.load_list(name)
        except FileNotFoundError:
            raise HTTPException(404, f"no saved list {name!r}")

    @app.put("/api/lists/{name}")
    def put_list(name: str, req: ListReq):
        out = config.save_list(name, req.targets)
        config.save_settings({"last_list": name})
        return out

    @app.delete("/api/lists/{name}")
    def delete_list(name: str):
        config.delete_list(name)
        return {"deleted": name}

    @app.post("/api/export")
    def export(req: ExportReq):
        ts = [t.model_dump() for t in req.targets if not t.body]
        if req.format == "jskycalc":
            return {"filename": "targets.txt", "text": write_jskycalc(ts)}
        lines = ["name,ra_deg,dec_deg,ra_hms,dec_dms,pm_ra_cosdec,pm_dec,epoch,url,notes"]
        for t in ts:
            q = lambda v: '"' + str(v).replace('"', '""') + '"' if any(c in str(v) for c in ',"\n') else str(v)  # noqa: E731
            lines.append(",".join(q(v) for v in (t["name"], f"{t['ra']:.6f}", f"{t['dec']:.6f}",
                                                tu.format_hms(t["ra"] / 15, decimals=2), tu.format_hms(t["dec"], True, 1),
                                                t["pm_ra_cosdec"], t["pm_dec"], t["epoch"], t["url"], t["notes"])))
        return {"filename": "targets.csv", "text": "\n".join(lines) + "\n"}

    @app.post("/api/instant")
    def instant(req: InstantReq):
        site, t = _site(req.site), _time(req.time)
        target = req.target.to_target() if req.target else _zenith_target(site, t)
        out = compute_instant(site, t, target, req.airmass_model, req.refraction)
        out["time_info"] = time_info(t, site)
        return clean(out)

    @app.post("/api/night")
    def night(req: NightReq):
        site = _site(req.site)
        d = date.fromisoformat(req.date) if req.date else tu.night_of(_time(req.time), site.tz)
        targets = [x.to_target() for x in req.targets]
        n, tr = plan_night(site, d, targets, step_min=req.step_min, airmass_model=req.airmass_model)
        return clean({"night": night_json(n, site), "tracks": {
            "jd": tr.jd, "last_h": tr.last_h, "sun_alt": tr.sun_alt, "moon_alt": tr.moon_alt,
            "alt": tr.alt, "airmass": tr.airmass, "ha_h": tr.ha_h, "moon_sep": tr.moon_sep,
            "parallactic": tr.parallactic, "names": [x.name for x in targets]}})

    @app.post("/api/hourly")
    def hourly(req: InstantReq):
        site, t = _site(req.site), _time(req.time)
        if not req.target:
            raise HTTPException(422, "hourly table needs a target")
        rows = hourly_table(site, tu.night_of(t, site.tz), req.target.to_target(), req.airmass_model)
        return clean({"rows": rows})

    @app.post("/api/seasonal")
    def seasonal(req: InstantReq):
        site, t = _site(req.site), _time(req.time)
        if not req.target or req.target.body:
            raise HTTPException(422, "seasonal table needs a fixed (non-solar-system) target")
        return clean({"rows": seasonal_table(site, t, req.target.to_target(), req.airmass_model)})

    @app.post("/api/sky")
    def sky(req: SkyReq):
        site, t = _site(req.site), _time(req.time)
        snap = sky_snapshot(site, t, [x.to_target() for x in req.targets])
        snap["arcs"] = reference_arcs(round(site.lat, 4))
        snap["time_info"] = time_info(t, site)
        return clean(snap)

    @app.post("/api/planets")
    def planets(req: InstantReq):
        site, t = _site(req.site), _time(req.time)
        ref = req.target.to_target() if req.target else None
        rows = []
        for p in PLANETS:
            inst = compute_instant(site, t, body_target(p), req.airmass_model)
            T = inst["target"]
            prox = None
            if ref is not None and not ref.is_body:
                prox = float(SkyCoord(T["icrs"]["ra_deg"] * u.deg, T["icrs"]["dec_deg"] * u.deg).separation(
                    ref.icrs_at(t)).deg)
            rows.append({"name": p.capitalize(), "body": p, "ra": T["apparent"]["ra_hms"],
                         "dec": T["apparent"]["dec_dms"], "ha": T["ha"], "alt_deg": T["alt_deg"],
                         "az_deg": T["az_deg"], "airmass": T["airmass"], "proximity_deg": prox,
                         "constellation": T["constellation"]})
        return clean({"rows": rows})

    # ---- static UI -------------------------------------------------------------
    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
    return app


def _zenith_target(site: Site, t: Time) -> Target:
    """JSkyCalc wakes up pointing at the zenith."""
    c = SkyCoord(alt=90 * u.deg, az=0 * u.deg, frame=AltAz(obstime=t, location=site.location)).icrs
    return Target(name="zenith", ra=float(c.ra.deg), dec=float(c.dec.deg))
