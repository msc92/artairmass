import { html, useContext, useState, useEffect, useRef, useMemo } from "../lib.js";
import { Store } from "../store.js";
import { Icon, Logo } from "./icons.js";
import { localTime, localDate, utcTime, zoneLabel, hms, wrap24, SIDEREAL_RATE, nightOf, skyState, fix } from "../format.js";
import { api } from "../api.js";

export function TopBar({ instant }) {
  const { state, dispatch, actions } = useContext(Store);
  const site = state.sites.find((s) => s.key === state.siteKey);
  if (!site) return null;
  return html`<header class="topbar">
    <div class="brand" title="artairmass — a modern JSkyCalc"><${Logo}/><div><b>artairmass</b></div></div>
    <${SitePicker} site=${site}/>
    <${NightNav} site=${site}/>
    <${TimeControls} site=${site}/>
    <div class="spacer"></div>
    <${Clocks} site=${site} instant=${instant}/>
    <${SkyChip} instant=${instant}/>
    <${ThemeSwitch}/>
    <button class="btn icon ghost" title="Settings" onClick=${() => dispatch({ type: "dialog", dialog: { kind: "settings" } })}><${Icon.gear}/></button>
    <button class="btn icon ghost" title="Keyboard shortcuts & help (?)" onClick=${() => dispatch({ type: "dialog", dialog: { kind: "help" } })}><${Icon.help}/></button>
  </header>`;
}

function SitePicker({ site }) {
  const { state, actions, dispatch } = useContext(Store);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef();
  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return state.sites.filter((s) => !needle || `${s.name} ${s.telescopes} ${s.key}`.toLowerCase().includes(needle));
  }, [q, state.sites]);
  const choose = (key) => { actions.setSite(key); setOpen(false); setQ(""); };
  return html`<div class="picker" ref=${ref}>
    <button class="btn" onClick=${() => setOpen(!open)} title="Observatory site" aria-haspopup="listbox" aria-expanded=${open}>
      <${Icon.pin}/> <span>${site.name}</span>
    </button>
    ${open && html`<div class="popover" role="listbox">
      <input class="inp" style="width:100%;margin-bottom:6px" placeholder="Search sites or telescopes…" value=${q}
        onInput=${(e) => setQ(e.target.value)} autofocus
        onKeyDown=${(e) => { if (e.key === "Enter" && list[0]) choose(list[0].key); if (e.key === "Escape") setOpen(false); }}/>
      ${list.map((s) => html`<div class=${"row" + (s.key === site.key ? " active" : "")} role="option" aria-selected=${s.key === site.key} onClick=${() => choose(s.key)}>
        <span class="check">${s.key === site.key ? "✓" : ""}</span>
        <div style="flex:1;min-width:0"><div>${s.name}${s.user ? html` <small>· yours</small>` : ""}</div>
          <small>${s.telescopes || ""}</small></div>
        <small class="mono">${fix(Math.abs(s.lat), 2)}°${s.lat < 0 ? "S" : "N"}</small>
      </div>`)}
      <hr/>
      <div class="row" onClick=${() => { setOpen(false); dispatch({ type: "dialog", dialog: { kind: "site" } }); }}>
        <span class="check">+</span><div>Add a custom site…</div></div>
      ${site.user && html`<div class="row" onClick=${() => { setOpen(false); dispatch({ type: "dialog", dialog: { kind: "site", edit: site } }); }}>
        <span class="check">✎</span><div>Edit “${site.name}”…</div></div>`}
    </div>`}
  </div>`;
}

function NightNav({ site }) {
  const { state, actions } = useContext(Store);
  const night = nightOf(state.jd, site.tz);
  return html`<div class="group" title="Night (local evening date). [ and ] step by one night">
    <button class="btn icon" onClick=${() => actions.stepBy("1 d", -1)} aria-label="Previous night"><${Icon.prev}/></button>
    <input type="date" class="inp mono" style="width:132px" value=${night} aria-label="Night of"
      onChange=${(e) => e.target.value && actions.setLocal(`${e.target.value} 22:00`)}/>
    <button class="btn icon" onClick=${() => actions.stepBy("1 d", +1)} aria-label="Next night"><${Icon.next}/></button>
  </div>`;
}

