// Season view: best time of year (hours per night vs date), plain-language advice,
// proposal semesters, list heatmap (targets × months) and JSkyCalc's seasonal table.
import { html, useContext, useState, useEffect, useMemo } from "../lib.js";
import { Store, targetPayload, DASHES } from "../store.js";
import { api } from "../api.js";
import { fix } from "../format.js";
import { css, PlotlyChart } from "./night.js";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const loadP = () => { try { return JSON.parse(localStorage.getItem("artairmass.v1.seasonPrefs")) || {}; } catch (e) { return {}; } };

export function SeasonView() {
  const { state, actions } = useContext(Store);
  const site = state.sites.find((s) => s.key === state.siteKey);
  const [p, setP] = useState(() => ({ scope: "selected", limitKind: "airmass", alt: 30, moon: "bright", maxIllum: 0.5, minSep: 0, period: "next12", ...loadP() }));
  useEffect(() => { try { localStorage.setItem("artairmass.v1.seasonPrefs", JSON.stringify(p)); } catch (e) { /* */ } }, [p]);
  const s = state.settings || {};
  const limit = p.limitKind === "airmass" ? (s.airmass_limit ?? 2) : p.alt;
  const twilight = s.twilight === "civil" ? "nautical" : (s.twilight ?? "astronomical");
  const selected = state.targets.find((t) => t.id === state.selectedId);
  const fixed = state.targets.filter((t) => !t.body);
  const targets = p.scope === "selected" ? (selected && !selected.body ? [selected] : []) : fixed.filter((t) => t.visible !== false);
  const start = useMemo(() => {
    const d = new Date((state.jd - 2440587.5) * 864e5);
    const y = d.getUTCFullYear(), m = d.getUTCMonth();
    if (p.period === "thisyear") return `${y}-01-01`;
    if (p.period === "nextyear") return `${y + 1}-01-01`;
    return `${y}-${String(m + 1).padStart(2, "0")}-01`;
  }, [p.period, Math.floor(state.jd / 30)]);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const key = JSON.stringify([state.siteKey, start, targets.map((t) => [t.id, t.ra, t.dec, t.name]), limit, p.limitKind, twilight, p.moon, p.maxIllum, p.minSep, s.airmass_model]);

  useEffect(() => {
    if (!targets.length) { setData(null); return; }
    let alive = true;
    setBusy(true);
    const t = setTimeout(() => {
      api.post("/api/besttime", { site: state.siteKey, targets: targets.map(targetPayload), start, days: 365, limit, limit_kind: p.limitKind,
        twilight, moon: p.moon, max_illum: p.maxIllum, min_sep: p.minSep, airmass_model: s.airmass_model || "hardie" })
        .then((r) => alive && setData({ ...r, ids: targets.map((x) => x.id) }))
        .catch((e) => actions.toast(e.message, true))
        .finally(() => alive && setBusy(false));
    }, 200);
    return () => { alive = false; clearTimeout(t); };
  }, [key]);

  // Only targets present in the current result (data may be stale while a new request runs).
  const shown = data ? targets.filter((t) => data.ids.includes(t.id)) : [];
  const seg = (k, opts, title) => html`<div class="seg" title=${title || ""}>${opts.map(([v, l]) => html`<button aria-pressed=${p[k] === v} onClick=${() => setP({ ...p, [k]: v })}>${l}</button>`)}</div>`;
  return html`<div>
    <div class="toolbar" role="toolbar" aria-label="Season controls">
      ${seg("scope", [["selected", "Selected target"], ["list", `Whole list (${fixed.filter((t) => t.visible !== false).length})`]])}
      ${seg("period", [["next12", "Next 12 months"], ["thisyear", "This year"], ["nextyear", "Next year"]])}
      ${seg("limitKind", [["airmass", "Airmass"], ["altitude", "Altitude"]], "Limit type")}
      ${p.limitKind === "airmass"
        ? html`<label class="field"><span>X ≤</span><input class="inp mono" type="number" step="0.1" style="width:66px" value=${limit} onChange=${(e) => { const v = parseFloat(e.target.value); if (v > 1) actions.saveSettings({ ...s, airmass_limit: v }); }}/></label>`
        : html`<label class="field"><span>alt ≥</span><input class="inp mono" type="number" step="1" style="width:66px" value=${p.alt} onChange=${(e) => setP({ ...p, alt: parseFloat(e.target.value) || 30 })}/><span>°</span></label>`}
      <label class="field"><span>dark after</span><select class="inp" value=${twilight} onChange=${(e) => actions.saveSettings({ ...s, twilight: e.target.value })}>
        <option value="astronomical">astronomical</option><option value="nautical">nautical</option></select></label>
      <span title="Moon constraint while the Moon is up: dark ≤ 35% illuminated, grey ≤ 70%, bright = any">${seg("moon", [["bright", "Any moon"], ["grey", "Grey"], ["dark", "Dark"], ["custom", "Custom"]])}</span>
      ${p.moon === "custom" && html`<label class="field"><span>illum ≤</span><input class="inp mono" type="number" step="0.05" min="0" max="1" style="width:64px" value=${p.maxIllum} onChange=${(e) => setP({ ...p, maxIllum: Math.max(0, Math.min(1, parseFloat(e.target.value) || 0)) })}/></label>`}
      <label class="field" title="Minimum Moon–target distance while the Moon is up"><span>Moon ≥</span><input class="inp mono" type="number" step="5" min="0" max="180" style="width:60px" value=${p.minSep} onChange=${(e) => setP({ ...p, minSep: Math.max(0, parseFloat(e.target.value) || 0) })}/><span>°</span></label>
    </div>
    ${!targets.length && html`<div class="placeholder">${p.scope === "selected" ? "Select a fixed (non-planet) target, or switch to the whole list." : "The list has no visible fixed targets."}</div>`}
    ${targets.length > 0 && !data && html`<div class="placeholder">Computing a year of nights…</div>`}
    ${data && shown.length > 0 && html`<div class=${busy ? "loading" : ""}>
      <${YearPlot} data=${data} targets=${shown} single=${shown.length === 1}/>
      <div style="height:12px"></div>
      <${Advice} data=${data} targets=${shown}/>
      ${shown.length > 1 && html`<div style="height:12px"></div><${Heatmap} data=${data} targets=${shown}/>`}
    </div>`}
    ${selected && !selected.body && html`<div style="height:12px"></div><${JSkySeasonal} target=${selected}/>`}
  </div>`;
}

