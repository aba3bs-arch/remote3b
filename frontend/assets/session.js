const params = new URLSearchParams(window.location.search);
const TOKEN_STORAGE_KEY = "am_connect_api_token";
const API_BASE_URL = (window.AM_CONNECT_CONFIG?.apiBaseUrl || "").replace(/\/$/, "");
const deviceId = params.get("device");
const deviceName = params.get("name") || params.get("device") || "Equipo conectado";
const initialPanel = params.get("panel");

const toolbar = document.querySelector("#operatorToolbar");
const collapseButton = document.querySelector("#collapseButton");
const restoreTab = document.querySelector("#restoreTab");
const deviceButton = document.querySelector("#deviceButton");
const deviceMenu = document.querySelector("#deviceMenu");
const deviceNameLabel = document.querySelector("#deviceName");
const remoteTabTitle = document.querySelector("#remoteTabTitle");
const remotePlaceholder = document.querySelector("#remotePlaceholder");
const screenImage = document.querySelector("#screenImage");
const screenStatus = document.querySelector("#screenStatus");
const refreshScreenButton = document.querySelector("#refreshScreenButton");
const liveToggleButton = document.querySelector("#liveToggleButton");
const filePanelButton = document.querySelector("#filePanelButton");
const adminPanelButton = document.querySelector("#adminPanelButton");
const filePanel = document.querySelector("#filePanel");
const adminPanel = document.querySelector("#adminPanel");
const downloadPathInput = document.querySelector("#downloadPathInput");
const downloadFileButton = document.querySelector("#downloadFileButton");
const uploadFileInput = document.querySelector("#uploadFileInput");
const uploadFileButton = document.querySelector("#uploadFileButton");
const fileTransferStatus = document.querySelector("#fileTransferStatus");
const sessionAdminTotal = document.querySelector("#sessionAdminTotal");
const sessionAdminOnline = document.querySelector("#sessionAdminOnline");
const sessionAdminScreens = document.querySelector("#sessionAdminScreens");
const sessionAdminTransfers = document.querySelector("#sessionAdminTransfers");
const sessionAuditEvents = document.querySelector("#sessionAuditEvents");

let liveInterval = null;
let lastScreenshotTimestamp = null;
let sessionSocket = null;
let controlEnabled = true;

deviceNameLabel.textContent = deviceName;
remoteTabTitle.textContent = deviceName;

function authHeaders() {
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function sessionSocketUrl() {
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  const apiBase = API_BASE_URL || window.location.origin;
  const wsBase = apiBase.replace(/^http/, "ws");
  return `${wsBase}/ws/session/${encodeURIComponent(deviceId)}?token=${encodeURIComponent(token)}`;
}

function relativePoint(event) {
  const rect = screenImage.getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width;
  const y = (event.clientY - rect.top) / rect.height;
  return {
    x: Math.min(1, Math.max(0, x)),
    y: Math.min(1, Math.max(0, y)),
  };
}

function sendInput(payload) {
  if (!controlEnabled || !deviceId) {
    return;
  }
  if (sessionSocket && sessionSocket.readyState === WebSocket.OPEN) {
    sessionSocket.send(JSON.stringify({ type: "input", ...payload }));
    return;
  }
  apiRequest(`/api/devices/${encodeURIComponent(deviceId)}/input`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).catch(() => {});
}

function showRemoteImage(image, width, height, timestamp) {
  screenImage.src = `data:image/jpeg;base64,${image}`;
  screenImage.hidden = false;
  remotePlaceholder.hidden = true;
  lastScreenshotTimestamp = timestamp;
  screenStatus.textContent = `Pantalla en vivo ${width || "?"}x${height || "?"} · control de mouse y teclado activo`;
}

function connectSessionSocket() {
  if (!deviceId) {
    screenStatus.textContent = "Falta el identificador del equipo.";
    return;
  }
  const previous = sessionSocket;
  screenStatus.textContent = "Conectando sesion remota...";
  const socket = new WebSocket(sessionSocketUrl());
  sessionSocket = socket;
  if (previous && previous.readyState < 2) {
    previous.close();
  }
  socket.addEventListener("open", () => {
    screenStatus.textContent = "Sesion conectada. Esperando pantalla de la tienda...";
  });
  socket.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "screen_capture" && data.image) {
      showRemoteImage(data.image, data.width, data.height, data.timestamp);
    } else if (data.type === "device_offline") {
      screenStatus.textContent = "El agente de la tienda se desconecto.";
    } else if (data.type === "agent_error") {
      screenStatus.textContent = data.error || "Fallo de conexion";
    }
  });
  socket.addEventListener("close", () => {
    if (sessionSocket === socket) {
      screenStatus.textContent = "La sesion se cerro. Reintentando...";
      window.setTimeout(connectSessionSocket, 2000);
    }
  });
}

