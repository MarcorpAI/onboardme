const TOKEN_KEY = "onboardme_admin_token";

const state = {
  settings: null,
  templates: [],
  selectedKey: null,
  creating: false,
  token: sessionStorage.getItem(TOKEN_KEY) || "",
  activePanel: "community",
  qrObjectUrl: null,
  whatsappPoll: null,
};

const statusEl = document.querySelector("#status");
const loginScreen = document.querySelector("#login-screen");
const appShell = document.querySelector("#app-shell");
const loginForm = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");
const communityForm = document.querySelector("#community-form");
const templateForm = document.querySelector("#template-form");
const templateList = document.querySelector("#template-list");
const templateKey = document.querySelector("#template-key");
const timingGrid = document.querySelector("#timing-grid");
const qrImage = document.querySelector("#qr-image");
const qrMessage = document.querySelector("#qr-message");
const whatsappState = document.querySelector("#whatsapp-state");
const whatsappDetail = document.querySelector("#whatsapp-detail");

function setStatus(message) {
  statusEl.textContent = message;
}

function showApp() {
  loginScreen.classList.add("hidden");
  appShell.classList.remove("hidden");
}

function showLogin(message = "") {
  appShell.classList.add("hidden");
  loginScreen.classList.remove("hidden");
  loginError.textContent = message;
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Admin-Token": state.token,
    ...(options.headers || {}),
  };

  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) {
    sessionStorage.removeItem(TOKEN_KEY);
    state.token = "";
    showLogin("Invalid or expired token.");
    throw new Error("Unauthorized");
  }

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

function emptyTemplate() {
  return {
    name: "",
    day: 1,
    send_time: "",
    phase: "foundation",
    automation: true,
    conditional: false,
    requires_human: false,
    purpose: "",
    cta: "",
    brief: "",
    fallback_message: "",
    active: true,
  };
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
    button.innerHTML = `
      <strong>${template.name || template.touchpoint_key}</strong>
      <span>Day ${template.day || 1}${template.send_time ? ` at ${template.send_time}` : ""} · ${template.automation ? "auto" : "manual"}</span>
    `;
    button.addEventListener("click", () => selectTemplate(template.touchpoint_key));
    templateList.appendChild(button);
  }
}

function selectTemplate(key) {
  const template = templateByKey(key);
  if (!template) return;
  state.creating = false;
  state.selectedKey = key;
  templateKey.textContent = key;
  setFormValues(templateForm, template);
  renderTemplates();
}

function startNewTemplate() {
  state.creating = true;
  state.selectedKey = null;
  templateKey.textContent = "new_message";
  setFormValues(templateForm, emptyTemplate());
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
    showApp();
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
    if (templates.length) selectTemplate(templates[0].touchpoint_key);
    await refreshWhatsApp();
    setStatus("Ready");
  } catch (error) {
    if (error.message !== "Unauthorized") setStatus(`Error: ${error.message}`);
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
    if (error.message !== "Unauthorized") setStatus(`Error: ${error.message}`);
  }
}

async function saveTemplate() {
  try {
    setStatus("Saving message...");
    const raw = formValues(templateForm);
    const payload = {
      ...raw,
      day: raw.day ? Number(raw.day) : 1,
      send_time: raw.send_time || null,
      active: templateForm.elements.active.checked,
      automation: templateForm.elements.automation.checked,
      conditional: templateForm.elements.conditional.checked,
      requires_human: templateForm.elements.requires_human.checked,
    };

    const path = state.creating ? "/api/templates" : `/api/templates/${state.selectedKey}`;
    const method = state.creating ? "POST" : "PUT";
    const saved = await api(path, { method, body: JSON.stringify(payload) });

    if (state.creating) {
      state.templates.push(saved);
    } else {
      state.templates = state.templates.map((template) =>
        template.touchpoint_key === saved.touchpoint_key ? saved : template
      );
    }
    state.templates.sort((a, b) => (a.day || 1) - (b.day || 1));
    selectTemplate(saved.touchpoint_key);
    setStatus("Message saved");
  } catch (error) {
    if (error.message !== "Unauthorized") setStatus(`Error: ${error.message}`);
  }
}

