const state = {
  settings: null,
  templates: [],
  selectedKey: null,
};

const statusEl = document.querySelector("#status");
const communityForm = document.querySelector("#community-form");
const templateForm = document.querySelector("#template-form");
const templateList = document.querySelector("#template-list");
const templateKey = document.querySelector("#template-key");
const timingGrid = document.querySelector("#timing-grid");

function setStatus(message) {
  statusEl.textContent = message;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Request failed: ${response.status}`);
  }

  return response.json();
}

function formValues(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function setFormValues(form, values) {
  for (const [key, value] of Object.entries(values)) {
    const field = form.elements[key];
    if (!field) continue;

    if (field.type === "checkbox") {
      field.checked = Boolean(value);
    } else {
      field.value = value ?? "";
    }
  }
}

function templateByKey(key) {
  return state.templates.find((template) => template.touchpoint_key === key);
}

function renderTemplates() {
  templateList.innerHTML = "";

  for (const template of state.templates) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = [
      "template-card",
      template.touchpoint_key === state.selectedKey ? "active" : "",
      template.active ? "" : "inactive",
    ].join(" ");
    button.dataset.key = template.touchpoint_key;
    button.innerHTML = `
      <strong>${template.name || template.touchpoint_key}</strong>
      <span>Day ${template.day || 1} · ${template.phase || "journey"} · ${template.automation ? "auto" : "manual"}</span>
    `;
    button.addEventListener("click", () => selectTemplate(template.touchpoint_key));
    templateList.appendChild(button);
  }
}

function selectTemplate(key) {
  const template = templateByKey(key);
  if (!template) return;

  state.selectedKey = key;
  templateKey.textContent = key;
  setFormValues(templateForm, template);
  renderTemplates();
}

function renderTiming(timing) {
  const labels = {
    follow_up_delay_mins: "Follow-up delay",
    abandon_after_hours: "Abandon after",
    nudge_delay_mins: "Nudge delay",
    timeout_hours: "Touchpoint timeout",
    engagement_threshold: "Engagement threshold",
    engagement_days: "Engagement window",
  };

  timingGrid.innerHTML = "";
  for (const [key, value] of Object.entries(timing)) {
    const card = document.createElement("div");
    card.className = "metric";
    card.innerHTML = `<span>${labels[key] || key}</span><strong>${value}</strong>`;
    timingGrid.appendChild(card);
  }
}

async function load() {
  try {
    setStatus("Loading settings...");
    const [settings, templates, timing] = await Promise.all([
      api("/api/settings"),
      api("/api/templates"),
      api("/api/settings/timing"),
    ]);

    state.settings = settings;
    state.templates = templates;
    setFormValues(communityForm, settings);
    renderTemplates();
    renderTiming(timing);

    if (templates.length) {
      selectTemplate(templates[0].touchpoint_key);
    }

    setStatus("Ready");
  } catch (error) {
    setStatus(`Error: ${error.message}`);
  }
}

async function saveCommunity() {
  try {
    setStatus("Saving community settings...");
    const payload = formValues(communityForm);
    state.settings = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    setFormValues(communityForm, state.settings);
    setStatus("Community settings saved");
  } catch (error) {
    setStatus(`Error: ${error.message}`);
  }
}

async function saveTemplate() {
  const selected = templateByKey(state.selectedKey);
  if (!selected) {
    setStatus("Select a template first");
    return;
  }

  try {
    setStatus("Saving template...");
    const raw = formValues(templateForm);
    const payload = {
      ...raw,
      day: raw.day ? Number(raw.day) : null,
      active: templateForm.elements.active.checked,
      automation: templateForm.elements.automation.checked,
      conditional: templateForm.elements.conditional.checked,
      requires_human: templateForm.elements.requires_human.checked,
    };

    const saved = await api(`/api/templates/${selected.touchpoint_key}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });

    state.templates = state.templates
      .map((template) => template.touchpoint_key === saved.touchpoint_key ? saved : template)
      .sort((a, b) => (a.day || 1) - (b.day || 1));

    selectTemplate(saved.touchpoint_key);
    setStatus("Template saved");
  } catch (error) {
    setStatus(`Error: ${error.message}`);
  }
}

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((panel) => panel.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#${button.dataset.panel}`).classList.add("active");
  });
});

document.querySelector("#save-community").addEventListener("click", saveCommunity);
document.querySelector("#save-template").addEventListener("click", saveTemplate);

load();
