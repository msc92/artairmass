# artairmass — architecture & build plan

*artairmass* (≈ "Artemis"): a modern, offline-first replacement for JSkyCalc.
Feature inventory: [FEATURES.md](FEATURES.md).

## 1. Shape of the app

```
artairmass  (CLI)  ──►  uvicorn on 127.0.0.1:<free port>  ──►  opens browser (or chromeless --app window)
                          │
                          ├─ FastAPI JSON API  (/api/…)
                          └─ static frontend   (HTML/CSS/ES modules, vendored Plotly — no CDN, no Node build)
```

### Why a local web app, not PySide6
I recommend staying with the web app:
* **Plotly** gives hover, zoom, toggle-by-legend, linked axes and click-to-select for free;
  doing the same in Qt (pyqtgraph/QtCharts) is a lot more custom work and looks dated.
* Dark / red night-vision themes are a CSS-variable swap; Qt theming is fiddly.
* `pip install -e .` stays light (no 300 MB Qt wheel, no platform-specific GUI issues on
  observatory Linux boxes); works over an SSH tunnel to a summit machine.
* Downside — it lives in a browser tab. Mitigated with `artairmass --app`, which opens a
  chromeless Chrome/Edge window when one is available.

### Frontend without a toolchain
No npm/webpack: native ES modules + **vendored** `plotly.min.js` and **Preact + htm**
(~15 kB, components without a build step), shipped inside the Python package. Everything works
with the network unplugged.

## 2. Package layout

```
src/artairmass/
  cli.py              artairmass [serve|--app|--no-browser|update-data|selftest]
  config.py           settings & user sites (JSON in platformdirs user config dir)
  data/               sites.json, bright stars (V≤4.5), IERS snapshot hook, vendored JS
  core/
    timeutil.py       instants, IANA tz (zoneinfo+tzdata), JD/MJD, LMST/LAST, step units s/m/h/d/t/l
    sites.py          Site model → astropy EarthLocation
    targets.py        Target (ICRS + PM + epoch, equinox handling, galactic/ecliptic I/O, planets)
    ephem.py          Sun/Moon/planets via astropy get_body (built-in ERFA ephemeris, offline)
    kernel.py         fast vectorized alt/az/HA/airmass/parallactic on a time grid (see §4)
    airmass.py        Hardie (JSkyCalc parity), Young 1994, sec z
    almanac.py        sun/moon rise-set, 6/12/18° twilights, night centre, dark time
    skybright.py      Krisciunas & Schaefer 1991 moonlight, zenith twilight (ported, cited)
    bary.py           BJD_TDB, HJD, barycentric RV correction (astropy)
    instant.py        everything in JSkyCalc's main window for one instant
    hourly.py, seasonal.py, besttime.py, parallactic.py, planets.py, finder.py(🌐)
  io/
    parser.py         flexible target-list parser (N1) → rows with status/flags
    resolver.py       Sesame/SIMBAD with JSON cache + timeout, fails gracefully
  plots/static.py     matplotlib publication exports (PNG/PDF/SVG)
  api/                FastAPI routers (one per feature), pydantic models
  web/                index.html, css/, js/ (components), vendor/
tests/                pytest: parser, kernel vs full astropy, vs JSkyCalc fixtures, API smoke
validation/           JSkyCalc harness (jjs script), reference fixtures, VALIDATION.md
```

## 3. Offline & data policy
* **IERS**: astropy ships `astropy-iers-data`. At startup set `auto_download=False`; if the
  table is older than ~3 months, show a warning badge (UT1−UTC extrapolated; worst case
  ~sub-second LST error) — never crash. `artairmass update-data` refreshes it when online.
* **Ephemeris**: astropy `builtin` (ERFA) — no download. Sun/planets ≪ 1″, Moon a few ″:
  better than JSkyCalc. If a JPL kernel (de440s) is in the astropy cache it is used
  automatically (also enables Pluto).
* **Name resolution**: the only network feature; cached, 5 s timeout, clear error.
* Time zones: `tzdata` dependency, so DST is correct on any OS.

## 4. Speed strategy (50 objects × a night ≈ instant; × a year in a second or two)
Full astropy `AltAz` transforms per target per grid point are correct but slow for year-long
grids. So:
1. Per night (and site): compute Sun & Moon with full astropy on a 2-min grid — cached.
2. Per target per night: astropy gives the **apparent (CIRS/TETE) RA/Dec at midnight once**
   (precession, nutation, aberration, PM, all handled by astropy).
3. Alt/az/HA/airmass/parallactic over the grid via numpy spherical trig with astropy's
   apparent sidereal time — vectorized over targets × times.
4. A test asserts the fast kernel agrees with full astropy `AltAz` to < 1″ in altitude over a
   whole night (the apparent place drifts ≪ 1″ in 12 h).
