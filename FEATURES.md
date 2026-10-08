# JSkyCalc feature inventory → artairmass

Source of truth for this inventory: the bundled `usermanual.html` (v1.6, rev. 2016) and the
CFR-decompiled class files from `JSkyCalc.jar` (`reference/jskycalc-src/`, ~7.9 k lines). Every
window, control, output field and table column found there is listed below, with notes on the
underlying algorithm where it matters for numerical parity.

Legend for the **artairmass** column: ✅ parity (same feature) · ⬆ parity + improvement ·
🔁 replaced by a better equivalent · 🌐 needs network (optional, fails gracefully).

---

## 1. Main window ("green banner")

### 1.1 Inputs
| JSkyCalc input | Behaviour / accepted formats | artairmass |
|---|---|---|
| **Object** name | Typing an exact list name + Enter selects it from loaded lists | ⬆ fuzzy search box over all lists + planets + SIMBAD/Sesame 🌐 |
| **RA** | `18 19 20.12`, `18:19:20.12`, decimal hours `18.322255`, decimal degrees `274.83383 d` | ⬆ adds `18h19m20.12s`, auto-detect, explicit unit override |
| **Dec** | sexagesimal (space/colon) or decimal degrees | ⬆ adds `+56d01m02s`, `56°01'02"` |
| **Equinox** | Usually 2000; **negative value ⇒ equinox of date** | ✅ (plus J/B prefixes, `ICRS`, `date`) |
| **Date** | `2014 1 04`, `2014 Jan 04`, `2014 January 04` (day of week appended on output) | ⬆ also ISO 8601, date picker |
| **Time** | `20 15 17.3`, `20 15`, `20`, decimal hours | ⬆ also ISO, time picker |
| **Time is:** UT / Local toggle | Switching re-expresses the same instant | ✅ (both always shown; input in either) |
| **Timestep** | number + unit: `s m h d`, `t` = sidereal day, `l` = lunation | ✅ same units |
| **Sleep for (s)** | interval for Auto Update / Auto Step | ✅ |
| **JD** | shows JD; typing a JD + Enter sets the time | ✅ (+ MJD input) |
| Site fields: name, longitude (with unit/sense e.g. `D E`, `H W`), latitude, std-time offset, **DST code** (0 none, 1 US, 2 Spanish/EU, −1 Chile, −2 Australia), zone name, zone abbrev, elevation, **terrain elevation** (height above the horizon-forming terrain, used for horizon dip in rise/set) | editable only after "Enable User Input" in site menu | 🔁 IANA time zones (`America/Santiago` etc.) replace DST codes; terrain elevation kept |

### 1.2 Outputs (instantaneous circumstances)
| Field | Definition in JSkyCalc | artairmass |
|---|---|---|
| **Sidereal** | Local *mean* sidereal time (GMST formula, IAU 1982) | ✅ LMST + LAST shown |
| **HA** | hour angle, negative = east; turns orange when \|HA\| > 6 h | ✅ |
| **Airmass** | "true airmass": Hardie (1962) polynomial in (sec z − 1) on *unrefracted* altitude; sec z − 1.5 above sec z = 12; warning colours at 2 / 3 / 4 | ✅ Hardie by default (parity); option for Young (1994) / plane-parallel |
| **AltAz** | unrefracted altitude, azimuth | ✅ (+ optional refracted) |
| **parallactic** | parallactic angle and its 180° opposite | ✅ |
| **SunRAdec** | topocentric Sun, equinox of date (~1″) | ✅ |
| **SunAltAz** | unrefracted | ✅ |
| **ZTwilight** | zenith twilight brightness in blue mag (polynomial in Sun altitude, 0 to −18°); colour-coded; "Daytime" if Sun up | ✅ ported formula |
| **MoonPhase** | text, e.g. "3.2 days after full moon." | ✅ |
| **MoonRAdec** | topocentric Moon, equinox of date (~10″) | ✅ |
| **MoonAltAz** | unrefracted | ✅ |
| **MoonIllumFrac** | illuminated fraction | ✅ |
| **LunSkyBrght** | scattered-moonlight sky brightness, V mag/arcsec², Krisciunas & Schaefer (1991) with k = 0.172; elaborate warning colours | ✅ ported formula (+ total sky = dark sky ⊕ moon ⊕ twilight) |
| **Moon-Obj ang.** | topocentric Moon–target separation, colour warnings | ✅ |
| **Bary. JD** | barycentric JD and correction in seconds (~0.01 s) | ✅ (astropy; also HJD for parity with old logs) |
| **Bary. Vcorrn.** | km/s to *add* to observed RV (≲ few m/s accuracy) | ✅ astropy `radial_velocity_correction` (cm/s level) |
| **Constellation** | Roman (1987) algorithm | ✅ astropy `get_constellation` (same algorithm) |
| **Planet Warning?** | lights up near a planet; red within ~1° of a bright one | ✅ |
| Object URL line + **Send** button | opens the object's attached URL/file | ✅ clickable link |

