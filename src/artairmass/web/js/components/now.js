import { html, useContext, useState, useEffect } from "../lib.js";
import { Store } from "../store.js";
import { api } from "../api.js";
import { fix, hms, hm, raStr, decStr, airmassLevel, haLevel, moonSepLevel, skyBrightLevel, skyState } from "../format.js";
import { MoonGlyph } from "./topbar.js";

// Definitions shown on hover — the conventions matter at the telescope.
const TIP = {
  ha: "Hour angle = LST − RA (apparent). Negative = east of the meridian (rising).",
  alt: "Geometric altitude (no refraction), as in JSkyCalc. Settings can switch to refracted.",
  az: "Azimuth, measured from north through east.",
  airmass: "Hardie (1962) airmass on the geometric altitude — JSkyCalc's 'true airmass'. Settings: Young 1994 or sec z.",
  par: "Parallactic angle: position angle of the direction to the zenith, N through E. Align a long slit here (or its opposite) to avoid differential-refraction losses.",
  lst: "Local apparent sidereal time (mean LST shown alongside).",
  icrs: "ICRS (≈ J2000) position at the target's epoch; proper motion applied to date.",
  mean: "Mean equator & equinox of date (precessed, no nutation/aberration) — what JSkyCalc shows as the current-epoch position.",
  app: "Apparent geocentric place: true equator & equinox of date, with aberration, nutation, light deflection.",
  gal: "Galactic longitude l and latitude b (IAU 1958 system via ICRS).",
  ecl: "Geocentric true ecliptic of date.",
  constel: "Constellation containing the position (Roman 1987 boundaries).",
  sunstate: "Sky state from the Sun's altitude: civil −6°, nautical −12°, astronomical −18°.",
  ztwi: "Zenith twilight: how many magnitudes the blue zenith sky is above its dark value (JSkyCalc fit). 0 = dark.",
  moonsep: "Topocentric angular distance from the Moon to the target.",
  lsb: "Scattered moonlight at the target, V mag/arcsec² (Krisciunas & Schaefer 1991, k = 0.172). Dark sky ≈ 21.7.",
  illum: "Illuminated fraction of the lunar disc as seen from the site.",
  bjd: "BJD_TDB: Barycentric Julian Date in the TDB scale (Eastman et al. 2010) — the modern standard for timing.",
  bjdutc: "Barycentric JD on a UTC basis: UTC JD + light-travel time. This is JSkyCalc's 'Bary. JD'.",
  hjd: "Heliocentric JD (UTC) — for comparing with older literature.",
  ltt: "Light-travel-time correction to the solar-system barycentre.",
  rv: "Add this to an observed radial velocity to refer it to the solar-system barycentre (astropy, cm/s accuracy).",
  pifac: "Parallax factors: E and N displacement (arcsec) of a star with 1″ parallax at this moment. Multiply by the parallax.",
  jd: "Julian Date (UTC).",
  mjd: "Modified Julian Date = JD − 2400000.5 (UTC).",
};

const Row = ({ k, tip, children }) => html`<dt title=${tip || ""}>${k}</dt><dd>${children}</dd>`;
const Pill = ({ s }) => (s ? html`<span class=${"status " + s.level}>${s.label}</span>` : null);

