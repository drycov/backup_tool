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
let oxidizedLogsLevelFilter = "all";
let oxidizedLogsRawData = null;
let oxidizedSettingsCache = null;
let groupPoliciesCache = [];
const SETTINGS_TAB_STORAGE_KEY = "backup-tools-settings-tab";

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
  audit: "Аудит",
};

const COMPLIANCE_BADGE = {
  ok: "success",
  failed: "danger",
  stale: "warning",
  overdue: "warning",
  never: "secondary",
  unreachable: "dark",
};

const AUDIT_ACTION_LABELS = {
  "credential.create": "Создание credentials",
  "credential.update": "Изменение credentials",
  "credential.delete": "Удаление credentials",
  "oxidized.fetch": "Fetch узла",
  "oxidized.backup_all": "Backup all",
  "scan.run": "Scan",
  "scan.discover": "Discovery",
};

const BADGE_THEMES = {
  success: "text-bg-success",
  danger: "text-bg-danger",
  warning: "text-bg-warning",
  info: "text-bg-info",
  secondary: "text-bg-secondary",
  light: "text-bg-light",
  dark: "text-bg-dark",
  primary: "text-bg-primary",
  orange: "text-bg-orange",
};

function badgeCls(color, extra = "") {
  const key = String(color || "secondary").replace(/^(badge-|text-bg-)/, "");
  const theme = BADGE_THEMES[key] || BADGE_THEMES.secondary;
  return extra ? `badge ${theme} ${extra}` : `badge ${theme}`;
}

function badgeSpan(label, color, extra = "") {
  return `<span class="${badgeCls(color, extra)}">${label}</span>`;
}

function smallBoxTheme(theme) {
  if (!theme) return BADGE_THEMES.info;
  if (theme.startsWith("text-bg-")) return theme;
  const raw = theme.replace(/^bg-/, "");
  return BADGE_THEMES[raw] || `text-bg-${raw}`;
}

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
    if (isModalOpen("oxidized-logs-modal")) {
      updateOxidizedLogsSearchBanner();
      loadOxidizedLogs();
    }
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
  syncSettingsActiveTab();
}

