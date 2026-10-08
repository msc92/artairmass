"""Astropy configuration for fully offline operation.

Policy
------
* astropy never touches the network on its own (``allow_internet = False``).
* Earth-orientation (IERS-A) data come from the newest of: a table previously fetched
  with ``artairmass update-data`` (astropy download cache) or the table bundled in
  ``astropy-iers-data``.
* Stale or out-of-range IERS data only produce a warning badge in the UI — never an
  exception. Beyond the table, UT1−UTC and polar motion are extrapolated/defaulted,
  which costs at most ~1 s in sidereal time and ~arcsec in pointing.
* The ephemeris is astropy's ``builtin`` (ERFA) model, which needs no download. If a JPL
  kernel is already in the astropy cache it is used instead.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass

from astropy.time import Time
from astropy.utils import data as astropy_data
from astropy.utils import iers

log = logging.getLogger(__name__)

STALE_AFTER_DAYS = 90  # IERS-A predictions older than this get a warning badge

_JPL_KERNELS = ("de440s", "de432s", "de430")
_configured = False
ephemeris_name = "builtin"


def configure() -> None:
    """Idempotently put astropy into offline mode and load the best local IERS table."""
    global _configured, ephemeris_name
    if _configured:
        return
    astropy_data.conf.allow_internet = False
    iers.conf.auto_download = False
    iers.conf.auto_max_age = None
    iers.conf.iers_degraded_accuracy = "warn"
    _load_cached_iers_if_newer()
    ephemeris_name = _pick_ephemeris()
    # Out-of-range polar motion / UT1 warnings are reported once via iers_status().
    warnings.filterwarnings("ignore", message=".*polar motion.*")
    warnings.filterwarnings("ignore", message=".*IERS.*", category=Warning)
    warnings.filterwarnings("ignore", category=iers.IERSStaleWarning)
    # Beyond the leap-second table ERFA flags every date as a "dubious year": expected, since
    # future leap seconds are unknown (≤ 1 s effect); reported once via iers_status().
    warnings.filterwarnings("ignore", message=".*dubious year.*")
    _configured = True


def predictive_mjd(table) -> float:
    """First MJD whose Earth-orientation values are predictions, not measurements.

    astropy ≥ 7 records this in ``table.meta``; older versions only flag rows ('P')."""
    meta = getattr(table, "meta", {}) or {}
    if "predictive_mjd" in meta:
        return float(meta["predictive_mjd"])
    mjd = table["MJD"]
    mjd = getattr(mjd, "value", mjd)
    for col in ("UT1Flag", "UT1Flag_A", "PolPMFlag", "PolPMFlag_A"):
        if col in table.colnames:
            flags = [str(f).strip() for f in table[col]]
            for k, f in enumerate(flags):
                if f == "P":
                    return float(mjd[k])
    return float(mjd[-1]) - 365.0  # conservative: treat the last year as predicted


def _cached_path(url: str) -> str | None:
    try:
        return astropy_data.cache_contents().get(url)
    except Exception:  # cache unreadable / missing
        return None


def _load_cached_iers_if_newer() -> None:
    bundled = iers.IERS_Auto.open()
    for url in (iers.conf.iers_auto_url, iers.conf.iers_auto_url_mirror):
        path = _cached_path(url)
        if not path:
            continue
        try:
            cached = iers.IERS_Auto.read(file=path)
        except Exception as err:  # corrupt cache entry: ignore it
            log.warning("ignoring unreadable cached IERS table %s: %s", path, err)
            continue
        if predictive_mjd(cached) > predictive_mjd(bundled):
            iers.IERS_Auto.iers_table = cached
            iers.earth_orientation_table.set(cached)
        return


def _pick_ephemeris() -> str:
    from astropy.coordinates import solar_system_ephemeris

    try:
        cached_urls = list(astropy_data.cache_contents())
    except Exception:
        cached_urls = []
    for name in _JPL_KERNELS:
        if any(u.endswith(f"/{name}.bsp") for u in cached_urls):
            try:
                solar_system_ephemeris.set(name)  # resolves from cache, no network
                return name
            except Exception:
                pass
    solar_system_ephemeris.set("builtin")
    return "builtin"


@dataclass
class IERSStatus:
    predictive_start: str   # first predicted (non-final) date in the table
    table_end: str          # last date covered at all
    age_days: float         # how old the predictions are
    stale: bool
    ephemeris: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def iers_status() -> IERSStatus:
    table = iers.IERS_Auto.open()
    pred = Time(predictive_mjd(table), format="mjd")
    end = Time(float(table["MJD"][-1].value), format="mjd")
    age = float(Time.now().mjd - pred.mjd)
    return IERSStatus(
        predictive_start=pred.iso[:10],
        table_end=end.iso[:10],
        age_days=round(age, 1),
        stale=age > STALE_AFTER_DAYS,
        ephemeris=ephemeris_name,
    )


def update_data(timeout: float = 20.0) -> str:
    """Download fresh IERS-A + leap seconds into the astropy cache (needs network)."""
    astropy_data.conf.allow_internet = True
    old_timeout = astropy_data.conf.remote_timeout
    astropy_data.conf.remote_timeout = timeout
    try:
        urls = (iers.conf.iers_auto_url, iers.conf.iers_auto_url_mirror)
        path = astropy_data.download_file(urls[0], sources=urls, cache="update")
        table = iers.IERS_Auto.read(file=path)
        iers.IERS_Auto.iers_table = table
        iers.earth_orientation_table.set(table)
        try:
            iers.LeapSeconds.auto_open(
                [iers.IERS_LEAP_SECOND_URL, iers.IETF_LEAP_SECOND_URL])
        except Exception as err:  # leap seconds rarely matter; don't fail the update
            log.warning("leap-second update failed: %s", err)
        return f"IERS-A updated; predictions start {Time(predictive_mjd(table), format='mjd').iso[:10]}"
    finally:
        astropy_data.conf.allow_internet = False
        astropy_data.conf.remote_timeout = old_timeout
