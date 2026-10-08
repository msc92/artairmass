// Tools: slit-angle planner, coordinate converter, finder chart, radio LST ranges,
// solar elongation for space observatories.
import { html, useContext, useState, useEffect, useMemo, useRef } from "../lib.js";
import { Store, targetPayload } from "../store.js";
import { api } from "../api.js";
import { fix, hm, raStr, decStr, airmassLevel } from "../format.js";
import { css, PlotlyChart } from "./night.js";

const TOOLS = [["slit", "Slit angle"], ["coords", "Coordinates"], ["finder", "Finder chart"], ["radio", "Radio · LST"], ["space", "Space · Sun angle"]];

export function ToolsView() {
  const [tool, setTool] = useState(() => { try { return localStorage.getItem("artairmass.v1.tool") || "slit"; } catch (e) { return "slit"; } });
  useEffect(() => { try { localStorage.setItem("artairmass.v1.tool", tool); } catch (e) { /* */ } }, [tool]);
  return html`<div>
    <div class="toolbar"><div class="seg" role="tablist">${TOOLS.map(([k, l]) => html`<button role="tab" aria-pressed=${tool === k} onClick=${() => setTool(k)}>${l}</button>`)}</div></div>
    ${tool === "slit" && html`<${SlitTool}/>`}
    ${tool === "coords" && html`<${CoordTool}/>`}
    ${tool === "finder" && html`<${FinderTool}/>`}
    ${tool === "radio" && html`<${RadioTool}/>`}
    ${tool === "space" && html`<${SpaceTool}/>`}
  </div>`;
}

const useSelected = () => {
  const { state } = useContext(Store);
  return state.targets.find((t) => t.id === state.selectedId) || null;
};
const needTarget = html`<div class="placeholder">Select a target in the sidebar first.</div>`;

