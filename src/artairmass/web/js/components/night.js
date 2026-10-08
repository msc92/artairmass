// Night view: interactive airmass chart, per-target summary, almanac, hourly table,
// multi-night observing-run mode, and exports.
import { html, useContext, useState, useEffect, useRef, useMemo } from "../lib.js";
import { Store, targetPayload, DASHES } from "../store.js";
import { api } from "../api.js";
import { fix, hm, nightOf, airmassLevel, addDays, localTime, utcTime } from "../format.js";

export const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const ALT_TICKS = [90, 60, 50, 40, 30, 25, 20, 15, 10];
const AM_TICKS = [1.0, 1.1, 1.2, 1.3, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0];

// Hardie airmass and its inverse (identical to the server's formula).
function hardie(alt) {
  if (alt <= 0) return NaN;
  const s = 1 / Math.sin((alt * Math.PI) / 180), x = s - 1;
  return s > 12 ? s - 1.5 : s - (((-4.716679e-5 * x + 0.001351167) * x + 0.003033104) * x + 0.002879465) * x;
}
function altForAirmass(am) {
  let lo = 0.01, hi = 90;
  for (let i = 0; i < 50; i++) { const m = (lo + hi) / 2; if (hardie(m) > am) lo = m; else hi = m; }
  return (lo + hi) / 2;
}

function usePrefs() {
  const { state, actions } = useContext(Store);
  const s = state.settings || {};
  const [p, setP] = useState(() => ({ yAxis: "airmass", yMax: 3.0, showMoon: true, nights: 1, ...loadPrefs() }));
  useEffect(() => { try { localStorage.setItem("artairmass.v1.nightPrefs", JSON.stringify(p)); } catch (e) { /* */ } }, [p]);
  return [{ ...p, limit: s.airmass_limit ?? 2, twilight: s.twilight ?? "astronomical" }, setP,
    (k, v) => actions.saveSettings({ ...state.settings, [k]: v })];
}
function loadPrefs() { try { return JSON.parse(localStorage.getItem("artairmass.v1.nightPrefs")) || {}; } catch (e) { return {}; } }