async function refreshWhatsApp() {
  try {
    const [status, qr] = await Promise.all([
      api("/api/whatsapp/status"),
      api("/api/whatsapp/qr"),
    ]);

    whatsappState.textContent = status.connected ? "Connected" : "Not connected";
    whatsappDetail.textContent = status.connected
      ? "The bridge is ready to send and receive messages."
      : "Scan the QR code with WhatsApp if one is available.";

    if (qr.qr) {
      qrImage.classList.remove("hidden");
      const imageResponse = await fetch(`/api/whatsapp/qr.png?t=${Date.now()}`, {
        cache: "no-store",
        headers: { "X-Admin-Token": state.token },
      });
      if (!imageResponse.ok) throw new Error("QR image unavailable");
      const blob = await imageResponse.blob();
      if (state.qrObjectUrl) URL.revokeObjectURL(state.qrObjectUrl);
      state.qrObjectUrl = URL.createObjectURL(blob);
      qrImage.src = state.qrObjectUrl;
      qrMessage.textContent = "Scan this code from WhatsApp > Linked devices.";
    } else {
      if (state.qrObjectUrl) URL.revokeObjectURL(state.qrObjectUrl);
      state.qrObjectUrl = null;
      qrImage.classList.add("hidden");
      qrImage.removeAttribute("src");
      qrMessage.textContent = qr.message || "No QR code available.";
    }
  } catch (error) {
    if (error.message !== "Unauthorized") {
      whatsappState.textContent = "Unavailable";
      whatsappDetail.textContent = error.message;
    }
  }
}

async function disconnectWhatsApp() {
  if (!confirm("Disconnect WhatsApp and clear the current bridge session?")) return;

  try {
    setStatus("Disconnecting WhatsApp...");
    await api("/api/whatsapp/disconnect", { method: "POST" });
    whatsappState.textContent = "Disconnected";
    whatsappDetail.textContent = "Session cleared. A new QR code should appear shortly.";
    setStatus("WhatsApp disconnected");
    setTimeout(refreshWhatsApp, 2000);
  } catch (error) {
    if (error.message !== "Unauthorized") setStatus(`Error: ${error.message}`);
  }
}

function updateWhatsAppPolling() {
  if (state.whatsappPoll) {
    clearInterval(state.whatsappPoll);
    state.whatsappPoll = null;
  }

  if (state.activePanel === "whatsapp" && state.token) {
    refreshWhatsApp();
    state.whatsappPoll = setInterval(refreshWhatsApp, 5000);
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = new FormData(loginForm).get("token");
  state.token = token;
  try {
    await api("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
    sessionStorage.setItem(TOKEN_KEY, token);
    loginError.textContent = "";
    await load();
  } catch (error) {
    sessionStorage.removeItem(TOKEN_KEY);
    state.token = "";
    loginError.textContent = "Invalid token.";
  }
});

document.querySelector("#logout").addEventListener("click", () => {
  sessionStorage.removeItem(TOKEN_KEY);
  state.token = "";
  if (state.whatsappPoll) clearInterval(state.whatsappPoll);
  state.whatsappPoll = null;
  showLogin();
});

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((panel) => panel.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#${button.dataset.panel}`).classList.add("active");
    state.activePanel = button.dataset.panel;
    updateWhatsAppPolling();
  });
});

document.querySelector("#save-community").addEventListener("click", saveCommunity);
document.querySelector("#save-template").addEventListener("click", saveTemplate);
document.querySelector("#new-template").addEventListener("click", startNewTemplate);
document.querySelector("#refresh-whatsapp").addEventListener("click", refreshWhatsApp);
document.querySelector("#disconnect-whatsapp").addEventListener("click", disconnectWhatsApp);

if (state.token) {
  load();
} else {
  showLogin();
}
