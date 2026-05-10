const params = new URLSearchParams(window.location.search);
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

deviceNameLabel.textContent = deviceName;
remoteTabTitle.textContent = deviceName;

function authHeaders() {
  const token = window.localStorage.getItem("remote3b_api_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
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
  link.download = transfer.filename || "remote3b-download";
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

loadLatestScreenshot();
