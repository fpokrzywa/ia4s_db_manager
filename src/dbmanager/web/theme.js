import { get, patch } from "./api.js";
import { showError } from "./app.js";

const SAVED_STYLE_ID = "theme-saved";
const LIVE_STYLE_ID = "theme-live";

// Apply a theme's full effective color map to the page by setting a single
// <style id="theme-saved"> block. Any previous live-preview style is removed
// so the saved theme takes effect cleanly.
export function applyTheme(theme) {
  document.getElementById(LIVE_STYLE_ID)?.remove();
  applyEffective(SAVED_STYLE_ID, theme.effective || {});
}

function applyEffective(id, effective) {
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement("style");
    el.id = id;
    document.head.append(el);
  }
  const rules = Object.entries(effective)
    .map(([k, v]) => `${k}:${v};`).join("");
  el.textContent = `:root{${rules}}`;
}

// Render the admin Theme page. Fetches current theme + preset library, builds
// the preset dropdown and seven color pickers, and wires live preview.
export async function renderTheme() {
  const panel = document.getElementById("panel");
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = "Theme";
  panel.append(h);

  let current, presets, curated;
  try {
    current = await get("/api/theme");
    const meta = await get("/api/themes");
    presets = meta.presets;
    curated = meta.curated_vars;
  } catch (e) { showError(e.message); return; }

  // Working state — starts as the saved theme; live preview tracks this.
  const draft = {
    preset: current.preset,
    overrides: { ...current.overrides },
  };
  const computeEffective = () => ({
    ...presets[draft.preset], ...draft.overrides,
  });
  const repaint = () => applyEffective(LIVE_STYLE_ID, computeEffective());

  // Preset row
  const presetRow = document.createElement("div");
  presetRow.className = "row";
  const presetLabel = document.createElement("label");
  presetLabel.textContent = "Preset";
  const presetSelect = document.createElement("select");
  for (const name of Object.keys(presets)) {
    const opt = document.createElement("option");
    opt.value = name; opt.textContent = name;
    presetSelect.append(opt);
  }
  presetSelect.value = draft.preset;
  presetSelect.onchange = () => {
    draft.preset = presetSelect.value;
    rebuildPickers();
    repaint();
  };
  presetRow.append(presetLabel, presetSelect);
  panel.append(presetRow);

  // Color pickers — one row per curated var
  const pickersEl = document.createElement("div");
  panel.append(pickersEl);

  function rebuildPickers() {
    pickersEl.innerHTML = "";
    for (const v of curated) {
      const row = document.createElement("div");
      row.className = "row";
      const label = document.createElement("label");
      label.textContent = `${labelFor(v)} (${v})`;
      const picker = document.createElement("input");
      picker.type = "color";
      const presetVal = presets[draft.preset][v];
      picker.value = draft.overrides[v] ?? presetVal;
      picker.oninput = () => {
        if (picker.value.toLowerCase() === presetVal.toLowerCase()) {
          delete draft.overrides[v];
        } else {
          draft.overrides[v] = picker.value;
        }
        renderResetLink();
        repaint();
      };
      const resetLink = document.createElement("button");
      resetLink.className = "ghost";
      resetLink.textContent = "Reset";
      resetLink.style.marginLeft = ".4rem";
      resetLink.onclick = () => {
        delete draft.overrides[v];
        picker.value = presetVal;
        renderResetLink();
        repaint();
      };
      function renderResetLink() {
        resetLink.style.display = draft.overrides[v] ? "" : "none";
      }
      renderResetLink();
      row.append(label, picker, resetLink);
      pickersEl.append(row);
    }
  }
  rebuildPickers();

  // Actions row
  const actions = document.createElement("div");
  actions.className = "row";
  actions.style.marginTop = ".8rem";
  const resetAll = document.createElement("button");
  resetAll.className = "ghost";
  resetAll.textContent = "Reset all overrides";
  resetAll.onclick = () => {
    draft.overrides = {};
    rebuildPickers();
    repaint();
  };
  const cancel = document.createElement("button");
  cancel.className = "ghost";
  cancel.textContent = "Cancel";
  cancel.onclick = () => {
    draft.preset = current.preset;
    draft.overrides = { ...current.overrides };
    presetSelect.value = draft.preset;
    rebuildPickers();
    document.getElementById(LIVE_STYLE_ID)?.remove();
  };
  const save = document.createElement("button");
  save.textContent = "Save";
  save.onclick = async () => {
    try {
      const updated = await patch("/api/theme", {
        preset: draft.preset, overrides: draft.overrides,
      });
      current = updated;
      applyTheme(updated);
    } catch (e) { showError(e.message); }
  };
  actions.append(resetAll, cancel, save);
  panel.append(actions);

  // Initial paint so the picker values match the live page.
  repaint();
}

function labelFor(cssVar) {
  return {
    "--soot":   "Background",
    "--iron":   "Accent (primary)",
    "--ember":  "Accent (warm)",
    "--bone":   "Primary text",
    "--ash":    "Secondary text",
    "--patina": "Success",
    "--rust":   "Error",
  }[cssVar] || cssVar;
}