export function NowView({ instant, loading }) {
  const { state, actions } = useContext(Store);
  if (!instant) return html`<div class="placeholder">Computing…</div>`;
  const T = instant.target, S = instant.sun, M = instant.moon, ti = instant.time_info;
  const amL = airmassLevel(T.airmass, T.alt_deg);
  const target = state.targets.find((t) => t.id === state.selectedId);
  const moonUp = M.alt_deg > 0;
  return html`<div class=${loading ? "loading" : ""}>
    <div class="target-title">
      <h1>${T.name}</h1>
      <span class="muted">${T.body ? "solar-system body" : T.constellation}</span>
      ${T.name === "zenith" && html`<span class="status info">no target selected — showing the zenith</span>`}
      ${instant.planets?.length > 0 && instant.planets.map((p) => html`<span class=${"status " + (p.level === "red" ? "critical" : "warning")}>${p.planet} ${fix(p.sep_deg, 2)}° away</span>`)}
      ${target?.url && html`<a class="btn" href=${target.url} target="_blank" rel="noopener">Open link</a>`}
    </div>
    <div class="grid">
      <section class="card wide">
        <div class="hero">
          <div>
            <div class="muted" style="font-size:.78rem;letter-spacing:.06em;text-transform:uppercase" title=${TIP.airmass}>Airmass</div>
            ${T.alt_deg > 0 && T.airmass != null ? html`<div class="big">${fix(T.airmass, 3)}</div>` : html`<div class="big down">Below horizon</div>`}
            ${T.alt_deg > 0 && html`<div style="margin-top:6px"><${Pill} s=${amL}/></div>`}
          </div>
          <div class="hero-stats">
            <div title=${TIP.alt}><span>Altitude</span><b class="num">${fix(T.alt_deg, 2)}°</b></div>
            <div title=${TIP.az}><span>Azimuth</span><b class="num">${fix(T.az_deg, 2)}°</b></div>
            <div title=${TIP.ha}><span>Hour angle</span><b class="num">${T.ha}</b></div>
            <div title=${TIP.par}><span>Parallactic</span><b class="num">${fix(T.parallactic_deg, 1)}° <small class="muted">/ ${fix(opp(T.parallactic_deg), 1)}°</small></b></div>
            <div title=${TIP.lst}><span>LST</span><b class="num">${instant.time.last}</b></div>
          </div>
        </div>
        ${haLevel(T.ha_h) && html`<div style="margin-top:10px"><${Pill} s=${haLevel(T.ha_h)}/></div>`}
      </section>

      ${target && !target.body && html`<${CoordEditor} target=${target}/>`}

      <section class="card">
        <h3>Coordinates</h3>
        <dl class="kv">
          <${Row} k="ICRS (J2000)" tip=${TIP.icrs}>${T.icrs.ra_hms} ${T.icrs.dec_dms}</${Row}>
          <${Row} k="  decimal" tip=${TIP.icrs}>${fix(T.icrs.ra_deg, 5)}° ${fix(T.icrs.dec_deg, 5)}°</${Row}>
          <${Row} k=${`Mean of date (${fix(instant.time.epoch, 2)})`} tip=${TIP.mean}>${T.mean_of_date.ra_hms} ${T.mean_of_date.dec_dms}</${Row}>
          <${Row} k="Apparent" tip=${TIP.app}>${T.apparent.ra_hms} ${T.apparent.dec_dms}</${Row}>
          <${Row} k="Galactic l, b" tip=${TIP.gal}>${fix(T.galactic.l_deg, 4)}° ${fix(T.galactic.b_deg, 4)}°</${Row}>
          <${Row} k="Ecliptic λ, β" tip=${TIP.ecl}>${fix(T.ecliptic.lon_deg, 4)}° ${fix(T.ecliptic.lat_deg, 4)}°</${Row}>
          <${Row} k="Constellation" tip=${TIP.constel}>${T.constellation} <small>(${T.constellation_abbr})</small></${Row}>
          ${instant.parallax_factors && html`<${Row} k="Parallax factors E, N" tip=${TIP.pifac}>${fix(instant.parallax_factors.east, 3)} ${fix(instant.parallax_factors.north, 3)}</${Row}>`}
        </dl>
      </section>

      <section class="card">
        <h3>Moon <${MoonGlyph} illum=${M.illum} waxing=${/1st|since new|before full/.test(M.phase)} size=${20}/></h3>
        <dl class="kv">
          <${Row} k="Phase">${M.phase.replace(/\.$/, "")}</${Row}>
          <${Row} k="Illuminated" tip=${TIP.illum}>${fix(M.illum * 100, 1)}%</${Row}>
          <${Row} k="Alt, az">${fix(M.alt_deg, 1)}° ${fix(M.az_deg, 1)}°</${Row}>
          <${Row} k="RA, Dec (topo.)">${M.ra_hms} ${M.dec_dms}</${Row}>
          <${Row} k="Moon–target" tip=${TIP.moonsep}>${fix(M.moon_obj_deg, 2)}°</${Row}>
          <${Row} k="Moonlit sky" tip=${TIP.lsb}>${M.sky_brightness_v == null ? html`<small>${moonUp ? "target down" : "Moon down"}</small>` : `${fix(M.sky_brightness_v, 2)} V/″²`}</${Row}>
        </dl>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px">
          <${Pill} s=${moonSepLevel(M.moon_obj_deg, M.alt_deg)}/>
          ${moonUp && T.alt_deg > 0 && html`<${Pill} s=${skyBrightLevel(M.sky_brightness_v)}/>`}
        </div>
      </section>

      <section class="card">
        <h3>Sun & sky</h3>
        <dl class="kv">
          <${Row} k="Sky" tip=${TIP.sunstate}>${skyState(S.alt_deg).name}</${Row}>
          <${Row} k="Sun alt, az">${fix(S.alt_deg, 2)}° ${fix(S.az_deg, 1)}°</${Row}>
          <${Row} k="Sun RA, Dec (topo.)">${S.ra_hms} ${S.dec_dms}</${Row}>
          <${Row} k="Zenith twilight" tip=${TIP.ztwi}>${S.ztwilight_mag >= 99 ? "daytime" : S.ztwilight_mag <= 0 ? "none" : fix(S.ztwilight_mag, 1) + " mag"}</${Row}>
          <${Row} k="Sun–target">${fix(S.sun_obj_deg, 1)}°</${Row}>
        </dl>
      </section>

      <section class="card">
        <h3>Time</h3>
        <dl class="kv">
          <${Row} k="Local">${ti.weekday} ${ti.local} <small>${ti.zone}</small></${Row}>
          <${Row} k="UTC">${ti.utc.replace("T", " ").slice(0, 19)}</${Row}>
          <${Row} k="JD" tip=${TIP.jd}>${fix(instant.time.jd, 5)}</${Row}>
          <${Row} k="MJD" tip=${TIP.mjd}>${fix(instant.time.mjd, 5)}</${Row}>
          <${Row} k="LST apparent / mean" tip=${TIP.lst}>${instant.time.last} / ${instant.time.lmst}</${Row}>
          ${instant.bary && html`
            <${Row} k="BJD_TDB" tip=${TIP.bjd}>${fix(instant.bary.bjd_tdb, 6)}</${Row}>
            <${Row} k="BJD (UTC)" tip=${TIP.bjdutc}>${fix(instant.bary.bjd_utc, 6)}</${Row}>
            <${Row} k="HJD (UTC)" tip=${TIP.hjd}>${fix(instant.bary.hjd_utc, 6)}</${Row}>
            <${Row} k="Light time" tip=${TIP.ltt}>${fix(instant.bary.ltt_bary_s, 2)} s</${Row}>
            <${Row} k="Bary. RV corr." tip=${TIP.rv}>${fix(instant.bary.rv_corr_kms, 3)} km/s</${Row}>`}
        </dl>
      </section>
    </div>
  </div>`;
}

