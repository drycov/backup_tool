const API = "";
let inventory = null;
let editingDeviceName = null;
let oxidizedPublicUrl = "http://localhost:8888";
let oxidizedProxyUrl = "/oxidized-proxy/nodes";
let currentUser = null;
let scanPollTimer = null;

const PAGE_TITLES = {
  dashboard: "Дашборд",
  inventory: "Инвентарь",
  scan: "Сканирование",
  oxidized: "Oxidized",
  "oxidized-ui": "Oxidized UI",
  users: "Пользователи",
};

function qs(sel) { return document.querySelector(sel); }
function qsa(sel) { return document.querySelectorAll(sel); }

function can(permission) {
  return currentUser?.permissions?.includes(permission);
}

function canAny(permissions) {
  const list = Array.isArray(permissions) ? permissions : String(permissions).split(",");
  return list.some(p => can(p.trim()));
}

function applyPermissions() {
  qsa("[data-permission]").forEach(el => {
    const allowed = can(el.dataset.permission);
    if (el.tagName === "LI") {
      el.style.display = allowed ? "" : "none";
    } else {
      el.style.display = allowed ? "" : "none";
      if (el.tagName === "BUTTON") el.disabled = !allowed;
    }
  });

  qsa("[data-permission-any]").forEach(el => {
    const allowed = canAny(el.dataset.permissionAny);
    if (el.tagName === "LI") {
      el.style.display = allowed ? "" : "none";
    } else {
      el.style.display = allowed ? "" : "none";
      if (el.tagName === "BUTTON") el.disabled = !allowed;
    }
  });

  const credCard = qs("#credentials-card");
  if (credCard) {
    credCard.style.display = can("credentials:read") || can("credentials:write") ? "" : "none";
  }
  const netsCard = qs("#networks-card");
  if (netsCard) {
    netsCard.style.display = can("inventory:write") ? "" : "none";
  }
}

function showLogin() {
  document.body.classList.add("login-page");
  document.body.classList.remove("sidebar-mini", "layout-fixed");
  qs("#login-screen").style.display = "block";
  qs("#app-layout").style.display = "none";
  currentUser = null;
}

function showApp() {
  document.body.classList.remove("login-page");
  document.body.classList.add("sidebar-mini", "layout-fixed");
  qs("#login-screen").style.display = "none";
  qs("#app-layout").style.display = "block";
  applyPermissions();
  updateNavbarUser();
}

function updateNavbarUser() {
  if (!currentUser) return;
  const roleLabels = { viewer: "Наблюдатель", operator: "Оператор", admin: "Администратор" };
  const usernameEl = qs("#navbar-username");
  const roleEl = qs("#navbar-user-role");
  if (usernameEl) usernameEl.textContent = currentUser.username;
  if (roleEl) {
    const src = currentUser.auth_source === "ldap" ? "LDAP" : "локальный";
    const lock = currentUser.role_locked ? " · роль фиксирована" : "";
    roleEl.textContent = `${roleLabels[currentUser.role] || currentUser.role} (${src}${lock})`;
  }
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...options.headers };
  const res = await fetch(`${API}${path}`, {
    credentials: "include",
    headers,
    ...options,
  });
  if (res.status === 401 && path !== "/api/auth/login") {
    showLogin();
    throw new Error("Требуется вход в систему");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

function badge(status) {
  const map = {
    online: "badge-success",
    offline: "badge-danger",
    partial: "badge-warning",
    success: "badge-success",
    no_connection: "badge-secondary",
  };
  const cls = map[status] || "badge-secondary";
  return `<span class="badge ${cls}">${status}</span>`;
}

function smallBox(value, label, bg = "bg-info", icon = "fa-server", valueClass = "") {
  const h3Class = valueClass ? ` class="${valueClass}"` : "";
  return `
    <div class="col-xl-2 col-lg-4 col-md-4 col-sm-6 col-12">
      <div class="small-box ${bg}">
        <div class="inner">
          <h3${h3Class}>${value}</h3>
          <p>${label}</p>
        </div>
        <div class="icon"><i class="fas ${icon}"></i></div>
      </div>
    </div>
  `;
}

function formatDate(d) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleString("ru-RU");
  } catch {
    return d;
  }
}