### 1.3 Control buttons
Refresh output · Set to Now · Step Forward · Step Back · **Auto Update** (track the clock) ·
**Auto Step** (animate: step, sleep, repeat) · Quit · toggles for every window below
(Site Menu, Sky Display, Hourly, Nightly Almanac, Seasonal, Planet Table, Object Lists,
Alt. Coordinates, Airmass Graphs, Parallactic…, ds9…, Help). → all ✅
(Auto Step becomes an animation "play" control.)

### 1.4 Variants
* **Large-type version** (bigger fonts for hi-DPI laptops) → 🔁 UI scale setting.

---

## 2. Site Menu window
* Radio-button list of sites read from `skycalcsites.dat` (first entry = default site;
  default is Kitt Peak). Changing site keeps the **same UT** (local time jumps).
* "Enable User Input" button to type a custom site.
* Built-in sites (20): Kitt Peak [MDM], Shattuck (Dartmouth), SAAO Sutherland, VLT Paranal,
  Mauna Kea, Cerro Tololo, Gemini South Pachón, Las Campanas, ESO La Silla, Palomar, Lick,
  McDonald, AAT, DAO Victoria, Mont Mégantic, Mt Hopkins, Mt Graham, La Palma, Calar Alto
  (+ commented OHP).

→ ⬆ larger bundled list (incl. Chajnantor/ALMA, Narrabri/ATCA, MRO/ASKAP, SALT, Rubin,
Siding Spring, Parkes, VLA, GBT, MeerKAT, etc.), user sites saved to a config file, searchable,
favourites, set-as-default.

## 3. Sky Display window
* All-sky alt-az map: stars to V = 4.5 (bundled `brightest.dat`, 904 stars, colour by
  spectral type), Sun, Moon (exaggerated size, **correct phase and cusp orientation**),
  planets incl. Pluto (size by magnitude), loaded list objects as text labels.
* Current coordinates marked with a light-blue square.
* Red arcs: meridian, celestial equator, hour-angle lines every 2 h to ±6 h; dotted circles
  at airmass 2, 3, 4.
* Background colour follows the Sun: black at night, dark grey step at twilight start/end,
  continuous blue ramp toward daylight.
* Clock face (local time) top-right; site and UT bottom-right.
* Mouse/keys: left-click or `s` = nearest list object (within ~5°); middle-click or `c` = set
  coords to cursor; `h` = nearest bright (HR) star; `w` = open object's URL; `f`/`b` = step
  time; `n` = now; `z`/`o` = zoom in/out at cursor; `p` = pan; `r` = restore; `q`/`x` = hide;
  right-button = help popup.

→ ⬆ interactive canvas/Plotly polar chart with the same overlays, hover readouts, click to
select, same key bindings, plus a time slider.

## 4. Hourly Circumstances window
* For the current target, every hour through the night: **Local, UT, LST, HA, airmass,
  moonAlt, sunAlt** with warning colours.
* Night selection rule: before local noon → previous night; after noon → coming night.
* "Dump to `jskycalc.out`" (appends). → ✅ + CSV/clipboard export, configurable step.

