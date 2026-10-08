// All-sky alt-az display (JSkyCalc's Sky Display, modernised).
// Projection: zenithal equidistant, zenith at centre, north up, east LEFT (the sky as seen
// looking up). Keys (when the chart has focus): f/b step, n now, z/o zoom at cursor,
// p pan to cursor, r restore, s/click select nearest target, c set coords at cursor,
// h nearest bright star, w open target URL.
import { html, useContext, useState, useRef, useMemo, useEffect, useCallback } from "../lib.js";
import { Store, seriesColor } from "../store.js";
import { fix, hms, localTime, utcTime, skyState, airmassLevel } from "../format.js";

const R = 470;              // horizon radius in SVG units
const C = 500;              // centre
const VB = 1000;
const D2R = Math.PI / 180;

function project(alt, az) {
  const r = (R * (90 - alt)) / 90;
  return [C - r * Math.sin(az * D2R), C - r * Math.cos(az * D2R)];
}
function unproject(x, y) {
  const dx = C - x, dy = C - y;
  const r = Math.hypot(dx, dy);
  return { alt: 90 - (r / R) * 90, az: ((Math.atan2(dx, dy) / D2R) + 360) % 360 };
}
function angDist(a1, z1, a2, z2) {
  const s = Math.sin(a1 * D2R) * Math.sin(a2 * D2R) + Math.cos(a1 * D2R) * Math.cos(a2 * D2R) * Math.cos((z1 - z2) * D2R);
  return Math.acos(Math.max(-1, Math.min(1, s))) / D2R;
}

// B−V → display colour (desaturated blackbody-ish ramp, as JSkyCalc does after Charity).
const BV = [[-0.4, [155, 176, 255]], [0.0, [202, 216, 255]], [0.3, [248, 247, 255]], [0.6, [255, 244, 234]],
  [0.9, [255, 228, 196]], [1.2, [255, 210, 161]], [1.6, [255, 190, 127]], [2.0, [255, 170, 100]]];
