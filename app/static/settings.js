const TOKEN_KEY = "onboardme_admin_token";

const state = {
  settings: null,
  templates: [],
  groups: [],
  events: [],
  selectedKey: null,
  selectedGroupId: null,
  selectedEventId: null,
  creating: false,
  creatingGroup: false,
  creatingEvent: false,
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
const whatsappForm = document.querySelector("#whatsapp-form");
const templateForm = document.querySelector("#template-form");
const templateList = document.querySelector("#template-list");
const templateKey = document.querySelector("#template-key");
const groupForm = document.querySelector("#group-form");
const groupList = document.querySelector("#group-list");
const groupId = document.querySelector("#group-id");
const eventForm = document.querySelector("#event-form");
const eventList = document.querySelector("#event-list");
const eventId = document.querySelector("#event-id");
const timingGrid = document.querySelector("#timing-grid");
const qrImage = document.querySelector("#qr-image");
const qrMessage = document.querySelector("#qr-message");
const whatsappState = document.querySelector("#whatsapp-state");
const whatsappDetail = document.querySelector("#whatsapp-detail");

const COMMUNITY_MESSAGE_META = {
  day_1_community_orientation: {
    order: 1,
    label: "Approval welcome",
    editorDay: 1,
  },
  weekly_build_in_public: {
    order: 2,
    label: "Monday rhythm",
    editorDay: 2,
  },
  checkin_midweek_progress: {
    order: 3,
    label: "Wednesday check-in",
    editorDay: 3,
  },
  weekly_member_visibility: {
    order: 4,
    label: "Thursday visibility",
    editorDay: 4,
  },
  weekly_little_wins: {
    order: 5,
    label: "Friday wins",
    editorDay: 5,
  },
  checkin_weekend_reflection: {
    order: 6,
    label: "Saturday reflection",
    editorDay: 6,
  },
};

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

function emptyGroup() {
  return {
    name: "",
    description: "",
    purpose: "",
    link: "",
    activity_day: "",
    cta_guidance: "",
    sort_order: state.groups.length + 1,
    active: true,
  };
}

function emptyEvent() {
  return {
    title: "",
    description: "",
    starts_at: "",
    ends_at: "",
    location: "",
    link: "",
    reminder_hours_before: 24,
    active: true,
  };
}

function templateByKey(key) {
  return state.templates.find((template) => template.touchpoint_key === key);
}

function groupById(id) {
  return state.groups.find((group) => group.id === id);
}

function eventById(id) {
  return state.events.find((event) => event.id === id);
}

function templateMeta(template) {
  return COMMUNITY_MESSAGE_META[template.touchpoint_key] || null;
}

function templateSortValue(template) {
  const meta = templateMeta(template);
  if (meta) return meta.order;
  return 1000 + (template.day || 1);
}

function sortTemplates() {
  state.templates.sort((a, b) => {
    const orderDiff = templateSortValue(a) - templateSortValue(b);
    if (orderDiff !== 0) return orderDiff;
    return (a.name || a.touchpoint_key).localeCompare(b.name || b.touchpoint_key);
  });
}

function templateScheduleLabel(template) {
  const meta = templateMeta(template);
  if (meta) return meta.label;
  return `Custom order ${template.day || 1}${template.send_time ? ` at ${template.send_time}` : ""}`;
}

function templateForForm(template) {
  const meta = templateMeta(template);
  if (!meta) return template;
  return {
    ...template,
    day: meta.editorDay,
    phase: template.phase || "community",
  };
}

function toDatetimeLocal(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function fromDatetimeLocal(value) {
  if (!value) return null;
  return new Date(value).toISOString();
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
      <span>${templateScheduleLabel(template)} · ${template.automation ? "auto" : "manual"}</span>
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
  setFormValues(templateForm, templateForForm(template));
  renderTemplates();
}

function startNewTemplate() {
  state.creating = true;
  state.selectedKey = null;
  templateKey.textContent = "new_message";
  setFormValues(templateForm, emptyTemplate());
  renderTemplates();
}

function renderGroups() {
  groupList.innerHTML = "";
  for (const group of state.groups) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = [
      "group-card",
      group.id === state.selectedGroupId ? "active" : "",
      group.active ? "" : "inactive",
    ].join(" ");
    button.innerHTML = `
      <strong>${group.name}</strong>
      <span>${group.activity_day || "Always available"}${group.link ? " · linked" : ""}</span>
    `;
    button.addEventListener("click", () => selectGroup(group.id));
    groupList.appendChild(button);
  }
}

function selectGroup(id) {
  const group = groupById(id);
  if (!group) return;
  state.creatingGroup = false;
  state.selectedGroupId = id;
  groupId.textContent = id;
  setFormValues(groupForm, group);
  renderGroups();
}

function startNewGroup() {
  state.creatingGroup = true;
  state.selectedGroupId = null;
  groupId.textContent = "new_group";
  setFormValues(groupForm, emptyGroup());
  renderGroups();
}

function renderEvents() {
  eventList.innerHTML = "";
  for (const event of state.events) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = [
      "event-card",
      event.id === state.selectedEventId ? "active" : "",
      event.active ? "" : "inactive",
    ].join(" ");
    const when = event.starts_at ? new Date(event.starts_at).toLocaleString() : "No date";
    button.innerHTML = `
      <strong>${event.title}</strong>
      <span>${when}${event.link ? " · linked" : ""}</span>
    `;
    button.addEventListener("click", () => selectEvent(event.id));
    eventList.appendChild(button);
  }
}