## 5. Nightly Almanac window
* **Sunset, Twilight Ends (18°), Night Center, Twilight Begins (18°), Sunrise, Moonrise,
  Moonset, LST at evening twilight, LST at morning twilight.**
* Sun/Moon rise/set defined at zenith distance 90°50′ (−0.83°), *plus* horizon dip
  `sqrt(2 h_terrain / R⊕)` from the terrain elevation. Same noon rule as Hourly.
* → ⬆ adds civil (6°) and nautical (12°) twilights, LST at midnight, length of dark time
  (12° and 18°), moon illumination at midnight, moon-free dark hours.

## 6. Seasonal Observability window
* Centred on program date: 8 lunations → **16 rows** (each New and each Full moon).
* Columns: **Moon (New/Full), Evening Date, HA.eve, airm.eve, HA.ctr, airm.ctr, HA.morn,
  airm.morn, hrs<3, hrs<2, hrs<1.5**. "eve/morn" = 18° twilight; "ctr" = night centre.
* Hours columns = hours between 18° twilights with altitude above 19.28°/29.88°/41.76°
  (airmass 3/2/1.5), computed analytically from the HA at which the target crosses that
  altitude. Print button.
* → ✅ identical table + ⬆ the new "best time of year" analysis (§N3 below).

## 7. Planet Table window
* Low-precision (Meeus) positions, equinox of date: **Name, RA, Dec, HA, airmass,
  proximity** (angle to current target). Mercury … Neptune + Pluto. Print button.
* → ⬆ astropy built-in (ERFA) ephemeris, far more accurate; click to select a planet as
  the target (also Sun/Moon). Pluto needs a JPL kernel: shown only if one is available locally.

## 8. Object Lists window
* Load text files; formats: space-separated `name hh mm ss dd mm ss equinox [url]` (name has
  no blanks; colons allowed) or comma-separated `name, ra, dec, equinox, extras` (RA with
  trailing `d` = degrees); `#` comments; each line parsed independently.
* Multiple lists remembered by name; sort by RA or alphabetical; Clear list; select → loads
  into main window; optional `file:`/`http` URL per object.
* → ⬆ the new flexible parser (§N1), drag-drop, preview & inline fixing; reads JSkyCalc format exactly.

## 9. Alternate Coordinates window
* Coordinates precessed to equinox of date; **J2000 in decimal degrees**; **Galactic l, b**
  (editable → converts back to equatorial); **ecliptic λ, β** (read-only);
  **parallax factors** (E and N displacement in arcsec for a 1″ parallax, at this time).
* → ✅ all, ⬆ ecliptic input too, proper-motion epoch propagation.

## 10. Airmass Graphs window (+ "Airmass Graph Sel." object selector)
* Airmass vs time sunset→sunrise; local time bottom, UT top; blue fades for twilight;
  low airmass at top; Moon altitude in yellow on a separate right-hand scale with phase
  symbols; multi-select objects (ctrl-click) → colour-coded curves (solid/dashed/dotted styles);
  clicking the graph **sets the program time** to that instant.
* → ⬆ the new airmass plot (§N2).

## 11. Parallactic Angle Predictor ("Parallactic…")
* Inputs: time until start (default min; `s`/`h` units), dwell time, current rotator angle.
* Output: **refraction-weighted optimal slit PA** for the exposure, airmass at start/end
  (warning colours), and a graph of the cross-slit refraction factor `tan z · sin(PA − PA_opt)`
  vs time for the optimal angle, ±15° steps, and the current rotator (red). Background
  shows twilight.
* → ✅ port.

## 12. ds9 control window ("ds9…")
* Via XPA: launch ds9, download DSS1/DSS2 (blue/red/IR) or 2MASS (J/H/K) from STScI/ESO
  server at a given field size and rotation; **Mark Chart** (name, J2000 coords, scale bar,
  compass, circle); **Blink DSS** (download all epochs, align on WCS, blink).
