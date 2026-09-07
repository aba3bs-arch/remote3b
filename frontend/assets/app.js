const TOKEN_STORAGE_KEY = "am_connect_api_token";
const API_BASE_URL = (window.AM_CONNECT_CONFIG?.apiBaseUrl || "").replace(/\/$/, "");

const sampleDevices = [
  { device_id: "device_001", device_name: "3B Fusion", os: "Windows", is_online: true, last_accessed: new Date(Date.now() - 60 * 60 * 1000).toISOString() },
  { device_id: "device_002", device_name: "3B10 ElMezquite", os: "Windows", is_online: true, last_accessed: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString() },
  { device_id: "device_003", device_name: "3B2 pueblo nuevo", os: "Windows", is_online: true, last_accessed: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString() },
  { device_id: "device_004", device_name: "3B5 Lomas Dos", os: "Windows", is_online: true, last_accessed: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString() },
  { device_id: "device_005", device_name: "3B6 Soli", os: "Windows", is_online: true, last_accessed: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString() },
  { device_id: "device_006", device_name: "3B7 Del Valle", os: "Windows", is_online: true, last_accessed: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString() },
  { device_id: "device_007", device_name: "3B9 B. Aires", os: "Windows", is_online: true, last_accessed: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString() },
  { device_id: "device_008", device_name: "EastTexas", os: "Windows", is_online: false, last_accessed: new Date(Date.now() - 9 * 60 * 60 * 1000).toISOString() },
  { device_id: "device_009", device_name: "TabletAcacia", os: "Windows", is_online: false, last_accessed: "2024-11-12T14:38:30" },
];

const state = {
  devices: [],
  selectedId: null,
  filter: "",
  usingApi: false,
  username: "",
};

const rows = document.querySelector("#computerRows");
const searchInput = document.querySelector("#searchInput");
const dataSource = document.querySelector("#dataSource");
const usedCount = document.querySelector("#usedCount");
const tokenDialog = document.querySelector("#tokenDialog");
const addDialog = document.querySelector("#addDialog");
const helpDialog = document.querySelector("#helpDialog");
const tokenButton = document.querySelector("#tokenButton");
const tokenInput = document.querySelector("#tokenInput");
const saveTokenButton = document.querySelector("#saveTokenButton");
const usernameInput = document.querySelector("#usernameInput");
const passwordInput = document.querySelector("#passwordInput");
const emailInput = document.querySelector("#emailInput");
const totpInput = document.querySelector("#totpInput");
const loginButton = document.querySelector("#loginButton");
const registerButton = document.querySelector("#registerButton");
const authMessage = document.querySelector("#authMessage");
const addMessage = document.querySelector("#addMessage");
const newDeviceName = document.querySelector("#newDeviceName");
const newDeviceOs = document.querySelector("#newDeviceOs");
const installerCommand = document.querySelector("#installerCommand");
const accountButton = document.querySelector("#accountButton");
const downloadAgentButton = document.querySelector("#downloadAgentButton");

function windowsIconSvg(isOnline) {
  const fill = isOnline ? "#00adef" : "#9aa4ab";
  return `<svg class="windows-icon" viewBox="0 0 88 88" aria-hidden="true"><path fill="${fill}" d="M0 12.5 36 7.6v33.2H0zm40-6.2L88 0v40.4H40zM0 47.2h36v33.2L0 75.4zm40 .4h48V88l-48-7.2z"/></svg>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function relativeAccessed(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const delta = Date.now() - date.getTime();
  const minutes = Math.round(delta / 60000);
  if (minutes < 2) {
    return "a minute ago";
  }
  if (minutes < 60) {
    return `${minutes} minutes ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours === 1) {
    return "an hour ago";
  }
  if (hours < 24) {
    return `${hours} hours ago`;
  }
  const days = Math.round(hours / 24);
  if (days < 14) {
    return `${days} day${days === 1 ? "" : "s"} ago`;
  }
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function normalizeApiDevice(device) {
  return {
    device_id: device.device_id,
    device_name: device.device_name || device.device_id,
    os: device.os || "Windows",
    is_online: Boolean(device.is_online),
    in_session: Boolean(device.in_session),
    last_seen: device.last_seen,
    last_accessed: device.last_accessed || device.last_seen,
    connection_error: device.connection_error,
  };
}

async function apiRequest(url, options = {}) {
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  const headers = { ...(options.headers || {}) };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(`${API_BASE_URL}${url}`, { ...options, headers });
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const text = await response.text();
    if (text.trim().startsWith("<!DOCTYPE") || text.trim().startsWith("<html")) {
      throw new Error("El frontend esta recibiendo HTML en vez de JSON.");
    }
    throw new Error(`Respuesta inesperada del servidor (${contentType || "sin content-type"}).`);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || payload.detail || `HTTP ${response.status}`);
  }
  return payload;
}

