import { html, useContext, useState, useRef, useEffect } from "../lib.js";
import { Store, seriesColor } from "../store.js";
import { Icon } from "./icons.js";
import { api } from "../api.js";
import { raStr, decStr, fix, airmassLevel } from "../format.js";

const PLANETS = ["Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"];

const PHONE = "(max-width: 760px)";
const isPhone = () => typeof matchMedia !== "undefined" && matchMedia(PHONE).matches;

export function Sidebar({ sky }) {
  const { state, dispatch, actions } = useContext(Store);
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState(() => !isPhone());
  // on phones the list is a drawer; it closes after picking a target
  const prevSel = useRef(state.selectedId);
  useEffect(() => {
    if (prevSel.current !== state.selectedId && isPhone()) setOpen(false);
    prevSel.current = state.selectedId;
  }, [state.selectedId]);
  const selected = state.targets.find((t) => t.id === state.selectedId);
  const needle = q.trim().toLowerCase();
  const shown = state.targets.filter((t) => !needle || t.name.toLowerCase().includes(needle));

  const selLive = selected ? liveFor(sky, state.targets, selected) : null;
  return html`<aside class=${"sidebar" + (open ? " open" : " closed")}>
    <button class="drawer-bar" onClick=${() => setOpen(!open)} aria-expanded=${open} aria-controls="target-drawer">
      <span class="chev">${open ? "▾" : "▸"}</span>
      <span>Targets <b>${state.targets.length}</b></span>
      ${selected && html`<span class="drawer-sel"><span class="swatch" style=${`background:${seriesColor(selected)}`}></span>${selected.name}
        <span class="muted">${selLive == null ? "" : selLive.alt > 0 ? `X ${fix(airmass(selLive.alt), 2)}` : "down"}</span></span>`}
    </button>
    <div class="drawer-body" id="target-drawer">
    <div class="side-head">
      <h2><span>Targets <span class="muted" style="text-transform:none;letter-spacing:0">${state.targets.length || ""}</span></span>
        <span class="group">
          <button class="btn ghost icon" title="Add one target" onClick=${() => setAdding(!adding)} aria-expanded=${adding}><${Icon.plus}/></button>
          <button class="btn ghost icon" title="Import / paste a list" onClick=${() => dispatch({ type: "dialog", dialog: { kind: "import" } })}><${Icon.upload}/></button>
        </span></h2>
      <div style="position:relative">
        <input id="target-search" class="inp" style="width:100%;padding-left:30px" placeholder="Filter targets  ( / )" value=${q} onInput=${(e) => setQ(e.target.value)}
          onKeyDown=${(e) => { if (e.key === "Enter" && shown[0]) actions.select(shown[0].id); if (e.key === "Escape") { setQ(""); e.target.blur(); } }}/>
        <span style="position:absolute;left:9px;top:8px;color:var(--muted);width:16px;height:16px;display:block"><${Icon.search}/></span>
      </div>
      <${ListBar}/>
      ${adding && html`<${AddTarget} onDone=${() => setAdding(false)}/>`}
    </div>
    <div class="tlist" role="listbox" aria-label="Targets">
      ${state.targets.length === 0 && html`<div class="empty">
        No targets yet. Add one with <b>+</b>, paste or drop a list with <span class="inline-icon"><${Icon.upload}/></span>, or pick a planet:
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px">${PLANETS.map((p) => html`<button class="btn" onClick=${() => actions.addBody(p)}>${p}</button>`)}</div>
      </div>`}
      ${shown.map((t) => html`<${TargetItem} t=${t} live=${liveFor(sky, state.targets, t)}/>`)}
    </div>
    </div>
  </aside>`;
}

function liveFor(sky, targets, t) {
  if (!sky || !sky.targets) return null;
  const idx = sky.ids ? sky.ids.indexOf(t.id) : -1;
  return idx >= 0 ? sky.targets[idx] : null;
}

function TargetItem({ t, live }) {
  const { state, dispatch, actions } = useContext(Store);
  const sel = state.selectedId === t.id;
  const alt = live?.alt;
  const am = alt > 0 ? airmass(alt) : null;
  const lvl = airmassLevel(am, alt);
  return html`<div class=${"titem" + (sel ? " sel" : "")} role="option" aria-selected=${sel} tabindex="-1"
      onClick=${() => actions.select(t.id)} onMouseEnter=${() => dispatch({ type: "hover", id: t.id })} onMouseLeave=${() => dispatch({ type: "hover", id: null })}>
    <input type="checkbox" class="vis" checked=${t.visible} style=${`color:${seriesColor(t)}`} title="Show on plots"
      onClick=${(e) => { e.stopPropagation(); dispatch({ type: "updateTarget", id: t.id, patch: { visible: !t.visible } }); }}/>
    <div style="min-width:0">
      <div class="nm">${t.name}</div>
      <div class="sub">${t.body ? "solar system" : `${raStr(t.ra, 1)}  ${decStr(t.dec, 0)}`}</div>
    </div>
    <div class="am" title=${live ? `alt ${fix(alt, 1)}°, az ${fix(live.az, 0)}° — ${lvl.label}` : ""}>
      ${live == null ? "" : alt > 0 ? html`<span class=${"status " + lvl.level} style="border:0;padding:0">${fix(am, 2)}</span>` : html`<span class="muted">down</span>`}
    </div>
    <button class="btn ghost icon rm" title="Remove target" aria-label=${`Remove ${t.name}`}
      onClick=${(e) => { e.stopPropagation(); dispatch({ type: "removeTarget", id: t.id }); }}><${Icon.x}/></button>
  </div>`;
}

