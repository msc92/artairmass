"""Fast Sun/Moon/sidereal-time model over a time span for one site.

astropy computes the exact apparent topocentric (TETE) places of the Sun and Moon and the
apparent sidereal time on a coarse grid of knots; between knots the places are cubic-spline
interpolated and LAST linearly interpolated (it is linear in UT1 to ≪ 1 ms over an hour).
Altitude/azimuth then follow from spherical trig. ``tests/test_skymodel.py`` checks this
against full astropy ``AltAz`` (pressure = 0): agreement is ≲ 1″ for knots of 1 h.

Neglected (all < 1″): polar motion in the alt/az step, diurnal aberration.
"""

from __future__ import annotations


import astropy.units as u
import numpy as np
from astropy.coordinates import TETE, get_body
from astropy.time import Time
from scipy.interpolate import CubicSpline

from . import kernel
from .sites import Site

BODIES = ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune")


def last_rad(t: Time, site: Site) -> np.ndarray:
    """Local apparent sidereal time (rad), exact via astropy."""
    return np.asarray(t.sidereal_time("apparent", longitude=site.lon * u.deg).rad)


def body_tete(body: str, t: Time, site: Site):
    """Apparent topocentric RA/Dec (rad, true equator & equinox of date) and distance (AU)."""
    loc = site.location
    c = get_body(body, t, loc).transform_to(TETE(obstime=t, location=loc))
    return (np.asarray(c.ra.rad), np.asarray(c.dec.rad),
            np.asarray(c.distance.to_value(u.AU)))


class SkyModel:
    """Interpolating ephemeris for ``site`` covering [jd_start, jd_end] (UTC JD)."""

    def __init__(self, site: Site, jd_start: float, jd_end: float,
                 knot_hours: float = 1.0, bodies=("sun", "moon")):
        self.site = site
        self.lat = np.radians(site.lat)
        step = knot_hours / 24.0
        n = int(np.ceil((jd_end - jd_start) / step)) + 5
        self.knots = jd_start - 2 * step + step * np.arange(n)
        tk = Time(self.knots, format="jd", scale="utc")
        self._last_knots = np.unwrap(last_rad(tk, site))
        self._splines = {}
        for b in bodies:
            ra, dec, dist = body_tete(b, tk, site)
            self._splines[b] = (CubicSpline(self.knots, np.unwrap(ra)),
                                CubicSpline(self.knots, dec),
                                CubicSpline(self.knots, dist))

    @property
    def jd_range(self) -> tuple[float, float]:
        return float(self.knots[2]), float(self.knots[-3])

    def last(self, jd) -> np.ndarray:
        return np.mod(np.interp(jd, self.knots, self._last_knots), kernel.TWO_PI)

    def radec(self, body: str, jd):
        sra, sdec, sdist = self._splines[body]
        return np.mod(sra(jd), kernel.TWO_PI), sdec(jd), sdist(jd)

    def body_altaz(self, body: str, jd):
        """(alt_deg, az_deg, ha_rad) of a body at UTC JDs."""
        ra, dec, _ = self.radec(body, jd)
        ha = kernel.wrap_pi(self.last(jd) - ra)
        alt, az = kernel.altaz(ha, dec, self.lat)
        return np.degrees(alt), np.degrees(az), ha

    def sun_alt(self, jd):
        return self.body_altaz("sun", jd)[0]

    def moon_alt(self, jd):
        return self.body_altaz("moon", jd)[0]

    def target_altaz(self, ra, dec, jd):
        """Alt/az for fixed apparent (TETE) places.

        ``ra``/``dec`` (rad) broadcast against ``jd``; pass shape (N, 1) vs (T,) to get (N, T).
        Returns alt_deg, az_deg, ha_rad, parallactic_rad.
        """
        ha = kernel.wrap_pi(self.last(jd) - ra)
        alt, az = kernel.altaz(ha, dec, self.lat)
        q = kernel.parallactic_angle(ha, dec, self.lat)
        return np.degrees(alt), np.degrees(az), ha, q
