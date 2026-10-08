# Validation of artairmass against JSkyCalc

## Method

JSkyCalc itself is the reference: `validation/harness/jskycalc_oracle.js` drives the
original `JSkyCalc.jar` classes headless through Java 8's Nashorn engine (`jjs`) and records
what JSkyCalc computes for every case — no hand-transcription from its GUI.
`validation/make_cases.py` builds the matrix; `validation/compare.py` computes the same
quantities with artairmass and reports the differences; `tests/test_vs_jskycalc.py` turns the
table below into regression tests with explicit tolerances.

    validation/run_jskycalc.sh         # regenerate reference values (needs jjs + jar)
    python validation/compare.py       # summary
    pytest tests/test_vs_jskycalc.py   # tolerances

**Matrix** — 27 site/instant cases × 12 targets = 324 target evaluations:

* **Sites** (JSkyCalc's own coordinates, so geography is identical): Las Campanas, Paranal,
  Mauna Kea, Kitt Peak, Palomar, AAT/Siding Spring, La Palma, DAO Victoria — latitudes −31°
  to +48.5°.
* **Instants**: evenings either side of every 2026 DST change in both hemispheres (US Mar 8 /
  Nov 1, Chile Apr 5 / Sep 6, Australia Apr 5 / Oct 4, EU Mar 29 / Oct 25), both solstices,
  the March equinox, and pre-dawn times.
* **Targets**: galaxy-cluster fields (A1795, Perseus, Phoenix, Hydra A), near-pole sources at
  δ = ±85° and −89.2°, a B1950 position (3C 273), and four synthetic targets placed 3°–8° above
  the horizon (N, E, S, W) at each instant.
* **Seasonal Observability** table for A1795 from 8 sites (128 rows × 3 HA, 3 airmass, 3 hours).

## Results

| Quantity | N | median abs Δ | 95th pct | max abs Δ | worst case |
|---|---:|---:|---:|---:|---|
| LMST [s] | 27 | 0.0493 | 0.113 | 0.118 | dao-1  |
| LAST vs JSkyCalc LMST [s] | 27 | 0.462 | 0.571 | 0.573 | lco-3  |
| Sun alt [arcsec] | 27 | 15.4 | 21 | 21.5 | lapalma-0  |
| Sun az [arcsec] | 27 | 12.3 | 24 | 25.6 | dao-0  |
| Moon alt [arcsec] | 27 | 3.14 | 6.72 | 7.6 | paranal-0  |
| Moon az [arcsec] | 27 | 4.67 | 9.19 | 9.27 | maunakea-0  |
| Moon illuminated fraction | 27 | 0.000897 | 0.00132 | 0.00133 | dao-0  |
| Zenith twilight [mag] | 27 | 0 | 1.71e-05 | 0.00181 | paranal-0  |
| Moon phase text [days] | 27 | 0 | 0 | 0 | lco-0  |
| Sunset [s] | 27 | 0.362 | 0.923 | 1.08 | lco-4 2026-06-20 |
| Sunrise [s] | 27 | 2.15 | 3.05 | 4.06 | dao-0 2026-06-21 |
| 18° twilight (evening) [s] | 26 | 1.28 | 1.87 | 2.01 | lco-4 2026-06-20 |
| 18° twilight (morning) [s] | 26 | 1.17 | 1.8 | 2.36 | kpno-2 2026-06-21 |
| Night centre [s] | 27 | 1.35 | 1.74 | 1.76 | lco-4 2026-06-20 |
| Moonrise [s] | 26 | 1.88 | 4.93 | 6 | dao-0 2026-06-21 |
| Moonset [s] | 26 | 0.881 | 2.62 | 6.25 | lapalma-1 2026-10-25 |
| Hour angle × cos δ [arcsec] | 324 | 13.4 | 24 | 31.2 | paranal-1 SPole89 |
| Hour angle, \|δ\| < 80° [s] | 243 | 1.09 | 2.66 | 5.62 | paranal-1 LowSouth |
| Altitude [arcsec] | 324 | 11.2 | 22.8 | 26.5 | lco-3 Phoenix_cl |
| Azimuth × cos(alt) [arcsec] | 324 | 11.1 | 24.3 | 26.7 | lapalma-2 LowNorth |
| Parallactic angle [arcsec] | 243 | 9.57 | 45.7 | 129 | kpno-1 Perseus |
| Mean place of date [arcsec] | 324 | 0.0683 | 0.439 | 0.441 | lapalma-2 3C273_B1950 |
| Galactic l,b [arcsec] | 324 | 0.391 | 0.529 | 0.534 | dao-0 LowEast |
| Constellation (mismatches) | 324 | 0 | 0 | 0 | lco-0 A1795 |
| Moon–object angle [arcsec] | 324 | 14.4 | 21.8 | 25.6 | maunakea-2 Perseus |
| Bary. JD (UTC-based, JSkyCalc def.) [s] | 324 | 0.00764 | 0.0199 | 0.0274 | lco-5 A1795 |
| Bary. light-time [s] | 324 | 0.00764 | 0.0199 | 0.0274 | lco-5 A1795 |
| Bary. RV correction [m/s] | 324 | 4.63 | 6.23 | 7.03 | lapalma-1 LowSouth |
| Parallax factors | 324 | 1.18e-05 | 1.95e-05 | 2.37e-05 | paranal-1 SPole89 |
| Seasonal: evening date (mismatches) | 128 | 0 | 0 | 0 | lco-0 New |
| Seasonal: HA [min] | 384 | 0 | 1 | 1 | lco-0 Full morn |
| Seasonal: hours observable [h] | 384 | 0.02 | 0.05 | 0.07 | dao-0 New <1.5 |
| Airmass (relative, alt > 10°) | 97 | 8.07e-05 | 0.000318 | 0.000524 | kpno-0 A1795 |
| Lunar sky brightness [mag] | 95 | 9.35e-05 | 0.000205 | 0.00024 | lapalma-1 LowWest |
| Airmass (relative, 0° < alt < 10°) | 117 | 0.000468 | 0.00193 | 0.00434 | maunakea-0 A1795 |
| 18° twilight: JSkyCalc degenerate cases | 2 | 0 | 0 | 0 | dao-0 2026-06-21 |

(Angles in arcsec unless noted; times in seconds. "N" = number of comparisons.)

## Interpretation

Everything agrees to the level expected from the known modelling differences. All of the
residuals are explained; none indicate a bug on either side.

* **Formula ports are exact.** Hardie airmass, Krisciunas & Schaefer moonlight, and the
  zenith-twilight polynomial reproduce JSkyCalc to 1e-12 when fed JSkyCalc's own inputs
  (`tests/test_airmass_skybright.py`).
* **Alt/az, HA, Moon–object angle: 10–30″.** JSkyCalc points with *mean* places precessed to
  date; it omits nutation (up to ~17″) and annual aberration (up to 20.5″). artairmass uses
  astropy's full apparent place (IAU 2006/2000A, aberration, light deflection). The mean place
  of date itself agrees to 0.07″ median, confirming the precession is the same and the
  difference is entirely nutation + aberration. In time units the hour angle agrees to ~1 s
  (|δ| < 80°); the near-pole HA differences look larger only because of the 1/cos δ factor —
  on the sky they are the same ≤ 31″.
* **Sun position: 15–25″.** Same cause: JSkyCalc's Sun lacks the 20.5″ annual aberration.
* **Moon: 3–9″**, consistent with JSkyCalc's stated ~10″ lunar theory.
* **Sidereal time.** JSkyCalc shows *mean* sidereal time computed from UTC; artairmass's LMST
  uses UT1, so they differ by UT1 − UTC (≤ 0.12 s here). artairmass also displays *apparent*
  sidereal time (which is what an hour angle should be measured from); it differs from
  JSkyCalc's LMST by the equation of the equinoxes (~0.5 s in 2026).
* **Rise/set and twilight: ≤ 6 s.** artairmass solves for the crossing numerically on the
  full ephemeris; JSkyCalc iterates an analytic approximation. Both use −(0.83° + horizon dip).
* **Barycentric time: ≤ 0.03 s; RV correction: 4–7 m/s.** JSkyCalc uses its own low-order
  planetary model for the solar-system barycentre ("a few m/s" in its manual); astropy uses the
  ERFA ephemeris (mm/s level). Note JSkyCalc's "Bary. JD" is UTC + light-time; artairmass shows
  that *and* the standard BJD_TDB (Eastman et al. 2010), which is larger by TT − UTC + (TDB − TT)
  ≈ 69.18 s.
* **Moon illuminated fraction: 0.001.** Both are topocentric; the remainder is JSkyCalc's
  elongation-based approximation of the phase angle.
* **Parallactic angle: ≤ 0.04°**, larger near the zenith where it changes fastest with
  position (the 129″ case is Perseus 8° from the zenith at Kitt Peak).
* **B1950 input (0.44″).** JSkyCalc precesses B1950 mean positions with the IAU 1976 matrix
  without the FK4 E-terms or equinox correction; artairmass treats pre-1984 equinoxes as FK4.
* **Airmass.** Above 10° altitude: 0.05 % worst. Below 10° the 20″ altitude difference above
  becomes up to 0.4 % in airmass at 1° altitude — the airmass gradient there is enormous.
* **Seasonal table.** Identical dates for all 128 rows, HA within the 1-minute display
  rounding, hours observable within 0.07 h (JSkyCalc integrates analytically; artairmass
  samples the actual track each minute).

### Cases with a larger, expected difference

* **Marginal astronomical darkness (DAO, 48.5°N, June solstice).** The Sun reaches only
  −18.04°. artairmass finds the real 23-minute window of astronomical darkness around
  midnight; JSkyCalc's analytic shortcut declares "no 18° twilight" and reports local
  midnight for both. These 2 cases are listed separately rather than counted as residuals.
* **DST rules.** JSkyCalc hard-codes DST rules by region code. All comparisons above are made
  in UTC/JD, so they are unaffected; artairmass derives local time from the IANA tz database
  (`tests/test_timeutil.py` checks the 2026 Chilean and US transitions).

## Independent cross-checks (not JSkyCalc)

* `tests/test_skymodel.py`: the fast interpolating engine vs astropy's full `AltAz` chain —
  < 1″ for fixed targets (including proper motion and near-pole sources), < 1.5″ for Sun and
  Moon, < 3″ for planets; interpolated sidereal time < 1 ms.
* `tests/test_almanac.py`: Sun rise/set and civil/nautical/astronomical twilights vs astroplan
  within 15 s (astroplan's own grid interpolation limit); polar day/night handled.

## The running application

Beyond the numerical tests, the real app was driven end to end in headless Chromium
(`scripts/uicheck_full.py`), 15 scenarios, all passing with no browser console errors:
site search/switch and custom sites; typed times, step forward/back, a sidereal-day step
(LST unchanged, as it must be), night navigation, live clock; adding targets by coordinates,
planet name and SIMBAD name; the Now view's coordinate editor; filtering, keyboard
navigation, hiding and removing targets; list import with name look-up, save, sort, JSkyCalc
export; the Night plot (altitude/airmass axis, limit, click-to-set-time, PNG/PDF/SVG/CSV
exports, hourly CSV, multi-night run); the Season view (selected/list, Moon presets, heatmap,
JSkyCalc table); the sky chart (click select, zoom keys, `h` bright star, `c` cursor target);
the planet table; every tool; settings persistence; help and all three themes.

Offline behaviour was checked with all non-local network traffic blocked and
`ARTAIRMASS_OFFLINE=1`: name look-ups and finder images fail with a clear message, everything
else works. Dates beyond the IERS table (e.g. 2031) compute normally.

Two bugs found by the click-through and fixed: typed times displayed one second early
(JD float round-off; displays now round to the nearest second), and the sky chart's `c`
(new target at cursor) read a stale copy of the sky data.