function filteredDevices() {
  const query = state.filter.trim().toLowerCase();
  if (!query) {
    return state.devices;
  }
  return state.devices.filter((device) => device.device_name.toLowerCase().includes(query));
}

function render() {
  const devices = filteredDevices();
  usedCount.textContent = state.devices.length;
  rows.innerHTML = "";

  if (devices.length === 0) {
    rows.innerHTML = '<tr><td colspan="4">No hay computadoras. Pulsa Agregar equipo / Descargar.</td></tr>';
  } else {
    devices.forEach((device) => {
      const row = document.createElement("tr");
      row.className = device.device_id === state.selectedId ? "selected" : "";
      const status = device.is_online ? "Online" : "Offline";
      row.innerHTML = `
        <td>
          <span class="computer-name">
            ${windowsIconSvg(device.is_online)}
            ${escapeHtml(device.device_name)}
          </span>
        </td>
        <td>
          <div class="status-actions">
            <button class="connect-small" type="button" ${device.is_online ? "" : "disabled"}>Connect</button>
            <span class="status ${device.is_online ? "online" : "offline"}">${status}</span>
          </div>
        </td>
        <td>${escapeHtml(relativeAccessed(device.last_accessed || device.last_seen))}</td>
        <td>${device.is_online ? '<button class="cloud-action" type="button" aria-label="Backup">☁</button>' : ""}</td>
      `;
      row.addEventListener("click", () => {
        state.selectedId = device.device_id;
        render();
      });
      row.querySelector(".connect-small").addEventListener("click", (event) => {
        event.stopPropagation();
        openRemoteSession(device);
      });
      rows.appendChild(row);
    });
  }

  if (state.username) {
    accountButton.textContent = state.username.slice(0, 1).toUpperCase();
  }
}

function openRemoteSession(device) {
  if (!device.is_online) {
    window.alert("El equipo esta Offline. Instala AM-CONNECT-Agent.exe en esa PC de tienda.");
    return;
  }
  const hasConsent = window.confirm(`Confirma que tienes autorizacion para Connect en ${device.device_name}.`);
  if (!hasConsent) {
    return;
  }
  if (state.usingApi) {
    apiRequest(`/api/devices/${encodeURIComponent(device.device_id)}/access`, { method: "POST" }).catch(() => {});
  }
  const query = new URLSearchParams({ device: device.device_id, name: device.device_name });
  window.location.assign(`/session?${query.toString()}`);
}

async function loadDevicesFromApi() {
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  if (!token) {
    state.devices = sampleDevices;
    state.usingApi = false;
    state.username = "";
    dataSource.textContent = "Mostrando ejemplo. Inicia sesion para ver tus PCs reales.";
    render();
    return;
  }

  try {
    const payload = await apiRequest("/api/devices");
    state.devices = (payload.devices || []).map(normalizeApiDevice);
    state.usingApi = true;
    dataSource.textContent =
      state.devices.length === 0
        ? "Sesion activa. Agrega la primera computadora de tienda."
        : `Computadoras usadas: ${state.devices.length}`;
    try {
      const me = await apiRequest("/api/me");
      state.username = me.user?.username || "";
    } catch (_error) {
      state.username = "";
    }
  } catch (error) {
    state.devices = sampleDevices;
    state.usingApi = false;
    dataSource.textContent = `No se pudo cargar la API (${error.message}). Mostrando ejemplo.`;
  }

  if (!state.selectedId || !state.devices.some((device) => device.device_id === state.selectedId)) {
    state.selectedId = state.devices[0]?.device_id || null;
  }
  render();
}

async function loginWithCredentials() {
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  const totp = totpInput.value.trim();
  if (!username || !password) {
    authMessage.textContent = "Escribe usuario y contrasena.";
    return;
  }
  const params = new URLSearchParams({ username, password });
  if (totp) {
    params.set("totp_code", totp);
  }
  authMessage.textContent = "Autenticando...";
  try {
    const payload = await apiRequest(`/api/auth/login?${params.toString()}`, { method: "POST" });
    window.localStorage.setItem(TOKEN_STORAGE_KEY, payload.access_token);
    tokenInput.value = payload.access_token;
    passwordInput.value = "";
    totpInput.value = "";
    state.username = payload.user.username;
    authMessage.textContent = `Sesion iniciada como ${payload.user.username}.`;
    await loadDevicesFromApi();
    tokenDialog.close();
  } catch (error) {
    authMessage.textContent = `Error de autenticacion: ${error.message}`;
  }
}

