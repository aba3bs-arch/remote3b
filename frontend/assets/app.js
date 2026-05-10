const sampleDevices = [
  {
    device_id: "device_001",
    device_name: "3B Fusion",
    os: "Windows",
    is_online: true,
    in_session: true,
    last_seen: "Hace 3 minutos",
  },
  {
    device_id: "device_002",
    device_name: "3B10 ElMezquite",
    os: "Windows",
    is_online: true,
    in_session: false,
    last_seen: "Hace 8 horas",
  },
  {
    device_id: "device_003",
    device_name: "3B2 pueblo nuevo",
    os: "Windows",
    is_online: true,
    in_session: false,
    last_seen: "Hace 3 dias",
  },
  {
    device_id: "device_004",
    device_name: "3B5 Lomas Dos",
    os: "Windows",
    is_online: true,
    in_session: false,
    last_seen: "Hace 3 dias",
  },
  {
    device_id: "device_005",
    device_name: "3B6 Soli",
    os: "Windows",
    is_online: true,
    in_session: false,
    last_seen: "Hace 18 horas",
  },
  {
    device_id: "device_006",
    device_name: "3B7 Del Valle",
    os: "Windows",
    is_online: true,
    in_session: false,
    last_seen: "Hace 4 dias",
  },
  {
    device_id: "device_007",
    device_name: "3B9 B. Aires",
    os: "Windows",
    is_online: true,
    in_session: false,
    last_seen: "Hace 5 dias",
  },
  {
    device_id: "device_008",
    device_name: "EastTexas",
    os: "Windows",
    is_online: false,
    in_session: false,
    last_seen: "Hace 9 horas",
  },
  {
    device_id: "device_009",
    device_name: "TabletAcacia",
    os: "Windows",
    is_online: false,
    in_session: false,
    last_seen: "12 Nov 2024, 14:38:30",
  },
];

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
const exportButton = document.querySelector("#exportButton");

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
    emptyRow.innerHTML = '<td colspan="4">No se encontraron equipos.</td>';
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
  const token = window.localStorage.getItem("remote3b_api_token");
  if (!token) {
    state.devices = sampleDevices;
    state.usingApi = false;
    dataSource.textContent = "Mostrando datos de ejemplo. Guarda un token para cargar tu API.";
    render();
    return;
  }

  try {
    const response = await fetch("/api/devices", {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    state.devices = (payload.devices || []).map(normalizeApiDevice);
    state.usingApi = true;
    dataSource.textContent = `Mostrando ${state.devices.length} equipos desde la API.`;
  } catch (error) {
    state.devices = sampleDevices;
    state.usingApi = false;
    dataSource.textContent = `No se pudo cargar la API (${error.message}). Mostrando datos de ejemplo.`;
  }

  state.selectedId = state.devices[0]?.device_id || null;
  render();
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
  link.download = "remote3b-computadoras.csv";
  link.click();
  URL.revokeObjectURL(url);
}

searchInput.addEventListener("input", (event) => {
  state.filter = event.target.value;
  renderRows();
});

tokenButton.addEventListener("click", () => {
  tokenInput.value = window.localStorage.getItem("remote3b_api_token") || "";
  tokenDialog.showModal();
});

saveTokenButton.addEventListener("click", () => {
  const token = tokenInput.value.trim();
  if (token) {
    window.localStorage.setItem("remote3b_api_token", token);
  } else {
    window.localStorage.removeItem("remote3b_api_token");
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
  window.alert("El modulo de archivos usara el mismo token autorizado de la API cuando se habiliten sus endpoints.");
});

auditButton.addEventListener("click", () => {
  window.alert("Los eventos de auditoria quedan asociados al usuario autenticado y al equipo seleccionado.");
});

exportButton.addEventListener("click", exportDevices);

loadDevicesFromApi();