async function apiRequest(url, options = {}) {
  const response = await fetch(`${API_BASE_URL}${url}`, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers || {}),
    },
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

function setToolbarVisible(isVisible) {
  toolbar.classList.toggle("is-hidden", !isVisible);
  restoreTab.hidden = isVisible;
  collapseButton.setAttribute("aria-expanded", String(isVisible));
}

collapseButton.addEventListener("click", () => {
  setToolbarVisible(false);
});

restoreTab.addEventListener("click", () => {
  setToolbarVisible(true);
});

deviceButton.addEventListener("click", () => {
  deviceMenu.hidden = !deviceMenu.hidden;
});

deviceMenu.addEventListener("click", (event) => {
  const label = event.target.textContent || "";
  if (label.includes("Cambiar equipo") || label.includes("Finalizar")) {
    window.location.assign("/");
  }
});

document.addEventListener("click", (event) => {
  if (!deviceMenu.hidden && !deviceMenu.contains(event.target) && !deviceButton.contains(event.target)) {
    deviceMenu.hidden = true;
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    deviceMenu.hidden = true;
    filePanel.hidden = true;
    adminPanel.hidden = true;
  }
});

function requireDevice() {
  if (!deviceId) {
    throw new Error("No se recibio device en la URL.");
  }
}

async function refreshScreenshot() {
  try {
    requireDevice();
    screenStatus.textContent = "Solicitando captura al agente autorizado...";
    await apiRequest(`/api/devices/${encodeURIComponent(deviceId)}/screenshot`, { method: "POST" });
    await new Promise((resolve) => setTimeout(resolve, 700));
    await loadLatestScreenshot();
  } catch (error) {
    screenStatus.textContent = `No se pudo actualizar pantalla: ${error.message}`;
  }
}

async function loadLatestScreenshot() {
  try {
    requireDevice();
    const payload = await apiRequest(`/api/devices/${encodeURIComponent(deviceId)}/screenshot/latest`);
    if (!payload.image) {
      throw new Error("Respuesta sin imagen.");
    }

    screenImage.src = `data:image/jpeg;base64,${payload.image}`;
    screenImage.hidden = false;
    remotePlaceholder.hidden = true;
    lastScreenshotTimestamp = payload.timestamp;
    screenStatus.textContent = `Pantalla actualizada: ${payload.timestamp} (${payload.width || "?"}x${payload.height || "?"})`;
  } catch (error) {
    screenStatus.textContent = `Esperando captura: ${error.message}`;
  }
}

function setLiveMode(enabled) {
  if (enabled && !liveInterval) {
    liveToggleButton.textContent = "Stop";
    refreshScreenshot();
    liveInterval = window.setInterval(refreshScreenshot, 2500);
    return;
  }

  if (!enabled && liveInterval) {
    window.clearInterval(liveInterval);
    liveInterval = null;
    liveToggleButton.textContent = "Live";
  }
}

function showPanel(panel) {
  filePanel.hidden = panel !== filePanel;
  adminPanel.hidden = panel !== adminPanel;
}

async function pollTransfer(fileId, onSuccess) {
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const payload = await apiRequest(`/api/files/${encodeURIComponent(fileId)}`);
    const transfer = payload.transfer;
    if (transfer.status === "success") {
      onSuccess(transfer);
      return;
    }
    if (transfer.status === "error") {
      throw new Error(transfer.error || "Transferencia fallida");
    }
    fileTransferStatus.textContent = `Transferencia pendiente (${attempt + 1}/12)...`;
    await new Promise((resolve) => setTimeout(resolve, 900));
  }
  throw new Error("La transferencia aun no esta lista.");
}

function downloadBase64File(transfer) {
  const byteCharacters = atob(transfer.content || "");
  const bytes = new Uint8Array(byteCharacters.length);
  for (let index = 0; index < byteCharacters.length; index += 1) {
    bytes[index] = byteCharacters.charCodeAt(index);
  }
  const blob = new Blob([bytes]);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = transfer.filename || "am-connect-download";
  link.click();
  URL.revokeObjectURL(url);
}