// ------------------------------------------------------------------------- slit angle
function SlitTool() {
  const { state, actions } = useContext(Store);
  const target = useSelected();
  const [f, setF] = useState({ start: 5, dwell: 60, pa: "" });
  const [r, setR] = useState(null);
  useEffect(() => {
    if (!target) return;
    const t = setTimeout(() => api.post("/api/parallactic", { site: state.siteKey, time: state.jd, start_in_min: +f.start || 0, dwell_min: +f.dwell || 60,
      current_pa: f.pa === "" ? null : +f.pa, target: targetPayload(target) }).then(setR).catch((e) => actions.toast(e.message, true)), 250);
    return () => clearTimeout(t);
  }, [target?.id, target?.ra, target?.dec, state.siteKey, Math.round(state.jd * 1440), f.start, f.dwell, f.pa]);
  const fig = useMemo(() => {
    if (!r || r.optimal_pa == null) return null;
    const names = { optimal: `optimal ${fix(r.optimal_pa, 1)}°`, current: `current ${f.pa}°`, "-15": "−15°", "+15": "+15°", "-30": "−30°", "+30": "+30°" };
    const color = (k) => (k === "optimal" ? css("--text") : k === "current" ? css("--critical") : k.includes("15") ? css("--s7") : css("--muted"));
    const traces = Object.entries(r.curves).map(([k, y]) => ({ x: r.minutes, y, name: names[k] || k, mode: "lines", line: { color: color(k), width: k === "optimal" || k === "current" ? 2.5 : 1.2 }, hovertemplate: "%{y:.2f}<extra>%{fullData.name}</extra>" }));
    const surf = css("--surface");
    const tw = r.sun_alt.map((a) => a > -18);
    const shapes = [];
    r.minutes.forEach((m, i) => { if (tw[i] && i < r.minutes.length - 1) shapes.push({ type: "rect", xref: "x", yref: "paper", x0: m, x1: r.minutes[i + 1], y0: 0, y1: 1, fillcolor: css("--twilight-civil"), line: { width: 0 }, layer: "below" }); });
    shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0, y1: 0, line: { color: css("--axis"), width: 1 } });
    return { traces, layout: { paper_bgcolor: surf, plot_bgcolor: surf, height: 340, margin: { l: 56, r: 20, t: 16, b: 44 }, font: { family: css("--font"), size: 11, color: css("--text-2") },
      xaxis: { title: { text: "minutes after start" }, showgrid: false, fixedrange: true }, yaxis: { title: { text: "cross-slit factor  tan z · sin(PA − q)" }, gridcolor: css("--grid"), zeroline: false, fixedrange: true },
      legend: { orientation: "h", y: -0.2 }, hovermode: "x unified", shapes } };
  }, [r, state.theme]);
  if (!target) return needTarget;
  const inp = (k, label, unit, title) => html`<label class="field" title=${title}><span>${label}</span><input class="inp mono" style="width:80px" value=${f[k]} onInput=${(e) => setF({ ...f, [k]: e.target.value })}/><span>${unit}</span></label>`;
  return html`<div class="grid">
    <section class="card wide">
      <h3>Slit position angle for ${target.name}</h3>
      <div class="toolbar">${inp("start", "starts in", "min", "Time from the program time to the start of the exposure")}${inp("dwell", "dwell", "min", "Total time on target")}${inp("pa", "current rotator PA", "°", "Leave empty if you don't have one")}</div>
      ${r && (r.optimal_pa == null ? html`<div class="status critical">The target is below the horizon for this whole interval.</div>` : html`
        <div class="hero" style="margin:6px 0 12px">
          <div><div class="muted" style="font-size:.78rem;text-transform:uppercase;letter-spacing:.06em">Best slit PA</div><div class="big">${fix(r.optimal_pa, 1)}°</div>
            <div class="muted">or ${fix(r.optimal_pa > 0 ? r.optimal_pa - 180 : r.optimal_pa + 180, 1)}° · refraction-weighted over the exposure</div></div>
          <div class="hero-stats">
            <div><span>Airmass at start</span><b>${r.airmass_start ? fix(r.airmass_start, 2) : "down"}</b></div>
            <div><span>at end</span><b>${r.airmass_end ? fix(r.airmass_end, 2) : "down"}</b></div>
            <div title="Largest |tan z · sin(PA − q)| during the exposure; < 1 is a good rule for a 1″ slit, 4000–7500 Å (Filippenko 1982)"><span>Worst factor (optimal)</span><b>${fix(r.max_factor_optimal, 2)}</b></div>
            ${r.max_factor_current != null && html`<div><span>Worst factor (current)</span><b class=${r.max_factor_current > 1 ? "status serious" : ""} style="border:0;padding:0">${fix(r.max_factor_current, 2)}</b></div>`}
          </div></div>
        ${r.below_horizon && html`<div class="status warning" style="margin-bottom:8px">The target is below the horizon for part of this interval.</div>`}
        ${fig && html`<${PlotlyChart} fig=${fig} compact=${true}/>`}
        <div class="muted" style="font-size:.82rem">Cross-slit refraction factor vs time for the optimal angle, ±15° and ±30°${f.pa !== "" ? ", and your current rotator angle" : ""}. Shading marks twilight. Rotator-to-slit offsets depend on your instrument.</div>`)}
    </section>
  </div>`;
}

