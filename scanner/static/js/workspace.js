/* Unified device workspace; no direct API calls, uses existing application adapters. */
(function () {
  "use strict";
  const el = id => document.getElementById(id);
  function close() {
    el("device-workspace").hidden = true;
    el("workspace-device-details").replaceChildren();
    el("workspace-device-actions").replaceChildren();
    el("workspace-device-title").textContent = "";
  }
  function renderDevice(device, actions) {
    if (!device) return close();
    el("workspace-device-title").textContent = device.name;
    const details = el("workspace-device-details");
    details.replaceChildren();
    const fields = [["IP", device.ip], ["Модель", device.model], ["Группа", device.group], ["Площадка", device.site], ["Роль", device.role], ["Состояние", device.enabled ? "Включено" : "Отключено"]];
    for (const [label,value] of fields) {
      const dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = label; dd.textContent = value || "—";
      details.append(dt,dd);
    }
    const container = el("workspace-device-actions");
    container.replaceChildren();
    for (const action of actions) {
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = "dk-btn dk-btn--secondary dk-btn--sm";
      btn.textContent = action.label;
      btn.addEventListener("click", action.run);
      container.append(btn);
    }
    el("device-workspace").hidden = false;
    el("device-workspace").scrollIntoView({block:"nearest"});
  }
  function renderMetrics(items) {
    const root = el("workspace-kpis");
    if (!root) return;
    root.replaceChildren();
    for (const item of items) {
      const card = document.createElement("div"), value = document.createElement("div"), label = document.createElement("div");
      card.className = "dk-stat";
      value.className = "dk-stat__value";
      value.textContent = String(item.value ?? "—");
      label.className = "dk-stat__label";
      label.textContent = item.label;
      card.append(value,label); root.append(card);
    }
  }
  function syncSections() {
    document.querySelectorAll(".workspace-section").forEach(header => {
      let item = header.nextElementSibling, visible = false;
      while (item && !item.classList.contains("workspace-section")) {
        if (item.style.display !== "none" && !item.classList.contains("workspace-filtered")) visible = true;
        item = item.nextElementSibling;
      }
      header.hidden = !visible;
    });
  }
  document.addEventListener("DOMContentLoaded", () => {
    el("workspace-device-close")?.addEventListener("click", close);
    const nav = document.querySelector(".sidebar-menu");
    if (nav) new MutationObserver(syncSections).observe(nav,{subtree:true,attributes:true,attributeFilter:["style","class"]});
    syncSections();
  });
  window.BackupWorkspace = {renderDevice, renderMetrics, close, syncSections};
})();
