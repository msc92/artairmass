"""Airmass formulae. All take *geometric* (unrefracted) altitude in degrees.

``hardie`` is the default and reproduces JSkyCalc exactly (``Spherical.true_airmass``):
Hardie (1962) polynomial in (sec z − 1), switching to sec z − 1.5 beyond sec z = 12.
Below the horizon the result is NaN (JSkyCalc returns −1 there).
"""

from __future__ import annotations

import numpy as np

_HARDIE = (0.002879465, 0.003033104, 0.001351167, -4.716679e-5)
MODELS = ("hardie", "young", "secz")


def secz(alt_deg):
    alt = np.asarray(alt_deg, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        x = 1.0 / np.sin(np.radians(alt))
    return np.where(alt > 0, x, np.nan)


def hardie(alt_deg):
    s = secz(alt_deg)
    sm1 = s - 1.0
    poly = ((( _HARDIE[3] * sm1 + _HARDIE[2]) * sm1 + _HARDIE[1]) * sm1 + _HARDIE[0]) * sm1
    return np.where(s > 12.0, s - 1.5, s - poly)


def young(alt_deg):
    """Young (1994) interpolative formula; well-behaved down to the horizon."""
    alt = np.asarray(alt_deg, dtype=float)
    c = np.cos(np.radians(90.0 - alt))  # cos z_true
    num = 1.002432 * c**2 + 0.148386 * c + 0.0096467
    den = c**3 + 0.149864 * c**2 + 0.0102963 * c + 0.000303978
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(alt > 0, num / den, np.nan)


def airmass(alt_deg, model: str = "hardie"):
    if model == "hardie":
        return hardie(alt_deg)
    if model == "young":
        return young(alt_deg)
    if model == "secz":
        return secz(alt_deg)
    raise ValueError(f"unknown airmass model {model!r}; choose from {MODELS}")


def alt_for_airmass(x: float, model: str = "hardie") -> float:
    """Geometric altitude (deg) at which the airmass equals ``x`` (bisection; monotonic)."""
    if x < 1.0:
        raise ValueError("airmass must be >= 1")
    lo, hi = 0.01, 90.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if float(airmass(mid, model)) > x:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