function starColor(bv, red) {
  if (red) return "var(--text)";
  let i = 0;
  while (i < BV.length - 2 && bv > BV[i + 1][0]) i++;
  const [b0, c0] = BV[i], [b1, c1] = BV[i + 1];
  const f = Math.max(0, Math.min(1, (bv - b0) / (b1 - b0)));
  const c = c0.map((v, k) => Math.round(v + (c1[k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
const starR = (v) => Math.max(0.9, 4.6 - 0.78 * v);

function skyBackground(sunAlt, theme) {
  const pal = theme === "red" ? ["#000", "#100000", "#1a0101", "#260202", "#320303"]
    : ["#05070c", "#0b1222", "#14213d", "#22365e", "#3b5a8f"];
  if (sunAlt < -18) return pal[0];
  if (sunAlt < -12) return pal[1];
  if (sunAlt < -6) return pal[2];
  if (sunAlt < -0.83) return pal[3];
  return pal[4];
}

export function SkyView({ sky, loading }) {
  const { state, dispatch, actions } = useContext(Store);
  const svgRef = useRef();
  const [view, setView] = useState({ x: 0, y: 0, w: VB });
  const [hover, setHover] = useState(null);
  const [mouse, setMouse] = useState(null);
  const site = state.sites.find((s) => s.key === state.siteKey);
  const red = state.theme === "red";

  const objects = useMemo(() => {
    if (!sky) return [];
    const out = [];
    sky.targets.forEach((t, i) => out.push({ kind: "target", id: sky.ids[i], name: t.name, alt: t.alt, az: t.az, ha: t.ha_h }));
    for (const [k, b] of Object.entries(sky.bodies)) out.push({ kind: k === "sun" || k === "moon" ? k : "planet", id: k, name: k[0].toUpperCase() + k.slice(1), alt: b.alt, az: b.az, ha: b.ha_h });
    return out;
  }, [sky]);

  const toSvg = useCallback((evt) => {
    const svg = svgRef.current;
    const pt = svg.createSVGPoint();
    pt.x = evt.clientX; pt.y = evt.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM().inverse());
    return [p.x, p.y];
  }, []);

  const nearest = (alt, az, kinds, maxDeg = 5) => {
    let best = null, bd = maxDeg;
    for (const o of objects) {
      if (kinds && !kinds.includes(o.kind)) continue;
      if (o.alt < -1) continue;
      const d = angDist(alt, az, o.alt, o.az);
      if (d < bd) { bd = d; best = o; }
    }
    return best;
  };
  const nearestStar = (alt, az) => {
    let best = null, bd = 8;
    for (const s of sky.stars) {
      const d = angDist(alt, az, s[0], s[1]);
      if (d < bd) { bd = d; best = s; }
    }
    return best;
  };

  const onMove = (e) => {
    if (!sky) return;
    const [x, y] = toSvg(e);
    const p = unproject(x, y);
    setMouse({ x, y, ...p, cx: e.clientX, cy: e.clientY });
    setHover(p.alt > -1 ? nearest(p.alt, p.az, null, 4 * (view.w / VB) + 1) : null);
  };
  const selectAt = (p) => {
    const o = nearest(p.alt, p.az, ["target", "planet", "moon"]);
    if (!o) return actions.toast("No listed object within 5° of the cursor");
    if (o.kind === "target") actions.select(o.id);
    else actions.addBody(o.name, true);
  };
  const onKey = async (e) => {
    if (!sky || e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key.toLowerCase();
    const p = mouse && mouse.alt > -1 ? mouse : null;
    const zoomAt = (f) => {
      const cx = p ? p.x : view.x + view.w / 2, cy = p ? p.y : view.y + view.w / 2;
      const w = Math.max(80, Math.min(VB, view.w * f));
      setView({ x: cx - w / 2, y: cy - w / 2, w });
    };
    const handled = {
      z: () => zoomAt(0.5), o: () => zoomAt(2), r: () => setView({ x: 0, y: 0, w: VB }),
      p: () => p && setView({ ...view, x: p.x - view.w / 2, y: p.y - view.w / 2 }),
      s: () => p && selectAt(p),
      c: () => p && actions.setCoordsAtAltAz(p.alt, p.az),
      h: () => { if (!p) return; const s = nearestStar(p.alt, p.az); if (s) actions.addStar(s); },
      w: () => { const t = state.targets.find((x) => x.id === state.selectedId); if (t?.url) window.open(t.url, "_blank", "noopener"); else actions.toast("No web address for this target"); },
      f: () => actions.stepBy(state.step, +1), b: () => actions.stepBy(state.step, -1), n: () => dispatch({ type: "live", live: true }),
    }[k];
    if (handled) { e.preventDefault(); e.stopPropagation(); handled(); }
  };

  if (!sky || !site) return html`<div class="placeholder">Loading sky…</div>`;
  const sun = sky.bodies.sun, moon = sky.bodies.moon;
  const bg = skyBackground(sun.alt, state.theme);
  const ink = red ? "var(--text-2)" : "rgba(200,215,255,0.55)";
  const arcInk = red ? "var(--muted)" : "rgba(229,103,103,0.45)";
  const selected = state.targets.find((t) => t.id === state.selectedId);
  const scale = view.w / VB;
  const amCircles = [[2, 30.0], [3, 19.29], [4, 14.39]];

  const arcPath = (pts) => {
    let d = "", pen = false;
    for (const p of pts) {
      if (!p) { pen = false; continue; }
      const [x, y] = project(p[0], p[1]);
      d += (pen ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
      pen = true;
    }
    return d;
  };

  return html`<div class="sky-wrap">
    <div class=${"card plot-card" + (loading ? " loading" : "")} style="padding:8px">
      <svg ref=${svgRef} class="sky-svg" viewBox=${`${view.x} ${view.y} ${view.w} ${view.w}`} tabindex="0"
        role="img" aria-label=${`All-sky chart for ${site.name}`}
        onPointerMove=${onMove} onPointerLeave=${() => { setHover(null); setMouse(null); }}
        onClick=${(e) => { const [x, y] = toSvg(e); const p = unproject(x, y); if (p.alt > -1) selectAt(p); }}
        onAuxClick=${(e) => { if (e.button === 1) { const [x, y] = toSvg(e); const p = unproject(x, y); actions.setCoordsAtAltAz(p.alt, p.az); } }}
        onKeyDown=${onKey}>
        <defs><clipPath id="horizon"><circle cx=${C} cy=${C} r=${R + 1}/></clipPath></defs>
        <rect x="-2000" y="-2000" width="5000" height="5000" fill="var(--surface)"/>
        <circle cx=${C} cy=${C} r=${R} fill=${bg}/>
        <g clip-path="url(#horizon)" fill="none" stroke-width=${1.2 * scale}>
          ${amCircles.map(([am, alt]) => html`<circle cx=${C} cy=${C} r=${(R * (90 - alt)) / 90} stroke=${ink} opacity="0.35"/>`)}
          ${Object.entries(sky.arcs).filter(([k]) => k !== "pole").map(([k, pts]) => html`<path d=${arcPath(pts)} stroke=${arcInk} stroke-width=${(k === "ha+0" || k === "equator" ? 1.6 : 1) * scale}/>`)}
        </g>
        ${amCircles.map(([am, alt]) => { const [x, y] = project(alt, 180); return html`<text x=${x + 4 * scale} y=${y - 4 * scale} font-size=${13 * scale} fill=${ink}>X=${am}</text>`; })}
        <circle cx=${C} cy=${C} r=${R} fill="none" stroke=${ink} stroke-width=${1.5 * scale}/>
        ${[["N", 0], ["E", 90], ["S", 180], ["W", 270]].map(([l, az]) => { const [x, y] = project(-4.5, az); return html`<text x=${x} y=${y + 6 * scale} text-anchor="middle" font-size=${17 * scale} font-weight="600" fill="var(--text-2)">${l}</text>`; })}

        <g>${sky.stars.map((s) => { if (s[0] < 0) return null; const [x, y] = project(s[0], s[1]); return html`<circle cx=${x} cy=${y} r=${starR(s[2]) * Math.sqrt(scale)} fill=${starColor(s[3], red)}/>`; })}</g>

        ${Object.entries(sky.bodies).filter(([k]) => k !== "sun" && k !== "moon" && sky.bodies[k].alt > -1).map(([k, b]) => {
          const [x, y] = project(b.alt, b.az);
          const r = Math.max(2.5, 6.5 - 0.7 * (b.mag ?? 3)) * Math.sqrt(scale);
          return html`<g><circle cx=${x} cy=${y} r=${r + 1.5 * scale} fill=${bg}/><circle cx=${x} cy=${y} r=${r} fill=${red ? "var(--text)" : "#f6e7b0"}/>
            <text x=${x + r + 4 * scale} y=${y + 4 * scale} font-size=${13 * scale} fill="var(--text-2)" paint-order="stroke" stroke=${bg} stroke-width=${3 * scale}>${k[0].toUpperCase() + k.slice(1)}</text></g>`;
        })}

        ${sun.alt > -1 && (() => { const [x, y] = project(sun.alt, sun.az); return html`<circle cx=${x} cy=${y} r=${13 * Math.sqrt(scale)} fill=${red ? "var(--text)" : "#ffd75e"}/>`; })()}
        ${moon.alt > -1 && html`<${MoonMark} moon=${moon} bg=${bg} scale=${scale} red=${red}/>`}

        ${sky.targets.map((t, i) => {
          if (t.alt < -1) return null;
          const id = sky.ids[i], tg = state.targets.find((x) => x.id === id);
          const [x, y] = project(t.alt, t.az);
          const sel = id === state.selectedId, hov = id === state.hoverId;
          const col = red ? "var(--text)" : (tg && tg.slot != null ? seriesColor(tg) : "var(--text-2)");
          return html`<g>
            <circle cx=${x} cy=${y} r=${(sel ? 5 : 4) * Math.sqrt(scale)} fill=${col} stroke=${bg} stroke-width=${2 * scale}/>
            ${sel && html`<rect x=${x - 11 * scale} y=${y - 11 * scale} width=${22 * scale} height=${22 * scale} fill="none" stroke="var(--accent)" stroke-width=${2 * scale}/>`}
            <text x=${x + 8 * scale} y=${y - 6 * scale} font-size=${(sel || hov ? 14 : 12) * scale} font-weight=${sel ? 650 : 450} fill=${sel ? "var(--text)" : "var(--text-2)"} paint-order="stroke" stroke=${bg} stroke-width=${3 * scale}>${t.name}</text>
          </g>`;
        })}

        <${ClockFace} x=${view.x + view.w - 70 * scale} y=${view.y + 70 * scale} r=${52 * scale} jd=${state.jd} tz=${site.tz} ink=${ink}/>
        <text x=${view.x + view.w - 14 * scale} y=${view.y + view.w - 34 * scale} text-anchor="end" font-size=${14 * scale} fill="var(--text-2)">${site.name}</text>
        <text x=${view.x + view.w - 14 * scale} y=${view.y + view.w - 14 * scale} text-anchor="end" font-size=${14 * scale} fill="var(--muted)" class="mono">UT ${utcTime(state.jd)} · LST ${hms(sky.last_h).slice(0, 5)}</text>
        <text x=${view.x + 14 * scale} y=${view.y + 26 * scale} font-size=${15 * scale} fill="var(--text-2)">${skyState(sun.alt).name}</text>
      </svg>
    </div>
    <div class="sky-legend">
      <div class="card">
        <h3>Under the cursor</h3>
        ${hover ? html`<dl class="kv">
            <dt>Object</dt><dd style="font-family:var(--font)">${hover.name}</dd>
            <dt>Alt, az</dt><dd>${fix(hover.alt, 1)}° ${fix(hover.az, 1)}°</dd>
            <dt>Hour angle</dt><dd>${hms(hover.ha, { signed: true }).slice(0, 6)}</dd>
            <dt>Airmass</dt><dd>${hover.alt > 0 ? fix(1 / Math.sin(hover.alt * D2R), 2) : "—"}</dd></dl>`
          : mouse && mouse.alt > -1 ? html`<dl class="kv"><dt>Alt, az</dt><dd>${fix(mouse.alt, 1)}° ${fix(mouse.az, 1)}°</dd></dl>`
          : html`<div class="muted">Point at the sky.</div>`}
      </div>
      <div class="card">
        <h3>Controls</h3>
        <div class="help-grid" style="font-size:.84rem">
          <kbd>click</kbd><span>select nearest target / planet</span>
          <kbd>z</kbd><span>zoom in at cursor</span><kbd>o</kbd><span>zoom out</span>
          <kbd>p</kbd><span>pan to cursor</span><kbd>r</kbd><span>restore view</span>
          <kbd>c</kbd><span>new target at cursor</span><kbd>h</kbd><span>nearest bright star</span>
          <kbd>f / b</kbd><span>step time forward / back</span>
          <kbd>n</kbd><span>now</span><kbd>w</kbd><span>open target's URL</span>
        </div>
        <div class="muted" style="margin-top:8px;font-size:.8rem">Click the chart first so it has keyboard focus. Circles: airmass 2, 3, 4. Red arcs: meridian, equator, HA ±2/4/6 h.</div>
      </div>
      <${TimeScrubber} site=${site}/>
    </div>
  </div>`;
}

function MoonMark({ moon, bg, scale, red }) {
  const [x, y] = project(moon.alt, moon.az);
  const r = 15 * Math.sqrt(scale);
  const k = Math.max(0, Math.min(1, moon.illum));
  // Bright-limb direction on the chart: the zenith direction (toward the centre) rotated by
  // (limb PA − parallactic angle), counter-clockwise as seen (we view the sky from inside).
  const zx = C - x, zy = -(C - y);                       // visual (y-up) vector to zenith
  const aZen = Math.atan2(zy, zx);
  const aLimb = aZen + moon.limb_vs_zenith_deg * D2R;     // CCW in visual coords
  const rot = -aLimb / D2R;                               // SVG rotate is clockwise in y-down
  const rx = Math.abs(1 - 2 * k) * r;
  const lit = `M0 ${-r} A${r} ${r} 0 0 1 0 ${r} A${rx} ${r} 0 0 ${k > 0.5 ? 1 : 0} 0 ${-r}Z`;
  const col = red ? "var(--text)" : "#efe9d2";
  return html`<g transform=${`translate(${x} ${y})`}>
    <circle r=${r + 2 * scale} fill=${bg}/>
    <circle r=${r} fill=${red ? "#1a0000" : "#2a2c33"}/>
    <path d=${lit} fill=${col} transform=${`rotate(${rot})`}/>
    <text x=${r + 5 * scale} y=${5 * scale} font-size=${13 * scale} fill="var(--text-2)" paint-order="stroke" stroke=${bg} stroke-width=${3 * scale}>Moon ${Math.round(k * 100)}%</text>
  </g>`;
}

function ClockFace({ x, y, r, jd, tz, ink }) {
  const [h, m] = localTime(jd, tz, false).split(":").map(Number);
  const ah = ((h % 12) + m / 60) * 30 * D2R, am = m * 6 * D2R;
  return html`<g transform=${`translate(${x} ${y})`} aria-hidden="true">
    <circle r=${r} fill="var(--surface-2)" stroke=${ink} stroke-width=${r / 40}/>
    ${[...Array(12)].map((_, i) => { const a = i * 30 * D2R; return html`<line x1=${Math.sin(a) * r * 0.82} y1=${-Math.cos(a) * r * 0.82} x2=${Math.sin(a) * r * 0.94} y2=${-Math.cos(a) * r * 0.94} stroke="var(--text-2)" stroke-width=${r / 30}/>`; })}
    <line x1="0" y1="0" x2=${Math.sin(ah) * r * 0.5} y2=${-Math.cos(ah) * r * 0.5} stroke="var(--text)" stroke-width=${r / 14} stroke-linecap="round"/>
    <line x1="0" y1="0" x2=${Math.sin(am) * r * 0.78} y2=${-Math.cos(am) * r * 0.78} stroke="var(--text)" stroke-width=${r / 22} stroke-linecap="round"/>
  </g>`;
}

/** Scrub through tonight in 10-minute steps. */
function TimeScrubber({ site }) {
  const { state, actions } = useContext(Store);
  const [base] = useState(() => Math.floor(state.jd - 0.5) + 0.5);
  return html`<div class="card">
    <h3>Scrub time</h3>
    <input type="range" min="-72" max="72" step="1" style="width:100%" value="0"
      onInput=${(e) => actions.setJd(actions.anchorJd() + (+e.target.value) / 144)}
      onPointerDown=${() => actions.setAnchor()}
      aria-label="Shift time by up to ±12 h"/>
    <div class="muted" style="font-size:.8rem;display:flex;justify-content:space-between"><span>−12 h</span><span>${localTime(state.jd, site.tz, false)} local</span><span>+12 h</span></div>
  </div>`;
}
