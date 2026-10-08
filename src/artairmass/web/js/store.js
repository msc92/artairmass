// App state: a single reducer + context. Targets carry a fixed colour slot (colour follows
// the entity, never its rank) and persist per-viewer in localStorage.
import { createContext } from "./lib.js";
import { SERIES, nowJd } from "./format.js";

export const Store = createContext(null);

const LS = "artairmass.v1.";
export function load(key, fallback) {
  try { const v = localStorage.getItem(LS + key); return v == null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
}
export function save(key, value) {
  try { localStorage.setItem(LS + key, JSON.stringify(value)); } catch (e) { /* private mode */ }
}

let nextId = 1;
export const newId = () => `t${Date.now().toString(36)}${(nextId++).toString(36)}`;

function freeSlot(targets) {
  const used = new Set(targets.map((t) => t.slot).filter((s) => s != null));
  for (let i = 0; i < SERIES; i++) if (!used.has(i)) return i;
  return null; // beyond 8 → grey context, highlighted on hover/selection
}

export const initialState = () => ({
  status: null,
  settings: null,
  sites: [],
  siteKey: null,
  jd: nowJd(),
  live: true,
  step: load("step", "1 h"),
  targets: load("targets", []),
  listName: load("listName", ""),
  selectedId: load("selectedId", null),
  view: load("view", "now"),
  theme: document.documentElement.dataset.theme || "dark",
  hoverId: null,
  toast: null,
  dialog: null,
});

export function reducer(state, action) {
  switch (action.type) {
    case "boot":
      return { ...state, ...action.payload };
    case "site":
      return { ...state, siteKey: action.key };
    case "time":
      return { ...state, jd: action.jd, live: action.live ?? false };
    case "tick":
      return state.live ? { ...state, jd: action.jd } : state;
    case "live":
      return { ...state, live: action.live, jd: action.live ? nowJd() : state.jd };
    case "step":
      return { ...state, step: action.step };
    case "view":
      return { ...state, view: action.view };
    case "theme":
      return { ...state, theme: action.theme };
    case "addTargets": {
      let targets = [...state.targets];
      const added = [];
      for (const t of action.targets) {
        const nt = { visible: true, ...t, id: newId() };
        nt.slot = freeSlot(targets);
        targets.push(nt);
        added.push(nt);
      }
      return { ...state, targets, selectedId: action.select === false ? state.selectedId : (added[0]?.id ?? state.selectedId) };
    }
    case "updateTarget":
      return { ...state, targets: state.targets.map((t) => (t.id === action.id ? { ...t, ...action.patch } : t)) };
    case "removeTarget": {
      const targets = state.targets.filter((t) => t.id !== action.id);
      return { ...state, targets, selectedId: state.selectedId === action.id ? (targets[0]?.id ?? null) : state.selectedId };
    }
    case "clearTargets":
      return { ...state, targets: [], selectedId: null };
    case "replaceTargets": {
      const targets = [];
      for (const t of action.targets) {
        const nt = { visible: true, ...t, id: t.id || newId() };
        nt.slot = t.slot != null && t.slot < SERIES && !targets.some((x) => x.slot === t.slot) ? t.slot : freeSlot(targets);
        targets.push(nt);
      }
      return { ...state, targets, selectedId: targets[0]?.id ?? null, listName: action.listName ?? state.listName };
    }
    case "listName":
      return { ...state, listName: action.name };
    case "sortTargets": {
      const key = action.by === "ra" ? (t) => (t.body ? 999 : t.ra) : (t) => t.name.toLowerCase();
      const targets = [...state.targets].sort((a, b) => (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0));
      return { ...state, targets };
    }
    case "select":
      return { ...state, selectedId: action.id };
    case "hover":
      return { ...state, hoverId: action.id };
    case "toast":
      return { ...state, toast: action.toast };
    case "dialog":
      return { ...state, dialog: action.dialog };
    default:
      throw new Error("unknown action " + action.type);
  }
}

export const targetPayload = (t) => ({
  name: t.name, ra: t.ra, dec: t.dec, pm_ra_cosdec: t.pm_ra_cosdec || 0, pm_dec: t.pm_dec || 0,
  epoch: t.epoch || 2000, body: t.body || null, url: t.url || "", notes: t.notes || "",
});
export const seriesColor = (t) => (t && t.slot != null ? `var(--s${t.slot + 1})` : "var(--context)");
// Red night-vision mode: identity by dash pattern, since hue is unavailable.
export const DASHES = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot", "5px,2px,1px,2px", "1px,3px"];
