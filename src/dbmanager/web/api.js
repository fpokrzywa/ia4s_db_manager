// Thin fetch wrapper. Throws Error(message) on failure; redirects to login on 401.
export async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(path, opts);
  if (resp.status === 401 && path !== "/api/login") {
    window.location.reload();
    throw new Error("session expired");
  }
  const data = resp.headers.get("content-type")?.includes("application/json")
    ? await resp.json() : null;
  if (!resp.ok) {
    throw new Error(data?.detail || `${resp.status} ${resp.statusText}`);
  }
  return data;
}

export const get = (p) => api("GET", p);
export const post = (p, b) => api("POST", p, b);
export const patch = (p, b) => api("PATCH", p, b);
export const del = (p, b) => api("DELETE", p, b);