function selectEvent(id) {
  const event = eventById(id);
  if (!event) return;
  state.creatingEvent = false;
  state.selectedEventId = id;
  eventId.textContent = id;
  setFormValues(eventForm, {
    ...event,
    starts_at: toDatetimeLocal(event.starts_at),
    ends_at: toDatetimeLocal(event.ends_at),
  });
  renderEvents();
}

function startNewEvent() {
  state.creatingEvent = true;
  state.selectedEventId = null;
  eventId.textContent = "new_event";
  setFormValues(eventForm, emptyEvent());
  renderEvents();
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
    const [settings, templates, groups, events, timing] = await Promise.all([
      api("/api/settings"),
      api("/api/templates"),
      api("/api/groups"),
      api("/api/events"),
      api("/api/settings/timing"),
    ]);

    state.settings = settings;
    state.templates = templates;
    state.groups = groups;
    state.events = events;
    sortTemplates();
    setFormValues(communityForm, settings);
    setFormValues(whatsappForm, settings);
    renderTemplates();
    renderGroups();
    renderEvents();
    renderTiming(timing);
    if (templates.length) selectTemplate(templates[0].touchpoint_key);
    if (groups.length) selectGroup(groups[0].id);
    if (events.length) selectEvent(events[0].id);
    await refreshWhatsApp();
    setStatus("Ready");
  } catch (error) {
    if (error.message !== "Unauthorized") setStatus(`Error: ${error.message}`);
  }
}

async function saveWhatsAppSettings() {
  try {
    setStatus("Saving WhatsApp settings...");
    const payload = formValues(whatsappForm);
    state.settings = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    setFormValues(whatsappForm, state.settings);
    setStatus("WhatsApp settings saved");
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
    sortTemplates();
    selectTemplate(saved.touchpoint_key);
    setStatus("Message saved");
  } catch (error) {
    if (error.message !== "Unauthorized") setStatus(`Error: ${error.message}`);
  }
}

async function saveGroup() {
  try {
    setStatus("Saving group...");
    const raw = formValues(groupForm);
    const payload = {
      ...raw,
      sort_order: raw.sort_order ? Number(raw.sort_order) : 0,
      active: groupForm.elements.active.checked,
    };

    const path = state.creatingGroup ? "/api/groups" : `/api/groups/${state.selectedGroupId}`;
    const method = state.creatingGroup ? "POST" : "PUT";
    const saved = await api(path, { method, body: JSON.stringify(payload) });

    if (state.creatingGroup) {
      state.groups.push(saved);
    } else {
      state.groups = state.groups.map((group) => group.id === saved.id ? saved : group);
    }
    state.groups.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    selectGroup(saved.id);
    setStatus("Group saved");
  } catch (error) {
    if (error.message !== "Unauthorized") setStatus(`Error: ${error.message}`);
  }
}

async function saveEvent() {
  try {
    setStatus("Saving event...");
    const raw = formValues(eventForm);
    const payload = {
      ...raw,
      starts_at: fromDatetimeLocal(raw.starts_at),
      ends_at: fromDatetimeLocal(raw.ends_at),
      reminder_hours_before: raw.reminder_hours_before ? Number(raw.reminder_hours_before) : 24,
      active: eventForm.elements.active.checked,
    };

    const path = state.creatingEvent ? "/api/events" : `/api/events/${state.selectedEventId}`;
    const method = state.creatingEvent ? "POST" : "PUT";
    const saved = await api(path, { method, body: JSON.stringify(payload) });

    if (state.creatingEvent) {
      state.events.push(saved);
    } else {
      state.events = state.events.map((event) => event.id === saved.id ? saved : event);
    }
    state.events.sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at));
    selectEvent(saved.id);
    setStatus("Event saved");
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
document.querySelector("#save-group").addEventListener("click", saveGroup);
document.querySelector("#new-group").addEventListener("click", startNewGroup);
document.querySelector("#save-event").addEventListener("click", saveEvent);
document.querySelector("#new-event").addEventListener("click", startNewEvent);
document.querySelector("#refresh-whatsapp").addEventListener("click", refreshWhatsApp);
document.querySelector("#disconnect-whatsapp").addEventListener("click", disconnectWhatsApp);
document.querySelector("#save-whatsapp").addEventListener("click", saveWhatsAppSettings);

if (state.token) {
  load();
} else {
  showLogin();
}