function showAlert(containerId, msg, type = "danger") {
  const el = qs(`#${containerId}`);
  if (!el) return;
  const alertType = type === "error" ? "danger" : type === "info" ? "info" : type;
  el.innerHTML = `
    <div class="alert alert-${alertType} alert-dismissible fade show" role="alert">
      ${msg}
      <button type="button" class="close" data-dismiss="alert"><span>&times;</span></button>
    </div>
  `;
  setTimeout(() => { el.innerHTML = ""; }, 5000);
}

function loadOxidizedIframe() {
  const iframe = qs("#oxidized-iframe");
  if (!iframe) return;
  const target = oxidizedProxyUrl || "/oxidized-proxy/nodes";
  if (iframe.getAttribute("src") !== target) {
    iframe.setAttribute("src", target);
  }
}

function setOxidizedLinks(url, proxyUrl) {
  oxidizedPublicUrl = url || oxidizedPublicUrl;
  if (proxyUrl) oxidizedProxyUrl = proxyUrl;
  ["link-oxidized", "link-oxidized-2", "link-oxidized-3"].forEach(id => {
    const a = qs(`#${id}`);
    if (a) a.href = oxidizedPublicUrl;
  });
  loadOxidizedIframe();
}

function setPageTitle(page) {
  const header = qs("#content-header");
  if (!header) return;
  const title = PAGE_TITLES[page] || "Backup Tools";
  header.innerHTML = `
    <div class="container-fluid">
      <div class="row mb-2">
        <div class="col-sm-6"><h1 class="m-0">${title}</h1></div>
      </div>
    </div>
  `;
}

function initNavigation() {
  qsa(".nav-page").forEach(link => {
    link.addEventListener("click", e => {
      e.preventDefault();
      qsa(".nav-page").forEach(l => l.classList.remove("active"));
      link.classList.add("active");
      const page = link.dataset.page;
      qsa(".page").forEach(p => p.classList.add("d-none"));
      const pageEl = qs(`#page-${page}`);
      if (pageEl) pageEl.classList.remove("d-none");
      setPageTitle(page);
      if (page === "oxidized") loadOxidizedNodes();
      if (page === "oxidized-ui") loadOxidizedIframe();
      if (page === "users") {
        loadUsers();
        loadRbacMatrix();
      }
      if (page === "scan") resumeScanIfRunning();
    });
  });
}

