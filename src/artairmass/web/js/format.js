// Formatting helpers and the warning thresholds (JSkyCalc's colour logic, as status levels).

export const JD_UNIX_EPOCH = 2440587.5;
export const SIDEREAL_RATE = 1.00273790935;
export const jdFromMs = (ms) => ms / 86400000 + JD_UNIX_EPOCH;
export const msFromJd = (jd) => (jd - JD_UNIX_EPOCH) * 86400000;
export const nowJd = () => jdFromMs(Date.now());

export function hms(hours, { signed = false, dp = 0, sep = ":" } = {}) {
  if (hours == null || !isFinite(hours)) return "—";
  const sign = hours < 0 ? "-" : signed ? "+" : "";
  const scale = 10 ** dp;
  let total = Math.round(Math.abs(hours) * 3600 * scale);
  const frac = total % scale;
  total = Math.floor(total / scale);
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  const p = (v, n = 2) => String(v).padStart(n, "0");
  return `${sign}${p(h)}${sep}${p(m)}${sep}${p(s)}${dp ? "." + p(frac, dp) : ""}`;
}
export const hm = (hours, signed = false) =>
  hours == null || !isFinite(hours) ? "—" : hms(Math.round(hours * 60) / 60, { signed }).slice(0, -3);
export const raStr = (deg, dp = 2) => hms(deg / 15, { dp });
export const decStr = (deg, dp = 1) => hms(deg, { signed: true, dp });
export const fix = (v, n = 2) => (v == null || !isFinite(v) ? "—" : Number(v).toFixed(n));
export const wrap24 = (h) => ((h % 24) + 24) % 24;

// Local wall-clock formatting in the *site's* IANA zone (not the browser's).
const fmtCache = new Map();
function fmt(tz, opts) {
  const key = tz + JSON.stringify(opts);
  if (!fmtCache.has(key)) fmtCache.set(key, new Intl.DateTimeFormat("en-GB", { timeZone: tz, hourCycle: "h23", ...opts }));
  return fmtCache.get(key);
}
export function localParts(jd, tz) {
  const parts = {};
  for (const p of fmt(tz, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", weekday: "short", timeZoneName: "short" }).formatToParts(new Date(msFromJd(jd))))
    parts[p.type] = p.value;
  return parts;
}
export function localTime(jd, tz, seconds = true) {
  const p = localParts(jd, tz);
  return seconds ? `${p.hour}:${p.minute}:${p.second}` : `${p.hour}:${p.minute}`;
}
export function localDate(jd, tz) {
  const p = localParts(jd, tz);
  return `${p.year}-${p.month}-${p.day}`;
}
export function zoneLabel(jd, tz) {
  const z = localParts(jd, tz).timeZoneName || "";
  return z.replace(/^GMT/, "UTC").replace(/^UTC([+-])(\d+)$/, (_, s, h) => `UTC${s === "-" ? "−" : "+"}${h}`);
}
export function utcTime(jd, seconds = true) {
  const d = new Date(msFromJd(jd));
  const s = d.toISOString();
  return seconds ? s.slice(11, 19) : s.slice(11, 16);
}
export const utcDate = (jd) => new Date(msFromJd(jd)).toISOString().slice(0, 10);

/** Night (local evening date) containing jd — before local noon belongs to the previous evening. */
export function nightOf(jd, tz) {
  const p = localParts(jd, tz);
  const d = new Date(Date.UTC(+p.year, +p.month - 1, +p.day));
  if (+p.hour < 12) d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}
export function addDays(iso, n) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

// ---- warning levels: status = good | warning | serious | critical (icon+label in UI) ----
export function airmassLevel(am, alt) {
  if (alt != null && alt <= 0) return { level: "critical", label: "below horizon" };
  if (am == null || !isFinite(am)) return { level: "critical", label: "below horizon" };
  if (am >= 4) return { level: "critical", label: "very high airmass" };
  if (am >= 3) return { level: "serious", label: "high airmass" };
  if (am >= 2) return { level: "warning", label: "airmass ≥ 2" };
  return { level: "good", label: "good" };
}
export function haLevel(haH) {
  return Math.abs(haH) > 6 ? { level: "warning", label: "|HA| > 6 h" } : null;
}
export function moonSepLevel(sep, moonAlt) {
  if (moonAlt != null && moonAlt < 0) return { level: "good", label: "Moon down" };
  if (sep < 10) return { level: "critical", label: "very close to Moon" };
  if (sep < 25) return { level: "serious", label: "close to Moon" };
  if (sep < 45) return { level: "warning", label: "Moon nearby" };
  return { level: "good", label: "clear of Moon" };
}
// K&S moonlight vs a ~21.7 V mag/arcsec² dark sky.
export function skyBrightLevel(v) {
  if (v == null) return { level: "good", label: "no moonlight" };
  if (v < 18) return { level: "critical", label: "very bright sky" };
  if (v < 19.5) return { level: "serious", label: "bright sky" };
  if (v < 21) return { level: "warning", label: "moonlit sky" };
  return { level: "good", label: "dark-ish" };
}
export function skyState(sunAlt) {
  if (sunAlt > -0.8333) return { name: "Daytime", short: "day" };
  if (sunAlt > -6) return { name: "Civil twilight", short: "civil" };
  if (sunAlt > -12) return { name: "Nautical twilight", short: "nautical" };
  if (sunAlt > -18) return { name: "Astronomical twilight", short: "astro" };
  return { name: "Night", short: "night" };
}
export const SERIES = 8;
