"""Sky-brightness estimates ported verbatim from JSkyCalc (``SkyIllum``).

* ``lunar_sky_brightness`` — scattered moonlight, Krisciunas & Schaefer (1991, PASP 103,
  1033), in V mag/arcsec². Returns 99 when the moon contributes negligibly.
* ``zenith_twilight`` — zenith twilight brightness in blue magnitudes relative to the dark
  sky (polynomial fit in Sun altitude between 0° and −18°): 0 = no twilight, 99 = daytime.
"""

from __future__ import annotations

import numpy as np

EARTH_RADII_PER_AU = 23454.7910556298
MEAN_MOON_DIST_ER = 60.27
DEFAULT_KZEN = 0.172  # V-band zenith extinction JSkyCalc assumes


def lunar_sky_brightness(elong_deg, rho_deg, alt_moon_deg, alt_obj_deg, moon_dist_au,
                         kzen: float = DEFAULT_KZEN):
    """Moonlight surface brightness (V mag/arcsec²) at a target.

    elong_deg: Sun–Moon elongation; rho_deg: Moon–target angle; moon_dist_au: topocentric
    Moon distance. Vectorized over all inputs. Matches JSkyCalc's arithmetic, including
    its use of 1/sqrt(1 − 0.96 sin² z) as the airmass.
    """
    elong, rho, altm, alto, dist = np.broadcast_arrays(
        *(np.asarray(v, dtype=float) for v in (elong_deg, rho_deg, alt_moon_deg, alt_obj_deg, moon_dist_au)))
    alpha = 180.0 - elong  # phase angle
    zm = np.radians(90.0 - altm)
    zo = np.radians(90.0 - alto)
    dist_rel = EARTH_RADII_PER_AU * dist / MEAN_MOON_DIST_ER

    istar = 10.0 ** (-0.4 * (3.84 + 0.026 * np.abs(alpha) + 4.0e-9 * alpha**4)) / dist_rel**2
    istar = np.where(np.abs(alpha) < 7.0, istar * (1.35 - 0.05 * np.abs(istar)), istar)

    rho_r = np.radians(rho)
    fp = 229087.0 * (1.06 + np.cos(rho_r) ** 2)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        fp = fp + np.where(np.abs(rho) > 10.0, 10.0 ** (6.15 - rho / 40.0),
                           np.where(np.abs(rho) > 0.25, 6.2e7 / rho**2, 9.9e8))
        xm = np.sqrt(1.0 - 0.96 * np.sin(zm) ** 2)
        xm = np.where(xm != 0.0, 1.0 / xm, 10000.0)
        xo = np.sqrt(1.0 - 0.96 * np.sin(zo) ** 2)
        xo = np.where(xo != 0.0, 1.0 / xo, 10000.0)
        bmoon = fp * istar * 10.0 ** (-0.4 * kzen * xm) * (1.0 - 10.0 ** (-0.4 * kzen * xo))
        mag = np.where(bmoon > 0.001, 22.5 - 1.08574 * np.log(bmoon / 34.08), 99.0)
    return mag if mag.ndim else float(mag)


def zenith_twilight(sun_alt_deg):
    alt = np.asarray(sun_alt_deg, dtype=float)
    x = (-alt - 9.0) / 9.0
    poly = ((2.0635175 * x + 1.246602) * x - 9.4084495) * x + 6.132725
    out = np.where(alt > 0.0, 99.0, np.where(alt < -18.0, 0.0, poly))
    return out if out.ndim else float(out)