function semesterBands(dates) {
  const out = [];
  let cur = null;
  const label = (iso) => {
    const y = +iso.slice(0, 4), m = +iso.slice(5, 7);
    return m >= 2 && m <= 7 ? `${y}A` : `${m >= 8 ? y : y - 1}B`;
  };
  for (const d of dates) {
    const l = label(d);
    if (!cur || cur.l !== l) { cur = { l, a: d, b: d }; out.push(cur); } else cur.b = d;
  }
  return out;
}

function YearPlot({ data, targets, single }) {
  const { state, actions } = useContext(Store);
  const red = state.theme === "red";
  const fig = useMemo(() => {
    const x = data.dates;
    const traces = [{ x, y: data.dark_hours, name: "Dark time available", mode: "lines", line: { color: css("--muted"), width: 1, shape: "hv" }, hovertemplate: "%{y:.1f} h<extra>dark time</extra>" }];
    targets.forEach((t, i) => {
      const k = data.ids.indexOf(t.id);
      const tt = data.targets[k];
      const col = red ? css("--s1") : t.slot != null ? css(`--s${t.slot + 1}`) : css("--context");
      const moonLimited = data.settings.moon !== "bright" || data.settings.min_sep > 0;
      if (single && moonLimited) traces.push({ x, y: tt.hours_no_moon, name: "ignoring the Moon", mode: "lines", line: { color: col, width: 1 }, opacity: 0.4, hovertemplate: "%{y:.1f} h<extra>no Moon limit</extra>" });
      traces.push({ x, y: tt.hours, name: t.name, mode: "lines", line: { color: col, width: 2, dash: red ? DASHES[i % DASHES.length] : "solid" }, hovertemplate: `%{y:.1f} h<extra>${String(t.name).replace(/</g, "&lt;")}</extra>` });
    });
    traces.push({ x, y: data.moon_illum.map((v) => v * 100), name: "Moon illum. (%)", yaxis: "y2", mode: "lines", line: { color: css("--moon"), width: 1 }, opacity: 0.55, hovertemplate: "%{y:.0f}%<extra>Moon</extra>", visible: "legendonly" });
    const shapes = [], annotations = [];
    semesterBands(x).forEach((b, i) => {
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: b.a, x1: b.b, y0: 0, y1: 1, fillcolor: b.l.endsWith("A") ? css("--accent-soft") : "rgba(0,0,0,0)", line: { width: 0 }, layer: "below" });
      annotations.push({ xref: "x", yref: "paper", x: b.a, y: 1, xanchor: "left", yanchor: "bottom", text: `<b>${b.l}</b>`, showarrow: false, font: { size: 11, color: css("--text-2") } });
    });
    targets.forEach((t) => {
      const tt = data.targets[data.ids.indexOf(t.id)];
      if (!tt.midnight_transit) return;
      shapes.push({ type: "line", xref: "x", yref: "paper", x0: tt.midnight_transit, x1: tt.midnight_transit, y0: 0, y1: 0.94, line: { color: css("--text-2"), width: 1, dash: "dot" } });
      if (single || targets.length <= 4) annotations.push({ x: tt.midnight_transit, yref: "paper", y: 0.94, text: single ? "transits at midnight" : `${t.name} @ midnight`, showarrow: false, yanchor: "bottom", font: { size: 10, color: css("--muted") } });
    });
    const surf = css("--surface");
    return {
      traces,
      layout: {
        paper_bgcolor: surf, plot_bgcolor: surf, height: 400, margin: { l: 52, r: 52, t: 40, b: 40 },
        font: { family: css("--font"), size: 11, color: css("--text-2") },
        xaxis: { type: "date", tickformat: "%b", dtick: "M1", showgrid: false, linecolor: css("--axis"), fixedrange: true },
        yaxis: { title: { text: "Hours per night", font: { size: 11, color: css("--muted") } }, gridcolor: css("--grid"), rangemode: "tozero", zeroline: false, fixedrange: true },
        yaxis2: { overlaying: "y", side: "right", range: [0, 100], title: { text: "Moon %", font: { size: 11, color: css("--muted") } }, showgrid: false, fixedrange: true },
        legend: { orientation: "h", y: -0.12, font: { size: 11 } }, hovermode: "x unified",
        hoverlabel: { bgcolor: surf, bordercolor: css("--border-strong"), font: { color: css("--text") } },
        shapes, annotations,
      },
    };
  }, [data, state.theme, targets.map((t) => t.slot).join()]);
  return html`<section class="card plot-card">
    <h3 style="margin:6px 8px 0">Observable hours per night <small class="muted" style="text-transform:none;letter-spacing:0">
      ${data.settings.limit_kind === "airmass" ? `X ≤ ${data.settings.limit}` : `alt ≥ ${data.settings.limit}°`} · Sun ${"<"} ${data.settings.twilight === "nautical" ? "−12°" : "−18°"} ·
      ${data.settings.moon === "bright" ? "any Moon" : `Moon ≤ ${Math.round(data.settings.max_illum * 100)}%`}${data.settings.min_sep ? ` & ≥ ${data.settings.min_sep}° away` : ""} · shaded = semester A (Feb–Jul) · click a date to open that night</small></h3>
    <${PlotlyChart} fig=${fig} onClickX=${(xv) => { const d = String(xv).slice(0, 10); actions.setLocal(`${d} 22:00`); }}/>
  </section>`;
}