function TimeControls({ site }) {
  const { state, dispatch, actions } = useContext(Store);
  const [txt, setTxt] = useState("");
  const [editing, setEditing] = useState(false);
  const shown = editing ? txt : localTime(state.jd, site.tz);
  const commit = () => {
    setEditing(false);
    const v = txt.trim();
    if (!v) return;
    if (/^\d{7}(\.\d*)?$/.test(v)) return actions.setJd(parseFloat(v));            // a JD
    if (/^\d{5}(\.\d*)?$/.test(v)) return actions.setJd(parseFloat(v) + 2400000.5); // an MJD
    const d = localDate(state.jd, site.tz);
    const m = v.match(/^(\d{1,2})(?::?(\d{2}))?(?::?(\d{2}(?:\.\d+)?))?$/) || v.match(/^(\d{1,2}(?:\.\d+)?)$/);
    if (!m) return actions.toast("Time: use HH:MM[:SS], decimal hours, a JD or an MJD", true);
    let hh = +m[1], mm = +(m[2] || 0), ss = +(m[3] || 0);
    if (!m[2] && String(m[1]).includes(".")) { const h = parseFloat(m[1]); hh = Math.floor(h); mm = Math.floor((h - hh) * 60); ss = Math.round(((h - hh) * 60 - mm) * 60); }
    // same night: times before noon belong to the following calendar day
    const night = nightOf(state.jd, site.tz);
    const day = hh < 12 ? addDay(night) : night;
    actions.setLocal(`${day} ${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:${String(Math.floor(ss)).padStart(2, "0")}`);
  };
  return html`<div class="group">
    <button class="btn icon" title="Step back (b)" onClick=${() => actions.stepBy(state.step, -1)}><${Icon.stepBack}/></button>
    <input class="inp mono" style="width:92px;text-align:center" value=${shown} title="Local time — type HH:MM[:SS], decimal hours, a JD or an MJD; Enter to set"
      onFocus=${(e) => { setTxt(localTime(state.jd, site.tz)); setEditing(true); setTimeout(() => e.target.select(), 0); }}
      onInput=${(e) => setTxt(e.target.value)} onBlur=${commit} onKeyDown=${(e) => { if (e.key === "Enter") e.target.blur(); if (e.key === "Escape") { setEditing(false); e.target.blur(); } }}/>
    <button class="btn icon" title="Step forward (f)" onClick=${() => actions.stepBy(state.step, +1)}><${Icon.stepFwd}/></button>
    <input class="inp mono" style="width:62px" value=${state.step} title="Timestep: s, m, h, d, t (sidereal day), l (lunation)"
      onChange=${(e) => actions.setStep(e.target.value)}/>
    <button class=${"btn" + (state.live ? " on live" : "")} title="Follow the clock (n = now, l = toggle)" onClick=${() => dispatch({ type: "live", live: !state.live })}>
      <span class="live-dot"></span>${state.live ? "Live" : "Now"}
    </button>
  </div>`;
}
const addDay = (iso) => { const d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + 1); return d.toISOString().slice(0, 10); };

function Clocks({ site, instant }) {
  const { state } = useContext(Store);
  // LST: anchor on the server's apparent sidereal time, extrapolate at the sidereal rate.
  let lst = null;
  const ti = instant?.time_info;
  if (ti && ti.last_h != null && instant.siteKey === site.key) lst = wrap24(ti.last_h + (state.jd - ti.jd) * 24 * SIDEREAL_RATE);
  return html`<div class="clocks">
    <div class="clock" title=${`Local civil time at ${site.name} (${site.tz})`}><span>Local · ${zoneLabel(state.jd, site.tz)}</span><b>${localTime(state.jd, site.tz)}</b></div>
    <div class="clock" title="Coordinated Universal Time"><span>UT · ${state.jd ? new Date((state.jd - 2440587.5) * 864e5).toISOString().slice(5, 10) : ""}</span><b>${utcTime(state.jd)}</b></div>
    <div class="clock" title="Local apparent sidereal time"><span>LST</span><b>${lst == null ? "—" : hms(lst)}</b></div>
  </div>`;
}

function SkyChip({ instant }) {
  if (!instant) return null;
  const st = skyState(instant.sun.alt_deg);
  const ill = Math.round(instant.moon.illum * 100);
  return html`<span class="chip" title=${`Sun altitude ${fix(instant.sun.alt_deg, 1)}°. Moon ${ill}% illuminated, ${instant.moon.alt_deg > 0 ? "up" : "down"}.`}>
    ${st.short === "day" ? html`<${Icon.sun}/>` : html`<${MoonGlyph} illum=${instant.moon.illum} waxing=${instant.moon.phase.includes("1st") || instant.moon.phase.includes("since new") || instant.moon.phase.includes("before full")} size=${14}/>`}
    ${st.short === "night" ? "Dark" : st.name.replace(" twilight", " tw.")} · ${ill}% ${instant.moon.alt_deg > 0 ? "↑" : "↓"}
  </span>`;
}

/** Small moon-phase glyph (northern-hemisphere orientation: waxing lit on the right). */
export function MoonGlyph({ illum, waxing = true, size = 16 }) {
  const r = 7, k = Math.max(0, Math.min(1, illum));
  const rx = Math.abs(1 - 2 * k) * r;
  const sweepTerm = k > 0.5 ? 1 : 0;
  const lit = `M8 1 A7 7 0 0 1 8 15 A${rx} 7 0 0 ${sweepTerm} 8 1Z`;
  return html`<svg width=${size} height=${size} viewBox="0 0 16 16" aria-hidden="true" style=${waxing ? "" : "transform:scaleX(-1)"}>
    <circle cx="8" cy="8" r=${r} fill="var(--surface-3)" stroke="var(--border-strong)" stroke-width="0.6"/>
    <path d=${lit} fill="var(--moon)"/>
  </svg>`;
}

function ThemeSwitch() {
  const { state, actions } = useContext(Store);
  const opts = [["dark", "Dark"], ["light", "Light"], ["red", "Night-vision red (r)"]];
  return html`<div class="seg" role="group" aria-label="Theme">
    ${opts.map(([k, label]) => html`<button aria-pressed=${state.theme === k} title=${label} onClick=${() => actions.setTheme(k)}>
      ${k === "dark" ? html`<${Icon.moonIcon}/>` : k === "light" ? html`<${Icon.sun}/>` : html`<${Icon.eye}/>`}
    </button>`)}
  </div>`;
}
