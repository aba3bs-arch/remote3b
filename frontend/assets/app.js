const TOKEN_STORAGE_KEY = "am_connect_api_token";
const API_BASE_URL = (window.AM_CONNECT_CONFIG?.apiBaseUrl || "").replace(/\/$/, "");

const state = {
  devices: [],
  selectedId: null,
  filter: "",
  usingApi: false,
};

const rows = document.querySelector("#computerRows");
const searchInput = document.querySelector("#searchInput");
const dataSource = document.querySelector("#dataSource");
const usedCount = document.querySelector("#usedCount");
const onlineCount = document.querySelector("#onlineCount");
const sessionCount = document.querySelector("#sessionCount");
const offlineCount = document.querySelector("#offlineCount");
const selectedName = document.querySelector("#selectedName");
const selectedMeta = document.querySelector("#selectedMeta");
const connectButton = document.querySelector("#connectButton");
const filesButton = document.querySelector("#filesButton");
const auditButton = document.querySelector("#auditButton");
const tokenDialog = document.querySelector("#tokenDialog");
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
const authState = document.querySelector("#authState");
const adminTotal = document.querySelector("#adminTotal");
const adminOnline = document.querySelector("#adminOnline");
const adminScreens = document.querySelector("#adminScreens");
const adminTransfers = document.querySelector("#adminTransfers");
const auditEvents = document.querySelector("#auditEvents");
const exportButton = document.querySelector("#exportButton");
const addComputerButton = document.querySelector("#addComputerButton");
const addComputerDialog = document.querySelector("#addComputerDialog");
const newDeviceNameInput = document.querySelector("#newDeviceNameInput");
const newDeviceOsInput = document.querySelector("#newDeviceOsInput");
const registerDeviceButton = document.querySelector("#registerDeviceButton");
const addComputerMessage = document.querySelector("#addComputerMessage");
const installCommandInput = document.querySelector("#installCommandInput");
const copyInstallButton = document.querySelector("#copyInstallButton");

function statusLabel(device) {
  if (device.in_session) {
    return "En sesion";
  }
  return device.is_online ? "En linea" : "Sin conexion";
}

