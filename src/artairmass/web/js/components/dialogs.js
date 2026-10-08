import { html, useContext, useState, useEffect, useRef } from "../lib.js";
import { Store } from "../store.js";
import { api } from "../api.js";
import { fix } from "../format.js";

export function Dialogs() {
  const { state, dispatch } = useContext(Store);
  const d = state.dialog;
  useEffect(() => {
    if (!d) return;
    const esc = (e) => e.key === "Escape" && dispatch({ type: "dialog", dialog: null });
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [d]);
  if (!d) return null;
  const close = () => dispatch({ type: "dialog", dialog: null });
  const body = { help: HelpDialog, site: SiteDialog, settings: SettingsDialog }[d.kind];
  if (!body) return null;
  return html`<div class="scrim" onPointerDown=${(e) => e.target === e.currentTarget && close()}>
    <div class="dialog" role="dialog" aria-modal="true"><${body} close=${close} ...${d}/></div>
  </div>`;
}

function HelpDialog({ close }) {
  const { state } = useContext(Store);
  const st = state.status;
  const keys = [
    ["n", "set time to now (live)"], ["l", "toggle live clock"], ["f / b", "step forward / back by the timestep"],
    ["[ / ]", "previous / next night"], ["1 – 6", "switch tab"], ["j / k", "next / previous target"],
    ["/", "filter targets"], ["t", "cycle theme"], ["r", "red night-vision mode on/off"], ["?", "this help"], ["Esc", "close dialogs"],
  ];
  return html`<h2>artairmass</h2>
    <p class="dim" style="margin-top:-6px">An offline-first observation planner — a modern JSkyCalc built on astropy.</p>
    <h3 style="font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em">Keyboard</h3>
    <div class="help-grid">${keys.map(([k, v]) => html`<kbd>${k}</kbd><span>${v}</span>`)}</div>
    <h3 style="font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-top:18px">Timestep units</h3>
    <p class="dim" style="margin:0">s, m, h, d · <b>t</b> = sidereal day (successive transits) · <b>l</b> = lunation. A bare number means hours.</p>
    <h3 style="font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-top:18px">Data status</h3>
    ${st && html`<dl class="kv">
      <dt>Version</dt><dd>${st.version}</dd>
      <dt>IERS predictions from</dt><dd>${st.iers.predictive_start} ${st.iers.stale ? html`<span class="status warning">stale</span>` : html`<span class="status good">fresh</span>`}</dd>
      <dt>IERS table ends</dt><dd>${st.iers.table_end}</dd>
      <dt>Ephemeris</dt><dd>${st.iers.ephemeris}</dd></dl>
      ${st.iers.stale && html`<p class="dim">Run <code>artairmass update-data</code> while online to refresh Earth-orientation data. Until then UT1 and polar motion are extrapolated (≲ 1 s in LST).</p>`}`}
    <div class="actions"><button class="btn primary" onClick=${close}>Close</button></div>`;
}

const TZ_HINTS = ["America/Santiago", "America/Phoenix", "America/Los_Angeles", "America/Denver", "America/Chicago", "America/New_York",
  "Pacific/Honolulu", "Atlantic/Canary", "Europe/Madrid", "Europe/London", "Africa/Johannesburg", "Australia/Sydney", "Australia/Perth", "Asia/Tokyo", "UTC"];

function SiteDialog({ close, edit }) {
  const { actions } = useContext(Store);
  const [f, setF] = useState(edit ? { ...edit } : { key: "", name: "", lat: "", lon: "", elevation: "0", tz: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC", horizon_height: "0", telescopes: "" });
  const [err, setErr] = useState(null);
  const save = async (e) => {
    e.preventDefault();
    try {
      const key = (f.key || f.name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "site";
      const body = { ...f, key, lat: parseFloat(f.lat), lon: parseFloat(f.lon), elevation: parseFloat(f.elevation || 0), horizon_height: parseFloat(f.horizon_height || 0) };
      if (!isFinite(body.lat) || !isFinite(body.lon)) throw new Error("Latitude and longitude must be decimal degrees (east positive).");
      await api.post("/api/sites", body);
      await actions.reloadSites(key);
      close();
    } catch (e2) { setErr(e2.message); }
  };
  const del = async () => { await api.del(`/api/sites/${edit.key}`); await actions.reloadSites(); close(); };
  const fld = (k, label, ph, extra = {}) => html`<label>${label}<input class="inp" value=${f[k]} placeholder=${ph} onInput=${(e) => setF({ ...f, [k]: e.target.value })} ...${extra}/></label>`;
  return html`<h2>${edit ? "Edit site" : "Add a site"}</h2>
    <form onSubmit=${save}>
      <div class="form">
        ${fld("name", "Name", "My observatory", { required: true })}
        ${fld("telescopes", "Telescopes (optional)", "1-m, spectrograph")}
        ${fld("lat", "Latitude (° N +)", "-29.0146", { required: true, inputmode: "decimal" })}
        ${fld("lon", "Longitude (° E +)", "-70.6926", { required: true, inputmode: "decimal" })}
        ${fld("elevation", "Elevation (m)", "2380", { inputmode: "decimal" })}
        <label>Time zone (IANA)<input class="inp" list="tzs" value=${f.tz} onInput=${(e) => setF({ ...f, tz: e.target.value })} required/>
          <datalist id="tzs">${TZ_HINTS.map((z) => html`<option value=${z}/>`)}</datalist></label>
        ${fld("horizon_height", "Height above horizon terrain (m)", "0", { inputmode: "decimal", title: "Lowers the horizon for rise/set times (JSkyCalc's 'terrain elevation'); 0 = standard −0.83°" })}
      </div>
      <p class="muted" style="font-size:.82rem">Longitude is east-positive degrees (Las Campanas = −70.69). Daylight-saving rules come from the time-zone database, so use the zone's name, not an offset.</p>
      ${err && html`<div class="status critical" style="white-space:normal">${err}</div>`}
      <div class="actions">
        ${edit && html`<button type="button" class="btn" style="margin-right:auto" onClick=${del}>Delete site</button>`}
        <button type="button" class="btn ghost" onClick=${close}>Cancel</button><button class="btn primary">Save site</button></div>
    </form>`;
}

function SettingsDialog({ close }) {
  const { state, actions } = useContext(Store);
  const [s, setS] = useState({ ...state.settings });
  const save = async () => { await actions.saveSettings(s); close(); };
  const sel = (k, label, opts, tip) => html`<label title=${tip || ""}>${label}<select class="inp" value=${s[k]} onChange=${(e) => setS({ ...s, [k]: e.target.value })}>
    ${opts.map(([v, l]) => html`<option value=${v}>${l}</option>`)}</select></label>`;
  const num = (k, label, step, tip) => html`<label title=${tip || ""}>${label}<input class="inp" type="number" step=${step} value=${s[k]} onInput=${(e) => setS({ ...s, [k]: parseFloat(e.target.value) })}/></label>`;
  return html`<h2>Settings</h2>
    <div class="form">
      ${sel("site", "Default site", state.sites.map((x) => [x.key, x.name]))}
      ${sel("twilight", "Dark time means", [["astronomical", "Sun below −18° (astronomical)"], ["nautical", "Sun below −12° (nautical)"]])}
      ${num("airmass_limit", "Airmass limit (plots)", 0.1)}
      ${sel("airmass_model", "Airmass formula", [["hardie", "Hardie 1962 (JSkyCalc)"], ["young", "Young 1994"], ["secz", "sec z"]])}
      ${num("sleep_s", "Live update interval (s)", 1, "How often the Now panel recomputes in live mode (JSkyCalc's 'sleep for')")}
      ${num("ui_scale", "Text size", 0.05, "1 = default; 1.2 = JSkyCalc's 'large type'")}
    </div>
    <div class="actions"><button class="btn ghost" onClick=${close}>Cancel</button><button class="btn primary" onClick=${save}>Save</button></div>`;
}
