const TOKEN_STORAGE_KEY = "am_connect_api_token";
const API_BASE_URL = (window.AM_CONNECT_CONFIG?.apiBaseUrl || "").replace(/\/$/, "");

const sampleDevices = [
  {
    device_id: "device_001",
    device_name: "3B Fusion",
    os: "Windows",
    is_online: true,
    last_accessed: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
  },
  {
    device_id: "device_002",
    device_name: "3B10 ElMezquite",
    os: "Windows",
    is_online: true,
    last_accessed: new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString(),
  },
  {
    device_id: "device_003",
    device_name: "3B2 pueblo nuevo",
    os: "Windows",
    is_online: false,
    connection_error: "Fallo de conexion",
    last_accessed: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    device_id: "device_004",
    device_name: "3B5 Lomas Dos",
    os: "Windows",
    is_online: true,
    last_accessed: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    device_id: "device_005",
    device_name: "3B6 Soli",
    os: "Windows",
    is_online: false,
    connection_error: "Fallo de conexion",
    last_accessed: new Date(Date.now() - 18 * 60 * 60 * 1000).toISOString(),
  },
  {
    device_id: "device_006",
    device_name: "3B7 Del Valle",
    os: "Windows",
    is_online: true,
    last_accessed: new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    device_id: "device_007",
    device_name: "3B9 B. Aires",
    os: "Windows",
    is_online: true,
  },
  {
    device_id: "device_008",
    device_name: "EastTexas",
    os: "Windows",
    is_online: false,
  },
  {
    device_id: "device_009",
    device_name: "TabletAcacia",
    os: "Windows",
    is_online: false,
  },
];

const state = {
  devices: [],
  selectedId: null,
  filter: "",
  usingApi: false,
  username: "",
};

const computerList = document.querySelector("#computerList");
const recentList = document.querySelector("#recentList");
const searchInput = document.querySelector("#searchInput");
const dataSource = document.querySelector("#dataSource");
const usedCount = document.querySelector("#usedCount");
const recentCount = document.querySelector("#recentCount");
const tokenDialog = document.querySelector("#tokenDialog");
const addDialog = document.querySelector("#addDialog");
const helpDialog = document.querySelector("#helpDialog");
const tokenButton = document.querySelector("#accountButton");
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