// Hardie airmass (same as the server) for the sidebar's live readout.
function airmass(alt) {
  const secz = 1 / Math.sin((alt * Math.PI) / 180), x = secz - 1;
  if (secz > 12) return secz - 1.5;
  return secz - (((-4.716679e-5 * x + 0.001351167) * x + 0.003033104) * x + 0.002879465) * x;
}

function AddTarget({ onDone }) {
  const { actions } = useContext(Store);
  const [f, setF] = useState({ name: "", ra: "", dec: "", equinox: "2000" });
  const [err, setErr] = useState(null);
  const first = useRef();
  useEffect(() => first.current?.focus(), []);
  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    const body = PLANETS.find((p) => p.toLowerCase() === f.name.trim().toLowerCase());
    if (body && !f.ra && !f.dec) { actions.addBody(body); onDone(); return; }
    if (!f.ra || !f.dec) {
      if (f.name.trim()) {           // name only → resolve
        const ok = await actions.resolveAndAdd(f.name.trim());
        if (ok) onDone(); else setErr("Name not resolved — enter coordinates, or check the network.");
        return;
      }
      setErr("Enter RA and Dec, or a name to look up.");
      return;
    }
    try {
      const r = await api.post("/api/coords", { name: f.name.trim() || "target", ra: f.ra, dec: f.dec, equinox: f.equinox });
      actions.addTargets([{ name: r.name, ra: r.ra, dec: r.dec }]);
      if (r.ambiguous) actions.toast(`RA “${f.ra}” read as decimal HOURS (≤ 24). Append “d” for degrees.`);
      onDone();
    } catch (e2) { setErr(e2.message); }
  };
  const inp = (k, ph, w) => html`<input class="inp mono" style=${`width:${w}`} placeholder=${ph} value=${f[k]} onInput=${(e) => setF({ ...f, [k]: e.target.value })}/>`;
  return html`<form onSubmit=${submit} style="display:grid;gap:6px;padding:8px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--page)">
    <input ref=${first} class="inp" placeholder="Name (or a planet / a name to look up)" value=${f.name} onInput=${(e) => setF({ ...f, name: e.target.value })}/>
    <div style="display:grid;grid-template-columns:1fr 1fr 64px;gap:6px">${inp("ra", "RA 13:48:52.5", "100%")}${inp("dec", "Dec +26:35:34", "100%")}${inp("equinox", "2000", "100%")}</div>
    ${err && html`<div class="status critical" style="white-space:normal">${err}</div>`}
    <div style="display:flex;gap:6px;justify-content:flex-end"><button type="button" class="btn ghost" onClick=${onDone}>Cancel</button><button class="btn primary">Add</button></div>
  </form>`;
}

function ListBar() {
  const { state, actions, dispatch } = useContext(Store);
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState([]);
  const ref = useRef();
  useEffect(() => {
    if (!open) return;
    api.get("/api/lists").then(setSaved).catch(() => {});
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  const item = (label, fn, extra = "") => html`<div class="row" onClick=${() => { setOpen(false); fn(); }}><span class="check">${extra}</span><div>${label}</div></div>`;
  return html`<div class="picker" ref=${ref}>
    <button class="btn" style="width:100%;justify-content:space-between" onClick=${() => setOpen(!open)} aria-haspopup="menu" aria-expanded=${open}>
      <span style="overflow:hidden;text-overflow:ellipsis">${state.listName ? html`List: <b>${state.listName}</b>` : html`<span class="muted">Unsaved list</span>`}</span><span class="muted">▾</span></button>
    ${open && html`<div class="popover" role="menu" style="width:280px">
      ${saved.length > 0 && html`<div class="muted" style="font-size:.72rem;padding:4px 9px;text-transform:uppercase;letter-spacing:.06em">Saved lists</div>`}
      ${saved.map((l) => html`<div class=${"row" + (l.name === state.listName ? " active" : "")} onClick=${() => { setOpen(false); actions.loadList(l.name); }}>
        <span class="check">${l.name === state.listName ? "✓" : ""}</span><div style="flex:1">${l.name}</div><small>${l.count}</small></div>`)}
      ${saved.length > 0 && html`<hr/>`}
      ${item("Save as…", () => { const n = prompt("Save this list as:", state.listName || "my targets"); if (n) actions.saveListAs(n.trim()); })}
      ${item("New empty list", actions.newList)}
      ${item("Import / paste…", () => dispatch({ type: "dialog", dialog: { kind: "import" } }))}
      <hr/>
      ${item("Sort by RA", () => actions.sortTargets("ra"))}
      ${item("Sort alphabetically", () => actions.sortTargets("name"))}
      ${item("Export CSV", () => actions.exportList("csv"))}
      ${item("Export JSkyCalc list", () => actions.exportList("jskycalc"))}
      <hr/>
      ${item("Clear targets", () => { if (confirm("Remove all targets from this list?")) dispatch({ type: "clearTargets" }); })}
      ${state.listName && item(`Delete “${state.listName}”`, () => { if (confirm(`Delete the saved list “${state.listName}”?`)) actions.deleteList(state.listName); })}
    </div>`}
  </div>`;
}
