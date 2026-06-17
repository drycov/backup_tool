const API = "";
let inventory = null;
let editingDeviceName = null;
let oxidizedPublicUrl = "http://localhost:8888";
let oxidizedProxyUrl = "/oxidized-proxy/nodes";
let oxidizedEngine = "python";
let oxidizedModels = ["routeros"];
const OXIDIZED_PROXY_PREFIX = "/oxidized-proxy";
let currentUser = null;
let scanPollTimer = null;
let globalSearchQuery = "";
let lastScanSummary = null;
let oxidizedNodesCache = [];
let usersCache = [];
let oxidizedLogsTimer = null;
let oxidizedLogsStickToBottom = true;
let oxidizedSettingsCache = null;

const SCAN_PHASE_LABELS = {
  idle: "Ожидание",
  discovery: "Discovery",
  scan: "Сканирование",
  rename: "Имена",
  done: "Готово",
  failed: "Ошибка",
};

const PAGE_TITLES = {
  dashboard: "Дашборд",
  inventory: "Инвентарь",
  scan: "Сканирование",
  oxidized: "Oxidized",
  "oxidized-ui": "Oxidized UI",
  settings: "Настройки",
  users: "Пользователи",
};

function qs(sel) { return document.querySelector(sel); }
function qsa(sel) { return document.querySelectorAll(sel); }

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function searchTokens(query) {
  return query.trim().toLowerCase().split(/\s+/).filter(Boolean);
}

function matchesSearch(values, query) {
  const tokens = searchTokens(query);
  if (!tokens.length) return true;
  const haystack = values
    .flatMap(v => (v == null ? [] : [String(v)]))
    .join(" ")
    .toLowerCase();
  return tokens.every(token => haystack.includes(token));
}

function updateSearchCountBadge(shown, total, badgeId) {
  const badge = qs(`#${badgeId}`);
  const navCount = qs("#global-search-count");
  const q = globalSearchQuery.trim();

  if (badge) {
    if (q && total > 0) {
      badge.style.display = "inline";
      badge.textContent = shown === total ? String(total) : `${shown} / ${total}`;
    } else {
      badge.style.display = "none";
    }
  }

  if (navCount) {
    if (q && total > 0) {
      navCount.classList.remove("d-none");
      navCount.textContent = shown === total ? `${total}` : `${shown}/${total}`;
    } else {
      navCount.classList.add("d-none");
      navCount.textContent = "";
    }
  }
}

function applyGlobalSearch() {
  renderNetworksTable();
  renderDevicesTable();
  if (lastScanSummary) renderScanResults(lastScanSummary);
  if (oxidizedNodesCache.length) renderOxidizedNodesTable(oxidizedNodesCache);
  if (!qs("#page-oxidized")?.classList.contains("d-none")) {
    refreshOxidizedLogBadge();
    if ($("#oxidized-logs-modal").hasClass("show")) loadOxidizedLogs();
  }
  renderSettingsCredentials();
  if (usersCache.length) renderUsersTable(usersCache);
}

function setGlobalSearch(query) {
  globalSearchQuery = query;
  const input = qs("#global-search");
  if (input && input.value !== query) input.value = query;
  applyGlobalSearch();
}

function clearGlobalSearch() {
  setGlobalSearch("");
}

function bindGlobalSearch() {
  const input = qs("#global-search");
  const clearBtn = qs("#global-search-clear");
  if (!input) return;

  let debounceTimer = null;
  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => setGlobalSearch(input.value), 150);
  });
  input.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      e.preventDefault();
      clearGlobalSearch();
      input.blur();
    }
  });
  clearBtn?.addEventListener("click", () => {
    clearGlobalSearch();
    input.focus();
  });

  document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      input.focus();
      input.select();
    }
  });
}

function searchEmptyRow(colspan, query) {
  const q = escapeHtml(query.trim());
  return `<tr class="search-empty-row"><td colspan="${colspan}">Ничего не найдено${q ? ` по запросу «${q}»` : ""}</td></tr>`;
}

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

  const credCard = qs("#settings-groups-card");
  if (credCard) {
    credCard.style.display = can("credentials:read") || can("credentials:write") ? "" : "none";
  }
  qsa("#settings-add-cred-card").forEach(el => {
    if (!el) return;
    const perm = el.dataset.permission;
    if (perm) {
      el.style.display = can(perm) ? "" : "none";
    }
  });
  const ldapTab = qs("#settings-ldap-tab-li");
  if (ldapTab) {
    ldapTab.style.display = can("users:manage") ? "" : "none";
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
  const iframe = qs("#oxidized-iframe");
  if (iframe) iframe.setAttribute("src", "about:blank");
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

function loadOxidizedIframe(force = false) {
  const iframe = qs("#oxidized-iframe");
  const card = qs(".oxidized-ui-card");
  if (!iframe || !currentUser) return;
  if (!oxidizedProxyUrl) {
    if (card) card.style.display = "none";
    return;
  }
  if (card) card.style.display = "";
  const target = oxidizedProxyUrl || "/oxidized-proxy/nodes";
  const current = iframe.getAttribute("src") || "";
  if (force || current === "about:blank" || !current.includes("/oxidized-proxy")) {
    iframe.setAttribute("src", target);
  }
}

function setOxidizedLinks(url, proxyUrl, engine) {
  oxidizedPublicUrl = url || oxidizedPublicUrl;
  if (engine) oxidizedEngine = engine;
  if (proxyUrl !== undefined && proxyUrl !== null) oxidizedProxyUrl = proxyUrl;
  else if (proxyUrl === undefined) oxidizedProxyUrl = "/oxidized-proxy/nodes";
  const card = qs(".oxidized-ui-card");
  if (card) card.style.display = oxidizedProxyUrl ? "" : "none";
  const proxyHref = oxidizedProxyUrl
    ? `${window.location.origin}${oxidizedProxyUrl}`
    : `${window.location.origin}/#oxidized`;
  const showExternal = oxidizedEngine !== "python" && oxidizedPublicUrl;
  ["link-oxidized", "link-oxidized-2"].forEach(id => {
    const a = qs(`#${id}`);
    if (!a) return;
    a.style.display = showExternal ? "" : "none";
    if (showExternal) a.href = oxidizedPublicUrl;
  });
  const embedLink = qs("#link-oxidized-3");
  if (embedLink) embedLink.href = proxyHref;
  const uiHint = qs("#oxidized-ui-hint");
  if (uiHint) {
    uiHint.textContent = oxidizedEngine === "python"
      ? "Встроенный Oxidized Web (Python engine)"
      : "Proxy к Ruby Oxidized Web";
  }
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
      if (page === "oxidized") {
        loadOxidizedNodes();
        refreshOxidizedLogBadge();
      } else {
        stopOxidizedLogsPolling();
      }
      if (page === "oxidized-ui") loadOxidizedIframe(true);
      if (page === "users") {
        loadUsers();
        loadRbacMatrix();
      }
      if (page === "scan") resumeScanIfRunning();
      if (page === "settings") loadSettings();
    });
  });
}

function getGroupNames() {
  const fromProfiles = (inventory?.credential_profiles || []).map(p => p.group_name);
  const fromDevices = (inventory?.devices || []).map(d => d.group);
  const fromNetworks = (inventory?.networks || []).map(n => n.group_name);
  return [...new Set([...fromProfiles, ...fromDevices, ...fromNetworks].filter(Boolean))].sort();
}