async function registerUser() {
  const username = usernameInput.value.trim();
  const email = emailInput.value.trim();
  const password = passwordInput.value;
  if (!username || !email || !password) {
    authMessage.textContent = "Para crear usuario escribe usuario, email y contrasena.";
    return;
  }
  const params = new URLSearchParams({ username, email, password });
  authMessage.textContent = "Creando usuario...";
  try {
    const payload = await apiRequest(`/api/auth/register?${params.toString()}`, { method: "POST" });
    authMessage.textContent = `Usuario ${payload.username} creado. Ahora inicia sesion.`;
  } catch (error) {
    authMessage.textContent = `No se pudo crear usuario: ${error.message}`;
  }
}

function requireAuthForAction() {
  if (window.localStorage.getItem(TOKEN_STORAGE_KEY)) {
    return true;
  }
  tokenDialog.showModal();
  return false;
}

async function registerStoreComputer() {
  if (!requireAuthForAction()) {
    return;
  }
  const name = newDeviceName.value.trim();
  if (!name) {
    addMessage.textContent = "Escribe el nombre de la tienda o de la PC.";
    return;
  }
  addMessage.textContent = "Registrando computadora...";
  try {
    const params = new URLSearchParams({ device_name: name, os: newDeviceOs.value });
    const created = await apiRequest(`/api/devices/register?${params.toString()}`, { method: "POST" });
    const installer = await apiRequest(`/api/devices/${encodeURIComponent(created.device_id)}/installer`);
    installerCommand.value = installer.command;
    addMessage.textContent = `${name} registrada. En la tienda pega el comando o usa el .exe del agente.`;
    await loadDevicesFromApi();
  } catch (error) {
    addMessage.textContent = `No se pudo registrar: ${error.message}`;
  }
}

function exportDevices() {
  const header = ["Computer Name", "Status", "Accessed"];
  const lines = filteredDevices().map((device) => [
    device.device_name,
    device.is_online ? "Online" : "Offline",
    relativeAccessed(device.last_accessed || device.last_seen),
  ]);
  const csv = [header, ...lines]
    .map((line) => line.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))
    .join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "am-connect-computadoras.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function showView(name) {
  const computersView = document.querySelector("#computersView");
  const attendedView = document.querySelector("#attendedView");
  const isAttended = name === "attended";
  computersView.hidden = isAttended;
  attendedView.hidden = !isAttended;
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === name);
  });
}

async function detectAgentDownload() {
    try {
      const payload = await apiRequest("/api/downloads");
      downloadAgentButton.hidden = !payload.agent_exe;
    } catch (_error) {
      downloadAgentButton.hidden = true;
    }
}

searchInput.addEventListener("input", (event) => {
  state.filter = event.target.value;
  render();
});

document.querySelector("#addComputerButton").addEventListener("click", () => {
  if (!requireAuthForAction()) {
    return;
  }
  addMessage.textContent = "";
  installerCommand.value = "";
  detectAgentDownload();
  addDialog.showModal();
});

document.querySelector("#helpNav").addEventListener("click", (event) => {
  event.preventDefault();
  helpDialog.showModal();
});

document.querySelector("#attendedBackButton").addEventListener("click", () => showView("computers"));
document.querySelector("#exportButton").addEventListener("click", exportDevices);

document.querySelectorAll("[data-view]").forEach((item) => {
  item.addEventListener("click", (event) => {
    const view = item.dataset.view;
    if (view === "help") {
      return;
    }
    event.preventDefault();
    if (view === "attended") {
      showView("attended");
      return;
    }
    if (view === "account") {
      tokenDialog.showModal();
      return;
    }
    showView("computers");
  });
});

tokenButton.addEventListener("click", () => {
  tokenInput.value = window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  tokenDialog.showModal();
});
accountButton.addEventListener("click", () => {
  tokenInput.value = window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  tokenDialog.showModal();
});
loginButton.addEventListener("click", loginWithCredentials);
registerButton.addEventListener("click", registerUser);
saveTokenButton.addEventListener("click", () => {
  const token = tokenInput.value.trim();
  if (token) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
  tokenDialog.close();
  loadDevicesFromApi();
});
document.querySelector("#registerDeviceButton").addEventListener("click", registerStoreComputer);
document.querySelector("#copyInstallerButton").addEventListener("click", async () => {
  if (!installerCommand.value) {
    addMessage.textContent = "Primero registra la computadora.";
    return;
  }
  await navigator.clipboard.writeText(installerCommand.value);
  addMessage.textContent = "Comando copiado. Pegalo en la PC de la tienda.";
});

detectAgentDownload();
loadDevicesFromApi();
window.setInterval(() => {
  if (state.usingApi) {
    loadDevicesFromApi();
  }
}, 10000);
