const params = new URLSearchParams(window.location.search);
const deviceName = params.get("name") || params.get("device") || "Equipo conectado";

const toolbar = document.querySelector("#operatorToolbar");
const collapseButton = document.querySelector("#collapseButton");
const restoreTab = document.querySelector("#restoreTab");
const deviceButton = document.querySelector("#deviceButton");
const deviceMenu = document.querySelector("#deviceMenu");
const deviceNameLabel = document.querySelector("#deviceName");

deviceNameLabel.textContent = deviceName;

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
  }
});