async function login(username, password) {
  const data = await api("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  currentUser = data.user;
  showApp();
  await bootstrapApp();
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch {}
  showLogin();
}

async function loadRbacMatrix() {
  const table = qs("#rbac-matrix-table tbody");
  if (!table) return;
  try {
    const data = await api("/api/auth/rbac");
    const roles = data.roles || [];
    const roleIds = roles.map(r => r.id);
    table.innerHTML = (data.permissions || []).map(perm => {
      const cells = roleIds.map(rid => {
        const role = roles.find(r => r.id === rid);
        const ok = role?.permissions?.includes(perm.id);
        return `<td class="text-center">${ok ? '<i class="fas fa-check text-success"></i>' : '<i class="fas fa-times text-muted"></i>'}</td>`;
      }).join("");
      return `<tr><td>${perm.label}<br><code class="small">${perm.id}</code></td>${cells}</tr>`;
    }).join("");
  } catch {
    table.innerHTML = `<tr><td colspan="4" class="text-muted">Нет доступа к матрице RBAC</td></tr>`;
  }
}

async function loadUsers() {
  const users = await api("/api/auth/users");
  const tbody = qs("#users-table");
  if (!users.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Нет пользователей</td></tr>`;
    return;
  }
  tbody.innerHTML = users.map(u => `
    <tr>
      <td><strong>${u.username}</strong></td>
      <td>
        <select class="form-control form-control-sm user-role-select" data-id="${u.id}" ${u.id === currentUser.id ? "disabled" : ""}>
          <option value="viewer" ${u.role === "viewer" ? "selected" : ""}>viewer</option>
          <option value="operator" ${u.role === "operator" ? "selected" : ""}>operator</option>
          <option value="admin" ${u.role === "admin" ? "selected" : ""}>admin</option>
        </select>
      </td>
      <td><span class="badge badge-${u.auth_source === "ldap" ? "info" : "secondary"}">${u.auth_source || "local"}</span></td>
      <td class="text-center">
        ${u.auth_source === "ldap" ? `<input type="checkbox" class="user-role-locked" data-id="${u.id}" ${u.role_locked ? "checked" : ""} title="Не обновлять роль из LDAP">` : "—"}
      </td>
      <td class="text-center">
        <input type="checkbox" class="user-active-check" data-id="${u.id}" ${u.is_active ? "checked" : ""} ${u.id === currentUser.id ? "disabled" : ""}>
      </td>
      <td>
        ${u.id !== currentUser.id ? `<button class="btn btn-danger btn-sm btn-delete-user" data-id="${u.id}"><i class="fas fa-trash"></i></button>` : "—"}
      </td>
    </tr>
  `).join("");

  tbody.querySelectorAll(".user-role-select").forEach(sel => {
    sel.addEventListener("change", async () => {
      await api(`/api/auth/users/${sel.dataset.id}`, {
        method: "PUT",
        body: JSON.stringify({ role: sel.value }),
      });
      showAlert("users-alert", "Роль обновлена", "success");
    });
  });

  tbody.querySelectorAll(".user-active-check").forEach(chk => {
    chk.addEventListener("change", async () => {
      await api(`/api/auth/users/${chk.dataset.id}`, {
        method: "PUT",
        body: JSON.stringify({ is_active: chk.checked }),
      });
      showAlert("users-alert", "Статус обновлён", "success");
    });
  });

  tbody.querySelectorAll(".user-role-locked").forEach(chk => {
    chk.addEventListener("change", async () => {
      await api(`/api/auth/users/${chk.dataset.id}`, {
        method: "PUT",
        body: JSON.stringify({ role_locked: chk.checked }),
      });
      showAlert("users-alert", "Фиксация роли обновлена", "success");
    });
  });

  tbody.querySelectorAll(".btn-delete-user").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm("Удалить пользователя?")) return;
      await api(`/api/auth/users/${btn.dataset.id}`, { method: "DELETE" });
      loadUsers();
    });
  });
}

async function loadHealth() {
  const health = await api("/health");
  const oxHealth = await api("/api/oxidized/health").catch(() => ({ reachable: false }));

  qs("#dashboard-stats").innerHTML = `
    <div class="col-12 stats-row">
      <div class="row">
        ${smallBox(health.inventory_devices, "Устройств", "bg-info", "fa-hdd")}
        ${smallBox(health.networks, "Подсетей", "bg-secondary", "fa-network-wired")}
        ${smallBox(oxHealth.reachable ? "OK" : "OFF", "Oxidized", oxHealth.reachable ? "bg-success" : "bg-danger", "fa-database")}
        ${smallBox(oxHealth.nodes_count || 0, "Узлов Oxidized", "bg-primary", "fa-server")}
        ${smallBox(formatDate(health.last_scan), "Последний scan", "bg-warning", "fa-clock", "text-sm")}
      </div>
    </div>
  `;
}

async function loadInventory() {
  inventory = await api("/inventory");

  const profilesEl = qs("#credential-profiles");
  const profiles = inventory.credential_profiles || [];
  const canEditCreds = can("credentials:write");
  const canViewCreds = can("credentials:read");

  profilesEl.innerHTML = profiles.map(p => `
    <form class="card card-outline card-light mb-3 credential-form" data-profile="${p.name}">
      <div class="card-body">
        <h5 class="mb-3">${p.name} <small class="text-muted">→ группа <code>${p.group_name}</code></small></h5>
        <div class="form-row">
          <div class="form-group col-md-6">
            <label>Username</label>
            <input type="text" class="form-control profile-username" value="${p.username}" ${canEditCreds ? "" : "readonly"}>
          </div>
          <div class="form-group col-md-6">
            <label>Password</label>
            <input type="password" class="form-control profile-password" value="${p.password}" ${canEditCreds ? "" : "readonly"}>
          </div>
        </div>
        ${canEditCreds ? `<button type="submit" class="btn btn-primary btn-sm"><i class="fas fa-save mr-1"></i> Сохранить ${p.name}</button>` : ""}
      </div>
    </form>
  `).join("") || (canViewCreds || canEditCreds
    ? `<p class="text-muted">Нет профилей — импортируйте network_inventory.yml</p>`
    : `<p class="text-muted">Пароли доступны только администратору</p>`);

  profilesEl.querySelectorAll(".credential-form").forEach(form => {
    if (!canEditCreds) return;
    form.addEventListener("submit", async e => {
      e.preventDefault();
      const name = form.dataset.profile;
      const username = form.querySelector(".profile-username").value;
      const password = form.querySelector(".profile-password").value;
      await api(`/inventory/credentials/${encodeURIComponent(name)}`, {
        method: "PUT",
        body: JSON.stringify({ username, password }),
      });
      showAlert("dashboard-alert", `Профиль ${name} сохранён`, "success");
    });
  });

  const netsTable = qs("#networks-table");
  const networks = inventory.networks || [];
  if (!networks.length) {
    netsTable.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Нет подсетей</td></tr>`;
  } else {
    netsTable.innerHTML = networks.map((n, idx) => `
      <tr>
        <td>${n.network}</td>
        <td>${n.group_name}</td>
        <td>${n.environment_name || "—"}</td>
        <td>${n.gateway || "—"}</td>
        <td>
          ${can("inventory:write") ? `<button class="btn btn-danger btn-sm btn-remove-network" data-idx="${idx}"><i class="fas fa-trash"></i></button>` : ""}
        </td>
      </tr>
    `).join("");

    netsTable.querySelectorAll(".btn-remove-network").forEach(btn => {
      btn.addEventListener("click", async () => {
        const idx = parseInt(btn.dataset.idx, 10);
        inventory.networks = inventory.networks.filter((_, i) => i !== idx);
        await api("/inventory", { method: "PUT", body: JSON.stringify(inventory) });
        loadInventory();
      });
    });
  }

  const tbody = qs("#devices-table");
  const devices = inventory.devices || [];
  if (!devices.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Нет устройств</td></tr>`;
    return;
  }

  tbody.innerHTML = devices.map(d => `
    <tr>
      <td><strong>${d.name}</strong></td>
      <td>${d.ip}</td>
      <td>${d.model}</td>
      <td>${d.group}</td>
      <td>${(d.ports || []).join(", ")}</td>
      <td>${d.enabled ? '<span class="badge badge-success">yes</span>' : '<span class="badge badge-secondary">no</span>'}</td>
      <td>
        ${can("inventory:devices") ? `<button class="btn btn-info btn-sm btn-edit-device" data-name="${d.name}"><i class="fas fa-edit"></i></button>` : ""}
        ${can("inventory:devices") ? `<button class="btn btn-danger btn-sm btn-delete-device" data-name="${d.name}"><i class="fas fa-trash"></i></button>` : ""}
      </td>
    </tr>
  `).join("");

  tbody.querySelectorAll(".btn-edit-device").forEach(btn => {
    btn.addEventListener("click", () => openDeviceModal(btn.dataset.name));
  });
  tbody.querySelectorAll(".btn-delete-device").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm(`Удалить ${btn.dataset.name}?`)) return;
      await api(`/inventory/devices/${encodeURIComponent(btn.dataset.name)}`, { method: "DELETE" });
      loadInventory();
      loadHealth();
    });
  });
}

function openDeviceModal(name = null) {
  editingDeviceName = name;
  const device = name ? inventory.devices.find(d => d.name === name) : null;

  qs("#device-modal-title").textContent = name ? "Изменить устройство" : "Добавить устройство";
  qs("#device-name").value = device?.name || "";
  qs("#device-name").disabled = !!name;
  qs("#device-ip").value = device?.ip || "";
  qs("#device-model").value = device?.model || "routeros";
  qs("#device-group").value = device?.group || "hex";
  qs("#device-ports").value = (device?.ports || [44333]).join(", ");
  qs("#device-enabled").value = device?.enabled ? "true" : "false";
  $("#device-modal").modal("show");
}

function closeDeviceModal() {
  $("#device-modal").modal("hide");
  editingDeviceName = null;
  qs("#device-name").disabled = false;
}

async function saveDevice() {
  const ports = qs("#device-ports").value
    .split(",")
    .map(p => parseInt(p.trim(), 10))
    .filter(p => !isNaN(p));

  const device = {
    name: qs("#device-name").value.trim(),
    ip: qs("#device-ip").value.trim(),
    model: qs("#device-model").value,
    group: qs("#device-group").value.trim() || "default",
    enabled: qs("#device-enabled").value === "true",
    ports: ports.length ? ports : [44333],
  };

  if (!device.name || !device.ip) {
    alert("Имя и IP обязательны");
    return;
  }

  if (editingDeviceName) {
    inventory.devices = inventory.devices.filter(d => d.name !== editingDeviceName);
    inventory.devices.push(device);
    await api("/inventory", { method: "PUT", body: JSON.stringify(inventory) });
  } else {
    await api("/inventory/devices", { method: "POST", body: JSON.stringify(device) });
  }

  closeDeviceModal();
  loadInventory();
  loadHealth();
}

function setScanButtonsDisabled(disabled) {
  ["btn-scan", "btn-scan-discover", "btn-quick-scan", "btn-quick-discover"].forEach(id => {
    const b = qs(`#${id}`);
    if (b) b.disabled = disabled;
  });
}