const opp = (q) => (q > 0 ? q - 180 : q + 180);

/** JSkyCalc's white input fields: edit RA/Dec/equinox of the selected target. */
function CoordEditor({ target }) {
  const { actions } = useContext(Store);
  const [f, setF] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { setF({ name: target.name, ra: raStr(target.ra, 2), dec: decStr(target.dec, 1), equinox: "2000" }); setErr(null); }, [target.id, target.ra, target.dec, target.name]);
  if (!f) return null;
  const apply = async (e) => {
    e.preventDefault();
    try {
      const r = await api.post("/api/coords", { name: f.name, ra: f.ra, dec: f.dec, equinox: f.equinox });
      actions.updateTarget(target.id, { name: f.name, ra: r.ra, dec: r.dec });
      setErr(r.ambiguous ? "RA read as decimal hours; add “d” for degrees." : null);
    } catch (e2) { setErr(e2.message); }
  };
  const fld = (k, label, ph) => html`<label>${label}<input class="inp mono" value=${f[k]} placeholder=${ph} onInput=${(e) => setF({ ...f, [k]: e.target.value })}/></label>`;
  return html`<section class="card wide">
    <h3>Edit target <small class="muted" style="text-transform:none;letter-spacing:0">Enter applies · RA as h:m:s, decimal hours, or degrees with “d” · equinox −1 = of date</small></h3>
    <form class="coord-edit" onSubmit=${apply}>
      ${fld("ra", "RA", "13:48:52.5")}${fld("dec", "Dec", "+26:35:34")}${fld("equinox", "Equinox", "2000")}
      <button class="btn primary">Apply</button>
    </form>
    ${err && html`<div class="status warning" style="margin-top:8px;white-space:normal">${err}</div>`}
  </section>`;
}