function updateGroupSelects(selected) {
  const groups = getGroupNames();
  const fallback = groups.length ? groups : ["default"];
  qsa(".group-select").forEach(sel => {
    const current = selected || sel.value || fallback[0];
    sel.innerHTML = fallback.map(g =>
      `<option value="${g}"${g === current ? " selected" : ""}>${g}</option>`
    ).join("");
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
  usersCache = await api("/api/auth/users");
  renderUsersTable(usersCache);
}

function renderUsersTable(users) {
  const tbody = qs("#users-table");
  if (!tbody) return;
  const query = globalSearchQuery;
  const filtered = (users || []).filter(u =>
    matchesSearch([u.username, u.role, u.auth_source, u.is_active ? "active" : "inactive"], query)
  );

  if (!users?.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Нет пользователей</td></tr>`;
    return;
  }
  if (!filtered.length) {
    tbody.innerHTML = searchEmptyRow(6, query);
    return;
  }

  tbody.innerHTML = filtered.map(u => `
    <tr>
      <td><strong>${escapeHtml(u.username)}</strong></td>
      <td>
        <select class="form-control form-control-sm user-role-select" data-id="${u.id}" ${u.id === currentUser.id ? "disabled" : ""}>
          <option value="viewer" ${u.role === "viewer" ? "selected" : ""}>viewer</option>
          <option value="operator" ${u.role === "operator" ? "selected" : ""}>operator</option>
          <option value="admin" ${u.role === "admin" ? "selected" : ""}>admin</option>
        </select>
      </td>
      <td><span class="badge badge-${u.auth_source === "ldap" ? "info" : "secondary"}">${escapeHtml(u.auth_source || "local")}</span></td>
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
  updateGroupSelects();
  renderNetworksTable();
  renderDevicesTable();
}

function renderNetworksTable() {
  const netsTable = qs("#networks-table");
  if (!netsTable) return;
  const networks = inventory?.networks || [];
  const query = globalSearchQuery;
  const filtered = networks.filter(n =>
    matchesSearch([n.network, n.group_name, n.environment_name, n.gateway], query)
  );

  if (!networks.length) {
    netsTable.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Нет подсетей</td></tr>`;
    return;
  }
  if (!filtered.length) {
    netsTable.innerHTML = searchEmptyRow(5, query);
    return;
  }

  netsTable.innerHTML = filtered.map(n => `
    <tr>
      <td>${escapeHtml(n.network)}</td>
      <td>${escapeHtml(n.group_name)}</td>
      <td>${escapeHtml(n.environment_name || "—")}</td>
      <td>${escapeHtml(n.gateway || "—")}</td>
      <td>
        ${can("inventory:write") ? `<button class="btn btn-danger btn-sm btn-remove-network" data-network="${escapeHtml(n.network)}"><i class="fas fa-trash"></i></button>` : ""}
      </td>
    </tr>
  `).join("");

  netsTable.querySelectorAll(".btn-remove-network").forEach(btn => {
    btn.addEventListener("click", async () => {
      const network = btn.dataset.network;
      inventory.networks = inventory.networks.filter(n => n.network !== network);
      await api("/inventory", { method: "PUT", body: JSON.stringify(inventory) });
      loadInventory();
    });
  });
}

function renderDevicesTable() {
  const tbody = qs("#devices-table");
  if (!tbody) return;
  const devices = inventory?.devices || [];
  const query = globalSearchQuery;
  const filtered = devices.filter(d =>
    matchesSearch([d.name, d.ip, d.model, d.group, (d.ports || []).join(" "), d.enabled ? "yes enabled" : "no disabled"], query)
  );

  updateSearchCountBadge(filtered.length, devices.length, "devices-count-badge");

  if (!devices.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Нет устройств</td></tr>`;
    return;
  }
  if (!filtered.length) {
    tbody.innerHTML = searchEmptyRow(7, query);
    return;
  }

  tbody.innerHTML = filtered.map(d => `
    <tr>
      <td><strong>${escapeHtml(d.name)}</strong></td>
      <td>${escapeHtml(d.ip)}</td>
      <td>${escapeHtml(d.model)}</td>
      <td>${escapeHtml(d.group)}</td>
      <td>${escapeHtml((d.ports || []).join(", "))}</td>
      <td>${d.enabled ? '<span class="badge badge-success">yes</span>' : '<span class="badge badge-secondary">no</span>'}</td>
      <td>
        ${can("inventory:devices") ? `<button class="btn btn-info btn-sm btn-edit-device" data-name="${escapeHtml(d.name)}"><i class="fas fa-edit"></i></button>` : ""}
        ${can("inventory:devices") ? `<button class="btn btn-danger btn-sm btn-delete-device" data-name="${escapeHtml(d.name)}"><i class="fas fa-trash"></i></button>` : ""}
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

async function loadSettings() {
  inventory = await api("/inventory");
  updateGroupSelects();
  updateDiscoveredCountBadge();
  if (can("oxidized:read") || can("oxidized:write")) {
    await loadOxidizedSettings();
    await loadBackupSettings();
  }
  renderSettingsCredentials();
  if (can("users:manage")) {
    await loadLdapSettings();
  }
}

function updateDiscoveredCountBadge() {
  const el = qs("#settings-discovered-count");
  if (!el || !inventory?.devices) return;
  const count = inventory.devices.filter(d => d.name.startsWith("discovered-")).length;
  el.textContent = count ? `В инвентаре: ${count} discovered-*` : "";
}

function fillModelSelect(selectEl, selected, models) {
  if (!selectEl) return;
  const list = (models && models.length) ? models : ["routeros"];
  selectEl.innerHTML = list.map(m =>
    `<option value="${escapeHtml(m)}"${m === selected ? " selected" : ""}>${escapeHtml(m)}</option>`
  ).join("");
}

function fillOxidizedSettingsForm(cfg) {
  oxidizedSettingsCache = cfg;
  const badge = qs("#ox-settings-engine-badge");
  if (badge) badge.textContent = cfg.engine_title || cfg.engine || "—";
  const nodesBadge = qs("#ox-settings-nodes-badge");
  if (nodesBadge) {
    const n = cfg.health?.nodes_count;
    if (n != null) {
      nodesBadge.style.display = "inline";
      nodesBadge.textContent = `${n} узлов`;
      nodesBadge.className = `badge ml-1 ${cfg.health?.reachable ? "badge-success" : "badge-danger"}`;
    } else {
      nodesBadge.style.display = "none";
    }
  }
  const note = qs("#ox-settings-env-note");
  if (note) note.textContent = cfg.env_note || "";
  qs("#ox-interval").value = cfg.interval ?? 3600;
  qs("#ox-threads").value = cfg.threads ?? 10;
  qs("#ox-timeout").value = cfg.timeout ?? 20;
  qs("#ox-retries").value = cfg.retries ?? 3;
  qs("#ox-ssh-port").value = cfg.ssh_port ?? 44333;
  qs("#ox-resolve-dns").checked = cfg.resolve_dns !== false;
  qs("#ox-git-remote").textContent = cfg.git_remote_url || "не задан (GIT_REMOTE_URL)";
  const logEl = qs("#ox-settings-log-path");
  if (logEl) logEl.textContent = cfg.log_path ? `Лог: ${cfg.log_path}` : "";
  fillModelSelect(qs("#ox-default-model"), cfg.default_model || "routeros", cfg.available_models);
  fillModelSelect(qs("#new-cred-model"), cfg.default_model || "routeros", cfg.available_models);
  const uiBtn = qs("#btn-settings-oxidized-ui");
  if (uiBtn && cfg.proxy_url) {
    uiBtn.href = `${window.location.origin}${cfg.proxy_url}`;
  }
  const scanConc = qs("#settings-scan-concurrency");
  if (scanConc) scanConc.textContent = String(cfg.scan_concurrency ?? "—");
}

function collectOxidizedSettingsForm() {
  const groupModels = { ...(oxidizedSettingsCache?.group_models || {}) };
  qsa("#settings-credentials-table tr[data-profile]").forEach(row => {
    const group = row.querySelector(".cred-group")?.value.trim();
    const model = row.querySelector(".cred-model")?.value;
    if (group && model) groupModels[group] = model;
  });
  return {
    interval: parseInt(qs("#ox-interval")?.value, 10) || 3600,
    threads: parseInt(qs("#ox-threads")?.value, 10) || 10,
    timeout: parseInt(qs("#ox-timeout")?.value, 10) || 20,
    retries: parseInt(qs("#ox-retries")?.value, 10) || 3,
    ssh_port: parseInt(qs("#ox-ssh-port")?.value, 10) || 44333,
    default_model: qs("#ox-default-model")?.value || "routeros",
    resolve_dns: qs("#ox-resolve-dns")?.checked !== false,
    group_models: groupModels,
  };
}

async function loadOxidizedSettings() {
  try {
    const cfg = await api("/api/settings/oxidized");
    cfg.scan_concurrency = cfg.scan_concurrency;
    fillOxidizedSettingsForm(cfg);
  } catch (e) {
    showAlert("settings-alert", `Oxidized: ${e.message}`, "error");
  }
}

async function saveOxidizedSettings(e) {
  e.preventDefault();
  if (!can("oxidized:write")) return;
  try {
    const saved = await api("/api/settings/oxidized", {
      method: "PUT",
      body: JSON.stringify(collectOxidizedSettingsForm()),
    });
    fillOxidizedSettingsForm(saved);
    showAlert("settings-alert", "Настройки Oxidized сохранены", "success");
    renderSettingsCredentials();
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
  }
}

async function syncOxidizedFromSettings() {
  if (!can("oxidized:write")) return;
  try {
    const res = await api("/oxidized/sync", { method: "POST" });
    showAlert("settings-alert", res.message || "Конфиг Oxidized синхронизирован", "success");
    await loadOxidizedSettings();
  } catch (e) {
    showAlert("settings-alert", e.message, "error");
  }
}

const SETTINGS_PASSWORD_MASK = "********";
let backupSettingsCache = null;

function fillBackupSettingsForm(cfg) {
  backupSettingsCache = cfg;
  if (qs("#bk-binary")) qs("#bk-binary").checked = cfg.binary_enabled !== false;
  if (qs("#bk-export")) qs("#bk-export").checked = cfg.export_enabled !== false;
  if (qs("#bk-hide-sensitive")) qs("#bk-hide-sensitive").checked = !!cfg.hide_sensitive;
  if (qs("#bk-purge")) qs("#bk-purge").checked = cfg.purge_enabled !== false;
  if (qs("#bk-purge-keep")) qs("#bk-purge-keep").value = cfg.purge_keep ?? 10;
  if (qs("#bk-timeout")) qs("#bk-timeout").value = cfg.backup_timeout ?? 300;
  if (qs("#bk-bin-dir")) qs("#bk-bin-dir").value = cfg.bin_dir || "/var/lib/oxidized/bin";
  if (qs("#bk-rsc-dir")) qs("#bk-rsc-dir").value = cfg.rsc_dir || "/var/lib/oxidized/rsc";
  const encEl = qs("#bk-encrypt-password");
  if (encEl) {
    encEl.value = "";
    encEl.placeholder = cfg.encrypt_password_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "Пусто = без шифрования";
  }
  if (qs("#nt-error-telegram")) qs("#nt-error-telegram").checked = !!cfg.error_notify_telegram;
  if (qs("#nt-error-email")) qs("#nt-error-email").checked = !!cfg.error_notify_email;
  if (qs("#nt-report-telegram")) qs("#nt-report-telegram").checked = !!cfg.report_send_telegram;
  if (qs("#nt-report-email")) qs("#nt-report-email").checked = !!cfg.report_send_email;
  if (qs("#nt-telegram-chat-notify")) qs("#nt-telegram-chat-notify").value = cfg.telegram_chat_notify || "";
  if (qs("#nt-telegram-chat-report")) qs("#nt-telegram-chat-report").value = cfg.telegram_chat_report || "";
  if (qs("#nt-smtp-server")) qs("#nt-smtp-server").value = cfg.smtp_server || "";
  if (qs("#nt-smtp-port")) qs("#nt-smtp-port").value = cfg.smtp_port ?? 465;
  if (qs("#nt-smtp-user")) qs("#nt-smtp-user").value = cfg.smtp_user || "";
  if (qs("#nt-smtp-from")) qs("#nt-smtp-from").value = cfg.smtp_from || "";
  if (qs("#nt-smtp-to-notify")) qs("#nt-smtp-to-notify").value = cfg.smtp_to_notify || "";
  if (qs("#nt-smtp-to-report")) qs("#nt-smtp-to-report").value = cfg.smtp_to_report || "";
  if (qs("#nt-smtp-ssl")) qs("#nt-smtp-ssl").checked = cfg.smtp_ssl !== false;
  const tokEl = qs("#nt-telegram-token");
  if (tokEl) {
    tokEl.value = "";
    tokEl.placeholder = cfg.telegram_token_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "Bot token";
  }
  const smtpPass = qs("#nt-smtp-password");
  if (smtpPass) {
    smtpPass.value = "";
    smtpPass.placeholder = cfg.smtp_password_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "Оставьте пустым, чтобы не менять";
  }
}

function collectBackupSettingsForm() {
  const encVal = qs("#bk-encrypt-password")?.value.trim();
  const tokVal = qs("#nt-telegram-token")?.value.trim();
  const smtpVal = qs("#nt-smtp-password")?.value.trim();
  return {
    binary_enabled: qs("#bk-binary")?.checked !== false,
    export_enabled: qs("#bk-export")?.checked !== false,
    hide_sensitive: qs("#bk-hide-sensitive")?.checked === true,
    encrypt_password: encVal || (backupSettingsCache?.encrypt_password_set ? SETTINGS_PASSWORD_MASK : ""),
    purge_enabled: qs("#bk-purge")?.checked !== false,
    purge_keep: parseInt(qs("#bk-purge-keep")?.value, 10) || 10,
    bin_dir: qs("#bk-bin-dir")?.value.trim() || "/var/lib/oxidized/bin",
    rsc_dir: qs("#bk-rsc-dir")?.value.trim() || "/var/lib/oxidized/rsc",
    backup_timeout: parseInt(qs("#bk-timeout")?.value, 10) || 300,
    error_notify_telegram: qs("#nt-error-telegram")?.checked === true,
    error_notify_email: qs("#nt-error-email")?.checked === true,
    report_send_telegram: qs("#nt-report-telegram")?.checked === true,
    report_send_email: qs("#nt-report-email")?.checked === true,
    telegram_token: tokVal || (backupSettingsCache?.telegram_token_set ? SETTINGS_PASSWORD_MASK : ""),
    telegram_chat_notify: qs("#nt-telegram-chat-notify")?.value.trim() || "",
    telegram_chat_report: qs("#nt-telegram-chat-report")?.value.trim() || "",
    smtp_server: qs("#nt-smtp-server")?.value.trim() || "",
    smtp_port: parseInt(qs("#nt-smtp-port")?.value, 10) || 465,
    smtp_user: qs("#nt-smtp-user")?.value.trim() || "",
    smtp_password: smtpVal || (backupSettingsCache?.smtp_password_set ? SETTINGS_PASSWORD_MASK : ""),
    smtp_ssl: qs("#nt-smtp-ssl")?.checked !== false,
    smtp_from: qs("#nt-smtp-from")?.value.trim() || "",
    smtp_to_notify: qs("#nt-smtp-to-notify")?.value.trim() || "",
    smtp_to_report: qs("#nt-smtp-to-report")?.value.trim() || "",
  };
}

async function loadBackupSettings() {
  try {
    const cfg = await api("/api/settings/backup");
    fillBackupSettingsForm(cfg);
  } catch (e) {
    showAlert("settings-alert", `Backup: ${e.message}`, "error");
  }
}

async function saveBackupSettings(e) {
  e.preventDefault();
  if (!can("oxidized:write")) return;
  try {
    const saved = await api("/api/settings/backup", {
      method: "PUT",
      body: JSON.stringify(collectBackupSettingsForm()),
    });
    fillBackupSettingsForm(saved);
    showAlert("settings-alert", "Настройки MikroTik backup сохранены", "success");
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
  }
}

async function saveNotifySettings(e) {
  e.preventDefault();
  if (!can("oxidized:write")) return;
  try {
    const saved = await api("/api/settings/backup", {
      method: "PUT",
      body: JSON.stringify(collectBackupSettingsForm()),
    });
    fillBackupSettingsForm(saved);
    showAlert("settings-alert", "Настройки уведомлений сохранены", "success");
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
  }
}

async function testBackupNotify(kind) {
  if (!can("oxidized:write")) return;
  const resultEl = qs("#notify-test-result");
  try {
    if (resultEl) resultEl.textContent = "Отправка…";
    const res = await api("/api/settings/backup/test-notify", {
      method: "POST",
      body: JSON.stringify({ kind }),
    });
    const text = (res.messages || []).join("; ");
    if (resultEl) {
      resultEl.textContent = text;
      resultEl.className = `small mt-2 ${res.ok ? "text-success" : "text-danger"}`;
    }
    showAlert("settings-alert", text || (res.ok ? "Отправлено" : "Ошибка"), res.ok ? "success" : "error");
  } catch (e) {
    if (resultEl) {
      resultEl.textContent = e.message;
      resultEl.className = "small mt-2 text-danger";
    }
    showAlert("settings-alert", e.message, "error");
  }
}

async function cleanupDiscoveredDevices() {
  if (!can("inventory:write")) return;
  const count = (inventory?.devices || []).filter(d => d.name.startsWith("discovered-")).length;
  if (!count) {
    showAlert("settings-alert", "Нет устройств discovered-*", "info");
    return;
  }
  if (!confirm(`Удалить ${count} устройств discovered-* из инвентаря?`)) return;
  try {
    const res = await api("/inventory/cleanup-discovered", { method: "POST" });
    inventory = res.inventory;
    showAlert("settings-alert", res.message || "Готово", "success");
    updateDiscoveredCountBadge();
    loadInventory();
    loadHealth();
    if (can("oxidized:read")) await loadOxidizedSettings();
  } catch (e) {
    showAlert("settings-alert", e.message, "error");
  }
}

const LDAP_PRESETS = {
  ldap: {
    user_filter: "(uid={username})",
    start_tls: true,
    use_ssl: false,
    hint: "OpenLDAP / generic: uid, StartTLS на порту 389",
  },
  ad: {
    user_filter: "(sAMAccountName={username})",
    start_tls: true,
    use_ssl: false,
    hint: "Active Directory: sAMAccountName, StartTLS или LDAPS",
  },
};

function updateLdapPresetHint() {
  const type = qs("#ldap-directory-type")?.value || "ldap";
  const hint = qs("#ldap-preset-hint");
  if (hint) hint.textContent = LDAP_PRESETS[type]?.hint || "";
}

function applyLdapPreset(force = false) {
  const type = qs("#ldap-directory-type")?.value || "ldap";
  const preset = LDAP_PRESETS[type];
  if (!preset) return;

  const filterEl = qs("#ldap-user-filter");
  if (force || !filterEl?.value.trim() || filterEl.value.includes("{username}")) {
    if (filterEl) filterEl.value = preset.user_filter;
  }
  if (force || qs("#ldap-start-tls")?.checked === undefined) {
    qs("#ldap-start-tls").checked = preset.start_tls;
  }
  if (force) {
    qs("#ldap-use-ssl").checked = preset.use_ssl;
  }
  updateLdapPresetHint();
}

function fillLdapForm(cfg) {
  qs("#ldap-enabled").checked = !!cfg.enabled;
  qs("#ldap-directory-type").value = cfg.directory_type || "ldap";
  qs("#ldap-server").value = cfg.server || "";
  qs("#ldap-use-ssl").checked = !!cfg.use_ssl;
  qs("#ldap-start-tls").checked = cfg.start_tls !== false;
  qs("#ldap-bind-dn").value = cfg.bind_dn || "";
  qs("#ldap-bind-password").value = cfg.bind_password_set ? "********" : "";
  qs("#ldap-user-base").value = cfg.user_base || "";
  qs("#ldap-user-filter").value = cfg.user_filter || "(uid={username})";
  qs("#ldap-dn-template").value = cfg.user_dn_template || "";
  qs("#ldap-upn-suffix").value = cfg.user_upn_suffix || "";
  qs("#ldap-admin-groups").value = cfg.admin_groups || "";
  qs("#ldap-operator-groups").value = cfg.operator_groups || "";
  qs("#ldap-default-role").value = cfg.default_role || "viewer";
  qs("#ldap-fallback-local").checked = cfg.fallback_local !== false;
  qs("#ldap-timeout").value = cfg.connect_timeout || 10;
  updateLdapPresetHint();
}

function collectLdapForm() {
  const bindPassword = qs("#ldap-bind-password").value;
  return {
    enabled: qs("#ldap-enabled").checked,
    directory_type: qs("#ldap-directory-type").value,
    server: qs("#ldap-server").value.trim(),
    use_ssl: qs("#ldap-use-ssl").checked,
    start_tls: qs("#ldap-start-tls").checked,
    bind_dn: qs("#ldap-bind-dn").value.trim(),
    bind_password: bindPassword === "********" ? "********" : bindPassword,
    user_base: qs("#ldap-user-base").value.trim(),
    user_filter: qs("#ldap-user-filter").value.trim(),
    user_dn_template: qs("#ldap-dn-template").value.trim(),
    user_upn_suffix: qs("#ldap-upn-suffix").value.trim(),
    admin_groups: qs("#ldap-admin-groups").value.trim(),
    operator_groups: qs("#ldap-operator-groups").value.trim(),
    default_role: qs("#ldap-default-role").value,
    fallback_local: qs("#ldap-fallback-local").checked,
    connect_timeout: parseInt(qs("#ldap-timeout").value, 10) || 10,
  };
}

function showLdapTestResult(result) {
  const el = qs("#ldap-test-result");
  if (!el) return;
  const cls = result.ok ? "text-success" : "text-danger";
  const icon = result.ok ? "check-circle" : "times-circle";
  el.innerHTML = `<span class="${cls}"><i class="fas fa-${icon} mr-1"></i>${escapeHtml(result.message)}</span>`;
}

async function loadLdapSettings() {
  try {
    const cfg = await api("/api/settings/ldap");
    fillLdapForm(cfg);
  } catch (e) {
    showAlert("settings-alert", `LDAP: ${e.message}`, "error");
  }
}

async function saveLdapSettings(e) {
  e.preventDefault();
  try {
    const saved = await api("/api/settings/ldap", {
      method: "PUT",
      body: JSON.stringify(collectLdapForm()),
    });
    fillLdapForm(saved);
    showAlert("settings-alert", "Настройки LDAP сохранены", "success");
    updateLoginAuthHint(saved);
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
  }
}

async function testLdap(mode) {
  const payload = { mode };
  if (mode === "auth") {
    payload.username = qs("#ldap-test-username")?.value.trim();
    payload.password = qs("#ldap-test-password")?.value;
  }
  try {
    if (mode === "bind") {
      await api("/api/settings/ldap", {
        method: "PUT",
        body: JSON.stringify(collectLdapForm()),
      });
    }
    const result = await api("/api/settings/ldap/test", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showLdapTestResult(result);
  } catch (err) {
    showLdapTestResult({ ok: false, message: err.message });
  }
}

function updateLoginAuthHint(authOrCfg) {
  const ldapHint = qs("#login-ldap-hint");
  const hintText = qs("#login-auth-hint-text");
  if (!ldapHint) return;

  const enabled = authOrCfg?.ldap_enabled ?? authOrCfg?.enabled;
  if (!enabled) {
    ldapHint.style.display = "none";
    return;
  }
  ldapHint.style.display = "block";
  if (hintText) {
    const type = authOrCfg.directory_type;
    hintText.textContent = type === "ad" ? "Active Directory" : "LDAP";
  }
}

function renderSettingsCredentials() {
  const profiles = inventory?.credential_profiles || [];
  const canEdit = can("credentials:write");
  const canView = can("credentials:read");
  const tbody = qs("#settings-credentials-table");
  const emptyEl = qs("#settings-credentials-empty");
  const query = globalSearchQuery;
  const groupModels = oxidizedSettingsCache?.group_models || {};
  const filtered = profiles.filter(p =>
    matchesSearch([p.name, p.group_name, p.username, p.password, groupModels[p.group_name]], query)
  );

  if (!profiles.length) {
    if (tbody) tbody.innerHTML = "";
    if (emptyEl) emptyEl.style.display = "block";
    return;
  }
  if (emptyEl) emptyEl.style.display = "none";

  if (!filtered.length) {
    tbody.innerHTML = searchEmptyRow(6, query);
    return;
  }

  const models = oxidizedSettingsCache?.available_models || ["routeros"];

  tbody.innerHTML = filtered.map(p => {
    const model = groupModels[p.group_name] || oxidizedSettingsCache?.default_model || "routeros";
    const modelOptions = models.map(m =>
      `<option value="${escapeHtml(m)}"${m === model ? " selected" : ""}>${escapeHtml(m)}</option>`
    ).join("");
    return `
    <tr data-profile="${escapeHtml(p.name)}">
      <td><strong>${escapeHtml(p.name)}</strong></td>
      <td>
        ${canEdit
          ? `<input type="text" class="form-control form-control-sm cred-group" value="${escapeHtml(p.group_name)}">`
          : `<code>${escapeHtml(p.group_name)}</code>`}
      </td>
      <td>
        ${canEdit
          ? `<select class="form-control form-control-sm cred-model">${modelOptions}</select>`
          : `<code>${escapeHtml(model)}</code>`}
      </td>
      <td>
        ${canEdit || canView
          ? `<input type="text" class="form-control form-control-sm cred-username" value="${escapeHtml(p.username)}" ${canEdit ? "" : "readonly"}>`
          : "—"}
      </td>
      <td>
        ${canEdit || canView
          ? `<input type="password" class="form-control form-control-sm cred-password" value="${escapeHtml(p.password)}" ${canEdit ? "" : "readonly"}>`
          : "********"}
      </td>
      <td class="text-nowrap">
        ${canEdit ? `<button class="btn btn-primary btn-sm btn-save-cred" data-name="${escapeHtml(p.name)}" title="Сохранить"><i class="fas fa-save"></i></button>` : ""}
        ${canEdit ? `<button class="btn btn-danger btn-sm btn-delete-cred" data-name="${escapeHtml(p.name)}" title="Удалить"><i class="fas fa-trash"></i></button>` : ""}
      </td>
    </tr>
  `;
  }).join("");

  tbody.querySelectorAll(".btn-save-cred").forEach(btn => {
    btn.addEventListener("click", async () => {
      const row = btn.closest("tr");
      const name = btn.dataset.name;
      try {
        inventory = await api(`/inventory/credentials/${encodeURIComponent(name)}`, {
          method: "PUT",
          body: JSON.stringify({
            username: row.querySelector(".cred-username").value,
            password: row.querySelector(".cred-password").value,
            group_name: row.querySelector(".cred-group").value.trim(),
            model: row.querySelector(".cred-model")?.value,
          }),
        });
        showAlert("settings-alert", `Профиль ${name} сохранён`, "success");
        loadSettings();
        loadInventory();
      } catch (e) {
        showAlert("settings-alert", e.message, "error");
      }
    });
  });

  tbody.querySelectorAll(".btn-delete-cred").forEach(btn => {
    btn.addEventListener("click", async () => {
      const name = btn.dataset.name;
      if (!confirm(`Удалить профиль «${name}»?`)) return;
      try {
        inventory = await api(`/inventory/credentials/${encodeURIComponent(name)}`, {
          method: "DELETE",
        });
        showAlert("settings-alert", `Профиль ${name} удалён`, "success");
        loadSettings();
        loadInventory();
      } catch (e) {
        showAlert("settings-alert", e.message, "error");
      }
    });
  });
}

function navigateToPage(page) {
  const link = qs(`.nav-page[data-page="${page}"]`);
  if (link) link.click();
}

function updateDeviceGroupHint() {
  const hint = qs("#device-group-hint");
  const groupSel = qs("#device-group");
  if (!hint || !groupSel) return;

  const group = groupSel.value;
  const profile = (inventory?.credential_profiles || []).find(p => p.group_name === group);
  const canSeePass = can("credentials:read") || can("credentials:write");

  if (!group) {
    hint.innerHTML = '<span class="text-muted">Выберите группу — SSH-креды берутся из профиля Oxidized</span>';
    return;
  }
  if (!profile) {
    hint.innerHTML = `
      <span class="text-warning">
        <i class="fas fa-exclamation-triangle mr-1"></i>
        Нет профиля для группы «${group}».
        <a href="#" class="device-goto-settings">Добавить в настройках</a>
      </span>`;
    hint.querySelector(".device-goto-settings")?.addEventListener("click", e => {
      e.preventDefault();
      $("#device-modal").modal("hide");
      navigateToPage("settings");
    });
    return;
  }

  const pass = canSeePass ? profile.password : "********";
  hint.innerHTML = `
    <span class="cred-preview text-muted">
      <i class="fas fa-key mr-1"></i>
      Профиль <strong>${profile.name}</strong>:
      <code>${profile.username}</code> / <code>${pass}</code>
    </span>`;
}

function syncDeviceEnabledLabel() {
  const chk = qs("#device-enabled");
  const lbl = qs("#device-enabled-label");
  if (chk && lbl) {
    lbl.textContent = chk.checked ? "Устройство включено" : "Устройство отключено";
  }
}

const OXIDIZED_MODEL_LABELS = {
  routeros: "RouterOS (MikroTik)",
  ios: "Cisco IOS",
  junos: "Juniper JunOS",
  iosxr: "Cisco IOS-XR",
  nxos: "Cisco NX-OS",
  eos: "Arista EOS",
  ironware: "Brocade IronWare",
  procurve: "HP ProCurve",
  openwrt: "OpenWrt",
  vyos: "VyOS",
  fortios: "FortiOS",
  panos: "Palo Alto PAN-OS",
};

function formatOxidizedModelLabel(model) {
  return OXIDIZED_MODEL_LABELS[model] || model;
}

function populateDeviceModelSelect(selectedModel) {
  const sel = qs("#device-model");
  if (!sel) return;
  const models = oxidizedModels.length ? oxidizedModels : ["routeros"];
  sel.innerHTML = models
    .map(m => `<option value="${escapeHtml(m)}">${escapeHtml(formatOxidizedModelLabel(m))}</option>`)
    .join("");
  const preferred = selectedModel || "routeros";
  if (models.includes(preferred)) {
    sel.value = preferred;
  } else if (models.length) {
    sel.value = models[0];
  }
}

async function loadOxidizedModels() {
  try {
    const data = await api("/api/oxidized/models");
    if (Array.isArray(data.models) && data.models.length) {
      oxidizedModels = data.models;
    }
  } catch {
    oxidizedModels = ["routeros"];
  }
  populateDeviceModelSelect();
}

function openDeviceModal(name = null) {
  editingDeviceName = name;
  const device = name ? inventory?.devices?.find(d => d.name === name) : null;

  const titleEl = qs("#device-modal-title");
  if (titleEl) {
    titleEl.innerHTML = name
      ? '<i class="fas fa-edit mr-2 text-muted"></i>Изменить устройство'
      : '<i class="fas fa-plus mr-2 text-muted"></i>Добавить устройство';
  }

  updateGroupSelects(device?.group || getGroupNames()[0]);

  qs("#device-name").value = device?.name || "";
  qs("#device-name").disabled = !!name;
  qs("#device-ip").value = device?.ip || "";
  populateDeviceModelSelect(device?.model || "routeros");
  if (device?.group) qs("#device-group").value = device.group;
  qs("#device-ports").value = (device?.ports || [44333]).join(", ");
  qs("#device-enabled").checked = device ? device.enabled : true;
  syncDeviceEnabledLabel();
  updateDeviceGroupHint();
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
    enabled: qs("#device-enabled").checked,
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

function formatLogTime(ts) {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleTimeString("ru-RU");
  } catch {
    return "";
  }
}

function renderScanLogLines(logEl, logs, fromIndex = 0) {
  if (!logEl) return;
  if (!logs?.length) {
    if (fromIndex === 0) {
      logEl.innerHTML = '<div class="scan-log-empty">Ожидание событий…</div>';
    }
    return;
  }
  if (fromIndex === 0) {
    logEl.innerHTML = "";
  }
  for (let i = fromIndex; i < logs.length; i++) {
    const entry = logs[i];
    const line = document.createElement("div");
    line.className = `scan-log-line log-${entry.level || "info"}`;
    line.textContent = `[${formatLogTime(entry.ts)}] ${entry.message}`;
    logEl.appendChild(line);
  }
  logEl.scrollTop = logEl.scrollHeight;
}

function updateScanActivityPanel(panel, status, { running }) {
  if (!panel) return;
  panel.style.display = running || status.status === "completed" || status.status === "failed" ? "block" : "none";

  const phaseBadge = panel.querySelector(".scan-phase-badge");
  const msgEl = panel.querySelector(".scan-progress-msg");
  const counterEl = panel.querySelector(".scan-progress-counter");
  const bar = panel.querySelector(".scan-progress-bar");
  const logEl = panel.querySelector(".scan-log-viewer");
  const runningIcon = panel.querySelector(".scan-running-icon");

  const phase = status.phase || "idle";
  if (phaseBadge) {
    phaseBadge.textContent = SCAN_PHASE_LABELS[phase] || phase;
    phaseBadge.className = `badge scan-phase-badge ${
      status.status === "failed" ? "badge-danger"
        : status.status === "completed" ? "badge-success"
          : "badge-info"
    }`;
  }

  if (msgEl) msgEl.textContent = status.message || "—";

  const pct = status.progress_pct || 0;
  const current = status.progress_current || 0;
  const total = status.progress_total || 0;
  if (counterEl) {
    counterEl.textContent = total > 0 ? `${current} / ${total} (${pct}%)` : (running ? "…" : "—");
  }
  if (bar) {
    bar.style.width = `${pct}%`;
    bar.textContent = total > 0 ? `${pct}%` : "";
    bar.classList.toggle("progress-bar-animated", running);
    bar.classList.toggle("progress-bar-striped", running);
  }
  if (runningIcon) {
    runningIcon.classList.toggle("fa-spin", running);
    runningIcon.classList.toggle("fa-spinner", running);
    runningIcon.classList.toggle("fa-check", !running && status.status === "completed");
    runningIcon.classList.toggle("fa-times", !running && status.status === "failed");
  }

  if (logEl && Array.isArray(status.logs)) {
    renderScanLogLines(logEl, status.logs, 0);
  } else if (logEl && running) {
    logEl.innerHTML = '<div class="scan-log-empty">Ожидание событий…</div>';
  }
}

function updateScanUI(status, { running = false } = {}) {
  qsa(".scan-activity-panel").forEach(panel => {
    updateScanActivityPanel(panel, status, { running });
  });
}

function hideScanActivity() {
  qsa(".scan-activity-panel").forEach(panel => {
    panel.style.display = "none";
  });
}

function resetScanLogState() {
  qsa(".scan-activity-panel .scan-log-viewer").forEach(el => {
    el.innerHTML = "";
  });
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
      updateScanUI(status, { running: true });
      return;
    }

    stopScanPolling();
    setScanButtonsDisabled(false);
    updateScanUI(status, { running: false });

    if (status.status === "completed" && status.summary) {
      renderScanResults(status.summary);
      showAlert("scan-alert", status.message || "Сканирование завершено", "success");
      loadHealth();
      loadInventory();
    } else if (status.status === "failed") {
      showAlert("scan-alert", status.error || status.message || "Ошибка сканирования", "error");
    } else if (status.status === "idle") {
      hideScanActivity();
    }

    if (onComplete) onComplete(status);
  } catch (e) {
    stopScanPolling();
    setScanButtonsDisabled(false);
    hideScanActivity();
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
      resetScanLogState();
      updateScanUI(status, { running: true });
      showAlert("scan-alert", status.message || "Сканирование выполняется…", "info");
      startScanPolling();
    }
  } catch {}
}

function renderScanResults(summary) {
  lastScanSummary = summary;

  if (!summary) {
    qs("#scan-empty").style.display = "block";
    qs("#scan-stats").innerHTML = "";
    qs("#scan-results-table").innerHTML = "";
    updateSearchCountBadge(0, 0, "scan-results-count-badge");
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

  const query = globalSearchQuery;
  const allResults = summary.results || [];
  const filtered = allResults.filter(r =>
    matchesSearch([
      r.name, r.ip, r.model, r.group, r.status,
      r.ping_ok ? "ping ok" : "ping fail",
      (r.ports || []).map(p => `${p.port} ${p.open ? "open" : "closed"}`).join(" "),
    ], query)
  );

  updateSearchCountBadge(filtered.length, allResults.length, "scan-results-count-badge");

  if (!filtered.length) {
    qs("#scan-results-table").innerHTML = searchEmptyRow(7, query);
    return;
  }

  qs("#scan-results-table").innerHTML = filtered.map(r => {
    const ports = (r.ports || []).map(p =>
      `<span class="mr-2"><span class="port-dot ${p.open ? "port-open" : "port-closed"}"></span>${p.port}</span>`
    ).join("");
    return `
      <tr>
        <td>${badge(r.status)}</td>
        <td>${escapeHtml(r.name)}</td>
        <td>${escapeHtml(r.ip)}</td>
        <td>${r.ping_ok ? "✓" : "✗"}</td>
        <td>${ports}</td>
        <td>${escapeHtml(r.model)}</td>
        <td>${formatDate(r.scanned_at)}</td>
      </tr>
    `;
  }).join("");
}

async function runScan(discover = false) {
  setScanButtonsDisabled(true);
  resetScanLogState();

  try {
    showAlert("scan-alert", discover ? "Запуск discovery и сканирования…" : "Запуск сканирования…", "info");
    await api(`/scan?discover=${discover}`, { method: "POST" });
    const status = await api("/scan/status");
    updateScanUI(status, { running: true });
    startScanPolling();
  } catch (e) {
    setScanButtonsDisabled(false);
    hideScanActivity();
    showAlert("scan-alert", e.message, "error");
  }
}

async function syncOxidized() {
  try {
    const res = await api("/oxidized/sync", { method: "POST" });
    showAlert(
      "oxidized-alert",
      res.message || `Конфиг обновлён (${res.engine_title || res.engine})`,
      "success",
    );
    showAlert("dashboard-alert", `HTTP source: ${res.source_url}`, "success");
    loadOxidizedNodes();
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

async function loadOxidizedNodes() {
  try {
    const health = await api("/api/oxidized/health");
    setOxidizedLinks(health.public_url, "/oxidized-proxy/nodes", health.engine);

    qs("#oxidized-stats").innerHTML = `
      <div class="col-12 stats-row">
        <div class="row">
          ${smallBox(health.reachable ? "OK" : "OFF", "Статус", health.reachable ? "bg-success" : "bg-danger", "fa-heartbeat")}
          ${smallBox(health.nodes_count, "Узлов", "bg-info", "fa-server")}
          ${smallBox(health.engine_title || (health.engine === "python" ? "Python" : "Ruby"), "Движок", "bg-secondary", "fa-cogs", "text-sm")}
        </div>
      </div>
    `;

    if (!health.reachable) {
      showAlert("oxidized-alert", health.error || "Oxidized недоступен", "error");
      oxidizedNodesCache = [];
      qs("#oxidized-empty").style.display = "block";
      qs("#oxidized-nodes-table").innerHTML = "";
      updateSearchCountBadge(0, 0, "oxidized-count-badge");
      return;
    }

    const nodes = await api("/api/oxidized/nodes");
    oxidizedNodesCache = nodes;
    renderOxidizedNodesTable(nodes);
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

function renderOxidizedNodesTable(nodes) {
  qs("#oxidized-empty").style.display = nodes.length ? "none" : "block";

  const query = globalSearchQuery;
  const filtered = (nodes || []).filter(n => {
    const last = n.last || {};
    return matchesSearch([
      n.name, n.ip, n.model, n.group,
      last.status, last.time,
    ], query);
  });

  updateSearchCountBadge(filtered.length, nodes.length, "oxidized-count-badge");

  if (!nodes.length) {
    qs("#oxidized-nodes-table").innerHTML = "";
    return;
  }
  if (!filtered.length) {
    qs("#oxidized-nodes-table").innerHTML = searchEmptyRow(7, query);
    return;
  }

  qs("#oxidized-nodes-table").innerHTML = filtered.map(n => {
    const last = n.last || {};
    const status = last.status || "unknown";
    return `
      <tr>
        <td><strong>${escapeHtml(n.name)}</strong></td>
        <td>${escapeHtml(n.ip || "—")}</td>
        <td>${escapeHtml(n.model || "—")}</td>
        <td>${escapeHtml(n.group || "—")}</td>
        <td>${formatDate(last.end || last.start)}</td>
        <td>${badge(status === "success" ? "success" : status)}</td>
        <td>
          <button class="btn btn-secondary btn-sm btn-show-versions" data-name="${escapeHtml(n.name)}" title="Версии / diff">
            <i class="fas fa-history"></i>
          </button>
          <button class="btn btn-info btn-sm btn-show-config" data-name="${escapeHtml(n.name)}" data-model="${escapeHtml(n.model || "routeros")}" title="Конфиг">
            <i class="fas fa-file-alt"></i>
          </button>
          ${can("oxidized:write") ? `<button class="btn btn-primary btn-sm btn-fetch-config" data-name="${escapeHtml(n.name)}" title="Fetch"><i class="fas fa-download"></i></button>` : ""}
          <button class="btn btn-outline-secondary btn-sm btn-show-backups" data-name="${escapeHtml(n.name)}" title="Файлы бэкапа">
            <i class="fas fa-archive"></i>
          </button>
        </td>
      </tr>
    `;
  }).join("");

  qs("#oxidized-nodes-table").querySelectorAll(".btn-show-config").forEach(btn => {
    btn.addEventListener("click", () => showNodeConfig(btn.dataset.name, btn.dataset.model));
  });
  qs("#oxidized-nodes-table").querySelectorAll(".btn-show-versions").forEach(btn => {
    btn.addEventListener("click", () => showNodeVersions(btn.dataset.name));
  });
  qs("#oxidized-nodes-table").querySelectorAll(".btn-fetch-config").forEach(btn => {
    btn.addEventListener("click", () => fetchNodeConfig(btn.dataset.name));
  });
  qs("#oxidized-nodes-table").querySelectorAll(".btn-show-backups").forEach(btn => {
    btn.addEventListener("click", () => showNodeBackups(btn.dataset.name));
  });
}

function navigateOxidizedIframe(path) {
  const iframe = qs("#oxidized-iframe");
  if (!iframe || !currentUser) return;
  if (path.startsWith(OXIDIZED_PROXY_PREFIX)) {
    iframe.setAttribute("src", path);
    return;
  }
  const suffix = path.startsWith("/") ? path : `/${path}`;
  iframe.setAttribute("src", `${OXIDIZED_PROXY_PREFIX}${suffix}`);
}

async function showNodeVersions(name) {
  try {
    const data = await api(`/api/oxidized/nodes/${encodeURIComponent(name)}/versions`);
    qs("#oxidized-versions-node").textContent = data.group
      ? `${data.node} (${data.group})`
      : data.node;
    const webLink = qs("#oxidized-versions-open-web");
    if (webLink) {
      webLink.href = `${window.location.origin}${data.versions_proxy_url}`;
    }

    const tbody = qs("#oxidized-versions-table");
    const emptyEl = qs("#oxidized-versions-empty");
    const versions = data.versions || [];

    if (!versions.length) {
      if (tbody) tbody.innerHTML = "";
      if (emptyEl) emptyEl.style.display = "block";
    } else {
      if (emptyEl) emptyEl.style.display = "none";
      tbody.innerHTML = versions.map(v => `
        <tr>
          <td>${v.num}</td>
          <td>${formatDate(v.time)}</td>
          <td><code class="small">${escapeHtml(String(v.oid || "").slice(0, 12))}</code></td>
          <td class="text-right text-nowrap">
            <button type="button" class="btn btn-outline-secondary btn-sm btn-view-config" data-name="${escapeHtml(name)}" data-url="${escapeHtml(v.view_url)}" data-label="${escapeHtml(formatDate(v.time))}" title="Просмотр версии">
              <i class="fas fa-eye"></i>
            </button>
            ${v.diff_url ? `
              <button type="button" class="btn btn-outline-primary btn-sm btn-open-diff" data-name="${escapeHtml(name)}" data-url="${escapeHtml(v.diff_url)}" title="Diff с предыдущей">
                <i class="fas fa-file-diff"></i> Diff
              </button>
            ` : `<span class="text-muted small">—</span>`}
          </td>
        </tr>
      `).join("");

      tbody.querySelectorAll(".btn-open-diff").forEach(btn => {
        btn.addEventListener("click", () => {
          openOxidizedDiff(btn.dataset.name, btn.dataset.url);
        });
      });
      tbody.querySelectorAll(".btn-view-config").forEach(btn => {
        btn.addEventListener("click", () => {
          openOxidizedConfigView(btn.dataset.name, btn.dataset.url, btn.dataset.label);
        });
      });
    }

    $("#oxidized-versions-modal").modal("show");
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

function openOxidizedDiff(name, diffUrl) {
  const iframe = qs("#oxidized-diff-iframe");
  const openTab = qs("#oxidized-diff-open-tab");
  qs("#oxidized-diff-node").textContent = name;
  const fullUrl = diffUrl.startsWith("http")
    ? diffUrl
    : `${window.location.origin}${diffUrl}`;
  if (iframe) iframe.setAttribute("src", fullUrl);
  if (openTab) openTab.href = fullUrl;
  $("#oxidized-diff-modal").modal("show");
}

function closeOxidizedDiffModal() {
  const iframe = qs("#oxidized-diff-iframe");
  if (iframe) iframe.setAttribute("src", "about:blank");
}

function classifyOxidizedLogLine(line) {
  const lower = line.toLowerCase();
  if (/error|fail|exception|fatal|unable|no_connection|authenticationfailed/.test(lower)) {
    return "log-error";
  }
  if (/warn|warning|retry/.test(lower)) return "log-warn";
  if (/success|stored|updated|configuration updated|finished|pushed/.test(lower)) {
    return "log-ok";
  }
  return "";
}

function renderOxidizedLogs(data) {
  const viewer = qs("#oxidized-log-viewer");
  const badge = qs("#oxidized-logs-count");
  const engineBadge = qs("#oxidized-log-engine");
  if (!viewer) return;

  if (engineBadge) {
    if (data.engine_title) {
      engineBadge.textContent = data.engine_title;
      engineBadge.style.display = "inline";
    } else {
      engineBadge.style.display = "none";
    }
  }

  if (!data.available) {
    viewer.textContent = data.error || "Лог недоступен";
    if (badge) badge.style.display = "none";
    updateOxidizedLogBtnBadge(data);
    return;
  }

  const lines = data.lines || [];
  if (!lines.length) {
    viewer.textContent = globalSearchQuery.trim()
      ? "Нет строк, подходящих под фильтр поиска"
      : "Лог пуст";
    if (badge) badge.style.display = "none";
    updateOxidizedLogBtnBadge(data);
    return;
  }

  viewer.innerHTML = lines
    .map(line => {
      const cls = classifyOxidizedLogLine(line);
      return cls ? `<span class="${cls}">${escapeHtml(line)}</span>` : escapeHtml(line);
    })
    .join("\n");

  if (badge) {
    badge.style.display = "inline";
    badge.textContent = data.truncated ? `${data.returned}+` : String(data.returned);
  }

  updateOxidizedLogBtnBadge(data);

  if (oxidizedLogsStickToBottom) {
    viewer.scrollTop = viewer.scrollHeight;
  }
}

function updateOxidizedLogBtnBadge(data) {
  const btnBadge = qs("#oxidized-logs-btn-badge");
  if (!btnBadge) return;
  const lines = data.lines || [];
  if (lines.length && data.available) {
    btnBadge.style.display = "inline";
    btnBadge.textContent = data.truncated ? `${data.returned}+` : String(data.returned);
    const hasError = lines.some(line => classifyOxidizedLogLine(line) === "log-error");
    btnBadge.className = `badge ml-1 ${hasError ? "badge-danger" : "badge-secondary"}`;
  } else {
    btnBadge.style.display = "none";
  }
}

async function refreshOxidizedLogBadge() {
  const params = new URLSearchParams({ lines: "100" });
  try {
    const data = await api(`/api/oxidized/logs?${params}`);
    updateOxidizedLogBtnBadge(data);
  } catch (e) {
    const btnBadge = qs("#oxidized-logs-btn-badge");
    if (btnBadge) btnBadge.style.display = "none";
  }
}

function openOxidizedLogsModal() {
  oxidizedLogsStickToBottom = true;
  $("#oxidized-logs-modal").modal("show");
}

async function loadOxidizedLogs() {
  const params = new URLSearchParams({ lines: "500" });
  if (globalSearchQuery.trim()) params.set("q", globalSearchQuery.trim());
  try {
    const data = await api(`/api/oxidized/logs?${params}`);
    renderOxidizedLogs(data);
  } catch (e) {
    const viewer = qs("#oxidized-log-viewer");
    if (viewer) viewer.textContent = e.message;
  }
}

function startOxidizedLogsPolling() {
  stopOxidizedLogsPolling();
  oxidizedLogsStickToBottom = true;
  loadOxidizedLogs();
  if (qs("#oxidized-logs-autorefresh")?.checked) {
    oxidizedLogsTimer = setInterval(loadOxidizedLogs, 3000);
  }
}

function stopOxidizedLogsPolling() {
  if (oxidizedLogsTimer) {
    clearInterval(oxidizedLogsTimer);
    oxidizedLogsTimer = null;
  }
}

async function showNodeConfig(name, model) {
  try {
    const data = await api(`/api/oxidized/nodes/${encodeURIComponent(name)}`);
    qs("#config-card").style.display = "block";
    qs("#config-node-name").textContent = name;
    qs("#config-card")?.setAttribute("data-node-name", name);
    const content = typeof data === "string" ? data : (data.full || JSON.stringify(data, null, 2));
    const nodeModel = model || oxidizedNodesCache.find(n => n.name === name)?.model;
    if (window.ConfigEditor) {
      ConfigEditor.setContent("config-content", content || "Пустой конфиг", { model: nodeModel });
    } else {
      const el = qs("#config-content");
      if (el) el.value = content || "Пустой конфиг";
    }
    qs("#config-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => window.ConfigEditor?.refreshAll(), 120);
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

async function openOxidizedConfigView(name, viewUrl, label) {
  const titleEl = qs("#oxidized-config-modal-node");
  if (titleEl) {
    titleEl.textContent = label ? `${name} · ${label}` : name;
  }
  try {
    const text = await api(viewUrl);
    const nodeModel = oxidizedNodesCache.find(n => n.name === name)?.model;
    if (window.ConfigEditor) {
      ConfigEditor.setContent("oxidized-config-modal-content", text, { model: nodeModel });
    }
    $("#oxidized-config-modal").modal("show");
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

function backupDownloadUrl(name, type, file) {
  const q = new URLSearchParams({ type, file });
  return `${API}/api/oxidized/nodes/${encodeURIComponent(name)}/backups/download?${q}`;
}

function renderBackupFileList(name, type, files) {
  if (!files.length) {
    return '<p class="text-muted small mb-0">Нет файлов</p>';
  }
  return `<ul class="list-unstyled mb-0">${files.map(f => `
    <li class="mb-1">
      <a href="${backupDownloadUrl(name, type, f.name)}" class="btn btn-link btn-sm p-0" download>
        <i class="fas fa-download mr-1"></i>${escapeHtml(f.name)}
      </a>
      <span class="text-muted small ml-2">${formatBytes(f.size)} · ${formatDate(f.mtime ? new Date(f.mtime * 1000).toISOString() : null)}</span>
    </li>
  `).join("")}</ul>`;
}

function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let n = Number(bytes);
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

async function showNodeBackups(name) {
  try {
    const data = await api(`/api/oxidized/nodes/${encodeURIComponent(name)}/backups`);
    qs("#oxidized-backups-node").textContent = name;
    qs("#oxidized-backups-bin").innerHTML = renderBackupFileList(name, "bin", data.backups?.binary || []);
    qs("#oxidized-backups-rsc").innerHTML = renderBackupFileList(name, "rsc", data.backups?.export || []);
    $("#oxidized-backups-modal").modal("show");
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

async function backupAllNodes() {
  if (!can("oxidized:write")) return;
  try {
    showAlert("oxidized-alert", "Запуск backup для всех узлов…", "info");
    const res = await api("/api/oxidized/backup/all", { method: "POST" });
    showAlert("oxidized-alert", `В очереди: ${res.queued} узлов`, "success");
    loadOxidizedNodes();
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

function bindEvents() {
  const addDeviceBtn = qs("#btn-add-device");
  if (addDeviceBtn) addDeviceBtn.addEventListener("click", () => openDeviceModal());

  qs("#device-group")?.addEventListener("change", updateDeviceGroupHint);
  qs("#device-enabled")?.addEventListener("change", syncDeviceEnabledLabel);
  qs("#btn-device-goto-settings")?.addEventListener("click", () => {
    $("#device-modal").modal("hide");
    navigateToPage("settings");
  });

  qs("#device-form").addEventListener("submit", e => {
    e.preventDefault();
    saveDevice();
  });

  qs("#btn-import-network")?.addEventListener("click", async () => {
    try {
      inventory = await api("/inventory/import-network", { method: "POST" });
      showAlert("settings-alert", "network_inventory.yml импортирован", "success");
      loadSettings();
      loadInventory();
      loadHealth();
    } catch (e) {
      showAlert("settings-alert", e.message, "error");
    }
  });

  qs("#ldap-settings-form")?.addEventListener("submit", saveLdapSettings);
  qs("#oxidized-settings-form")?.addEventListener("submit", saveOxidizedSettings);
  qs("#backup-settings-form")?.addEventListener("submit", saveBackupSettings);
  qs("#notify-settings-form")?.addEventListener("submit", saveNotifySettings);
  qs("#btn-test-notify-report")?.addEventListener("click", () => testBackupNotify("report"));
  qs("#btn-test-notify-error")?.addEventListener("click", () => testBackupNotify("error"));
  qs("#btn-settings-sync-oxidized")?.addEventListener("click", syncOxidizedFromSettings);
  qs("#btn-cleanup-discovered")?.addEventListener("click", cleanupDiscoveredDevices);
  qs("#btn-ldap-apply-preset")?.addEventListener("click", () => applyLdapPreset(true));
  qs("#ldap-directory-type")?.addEventListener("change", () => {
    applyLdapPreset(false);
    updateLdapPresetHint();
  });
  qs("#btn-ldap-test-bind")?.addEventListener("click", () => testLdap("bind"));
  qs("#btn-ldap-test-auth")?.addEventListener("click", () => {
    const fields = qs("#ldap-test-auth-fields");
    if (fields) fields.style.display = "";
    testLdap("auth");
  });

  qs("#credential-create-form")?.addEventListener("submit", async e => {
    e.preventDefault();
    if (!can("credentials:write")) return;
    try {
      inventory = await api("/inventory/credentials", {
        method: "POST",
        body: JSON.stringify({
          name: qs("#new-cred-name").value.trim(),
          group_name: qs("#new-cred-group").value.trim(),
          username: qs("#new-cred-username").value,
          password: qs("#new-cred-password").value,
          model: qs("#new-cred-model")?.value || "routeros",
        }),
      });
      qs("#new-cred-name").value = "";
      qs("#new-cred-group").value = "";
      qs("#new-cred-username").value = "";
      qs("#new-cred-password").value = "";
      showAlert("settings-alert", "Группа добавлена", "success");
      loadSettings();
      loadInventory();
    } catch (err) {
      showAlert("settings-alert", err.message, "error");
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

  qsa(".scan-log-clear").forEach(btn => {
    btn.addEventListener("click", () => {
      const panel = btn.closest(".scan-activity-panel");
      const logEl = panel?.querySelector(".scan-log-viewer");
      if (logEl) logEl.innerHTML = '<div class="scan-log-empty">Лог очищен (новые строки появятся при опросе)</div>';
    });
  });
  qs("#btn-quick-sync")?.addEventListener("click", syncOxidized);
  qs("#btn-sync-oxidized")?.addEventListener("click", syncOxidized);
  qs("#btn-backup-all")?.addEventListener("click", backupAllNodes);
  qs("#btn-refresh-oxidized")?.addEventListener("click", loadOxidizedNodes);
  qs("#btn-refresh-oxidized-logs")?.addEventListener("click", loadOxidizedLogs);
  qs("#btn-open-oxidized-logs")?.addEventListener("click", openOxidizedLogsModal);
  $("#oxidized-logs-modal").on("shown.bs.modal", startOxidizedLogsPolling);
  $("#oxidized-logs-modal").on("hidden.bs.modal", stopOxidizedLogsPolling);
  qs("#btn-oxidized-iframe-reload")?.addEventListener("click", () => loadOxidizedIframe(true));
  qs("#btn-oxidized-iframe-nodes")?.addEventListener("click", () => navigateOxidizedIframe("/nodes"));
  qs("#config-card")?.querySelector(".btn-show-versions")?.addEventListener("click", () => {
    const name = qs("#config-card")?.getAttribute("data-node-name");
    if (name) showNodeVersions(name);
  });
  $("#oxidized-diff-modal").on("hidden.bs.modal", closeOxidizedDiffModal);
  $("#oxidized-config-modal").on("shown.bs.modal", () => window.ConfigEditor?.refreshAll());
  qs("#oxidized-logs-autorefresh")?.addEventListener("change", () => {
    if ($("#oxidized-logs-modal").hasClass("show")) {
      startOxidizedLogsPolling();
    }
  });
  qs("#oxidized-log-viewer")?.addEventListener("scroll", e => {
    const el = e.target;
    oxidizedLogsStickToBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 24;
  });
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
    setOxidizedLinks(uiConfig.oxidized_public_url, uiConfig.oxidized_proxy_url, uiConfig.oxidized_engine);
    updateLoginAuthHint(uiConfig.auth || {});
  } catch {}

  await loadOxidizedModels();
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
  bindGlobalSearch();

  try {
    const uiConfig = await api("/api/ui/config").catch(() => ({}));
    updateLoginAuthHint(uiConfig.auth || {});
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