function statusClass(device) {
  if (device.in_session) {
    return "session";
  }
  return device.is_online ? "online" : "offline";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatLastSeen(device) {
  if (!device.last_seen) {
    return "Sin actividad registrada";
  }

  if (device.last_seen.startsWith("Hace") || device.last_seen.includes(",")) {
    return device.last_seen;
  }

  const date = new Date(device.last_seen);
  if (Number.isNaN(date.getTime())) {
    return device.last_seen;
  }

  return new Intl.DateTimeFormat("es", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function normalizeApiDevice(device) {
  return {
    device_id: device.device_id,
    device_name: device.device_name || device.device_id,
    os: device.os || "Desconocido",
    is_online: Boolean(device.is_online),
    in_session: Boolean(device.in_session),
    last_seen: device.last_seen || device.created_at,
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
        "El frontend esta recibiendo HTML en vez de JSON. Configura AM_CONNECT_API_BASE_URL en Netlify con la URL de Render y redeploy."
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

  return state.devices.filter((device) => {
    return [device.device_name, device.os, statusLabel(device), formatLastSeen(device)]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

function renderRows() {
  const devices = filteredDevices();
  rows.innerHTML = "";

  if (devices.length === 0) {
    const emptyRow = document.createElement("tr");
    emptyRow.innerHTML = '<td colspan="4">No hay equipos todavia. Inicia sesion y usa Agregar equipo para conectar una tienda.</td>';
    rows.appendChild(emptyRow);
    return;
  }

  devices.forEach((device) => {
    const row = document.createElement("tr");
    const os = escapeHtml(device.os);
    const name = escapeHtml(device.device_name);
    const status = escapeHtml(statusLabel(device));
    const lastSeen = escapeHtml(formatLastSeen(device));
    row.className = device.device_id === state.selectedId ? "selected" : "";
    row.innerHTML = `
      <td>
        <span class="computer-name">
          <span class="os-icon">${os.slice(0, 1).toUpperCase()}</span>
          ${name}
        </span>
      </td>
      <td>
        <div class="status-actions">
          <button class="connect-small" type="button" ${device.is_online ? "" : "disabled"}>Conectar</button>
          <span class="status ${statusClass(device)}">${status}</span>
        </div>
      </td>
      <td>${lastSeen}</td>
      <td><button class="cloud-action" type="button" aria-label="Backup">☁</button></td>
    `;

    row.addEventListener("click", () => selectDevice(device.device_id));
    row.querySelector(".connect-small").addEventListener("click", (event) => {
      event.stopPropagation();
      selectDevice(device.device_id);
      openRemoteSession(device);
    });
    rows.appendChild(row);
  });
}

function renderSummary() {
  usedCount.textContent = state.devices.length;
  onlineCount.textContent = state.devices.filter((device) => device.is_online).length;
  sessionCount.textContent = state.devices.filter((device) => device.in_session).length;
  offlineCount.textContent = state.devices.filter((device) => !device.is_online).length;
}

function renderSelected() {
  const device = state.devices.find((item) => item.device_id === state.selectedId);
  const hasDevice = Boolean(device);
  selectedName.textContent = hasDevice ? device.device_name : "Selecciona un equipo";
  selectedMeta.textContent = hasDevice
    ? `${statusLabel(device)} · ${device.os} · Ultimo acceso: ${formatLastSeen(device)}`
    : "Veras aqui los detalles de la sesion y acciones seguras.";

  connectButton.disabled = !hasDevice || !device.is_online;
  filesButton.disabled = !hasDevice;
  auditButton.disabled = !hasDevice;
}

function render() {
  renderSummary();
  renderRows();
  renderSelected();
}

function selectDevice(deviceId) {
  state.selectedId = deviceId;
  render();
}

function openRemoteSession(device) {
  if (!device.is_online) {
    window.alert("El equipo esta sin conexion. Intenta de nuevo cuando el agente autorizado este en linea.");
    return;
  }

  const hasConsent = window.confirm(
    `Confirma que tienes autorizacion para iniciar sesion en ${device.device_name}.`
  );

  if (!hasConsent) {
    return;
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
    state.devices = [];
    state.usingApi = false;
    dataSource.textContent = "Inicia sesion para ver las computadoras de tus tiendas.";
    authState.textContent = "Sin autenticacion. Crea un usuario o inicia sesion para administrar tus tiendas.";
    renderAdminSummary(null);
    render();
    if (tokenDialog && !tokenDialog.open) {
      tokenDialog.showModal();
    }
    return;
  }

  try {
    const payload = await apiRequest("/api/devices");
    state.devices = (payload.devices || []).map(normalizeApiDevice);
    state.usingApi = true;
    dataSource.textContent = state.devices.length
      ? `Mostrando ${state.devices.length} equipos desde tu servidor (sin suscripcion).`
      : "No hay equipos. Usa Agregar equipo y corre el instalador en la PC de la tienda.";
    authState.textContent = "Sesion activa. Panel administrativo sincronizado con la API.";
    await loadAdminSummary();
  } catch (error) {
    state.usingApi = false;
    dataSource.textContent = `No se pudo cargar la API (${error.message}).`;
    authState.textContent = `No se pudo cargar la API (${error.message}).`;
    if (!state.devices.length) {
      renderAdminSummary(null);
    }
  }

  const previousSelected = state.selectedId;
  state.selectedId = state.devices.some((device) => device.device_id === previousSelected)
    ? previousSelected
    : state.devices[0]?.device_id || null;
  render();
}

function renderAdminSummary(summary) {
  adminTotal.textContent = summary?.total_devices ?? 0;
  adminOnline.textContent = summary?.online_devices ?? 0;
  adminScreens.textContent = summary?.stored_screenshots ?? 0;
  adminTransfers.textContent = summary?.file_transfers ?? 0;

  auditEvents.innerHTML = "";
  const events = summary?.recent_events || [];
  if (events.length === 0) {
    const item = document.createElement("li");
    item.textContent = "Sin eventos recientes.";
    auditEvents.appendChild(item);
    return;
  }

  events.forEach((event) => {
    const item = document.createElement("li");
    item.textContent = `${event.timestamp} · ${event.action}${event.device_id ? ` · ${event.device_id}` : ""}`;
    auditEvents.appendChild(item);
  });
}

async function loadAdminSummary() {
  try {
    const payload = await apiRequest("/api/admin/summary");
    renderAdminSummary(payload.summary);
  } catch (error) {
    renderAdminSummary(null);
    authState.textContent = `No se pudo cargar administracion (${error.message}).`;
  }
}

async function loginWithCredentials() {
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  const totp = totpInput.value.trim();

  if (!username || !password) {
    authMessage.textContent = "Escribe usuario y contrasena.";
    return;
  }

  authMessage.textContent = "Autenticando...";
  try {
    const payload = await apiRequest("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        password,
        totp_code: totp || null,
      }),
    });

    window.localStorage.setItem(TOKEN_STORAGE_KEY, payload.access_token);
    tokenInput.value = payload.access_token;
    passwordInput.value = "";
    totpInput.value = "";
    authMessage.textContent = `Sesion iniciada como ${payload.user.username}.`;
    tokenDialog.close();
    await loadDevicesFromApi();
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

  authMessage.textContent = "Creando usuario...";
  try {
    const payload = await apiRequest("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, email, password }),
    });

    authMessage.textContent = `Usuario ${payload.username} creado. Ahora inicia sesion.`;
  } catch (error) {
    authMessage.textContent = `No se pudo crear usuario: ${error.message}`;
  }
}

function exportDevices() {
  const header = ["Nombre", "Estado", "Ultimo acceso", "Sistema"];
  const lines = filteredDevices().map((device) => [
    device.device_name,
    statusLabel(device),
    formatLastSeen(device),
    device.os,
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

searchInput.addEventListener("input", (event) => {
  state.filter = event.target.value;
  renderRows();
});

tokenButton.addEventListener("click", () => {
  tokenInput.value = window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  tokenDialog.showModal();
});

registerButton.addEventListener("click", registerUser);
tokenDialog.querySelector("form").addEventListener("submit", (event) => {
  if (event.submitter && event.submitter.value === "cancel") {
    return;
  }
  event.preventDefault();
  loginWithCredentials();
});

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

connectButton.addEventListener("click", () => {
  const device = state.devices.find((item) => item.device_id === state.selectedId);
  if (device) {
    openRemoteSession(device);
  }
});

filesButton.addEventListener("click", () => {
  const device = state.devices.find((item) => item.device_id === state.selectedId);
  if (device) {
    const query = new URLSearchParams({
      device: device.device_id,
      name: device.device_name,
      panel: "files",
    });
    window.location.assign(`/session?${query.toString()}`);
  }
});

auditButton.addEventListener("click", () => {
  loadAdminSummary();
});

exportButton.addEventListener("click", exportDevices);

function serverOrigin() {
  return API_BASE_URL || window.location.origin;
}

function buildInstallCommand(device) {
  const api = serverOrigin();
  const name = String(device.device_name || "").replaceAll('"', "'");
  return [
    `$Api="${api}"`,
    `$Id="${device.device_id}"`,
    `$Tok="${device.device_token}"`,
    `$Name="${name}"`,
    `irm "$Api/install/windows.ps1" -OutFile "$env:TEMP\\am-connect-install.ps1"`,
    `powershell -ExecutionPolicy Bypass -File "$env:TEMP\\am-connect-install.ps1" -ServerUrl $Api -DeviceId $Id -DeviceToken $Tok -DeviceName $Name`,
  ].join("\n");
}

async function registerStoreComputer() {
  const deviceName = newDeviceNameInput.value.trim();
  const osName = (newDeviceOsInput.value || "Windows").trim();
  if (!deviceName) {
    addComputerMessage.textContent = "Escribe el nombre de la tienda, por ejemplo 3B7 Del Valle.";
    return;
  }
  if (!window.localStorage.getItem(TOKEN_STORAGE_KEY)) {
    addComputerMessage.textContent = "Primero inicia sesion.";
    addComputerDialog.close();
    tokenDialog.showModal();
    return;
  }

  addComputerMessage.textContent = "Registrando equipo...";
  try {
    const payload = await apiRequest("/api/devices/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_name: deviceName, os: osName }),
    });
    installCommandInput.value = buildInstallCommand(payload);
    addComputerMessage.textContent =
      "Equipo registrado. Copia el comando y pegalo en PowerShell de la computadora de la tienda. El agente queda Always-ON al iniciar Windows.";
    await loadDevicesFromApi();
  } catch (error) {
    addComputerMessage.textContent = `No se pudo registrar: ${error.message}`;
  }
}

addComputerButton.addEventListener("click", () => {
  if (!window.localStorage.getItem(TOKEN_STORAGE_KEY)) {
    tokenDialog.showModal();
    authMessage.textContent = "Inicia sesion para agregar una computadora de tienda.";
    return;
  }
  addComputerMessage.textContent = "";
  installCommandInput.value = "";
  addComputerDialog.showModal();
});

registerDeviceButton.addEventListener("click", registerStoreComputer);

copyInstallButton.addEventListener("click", async () => {
  const command = installCommandInput.value.trim();
  if (!command) {
    addComputerMessage.textContent = "Registra el equipo primero para generar el comando.";
    return;
  }
  try {
    await navigator.clipboard.writeText(command);
    addComputerMessage.textContent = "Comando copiado. Pegalo en PowerShell de la tienda.";
  } catch (error) {
    installCommandInput.select();
    addComputerMessage.textContent = "No se pudo copiar automaticamente. Selecciona el texto y copia con Ctrl+C.";
  }
});

window.setInterval(() => {
  if (window.localStorage.getItem(TOKEN_STORAGE_KEY)) {
    loadDevicesFromApi();
  }
}, 5000);

loadDevicesFromApi();