async function requestDownload() {
  const filepath = downloadPathInput.value.trim();
  if (!filepath) {
    fileTransferStatus.textContent = "Escribe la ruta remota que quieres descargar.";
    return;
  }

  try {
    requireDevice();
    fileTransferStatus.textContent = "Solicitando archivo al equipo...";
    const params = new URLSearchParams({ filepath });
    const payload = await apiRequest(
      `/api/devices/${encodeURIComponent(deviceId)}/files/download?${params.toString()}`,
      { method: "POST" }
    );
    await pollTransfer(payload.file_id, (transfer) => {
      downloadBase64File(transfer);
      fileTransferStatus.textContent = `Descarga lista: ${transfer.filename || filepath}`;
    });
  } catch (error) {
    fileTransferStatus.textContent = `No se pudo descargar: ${error.message}`;
  }
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function requestUpload() {
  const file = uploadFileInput.files[0];
  if (!file) {
    fileTransferStatus.textContent = "Selecciona un archivo para subir.";
    return;
  }

  try {
    requireDevice();
    fileTransferStatus.textContent = "Preparando subida...";
    const contentBase64 = await readFileAsBase64(file);
    const payload = await apiRequest(`/api/devices/${encodeURIComponent(deviceId)}/files/upload`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        filename: file.name,
        content_base64: contentBase64,
      }),
    });
    await pollTransfer(payload.upload_id, (transfer) => {
      fileTransferStatus.textContent = `Subida completada: ${transfer.saved_path || transfer.filename}`;
    });
  } catch (error) {
    fileTransferStatus.textContent = `No se pudo subir: ${error.message}`;
  }
}

function renderAdminSummary(summary) {
  sessionAdminTotal.textContent = summary?.total_devices ?? 0;
  sessionAdminOnline.textContent = summary?.online_devices ?? 0;
  sessionAdminScreens.textContent = summary?.stored_screenshots ?? 0;
  sessionAdminTransfers.textContent = summary?.file_transfers ?? 0;
  sessionAuditEvents.innerHTML = "";

  const events = summary?.recent_events || [];
  if (events.length === 0) {
    const item = document.createElement("li");
    item.textContent = "Sin eventos recientes.";
    sessionAuditEvents.appendChild(item);
    return;
  }

  events.forEach((event) => {
    const item = document.createElement("li");
    item.textContent = `${event.timestamp} · ${event.action}${event.device_id ? ` · ${event.device_id}` : ""}`;
    sessionAuditEvents.appendChild(item);
  });
}

async function loadAdminSummary() {
  try {
    const payload = await apiRequest("/api/admin/summary");
    renderAdminSummary(payload.summary);
  } catch (error) {
    renderAdminSummary(null);
    const item = document.createElement("li");
    item.textContent = `No se pudo cargar administracion: ${error.message}`;
    sessionAuditEvents.appendChild(item);
  }
}

refreshScreenButton.addEventListener("click", refreshScreenshot);
liveToggleButton.addEventListener("click", () => setLiveMode(!liveInterval));
filePanelButton.addEventListener("click", () => showPanel(filePanel));
adminPanelButton.addEventListener("click", () => {
  showPanel(adminPanel);
  loadAdminSummary();
});
downloadFileButton.addEventListener("click", requestDownload);
uploadFileButton.addEventListener("click", requestUpload);

document.querySelectorAll("[data-close-panel]").forEach((button) => {
  button.addEventListener("click", () => {
    const panel = document.querySelector(`#${button.dataset.closePanel}`);
    if (panel) {
      panel.hidden = true;
    }
  });
});

if (initialPanel === "files") {
  showPanel(filePanel);
}

screenImage.addEventListener("mousedown", (event) => {
  event.preventDefault();
  screenImage.focus();
  const point = relativePoint(event);
  sendInput({
    event: "mouse_down",
    button: event.button === 2 ? "right" : event.button === 1 ? "middle" : "left",
    x: point.x,
    y: point.y,
  });
});

screenImage.addEventListener("mouseup", (event) => {
  const point = relativePoint(event);
  sendInput({
    event: "mouse_up",
    button: event.button === 2 ? "right" : event.button === 1 ? "middle" : "left",
    x: point.x,
    y: point.y,
  });
});

screenImage.addEventListener("mousemove", (event) => {
  if (event.buttons === 0) {
    return;
  }
  const point = relativePoint(event);
  sendInput({
    event: "mouse_move",
    button: "left",
    x: point.x,
    y: point.y,
  });
});

screenImage.addEventListener("wheel", (event) => {
  event.preventDefault();
  sendInput({
    event: "scroll",
    dx: Math.sign(event.deltaX),
    dy: -Math.sign(event.deltaY),
  });
}, { passive: false });

screenImage.addEventListener("contextmenu", (event) => event.preventDefault());
screenImage.tabIndex = 0;

document.addEventListener("keydown", (event) => {
  if (filePanel.hidden === false || adminPanel.hidden === false) {
    return;
  }
  if (event.target.closest("input, textarea")) {
    return;
  }
  event.preventDefault();
  sendInput({
    event: "key_down",
    key: event.key,
  });
});

document.addEventListener("keyup", (event) => {
  if (event.target.closest("input, textarea")) {
    return;
  }
  sendInput({
    event: "key_up",
    key: event.key,
  });
});

connectSessionSocket();
loadLatestScreenshot();
