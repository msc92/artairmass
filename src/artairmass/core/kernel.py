"""Vectorized spherical astronomy on numpy arrays (radians in, radians out).

These are the hot loops; the astrometry that feeds them (apparent places, sidereal time)
comes from astropy. Conventions: azimuth from north through east; hour angle west-positive;
parallactic angle = position angle of the zenith direction measured N through E.
"""

from __future__ import annotations

import numpy as np

TWO_PI = 2.0 * np.pi


def wrap_pi(x):
    """Wrap angle to (−π, π]."""
    return np.pi - np.mod(np.pi - x, TWO_PI)


def altaz(ha, dec, lat):
    sin_alt = np.sin(lat) * np.sin(dec) + np.cos(lat) * np.cos(dec) * np.cos(ha)
    alt = np.arcsin(np.clip(sin_alt, -1.0, 1.0))
    az = np.arctan2(-np.cos(dec) * np.sin(ha),
                    np.sin(dec) * np.cos(lat) - np.cos(dec) * np.cos(ha) * np.sin(lat))
    return alt, np.mod(az, TWO_PI)


def parallactic_angle(ha, dec, lat):
    return np.arctan2(np.sin(ha), np.tan(lat) * np.cos(dec) - np.sin(dec) * np.cos(ha))


def separation(ra1, dec1, ra2, dec2):
    """Angular distance (Vincenty formula: stable at all separations)."""
    dra = ra2 - ra1
    s1, c1 = np.sin(dec1), np.cos(dec1)
    s2, c2 = np.sin(dec2), np.cos(dec2)
    num = np.hypot(c2 * np.sin(dra), c1 * s2 - s1 * c2 * np.cos(dra))
    den = s1 * s2 + c1 * c2 * np.cos(dra)
    return np.arctan2(num, den)


def ha_at_altitude(alt, dec, lat):
    """|HA| (rad) at which a source of declination ``dec`` reaches altitude ``alt``.

    Returns 0 where it never gets that high, π where it never gets that low.
    """
    cos_h = (np.sin(alt) - np.sin(lat) * np.sin(dec)) / (np.cos(lat) * np.cos(dec))
    return np.arccos(np.clip(cos_h, -1.0, 1.0))