// ------------------------------------------------------------------------- converter
function CoordTool() {
  const { state, actions } = useContext(Store);
  const target = useSelected();
  const [f, setF] = useState({ system: "galactic", a: "0", b: "0", equinox: "2000" });
  const [r, setR] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    const t = setTimeout(() => api.post("/api/convert", { ...f, time: state.jd }).then((x) => { setR(x); setErr(null); }).catch((e) => setErr(e.message)), 250);
    return () => clearTimeout(t);
  }, [f.system, f.a, f.b, f.equinox]);
  const labels = { equatorial: ["RA", "Dec"], galactic: ["l (°)", "b (°)"], ecliptic: ["λ (°)", "β (°)"] };
  return html`<div class="grid">
    <section class="card">
      <h3>Convert a position</h3>
      <div class="seg" style="margin-bottom:10px">${["equatorial", "galactic", "ecliptic"].map((k) => html`<button aria-pressed=${f.system === k} onClick=${() => setF({ ...f, system: k })}>${k}</button>`)}</div>
      <div class="coord-edit" style="grid-template-columns:1fr 1fr 90px">
        <label>${labels[f.system][0]}<input class="inp mono" value=${f.a} onInput=${(e) => setF({ ...f, a: e.target.value })}/></label>
        <label>${labels[f.system][1]}<input class="inp mono" value=${f.b} onInput=${(e) => setF({ ...f, b: e.target.value })}/></label>
        ${f.system === "equatorial" ? html`<label>Equinox<input class="inp mono" value=${f.equinox} onInput=${(e) => setF({ ...f, equinox: e.target.value })}/></label>` : html`<span></span>`}
      </div>
      ${target && !target.body && html`<button class="btn" style="margin-top:10px" onClick=${() => setF({ system: "equatorial", a: raStr(target.ra, 3), b: decStr(target.dec, 2), equinox: "ICRS" })}>Use ${target.name}</button>`}
      ${err && html`<div class="status critical" style="margin-top:8px">${err}</div>`}
      ${f.system === "ecliptic" && html`<p class="muted" style="font-size:.82rem">Ecliptic = geocentric true ecliptic and equinox of the program date.</p>`}
    </section>
    ${r && html`<section class="card">
      <h3>Result</h3>
      <dl class="kv">
        <dt>ICRS (J2000)</dt><dd>${r.icrs.ra_hms} ${r.icrs.dec_dms}</dd>
        <dt>  decimal</dt><dd>${fix(r.icrs.ra_deg, 6)}° ${fix(r.icrs.dec_deg, 6)}°</dd>
        <dt>FK4 B1950</dt><dd>${r.b1950.ra_hms} ${r.b1950.dec_dms}</dd>
        <dt>Mean of date (${fix(r.epoch, 2)})</dt><dd>${r.of_date.ra_hms} ${r.of_date.dec_dms}</dd>
        <dt>Galactic l, b</dt><dd>${fix(r.galactic.l, 5)}° ${fix(r.galactic.b, 5)}°</dd>
        <dt>Ecliptic λ, β</dt><dd>${fix(r.ecliptic.lon, 5)}° ${fix(r.ecliptic.lat, 5)}°</dd>
      </dl>
      <button class="btn primary" style="margin-top:12px" onClick=${() => { const name = prompt("Name for the new target:", f.system === "galactic" ? `G${fix(r.galactic.l, 2)}${r.galactic.b >= 0 ? "+" : ""}${fix(r.galactic.b, 2)}` : "converted"); if (name) actions.addTargets([{ name, ra: r.icrs.ra_deg, dec: r.icrs.dec_deg }]); }}>Add as target</button>
    </section>`}
  </div>`;
}

// ------------------------------------------------------------------------- finder chart
const SURVEYS = [
  ["CDS/P/DSS2/red", "DSS2 red"], ["CDS/P/DSS2/blue", "DSS2 blue"], ["CDS/P/DSS2/color", "DSS2 colour"],
  ["CDS/P/2MASS/J", "2MASS J"], ["CDS/P/2MASS/K", "2MASS K"], ["CDS/P/2MASS/color", "2MASS colour"],
  ["CDS/P/PanSTARRS/DR1/color-z-zg-g", "Pan-STARRS colour"], ["CDS/P/DES-DR2/ColorIRG", "DES DR2 colour"],
  ["CDS/P/SDSS9/color", "SDSS9 colour"], ["CDS/P/unWISE/color-W2-W1W2-W1", "unWISE colour"],
];