export function NightView() {
  const { state, dispatch, actions } = useContext(Store);
  const site = state.sites.find((s) => s.key === state.siteKey);
  const [prefs, setPrefs, saveSetting] = usePrefs();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const night = nightOf(state.jd, site.tz);
  const visible = state.targets.filter((t) => t.visible !== false);
  const key = JSON.stringify([state.siteKey, night, visible.map((t) => [t.id, t.ra, t.dec, t.body, t.name]), prefs.limit, prefs.twilight, prefs.nights, state.settings?.airmass_model]);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    const t = setTimeout(() => {
      api.post("/api/night", { site: state.siteKey, date: night, targets: visible.map(targetPayload), airmass_limit: prefs.limit,
        twilight: prefs.twilight, nights: prefs.nights, airmass_model: state.settings?.airmass_model || "hardie" })
        .then((r) => { if (alive) setData({ ...r, ids: visible.map((t) => t.id) }); })
        .catch((e) => actions.toast(e.message, true))
        .finally(() => alive && setBusy(false));
    }, 150);
    return () => { alive = false; clearTimeout(t); };
  }, [key]);

  const exportAs = async (format, mono = false) => {
    try {
      const res = await fetch(`/api/night/export?format=${format}`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ site: state.siteKey, date: night, targets: visible.map(targetPayload), airmass_limit: prefs.limit,
          twilight: prefs.twilight, y_max: prefs.yMax, slots: visible.map((t) => t.slot), mono, airmass_model: state.settings?.airmass_model || "hardie" }) });
      if (!res.ok) throw new Error((await res.json()).detail);
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `airmass_${state.siteKey}_${night}.${format}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) { actions.toast(`Export failed: ${e.message}`, true); }
  };

  return html`<div>
    <div class="toolbar" role="toolbar" aria-label="Night plot controls">
      <div class="seg" title="One night, or an observing run of several nights">
        <button aria-pressed=${prefs.nights === 1} onClick=${() => setPrefs({ ...prefs, nights: 1 })}>Night</button>
        <button aria-pressed=${prefs.nights > 1} onClick=${() => setPrefs({ ...prefs, nights: prefs.nights > 1 ? prefs.nights : 5 })}>Run</button>
      </div>
      ${prefs.nights > 1 && html`<label class="field"><span>nights</span><input class="inp mono" type="number" min="2" max="31" style="width:64px" value=${prefs.nights}
        onChange=${(e) => setPrefs({ ...prefs, nights: Math.max(2, Math.min(31, parseInt(e.target.value) || 2)) })}/></label>`}
      <div class="seg" title="Vertical axis">
        <button aria-pressed=${prefs.yAxis === "airmass"} onClick=${() => setPrefs({ ...prefs, yAxis: "airmass" })}>Airmass</button>
        <button aria-pressed=${prefs.yAxis === "altitude"} onClick=${() => setPrefs({ ...prefs, yAxis: "altitude" })}>Altitude</button>
      </div>
      <label class="field" title="Airmass limit: drawn on the plot and used for rise/set and observable hours"><span>limit X</span>
        <input class="inp mono" type="number" step="0.1" min="1.05" max="10" style="width:70px" value=${prefs.limit}
          onChange=${(e) => { const v = parseFloat(e.target.value); if (v > 1 && v <= 10) saveSetting("airmass_limit", v); }}/></label>
      <label class="field" title="Which twilight ends 'dark time'"><span>dark after</span>
        <select class="inp" value=${prefs.twilight} onChange=${(e) => saveSetting("twilight", e.target.value)}>
          <option value="astronomical">astronomical (−18°)</option><option value="nautical">nautical (−12°)</option><option value="civil">civil (−6°)</option></select></label>
      ${prefs.yAxis === "airmass" && html`<label class="field"><span>axis to X</span><select class="inp" value=${prefs.yMax} onChange=${(e) => setPrefs({ ...prefs, yMax: parseFloat(e.target.value) })}>
        ${[2, 2.5, 3, 4, 5].map((v) => html`<option value=${v}>${v}</option>`)}</select></label>`}
      <label class="field"><input type="checkbox" checked=${prefs.showMoon} onChange=${(e) => setPrefs({ ...prefs, showMoon: e.target.checked })}/><span>Moon</span></label>
      <span class="spacer"></span>
      ${prefs.nights === 1 && html`<${ExportMenu} onExport=${exportAs}/>`}
    </div>
    ${visible.length === 0 && html`<div class="placeholder" style="margin-bottom:12px">No visible targets — add some in the sidebar (or tick their boxes). The almanac below still applies.</div>`}
    ${data && prefs.nights === 1 && !data.nights && html`<${SingleNight} data=${data} prefs=${prefs} busy=${busy} site=${site}/>`}
    ${data && data.nights && prefs.nights > 1 && html`<${RunView} data=${data} prefs=${prefs} busy=${busy} site=${site}/>`}
    ${!data && html`<div class="placeholder">Computing the night…</div>`}
  </div>`;
}

function ExportMenu({ onExport }) {
  const [open, setOpen] = useState(false);
  const ref = useRef();
  useEffect(() => {
    if (!open) return;
    const c = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", c);
    return () => document.removeEventListener("pointerdown", c);
  }, [open]);
  const it = (label, f, mono) => html`<div class="row" onClick=${() => { setOpen(false); onExport(f, mono); }}><span class="check"></span><div>${label}</div></div>`;
  return html`<div class="picker" ref=${ref}>
    <button class="btn" onClick=${() => setOpen(!open)} aria-haspopup="menu">Export ▾</button>
    ${open && html`<div class="popover" role="menu" style="left:auto;right:0;width:250px">
      ${it("PNG (publication, 150 dpi)", "png")}${it("PDF (vector)", "pdf")}${it("SVG (vector)", "svg")}
      ${it("PDF — black & white, dashed", "pdf", true)}<hr/>${it("CSV — the tracks behind the plot", "csv")}
    </div>`}
  </div>`;
}

// ------------------------------------------------------------------------- the chart
function buildFigure(d, targets, prefs, state, opts = {}) {
  const narrow = typeof window !== "undefined" && window.innerWidth < 760;
  const red = state.theme === "red";
  const ink2 = css("--text-2"), muted = css("--muted"), grid = css("--grid"), surf = css("--surface");
  const x = d.x;
  const isAm = prefs.yAxis === "airmass";
  const yOf = (alt) => (isAm ? (alt > 0 ? hardie(alt) : NaN) : alt);
  const traces = [];
  const n = d.night;
  const names = d.tracks.names;
  const hl = state.hoverId;
  const tz = state.sites.find((x) => x.key === state.siteKey)?.tz;
  traces.push({
    x, y: x.map(() => (prefs.yAxis === "airmass" ? 1.0 : 90)), mode: "lines", showlegend: false, name: "time",
    line: { width: 0, color: "rgba(0,0,0,0)" },
    customdata: d.tracks.jd.map((jd, k) => `${tz ? localTime(jd, tz, false) : ""} local · ${utcTime(jd, false)} UT · LST ${hm(d.tracks.last_h[k])}`),
    hovertemplate: "<b>%{customdata}</b><extra></extra>",
  });

  targets.forEach((t, i) => {
    const idx = d.ids.indexOf(t.id);
    if (idx < 0) return;
    const alt = d.tracks.alt[idx];
    const y = alt.map((a) => { const v = yOf(a); return isAm && v > prefs.yMax + 0.5 ? NaN : v; });
    const col = red ? css("--s1") : t.slot != null ? css(`--s${t.slot + 1}`) : css("--context");
    const s = d.summary[idx];
    const sep = s?.min_moon_sep;
    const dim = hl && hl !== t.id;
    traces.push({
      x, y, type: "scatter", mode: "lines", name: `${t.name}${sep != null ? ` · Moon ≥ ${sep.toFixed(0)}°` : ""}`,
      line: { color: col, width: hl === t.id ? 3 : 2, dash: red ? DASHES[i % DASHES.length] : "solid", shape: "spline", smoothing: 0.4 },
      opacity: dim ? 0.25 : 1, meta: t.id,
      customdata: alt.map((a, k) => [a > 0 ? hardie(a).toFixed(2) : "down", a.toFixed(1), hm(d.tracks.ha_h[idx][k], true), d.tracks.moon_sep[idx][k].toFixed(0)]),
      hovertemplate: `X %{customdata[0]}  ·  %{customdata[1]}°  ·  HA %{customdata[2]}  ·  Moon %{customdata[3]}°<extra>${escapeHtml(t.name)}</extra>`,
      showlegend: true,
    });
  });
  if (prefs.showMoon) {
    traces.push({
      x, y: d.tracks.moon_alt.map((a) => { const v = yOf(a); return isAm && v > prefs.yMax + 0.5 ? NaN : v; }),
      type: "scatter", mode: "lines", name: `Moon · ${Math.round(n.moon_illum * 100)}%`, line: { color: css("--moon"), width: 1.5 },
      customdata: d.tracks.moon_alt, hovertemplate: `%{customdata:.1f}°<extra>Moon</extra>`, showlegend: true,
    });
  }
  // invisible trace to carry the top (UT/LST) axis
  traces.push({ x: [x[0], x[x.length - 1]], y: [null, null], xaxis: "x2", showlegend: false, hoverinfo: "skip", mode: "markers", marker: { opacity: 0 } });
  traces.push({ x: [x[0], x[x.length - 1]], y: [null, null], yaxis: "y2", showlegend: false, hoverinfo: "skip", mode: "markers", marker: { opacity: 0 } });

  // twilight & day bands
  const shapes = [];
  const band = (a, b, fill) => { if (a && b) shapes.push({ type: "rect", xref: "x", yref: "paper", x0: a.x ?? (a.jd - n.midnight.jd) * 24, x1: b.x ?? (b.jd - n.midnight.jd) * 24, y0: 0, y1: 1, fillcolor: fill, line: { width: 0 }, layer: "below" }); };
  const xs = (e) => (e ? { x: (e.jd - n.midnight.jd) * 24 } : null);
  const tw = n.twilight;
  const L = { x: x[0] }, R = { x: x[x.length - 1] };
  band(L, xs(n.sunset) || R, css("--day"));
  band(xs(n.sunrise) || L, R, css("--day"));
  band(xs(n.sunset), xs(tw.civil.evening), css("--twilight-civil"));
  band(xs(tw.civil.morning), xs(n.sunrise), css("--twilight-civil"));
  band(xs(tw.civil.evening), xs(tw.nautical.evening), css("--twilight-nautical"));
  band(xs(tw.nautical.morning), xs(tw.civil.morning), css("--twilight-nautical"));
  band(xs(tw.nautical.evening), xs(tw.astronomical.evening), css("--twilight-astro"));
  band(xs(tw.astronomical.morning), xs(tw.nautical.morning), css("--twilight-astro"));
  // limit line (dashed: it is a threshold, not a gridline)
  const limY = isAm ? prefs.limit : altForAirmass(prefs.limit);
  shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: limY, y1: limY, line: { color: muted, width: 1, dash: "dash" } });
  // "now" (program time)
  const nowX = (state.jd - n.midnight.jd) * 24;
  if (nowX >= x[0] && nowX <= x[x.length - 1]) shapes.push({ type: "line", xref: "x", yref: "paper", x0: nowX, x1: nowX, y0: 0, y1: 1, line: { color: css("--accent"), width: 1.5 } });

  const annotations = [{ xref: "paper", yref: "y", x: 0.005, y: limY, xanchor: "left", yanchor: isAm ? "bottom" : "bottom", text: `limit X = ${prefs.limit}`, showarrow: false, font: { size: 10, color: muted } }];
  // direct labels at the peak for up to four curves (legend carries the rest)
  if (!opts.compact && !narrow && targets.length <= 4) {
    targets.forEach((t) => {
      const idx = d.ids.indexOf(t.id);
      if (idx < 0) return;
      const alt = d.tracks.alt[idx];
      let k = 0;
      alt.forEach((a, j) => { if (a > alt[k]) k = j; });
      const y = yOf(alt[k]);
      if (!isFinite(y) || (isAm && y > prefs.yMax)) return;
      annotations.push({ x: x[k], y, text: escapeHtml(t.name), showarrow: false, yanchor: "bottom", yshift: 4, font: { size: 11, color: ink2 } });
    });
  }
  // twilight labels along the top edge (evening side)
  const tl = [[n.sunset, "sunset"], [tw.civil.evening, "civil"], [tw.nautical.evening, "naut."], [tw.astronomical.evening, "astro."]];
  if (!opts.compact && !narrow) for (const [e, label] of tl) if (e) annotations.push({ xref: "x", yref: "paper", x: (e.jd - n.midnight.jd) * 24, y: 0, yanchor: "bottom", xanchor: "left", xshift: 2, text: label, showarrow: false, textangle: -90, font: { size: 9, color: muted } });

  const every = opts.compact || narrow ? (narrow && !opts.compact ? 3 : 2) : 1;
  const ticks = d.ticks.filter((t, i) => i % every === 0);
  const yRange = isAm ? [prefs.yMax, 1.0] : [0, 90];
  const rightVals = isAm ? ALT_TICKS.map(hardie).filter((v) => v <= prefs.yMax) : AM_TICKS.map(altForAirmass);
  const rightText = isAm ? ALT_TICKS.filter((a) => hardie(a) <= prefs.yMax).map((a) => `${a}°`) : AM_TICKS.map((v) => v.toFixed(v < 2 ? 1 : 1));
  const font = { family: css("--font") || "system-ui", size: 11, color: ink2 };
  const layout = {
    paper_bgcolor: surf, plot_bgcolor: surf, font,
    margin: opts.compact ? { l: 44, r: 40, t: 34, b: 30 } : narrow ? { l: 40, r: 38, t: 56, b: 40 } : { l: 56, r: 56, t: 64, b: 46 },
    height: opts.height || (narrow ? 400 : 470),
    xaxis: { unifiedhovertitle: { text: "\u200b" }, range: [x[0], x[x.length - 1]], tickvals: ticks.map((t) => t.x), ticktext: ticks.map((t) => t.local), showgrid: false, zeroline: false,
      linecolor: css("--axis"), ticks: "outside", tickcolor: css("--axis"), title: opts.compact || narrow ? undefined : { text: `Local time (${zoneText(d.ticks[0]?.zone)})`, font: { size: 11, color: muted } }, fixedrange: true },
    xaxis2: { overlaying: "x", side: "top", range: [x[0], x[x.length - 1]], tickvals: ticks.map((t) => t.x), ticktext: ticks.map((t) => (opts.compact ? t.ut : `${t.ut}<br><span style="color:${muted}">${t.lst}</span>`)), showgrid: false, zeroline: false, ticks: "outside", tickcolor: css("--axis"), fixedrange: true, tickfont: { size: 10, color: ink2 } },
    yaxis: { range: yRange, title: { text: isAm ? "Airmass" : "Altitude (°)", font: { size: 11, color: muted } }, gridcolor: grid, zeroline: false, linecolor: css("--axis"), fixedrange: true, dtick: isAm ? (prefs.yMax > 3 ? 0.5 : 0.25) : 15 },
    yaxis2: { overlaying: "y", side: "right", range: yRange, tickvals: rightVals, ticktext: rightText, showgrid: false, zeroline: false, title: { text: isAm ? "Altitude" : "Airmass", font: { size: 11, color: muted } }, fixedrange: true },
    showlegend: true, legend: opts.compact ? { orientation: "h", y: -0.12, x: 0, font: { size: 9, color: ink2 } } : { orientation: "h", y: -0.16, x: 0, font: { size: 11, color: ink2 } },
    hovermode: "x unified", hoverlabel: { bgcolor: css("--surface"), bordercolor: css("--border-strong"), font: { color: css("--text"), size: 12 } },
    shapes, annotations,
  };
  if (!opts.compact) layout.title = { text: "UT / <span style='color:" + muted + "'>LST</span>", x: 0.005, xanchor: "left", y: 0.995, yanchor: "top", font: { size: 10, color: ink2 } };
  return { traces, layout };
}
const zoneText = (z) => (z && /^[+-]\d\d$/.test(z) ? `UTC${z[0] === "-" ? "−" : "+"}${+z.slice(1)}` : z || "");
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function PlotlyChart({ fig, onClickX, onLegend, compact }) {
  const ref = useRef();
  useEffect(() => {
    const el = ref.current;
    if (!el || !window.Plotly) return;
    window.Plotly.react(el, fig.traces, fig.layout, { displaylogo: false, responsive: true, displayModeBar: window.innerWidth >= 760 ? "hover" : false, modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "zoom2d", "pan2d", "zoomIn2d", "zoomOut2d", "resetScale2d"], toImageButtonOptions: { format: "png", scale: 2, filename: "artairmass" } });
    el.removeAllListeners?.("plotly_click");
    el.removeAllListeners?.("plotly_legendclick");
    if (onClickX) el.on("plotly_click", (ev) => { const p = ev.points?.[0]; if (p) onClickX(p.x); });
    if (onLegend) el.on("plotly_legendclick", (ev) => onLegend(ev.data[ev.curveNumber]?.meta));
  }, [fig]);
  useEffect(() => () => { if (ref.current && window.Plotly) window.Plotly.purge(ref.current); }, []);
  return html`<div ref=${ref} class=${compact ? "" : "plot"} role="img" aria-label="Airmass versus time"></div>`;
}

function SingleNight({ data, prefs, busy, site }) {
  const { state, dispatch, actions } = useContext(Store);
  const targets = state.targets.filter((t) => t.visible !== false && data.ids.includes(t.id));
  const fig = useMemo(() => buildFigure(data, targets, prefs, state), [data, prefs, state.theme, state.hoverId, Math.round(state.jd * 1440), targets.map((t) => t.slot).join()]);
  const n = data.night;
  return html`
    <section class=${"card plot-card" + (busy ? " loading" : "")}>
      <${PlotlyChart} fig=${fig}
        onClickX=${(x) => actions.setJd(n.midnight.jd + x / 24)}
        onLegend=${(id) => { if (id) { dispatch({ type: "updateTarget", id, patch: { visible: false } }); actions.toast("Hidden — tick it in the sidebar to show again"); } return false; }}/>
      <div class="muted" style="font-size:.8rem;padding:0 8px 6px">Click the chart to move the program time there. Shading: daylight, then civil, nautical and astronomical twilight. Click a legend entry to hide a target.</div>
    </section>
    <div style="height:12px"></div>
    <${SummaryTable} data=${data} targets=${targets} prefs=${prefs}/>
    <div style="height:12px"></div>
    <div class="grid">
      <${Almanac} n=${n} site=${site}/>
      <${Hourly} site=${site}/>
    </div>`;
}

function SummaryTable({ data, targets, prefs }) {
  const { state, actions } = useContext(Store);
  if (!targets.length) return null;
  const rows = targets.map((t) => ({ t, s: data.summary[data.ids.indexOf(t.id)] }));
  const tm = (e) => (e ? e.local : "—");
  return html`<section class="card">
    <h3>Tonight at a glance <small class="muted" style="text-transform:none;letter-spacing:0">limit X = ${prefs.limit}, dark = ${prefs.twilight} twilight · click a row to select</small></h3>
    <div style="overflow:auto"><table class="tbl">
      <thead><tr><th>Target</th><th title="Rises above the airmass limit">Rises ${"<"} X</th><th title="Sets below the airmass limit">Sets ${">"} X</th><th>Transit</th><th title="Meridian altitude">Transit alt</th>
        <th title="Highest altitude during dark time">Best in dark</th><th title="Hours in dark time with airmass below the limit">Dark h ${"<"} X</th><th title="First–last observable time in dark">Window</th><th title="Smallest Moon distance during the window">Moon ≥</th></tr></thead>
      <tbody>${rows.map(({ t, s }) => {
        const sel = t.id === state.selectedId;
        const lvl = s.dark_hours > 0 ? null : { level: "critical", label: "not observable" };
        return html`<tr class="clickable" style=${sel ? "background:var(--accent-soft)" : ""} onClick=${() => actions.select(t.id)}>
          <td style="font-family:var(--font)"><span class="swatch" style=${`background:${t.slot != null ? `var(--s${t.slot + 1})` : "var(--context)"};margin-right:8px`}></span>${t.name}</td>
          <td>${s.always_above ? "up" : tm(s.rise)}</td><td>${s.always_above ? "—" : tm(s.set)}</td>
          <td class=${s.transit_in_night ? "" : "w-muted"}>${tm(s.transit)}</td>
          <td>${s.transit_alt != null ? fix(s.transit_alt, 1) + "°" : "—"}</td>
          <td>${s.max_alt_dark != null && s.max_alt_dark > 0 ? html`${fix(s.max_alt_dark, 1)}° <small class="muted">X ${fix(s.min_airmass_dark, 2)} @ ${tm(s.max_alt)}</small>` : "below"}</td>
          <td>${lvl ? html`<span class=${"status " + lvl.level}>${lvl.label}</span>` : fix(s.dark_hours, 1)}</td>
          <td>${s.window_start ? `${tm(s.window_start)}–${tm(s.window_end)}` : "—"}</td>
          <td class=${s.min_moon_sep != null && s.min_moon_sep < 25 && data.night.moon_illum > 0.3 ? "w-serious" : ""}>${s.min_moon_sep != null ? fix(s.min_moon_sep, 0) + "°" : "—"}</td>
        </tr>`;
      })}</tbody></table></div>
  </section>`;
}

function Almanac({ n, site }) {
  const e = (x) => (x ? html`${x.local} <small class="muted">${x.ut} UT</small>` : html`<span class="muted">—</span>`);
  const tw = n.twilight;
  const moonEv = n.moon_events.map((m) => html`<dt>Moon${m.kind}</dt><dd>${m.local} <small class="muted">${m.ut} UT</small></dd>`);
  return html`<section class="card">
    <h3>Almanac · night of ${n.date}</h3>
    ${n.sun_status !== "normal" && html`<div class="status warning" style="margin-bottom:8px">${n.sun_status === "sun_never_sets" ? "Midnight sun — the Sun does not set" : "Polar night — the Sun does not rise"}</div>`}
    <dl class="kv">
      <dt title="Upper limb on the horizon (−0.83° + horizon dip)">Sunset</dt><dd>${e(n.sunset)}</dd>
      <dt>Civil twilight ends (−6°)</dt><dd>${e(tw.civil.evening)}</dd>
      <dt>Nautical ends (−12°)</dt><dd>${e(tw.nautical.evening)}</dd>
      <dt>Astronomical ends (−18°)</dt><dd>${e(tw.astronomical.evening)}</dd>
      <dt title="Midpoint of sunset and sunrise">Night centre</dt><dd>${e(n.night_center)}</dd>
      <dt>Astronomical begins</dt><dd>${e(tw.astronomical.morning)}</dd>
      <dt>Nautical begins</dt><dd>${e(tw.nautical.morning)}</dd>
      <dt>Civil begins</dt><dd>${e(tw.civil.morning)}</dd>
      <dt>Sunrise</dt><dd>${e(n.sunrise)}</dd>
      <dt>LST at 18° twilights</dt><dd>${tw.astronomical.evening?.lst ?? "—"} → ${tw.astronomical.morning?.lst ?? "—"}</dd>
      <dt>LST at midnight</dt><dd>${n.midnight.lst}</dd>
      <dt>Dark time</dt><dd>${fix(n.dark_hours.astronomical, 2)} h <small class="muted">astro · ${fix(n.dark_hours.nautical, 2)} h naut.</small></dd>
      ${moonEv}
      <dt>Moon at midnight</dt><dd>${fix(n.moon_illum * 100, 0)}% <small class="muted">${n.moon_phase.replace(/\.$/, "")}</small></dd>
    </dl>
  </section>`;
}

function Hourly({ site }) {
  const { state, actions } = useContext(Store);
  const target = state.targets.find((t) => t.id === state.selectedId);
  const [rows, setRows] = useState(null);
  const night = nightOf(state.jd, site.tz);
  useEffect(() => {
    if (!target) { setRows(null); return; }
    let alive = true;
    api.post("/api/hourly", { site: state.siteKey, time: state.jd, target: targetPayload(target), airmass_model: state.settings?.airmass_model || "hardie" })
      .then((r) => alive && setRows(r.rows)).catch((e) => actions.toast(e.message, true));
    return () => { alive = false; };
  }, [state.siteKey, night, target?.id, target?.ra, target?.dec]);
  const csv = () => {
    const head = "local,ut,lst,ha,alt_deg,airmass,moon_alt,sun_alt,moon_sep";
    const body = rows.map((r) => [r.local, r.ut, r.lst, r.ha, r.alt.toFixed(2), r.airmass ? r.airmass.toFixed(3) : "", r.moon_alt.toFixed(1), r.sun_alt.toFixed(1), r.moon_sep.toFixed(1)].join(","));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([[head, ...body].join("\n") + "\n"], { type: "text/csv" }));
    a.download = `hourly_${(target.name || "target").replace(/\W+/g, "_")}_${night}.csv`;
    a.click();
  };
  const amClass = (r) => (r.alt <= 0 ? "w-muted" : r.airmass >= 4 ? "w-critical" : r.airmass >= 3 ? "w-serious" : r.airmass >= 2 ? "w-warning" : "");
  return html`<section class="card">
    <h3>Hourly circumstances${target ? ` · ${target.name}` : ""} ${rows && html`<button class="btn ghost" style="height:24px" onClick=${csv}>CSV</button>`}</h3>
    ${!target ? html`<div class="muted">Select a target to see its hour-by-hour table.</div>` : !rows ? html`<div class="muted">Computing…</div>` : html`
    <div style="overflow:auto;max-height:420px"><table class="tbl">
      <thead><tr><th>Local</th><th>UT</th><th>LST</th><th>HA</th><th>Airmass</th><th>Alt</th><th>Moon alt</th><th>Sun alt</th><th>Moon sep</th></tr></thead>
      <tbody>${rows.map((r) => html`<tr class="clickable" onClick=${() => actions.setJd(r.jd)}>
        <td>${r.local}</td><td>${r.ut}</td><td>${r.lst}</td><td class=${Math.abs(r.ha_h) > 6 ? "w-warning" : ""}>${r.ha}</td>
        <td class=${amClass(r)}>${r.airmass_str.trim()}</td><td>${fix(r.alt, 1)}</td>
        <td class=${r.moon_alt > 0 ? "" : "w-muted"}>${fix(r.moon_alt, 1)}</td><td class=${r.sun_alt > -12 ? "w-warning" : ""}>${fix(r.sun_alt, 1)}</td><td>${fix(r.moon_sep, 0)}°</td>
      </tr>`)}</tbody></table></div>`}
  </section>`;
}

// ------------------------------------------------------------------------- run view
function RunView({ data, prefs, busy, site }) {
  const { state, actions } = useContext(Store);
  const targets = state.targets.filter((t) => t.visible !== false && data.ids.includes(t.id));
  return html`<div class=${busy ? "loading" : ""}>
    <section class="card">
      <h3>Observing run · ${data.nights.length} nights from ${data.nights[0].night.date} <small class="muted" style="text-transform:none;letter-spacing:0">dark hours with X ${"<"} ${prefs.limit} · click a night to open it</small></h3>
      <div style="overflow:auto"><table class="tbl">
        <thead><tr><th>Target</th>${data.nights.map((nn) => html`<th style="cursor:pointer" onClick=${() => actions.setLocal(`${nn.night.date} 22:00`)}>${nn.night.date.slice(5)}<br/><small>${Math.round(nn.night.moon_illum * 100)}% ☾</small></th>`)}</tr></thead>
        <tbody>${targets.map((t) => html`<tr>
          <td style="font-family:var(--font)"><span class="swatch" style=${`background:${t.slot != null ? `var(--s${t.slot + 1})` : "var(--context)"};margin-right:8px`}></span>${t.name}</td>
          ${data.nights.map((nn) => {
            const s = nn.summary[data.ids.indexOf(t.id)];
            const h = s?.dark_hours ?? 0;
            return html`<td title=${s?.window_start ? `${s.window_start.local}–${s.window_end.local}, best ${fix(s.max_alt_dark, 0)}°, Moon ≥ ${fix(s.min_moon_sep, 0)}°` : "not observable"}
              style=${`background:color-mix(in srgb, var(--s1) ${Math.min(100, (h / 10) * 55)}%, transparent)`}>${h > 0 ? fix(h, 1) : html`<span class="muted">—</span>`}</td>`;
          })}
        </tr>`)}
        <tr><td class="muted" style="font-family:var(--font)">Dark time</td>${data.nights.map((nn) => html`<td class="muted">${fix(nn.night.dark_hours[prefs.twilight] ?? nn.night.dark_hours.astronomical, 1)}</td>`)}</tr>
        </tbody></table></div>
    </section>
    <div style="height:12px"></div>
    <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(420px,1fr))">
      ${data.nights.map((nn) => html`<section class="card plot-card" style="cursor:pointer">
        <h3 style="margin:6px 8px 0" onClick=${() => actions.setLocal(`${nn.night.date} 22:00`)}>${nn.night.date} <small class="muted">Moon ${Math.round(nn.night.moon_illum * 100)}%</small></h3>
        <${PlotlyChart} compact=${true} fig=${buildFigure({ ...nn, ids: data.ids }, targets, prefs, state, { compact: true, height: 330 })}/>
      </section>`)}
    </div>
  </div>`;
}