function normalizeSettingsTabId(raw) {
  if (!raw) return "";
  let s = String(raw).replace(/^#/, "").trim();
  if (s.startsWith("settings-tab-")) return s;
  if (s.startsWith("settings/")) s = s.slice("settings/".length);
  const aliases = {
    backup: "settings-tab-backup",
    git: "settings-tab-git",
    notify: "settings-tab-notify",
    notifications: "settings-tab-notify",
    groups: "settings-tab-groups",
    ldap: "settings-tab-ldap",
    service: "settings-tab-service",
  };
  return aliases[s] || "";
}

function isSettingsTabVisible(tabId) {
  if (!tabId) return false;
  const navItem = qs(`#settings-tab-nav a[href="#${tabId}"]`)?.closest(".nav-item");
  if (!navItem || navItem.style.display === "none") return false;
  const pane = qs(`#${tabId}`);
  return !!(pane && pane.style.display !== "none");
}

function getVisibleSettingsTabIds() {
  return qsa("#settings-tab-nav .nav-item a.nav-link")
    .map(a => a.getAttribute("href")?.slice(1))
    .filter(id => id && isSettingsTabVisible(id));
}

function activateSettingsTab(tabId, opts = {}) {
  const { persist = true, updateHash = true, scroll = false } = opts;
  let id = normalizeSettingsTabId(tabId);
  if (!id || !isSettingsTabVisible(id)) {
    id = getVisibleSettingsTabIds()[0] || "";
  }
  if (!id) return;

  const link = qs(`#settings-tab-nav a[href="#${id}"]`);
  if (link && !link.classList.contains("active")) {
    if (window.bootstrap?.Tab) {
      window.bootstrap.Tab.getOrCreateInstance(link).show();
    } else {
      link.click();
    }
  }
  if (persist) {
    try { localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, id); } catch {}
  }
  if (updateHash) {
    const short = id.replace("settings-tab-", "");
    const next = `#settings/${short}`;
    if (location.hash !== next) {
      history.replaceState(null, "", next);
    }
  }
  if (scroll) {
    qs(".settings-content-card")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function resolveInitialSettingsTab() {
  const hashPart = location.hash.replace(/^#/, "");
  if (hashPart.startsWith("settings/")) {
    const fromHash = normalizeSettingsTabId(hashPart);
    if (fromHash && isSettingsTabVisible(fromHash)) return fromHash;
  }
  try {
    const stored = localStorage.getItem(SETTINGS_TAB_STORAGE_KEY);
    if (stored && isSettingsTabVisible(stored)) return stored;
  } catch {}
  return getVisibleSettingsTabIds()[0] || "settings-tab-backup";
}

function syncSettingsActiveTab() {
  if (qs("#page-settings")?.classList.contains("d-none")) return;
  const activeId = qs("#settings-tab-nav .nav-link.active")?.getAttribute("href")?.slice(1);
  if (activeId && isSettingsTabVisible(activeId)) return;
  activateSettingsTab(resolveInitialSettingsTab(), { updateHash: false });
}

function initSettingsTabs() {
  qsa("#settings-tab-nav a[data-bs-toggle='tab']").forEach(link => {
    link.addEventListener("shown.bs.tab", e => {
      const id = e.target.getAttribute("href")?.slice(1);
      if (!id) return;
      try { localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, id); } catch {}
      const short = id.replace("settings-tab-", "");
      const next = `#settings/${short}`;
      if (location.hash !== next) {
        history.replaceState(null, "", next);
      }
    });
  });
}

function navigateToSettingsTab(tabId, opts = {}) {
  navigateToPage("settings");
  window.setTimeout(() => {
    activateSettingsTab(tabId, { scroll: true, ...opts });
  }, 150);
}

function handleRouteHash() {
  const h = location.hash.replace(/^#/, "");
  if (!h || h === "settings" || h.startsWith("settings/")) {
    if (!currentUser) return;
    const tab = h.startsWith("settings/") ? h.slice("settings/".length) : "";
    navigateToPage("settings");
    window.setTimeout(() => {
      activateSettingsTab(tab || resolveInitialSettingsTab(), { updateHash: !tab });
    }, 150);
    return;
  }
  const pages = ["dashboard", "inventory", "scan", "oxidized", "oxidized-ui", "audit", "users"];
  if (pages.includes(h)) {
    navigateToPage(h);
  }
}

function showLogin() {
  document.body.classList.add("login-page");
  document.body.classList.remove("layout-fixed", "sidebar-expand-lg", "bg-body-tertiary");
  qs("#login-screen").style.display = "block";
  qs("#app-layout").classList.add("d-none");
  currentUser = null;
}

function showApp() {
  document.body.classList.remove("login-page");
  document.body.classList.add("layout-fixed", "sidebar-expand-lg", "bg-body-tertiary");
  qs("#login-screen").style.display = "none";
  qs("#app-layout").classList.remove("d-none");
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
  updateScopeBanner();
}

function updateScopeBanner() {
  const wrap = qs("#user-scope-banner-wrap");
  const banner = qs("#user-scope-banner");
  if (!wrap || !banner || !currentUser) return;
  if (!currentUser.scoped || currentUser.role === "admin") {
    wrap.style.display = "none";
    banner.innerHTML = "";
    return;
  }
  const groups = (currentUser.allowed_groups || []).join(", ") || "—";
  const sites = (currentUser.allowed_sites || []).join(", ") || "—";
  wrap.style.display = "";
  banner.innerHTML =
    `<i class="fas fa-filter me-1"></i> Ограниченный доступ: группы <strong>${escapeHtml(groups)}</strong>, sites <strong>${escapeHtml(sites)}</strong>. Видны только соответствующие устройства и узлы Oxidized.`;
}

function deviceTagsHtml(device) {
  const tags = [];
  if (device.maintenance) {
    tags.push(`<span class="${badgeCls("warning", "badge-tag")}" title="Scheduled backup paused in maintenance window"><i class="fas fa-moon"></i> maint</span>`);
  }
  if (device.critical) {
    tags.push(`<span class="${badgeCls("danger", "badge-tag")}">critical</span>`);
  }
  if (device.site) {
    tags.push(`<span class="${badgeCls("light", "border badge-tag")}">${escapeHtml(device.site)}</span>`);
  }
  if (device.role) {
    tags.push(`<span class="${badgeCls("secondary", "badge-tag")}">${escapeHtml(device.role)}</span>`);
  }
  return tags.length
    ? `<span class="device-tags">${tags.join(" ")}</span>`
    : '<span class="text-muted">—</span>';
}

function isMaintenanceWindowActiveClient(cfg) {
  if (!cfg || cfg.maintenance_window_enabled === false) return false;
  const now = new Date();
  const day = (now.getUTCDay() + 6) % 7;
  const days = cfg.maintenance_days && cfg.maintenance_days.length
    ? cfg.maintenance_days.map(d => parseInt(d, 10))
    : [0, 1, 2, 3, 4, 5, 6];
  if (!days.includes(day)) return false;
  const hour = now.getUTCHours();
  const start = parseInt(cfg.maintenance_start_hour_utc, 10) || 22;
  const end = parseInt(cfg.maintenance_end_hour_utc, 10) || 6;
  if (start === end) return false;
  if (start < end) return hour >= start && hour < end;
  return hour >= start || hour < end;
}

function updateMaintenanceStatusBadge(cfg) {
  const el = qs("#bk-maint-status");
  if (!el) return;
  if (!cfg || cfg.maintenance_window_enabled === false) {
    el.className = `${badgeCls("secondary")} me-2 mb-1`;
    el.textContent = "Окно выключено";
    return;
  }
  const active = isMaintenanceWindowActiveClient(cfg);
  el.className = `${badgeCls(active ? "warning" : "success")} me-2 mb-1`;
  el.textContent = active
    ? `Сейчас активно (UTC ${cfg.maintenance_start_hour_utc}:00–${cfg.maintenance_end_hour_utc}:00)`
    : `Сейчас неактивно (UTC ${cfg.maintenance_start_hour_utc}:00–${cfg.maintenance_end_hour_utc}:00)`;
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
    online: "success",
    offline: "danger",
    partial: "warning",
    success: "success",
    no_connection: "secondary",
  };
  return badgeSpan(status, map[status] || "secondary");
}

function smallBox(value, label, bg = "info", icon = "fa-server", valueClass = "") {
  const h3Class = valueClass ? ` class="${valueClass}"` : "";
  const theme = smallBoxTheme(bg);
  return `
    <div class="col-xl-2 col-lg-4 col-md-4 col-sm-6 col-12">
      <div class="small-box ${theme}">
        <div class="inner">
          <h3${h3Class}>${value}</h3>
          <p>${label}</p>
        </div>
        <i class="small-box-icon fas ${icon}" aria-hidden="true"></i>
      </div>
    </div>
  `;
}

function formatDate(d, short = false) {
  if (!d) return "—";
  try {
    const dt = new Date(d);
    if (short) {
      return dt.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
    }
    return dt.toLocaleString("ru-RU");
  } catch {
    return d;
  }
}

function showAlert(containerId, msg, type = "danger") {
  const el = qs(`#${containerId}`);
  if (!el) return;
  const alertType = type === "error" ? "danger" : type === "info" ? "info" : type;
  const icons = {
    danger: "fa-exclamation-circle",
    success: "fa-check-circle",
    info: "fa-info-circle",
    warning: "fa-exclamation-triangle",
  };
  const icon = icons[alertType] || icons.info;
  el.innerHTML = `
    <div class="alert alert-${alertType} alert-dismissible fade show" role="alert">
      <i class="fas ${icon} me-1"></i>${msg}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    </div>
  `;
  if (type !== "error") {
    setTimeout(() => { el.innerHTML = ""; }, 5000);
  }
}

function isPythonEngine() {
  return oxidizedEngine === "python";
}

function isRouterOsModel(model) {
  const key = String(model || "").toLowerCase().replace(/[\s_-]/g, "");
  return key === "routeros" || key === "mikrotik" || key === "ros" || key.startsWith("mikrotik");
}

function applyEngineAwareUi() {
  const python = isPythonEngine();
  const backupAll = qs("#btn-backup-all");
  if (backupAll) backupAll.style.display = python ? "" : "none";

  const mikrotikBlock = qs("#mikrotik-backup-settings");
  if (mikrotikBlock) {
    const externalNote = qs("#mikrotik-external-note");
    if (externalNote) externalNote.style.display = python ? "none" : "";
    qsa("#mikrotik-backup-settings .settings-section-header, #mikrotik-backup-settings .settings-section-body").forEach(el => {
      el.style.display = python ? "" : "none";
    });
  }

  const engineBanner = qs("#oxidized-engine-banner");
  if (engineBanner) {
    if (python) {
      engineBanner.style.display = "none";
      engineBanner.innerHTML = "";
    } else {
      engineBanner.style.display = "";
      engineBanner.innerHTML =
        '<i class="fas fa-info-circle me-1"></i> Режим <strong>Ruby Oxidized</strong>: «Backup все» и MikroTik binary/export недоступны в scanner. Используйте внешний контейнер oxidized.';
    }
  }

  if (oxidizedNodesCache.length) renderOxidizedNodesTable(oxidizedNodesCache);
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
  applyEngineAwareUi();
}

function setPageTitle(page) {
  const title = PAGE_TITLES[page] || "Backup Tools";
  const titleEl = qs("#page-title");
  const crumbEl = qs("#page-breadcrumb-active");
  if (titleEl) titleEl.textContent = title;
  if (crumbEl) crumbEl.textContent = title;
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
      if (page === "scan") {
        resumeScanIfRunning();
        loadScanHistory();
      }
      if (page === "audit") loadAudit();
      if (page === "settings") {
        loadSettings().then(() => {
          activateSettingsTab(resolveInitialSettingsTab(), { updateHash: false });
        });
      }
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
  try {
    usersCache = await api("/api/auth/users");
    renderUsersTable(usersCache);
  } catch (e) {
    showAlert("users-alert", e.message, "error");
  }
}

function renderUsersTable(users) {
  const tbody = qs("#users-table");
  if (!tbody) return;
  const query = globalSearchQuery;
  const filtered = (users || []).filter(u =>
    matchesSearch([u.username, u.role, u.auth_source, u.is_active ? "active" : "inactive"], query)
  );

  if (!users?.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Нет пользователей</td></tr>`;
    return;
  }
  if (!filtered.length) {
    tbody.innerHTML = searchEmptyRow(8, query);
    return;
  }

  tbody.innerHTML = filtered.map(u => {
    const scopeBadge = u.scoped
      ? `<span class="${badgeCls("warning", "badge-tag ms-1")}" title="Object scope">scope</span>`
      : "";
    return `
    <tr data-user-id="${u.id}">
      <td><strong>${escapeHtml(u.username)}</strong>${scopeBadge}</td>
      <td>
        <select class="form-control form-control-sm user-role-select" data-id="${u.id}" ${u.id === currentUser.id ? "disabled" : ""}>
          <option value="viewer" ${u.role === "viewer" ? "selected" : ""}>viewer</option>
          <option value="operator" ${u.role === "operator" ? "selected" : ""}>operator</option>
          <option value="admin" ${u.role === "admin" ? "selected" : ""}>admin</option>
        </select>
      </td>
      <td>
        <input type="text" class="form-control form-control-sm user-scope-groups" data-id="${u.id}"
          value="${escapeHtml((u.allowed_groups || []).join(", "))}" placeholder="hex, us"
          ${u.role === "admin" ? "disabled title=\"Admin — полный доступ\"" : ""}>
      </td>
      <td>
        <input type="text" class="form-control form-control-sm user-scope-sites" data-id="${u.id}"
          value="${escapeHtml((u.allowed_sites || []).join(", "))}" placeholder="dc1"
          ${u.role === "admin" ? "disabled" : ""}>
      </td>
      <td><span class="${badgeCls(u.auth_source === "ldap" ? "info" : "secondary")}">${escapeHtml(u.auth_source || "local")}</span></td>
      <td class="text-center">
        ${u.auth_source === "ldap"
    ? `<input type="checkbox" class="user-role-locked" data-id="${u.id}" ${u.role_locked ? "checked" : ""} title="Не обновлять роль из LDAP">`
    : "—"}
      </td>
      <td class="text-center">
        <input type="checkbox" class="user-active-check" data-id="${u.id}" ${u.is_active ? "checked" : ""} ${u.id === currentUser.id ? "disabled" : ""}>
      </td>
      <td class="text-nowrap">
        ${u.role !== "admin" ? `<button type="button" class="btn btn-primary btn-sm btn-save-user-scope" data-id="${u.id}" title="Сохранить scope"><i class="fas fa-save"></i></button>` : ""}
        ${u.id !== currentUser.id ? `<button class="btn btn-danger btn-sm btn-delete-user" data-id="${u.id}"><i class="fas fa-trash"></i></button>` : "—"}
      </td>
    </tr>
  `;
  }).join("");

  tbody.querySelectorAll(".user-role-select").forEach(sel => {
    sel.addEventListener("change", async () => {
      try {
        await api(`/api/auth/users/${sel.dataset.id}`, {
          method: "PUT",
          body: JSON.stringify({ role: sel.value }),
        });
        showAlert("users-alert", "Роль обновлена", "success");
      } catch (e) {
        showAlert("users-alert", e.message, "error");
        loadUsers();
      }
    });
  });

  tbody.querySelectorAll(".user-active-check").forEach(chk => {
    chk.addEventListener("change", async () => {
      try {
        await api(`/api/auth/users/${chk.dataset.id}`, {
          method: "PUT",
          body: JSON.stringify({ is_active: chk.checked }),
        });
        showAlert("users-alert", "Статус обновлён", "success");
      } catch (e) {
        showAlert("users-alert", e.message, "error");
        chk.checked = !chk.checked;
      }
    });
  });

  tbody.querySelectorAll(".user-role-locked").forEach(chk => {
    chk.addEventListener("change", async () => {
      try {
        await api(`/api/auth/users/${chk.dataset.id}`, {
          method: "PUT",
          body: JSON.stringify({ role_locked: chk.checked }),
        });
        showAlert("users-alert", "Фиксация роли обновлена", "success");
      } catch (e) {
        showAlert("users-alert", e.message, "error");
        chk.checked = !chk.checked;
      }
    });
  });

  tbody.querySelectorAll(".btn-save-user-scope").forEach(btn => {
    btn.addEventListener("click", async () => {
      const row = btn.closest("tr");
      const id = btn.dataset.id;
      const parseList = val => val.split(",").map(s => s.trim()).filter(Boolean);
      try {
        await api(`/api/auth/users/${id}`, {
          method: "PUT",
          body: JSON.stringify({
            allowed_groups: parseList(row.querySelector(".user-scope-groups")?.value || ""),
            allowed_sites: parseList(row.querySelector(".user-scope-sites")?.value || ""),
          }),
        });
        showAlert("users-alert", "Scope сохранён", "success");
        loadUsers();
      } catch (e) {
        showAlert("users-alert", e.message, "error");
      }
    });
  });

  tbody.querySelectorAll(".btn-delete-user").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm("Удалить пользователя?")) return;
      try {
        await api(`/api/auth/users/${btn.dataset.id}`, { method: "DELETE" });
        loadUsers();
      } catch (e) {
        showAlert("users-alert", e.message, "error");
      }
    });
  });
}

async function loadHealth() {
  try {
    const health = await api("/health");
    const oxHealth = await api("/api/oxidized/health").catch(() => ({ reachable: false }));
    const trends = await api("/api/scan/trends?days=30").catch(() => ({ points: [] }));

    let warningHtml = "";
    if (oxHealth.models === "python-fallback") {
      warningHtml = `
        <div class="col-12 mb-2">
          <div class="alert alert-warning py-2 mb-0">
            <i class="fas fa-exclamation-triangle me-1"></i>
            Ruby bridge недоступен — gem-модели Oxidized не загружены. Поддерживается только <strong>routeros</strong>.
          </div>
        </div>`;
    }

    const latest = trends.latest || {};
    qs("#dashboard-stats").innerHTML = `
      ${warningHtml}
      <div class="col-12 stats-row">
        <div class="row">
          ${smallBox(health.inventory_devices, "Устройств", "bg-info", "fa-hdd")}
          ${smallBox(health.networks, "Подсетей", "bg-secondary", "fa-network-wired")}
          ${smallBox(oxHealth.reachable ? "OK" : "OFF", "Oxidized", oxHealth.reachable ? "bg-success" : "bg-danger", "fa-database")}
          ${smallBox(oxHealth.nodes_count || 0, "Узлов Oxidized", "bg-primary", "fa-server")}
          ${smallBox(latest.online ?? "—", "Online (scan)", "bg-success", "fa-check-circle")}
          ${smallBox(latest.offline ?? "—", "Offline (scan)", "bg-danger", "fa-times-circle")}
          ${smallBox(formatDate(health.last_scan), "Последний scan", "bg-warning", "fa-clock", "text-sm")}
        </div>
      </div>
    `;
    await loadComplianceDashboard();
    renderScanTrends(trends);
  } catch (e) {
    showAlert("dashboard-alert", e.message, "error");
  }
}

function complianceFilterQuery() {
  const params = new URLSearchParams();
  const site = qs("#cf-site")?.value.trim();
  const role = qs("#cf-role")?.value.trim();
  const group = qs("#cf-group")?.value.trim();
  const state = qs("#cf-state")?.value.trim();
  const critical = qs("#cf-critical")?.value.trim();
  if (site) params.set("site", site);
  if (role) params.set("role", role);
  if (group) params.set("group", group);
  if (state) params.set("state", state);
  if (critical) params.set("critical", critical);
  const q = params.toString();
  return q ? `?${q}` : "";
}

async function loadComplianceDashboard() {
  const compliance = await api(`/api/compliance/summary${complianceFilterQuery()}`).catch(() => null);
  if (!compliance) return;

  const counts = compliance.counts || {};
  qs("#dashboard-compliance-stats").innerHTML = `
    <div class="col-12 stats-row">
      <div class="row">
        ${smallBox(`${compliance.compliance_pct}%`, "Compliance", compliance.compliance_pct >= 90 ? "bg-success" : "bg-warning", "fa-shield-alt")}
        ${smallBox(counts.ok || 0, "OK", "bg-success", "fa-check")}
        ${smallBox(counts.failed || 0, "Ошибки бэкапа", "bg-danger", "fa-exclamation-triangle")}
        ${smallBox(counts.overdue || 0, "Просрочено", "bg-warning", "fa-hourglass-half")}
        ${smallBox(counts.stale || 0, `Stale >${compliance.stale_days_threshold}д`, "bg-orange", "fa-pause-circle")}
        ${smallBox(counts.unreachable || 0, "Offline", "bg-dark", "fa-unlink")}
        ${smallBox(counts.never || 0, "Нет бэкапа", "bg-secondary", "fa-question-circle")}
      </div>
    </div>
  `;

  const genEl = qs("#compliance-generated-at");
  if (genEl) genEl.textContent = formatDate(compliance.generated_at);

  const tbody = qs("#compliance-table");
  const empty = qs("#compliance-empty");
  const nodes = compliance.nodes || [];
  if (!tbody) return;
  if (!nodes.length) {
    tbody.innerHTML = "";
    if (empty) empty.style.display = "";
    return;
  }
  if (empty) empty.style.display = "none";
  tbody.innerHTML = nodes.map(n => `
    <tr>
      <td><span class="${badgeCls(COMPLIANCE_BADGE[n.state] || "secondary")}">${escapeHtml(n.state_label)}</span></td>
      <td>${escapeHtml(n.name)}</td>
      <td>${escapeHtml(n.ip)}</td>
      <td>${escapeHtml(n.group)}</td>
      <td>${escapeHtml(n.site || "—")}</td>
      <td>${escapeHtml(n.role || "—")}</td>
      <td>${n.critical ? badgeSpan("yes", "danger") : badgeSpan("no", "light")}</td>
      <td class="text-sm">${formatDate(n.last_backup_at) || "—"}</td>
      <td>${n.reachability ? badgeSpan(n.reachability, n.reachability === "online" ? "success" : "danger") : "—"}</td>
    </tr>
  `).join("");
}

async function exportComplianceCsv() {
  try {
    const res = await fetch(`/api/compliance/export${complianceFilterQuery()}`, { credentials: "include" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const blob = await res.blob();
    const cd = res.headers.get("content-disposition") || "";
    const match = cd.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : "compliance.csv";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showAlert("dashboard-alert", e.message, "error");
  }
}

function renderScanTrends(trends) {
  const chart = qs("#scan-trends-chart");
  const empty = qs("#scan-trends-empty");
  if (!chart) return;
  const points = trends?.points || [];
  if (!points.length) {
    chart.innerHTML = "";
    if (empty) empty.style.display = "";
    return;
  }
  if (empty) empty.style.display = "none";
  const maxTotal = Math.max(1, ...points.map(p => p.total || 0));
  chart.innerHTML = `
    <div class="scan-trend-bars">
      ${points.map(p => {
        const onlineH = Math.round(100 * (p.online || 0) / maxTotal);
        const offlineH = Math.round(100 * (p.offline || 0) / maxTotal);
        const partialH = Math.round(100 * (p.partial || 0) / maxTotal);
        const label = formatDate(p.scanned_at, true);
        return `
          <div class="scan-trend-col" title="${label}: online ${p.online}, offline ${p.offline}">
            <div class="scan-trend-stack">
              <div class="scan-trend-seg bg-success" style="height:${onlineH}%"></div>
              <div class="scan-trend-seg bg-warning" style="height:${partialH}%"></div>
              <div class="scan-trend-seg bg-danger" style="height:${offlineH}%"></div>
            </div>
            <div class="scan-trend-label">${label}</div>
          </div>`;
      }).join("")}
    </div>
    <div class="small text-muted mt-2">
      ${badgeSpan("online", "success", "me-1")}
      ${badgeSpan("partial", "warning", "me-1")}
      ${badgeSpan("offline", "danger")}
    </div>`;
}

async function loadScanHistory() {
  const data = await api("/api/scan/history?limit=30&days=30").catch(() => ({ items: [] }));
  const tbody = qs("#scan-history-table");
  const empty = qs("#scan-history-empty");
  if (!tbody) return;
  const items = data.items || [];
  if (!items.length) {
    tbody.innerHTML = "";
    if (empty) empty.style.display = "";
    return;
  }
  if (empty) empty.style.display = "none";
  tbody.innerHTML = items.map(row => `
    <tr>
      <td class="text-sm">${formatDate(row.scanned_at)}</td>
      <td>${row.discover ? badgeSpan("discovery", "info") : "scan"}</td>
      <td>${badgeSpan(row.status, row.status === "completed" ? "success" : "danger")}</td>
      <td>${row.online}</td>
      <td>${row.offline}</td>
      <td>${row.partial}</td>
      <td>${row.total}</td>
    </tr>
  `).join("");
}

async function loadAudit() {
  const filter = qs("#audit-action-filter")?.value || "";
  const query = filter ? `?limit=100&action=${encodeURIComponent(filter)}` : "?limit=100";
  try {
    const data = await api(`/api/audit${query}`);
    const tbody = qs("#audit-table");
    const empty = qs("#audit-empty");
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) {
      tbody.innerHTML = "";
      if (empty) empty.style.display = "";
      return;
    }
    if (empty) empty.style.display = "none";
    tbody.innerHTML = items.map(row => `
      <tr>
        <td class="text-sm">${formatDate(row.created_at)}</td>
        <td>${escapeHtml(row.username)}</td>
        <td><code>${escapeHtml(AUDIT_ACTION_LABELS[row.action] || row.action)}</code></td>
        <td>${escapeHtml(row.target || "—")}</td>
        <td class="text-sm">${escapeHtml(row.detail || "—")}</td>
        <td class="text-sm">${escapeHtml(row.ip_address || "—")}</td>
      </tr>
    `).join("");
  } catch (e) {
    showAlert("audit-alert", e.message, "error");
  }
}

async function loadInventory() {
  try {
    inventory = await api("/inventory");
    updateGroupSelects();
    renderNetworksTable();
    renderDevicesTable();
  } catch (e) {
    showAlert("inventory-alert", e.message, "error");
  }
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
    matchesSearch([d.name, d.ip, d.model, d.group, d.site, d.role, d.critical ? "critical" : "", (d.ports || []).join(" "), d.enabled ? "yes enabled" : "no disabled"], query)
  );

  updateSearchCountBadge(filtered.length, devices.length, "devices-count-badge");

  if (!devices.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Нет устройств</td></tr>`;
    return;
  }
  if (!filtered.length) {
    tbody.innerHTML = searchEmptyRow(8, query);
    return;
  }

  tbody.innerHTML = filtered.map(d => `
    <tr>
      <td><strong>${escapeHtml(d.name)}</strong></td>
      <td>${escapeHtml(d.ip)}</td>
      <td><span class="oxidized-model-label">${escapeHtml(formatOxidizedModelLabel(d.model))}</span></td>
      <td>${escapeHtml(d.group)}</td>
      <td>${deviceTagsHtml(d)}</td>
      <td>${escapeHtml((d.ports || []).join(", "))}</td>
      <td>${d.enabled ? badgeSpan("on", "success") : badgeSpan("off", "secondary")}</td>
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
      try {
        await api(`/inventory/devices/${encodeURIComponent(btn.dataset.name)}`, { method: "DELETE" });
        loadInventory();
        loadHealth();
      } catch (e) {
        showAlert("inventory-alert", e.message, "error");
      }
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
    await loadGitSettings();
  }
  renderSettingsCredentials();
  if (can("users:manage")) {
    await loadLdapSettings();
  }
  if (can("inventory:write")) {
    await loadScanSettings();
  }
  if (can("oxidized:read") || can("oxidized:write")) {
    await loadGroupPolicies();
    populateGroupPolicyModelSelect();
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
      nodesBadge.className = `${badgeCls(cfg.health?.reachable ? "success" : "danger")} ms-1`;
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
  const logEl = qs("#ox-settings-log-path");
  if (logEl) logEl.textContent = cfg.log_path ? `Лог: ${cfg.log_path}` : "";
  fillModelSelect(qs("#ox-default-model"), cfg.default_model || "routeros", cfg.available_models);
  fillModelSelect(qs("#new-cred-model"), cfg.default_model || "routeros", cfg.available_models);
  const uiBtn = qs("#btn-settings-oxidized-ui");
  if (uiBtn && cfg.proxy_url) {
    uiBtn.href = `${window.location.origin}${cfg.proxy_url}`;
  }
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
let gitSettingsCache = null;
let scanSettingsCache = null;

function fillBackupSettingsForm(cfg) {
  backupSettingsCache = cfg;
  if (qs("#bk-binary")) qs("#bk-binary").checked = cfg.binary_enabled !== false;
  if (qs("#bk-export")) qs("#bk-export").checked = cfg.export_enabled !== false;
  if (qs("#bk-hide-sensitive")) qs("#bk-hide-sensitive").checked = !!cfg.hide_sensitive;
  if (qs("#bk-purge")) qs("#bk-purge").checked = cfg.purge_enabled !== false;
  if (qs("#bk-git-push")) qs("#bk-git-push").checked = cfg.mk_backup_git_push !== false;
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
  if (qs("#nt-degrade-telegram")) qs("#nt-degrade-telegram").checked = !!cfg.degrade_notify_telegram;
  if (qs("#nt-degrade-email")) qs("#nt-degrade-email").checked = !!cfg.degrade_notify_email;
  if (qs("#nt-stale-days")) qs("#nt-stale-days").value = cfg.stale_days_threshold ?? 30;
  if (qs("#nt-alert-cooldown")) qs("#nt-alert-cooldown").value = cfg.alert_cooldown_hours ?? 24;
  if (qs("#nt-degrade-interval")) qs("#nt-degrade-interval").value = cfg.degrade_check_interval_sec ?? 3600;
  if (qs("#nt-compliance-telegram")) qs("#nt-compliance-telegram").checked = !!cfg.compliance_report_telegram;
  if (qs("#nt-compliance-email")) qs("#nt-compliance-email").checked = !!cfg.compliance_report_email;
  if (qs("#nt-compliance-hour")) qs("#nt-compliance-hour").value = cfg.compliance_report_hour_utc ?? 7;
  const lastSentEl = qs("#nt-compliance-last-sent");
  if (lastSentEl) {
    lastSentEl.textContent = cfg.compliance_report_last_sent_at
      ? `Последний: ${formatDate(cfg.compliance_report_last_sent_at)}`
      : "Последний: —";
  }
  if (qs("#nt-webhook-enabled")) qs("#nt-webhook-enabled").checked = !!cfg.degrade_webhook_enabled;
  if (qs("#nt-webhook-url")) qs("#nt-webhook-url").value = cfg.degrade_webhook_url || "";
  if (qs("#bk-maint-enabled")) qs("#bk-maint-enabled").checked = cfg.maintenance_window_enabled !== false;
  if (qs("#bk-maint-start")) qs("#bk-maint-start").value = cfg.maintenance_start_hour_utc ?? 22;
  if (qs("#bk-maint-end")) qs("#bk-maint-end").value = cfg.maintenance_end_hour_utc ?? 6;
  fillMaintenanceDays(cfg.maintenance_days);
  updateMaintenanceStatusBadge(cfg);
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

function collectNotifySettingsForm() {
  const tokVal = qs("#nt-telegram-token")?.value.trim();
  const smtpVal = qs("#nt-smtp-password")?.value.trim();
  return {
    error_notify_telegram: qs("#nt-error-telegram")?.checked === true,
    error_notify_email: qs("#nt-error-email")?.checked === true,
    report_send_telegram: qs("#nt-report-telegram")?.checked === true,
    report_send_email: qs("#nt-report-email")?.checked === true,
    degrade_notify_telegram: qs("#nt-degrade-telegram")?.checked === true,
    degrade_notify_email: qs("#nt-degrade-email")?.checked === true,
    stale_days_threshold: parseInt(qs("#nt-stale-days")?.value, 10) || 30,
    alert_cooldown_hours: parseInt(qs("#nt-alert-cooldown")?.value, 10) || 24,
    degrade_check_interval_sec: parseInt(qs("#nt-degrade-interval")?.value, 10) || 3600,
    compliance_report_telegram: qs("#nt-compliance-telegram")?.checked === true,
    compliance_report_email: qs("#nt-compliance-email")?.checked === true,
    compliance_report_hour_utc: parseInt(qs("#nt-compliance-hour")?.value, 10) || 7,
    degrade_webhook_enabled: qs("#nt-webhook-enabled")?.checked === true,
    degrade_webhook_url: qs("#nt-webhook-url")?.value.trim() || "",
    maintenance_window_enabled: qs("#bk-maint-enabled")?.checked !== false,
    maintenance_start_hour_utc: parseInt(qs("#bk-maint-start")?.value, 10) || 22,
    maintenance_end_hour_utc: parseInt(qs("#bk-maint-end")?.value, 10) || 6,
    maintenance_days: collectMaintenanceDays(),
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

function collectNotifyTestPayload(kind) {
  const tokVal = qs("#nt-telegram-token")?.value.trim();
  const smtpVal = qs("#nt-smtp-password")?.value.trim();
  const payload = {
    kind,
    error_notify_telegram: qs("#nt-error-telegram")?.checked === true,
    error_notify_email: qs("#nt-error-email")?.checked === true,
    report_send_telegram: qs("#nt-report-telegram")?.checked === true,
    report_send_email: qs("#nt-report-email")?.checked === true,
    degrade_notify_telegram: qs("#nt-degrade-telegram")?.checked === true,
    degrade_notify_email: qs("#nt-degrade-email")?.checked === true,
    telegram_chat_notify: qs("#nt-telegram-chat-notify")?.value.trim() || "",
    telegram_chat_report: qs("#nt-telegram-chat-report")?.value.trim() || "",
    smtp_server: qs("#nt-smtp-server")?.value.trim() || "",
    smtp_port: parseInt(qs("#nt-smtp-port")?.value, 10) || 465,
    smtp_user: qs("#nt-smtp-user")?.value.trim() || "",
    smtp_ssl: qs("#nt-smtp-ssl")?.checked !== false,
    smtp_from: qs("#nt-smtp-from")?.value.trim() || "",
    smtp_to_notify: qs("#nt-smtp-to-notify")?.value.trim() || "",
    smtp_to_report: qs("#nt-smtp-to-report")?.value.trim() || "",
  };
  if (tokVal) payload.telegram_token = tokVal;
  if (smtpVal) payload.smtp_password = smtpVal;
  return payload;
}

function fillMaintenanceDays(days) {
  const selected = new Set(
    Array.isArray(days) && days.length ? days.map(d => parseInt(d, 10)) : [0, 1, 2, 3, 4, 5, 6],
  );
  qsa("#bk-maint-days input[data-day]").forEach(inp => {
    const day = parseInt(inp.dataset.day, 10);
    inp.checked = selected.has(day);
    inp.closest("label")?.classList.toggle("active", inp.checked);
  });
}

function collectMaintenanceDays() {
  return qsa("#bk-maint-days input[data-day]:checked")
    .map(inp => parseInt(inp.dataset.day, 10))
    .filter(n => !Number.isNaN(n))
    .sort((a, b) => a - b);
}

function bindMaintenanceDayToggles() {
  qsa("#bk-maint-days input[data-day]").forEach(inp => {
    inp.addEventListener("change", () => {
      inp.closest("label")?.classList.toggle("active", inp.checked);
      updateMaintenanceStatusBadge({
        maintenance_window_enabled: qs("#bk-maint-enabled")?.checked !== false,
        maintenance_start_hour_utc: parseInt(qs("#bk-maint-start")?.value, 10) || 22,
        maintenance_end_hour_utc: parseInt(qs("#bk-maint-end")?.value, 10) || 6,
        maintenance_days: collectMaintenanceDays(),
      });
    });
  });
  ["#bk-maint-enabled", "#bk-maint-start", "#bk-maint-end"].forEach(sel => {
    qs(sel)?.addEventListener("change", () => {
      updateMaintenanceStatusBadge({
        maintenance_window_enabled: qs("#bk-maint-enabled")?.checked !== false,
        maintenance_start_hour_utc: parseInt(qs("#bk-maint-start")?.value, 10) || 22,
        maintenance_end_hour_utc: parseInt(qs("#bk-maint-end")?.value, 10) || 6,
        maintenance_days: collectMaintenanceDays(),
      });
    });
  });
  qs("#bk-maint-preset-weekdays")?.addEventListener("click", e => {
    e.preventDefault();
    fillMaintenanceDays([0, 1, 2, 3, 4]);
    updateMaintenanceStatusBadge(collectMaintenanceSettingsOnly());
  });
  qs("#bk-maint-preset-all")?.addEventListener("click", e => {
    e.preventDefault();
    fillMaintenanceDays([0, 1, 2, 3, 4, 5, 6]);
    updateMaintenanceStatusBadge(collectMaintenanceSettingsOnly());
  });
}

function collectMaintenanceSettingsOnly() {
  return {
    maintenance_window_enabled: qs("#bk-maint-enabled")?.checked !== false,
    maintenance_start_hour_utc: parseInt(qs("#bk-maint-start")?.value, 10) || 22,
    maintenance_end_hour_utc: parseInt(qs("#bk-maint-end")?.value, 10) || 6,
    maintenance_days: collectMaintenanceDays(),
  };
}

async function saveMaintenanceSettings() {
  if (!can("oxidized:write")) return;
  try {
    const payload = {
      ...(backupSettingsCache || {}),
      ...collectMaintenanceSettingsOnly(),
    };
    const saved = await api("/api/settings/backup", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    backupSettingsCache = saved;
    fillBackupSettingsForm(saved);
    showAlert("settings-alert", "Окно обслуживания сохранено", "success");
  } catch (e) {
    showAlert("settings-alert", e.message, "error");
  }
}

function collectBackupSettingsForm() {
  const encVal = qs("#bk-encrypt-password")?.value.trim();
  return {
    ...collectNotifySettingsForm(),
    binary_enabled: qs("#bk-binary")?.checked !== false,
    export_enabled: qs("#bk-export")?.checked !== false,
    hide_sensitive: qs("#bk-hide-sensitive")?.checked === true,
    encrypt_password: encVal || (backupSettingsCache?.encrypt_password_set ? SETTINGS_PASSWORD_MASK : ""),
    purge_enabled: qs("#bk-purge")?.checked !== false,
    mk_backup_git_push: qs("#bk-git-push")?.checked !== false,
    purge_keep: parseInt(qs("#bk-purge-keep")?.value, 10) || 10,
    bin_dir: qs("#bk-bin-dir")?.value.trim() || "/var/lib/oxidized/bin",
    rsc_dir: qs("#bk-rsc-dir")?.value.trim() || "/var/lib/oxidized/rsc",
    backup_timeout: parseInt(qs("#bk-timeout")?.value, 10) || 300,
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

function fillGitSettingsForm(cfg) {
  gitSettingsCache = cfg;
  if (qs("#git-remote-url")) qs("#git-remote-url").value = cfg.git_remote_url || "";
  if (qs("#git-branch")) qs("#git-branch").value = cfg.git_branch || "main";
  if (qs("#git-gitea-user")) qs("#git-gitea-user").value = cfg.gitea_http_user || "oauth2";
  if (qs("#git-commit-user")) qs("#git-commit-user").value = cfg.git_commit_user || "Oxidized";
  if (qs("#git-commit-email")) qs("#git-commit-email").value = cfg.git_commit_email || "";
  if (qs("#git-public-url")) qs("#git-public-url").value = cfg.oxidized_public_url || "";
  const giteaTok = qs("#git-gitea-token");
  if (giteaTok) {
    giteaTok.value = "";
    giteaTok.placeholder = cfg.gitea_token_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "Gitea personal access token";
  }
  const sourceTok = qs("#git-source-token");
  if (sourceTok) {
    sourceTok.value = "";
    sourceTok.placeholder = cfg.oxidized_source_token_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "Токен для /api/oxidized/source";
  }
}

function collectGitSettingsForm() {
  const giteaVal = qs("#git-gitea-token")?.value.trim();
  const sourceVal = qs("#git-source-token")?.value.trim();
  return {
    git_remote_url: qs("#git-remote-url")?.value.trim() || "",
    git_branch: qs("#git-branch")?.value.trim() || "main",
    gitea_http_user: qs("#git-gitea-user")?.value.trim() || "oauth2",
    git_commit_user: qs("#git-commit-user")?.value.trim() || "Oxidized",
    git_commit_email: qs("#git-commit-email")?.value.trim() || "oxidized@localhost",
    oxidized_public_url: qs("#git-public-url")?.value.trim() || "",
    gitea_token: giteaVal || (gitSettingsCache?.gitea_token_set ? SETTINGS_PASSWORD_MASK : ""),
    oxidized_source_token: sourceVal || (gitSettingsCache?.oxidized_source_token_set ? SETTINGS_PASSWORD_MASK : ""),
  };
}

async function loadGitSettings() {
  try {
    const cfg = await api("/api/settings/git");
    fillGitSettingsForm(cfg);
  } catch (e) {
    showAlert("settings-alert", `Git: ${e.message}`, "error");
  }
}

async function saveGitSettings(e) {
  e.preventDefault();
  if (!can("oxidized:write")) return;
  try {
    const saved = await api("/api/settings/git", {
      method: "PUT",
      body: JSON.stringify(collectGitSettingsForm()),
    });
    fillGitSettingsForm(saved);
    showAlert("settings-alert", "Настройки Git сохранены", "success");
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
  }
}

function fillScanSettingsForm(cfg) {
  scanSettingsCache = cfg;
  if (qs("#scan-concurrency")) qs("#scan-concurrency").value = cfg.scan_concurrency ?? 50;
  if (qs("#scan-discover-max")) qs("#scan-discover-max").value = cfg.discover_max_hosts ?? 4096;
  if (qs("#scan-ping-workers")) qs("#scan-ping-workers").value = cfg.discover_ping_workers ?? 100;
  if (qs("#scan-ovn-user")) qs("#scan-ovn-user").value = cfg.ovn_user || "satcoadm";
  if (qs("#scan-us-user")) qs("#scan-us-user").value = cfg.us_user || "satcoadm";
  const ovnPass = qs("#scan-ovn-pass");
  if (ovnPass) {
    ovnPass.value = "";
    ovnPass.placeholder = cfg.ovn_pass_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "OVN password";
  }
  const usPass = qs("#scan-us-pass");
  if (usPass) {
    usPass.value = "";
    usPass.placeholder = cfg.us_pass_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "US password";
  }
}

function collectScanSettingsForm() {
  const ovnVal = qs("#scan-ovn-pass")?.value.trim();
  const usVal = qs("#scan-us-pass")?.value.trim();
  return {
    scan_concurrency: parseInt(qs("#scan-concurrency")?.value, 10) || 50,
    discover_max_hosts: parseInt(qs("#scan-discover-max")?.value, 10) || 4096,
    discover_ping_workers: parseInt(qs("#scan-ping-workers")?.value, 10) || 100,
    ovn_user: qs("#scan-ovn-user")?.value.trim() || "satcoadm",
    ovn_pass: ovnVal || (scanSettingsCache?.ovn_pass_set ? SETTINGS_PASSWORD_MASK : ""),
    us_user: qs("#scan-us-user")?.value.trim() || "satcoadm",
    us_pass: usVal || (scanSettingsCache?.us_pass_set ? SETTINGS_PASSWORD_MASK : ""),
  };
}

async function loadScanSettings() {
  try {
    const cfg = await api("/api/settings/scan");
    fillScanSettingsForm(cfg);
  } catch (e) {
    showAlert("settings-alert", `Scan: ${e.message}`, "error");
  }
}

async function saveScanSettings(e) {
  e.preventDefault();
  if (!can("inventory:write")) return;
  try {
    const saved = await api("/api/settings/scan", {
      method: "PUT",
      body: JSON.stringify(collectScanSettingsForm()),
    });
    fillScanSettingsForm(saved);
    showAlert("settings-alert", "Настройки scan сохранены", "success");
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
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
    if (resultEl) {
      resultEl.textContent = "Отправка…";
      resultEl.className = "small mt-2 text-muted";
    }
    const res = await api("/api/settings/backup/test-notify", {
      method: "POST",
      body: JSON.stringify(collectNotifyTestPayload(kind)),
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

async function runDegradeCheckNow() {
  if (!can("oxidized:write")) return;
  const resultEl = qs("#notify-test-result");
  try {
    if (resultEl) resultEl.textContent = "Проверка деградации…";
    const res = await api("/api/settings/backup/degrade-check", { method: "POST" });
    const msg = res.skipped
      ? "Деградация: каналы уведомлений выключены"
      : `Проверка завершена, отправлено категорий: ${res.sent || 0}`;
    if (resultEl) {
      resultEl.textContent = msg;
      resultEl.className = "small mt-2 text-muted";
    }
    showAlert("settings-alert", msg, "success");
  } catch (e) {
    showAlert("settings-alert", e.message, "error");
  }
}

async function testComplianceReport() {
  if (!can("oxidized:write")) return;
  const resultEl = qs("#notify-test-result");
  try {
    if (resultEl) {
      resultEl.textContent = "Отправка compliance-отчёта…";
      resultEl.className = "small mt-2 text-muted";
    }
    const res = await api("/api/settings/backup/compliance-report-test", { method: "POST" });
    const text = (res.messages || []).join("; ");
    if (resultEl) {
      resultEl.textContent = text;
      resultEl.className = `small mt-2 ${res.ok ? "text-success" : "text-danger"}`;
    }
    showAlert("settings-alert", text || (res.ok ? "Отправлено" : "Ошибка"), res.ok ? "success" : "error");
    await loadBackupSettings();
  } catch (e) {
    if (resultEl) {
      resultEl.textContent = e.message;
      resultEl.className = "small mt-2 text-danger";
    }
    showAlert("settings-alert", e.message, "error");
  }
}

function mkTriStateValue(selectVal) {
  if (selectVal === "true") return true;
  if (selectVal === "false") return false;
  return null;
}

function mkTriStateLabel(val) {
  if (val === true) return "Вкл";
  if (val === false) return "Выкл";
  return "Наследовать";
}

function mkTriStateSelect(className, val, canEdit) {
  const disabled = canEdit ? "" : "disabled";
  return `
    <select class="form-control form-control-sm ${className}" ${disabled}>
      <option value="inherit"${val == null ? " selected" : ""}>Наследовать</option>
      <option value="true"${val === true ? " selected" : ""}>Вкл</option>
      <option value="false"${val === false ? " selected" : ""}>Выкл</option>
    </select>`;
}

function populateGroupPolicyModelSelect() {
  const sel = qs("#gp-model");
  if (!sel) return;
  const models = oxidizedSettingsCache?.available_models || ["routeros"];
  const current = sel.value;
  sel.innerHTML = '<option value="">—</option>' + models.map(m =>
    `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`
  ).join("");
  if (current) sel.value = current;
}

async function loadGroupPolicies() {
  if (!can("oxidized:read") && !can("oxidized:write")) return;
  try {
    const data = await api("/api/policies/groups");
    groupPoliciesCache = data.policies || [];
    renderGroupPolicies();
  } catch (e) {
    showAlert("settings-alert", `Политики: ${e.message}`, "error");
  }
}

function renderGroupPolicies() {
  const tbody = qs("#group-policies-table");
  const emptyEl = qs("#group-policies-empty");
  const canEdit = can("oxidized:write");
  if (!tbody) return;

  const policies = groupPoliciesCache || [];
  if (!policies.length) {
    tbody.innerHTML = "";
    if (emptyEl) emptyEl.style.display = "";
    return;
  }
  if (emptyEl) emptyEl.style.display = "none";

  const models = oxidizedSettingsCache?.available_models || ["routeros"];
  tbody.innerHTML = policies.map(p => {
    const modelOptions = ['<option value="">—</option>']
      .concat(models.map(m => `<option value="${escapeHtml(m)}"${m === (p.model || "") ? " selected" : ""}>${escapeHtml(m)}</option>`))
      .join("");
    return `
      <tr data-group="${escapeHtml(p.group_name)}">
        <td><code>${escapeHtml(p.group_name)}</code></td>
        <td>${canEdit
          ? `<input type="number" class="form-control form-control-sm gp-interval" min="0" max="604800" value="${p.backup_interval_sec || 0}">`
          : (p.backup_interval_sec || "глобальный")}
        </td>
        <td>${canEdit ? `<select class="form-control form-control-sm gp-model">${modelOptions}</select>` : escapeHtml(p.model || "—")}</td>
        <td>${canEdit ? mkTriStateSelect("gp-mk-binary", p.mk_binary_enabled, true) : escapeHtml(mkTriStateLabel(p.mk_binary_enabled))}</td>
        <td>${canEdit ? mkTriStateSelect("gp-mk-export", p.mk_export_enabled, true) : escapeHtml(mkTriStateLabel(p.mk_export_enabled))}</td>
        <td class="text-nowrap">
          ${canEdit ? `<button type="button" class="btn btn-primary btn-sm btn-save-gp" title="Сохранить"><i class="fas fa-save"></i></button>` : ""}
          ${canEdit ? `<button type="button" class="btn btn-danger btn-sm btn-delete-gp" title="Удалить"><i class="fas fa-trash"></i></button>` : ""}
        </td>
      </tr>`;
  }).join("");

  tbody.querySelectorAll(".btn-save-gp").forEach(btn => {
    btn.addEventListener("click", () => saveGroupPolicyRow(btn.closest("tr")));
  });
  tbody.querySelectorAll(".btn-delete-gp").forEach(btn => {
    btn.addEventListener("click", async () => {
      const row = btn.closest("tr");
      const group = row?.dataset.group;
      if (!group || !confirm(`Удалить политику для «${group}»?`)) return;
      try {
        await api(`/api/policies/groups/${encodeURIComponent(group)}`, { method: "DELETE" });
        showAlert("settings-alert", `Политика ${group} удалена`, "success");
        await loadGroupPolicies();
      } catch (e) {
        showAlert("settings-alert", e.message, "error");
      }
    });
  });
}

async function saveGroupPolicyRow(row) {
  if (!row || !can("oxidized:write")) return;
  const group = row.dataset.group;
  const payload = {
    group_name: group,
    backup_interval_sec: parseInt(row.querySelector(".gp-interval")?.value, 10) || 0,
    model: row.querySelector(".gp-model")?.value || "",
    mk_binary_enabled: mkTriStateValue(row.querySelector(".gp-mk-binary")?.value),
    mk_export_enabled: mkTriStateValue(row.querySelector(".gp-mk-export")?.value),
  };
  try {
    await api("/api/policies/groups", { method: "PUT", body: JSON.stringify(payload) });
    showAlert("settings-alert", `Политика ${group} сохранена`, "success");
    await loadGroupPolicies();
  } catch (e) {
    showAlert("settings-alert", e.message, "error");
  }
}

async function saveGroupPolicyForm(e) {
  e.preventDefault();
  if (!can("oxidized:write")) return;
  const payload = {
    group_name: qs("#gp-group")?.value.trim(),
    backup_interval_sec: parseInt(qs("#gp-interval")?.value, 10) || 0,
    model: qs("#gp-model")?.value || "",
    mk_binary_enabled: mkTriStateValue(qs("#gp-mk-binary")?.value),
    mk_export_enabled: mkTriStateValue(qs("#gp-mk-export")?.value),
  };
  if (!payload.group_name) return;
  try {
    await api("/api/policies/groups", { method: "PUT", body: JSON.stringify(payload) });
    showAlert("settings-alert", `Политика ${payload.group_name} сохранена`, "success");
    qs("#group-policy-form")?.reset();
    if (qs("#gp-interval")) qs("#gp-interval").value = "0";
    await loadGroupPolicies();
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
  }
}

async function runBackupData() {
  if (!can("users:manage")) return;
  const resultEl = qs("#backup-data-result");
  try {
    if (resultEl) resultEl.textContent = "Копирование…";
    const res = await api("/api/admin/backup-data", { method: "POST" });
    const msg = res.ok ? `OK → ${res.path}` : `Ошибка: ${res.database || "unknown"}`;
    if (resultEl) {
      resultEl.textContent = msg;
      resultEl.className = `small ms-2 ${res.ok ? "text-success" : "text-danger"}`;
    }
    showAlert("settings-alert", msg, res.ok ? "success" : "error");
  } catch (e) {
    if (resultEl) resultEl.textContent = e.message;
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
  el.innerHTML = `<span class="${cls}"><i class="fas fa-${icon} me-1"></i>${escapeHtml(result.message)}</span>`;
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
    const model = p.model || groupModels[p.group_name] || oxidizedSettingsCache?.default_model || "routeros";
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
        <i class="fas fa-exclamation-triangle me-1"></i>
        Нет профиля для группы «${group}».
        <a href="#" class="device-goto-settings">Добавить в настройках</a>
      </span>`;
    hint.querySelector(".device-goto-settings")?.addEventListener("click", e => {
      e.preventDefault();
      hideModal("device-modal");
      navigateToSettingsTab("groups");
    });
    return;
  }

  const pass = canSeePass ? profile.password : "********";
  hint.innerHTML = `
    <span class="cred-preview text-muted">
      <i class="fas fa-key me-1"></i>
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
      ? '<i class="fas fa-edit me-2 text-muted"></i>Изменить устройство'
      : '<i class="fas fa-plus me-2 text-muted"></i>Добавить устройство';
  }

  updateGroupSelects(device?.group || getGroupNames()[0]);

  qs("#device-name").value = device?.name || "";
  qs("#device-name").disabled = !!name;
  qs("#device-ip").value = device?.ip || "";
  populateDeviceModelSelect(device?.model || "routeros");
  if (device?.group) qs("#device-group").value = device.group;
  qs("#device-ports").value = (device?.ports || [44333]).join(", ");
  qs("#device-enabled").checked = device ? device.enabled : true;
  if (qs("#device-site")) qs("#device-site").value = device?.site || "";
  if (qs("#device-role")) qs("#device-role").value = device?.role || "";
  if (qs("#device-critical")) qs("#device-critical").checked = !!device?.critical;
  if (qs("#device-maintenance")) qs("#device-maintenance").checked = !!device?.maintenance;
  syncDeviceEnabledLabel();
  updateDeviceGroupHint();
  showModal("device-modal");
}

function closeDeviceModal() {
  hideModal("device-modal");
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
    site: qs("#device-site")?.value.trim() || "",
    role: qs("#device-role")?.value.trim() || "",
    critical: qs("#device-critical")?.checked === true,
    maintenance: qs("#device-maintenance")?.checked === true,
  };

  if (!device.name || !device.ip) {
    showAlert("inventory-alert", "Имя и IP обязательны", "error");
    return;
  }

  try {
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
  } catch (e) {
    showAlert("inventory-alert", e.message, "error");
  }
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
    phaseBadge.className = `${badgeCls(
      status.status === "failed" ? "danger"
        : status.status === "completed" ? "success"
          : "info"
    )} scan-phase-badge`;
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
      loadScanHistory();
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
      `<span class="me-2"><span class="port-dot ${p.open ? "port-open" : "port-closed"}"></span>${p.port}</span>`
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
          ${smallBox(health.engine_title || (health.engine === "python" ? "Python" : "Ruby"), "Движок", "bg-secondary", "fa-server", "text-sm")}
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

    const modelsWarning = qs("#oxidized-models-warning");
    if (modelsWarning) {
      if (health.models === "python-fallback" && isPythonEngine()) {
        modelsWarning.style.display = "";
        modelsWarning.innerHTML =
          '<i class="fas fa-exclamation-triangle me-1"></i> Ruby bridge недоступен — бэкап только для модели <strong>routeros</strong>.';
      } else {
        modelsWarning.style.display = "none";
        modelsWarning.innerHTML = "";
      }
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
    const showMikrotik = isPythonEngine() && isRouterOsModel(n.model);
    return `
      <tr>
        <td><strong>${escapeHtml(n.name)}</strong></td>
        <td>${escapeHtml(n.ip || "—")}</td>
        <td><span class="oxidized-model-label" title="${escapeHtml(n.model || "")}">${escapeHtml(formatOxidizedModelLabel(n.model || ""))}</span></td>
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
          ${showMikrotik ? `<button class="btn btn-outline-secondary btn-sm btn-show-backups" data-name="${escapeHtml(n.name)}" title="MikroTik binary / export"><i class="fas fa-archive"></i></button>` : ""}
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

let oxidizedVersionsCache = { name: null, versions: [] };
let oxidizedDiffState = { name: null, oid: null, oid2: null, mode: "unified", patch: "" };

function updateVersionsCompareButton() {
  const btn = qs("#btn-versions-compare");
  if (!btn) return;
  const checked = qsa("#oxidized-versions-table .version-compare-cb:checked");
  btn.disabled = checked.length !== 2;
  const n = checked.length;
  btn.innerHTML = n === 2
    ? '<i class="fas fa-columns me-1"></i> Сравнить side-by-side'
    : `<i class="fas fa-columns me-1"></i> Сравнить (${n}/2)`;
  qsa("#oxidized-versions-table tr").forEach(row => row.classList.remove("version-row-selected"));
  checked.forEach(cb => cb.closest("tr")?.classList.add("version-row-selected"));
}

async function showNodeVersions(name) {
  const loading = qs("#oxidized-versions-loading");
  const wrap = qs("#oxidized-versions-table-wrap");
  const emptyEl = qs("#oxidized-versions-empty");
  qs("#oxidized-versions-node").textContent = name;
  if (loading) loading.style.display = "";
  if (wrap) wrap.style.display = "none";
  if (emptyEl) emptyEl.style.display = "none";
  updateVersionsCompareButton();
  showModal("oxidized-versions-modal");
  try {
    const data = await api(`/api/oxidized/nodes/${encodeURIComponent(name)}/versions`);
    oxidizedVersionsCache = { name, versions: data.versions || [] };
    qs("#oxidized-versions-node").textContent = data.group
      ? `${data.node} (${data.group})`
      : data.node;
    const webLink = qs("#oxidized-versions-open-web");
    if (webLink) {
      const proxyPath = data.versions_proxy_url
        || (data.node_full
          ? `/oxidized-proxy/node/version?node_full=${encodeURIComponent(data.node_full)}`
          : "");
      if (proxyPath.startsWith("/api/oxidized/")) {
        webLink.style.display = "none";
      } else if (proxyPath) {
        webLink.style.display = "";
        webLink.href = `${window.location.origin}${proxyPath}`;
      } else {
        webLink.style.display = "none";
      }
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
          <td><input type="checkbox" class="version-compare-cb" data-oid="${escapeHtml(v.oid || "")}"></td>
          <td>${v.num}</td>
          <td>${formatDate(v.time)}</td>
          <td><code class="small">${escapeHtml(String(v.oid || "").slice(0, 12))}</code></td>
          <td class="text-right text-nowrap">
            <button type="button" class="btn btn-outline-secondary btn-sm btn-view-config" data-name="${escapeHtml(name)}" data-url="${escapeHtml(v.view_url)}" data-label="${escapeHtml(formatDate(v.time))}" title="Просмотр версии">
              <i class="fas fa-eye"></i>
            </button>
            ${v.diff_url ? `
              <button type="button" class="btn btn-outline-primary btn-sm btn-open-diff" data-name="${escapeHtml(name)}" data-url="${escapeHtml(v.diff_url)}" data-oid="${escapeHtml(v.oid || "")}" title="Diff с предыдущей">
                <i class="fas fa-file-diff"></i> Diff
              </button>
            ` : `<span class="text-muted small">—</span>`}
          </td>
        </tr>
      `).join("");

      tbody.querySelectorAll(".version-compare-cb").forEach(cb => {
        cb.addEventListener("change", () => {
          const all = [...tbody.querySelectorAll(".version-compare-cb:checked")];
          if (all.length > 2) {
            cb.checked = false;
          }
          updateVersionsCompareButton();
        });
      });
      tbody.querySelectorAll(".btn-open-diff").forEach(btn => {
        btn.addEventListener("click", () => {
          openOxidizedDiff(btn.dataset.name, btn.dataset.url, btn.dataset.oid);
        });
      });
      tbody.querySelectorAll(".btn-view-config").forEach(btn => {
        btn.addEventListener("click", () => {
          openOxidizedConfigView(btn.dataset.name, btn.dataset.url, btn.dataset.label);
        });
      });
      updateVersionsCompareButton();
    }
  } catch (e) {
    hideModal("oxidized-versions-modal");
    showAlert("oxidized-alert", e.message, "error");
  } finally {
    if (loading) loading.style.display = "none";
    if (wrap) wrap.style.display = "";
  }
}

function renderDiffPanelContent(patch, query) {
  const panel = qs("#oxidized-diff-panel");
  if (!panel) return;
  const q = (query || "").trim().toLowerCase();
  const lines = (patch || "").split("\n");
  const html = lines.map(line => {
    const cls = line.startsWith("+") && !line.startsWith("+++")
      ? "diff-line-add"
      : line.startsWith("-") && !line.startsWith("---")
        ? "diff-line-del"
        : line.startsWith("@@") ? "diff-line-hunk" : "";
    const hit = q && line.toLowerCase().includes(q);
    return `<div class="diff-line ${cls}${hit ? " diff-line-hit" : ""}">${escapeHtml(line)}</div>`;
  }).join("");
  panel.innerHTML = html || '<div class="text-muted p-3">Пустой diff</div>';
}

function setDiffSubtitle(name, oid, oid2, mode) {
  const el = qs("#oxidized-diff-subtitle");
  if (!el) return;
  const parts = [];
  if (oid) parts.push(`oid ${String(oid).slice(0, 12)}`);
  if (oid2) parts.push(`↔ ${String(oid2).slice(0, 12)}`);
  const modeLabel = mode === "side_by_side" ? "side-by-side" : "unified";
  el.textContent = parts.length ? `${name} · ${parts.join(" ")} · ${modeLabel}` : "";
}

async function loadInAppDiff(name, oid, oid2, mode) {
  const panel = qs("#oxidized-diff-panel");
  const iframe = qs("#oxidized-diff-iframe");
  if (!panel) return;
  oxidizedDiffState = { name, oid, oid2, mode, patch: "" };
  setDiffSubtitle(name, oid, oid2, mode);
  if (iframe) iframe.style.display = "none";
  panel.style.display = "block";
  panel.innerHTML = '<div class="text-muted p-3"><i class="fas fa-spinner fa-spin"></i> Загрузка…</div>';

  const base = `/api/oxidized/nodes/${encodeURIComponent(name)}/diff`;
  let url;
  if (mode === "side_by_side" && oid2) {
    url = `${base}?oid=${encodeURIComponent(oid)}&oid2=${encodeURIComponent(oid2)}&format=side_by_side`;
    const res = await fetch(url, { credentials: "include" });
    if (!res.ok) throw new Error(await res.text());
    panel.innerHTML = await res.text();
    return;
  }
  url = `${base}?oid=${encodeURIComponent(oid)}${oid2 ? `&oid2=${encodeURIComponent(oid2)}` : ""}&format=text`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(await res.text());
  const patch = await res.text();
  oxidizedDiffState.patch = patch;
  renderDiffPanelContent(patch, qs("#oxidized-diff-search")?.value);
}

function openOxidizedDiff(name, diffUrl, oid = null) {
  const iframe = qs("#oxidized-diff-iframe");
  const panel = qs("#oxidized-diff-panel");
  const openTab = qs("#oxidized-diff-open-tab");
  qs("#oxidized-diff-node").textContent = name;
  const fullUrl = diffUrl.startsWith("http")
    ? diffUrl
    : `${window.location.origin}${diffUrl}`;

  const useInApp = fullUrl.includes("/api/oxidized/") && oxidizedEngine === "python";
  if (useInApp && oid) {
    const u = new URL(fullUrl);
    const oid2 = u.searchParams.get("oid2");
    loadInAppDiff(name, oid, oid2, oxidizedDiffState.mode || "unified").catch(e => {
      showAlert("oxidized-alert", e.message, "error");
    });
    if (openTab) openTab.href = fullUrl;
    showModal("oxidized-diff-modal");
    return;
  }

  if (panel) panel.style.display = "none";
  if (iframe) {
    iframe.style.display = "block";
    iframe.setAttribute("src", fullUrl);
  }
  if (openTab) openTab.href = fullUrl;
  showModal("oxidized-diff-modal");
}

function closeOxidizedDiffModal() {
  const iframe = qs("#oxidized-diff-iframe");
  const panel = qs("#oxidized-diff-panel");
  if (iframe) iframe.setAttribute("src", "about:blank");
  if (panel) panel.innerHTML = "";
  oxidizedDiffState = { name: null, oid: null, oid2: null, mode: "unified", patch: "" };
}

async function compareSelectedVersions() {
  const checked = [...qsa("#oxidized-versions-table .version-compare-cb:checked")];
  if (checked.length !== 2 || !oxidizedVersionsCache.name) return;
  const oids = checked.map(cb => cb.dataset.oid).filter(Boolean);
  if (oids.length !== 2) return;
  const [oidNew, oidOld] = oids;
  oxidizedDiffState.mode = "side_by_side";
  qs("#btn-diff-side")?.classList.add("active");
  qs("#btn-diff-unified")?.classList.remove("active");
  hideModal("oxidized-versions-modal");
  qs("#oxidized-diff-node").textContent = oxidizedVersionsCache.name;
  try {
    await loadInAppDiff(oxidizedVersionsCache.name, oidNew, oidOld, "side_by_side");
    const openTab = qs("#oxidized-diff-open-tab");
    if (openTab) {
      openTab.href = `${window.location.origin}/api/oxidized/nodes/${encodeURIComponent(oxidizedVersionsCache.name)}/diff?oid=${encodeURIComponent(oidNew)}&oid2=${encodeURIComponent(oidOld)}&format=side_by_side`;
    }
    showModal("oxidized-diff-modal");
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

function classifyOxidizedLogLine(line) {
  const lower = line.toLowerCase();
  if (/error|fail|exception|fatal|unable|no_connection|authenticationfailed/.test(lower)) {
    return "log-error";
  }
  if (/warn|warning|retry/.test(lower)) return "log-warn";
  if (/success|stored|updated|configuration updated|finished|pushed|mikrotik \| (binary|export) backup/.test(lower)) {
    return "log-ok";
  }
  return "";
}

function filterOxidizedLogLines(lines, level) {
  if (!lines || level === "all") return lines || [];
  return lines.filter(line => {
    const cls = classifyOxidizedLogLine(line);
    if (level === "error") return cls === "log-error";
    if (level === "warn") return cls === "log-warn";
    if (level === "ok") return cls === "log-ok";
    return true;
  });
}

function updateOxidizedLogsSearchBanner() {
  const banner = qs("#oxidized-logs-search-banner");
  if (!banner) return;
  const q = globalSearchQuery.trim();
  if (q) {
    banner.style.display = "";
    banner.innerHTML =
      `<i class="fas fa-search me-1"></i> Активен глобальный поиск: <code>${escapeHtml(q)}</code> — очищает фильтр в navbar`;
  } else {
    banner.style.display = "none";
    banner.innerHTML = "";
  }
}

function paintOxidizedLogViewer(lines) {
  const viewer = qs("#oxidized-log-viewer");
  if (!viewer) return;
  if (!lines.length) {
    const levelHint = oxidizedLogsLevelFilter !== "all" ? ` (фильтр: ${oxidizedLogsLevelFilter})` : "";
    viewer.textContent = globalSearchQuery.trim()
      ? `Нет строк, подходящих под фильтр${levelHint}`
      : oxidizedLogsLevelFilter !== "all"
        ? `Нет строк уровня «${oxidizedLogsLevelFilter}»`
        : "Лог пуст";
    return;
  }
  viewer.innerHTML = lines
    .map(line => {
      const cls = classifyOxidizedLogLine(line);
      return cls ? `<span class="${cls}">${escapeHtml(line)}</span>` : escapeHtml(line);
    })
    .join("\n");
  if (oxidizedLogsStickToBottom) {
    viewer.scrollTop = viewer.scrollHeight;
  }
}

function renderOxidizedLogs(data) {
  const badge = qs("#oxidized-logs-count");
  const engineBadge = qs("#oxidized-log-engine");
  const pathEl = qs("#oxidized-logs-path");
  const truncatedEl = qs("#oxidized-logs-truncated");

  if (!data || typeof data !== "object") {
    const viewer = qs("#oxidized-log-viewer");
    if (viewer) {
      viewer.textContent = typeof data === "string" && data.trim()
        ? data.trim()
        : "Пустой ответ API логов";
    }
    if (badge) badge.style.display = "none";
    return;
  }

  oxidizedLogsRawData = data;
  updateOxidizedLogsSearchBanner();

  if (pathEl) {
    if (data.path) {
      pathEl.textContent = data.path;
      pathEl.title = data.path;
      pathEl.style.display = "";
    } else {
      pathEl.textContent = "";
      pathEl.style.display = "none";
    }
  }
  if (truncatedEl) {
    truncatedEl.style.display = data.truncated ? "inline" : "none";
  }

  if (engineBadge) {
    if (data.engine_title) {
      engineBadge.textContent = data.engine_title;
      engineBadge.style.display = "inline";
    } else {
      engineBadge.style.display = "none";
    }
  }

  if (!data.available) {
    paintOxidizedLogViewer([]);
    const viewer = qs("#oxidized-log-viewer");
    if (viewer) viewer.textContent = data.error || "Лог недоступен";
    if (badge) badge.style.display = "none";
    updateOxidizedLogBtnBadge(data);
    return;
  }

  const allLines = data.lines || [];
  const lines = filterOxidizedLogLines(allLines, oxidizedLogsLevelFilter);
  paintOxidizedLogViewer(lines);

  if (badge) {
    if (allLines.length) {
      badge.style.display = "inline";
      const shown = lines.length;
      const suffix = oxidizedLogsLevelFilter !== "all" ? ` / ${shown}` : "";
      badge.textContent = data.truncated
        ? `${data.returned}+${suffix}`
        : `${data.returned}${suffix}`;
    } else {
      badge.style.display = "none";
    }
  }

  updateOxidizedLogBtnBadge(data);
}

function updateOxidizedLogBtnBadge(data) {
  const btnBadge = qs("#oxidized-logs-btn-badge");
  if (!btnBadge) return;
  const lines = data.lines || [];
  if (lines.length && data.available) {
    btnBadge.style.display = "inline";
    btnBadge.textContent = data.truncated ? `${data.returned}+` : String(data.returned);
    const hasError = lines.some(line => classifyOxidizedLogLine(line) === "log-error");
    btnBadge.className = `${badgeCls(hasError ? "danger" : "secondary")} ms-1`;
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

let oxidizedLogsSearchQuery = "";

function openOxidizedLogsModal(prefill = "") {
  oxidizedLogsSearchQuery = prefill || "";
  oxidizedLogsStickToBottom = true;
  updateOxidizedLogsSearchBanner();
  const viewer = qs("#oxidized-log-viewer");
  if (viewer) viewer.textContent = "Загрузка…";
  showModal("oxidized-logs-modal");
  // Не полагаемся только на shown.bs.modal (стек модалок / анимация fade).
  startOxidizedLogsPolling();
}

function setOxidizedLogsLevelFilter(level) {
  oxidizedLogsLevelFilter = level;
  qsa("#oxidized-logs-level-filter [data-level]").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.level === level);
  });
  if (oxidizedLogsRawData) renderOxidizedLogs(oxidizedLogsRawData);
}

async function copyOxidizedLogs() {
  const viewer = qs("#oxidized-log-viewer");
  const btn = qs("#btn-copy-oxidized-logs");
  if (!viewer) return;
  const text = viewer.innerText || viewer.textContent || "";
  try {
    await navigator.clipboard.writeText(text);
    if (btn) {
      const icon = btn.innerHTML;
      btn.innerHTML = '<i class="fas fa-check text-success"></i>';
      window.setTimeout(() => { btn.innerHTML = icon; }, 1500);
    }
  } catch (e) {
    showAlert("oxidized-alert", "Не удалось скопировать: " + e.message, "error");
  }
}

async function loadOxidizedLogs() {
  const params = new URLSearchParams({ lines: "500" });
  const q = oxidizedLogsSearchQuery.trim() || globalSearchQuery.trim();
  if (q) params.set("q", q);
  const viewer = qs("#oxidized-log-viewer");
  try {
    const data = await api(`/api/oxidized/logs?${params}`);
    try {
      renderOxidizedLogs(data);
    } catch (renderErr) {
      if (viewer) viewer.textContent = `Ошибка отображения: ${renderErr.message}`;
    }
  } catch (e) {
    if (viewer) viewer.textContent = e.message || "Не удалось загрузить лог";
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

let oxidizedConfigModalNode = null;

async function openOxidizedConfigInModal(name, viewUrl, label, model) {
  oxidizedConfigModalNode = name;
  const titleEl = qs("#oxidized-config-modal-node");
  if (titleEl) {
    titleEl.textContent = label ? `${name} · ${label}` : name;
  }
  try {
    let text;
    if (viewUrl) {
      text = await api(viewUrl);
    } else {
      const data = await api(`/api/oxidized/nodes/${encodeURIComponent(name)}`);
      text = typeof data === "string" ? data : (data.full || JSON.stringify(data, null, 2));
    }
    const nodeModel = model || oxidizedNodesCache.find(n => n.name === name)?.model;
    if (window.ConfigEditor) {
      ConfigEditor.setContent("oxidized-config-modal-content", text || "Пустой конфиг", { model: nodeModel });
    } else {
      const el = qs("#oxidized-config-modal-content");
      if (el) el.value = text || "Пустой конфиг";
    }
    showModal("oxidized-config-modal");
    window.setTimeout(() => window.ConfigEditor?.refreshAll(), 120);
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  }
}

async function showNodeConfig(name, model) {
  await openOxidizedConfigInModal(name, null, null, model);
}

async function openOxidizedConfigView(name, viewUrl, label) {
  await openOxidizedConfigInModal(name, viewUrl, label);
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
        <i class="fas fa-download me-1"></i>${escapeHtml(f.name)}
      </a>
      <span class="text-muted small ms-2">${formatBytes(f.size)} · ${formatDate(f.mtime ? new Date(f.mtime * 1000).toISOString() : null)}</span>
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
  const loading = qs("#oxidized-backups-loading");
  const content = qs("#oxidized-backups-content");
  const emptyHint = qs("#oxidized-backups-empty-hint");
  const runBtn = qs("#btn-run-mikrotik-backup");
  qs("#oxidized-backups-node").textContent = name;
  if (runBtn) {
    runBtn.dataset.name = name;
    runBtn.style.display = isPythonEngine() && can("oxidized:write") ? "" : "none";
  }
  if (loading) loading.style.display = "";
  if (content) content.style.display = "none";
  if (emptyHint) emptyHint.style.display = "none";
  qs("#oxidized-backups-bin").innerHTML = "";
  qs("#oxidized-backups-rsc").innerHTML = "";
  showModal("oxidized-backups-modal");
  await loadNodeBackupFiles(name);
}

async function loadNodeBackupFiles(name) {
  const loading = qs("#oxidized-backups-loading");
  const content = qs("#oxidized-backups-content");
  const emptyHint = qs("#oxidized-backups-empty-hint");
  try {
    const data = await api(`/api/oxidized/nodes/${encodeURIComponent(name)}/backups`);
    const binFiles = data.backups?.binary || [];
    const rscFiles = data.backups?.export || [];
    qs("#oxidized-backups-bin").innerHTML = renderBackupFileList(name, "bin", binFiles);
    qs("#oxidized-backups-rsc").innerHTML = renderBackupFileList(name, "rsc", rscFiles);
    if (loading) loading.style.display = "none";
    if (content) content.style.display = "";
    if (emptyHint) {
      emptyHint.style.display =
        isPythonEngine() && !binFiles.length && !rscFiles.length ? "" : "none";
    }
  } catch (e) {
    if (loading) loading.style.display = "none";
    hideModal("oxidized-backups-modal");
    showAlert("oxidized-alert", e.message, "error");
  }
}

async function runMikrotikBackupForNode(name) {
  if (!can("oxidized:write") || !name) return;
  const runBtn = qs("#btn-run-mikrotik-backup");
  if (runBtn) runBtn.disabled = true;
  try {
    await api(`/api/oxidized/nodes/${encodeURIComponent(name)}/backups/run`, { method: "POST" });
    showAlert("oxidized-alert", `MikroTik backup для ${name} выполнен`, "success");
    await loadNodeBackupFiles(name);
  } catch (e) {
    showAlert("oxidized-alert", e.message, "error");
  } finally {
    if (runBtn) runBtn.disabled = false;
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
  bindMaintenanceDayToggles();
  initSettingsTabs();
  window.addEventListener("hashchange", handleRouteHash);
  const addDeviceBtn = qs("#btn-add-device");
  if (addDeviceBtn) addDeviceBtn.addEventListener("click", () => openDeviceModal());

  qs("#device-group")?.addEventListener("change", updateDeviceGroupHint);
  qs("#device-enabled")?.addEventListener("change", syncDeviceEnabledLabel);
  qs("#btn-device-goto-settings")?.addEventListener("click", () => {
    hideModal("device-modal");
    navigateToSettingsTab("groups");
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
  qs("#git-settings-form")?.addEventListener("submit", saveGitSettings);
  qs("#device-maintenance-settings-link")?.addEventListener("click", e => {
    e.preventDefault();
    hideModal("device-modal");
    navigateToSettingsTab("service");
  });

  qs("#btn-save-maintenance")?.addEventListener("click", saveMaintenanceSettings);
  qs("#scan-settings-form")?.addEventListener("submit", saveScanSettings);
  qs("#notify-settings-form")?.addEventListener("submit", saveNotifySettings);
  qs("#audit-action-filter")?.addEventListener("change", () => loadAudit());
  qs("#btn-test-notify-report")?.addEventListener("click", () => testBackupNotify("report"));
  qs("#btn-test-notify-error")?.addEventListener("click", () => testBackupNotify("error"));
  qs("#btn-test-notify-degrade")?.addEventListener("click", () => testBackupNotify("degrade"));
  qs("#btn-test-compliance-report")?.addEventListener("click", testComplianceReport);
  qs("#btn-degrade-check-now")?.addEventListener("click", runDegradeCheckNow);
  qs("#btn-compliance-export")?.addEventListener("click", exportComplianceCsv);
  qs("#btn-compliance-apply")?.addEventListener("click", () => loadComplianceDashboard());
  qs("#group-policy-form")?.addEventListener("submit", saveGroupPolicyForm);
  qs("#btn-backup-data")?.addEventListener("click", runBackupData);
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
  qs("#btn-copy-oxidized-logs")?.addEventListener("click", copyOxidizedLogs);
  qsa("#oxidized-logs-level-filter [data-level]").forEach(btn => {
    btn.addEventListener("click", () => setOxidizedLogsLevelFilter(btn.dataset.level));
  });
  qs("#oxidized-backups-goto-settings")?.addEventListener("click", e => {
    e.preventDefault();
    hideModal("oxidized-backups-modal");
    navigateToSettingsTab("backup");
  });
  qs("#oxidized-backups-goto-logs")?.addEventListener("click", e => {
    e.preventDefault();
    hideModal("oxidized-backups-modal");
    navigateToPage("oxidized");
    window.setTimeout(() => openOxidizedLogsModal("mikrotik"), 300);
  });
  qs("#btn-run-mikrotik-backup")?.addEventListener("click", () => {
    const name = qs("#btn-run-mikrotik-backup")?.dataset.name;
    if (name) runMikrotikBackupForNode(name);
  });
  onModalEvent("oxidized-logs-modal", "hidden.bs.modal", stopOxidizedLogsPolling);
  qs("#btn-oxidized-iframe-reload")?.addEventListener("click", () => loadOxidizedIframe(true));
  qs("#btn-oxidized-iframe-nodes")?.addEventListener("click", () => navigateOxidizedIframe("/nodes"));
  qs("#btn-oxidized-config-versions")?.addEventListener("click", () => {
    if (!oxidizedConfigModalNode) return;
    hideModal("oxidized-config-modal");
    showNodeVersions(oxidizedConfigModalNode);
  });
  onModalEvent("oxidized-diff-modal", "hidden.bs.modal", closeOxidizedDiffModal);
  qs("#btn-versions-compare")?.addEventListener("click", compareSelectedVersions);
  qs("#oxidized-diff-search")?.addEventListener("input", () => {
    if (oxidizedDiffState.patch) {
      renderDiffPanelContent(oxidizedDiffState.patch, qs("#oxidized-diff-search")?.value);
    }
  });
  qs("#btn-diff-search-clear")?.addEventListener("click", () => {
    const input = qs("#oxidized-diff-search");
    if (input) input.value = "";
    if (oxidizedDiffState.patch) renderDiffPanelContent(oxidizedDiffState.patch, "");
  });
  qs("#btn-diff-unified")?.addEventListener("click", async () => {
    qs("#btn-diff-unified")?.classList.add("active");
    qs("#btn-diff-side")?.classList.remove("active");
    if (oxidizedDiffState.name && oxidizedDiffState.oid) {
      oxidizedDiffState.mode = "unified";
      try {
        await loadInAppDiff(oxidizedDiffState.name, oxidizedDiffState.oid, oxidizedDiffState.oid2, "unified");
      } catch (e) {
        showAlert("oxidized-alert", e.message, "error");
      }
    }
  });
  qs("#btn-diff-side")?.addEventListener("click", async () => {
    qs("#btn-diff-side")?.classList.add("active");
    qs("#btn-diff-unified")?.classList.remove("active");
    if (!oxidizedDiffState.oid2) {
      showAlert("oxidized-alert", "Side-by-side: выберите две версии в истории", "warning");
      return;
    }
    oxidizedDiffState.mode = "side_by_side";
    try {
      await loadInAppDiff(oxidizedDiffState.name, oxidizedDiffState.oid, oxidizedDiffState.oid2, "side_by_side");
    } catch (e) {
      showAlert("oxidized-alert", e.message, "error");
    }
  });
  onModalEvent("oxidized-config-modal", "shown.bs.modal", () => window.ConfigEditor?.refreshAll());
  qs("#oxidized-logs-autorefresh")?.addEventListener("change", () => {
    if (isModalOpen("oxidized-logs-modal")) {
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
    handleRouteHash();
  } catch {
    showLogin();
  }
}

init();
