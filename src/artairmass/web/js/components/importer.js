// Import / paste a target list: live parse preview with per-row status, inline fixes,
// name resolution, and add/replace into the current list.
import { html, useContext, useState, useEffect, useRef, useMemo } from "../lib.js";
import { Store } from "../store.js";
import { api } from "../api.js";
import { raStr, decStr } from "../format.js";

const EXAMPLE = `# Paste anything: CSV, TSV, JSkyCalc lists, SIMBAD/NED exports, ds9 regions…
name, ra, dec
Abell 1795, 13:48:52.5, +26:35:34
Perseus    03 19 48.16  +41 30 42.1
Phoenix cluster  356.1829d  -42.72
NGC 1275          (name only → looked up)`;

const STATUS = {
  ok: ["good", "OK"], warning: ["warning", "Check"], error: ["critical", "Error"], resolve: ["info", "Look up"],
};

export function ImportDialog({ close, initialText = "", fileName = "" }) {
  const { state, actions } = useContext(Store);
  const [text, setText] = useState(initialText);
  const [opts, setOpts] = useState({ ra_unit: "auto", equinox: "2000", header: "auto", delimiter: "auto", coord_system: "auto" });
  const [res, setRes] = useState(null);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [mode, setMode] = useState(state.targets.length ? "append" : "replace");
  const [listName, setListName] = useState(fileName ? fileName.replace(/\.[^.]+$/, "") : (state.listName || ""));
  const [drag, setDrag] = useState(false);
  const fileRef = useRef();

  // parse (debounced) whenever text or options change
  useEffect(() => {
    if (!text.trim()) { setRes(null); setRows([]); return; }
    setBusy(true);
    const t = setTimeout(() => {
      api.post("/api/parse", { text, ...opts, time: state.jd })
        .then((r) => { setRes(r); setRows(r.rows.map((x, i) => ({ ...x, key: i }))); })
        .catch((e) => actions.toast(e.message, true))
        .finally(() => setBusy(false));
    }, 300);
    return () => clearTimeout(t);
  }, [text, opts]);

  const readFile = (file) => {
    if (!file) return;
    if (file.size > 5e6) return actions.toast("File too large (5 MB max)", true);
    const fr = new FileReader();
    fr.onload = () => { setText(String(fr.result)); if (!listName) setListName(file.name.replace(/\.[^.]+$/, "")); };
    fr.onerror = () => actions.toast("Couldn't read that file", true);
    fr.readAsText(file);
  };

  const counts = useMemo(() => rows.reduce((c, r) => ({ ...c, [r.status]: (c[r.status] || 0) + 1 }), {}), [rows]);
  const usable = rows.filter((r) => (r.status === "ok" || r.status === "warning") && r.ra != null);
  const toResolve = rows.filter((r) => r.status === "resolve");

  const updateRow = (key, patch) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const revalidate = async (row, field, value) => {
    const next = { ...row, [field]: value };
    if (field === "name") return updateRow(row.key, { name: value });
    try {
      const r = await api.post("/api/coords", { name: next.name, ra: next.ra_text, dec: next.dec_text, equinox: next.equinox || opts.equinox, ra_unit: opts.ra_unit, time: state.jd });
      updateRow(row.key, { [field]: value, ra: r.ra, dec: r.dec, status: r.ambiguous ? "warning" : "ok",
        how: [`RA: ${r.ra_how}`, `Dec: ${r.dec_how}`, "edited"], messages: r.ambiguous ? ["decimal RA ≤ 24 read as hours"] : [] });
    } catch (e) {
      updateRow(row.key, { [field]: value, status: "error", messages: [e.message] });
    }
  };

  const lookUp = async () => {
    setResolving(true);
    try {
      const names = toResolve.map((r) => r.name);
      const out = await api.post("/api/resolve", { names });
      const byName = new Map(out.results.map((r) => [r.name, r]));
      setRows((rs) => rs.map((r) => {
        if (r.status !== "resolve") return r;
        const hit = byName.get(r.name);
        if (!hit || hit.error) return { ...r, status: "error", messages: [hit ? hit.error : "no answer"] };
        return { ...r, status: "ok", ra: hit.ra, dec: hit.dec, ra_text: raStr(hit.ra, 2), dec_text: decStr(hit.dec, 1),
          pm_ra_cosdec: hit.pm_ra_cosdec || 0, pm_dec: hit.pm_dec || 0,
          how: [`${hit.resolver || "Sesame"}${hit.cached ? " (cached)" : ""}: ${hit.oname || r.name}${hit.otype ? " · " + hit.otype : ""}`], messages: [] };
      }));
    } catch (e) { actions.toast(e.message, true); }
    setResolving(false);
  };

  const commit = () => {
    const targets = usable.map((r) => ({ name: r.name, ra: r.ra, dec: r.dec, pm_ra_cosdec: r.pm_ra_cosdec || 0, pm_dec: r.pm_dec || 0,
      epoch: r.pm_ra_cosdec || r.pm_dec ? 2000 : 2000, url: r.url || "", notes: r.notes || "" }));
    actions.importTargets(targets, mode, listName.trim());
    close();
  };

  const optSeg = (k, choices, label, title) => html`<div class="field" title=${title || ""}><span>${label}</span><div class="seg">
    ${choices.map(([v, l]) => html`<button type="button" aria-pressed=${opts[k] === v} onClick=${() => setOpts({ ...opts, [k]: v })}>${l}</button>`)}</div></div>`;

  return html`<div style="width:min(1100px, 92vw)" onDragOver=${(e) => { e.preventDefault(); setDrag(true); }} onDragLeave=${() => setDrag(false)}
      onDrop=${(e) => { e.preventDefault(); setDrag(false); readFile(e.dataTransfer.files?.[0]); }}>
    <h2 style="display:flex;justify-content:space-between;align-items:center">Add targets
      <span class="group"><button class="btn" onClick=${() => fileRef.current.click()}>Choose file…</button>
      <input ref=${fileRef} type="file" accept=".txt,.csv,.tsv,.dat,.cat,.list,.lst,.reg,.tbl,.ipac,text/*" style="display:none" onChange=${(e) => readFile(e.target.files[0])}/></span></h2>
    <textarea class="inp mono" rows="8" style=${`width:100%;font-size:.85rem;${drag ? "outline:2px dashed var(--accent)" : ""}`} placeholder=${EXAMPLE}
      value=${text} onInput=${(e) => setText(e.target.value)} spellcheck="false" aria-label="Target list text"></textarea>
    <div class="muted" style="font-size:.8rem;margin:4px 0 10px">Drop a file here, paste, or type. Lines starting with # are ignored; extra columns are kept as notes.</div>

    <div class="toolbar">
      ${optSeg("ra_unit", [["auto", "Auto"], ["hours", "Hours"], ["deg", "Degrees"]], "Decimal RA", "How to read RA values written as a bare decimal number")}
      <label class="field"><span>Default equinox</span><input class="inp mono" style="width:76px" value=${opts.equinox} onChange=${(e) => setOpts({ ...opts, equinox: e.target.value })} title="2000, J2000, B1950, ICRS, or -1 for equinox of date"/></label>
      <label class="field"><span>Header</span><select class="inp" value=${opts.header} onChange=${(e) => setOpts({ ...opts, header: e.target.value })}><option value="auto">auto</option><option value="yes">first line</option><option value="no">none</option></select></label>
      <label class="field"><span>Delimiter</span><select class="inp" value=${opts.delimiter} onChange=${(e) => setOpts({ ...opts, delimiter: e.target.value })}>
        <option value="auto">auto</option><option value=",">comma</option><option value="\t">tab</option><option value=";">semicolon</option><option value="|">pipe</option><option value="whitespace">spaces</option></select></label>
      <label class="field"><span>Coordinates</span><select class="inp" value=${opts.coord_system} onChange=${(e) => setOpts({ ...opts, coord_system: e.target.value })}><option value="auto">auto</option><option value="equatorial">RA/Dec</option><option value="galactic">galactic l, b</option></select></label>
    </div>

    ${res && html`<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:6px 0 8px;font-size:.88rem">
      <span class="dim">Read as <b>${res.format}</b>${res.columns && Object.keys(res.columns).length ? html` · columns ${Object.entries(res.columns).map(([k, v]) => `${k}=${v}`).join(", ")}` : ""}</span>
      ${["ok", "warning", "resolve", "error"].filter((s) => counts[s]).map((s) => html`<span class=${"status " + STATUS[s][0]}>${counts[s]} ${STATUS[s][1].toLowerCase()}</span>`)}
    </div>
    ${res.ra_unit_reason.startsWith("AMBIGUOUS") && opts.ra_unit === "auto" && html`<div class="banner warn" style="border-radius:var(--radius-sm);margin-bottom:8px">
      <span>Every decimal RA is ≤ 24, so it could be hours or degrees. Currently read as <b>hours</b> (JSkyCalc's convention).</span>
      <span class="spacer"></span>
      <button class="btn" onClick=${() => setOpts({ ...opts, ra_unit: "hours" })}>They are hours</button>
      <button class="btn" onClick=${() => setOpts({ ...opts, ra_unit: "deg" })}>They are degrees</button></div>`}`}

    ${rows.length > 0 && html`<div class=${busy ? "loading" : ""} style="max-height:42vh;overflow:auto;border:1px solid var(--border);border-radius:var(--radius-sm)">
      <table class="tbl"><thead><tr><th style="text-align:left">Status</th><th>Line</th><th style="text-align:left">Name</th><th>RA</th><th>Dec</th><th style="text-align:left">How it was read</th></tr></thead>
      <tbody>${rows.map((r) => html`<tr>
        <td style="font-family:var(--font)"><span class=${"status " + STATUS[r.status][0]}>${STATUS[r.status][1]}</span></td>
        <td class="muted">${r.line}</td>
        <td style="text-align:left"><input class="inp" style="height:26px;width:170px" value=${r.name} onChange=${(e) => revalidate(r, "name", e.target.value)}/></td>
        <td><input class=${"inp mono" + (r.status === "error" ? " err" : "")} style="height:26px;width:125px" value=${r.ra_text || (r.ra != null ? raStr(r.ra, 2) : "")} placeholder="RA" onChange=${(e) => revalidate(r, "ra_text", e.target.value)}/></td>
        <td><input class=${"inp mono" + (r.status === "error" ? " err" : "")} style="height:26px;width:125px" value=${r.dec_text || (r.dec != null ? decStr(r.dec, 1) : "")} placeholder="Dec" onChange=${(e) => revalidate(r, "dec_text", e.target.value)}/></td>
        <td style="text-align:left;white-space:normal;font-family:var(--font);font-size:.8rem;min-width:220px">
          ${r.messages?.length ? html`<div style=${r.status === "error" ? "color:var(--critical)" : r.status === "warning" ? "color:var(--warning)" : ""}>${r.messages.join("; ")}</div>` : ""}
          <div class="muted">${(r.how || []).join(" · ")}</div></td>
      </tr>`)}</tbody></table></div>`}

    <div class="actions" style="align-items:center;flex-wrap:wrap">
      ${toResolve.length > 0 && html`<button class="btn" disabled=${resolving} onClick=${lookUp} title="Query SIMBAD/NED/VizieR via CDS Sesame (needs network; results are cached)">${resolving ? "Looking up…" : `Look up ${toResolve.length} name${toResolve.length > 1 ? "s" : ""}`}</button>`}
      <span class="spacer"></span>
      <label class="field"><span>List name</span><input class="inp" style="width:170px" value=${listName} placeholder="(unsaved)" onInput=${(e) => setListName(e.target.value)}/></label>
      <div class="seg"><button aria-pressed=${mode === "append"} onClick=${() => setMode("append")}>Add to list</button><button aria-pressed=${mode === "replace"} onClick=${() => setMode("replace")}>Replace list</button></div>
      <button class="btn ghost" onClick=${close}>Cancel</button>
      <button class="btn primary" disabled=${!usable.length} onClick=${commit}>Add ${usable.length} target${usable.length === 1 ? "" : "s"}</button>
    </div>
    ${counts.error > 0 && html`<div class="muted" style="font-size:.8rem;text-align:right;margin-top:6px">${counts.error} row${counts.error > 1 ? "s" : ""} with errors will be skipped — fix them inline above to include them.</div>`}
  </div>`;
}
