import { html, render, useReducer, useEffect, useMemo, useRef, useState, useCallback } from "./lib.js";
import { Store, reducer, initialState, save, load, targetPayload } from "./store.js";
import { api, ApiError } from "./api.js";
import { nowJd, fix } from "./format.js";
import { TopBar } from "./components/topbar.js";
import { Sidebar } from "./components/sidebar.js";
import { NowView } from "./components/now.js";
import { SkyView } from "./components/sky.js";
import { PlanetsView } from "./components/planets.js";
import { NightView } from "./components/night.js";
import { SeasonView } from "./components/season.js";
import { Dialogs } from "./components/dialogs.js";

const VIEWS = [
  ["now", "Now"], ["night", "Night"], ["season", "Season"], ["sky", "Sky"], ["planets", "Planets"], ["tools", "Tools"],
];
const THEMES = ["dark", "light", "red"];

function useDebounced(fn, deps, ms) {
  useEffect(() => {
    const t = setTimeout(fn, ms);
    return () => clearTimeout(t);
  }, deps);
}

function App() {
  const [state, dispatch] = useReducer(reducer, null, initialState);
  const [instant, setInstant] = useState(null);
  const [sky, setSky] = useState(null);
  const [busy, setBusy] = useState({});
  const [lost, setLost] = useState(false);
  const stateRef = useRef(state);
  stateRef.current = state;
  const anchor = useRef(state.jd);

  // ---------------------------------------------------------------- actions
  const actions = useMemo(() => {
    const S = () => stateRef.current;
    const toast = (msg, error = false) => {
      dispatch({ type: "toast", toast: { msg, error, at: Date.now() } });
      setTimeout(() => { if (S().toast && Date.now() - S().toast.at >= 3900) dispatch({ type: "toast", toast: null }); }, 4000);
    };
    const guard = (p) => p.catch((e) => { if (!(e instanceof ApiError && e.message === "__stale__")) toast(e.message, true); return null; });
    return {
      toast,
      setSite: (key) => { dispatch({ type: "site", key }); save("site", key); },
      setJd: (jd) => dispatch({ type: "time", jd, live: false }),
      setLocal: async (local) => {
        const r = await guard(api.post("/api/time", { site: S().siteKey, local }));
        if (r) dispatch({ type: "time", jd: r.jd, live: false });
      },
      stepBy: async (step, sign) => {
        const r = await guard(api.post("/api/time", { site: S().siteKey, jd: S().jd, step, steps: sign }));
        if (r) dispatch({ type: "time", jd: r.jd, live: false });
      },
      setStep: async (step) => {
        const r = await guard(api.post("/api/time", { site: S().siteKey, jd: S().jd, step, steps: 0 }));
        if (r) { dispatch({ type: "step", step }); save("step", step); }
      },
      select: (id) => dispatch({ type: "select", id }),
      addTargets: (targets, select = true) => dispatch({ type: "addTargets", targets, select }),
      updateTarget: (id, patch) => dispatch({ type: "updateTarget", id, patch }),
      addBody: (name, select = true) => {
        const ex = S().targets.find((t) => t.body === name.toLowerCase());
        if (ex) return dispatch({ type: "select", id: ex.id });
        dispatch({ type: "addTargets", targets: [{ name, body: name.toLowerCase(), ra: 0, dec: 0 }], select });
      },
      addStar: (s) => {  // [alt, az, V, B-V, HR, designation, proper, ra, dec]
        const name = s[6] || s[5] || `HR ${s[4]}`;
        dispatch({ type: "addTargets", targets: [{ name: `${name} (HR ${s[4]}, V=${s[2]})`, ra: s[7], dec: s[8], notes: "bright star" }] });
      },
      setCoordsAtAltAz: async (alt, az) => {
        const site = S().sites.find((x) => x.key === S().siteKey);
        if (!site || !sky) return;
        const d2r = Math.PI / 180, lat = site.lat * d2r, a = alt * d2r, z = az * d2r;
        const dec = Math.asin(Math.sin(lat) * Math.sin(a) + Math.cos(lat) * Math.cos(a) * Math.cos(z));
        const ha = Math.atan2(-Math.sin(z) * Math.cos(a), Math.cos(lat) * Math.sin(a) - Math.sin(lat) * Math.cos(a) * Math.cos(z));
        const raH = (((skyRef.current.last_h - ha / d2r / 15) % 24) + 24) % 24;
        const r = await guard(api.post("/api/coords", { name: "cursor", ra: `${raH}h`, dec: String(dec / d2r), equinox: "date", time: S().jd }));
        if (r) dispatch({ type: "addTargets", targets: [{ name: `cursor ${fix(alt, 0)}°/${fix(az, 0)}°`, ra: r.ra, dec: r.dec }] });
      },
      resolveAndAdd: async (name) => {
        try {
          const r = await api.post("/api/resolve", { names: [name] });
          const hit = r.results?.[0];
          if (!hit || hit.error) return false;
          dispatch({ type: "addTargets", targets: [{ name: hit.name, ra: hit.ra, dec: hit.dec, pm_ra_cosdec: hit.pm_ra_cosdec || 0, pm_dec: hit.pm_dec || 0, epoch: hit.epoch || 2000 }] });
          return true;
        } catch (e) { return false; }
      },
      setTheme: (theme) => {
        document.documentElement.dataset.theme = theme;
        try { localStorage.setItem("artairmass.theme", theme); } catch (e) { /* ignore */ }
        dispatch({ type: "theme", theme });
      },
      saveSettings: async (s) => {
        const r = await guard(api.put("/api/settings", s));
        if (r) { dispatch({ type: "boot", payload: { settings: r } }); applySettings(r); }
      },
      reloadSites: async (selectKey) => {
        const sites = await guard(api.get("/api/sites"));
        if (!sites) return;
        dispatch({ type: "boot", payload: { sites } });
        if (selectKey) { dispatch({ type: "site", key: selectKey }); save("site", selectKey); }
        else if (!sites.find((s) => s.key === S().siteKey)) dispatch({ type: "site", key: sites[0].key });
      },
      importTargets: (targets, mode, listName) => {
        if (mode === "replace") dispatch({ type: "replaceTargets", targets, listName: listName || S().listName });
        else {
          dispatch({ type: "addTargets", targets });
          if (listName && listName !== S().listName) dispatch({ type: "listName", name: listName });
        }
        toast(`${mode === "replace" ? "Loaded" : "Added"} ${targets.length} target${targets.length === 1 ? "" : "s"}${listName ? ` · list “${listName}”` : ""}`);
      },
      loadList: async (name) => {
        const r = await guard(api.get(`/api/lists/${encodeURIComponent(name)}`));
        if (r) { dispatch({ type: "replaceTargets", targets: r.targets, listName: r.name }); toast(`Loaded “${r.name}” (${r.targets.length})`); }
      },
      saveListAs: async (name) => {
        if (!name) return;
        dispatch({ type: "listName", name });
        const r = await guard(api.put(`/api/lists/${encodeURIComponent(name)}`, { targets: S().targets.map(stripTarget) }));
        if (r) toast(`Saved “${name}”`);
      },
      deleteList: async (name) => {
        await guard(api.del(`/api/lists/${encodeURIComponent(name)}`));
        if (S().listName === name) dispatch({ type: "listName", name: "" });
        toast(`Deleted list “${name}”`);
      },
      newList: () => { dispatch({ type: "replaceTargets", targets: [], listName: "" }); },
      exportList: async (format) => {
        const r = await guard(api.post("/api/export", { targets: S().targets.map(targetPayload), format }));
        if (!r) return;
        const blob = new Blob([r.text], { type: "text/plain" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = (S().listName || "targets").replace(/[^\w.-]+/g, "_") + (format === "jskycalc" ? ".txt" : ".csv");
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      },
      sortTargets: (by) => dispatch({ type: "sortTargets", by }),
      anchorJd: () => anchor.current,
      setAnchor: () => { anchor.current = S().jd; },
    };
  }, []);
  const skyRef = useRef(null);
  skyRef.current = sky;

  // ---------------------------------------------------------------- boot
  useEffect(() => {
    (async () => {
      try {
        const [status, sites] = await Promise.all([api.get("/api/status"), api.get("/api/sites")]);
        const settings = status.settings;
        const remembered = load("site", null);
        const siteKey = sites.find((s) => s.key === remembered) ? remembered : (sites.find((s) => s.key === settings.site) ? settings.site : sites[0].key);
        dispatch({ type: "boot", payload: { status, settings, sites, siteKey } });
        applySettings(settings);
      } catch (e) {
        setLost(true);
      }
    })();
  }, []);

  // persist targets & view per viewer
  useEffect(() => save("targets", state.targets), [state.targets]);
  useEffect(() => save("selectedId", state.selectedId), [state.selectedId]);
  useEffect(() => save("view", state.view), [state.view]);
  useEffect(() => save("listName", state.listName), [state.listName]);
  // named lists autosave to the server (debounced)
  useDebounced(() => {
    if (!state.listName || !state.siteKey) return;
    api.put(`/api/lists/${encodeURIComponent(state.listName)}`, { targets: state.targets.map(stripTarget) }).catch(() => {});
  }, [state.listName, JSON.stringify(state.targets.map(stripTarget))], 800);

  // drop a file anywhere → import dialog
  useEffect(() => {
    const over = (e) => { if (e.dataTransfer?.types?.includes("Files")) e.preventDefault(); };
    const drop = (e) => {
      const f = e.dataTransfer?.files?.[0];
      if (!f || stateRef.current.dialog) return;
      e.preventDefault();
      const fr = new FileReader();
      fr.onload = () => dispatch({ type: "dialog", dialog: { kind: "import", initialText: String(fr.result), fileName: f.name } });
      fr.readAsText(f);
    };
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => { window.removeEventListener("dragover", over); window.removeEventListener("drop", drop); };
  }, []);

  // live clock
  useEffect(() => {
    const id = setInterval(() => dispatch({ type: "tick", jd: nowJd() }), 1000);
    return () => clearInterval(id);
  }, []);

  // ---------------------------------------------------------------- data
  const selected = state.targets.find((t) => t.id === state.selectedId) || null;
  const sleep = Math.max(1, state.settings?.sleep_s || 5);
  // In live mode refresh every `sleep` seconds; otherwise on every change.
  const tKey = state.live ? Math.floor(state.jd * 86400 / sleep) : state.jd;
  const selKey = selected ? JSON.stringify(targetPayload(selected)) : "";
  useDebounced(() => {
    if (!state.siteKey) return;
    setBusy((b) => ({ ...b, instant: true }));
    api.post("/api/instant", { site: state.siteKey, time: stateRef.current.jd, target: selected ? targetPayload(selected) : null, airmass_model: state.settings?.airmass_model || "hardie" })
      .then((r) => { setInstant({ ...r, siteKey: state.siteKey }); setLost(false); })
      .catch((e) => { if (e.message.startsWith("Lost contact")) setLost(true); else actions.toast(e.message, true); })
      .finally(() => setBusy((b) => ({ ...b, instant: false })));
  }, [state.siteKey, tKey, selKey, state.settings?.airmass_model], 120);

  const skyKey = state.live ? Math.floor(state.jd * 86400 / Math.max(sleep, 10)) : state.jd;
  const listKey = JSON.stringify(state.targets.map((t) => [t.id, t.ra, t.dec, t.body]));
  useDebounced(() => {
    if (!state.siteKey) return;
    setBusy((b) => ({ ...b, sky: true }));
    const ids = state.targets.map((t) => t.id);
    api.post("/api/sky", { site: state.siteKey, time: stateRef.current.jd, targets: state.targets.map(targetPayload) })
      .then((r) => setSky({ ...r, ids }))
      .catch(() => {})
      .finally(() => setBusy((b) => ({ ...b, sky: false })));
  }, [state.siteKey, skyKey, listKey], 150);

  // ---------------------------------------------------------------- keyboard
  useEffect(() => {
    const onKey = (e) => {
      const el = e.target;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const S = stateRef.current;
      const k = e.key;
      const idx = S.targets.findIndex((t) => t.id === S.selectedId);
      const map = {
        n: () => dispatch({ type: "live", live: true }),
        l: () => dispatch({ type: "live", live: !S.live }),
        f: () => actions.stepBy(S.step, +1),
        b: () => actions.stepBy(S.step, -1),
        "[": () => actions.stepBy("1 d", -1),
        "]": () => actions.stepBy("1 d", +1),
        j: () => S.targets.length && actions.select(S.targets[(idx + 1) % S.targets.length].id),
        k: () => S.targets.length && actions.select(S.targets[(idx - 1 + S.targets.length) % S.targets.length].id),
        "/": () => document.getElementById("target-search")?.focus(),
        t: () => actions.setTheme(THEMES[(THEMES.indexOf(S.theme) + 1) % THEMES.length]),
        r: () => actions.setTheme(S.theme === "red" ? "dark" : "red"),
        "?": () => dispatch({ type: "dialog", dialog: { kind: "help" } }),
      };
      if (/^[1-6]$/.test(k)) map[k] = () => dispatch({ type: "view", view: VIEWS[+k - 1][0] });
      if (map[k]) { e.preventDefault(); map[k](); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (lost && !state.siteKey) return html`<div class="boot" style="letter-spacing:0">Can't reach the artairmass server. Start it with <code style="margin-left:6px">artairmass</code>.</div>`;
  if (!state.siteKey) return html`<div class="boot">artairmass</div>`;

  const ctx = { state, dispatch, actions };
  const stale = state.status?.iers?.stale;
  return html`<${Store.Provider} value=${ctx}>
    <div class="app">
      <div>
        <${TopBar} instant=${instant}/>
        ${lost && html`<div class="banner warn">Lost contact with the artairmass server — results may be out of date.</div>`}
        ${stale && html`<div class="banner warn">Earth-orientation (IERS) data are ${fix(state.status.iers.age_days, 0)} days old — sidereal time may be off by up to ~1 s. Run <code>artairmass update-data</code> when online.</div>`}
      </div>
      <div class="body">
        <${Sidebar} sky=${sky}/>
        <main class="content">
          <nav class="tabs" role="tablist">
            ${VIEWS.map(([k, label], i) => html`<button class="tab" role="tab" aria-selected=${state.view === k} onClick=${() => dispatch({ type: "view", view: k })}>${label}<kbd>${i + 1}</kbd></button>`)}
          </nav>
          <div class="view">
            ${state.view === "now" && html`<${NowView} instant=${instant} loading=${busy.instant}/>`}
            ${state.view === "sky" && html`<${SkyView} sky=${sky} loading=${busy.sky}/>`}
            ${state.view === "planets" && html`<${PlanetsView}/>`}
            ${state.view === "night" && html`<${NightView}/>`}
            ${state.view === "season" && html`<${SeasonView}/>`}
            ${["tools"].includes(state.view) && html`<div class="placeholder">${VIEWS.find((v) => v[0] === state.view)[1]} view — coming in a later stage.</div>`}
          </div>
        </main>
      </div>
    </div>
    <${Dialogs}/>
    ${state.toast && html`<div class=${"toast" + (state.toast.error ? " error" : "")} role="status">${state.toast.msg}</div>`}
  </${Store.Provider}>`;
}

const stripTarget = (t) => ({ name: t.name, ra: t.ra, dec: t.dec, pm_ra_cosdec: t.pm_ra_cosdec || 0, pm_dec: t.pm_dec || 0,
  epoch: t.epoch || 2000, body: t.body || null, url: t.url || "", notes: t.notes || "", visible: t.visible !== false, slot: t.slot });

function applySettings(s) {
  if (s && s.ui_scale) document.documentElement.style.setProperty("--scale", s.ui_scale);
}

render(html`<${App}/>`, document.getElementById("app"));
