import { html, useContext, useEffect, useState } from "../lib.js";
import { Store, targetPayload } from "../store.js";
import { api } from "../api.js";
import { fix, airmassLevel } from "../format.js";

export function PlanetsView() {
  const { state, actions } = useContext(Store);
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(false);
  const target = state.targets.find((t) => t.id === state.selectedId);
  useEffect(() => {
    let alive = true;
    setBusy(true);
    const t = setTimeout(() => api.post("/api/planets", { site: state.siteKey, time: state.jd, target: target && !target.body ? targetPayload(target) : null })
      .then((r) => alive && setRows(r.rows)).catch((e) => actions.toast(e.message, true)).finally(() => alive && setBusy(false)), 250);
    return () => { alive = false; clearTimeout(t); };
  }, [state.siteKey, Math.round(state.jd * 1440), target?.id, target?.ra, target?.dec]);
  if (!rows) return html`<div class="placeholder">Computing planet positions…</div>`;
  return html`<section class=${"card" + (busy ? " loading" : "")}>
    <h3>Planets <small class="muted" style="text-transform:none;letter-spacing:0">apparent topocentric, equinox of date · click a row to make it the target</small></h3>
    <div style="overflow:auto"><table class="tbl">
      <thead><tr><th>Planet</th><th>RA</th><th>Dec</th><th>HA</th><th>Alt</th><th>Az</th><th>Airmass</th><th>Constellation</th><th title="Angle from the selected target">Proximity</th></tr></thead>
      <tbody>${rows.map((r) => {
        const lvl = airmassLevel(r.airmass, r.alt_deg);
        return html`<tr class="clickable" onClick=${() => actions.addBody(r.name, true)}>
          <td style="font-family:var(--font);font-weight:550">${r.name}</td><td>${r.ra}</td><td>${r.dec}</td><td>${r.ha.slice(0, 6)}</td>
          <td>${fix(r.alt_deg, 1)}°</td><td>${fix(r.az_deg, 1)}°</td>
          <td class=${r.alt_deg <= 0 ? "w-muted" : ""}>${r.alt_deg > 0 ? html`${fix(r.airmass, 2)} <span class=${"status " + lvl.level} style="border:0;padding:0 0 0 4px"></span>` : "down"}</td>
          <td style="font-family:var(--font)">${r.constellation}</td>
          <td class=${r.proximity_deg != null && r.proximity_deg < 3 ? "w-serious" : ""}>${r.proximity_deg == null ? "—" : fix(r.proximity_deg, 2) + "°"}</td></tr>`;
      })}</tbody></table></div>
    <p class="muted" style="font-size:.82rem;margin:10px 0 0">Positions from astropy's built-in ERFA ephemeris (much better than JSkyCalc's arcminute-level Meeus theory). Pluto needs a JPL kernel and is omitted offline.</p>
  </section>`;
}