function Advice({ data, targets }) {
  const { state, actions } = useContext(Store);
  return html`<section class="card">
    <h3>When to observe</h3>
    <div style="display:grid;gap:12px">
      ${targets.map((t) => {
        const tt = data.targets[data.ids.indexOf(t.id)];
        const st = tt.semester_type_hours || { A: 0, B: 0 };
        const tot = st.A + st.B;
        return html`<div style="display:grid;grid-template-columns:minmax(140px,200px) 1fr;gap:12px;align-items:start">
          <div><b style="font-size:1.02rem">${t.name}</b>
            ${tt.recommended_semester && html`<div style="margin-top:4px" title=${`${tt.recommended_type} semesters suit this target best; the next one is ${tt.recommended_semester}`}><span class="status good">${tt.recommended_type} semester · next ${tt.recommended_semester}</span></div>`}
            ${tt.midnight_transit && html`<div class="muted" style="font-size:.8rem;margin-top:4px">transits at midnight ${new Date(tt.midnight_transit + "T00:00:00Z").toUTCString().slice(5, 11)}</div>`}</div>
          <div>
            <div style="line-height:1.5">${tt.summary}</div>
            ${tot > 0 && html`<div style="display:flex;gap:2px;margin-top:8px;height:8px;border-radius:4px;overflow:hidden" title="Observable hours in A-type (Feb–Jul) vs B-type (Aug–Jan) semesters">
              <div style=${`flex:${st.A};background:var(--accent)`}></div><div style=${`flex:${st.B};background:var(--muted)`}></div></div>
              <div class="muted" style="font-size:.78rem;margin-top:4px">A (Feb–Jul): ${fix(st.A, 0)} h · ${Math.round((100 * st.A) / tot)}% · B (Aug–Jan): ${fix(st.B, 0)} h · ${Math.round((100 * st.B) / tot)}%</div>`}
          </div>
        </div>`;
      })}
    </div>
  </section>`;
}

