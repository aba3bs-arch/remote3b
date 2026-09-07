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
const fullscreenButton = document.querySelector("#fullscreenButton");
const controlToggleButton = document.querySelector("#controlToggleButton");
const snapshotButton = document.querySelector("#snapshotButton");
const changeDeviceButton = document.querySelector("#changeDeviceButton");
const endSessionButton = document.querySelector("#endSessionButton");
const infoButton = document.querySelector("#infoButton");

let liveInterval = null;
let lastScreenshotTimestamp = null;
let operatorSocket = null;
let pingTimer = null;
let controlEnabled = true;
let dragging = false;
let screenWidth = 0;
let screenHeight = 0;
let lastMoveAt = 0;

deviceNameLabel.textContent = deviceName;
remoteTabTitle.textContent = deviceName;
screenImage.classList.toggle("is-control", controlEnabled);
if (controlToggleButton) {
  controlToggleButton.classList.toggle("is-active", controlEnabled);
}

function apiOrigin() {
  return API_BASE_URL || window.location.origin;
}

function operatorWsUrl() {
  const base = new URL(apiOrigin());
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  return `${base.origin}/ws/operator/${encodeURIComponent(deviceId)}?token=${encodeURIComponent(token)}`;
}

function authHeaders() {
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
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

function applyScreenshot(payload) {
  if (!payload?.image) {
    throw new Error("Respuesta sin imagen.");
  }
  screenImage.src = `data:image/jpeg;base64,${payload.image}`;
  screenImage.hidden = false;
  remotePlaceholder.hidden = true;
  lastScreenshotTimestamp = payload.timestamp;
  screenWidth = Number(payload.screen_width || payload.width || 0);
  screenHeight = Number(payload.screen_height || payload.height || 0);
  screenStatus.textContent = `En vivo: ${payload.timestamp || "ahora"} (${payload.width || "?"}x${payload.height || "?"})`;
}

function sendOperator(message) {
  if (operatorSocket && operatorSocket.readyState === WebSocket.OPEN) {
    operatorSocket.send(JSON.stringify(message));
    return true;
  }
  return false;
}

function connectOperatorSocket() {
  if (!deviceId) {
    screenStatus.textContent = "Falta el identificador del equipo.";
    return;
  }
  if (!window.localStorage.getItem(TOKEN_STORAGE_KEY)) {
    screenStatus.textContent = "Inicia sesion en el panel antes de abrir la sesion remota.";
    return;
  }

  if (operatorSocket) {
    operatorSocket.close();
  }

  screenStatus.textContent = "Conectando con el agente de la tienda...";
  operatorSocket = new WebSocket(operatorWsUrl());

  operatorSocket.addEventListener("open", () => {
    liveToggleButton.textContent = "Stop";
    sendOperator({ type: "start_stream" });
    pingTimer = window.setInterval(() => sendOperator({ type: "ping" }), 20000);
  });

  operatorSocket.addEventListener("message", (event) => {
    let payload = {};
    try {
      payload = JSON.parse(event.data);
    } catch (error) {
      return;
    }

    if (payload.type === "screen_capture") {
      try {
        applyScreenshot(payload);
      } catch (error) {
        screenStatus.textContent = `Pantalla invalida: ${error.message}`;
      }
      return;
    }

    if (payload.type === "session_ready") {
      screenStatus.textContent = payload.is_online
        ? "Sesion lista. Esperando pantalla en vivo..."
        : "El agente de la tienda esta sin conexion. Dejalo instalado Always-ON.";
      return;
    }

    if (payload.type === "device_offline") {
      screenStatus.textContent = payload.message || "La computadora de la tienda se desconecto.";
      return;
    }

    if (payload.type === "device_online") {
      screenStatus.textContent = "La tienda volvio a conectarse. Recuperando pantalla...";
      sendOperator({ type: "start_stream" });
    }
  });

  operatorSocket.addEventListener("close", () => {
    if (pingTimer) {
      window.clearInterval(pingTimer);
      pingTimer = null;
    }
    liveToggleButton.textContent = "Live";
    if (!liveInterval) {
      screenStatus.textContent = "Conexion en vivo cerrada. Pulsa Live para reintentar.";
    }
  });
}

async function refreshScreenshot() {
  try {
    requireDevice();
    if (sendOperator({ type: "screenshot" })) {
      screenStatus.textContent = "Solicitando captura al agente autorizado...";
      return;
    }
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
    applyScreenshot(payload);
  } catch (error) {
    screenStatus.textContent = `Esperando captura: ${error.message}`;
  }
}

function setLiveMode(enabled) {
  if (enabled) {
    liveToggleButton.textContent = "Stop";
    if (!operatorSocket || operatorSocket.readyState !== WebSocket.OPEN) {
      connectOperatorSocket();
    } else {
      sendOperator({ type: "start_stream" });
    }
    if (!liveInterval) {
      liveInterval = window.setInterval(() => {
        if (!operatorSocket || operatorSocket.readyState !== WebSocket.OPEN) {
          refreshScreenshot();
        }
      }, 2500);
    }
    return;
  }

  liveToggleButton.textContent = "Live";
  sendOperator({ type: "stop_stream" });
  if (liveInterval) {
    window.clearInterval(liveInterval);
    liveInterval = null;
  }
}

function eventToRemotePoint(event) {
  const rect = screenImage.getBoundingClientRect();
  const naturalW = screenImage.naturalWidth || 1;
  const naturalH = screenImage.naturalHeight || 1;
  const scale = Math.min(rect.width / naturalW, rect.height / naturalH);
  const displayedW = naturalW * scale;
  const displayedH = naturalH * scale;
  const offsetX = (rect.width - displayedW) / 2;
  const offsetY = (rect.height - displayedH) / 2;
  const jpegX = (event.clientX - rect.left - offsetX) / displayedW * naturalW;
  const jpegY = (event.clientY - rect.top - offsetY) / displayedH * naturalH;
  const remoteW = screenWidth || naturalW;
  const remoteH = screenHeight || naturalH;
  return {
    x: Math.round(jpegX * (remoteW / naturalW)),
    y: Math.round(jpegY * (remoteH / naturalH)),
  };
}

function sendMouse(action, event, extra = {}) {
  if (!controlEnabled || screenImage.hidden) {
    return;
  }
  event.preventDefault();
  const point = eventToRemotePoint(event);
  if (point.x < 0 || point.y < 0) {
    return;
  }
  sendOperator({
    type: "input",
    kind: "mouse",
    action,
    button: event.button === 2 ? "right" : event.button === 1 ? "middle" : "left",
    ...point,
    ...extra,
  });
}

screenImage.addEventListener("mousedown", (event) => {
  dragging = true;
  screenImage.focus();
  sendMouse("down", event);
});

window.addEventListener("mouseup", (event) => {
  if (!dragging) {
    return;
  }
  dragging = false;
  sendMouse("up", event);
});

screenImage.addEventListener("mousemove", (event) => {
  if (!dragging || !controlEnabled) {
    return;
  }
  const now = Date.now();
  if (now - lastMoveAt < 40) {
    return;
  }
  lastMoveAt = now;
  sendMouse("move", event);
});

screenImage.addEventListener("wheel", (event) => {
  if (!controlEnabled) {
    return;
  }
  event.preventDefault();
  const point = eventToRemotePoint(event);
  sendOperator({
    type: "input",
    kind: "mouse",
    action: "wheel",
    delta: event.deltaY < 0 ? 1 : -1,
    ...point,
  });
}, { passive: false });

screenImage.addEventListener("contextmenu", (event) => {
  if (controlEnabled) {
    event.preventDefault();
  }
});

document.addEventListener("keydown", (event) => {
  if (!controlEnabled || document.activeElement !== screenImage) {
    return;
  }
  if (["INPUT", "TEXTAREA"].includes(event.target.tagName)) {
    return;
  }
  event.preventDefault();
  sendOperator({
    type: "input",
    kind: "key",
    action: "down",
    key: event.key,
  });
});

document.addEventListener("keyup", (event) => {
  if (!controlEnabled || document.activeElement !== screenImage) {
    return;
  }
  if (["INPUT", "TEXTAREA"].includes(event.target.tagName)) {
    return;
  }
  event.preventDefault();
  sendOperator({
    type: "input",
    kind: "key",
    action: "up",
    key: event.key,
  });
});

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
liveToggleButton.addEventListener("click", () => {
  const live = liveToggleButton.textContent === "Live";
  setLiveMode(live);
});
filePanelButton.addEventListener("click", () => showPanel(filePanel));
adminPanelButton.addEventListener("click", () => {
  showPanel(adminPanel);
  loadAdminSummary();
});
downloadFileButton.addEventListener("click", requestDownload);
uploadFileButton.addEventListener("click", requestUpload);
controlToggleButton.addEventListener("click", () => {
  controlEnabled = !controlEnabled;
  screenImage.classList.toggle("is-control", controlEnabled);
  controlToggleButton.classList.toggle("is-active", controlEnabled);
  screenStatus.textContent = controlEnabled
    ? "Control remoto activo: haz clic en la pantalla y escribe."
    : "Control remoto pausado. Solo estas viendo la pantalla.";
  if (controlEnabled) {
    screenImage.focus();
  }
});
fullscreenButton.addEventListener("click", () => {
  const stage = document.querySelector(".remote-stage");
  if (!document.fullscreenElement) {
    stage.requestFullscreen?.();
  } else {
    document.exitFullscreen?.();
  }
});
snapshotButton.addEventListener("click", () => {
  if (!screenImage.src) {
    return;
  }
  const link = document.createElement("a");
  link.href = screenImage.src;
  link.download = `${deviceName.replaceAll(" ", "-")}-captura.jpg`;
  link.click();
});
infoButton?.addEventListener("click", () => {
  window.alert(`${deviceName}\nID: ${deviceId || "desconocido"}\nControl: ${controlEnabled ? "activo" : "pausado"}`);
});
changeDeviceButton?.addEventListener("click", () => {
  window.location.assign("/dashboard");
});
endSessionButton?.addEventListener("click", () => {
  sendOperator({ type: "stop_stream" });
  window.location.assign("/dashboard");
});

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

loadLatestScreenshot();
setLiveMode(true);