Year analysis = 365 nights × N targets × ~150 samples — a few million trig ops.

## 5. Numerical conventions (choices you can override in Settings)
| Quantity | Default | Notes |
|---|---|---|
| Altitude | geometric (unrefracted) | as JSkyCalc; refracted optional |
| Airmass | Hardie 1962 | as JSkyCalc; Young 1994 optional |
| Twilight | astronomical (18°) for "dark"; 12° selectable | civil/nautical/astro bands all drawn |
| Rise/set | −0.833° + horizon dip from terrain height | as JSkyCalc |
| LST | apparent (LAST) displayed; mean also shown | |
| Night of date D | sunset on D → sunrise D+1; before local noon ⇒ previous night | as JSkyCalc |
| Semesters | A = Feb 1–Jul 31, B = Aug 1–Jan 31 | configurable |

## 6. UI sketch

```
┌─ artairmass ── Las Campanas (Magellan) ▾ ── 2026-10-07 ◂ ▸ ── Now ⟳ ── Local 21:14 CLST · UT 00:14 · LST 22:03 ─ ◐ 18% ─ IERS ✓ ─┐
│ ▸ Targets panel (left)          │  Tabs:  Now │ Night │ Season │ Sky │ Planets │ Tools                                    │
│  search / paste / drop          │                                                                                          │
│  list with visibility sparkline │  Night tab: airmass plot (Plotly) + summary table + almanac strip + hourly table          │
│  ☑ toggles, colour chips        │  Now tab:   JSkyCalc main-window quantities as grouped cards, warning colours            │
│                                 │  Season:    hours-observable vs date, semesters shaded, list heatmap, JSkyCalc table     │
└─────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────┘
```
* Themes: light, dark, **red night-vision** (pure red-on-black, dims plots too).
* Keyboard: `n` now · `f`/`b` step · `[`/`]` prev/next night · `1–6` tabs · `/` search ·
  `j`/`k` next/prev target · `t` theme · `r` red mode · `?` cheat sheet.
* Many targets on one plot: the first 8 get distinct, CVD-validated colours with direct labels;
  beyond that, curves are grey and the hovered/selected ones highlight.
* Tooltips on every quantity (definition + convention used).

## 7. Validation plan
* **JSkyCalc as oracle**: JSkyCalc's own classes are driven headless through Java 8's
  built-in `jjs` engine (no JDK install needed; already proven on this machine). A script
  generates reference fixtures for a matrix:
  sites {Las Campanas, Mauna Kea, Paranal, Kitt Peak, AAT/Siding Spring, La Palma} ×
  dates {solstices, equinox, both DST transitions per hemisphere} ×
  targets {circumpolar/near-pole (δ = ±85°), near-horizon (alt 2–10°), transit near
  zenith, typical cluster fields} →
  LST, HA, alt, az, airmass, parallactic, Moon/Sun positions, twilights, rise/set,
  BJD & RV corrections, sky brightness, seasonal table.
* Expected agreement: time ≲ few s, alt/az ≲ 40″ (JSkyCalc omits nutation & aberration),
  airmass ≲ 1e-3 below airmass 3, BJD ≲ 0.05 s, RV ≲ 5 m/s; every larger difference is
  explained in `validation/VALIDATION.md`.
* **Independent checks**: fast kernel vs full astropy; almanac vs astroplan;
  a few JPL Horizons values saved as fixtures (fetched once).
* Parser: ~100 messy real-world lines (NED/SIMBAD/ALMA/ESO exports, JSkyCalc lists, TSV
  from spreadsheets, unicode °′″, mixed signs like `-00 12 03`).
* Before "done": launch the app and exercise every feature (scripted browser run +
  screenshots), dark/red modes included.

## 8. Stages (one git commit each)
0. Inventory + plan *(this commit)*
1. Package skeleton, config, sites, time, core calculations + JSkyCalc fixture harness + tests
2. API + GUI shell (Now tab, site/time controls, themes, shortcuts, sky chart)
3. List input (parser, resolver, preview/fix UI) + tests
4. Night: airmass plots, summary, almanac, hourly, exports
5. Season: JSkyCalc seasonal table, best-time-of-year, heatmap, semesters
6. Planets, alt coords, parallactic tool, finder chart, radio/space extras, polish,
   VALIDATION.md, README, full click-through

## 9. Open decisions (my default in **bold**)
1. Finder chart / ds9 parity: **in-app HiPS finder (network-only), with SAMP/XPA "send to
   ds9" if ds9 is running**, or drop it?
2. Radio mode (ALMA/ATCA: LST-range view, no twilight, Sun avoidance): **include**?
3. Space-observatory solar-elongation view (JWST 85–135°, HST/Chandra Sun avoidance as
   editable presets, labelled approximate): **include as a small stage-6 extra**?
4. Default site on first launch: **Las Campanas**?