function windowsIconSvg(isOnline) {
  const fill = isOnline ? "#00adef" : "#9aa4ab";
  return `
    <svg class="windows-icon ${isOnline ? "" : "offline"}" viewBox="0 0 88 88" aria-hidden="true">
      <path fill="${fill}" d="M0 12.5 36 7.6v33.2H0zm40-6.2L88 0v40.4H40zM0 47.2h36v33.2L0 75.4zm40 .4h48V88l-48-7.2z"/>
    </svg>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeApiDevice(device) {
  return {
    device_id: device.device_id,
    device_name: device.device_name || device.device_id,
    os: device.os || "Windows",
    is_online: Boolean(device.is_online),
    in_session: Boolean(device.in_session),
    last_seen: device.last_seen,
    last_accessed: device.last_accessed,
    connection_error: device.connection_error,
  };
}

async function apiRequest(url, options = {}) {
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  const headers = {
    ...(options.headers || {}),
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${url}`, {
    ...options,
    headers,
  });

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const text = await response.text();
    if (text.trim().startsWith("<!DOCTYPE") || text.trim().startsWith("<html")) {
      throw new Error(
        "El frontend esta recibiendo HTML en vez de JSON. Configura AM_CONNECT_API_BASE_URL."
      );
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

function recentDevices() {
  return filteredDevices()
    .filter((device) => device.last_accessed)
    .sort((a, b) => new Date(b.last_accessed) - new Date(a.last_accessed))
    .slice(0, 5);
}

function renderItem(device) {
  const item = document.createElement("li");
  item.className = `computer-item${device.device_id === state.selectedId ? " selected" : ""}`;
  const failure = !device.is_online ? device.connection_error || "Fallo de conexion" : "";
  item.innerHTML = `
    <span class="os-badge">
      ${windowsIconSvg(device.is_online)}
      ${device.is_online ? '<span class="status-dot"></span>' : ""}
    </span>
    <span class="computer-copy">
      <span class="computer-name">${escapeHtml(device.device_name)}</span>
      ${failure ? `<div class="failure-text">${escapeHtml(failure)}</div>` : ""}
    </span>
    <button class="connect-inline" type="button" ${device.is_online ? "" : "disabled"}>Conectar</button>
  `;
  item.addEventListener("click", () => {
    state.selectedId = device.device_id;
    render();
  });
  item.addEventListener("dblclick", () => openRemoteSession(device));
  item.querySelector(".connect-inline").addEventListener("click", (event) => {
    event.stopPropagation();
    openRemoteSession(device);
  });
  return item;
}

function renderList(target, devices, emptyText) {
  target.innerHTML = "";
  if (devices.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty-row";
    empty.textContent = emptyText;
    target.appendChild(empty);
    return;
  }
  devices.forEach((device) => target.appendChild(renderItem(device)));
}

function render() {
  const devices = filteredDevices();
  const recents = recentDevices();
  usedCount.textContent = state.devices.length;
  recentCount.textContent = recents.length;
  renderList(recentList, recents, "Aun no hay sesiones recientes.");
  renderList(computerList, devices, "No hay computadoras. Agrega la PC de una tienda.");
  if (state.username) {
    accountButton.textContent = state.username.slice(0, 1).toUpperCase();
  }
}

function openRemoteSession(device) {
  if (!device.is_online) {
    window.alert("El equipo esta sin conexion. Instala el agente Always-ON en esa PC de tienda.");
    return;
  }

  const hasConsent = window.confirm(
    `Confirma que tienes autorizacion para iniciar sesion en ${device.device_name}.`
  );
  if (!hasConsent) {
    return;
  }

  if (state.usingApi) {
    apiRequest(`/api/devices/${encodeURIComponent(device.device_id)}/access`, { method: "POST" }).catch(() => {});
  }

  const query = new URLSearchParams({
    device: device.device_id,
    name: device.device_name,
  });
  window.location.assign(`/session?${query.toString()}`);
}

async function loadDevicesFromApi() {
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  if (!token) {
    state.devices = sampleDevices;
    state.usingApi = false;
    state.username = "";
    dataSource.textContent = "Mostrando ejemplo de tiendas. Inicia sesion para ver tus PCs reales.";
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
        : `Mostrando ${state.devices.length} computadoras Always-ON.`;
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
    const params = new URLSearchParams({
      device_name: name,
      os: newDeviceOs.value,
    });
    const created = await apiRequest(`/api/devices/register?${params.toString()}`, { method: "POST" });
    const installer = await apiRequest(`/api/devices/${encodeURIComponent(created.device_id)}/installer`);
    installerCommand.value = installer.command;
    addMessage.textContent = `${name} registrada. Copia el comando y pegalo en PowerShell de esa PC.`;
    await loadDevicesFromApi();
  } catch (error) {
    addMessage.textContent = `No se pudo registrar: ${error.message}`;
  }
}

function setAlwaysOn(enabled) {
  document.querySelector("#alwaysOnView").hidden = !enabled;
  document.querySelector("#attendedView").hidden = enabled;
  document.querySelector("#modeAlwaysOn").classList.toggle("is-active", enabled);
  document.querySelector("#modeAttended").classList.toggle("is-active", !enabled);
}

searchInput.addEventListener("input", (event) => {
  state.filter = event.target.value;
  render();
});

document.querySelector("#refreshButton").addEventListener("click", loadDevicesFromApi);
document.querySelector("#addComputerButton").addEventListener("click", () => {
  if (!requireAuthForAction()) {
    return;
  }
  addMessage.textContent = "";
  installerCommand.value = "";
  addDialog.showModal();
});
document.querySelector("#configureNowButton").addEventListener("click", () => {
  if (!requireAuthForAction()) {
    return;
  }
  newDeviceName.value = newDeviceName.value || window.location.hostname || "Esta computadora";
  addDialog.showModal();
});
document.querySelector("#helpButton").addEventListener("click", () => helpDialog.showModal());
document.querySelector("#settingsButton").addEventListener("click", () => {
  tokenInput.value = window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  tokenDialog.showModal();
});
document.querySelector("#modeAlwaysOn").addEventListener("click", () => setAlwaysOn(true));
document.querySelector("#modeAttended").addEventListener("click", () => setAlwaysOn(false));
document.querySelector("#attendedBackButton").addEventListener("click", () => setAlwaysOn(true));
document.querySelector("#recentToggle").addEventListener("click", () => {
  const expanded = document.querySelector("#recentToggle").getAttribute("aria-expanded") === "true";
  document.querySelector("#recentToggle").setAttribute("aria-expanded", String(!expanded));
  recentList.hidden = expanded;
});
document.querySelector("#allToggle").addEventListener("click", () => {
  const expanded = document.querySelector("#allToggle").getAttribute("aria-expanded") === "true";
  document.querySelector("#allToggle").setAttribute("aria-expanded", String(!expanded));
  computerList.hidden = expanded;
});

tokenButton.addEventListener("click", () => {
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
    addMessage.textContent = "Primero registra la computadora para generar el comando.";
    return;
  }
  await navigator.clipboard.writeText(installerCommand.value);
  addMessage.textContent = "Comando copiado. Pegalo en PowerShell de la PC de la tienda.";
});

loadDevicesFromApi();
window.setInterval(() => {
  if (state.usingApi) {
    loadDevicesFromApi();
  }
}, 10000);