* → 🌐 replaced by an in-app finder chart (CDS hips2fits / HiPS: DSS2, 2MASS, PanSTARRS,
  DES…) with the same Spinrad mark-up, exportable as PNG/PDF; optional "send to ds9" via
  SAMP/XPA if present. Network-only and optional.

## 13. Help window
* Shows the user manual. → ✅ built-in help + per-quantity tooltips.

## 14. Algorithms worth noting (affects validation)
* Precession: IAU 1976, applied to *mean* coordinates; **no nutation, no annual aberration**
  in the target's apparent place → expect ~10–40″ alt/az differences vs astropy (which is right).
* LST: mean sidereal time (no equation of the equinoxes, ≤ ~1.1 s).
* Time: ΔT extrapolation; no UT1–UTC (≤ 0.9 s).
* Sun ~1″, Moon ~10″ (topocentric); planets Meeus low-precision (~1′, outer worse).
* Barycentric: own solar+planet barycentre model, ~0.01 s, few m/s.
* Rise/set: −0.83° plus terrain dip; twilight at −18° only.
* DST: hard-coded rule tables per code — the Chilean rules have changed several times since
  2016, so JSkyCalc local times in Chile may be off by 1 h on some dates (artairmass uses IANA tzdb).
* Altitude/airmass are geometric (unrefracted).

---

## New features requested (not in JSkyCalc)

**N1. Flexible list input** — paste/upload/drag-drop; CSV/TSV/whitespace/semicolon; header
auto-detection; `#` comments; extra columns ignored; sexagesimal with `:`/spaces/letters,
decimal degrees, decimal-hour RA (detect or force); equinox/epoch column; galactic l,b;
name-only rows resolved via Sesame with on-disk cache; JSkyCalc format; simple catalog
formats; preview table with per-row parse status, ambiguity flags, inline fixes.

**N2. Airmass plots (night or multi-night run)** — inverted airmass axis (1.0–3.0) left,
altitude right; local time bottom, UT & LST top; civil/nautical/astronomical twilight bands;
moon altitude curve; moon illumination & per-object separation; toggle objects; hover;
airmass limit line; matplotlib PNG/PDF/SVG + CSV export; per-object summary (rise/set at the
limit, transit, max alt, dark hours observable, min moon separation).

**N3. Best time of year** — per night of the year: hours above alt/airmass limit in dark
time (nautical or astronomical), optional moon constraints (max illumination, min sep,
dark/grey/bright); plot vs date with midnight-transit date marked; plain-language best
months; semesters A (Feb–Jul) / B (Aug–Jan) shaded; heatmap objects × months for a list.

**UX** — modern layout, dark mode + red night-vision mode, keyboard shortcuts, tooltips,
persisted settings, fast vectorized computation (50 objects × 1 night ≈ instant).

---

## Ideas borrowed from other planning tools

| Tool | What's worth borrowing |
|---|---|
| **ING Staralt** (Staralt / Startrack / Starobs modes) | Starobs = altitude-at-midnight-through-the-year plot; Startrack = polar sky tracks of targets over the night |
| **airmass.org** | Clean multi-target airmass plot with per-target moon separation; shareable/encodable target lists |
| **astroplan** | Constraint objects (altitude, airmass, moon sep/illum, twilight) composed into an observability grid — we'll use it as the conceptual model and as an independent cross-check |
| **ESO Observability / SkyCalc** | Moon-constraint filtering by illumination & separation; sky-brightness-aware observability |
| **Gemini OT elevation plot** | Parallactic-angle and sky-brightness overlays selectable on the same time axis; Moon/target timing marks |
| **ALMA OT / ATCA CABB scheduler** | Radio planning is **LST- and elevation-driven, not twilight-driven**: an "LST range" view and a radio mode with twilight off and Sun-avoidance angle on |
| **JWST GTVT / HST & Chandra visibility tools** | Solar-elongation windows by date (JWST field of regard 85°–135°) — relevant to your space programs; a light "space visibility" view, clearly marked approximate (official tools remain authoritative) |
| **Telescope TOMs (LCO/TOM Toolkit)** | Visibility sparkline per target in list tables |
