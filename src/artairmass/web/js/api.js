// Thin JSON client for the artairmass API. Errors carry the server's message.
export class ApiError extends Error {}

async function call(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    throw new ApiError("Lost contact with the artairmass server — is it still running?");
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { /* non-JSON */ }
  if (!res.ok) {
    let msg = data && data.detail ? data.detail : `${res.status} ${res.statusText}`;
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg || JSON.stringify(d)).join("; ");
    throw new ApiError(msg);
  }
  return data;
}

export const api = {
  get: (p) => call("GET", p),
  post: (p, b) => call("POST", p, b),
  put: (p, b) => call("PUT", p, b),
  del: (p) => call("DELETE", p),
};

// Run at most one request per key at a time; drop stale responses.
const latest = new Map();
export async function latestOnly(key, fn) {
  const token = Symbol();
  latest.set(key, token);
  const result = await fn();
  if (latest.get(key) !== token) throw new ApiError("__stale__");
  return result;
}
