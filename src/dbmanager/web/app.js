import { get, post } from "./api.js";

const loginEl = document.getElementById("login");
const appEl = document.getElementById("app");

async function showApp() {
  loginEl.classList.add("hidden");
  appEl.classList.remove("hidden");
  await loadSidebar();
}

function showLogin() {
  appEl.classList.add("hidden");
  loginEl.classList.remove("hidden");
}

async function loadSidebar() {
  // Replaced in Task 9.
  document.getElementById("sidebar").textContent = "Loading…";
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("login-error");
  errEl.textContent = "";
  try {
    await post("/api/login", {
      password: document.getElementById("login-password").value,
    });
    await showApp();
  } catch (err) {
    errEl.textContent = err.message;
  }
});

document.getElementById("logout").addEventListener("click", async () => {
  await post("/api/logout");
  showLogin();
});

// Probe the session: any authenticated endpoint works. Until Phase 2 adds
// /api/databases, fall back to showing the login screen.
(async function init() {
  try {
    await get("/api/databases");
    await showApp();
  } catch {
    showLogin();
  }
})();