function Heatmap({ data, targets }) {
  const { state, actions } = useContext(Store);
  const fig = useMemo(() => {
    const months = data.monthly.months;
    const z = targets.map((t) => data.monthly.mean_hours[data.ids.indexOf(t.id)]);
    const theme = state.theme;
    const scale = theme === "red" ? [[0, "#070000"], [1, "#ff4a3a"]]
      : theme === "light" ? [[0, "#f4f8fe"], [0.2, "#cde2fb"], [0.45, "#86b6ef"], [0.7, "#2a78d6"], [1, "#0d366b"]]
      : [[0, "#1b2029"], [0.25, "#184f95"], [0.6, "#3987e5"], [1, "#b7d3f6"]];
    const zmax = Math.max(1, ...z.flat());
    const surf = css("--surface");
    return {
      traces: [{
        type: "heatmap", x: months.map((m) => `${m.slice(0, 3)} '${m.slice(-2)}`), y: targets.map((t) => t.name), z, zmin: 0, zmax,
        colorscale: scale, xgap: 2, ygap: 2, colorbar: { title: { text: "h/night", side: "right" }, thickness: 10, outlinewidth: 0, tickfont: { color: css("--text-2") } },
        hovertemplate: "<b>%{y}</b><br>%{x}: %{z:.1f} h/night<extra></extra>",
      }],
      layout: {
        annotations: targets.length > 25 ? [] : z.flatMap((row, i) => row.map((v, j) => ({
          x: `${months[j].slice(0, 3)} '${months[j].slice(-2)}`, y: targets[i].name, text: v.toFixed(1), showarrow: false,
          font: { size: 10, color: (theme === "light" ? v / zmax > 0.55 : v / zmax < 0.6) ? "#ffffff" : "#0b0b0b" },
        }))),
        paper_bgcolor: surf, plot_bgcolor: surf, height: Math.max(220, 40 + 26 * targets.length), margin: { l: 140, r: 40, t: 20, b: 40 },
        font: { family: css("--font"), size: 11, color: css("--text-2") },
        yaxis: { autorange: "reversed", fixedrange: true, automargin: true }, xaxis: { side: "bottom", fixedrange: true },
      },
    };
  }, [data, state.theme]);
  return html`<section class="card plot-card">
    <h3 style="margin:6px 8px 0">Mean observable hours per night, by month <small class="muted" style="text-transform:none;letter-spacing:0">same constraints as above</small></h3>
    <${PlotlyChart} fig=${fig} compact=${true}/>
  </section>`;
}

/** JSkyCalc's Seasonal Observability table, verbatim layout. */
function JSkySeasonal({ target }) {
  const { state, actions } = useContext(Store);
  const [rows, setRows] = useState(null);
  useEffect(() => {
    let alive = true;
    setRows(null);
    api.post("/api/seasonal", { site: state.siteKey, time: state.jd, target: targetPayload(target), airmass_model: state.settings?.airmass_model || "hardie" })
      .then((r) => alive && setRows(r.rows)).catch((e) => actions.toast(e.message, true));
    return () => { alive = false; };
  }, [state.siteKey, Math.floor(state.jd / 7), target.id, target.ra, target.dec]);
  const am = (s) => (s.includes("down") ? "w-muted" : s.includes(">") ? "w-critical" : parseFloat(s) >= 3 ? "w-serious" : parseFloat(s) >= 2 ? "w-warning" : "");
  return html`<section class="card">
    <h3>Seasonal observability (JSkyCalc table) · ${target.name} <small class="muted" style="text-transform:none;letter-spacing:0">each new & full Moon; HA and airmass at evening 18° twilight, night centre, morning twilight; hours between twilights at X ${"<"} 3, 2, 1.5</small></h3>
    ${!rows ? html`<div class="muted">Computing…</div>` : html`<div style="overflow:auto"><table class="tbl">
      <thead><tr><th>Moon</th><th>Evening date</th><th>HA eve</th><th>X eve</th><th>HA ctr</th><th>X ctr</th><th>HA morn</th><th>X morn</th><th>h, X${"<"}3</th><th>h, X${"<"}2</th><th>h, X${"<"}1.5</th></tr></thead>
      <tbody>${rows.map((r) => html`<tr class="clickable" onClick=${() => actions.setLocal(`${r.evening_date} 22:00`)}>
        <td style="font-family:var(--font)">${r.moon === "New" ? "● New" : "○ Full"}</td><td>${r.evening_date}</td>
        <td>${r.ha_eve}</td><td class=${am(r.airmass_eve)}>${r.airmass_eve.trim()}</td>
        <td>${r.ha_ctr}</td><td class=${am(r.airmass_ctr)}>${r.airmass_ctr.trim()}</td>
        <td>${r.ha_morn}</td><td class=${am(r.airmass_morn)}>${r.airmass_morn.trim()}</td>
        <td>${fix(r["hrs_lt_3"], 1)}</td><td>${fix(r["hrs_lt_2"], 1)}</td><td>${fix(r["hrs_lt_1.5"], 1)}</td></tr>`)}</tbody></table></div>`}
  </section>`;
}