function showScanProgress(status) {
  const wrap = qs("#scan-progress-wrap");
  const bar = qs("#scan-progress-bar");
  const msg = qs("#scan-progress-msg");
  const pct = qs("#scan-progress-pct");
  if (!wrap || !bar) return;

  wrap.style.display = "block";
  const value = status.progress_pct || 0;
  bar.style.width = `${value}%`;
  bar.setAttribute("aria-valuenow", String(value));
  if (msg) msg.textContent = status.message || "Выполняется…";
  if (pct) pct.textContent = status.progress_total > 0 ? `${value}%` : "…";
}

function hideScanProgress() {
  const wrap = qs("#scan-progress-wrap");
  if (wrap) wrap.style.display = "none";
}

function stopScanPolling() {
  if (scanPollTimer) {
    clearInterval(scanPollTimer);
    scanPollTimer = null;
  }
}

async function pollScanStatus(onComplete) {
  try {
    const status = await api("/scan/status");
    if (status.status === "running") {
      showScanProgress(status);
      return;
    }

    stopScanPolling();
    setScanButtonsDisabled(false);
    hideScanProgress();

    if (status.status === "completed" && status.summary) {
      renderScanResults(status.summary);
      showAlert("scan-alert", status.message || "Сканирование завершено", "success");
      loadHealth();
      loadInventory();
    } else if (status.status === "failed") {
      showAlert("scan-alert", status.error || status.message || "Ошибка сканирования", "error");
    }

    if (onComplete) onComplete(status);
  } catch (e) {
    stopScanPolling();
    setScanButtonsDisabled(false);
    hideScanProgress();
    showAlert("scan-alert", e.message, "error");
  }
}