function FinderTool() {
  const { state, actions } = useContext(Store);
  const target = useSelected();
  const [f, setF] = useState(() => { try { return JSON.parse(localStorage.getItem("artairmass.v1.finder")) || { hips: SURVEYS[0][0], fov: 10, rot: 0, invert: true }; } catch (e) { return { hips: SURVEYS[0][0], fov: 10, rot: 0, invert: true }; } });
  useEffect(() => { try { localStorage.setItem("artairmass.v1.finder", JSON.stringify(f)); } catch (e) { /* */ } }, [f]);
  const [status, setStatus] = useState("idle");
  const canvasRef = useRef();
  const px = 800;
  const ok = target && !target.body;
  const url = !ok ? "" : `https://alasky.cds.unistra.fr/hips-image-services/hips2fits?hips=${encodeURIComponent(f.hips)}&width=${px}&height=${px}&fov=${f.fov / 60}&projection=TAN&coordsys=icrs&rotation_angle=${f.rot}&ra=${target.ra}&dec=${target.dec}&format=jpg`;
  useEffect(() => {
    if (!url) return;
    setStatus("loading");
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => { draw(canvasRef.current, img, target, f, px); setStatus("ok"); };
    img.onerror = () => { draw(canvasRef.current, null, target, f, px); setStatus("offline"); };
    img.src = url;
  }, [url, state.theme]);
  if (!ok) return needTarget;
  const download = () => {
    const a = document.createElement("a");
    a.href = canvasRef.current.toDataURL("image/png");
    a.download = `finder_${target.name.replace(/\W+/g, "_")}.png`;
    a.click();
  };
  const ds9 = () => api.post("/api/ds9", { ra: target.ra, dec: target.dec, name: target.name, size_arcmin: f.fov }).then(() => actions.toast("Sent to ds9")).catch((e) => actions.toast(e.message, true));
  return html`<div class="grid" style="grid-template-columns:minmax(0,1fr) 280px">
    <section class="card plot-card" style="padding:10px">
      <canvas ref=${canvasRef} width=${px} height=${px} style="width:100%;max-width:${px}px;aspect-ratio:1;border-radius:8px;display:block;margin:auto" aria-label=${`Finder chart for ${target.name}`}></canvas>
      ${status === "loading" && html`<div class="muted" style="text-align:center;margin-top:6px">Fetching ${SURVEYS.find((s) => s[0] === f.hips)?.[1]} from CDS…</div>`}
      ${status === "offline" && html`<div class="status warning" style="margin-top:8px;white-space:normal">Couldn't fetch the survey image (offline?). The chart overlay is still drawn — survey images need the network.</div>`}
    </section>
    <section class="card">
      <h3>Finder chart</h3>
      <div style="display:grid;gap:10px">
        <label class="field" style="display:grid"><span>Survey</span><select class="inp" value=${f.hips} onChange=${(e) => setF({ ...f, hips: e.target.value })}>${SURVEYS.map(([k, l]) => html`<option value=${k}>${l}</option>`)}</select></label>
        <label class="field"><span>Field</span><input class="inp mono" type="number" min="1" max="120" style="width:70px" value=${f.fov} onChange=${(e) => setF({ ...f, fov: Math.max(1, Math.min(120, +e.target.value || 10)) })}/><span>arcmin</span></label>
        <label class="field"><span>Rotation</span><input class="inp mono" type="number" style="width:70px" value=${f.rot} onChange=${(e) => setF({ ...f, rot: +e.target.value || 0 })}/><span>° (N through E)</span></label>
        <label class="field"><input type="checkbox" checked=${f.invert} onChange=${(e) => setF({ ...f, invert: e.target.checked })}/><span>Invert (black stars on white)</span></label>
        <button class="btn primary" onClick=${download}>Download PNG</button>
        <button class="btn" onClick=${ds9} title="Uses XPA to point a running SAOImage ds9 at this target and fetch DSS">Send to ds9</button>
        <p class="muted" style="font-size:.8rem;margin:0">Marked as every finder chart should be: object, J2000 coordinates, scale bar, compass, circle on the position. Images: CDS hips2fits (network required).</p>
      </div>
    </section>
  </div>`;
}

function draw(cv, img, t, f, px) {
  if (!cv) return;
  const g = cv.getContext("2d");
  g.save();
  g.fillStyle = f.invert ? "#ffffff" : "#000000";
  g.fillRect(0, 0, px, px);
  if (img) {
    g.filter = f.invert && !/color/i.test(f.hips) ? "invert(1) contrast(1.15)" : "none";
    g.drawImage(img, 0, 0, px, px);
    g.filter = "none";
  }
  const ink = f.invert && !/color/i.test(f.hips) ? "#000" : "#fff";
  const accent = f.invert && !/color/i.test(f.hips) ? "#c4161c" : "#ff5a4a";
  const c = px / 2, sc = px / f.fov; // px per arcmin
  g.strokeStyle = accent; g.lineWidth = 2.5;
  g.beginPath(); g.arc(c, c, Math.max(10, 0.35 * sc), 0, 2 * Math.PI); g.stroke();
  g.font = "600 22px system-ui, sans-serif"; g.fillStyle = ink; g.textBaseline = "top";
  g.fillText(t.name, 18, 16);
  g.font = "16px ui-monospace, Menlo, monospace";
  g.fillText(`${raStr(t.ra, 2)}  ${decStr(t.dec, 1)}  (J2000)`, 18, 46);
  g.fillText(`${f.fov}′ × ${f.fov}′ · ${SURVEYS.find((s) => s[0] === f.hips)?.[1] || f.hips}`, 18, 70);
  // scale bar: a round number of arcmin ≈ 1/4 of the field
  const bar = [0.5, 1, 2, 5, 10, 20, 30].reduce((b, v) => (v <= f.fov / 3 ? v : b), 0.5);
  const y = px - 30, x0 = 24;
  g.lineWidth = 3; g.strokeStyle = ink;
  g.beginPath(); g.moveTo(x0, y); g.lineTo(x0 + bar * sc, y); g.stroke();
  g.fillText(bar >= 1 ? `${bar}′` : `${bar * 60}″`, x0, y - 26);
  // compass (N up, E left for rotation 0; rotate with the image)
  const cx = px - 70, cy = px - 70, L = 46, a = (-f.rot * Math.PI) / 180;
  const arrow = (ang, label) => {
    const ex = cx + L * Math.sin(ang), ey = cy - L * Math.cos(ang);
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(ex, ey); g.stroke();
    g.fillText(label, ex + 6 * Math.sin(ang) - 5, ey - 10 * Math.cos(ang) - 8);
  };
  g.lineWidth = 2.5;
  arrow(a, "N");
  arrow(a - Math.PI / 2, "E");
  g.restore();
}

// ------------------------------------------------------------------------- radio LST
function RadioTool() {
  const { state, actions } = useContext(Store);
  const [elev, setElev] = useState(20);
  const [rows, setRows] = useState(null);
  const fixedT = state.targets.filter((t) => !t.body && t.visible !== false);
  useEffect(() => {
    if (!fixedT.length) { setRows(null); return; }
    const t = setTimeout(() => api.post("/api/lst", { site: state.siteKey, targets: fixedT.map(targetPayload), min_elev: elev, time: state.jd }).then((r) => setRows(r.rows)).catch((e) => actions.toast(e.message, true)), 200);
    return () => clearTimeout(t);
  }, [state.siteKey, elev, JSON.stringify(fixedT.map((t) => [t.ra, t.dec, t.name])), Math.floor(state.jd)]);
  const fig = useMemo(() => {
    if (!rows) return null;
    const traces = [];
    rows.forEach((r, i) => {
      const segs = r.lst_start == null ? [] : r.hours >= 24 ? [[0, 24]] : r.lst_start < r.lst_end ? [[r.lst_start, r.lst_end]] : [[r.lst_start, 24], [0, r.lst_end]];
      segs.forEach(([a, b], k) => traces.push({ type: "bar", orientation: "h", y: [r.name], x: [b - a], base: [a], width: 0.5, marker: { color: fixedT[i]?.slot != null ? css(`--s${fixedT[i].slot + 1}`) : css("--context") }, showlegend: false,
        hovertemplate: `${r.name}: LST ${hm(r.lst_start)}–${hm(r.lst_end)} (${fix(r.hours, 1)} h)<extra></extra>` }));
    });
    const surf = css("--surface");
    return { traces, layout: { paper_bgcolor: surf, plot_bgcolor: surf, height: Math.max(200, 60 + 34 * rows.length), barmode: "overlay", margin: { l: 130, r: 20, t: 10, b: 40 },
      font: { family: css("--font"), size: 11, color: css("--text-2") }, xaxis: { range: [0, 24], dtick: 2, title: { text: "LST (h)" }, gridcolor: css("--grid"), fixedrange: true },
      yaxis: { autorange: "reversed", fixedrange: true } } };
  }, [rows, state.theme]);
  if (!fixedT.length) return html`<div class="placeholder">Add fixed targets to see their LST ranges.</div>`;
  return html`<div class="grid">
    <section class="card wide">
      <h3>LST ranges above an elevation limit <small class="muted" style="text-transform:none;letter-spacing:0">for radio / mm arrays: no twilight constraint</small></h3>
      <div class="toolbar"><label class="field"><span>min. elevation</span><input class="inp mono" type="number" style="width:70px" value=${elev} onChange=${(e) => setElev(Math.max(0, Math.min(89, +e.target.value || 0)))}/><span>°</span></label>
        <span class="muted" style="font-size:.82rem">Typical: ALMA 20–30°, ATCA 12°, ASKAP 15°, VLA 8°</span></div>
      ${fig && html`<${PlotlyChart} fig=${fig} compact=${true}/>`}
      ${rows && html`<table class="tbl"><thead><tr><th>Target</th><th>RA</th><th>LST start</th><th>LST end</th><th>Hours</th><th>Transit elev.</th><th title="Angle from the Sun today (solar avoidance)">Sun distance</th></tr></thead>
        <tbody>${rows.map((r) => html`<tr><td style="font-family:var(--font)">${r.name}</td><td>${hm(r.ra_h)}</td>
          <td>${r.lst_start == null ? "never" : r.hours >= 24 ? "always" : hm(r.lst_start)}</td><td>${r.lst_end == null || r.hours >= 24 ? "—" : hm(r.lst_end)}</td>
          <td>${fix(r.hours, 1)}</td><td>${fix(r.transit_elev, 1)}°</td><td class=${r.sun_sep < 30 ? "w-serious" : ""}>${fix(r.sun_sep, 0)}°</td></tr>`)}</tbody></table>`}
    </section></div>`;
}

// ------------------------------------------------------------------------- space
function SpaceTool() {
  const { state, actions } = useContext(Store);
  const [preset, setPreset] = useState("JWST");
  const [lim, setLim] = useState({ lo: 85, hi: 135 });
  const [data, setData] = useState(null);
  const fixedT = state.targets.filter((t) => !t.body && t.visible !== false);
  const presets = { JWST: [85, 135], HST: [50, 180], Chandra: [46, 180] };
  useEffect(() => {
    if (!fixedT.length) return;
    const t = setTimeout(() => api.post("/api/elongation", { targets: fixedT.map(targetPayload), lo: lim.lo, hi: lim.hi, days: 365 }).then(setData).catch((e) => actions.toast(e.message, true)), 200);
    return () => clearTimeout(t);
  }, [lim.lo, lim.hi, JSON.stringify(fixedT.map((t) => [t.ra, t.dec, t.name]))]);
  const fig = useMemo(() => {
    if (!data) return null;
    const traces = fixedT.map((t, i) => ({ x: data.dates, y: data.targets[i]?.elongation, name: t.name, mode: "lines", line: { color: t.slot != null ? css(`--s${t.slot + 1}`) : css("--context"), width: 2 } }));
    const surf = css("--surface");
    return { traces, layout: { paper_bgcolor: surf, plot_bgcolor: surf, height: 360, margin: { l: 52, r: 20, t: 10, b: 40 }, font: { family: css("--font"), size: 11, color: css("--text-2") },
      xaxis: { type: "date", tickformat: "%b %Y", showgrid: false, fixedrange: true }, yaxis: { range: [0, 180], dtick: 30, title: { text: "Solar elongation (°)" }, gridcolor: css("--grid"), fixedrange: true },
      shapes: [{ type: "rect", xref: "paper", x0: 0, x1: 1, y0: lim.lo, y1: lim.hi, fillcolor: css("--accent-soft"), line: { width: 0 }, layer: "below" }],
      legend: { orientation: "h", y: -0.15 }, hovermode: "x unified" } };
  }, [data, state.theme]);
  if (!fixedT.length) return html`<div class="placeholder">Add fixed targets to see their solar-elongation windows.</div>`;
  return html`<div class="grid">
    <section class="card wide">
      <h3>Solar elongation windows <small class="muted" style="text-transform:none;letter-spacing:0">approximate — always confirm with the observatory's own tools (JWST APT/GTVT, HST APT, Chandra CPT)</small></h3>
      <div class="toolbar">
        <div class="seg">${Object.keys(presets).map((k) => html`<button aria-pressed=${preset === k} onClick=${() => { setPreset(k); setLim({ lo: presets[k][0], hi: presets[k][1] }); }}>${k}</button>`)}</div>
        <label class="field"><span>from</span><input class="inp mono" type="number" style="width:64px" value=${lim.lo} onChange=${(e) => { setPreset("custom"); setLim({ ...lim, lo: +e.target.value }); }}/><span>° to</span>
          <input class="inp mono" type="number" style="width:64px" value=${lim.hi} onChange=${(e) => { setPreset("custom"); setLim({ ...lim, hi: +e.target.value }); }}/><span>°</span></label>
        ${data?.presets?.[preset] && html`<span class="muted" style="font-size:.82rem">${data.presets[preset].note}</span>`}
      </div>
      ${fig && html`<${PlotlyChart} fig=${fig} compact=${true}/>`}
      ${data && html`<table class="tbl"><thead><tr><th>Target</th><th>Days in window (next 12 months)</th><th style="text-align:left">Windows</th></tr></thead>
        <tbody>${fixedT.map((t, i) => { const d = data.targets[i]; return d && html`<tr><td style="font-family:var(--font)">${t.name}</td><td>${d.days_visible}</td>
          <td style="text-align:left;white-space:normal">${d.windows.length ? d.windows.map((w) => `${w[0]} → ${w[1]} (${w[2]} d)`).join(" · ") : "none"}</td></tr>`; })}</tbody></table>`}
    </section></div>`;
}
