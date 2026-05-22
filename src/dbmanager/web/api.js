// Thin fetch wrapper. Throws Error(message) on failure; shows login on 401.
export async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(path, opts);
  if (resp.status === 401 && path !== "/api/login") {
    // Not authenticated — reveal the login screen. Never reload the page here:
    // the startup session probe expects a 401, and reloading would loop.
    document.getElementById("app")?.classList.add("hidden");
    document.getElementById("login")?.classList.remove("hidden");
    throw new Error("not authenticated");
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