function startScanPolling(onComplete) {
  stopScanPolling();
  pollScanStatus(onComplete);
  scanPollTimer = setInterval(() => pollScanStatus(onComplete), 1500);
}

async function resumeScanIfRunning() {
  try {
    const status = await api("/scan/status");
    if (status.status === "running") {
      setScanButtonsDisabled(true);
      showAlert("scan-alert", status.message || "Сканирование выполняется…", "info");
      startScanPolling();
    }
  } catch {}
}

function renderScanResults(summary) {
  if (!summary) {
    qs("#scan-empty").style.display = "block";
    qs("#scan-stats").innerHTML = "";
    qs("#scan-results-table").innerHTML = "";
    return;
  }

  qs("#scan-empty").style.display = "none";
  qs("#scan-stats").innerHTML = `
    <div class="col-12 stats-row">
      <div class="row">
        ${smallBox(summary.total, "Всего", "bg-info", "fa-list")}
        ${smallBox(summary.online, "Online", "bg-success", "fa-check")}
        ${smallBox(summary.partial, "Partial", "bg-warning", "fa-exclamation-triangle")}
        ${smallBox(summary.offline, "Offline", "bg-danger", "fa-times")}
      </div>
    </div>
  `;

  qs("#scan-results-table").innerHTML = (summary.results || []).map(r => {
    const ports = (r.ports || []).map(p =>
      `<span class="mr-2"><span class="port-dot ${p.open ? "port-open" : "port-closed"}"></span>${p.port}</span>`
    ).join("");
    return `
      <tr>
        <td>${badge(r.status)}</td>
        <td>${r.name}</td>
        <td>${r.ip}</td>
        <td>${r.ping_ok ? "✓" : "✗"}</td>
        <td>${ports}</td>
        <td>${r.model}</td>
        <td>${formatDate(r.scanned_at)}</td>
      </tr>
    `;
  }).join("");
}

async function runScan(discover = false) {
  setScanButtonsDisabled(true);

  try {
    showAlert("scan-alert", discover ? "Запуск discovery и сканирования…" : "Запуск сканирования…", "info");
    await api(`/scan?discover=${discover}`, { method: "POST" });
    startScanPolling();
  } catch (e) {
    setScanButtonsDisabled(false);
    hideScanProgress();
    showAlert("scan-alert", e.message, "error");
  }
}

async function syncOxidized() {
  try {
    const res = await api("/oxidized/sync", { method: "POST" });
    showAlert("oxidized-alert", "Конфиг Oxidized обновлён", "success");
    showAlert("dashboard-alert", `HTTP source: ${res.source_url}`, "success");
    loadOxidizedNodes();
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

async function loadOxidizedNodes() {
  try {
    const health = await api("/api/oxidized/health");
    setOxidizedLinks(health.public_url);

    qs("#oxidized-stats").innerHTML = `
      <div class="col-12 stats-row">
        <div class="row">
          ${smallBox(health.reachable ? "OK" : "OFF", "Статус", health.reachable ? "bg-success" : "bg-danger", "fa-heartbeat")}
          ${smallBox(health.nodes_count, "Узлов", "bg-info", "fa-server")}
        </div>
      </div>
    `;

    if (!health.reachable) {
      showAlert("oxidized-alert", health.error || "Oxidized недоступен", "error");
      qs("#oxidized-empty").style.display = "block";
      qs("#oxidized-nodes-table").innerHTML = "";
      return;
    }

    const nodes = await api("/api/oxidized/nodes");
    qs("#oxidized-empty").style.display = nodes.length ? "none" : "block";

    qs("#oxidized-nodes-table").innerHTML = nodes.map(n => {
      const last = n.last || {};
      const status = last.status || "unknown";
      return `
        <tr>
          <td><strong>${n.name}</strong></td>
          <td>${n.ip || "—"}</td>
          <td>${n.model || "—"}</td>
          <td>${n.group || "—"}</td>
          <td>${formatDate(last.time)}</td>
          <td>${badge(status === "success" ? "success" : status)}</td>
          <td>
            <button class="btn btn-info btn-sm btn-show-config" data-name="${n.name}"><i class="fas fa-file-alt"></i></button>
            ${can("oxidized:write") ? `<button class="btn btn-primary btn-sm btn-fetch-config" data-name="${n.name}"><i class="fas fa-download"></i></button>` : ""}
          </td>
        </tr>
      `;
    }).join("");

    qs("#oxidized-nodes-table").querySelectorAll(".btn-show-config").forEach(btn => {
      btn.addEventListener("click", () => showNodeConfig(btn.dataset.name));
    });
    qs("#oxidized-nodes-table").querySelectorAll(".btn-fetch-config").forEach(btn => {
      btn.addEventListener("click", () => fetchNodeConfig(btn.dataset.name));
    });
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

async function showNodeConfig(name) {
  try {
    const data = await api(`/api/oxidized/nodes/${encodeURIComponent(name)}`);
    qs("#config-card").style.display = "block";
    qs("#config-node-name").textContent = name;
    const content = typeof data === "string" ? data : (data.full || JSON.stringify(data, null, 2));
    qs("#config-content").textContent = content || "Пустой конфиг";
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

async function fetchNodeConfig(name) {
  try {
    showAlert("oxidized-alert", `Fetch ${name}…`, "info");
    await api(`/api/oxidized/nodes/${encodeURIComponent(name)}/fetch`, { method: "POST" });
    showAlert("oxidized-alert", `Fetch ${name} выполнен`, "success");
    loadOxidizedNodes();
    showNodeConfig(name);
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

function bindEvents() {
  const addDeviceBtn = qs("#btn-add-device");
  if (addDeviceBtn) addDeviceBtn.addEventListener("click", () => openDeviceModal());

  qs("#device-form").addEventListener("submit", e => {
    e.preventDefault();
    saveDevice();
  });

  qs("#btn-import-network")?.addEventListener("click", async () => {
    try {
      await api("/inventory/import-network", { method: "POST" });
      showAlert("dashboard-alert", "network_inventory.yml импортирован", "success");
      loadInventory();
      loadHealth();
    } catch (e) {
      showAlert("dashboard-alert", e.message, "error");
    }
  });

  const addNetworkBtn = qs("#btn-add-network");
  if (addNetworkBtn) {
    addNetworkBtn.addEventListener("click", async () => {
      const net = qs("#network-input").value.trim();
      const group = qs("#network-group").value;
      if (!net) return;
      inventory = await api("/inventory");
      inventory.networks.push({
        network: net,
        group_name: group,
        environment_name: null,
        gateway: null,
      });
      await api("/inventory", { method: "PUT", body: JSON.stringify(inventory) });
      qs("#network-input").value = "";
      loadInventory();
    });
  }

  qs("#btn-scan")?.addEventListener("click", () => runScan(false));
  qs("#btn-scan-discover")?.addEventListener("click", () => runScan(true));
  qs("#btn-quick-scan")?.addEventListener("click", () => runScan(false));
  qs("#btn-quick-discover")?.addEventListener("click", () => runScan(true));
  qs("#btn-quick-sync")?.addEventListener("click", syncOxidized);
  qs("#btn-sync-oxidized")?.addEventListener("click", syncOxidized);
  qs("#btn-refresh-oxidized")?.addEventListener("click", loadOxidizedNodes);
  qs("#btn-logout").addEventListener("click", e => {
    e.preventDefault();
    logout();
  });

  qs("#login-form").addEventListener("submit", async e => {
    e.preventDefault();
    try {
      await login(qs("#login-username").value.trim(), qs("#login-password").value);
    } catch (err) {
      showAlert("login-alert", err.message, "error");
    }
  });

  qs("#user-create-form")?.addEventListener("submit", async e => {
    e.preventDefault();
    try {
      await api("/api/auth/users", {
        method: "POST",
        body: JSON.stringify({
          username: qs("#new-user-username").value.trim(),
          password: qs("#new-user-password").value,
          role: qs("#new-user-role").value,
        }),
      });
      qs("#new-user-username").value = "";
      qs("#new-user-password").value = "";
      showAlert("users-alert", "Пользователь создан", "success");
      loadUsers();
    } catch (err) {
      showAlert("users-alert", err.message, "error");
    }
  });
}

async function bootstrapApp() {
  try {
    const uiConfig = await api("/api/ui/config");
    setOxidizedLinks(uiConfig.oxidized_public_url, uiConfig.oxidized_proxy_url);
    const ldapHint = qs("#login-ldap-hint");
    if (ldapHint && uiConfig.auth?.ldap_enabled) {
      ldapHint.style.display = "block";
    }
  } catch {}

  setPageTitle("dashboard");
  await loadHealth();
  await loadInventory();

  const latest = await api("/scan/latest").catch(() => null);
  renderScanResults(latest);
  await resumeScanIfRunning();
}

async function init() {
  initNavigation();
  bindEvents();

  try {
    const uiConfig = await api("/api/ui/config").catch(() => ({}));
    const ldapHint = qs("#login-ldap-hint");
    if (ldapHint && uiConfig.auth?.ldap_enabled) {
      ldapHint.style.display = "block";
    }
  } catch {}

  try {
    currentUser = await api("/api/auth/me");
    showApp();
    await bootstrapApp();
  } catch {
    showLogin();
  }
}

init();
