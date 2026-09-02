const API = "";
let inventory = null;
let editingDeviceName = null;
let editingNetworkKey = null;
let oxidizedPublicUrl = "http://localhost:8888";
let oxidizedProxyUrl = "/oxidized-proxy/nodes";
let oxidizedEngine = "python";
let oxidizedModels = ["routeros"];
let vendorCatalog = {};
const OXIDIZED_PROXY_PREFIX = "/oxidized-proxy";
let currentUser = null;
let scanPollTimer = null;
let globalSearchQuery = "";
let lastScanSummary = null;
let oxidizedNodesCache = [];
let usersCache = [];
let customRolesCache = [];
let rbacPermissionsCache = [];
let oxidizedLogsTimer = null;
let oxidizedLogsStickToBottom = true;
let oxidizedLogsLevelFilter = "all";
let oxidizedLogsRawData = null;
let oxidizedSettingsCache = null;
let groupPoliciesCache = [];
const SETTINGS_TAB_STORAGE_KEY = "backup-tools-settings-tab";
let settingsStateBaseline = "";
const selectedDeviceNames = new Set();

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
  security: "Безопасность конфигов",
  provision: "Провижионинг",
};

const SECURITY_SEVERITY_BADGE = {
  critical: "danger",
  high: "danger",
  medium: "warning",
  low: "info",
  info: "secondary",
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
function qsa(sel) { return Array.from(document.querySelectorAll(sel)); }

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

function tableLoadingRow(colSpan, text = "Загрузка данных…") {
  return `<tr class="table-loading"><td colspan="${colSpan}" class="text-center text-muted table-loading-td loading-spinner-row"><i class="fas fa-spinner fa-spin me-1" aria-hidden="true"></i>${escapeHtml(text)}<span class="loading-dots"></span></td></tr>`;
}

/* Блокировка кнопки + спиннер */
function setBtnLoading(btn, on) {
  if (!btn) return;
  btn.classList.toggle("btn-loading", !!on);
  btn.disabled = !!on;
  if (on) btn.setAttribute("aria-busy", "true");
  else btn.removeAttribute("aria-busy");
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

function updateLocationHash(hash) {
  const next = hash.startsWith("#") ? hash : `#${hash}`;
  if (location.hash === next) return;
  history.replaceState(null, "", next);
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
    integrations: "settings-tab-integrations",
    system: "settings-tab-system",
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
    updateLocationHash(`settings/${short}`);
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
    link.addEventListener("hide.bs.tab", e => {
      if (!isSettingsDirty()) return;
      if (!confirm("Есть несохранённые изменения. Переключить вкладку без сохранения?")) {
        e.preventDefault();
      }
    });
    link.addEventListener("shown.bs.tab", e => {
      const id = e.target.getAttribute("href")?.slice(1);
      if (!id) return;
      try { localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, id); } catch {}
      const short = id.replace("settings-tab-", "");
      updateLocationHash(`settings/${short}`);
      updateSettingsDirtyUi();
    });
  });
  qsa("#page-settings input, #page-settings select, #page-settings textarea").forEach(el => {
    el.addEventListener("input", updateSettingsDirtyUi);
    el.addEventListener("change", updateSettingsDirtyUi);
  });
}

function getSettingsStatePayload() {
  const parts = {};
  if (qs("#oxidized-settings-form")) parts.oxidized = collectOxidizedSettingsForm();
  if (qs("#backup-settings-form")) parts.backup = collectBackupSettingsForm();
  if (qs("#git-settings-form")) {
    parts.git = {
      git_remote_url: qs("#git-remote-url")?.value,
      git_branch: qs("#git-branch")?.value,
      git_gitea_user: qs("#git-gitea-user")?.value,
      git_commit_user: qs("#git-commit-user")?.value,
      git_commit_email: qs("#git-commit-email")?.value,
      git_public_url: qs("#git-public-url")?.value,
    };
  }
  if (qs("#notify-settings-form")) parts.notify = collectNotifySettingsForm();
  if (qs("#ldap-settings-form")) {
    parts.ldap = {
      enabled: qs("#ldap-enabled")?.checked,
      server: qs("#ldap-server")?.value,
      directory_type: qs("#ldap-directory-type")?.value,
    };
  }
  if (qs("#scan-settings-form")) {
    parts.scan = {
      scan_concurrency: qs("#scan-concurrency")?.value,
      scan_discover_max: qs("#scan-discover-max")?.value,
      schedule_enabled: qs("#scan-schedule-enabled")?.checked,
    };
  }
  parts.maintenance = collectMaintenanceSettingsOnly();
  if (qs("#system-settings-form")) parts.system = collectSystemSettingsForm();
  return JSON.stringify(parts);
}

function refreshSettingsBaseline() {
  settingsStateBaseline = getSettingsStatePayload();
  updateSettingsDirtyUi();
}

function isSettingsDirty() {
  if (!settingsStateBaseline || !qs("#page-settings") || qs("#page-settings").classList.contains("d-none")) {
    return false;
  }
  return getSettingsStatePayload() !== settingsStateBaseline;
}

function updateSettingsDirtyUi() {
  const banner = qs("#settings-unsaved-banner");
  if (!banner) return;
  banner.classList.toggle("d-none", !isSettingsDirty());
}

function markSettingsSaved() {
  refreshSettingsBaseline();
}

function navigateToSettingsTab(tabId, opts = {}) {
  const id = normalizeSettingsTabId(tabId);
  if (id) {
    const short = id.replace("settings-tab-", "");
    updateLocationHash(`settings/${short}`);
  }
  navigateToPage("settings");
  window.setTimeout(() => {
    activateSettingsTab(tabId, { scroll: true, updateHash: false, ...opts });
  }, 150);
}

function handleRouteHash() {
  const h = location.hash.replace(/^#/, "");
  if (!h) return;

  if (h === "settings" || h.startsWith("settings/")) {
    if (!currentUser) return;
    navigateToPage("settings");
    return;
  }
  const pages = ["dashboard", "inventory", "scan", "oxidized", "oxidized-ui", "security", "provision", "audit", "users"];
  if (pages.includes(h)) {
    navigateToPage(h);
  }
}

function currentAppPage() {
  const h = location.hash.replace(/^#/, "");
  if (!h || h === "settings" || h.startsWith("settings/")) {
    return h.startsWith("settings") ? "settings" : "dashboard";
  }
  const pages = ["dashboard", "inventory", "scan", "oxidized", "oxidized-ui", "security", "provision", "audit", "users"];
  return pages.includes(h) ? h : "dashboard";
}

function syncAppRouteFromHash() {
  if (!currentUser) return;
  const h = location.hash.replace(/^#/, "");
  if (!h) {
    navigateToPage("dashboard");
    updateLocationHash("dashboard");
    return;
  }
  handleRouteHash();
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
  for (const t of device.tags || []) {
    if (t) tags.push(`<span class="${badgeCls("info", "badge-tag")}">${escapeHtml(t)}</span>`);
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
  const theme = smallBoxTheme(bg).replace(/^text-bg-/, "");
  const valueCls = valueClass ? ` ${valueClass}` : "";
  return `
    <div class="col-xl-2 col-lg-4 col-md-4 col-sm-6 col-12">
      <div class="kpi-card kpi-card--${theme}">
        <div class="kpi-card__icon" aria-hidden="true"><i class="fas ${icon}"></i></div>
        <div class="kpi-card__content">
          <div class="kpi-card__value${valueCls}">${value}</div>
          <div class="kpi-card__label">${label}</div>
        </div>
      </div>
    </div>
  `;
}

const dashboardStatsState = {
  warningHtml: "",
  platform: [],
  scan: [],
  compliance: [],
  sites: [],
};

function dashboardStatItem(label, value, tone = "") {
  return { label, value, tone };
}

function dashboardStatValueHtml(value, tone) {
  if (typeof value === "string" && value.includes("<")) return value;
  const cls = tone ? `dashboard-stat-value dashboard-stat-value--${tone}` : "dashboard-stat-value";
  return `<span class="${cls}">${escapeHtml(String(value))}</span>`;
}

function renderDashboardStatsTable() {
  const tbody = qs("#dashboard-stats-table-body");
  if (!tbody) return;

  const sections = [
    { key: "platform", title: "Платформа" },
    { key: "scan", title: "Сканирование" },
    { key: "compliance", title: "Compliance" },
  ];

  const rows = [];
  for (const sec of sections) {
    const items = dashboardStatsState[sec.key] || [];
    if (!items.length) continue;
    items.forEach((item, idx) => {
      rows.push(`
        <tr>
          <td class="dashboard-stats-group">${idx === 0 ? escapeHtml(sec.title) : ""}</td>
          <td class="dashboard-stats-label">${escapeHtml(item.label)}</td>
          <td class="text-end">${dashboardStatValueHtml(item.value, item.tone)}</td>
        </tr>
      `);
    });
  }

  tbody.innerHTML = rows.length
    ? rows.join("")
    : `<tr><td colspan="3" class="text-muted text-center py-3">Нет данных</td></tr>`;

  const warnEl = qs("#dashboard-warnings");
  if (warnEl) warnEl.innerHTML = dashboardStatsState.warningHtml || "";

  const siteCard = qs("#dashboard-compliance-by-site-card");
  const siteBody = qs("#dashboard-compliance-by-site-table");
  const sites = dashboardStatsState.sites || [];
  if (siteCard && siteBody) {
    if (sites.length) {
      siteCard.classList.remove("d-none");
      siteBody.innerHTML = sites.map(s => `
        <tr>
          <td><strong>${escapeHtml(s.site)}</strong></td>
          <td class="text-end">${s.ok}</td>
          <td class="text-end">${s.total}</td>
          <td class="text-end">${s.failed}</td>
          <td class="text-end">${s.critical}</td>
          <td class="text-end"><span class="${badgeCls(s.compliance_pct >= 90 ? "success" : s.compliance_pct >= 70 ? "warning" : "danger")}">${s.compliance_pct}%</span></td>
        </tr>
      `).join("");
    } else {
      siteCard.classList.add("d-none");
      siteBody.innerHTML = "";
    }
  }
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
  el.setAttribute("role", "status");
  el.setAttribute("aria-live", type === "error" ? "assertive" : "polite");
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
  const info = vendorCatalog[model];
  if (info) return !!info.mikrotik_binary;
  const key = String(model || "").toLowerCase().replace(/[\s_-]/g, "");
  return key === "routeros" || key === "mikrotik" || key === "ros" || key.startsWith("mikrotik");
}

function nativePythonModels() {
  const fromCatalog = Object.entries(vendorCatalog)
    .filter(([, info]) => info.native_python)
    .map(([id]) => id);
  return fromCatalog.length ? fromCatalog : ["routeros", "ios", "junos", "eos"];
}

function defaultPortsForModel(model) {
  const info = vendorCatalog[model];
  if (info?.default_ports?.length) return info.default_ports;
  if (isRouterOsModel(model)) return [44333, 22];
  return [22];
}

function nativeModelsHintHtml() {
  return nativePythonModels().map(m => `<strong>${escapeHtml(m)}</strong>`).join(", ");
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
        loadRbacMatrix().then(() => loadCustomRoles());
        loadUsers();
        refreshTotpSettings();
      }
      if (page === "scan") {
        resumeScanIfRunning();
        loadScanHistory();
      }
      if (page === "audit") loadAudit();
      if (page === "security") loadSecurityAudit();
      if (page === "provision") loadProvisionPage();
      if (page === "dashboard") loadHealth();
      if (page === "settings") {
        loadSettings().then(() => {
          activateSettingsTab(resolveInitialSettingsTab(), { updateHash: true });
        });
      } else {
        updateLocationHash(page);
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
  if (data.totp_required) {
    showLoginTotpStep(data.challenge, data.user?.username || username);
    return;
  }
  await completeLogin(data);
}

function showLoginTotpStep(challenge, username) {
  const block = qs("#login-totp-block");
  const challengeEl = qs("#login-totp-challenge");
  const codeEl = qs("#login-totp-code");
  const recoveryEl = qs("#login-recovery-code");
  if (block) block.style.display = "";
  if (challengeEl) challengeEl.value = challenge || "";
  if (codeEl) {
    codeEl.value = "";
    codeEl.focus();
  }
  if (recoveryEl) recoveryEl.value = "";
  showAlert("login-alert", `2FA: ${username}`, "info");
}

async function verifyLoginTotp() {
  const challenge = qs("#login-totp-challenge")?.value;
  const code = qs("#login-totp-code")?.value.trim();
  const recovery_code = qs("#login-recovery-code")?.value.trim();
  if (!challenge) throw new Error("Нет challenge 2FA — войдите снова");
  const data = await api("/api/auth/totp", {
    method: "POST",
    body: JSON.stringify({ challenge, code, recovery_code }),
  });
  const block = qs("#login-totp-block");
  if (block) block.style.display = "none";
  await completeLogin(data);
}

async function completeLogin(data) {
  currentUser = data.user;
  showApp();
  syncAppRouteFromHash();
  bootstrapApp(window.__uiConfig).catch(err => {
    console.error("bootstrap failed", err);
  });
  if (currentUser?.must_change_password) {
    showPasswordChangeModal();
  }
}

function showPasswordChangeModal() {
  const cur = qs("#pw-change-current");
  const neu = qs("#pw-change-new");
  if (cur) cur.value = "";
  if (neu) neu.value = "";
  showModal("password-change-modal");
}

async function submitPasswordChange(e) {
  e.preventDefault();
  try {
    await api("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: qs("#pw-change-current").value,
        new_password: qs("#pw-change-new").value,
      }),
    });
    currentUser = await api("/api/auth/me");
    hideModal("password-change-modal");
    showAlert("settings-alert", "Пароль обновлён", "success");
  } catch (err) {
    showAlert("password-change-alert", err.message, "error");
  }
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch {}
  history.replaceState(null, "", location.pathname + location.search);
  showLogin();
}

async function loadRbacMatrix() {
  const table = qs("#rbac-matrix-table tbody");
  const theadRow = qs("#rbac-matrix-table thead tr");
  if (!table) return;
  try {
    const data = await api("/api/auth/rbac");
    const roles = data.roles || [];
    rbacPermissionsCache = data.permissions || [];
    const roleIds = roles.map(r => r.id);
    if (theadRow) {
      theadRow.innerHTML = `<th>Право</th>${roles.map(r =>
        `<th class="text-center small" title="${escapeHtml(r.description || "")}">${escapeHtml(r.label || r.id)}</th>`
      ).join("")}`;
    }
    table.innerHTML = (data.permissions || []).map(perm => {
      const cells = roleIds.map(rid => {
        const role = roles.find(r => r.id === rid);
        const ok = role?.permissions?.includes(perm.id);
        return `<td class="text-center">${ok ? '<i class="fas fa-check text-success"></i>' : '<i class="fas fa-times text-muted"></i>'}</td>`;
      }).join("");
      return `<tr><td>${escapeHtml(perm.label)}<br><code class="small">${escapeHtml(perm.id)}</code></td>${cells}</tr>`;
    }).join("");
    renderCustomRolePermissionPicker();
  } catch {
    table.innerHTML = `<tr><td colspan="4" class="text-muted">Нет доступа к матрице RBAC</td></tr>`;
  }
}

function renderCustomRolePermissionPicker() {
  const box = qs("#cr-permissions-picker");
  if (!box) return;
  if (!rbacPermissionsCache.length) {
    box.innerHTML = '<span class="text-muted small">Загрузите матрицу RBAC для выбора permissions</span>';
    return;
  }
  box.innerHTML = `<div class="row g-1">${rbacPermissionsCache.map(p => `
    <div class="col-lg-4 col-md-6">
      <label class="form-check small mb-0">
        <input type="checkbox" class="form-check-input cr-perm-check" value="${escapeHtml(p.id)}">
        <span class="form-check-label">${escapeHtml(p.label)}</span>
      </label>
    </div>`).join("")}</div>`;
}

function customRoleSelectOptions(selectedId) {
  const opts = ['<option value="">— встроенная —</option>'];
  for (const r of customRolesCache) {
    if (r.is_system) continue;
    const sel = selectedId === r.id ? " selected" : "";
    opts.push(`<option value="${r.id}"${sel}>${escapeHtml(r.label)} (${escapeHtml(r.slug)})</option>`);
  }
  return opts.join("");
}

function selectedCustomRolePermissions() {
  return [...qsa("#cr-permissions-picker .cr-perm-check:checked")].map(el => el.value);
}

function renderCustomRolesTable() {
  const tbody = qs("#custom-roles-table tbody");
  if (!tbody) return;
  if (!customRolesCache.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">Нет пользовательских ролей</td></tr>';
    return;
  }
  tbody.innerHTML = customRolesCache.map(r => `
    <tr data-role-id="${r.id}">
      <td><code>${escapeHtml(r.slug)}</code>${r.is_system ? ' <span class="badge bg-secondary">system</span>' : ""}</td>
      <td>${escapeHtml(r.label)}<div class="small text-muted">${escapeHtml(r.description || "")}</div></td>
      <td class="small"><code>${escapeHtml((r.permissions || []).join(", "))}</code></td>
      <td class="text-nowrap">
        ${r.is_system ? "—" : `<button type="button" class="btn btn-danger btn-sm btn-delete-custom-role" data-id="${r.id}"><i class="fas fa-trash"></i></button>`}
      </td>
    </tr>`).join("");

  tbody.querySelectorAll(".btn-delete-custom-role").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm("Удалить пользовательскую роль?")) return;
      try {
        await api(`/api/auth/custom-roles/${btn.dataset.id}`, { method: "DELETE" });
        showAlert("users-alert", "Роль удалена", "success");
        await loadCustomRoles();
        loadRbacMatrix();
      } catch (e) {
        showAlert("users-alert", e.message, "error");
      }
    });
  });
}

async function loadCustomRoles() {
  const panel = qs("#custom-roles-table");
  if (!panel) return;
  try {
    const data = await api("/api/auth/custom-roles");
    customRolesCache = data.items || [];
    renderCustomRolesTable();
    if (!rbacPermissionsCache.length) {
      try {
        const rbac = await api("/api/auth/rbac");
        rbacPermissionsCache = rbac.permissions || [];
        renderCustomRolePermissionPicker();
      } catch {}
    }
    if (usersCache?.length) renderUsersTable(usersCache);
  } catch {}
}

async function loadUsers() {
  try {
    usersCache = await api("/api/auth/users");
    if (!customRolesCache.length) {
      try {
        const cr = await api("/api/auth/custom-roles");
        customRolesCache = cr.items || [];
      } catch { /* optional */ }
    }
    renderUsersTable(usersCache);
  } catch (e) {
    showAlert("users-alert", e.message, "error");
  }
}

let totpSetupPending = null;

async function loadNetboxTopology() {
  const host = qs("#topology-preview");
  const alertId = "settings-alert";
  if (!host) return;
  host.innerHTML = `<span class="text-muted"><i class="fas fa-spinner fa-spin"></i> Загрузка…</span>`;
  try {
    const data = await api("/api/inventory/topology/netbox");
    const nodes = data.nodes?.length || 0;
    const edges = data.edges?.length || 0;
    const edgeList = (data.edges || []).slice(0, 50).map(e =>
      `<li><code>${escapeHtml(e.source)}</code> ↔ <code>${escapeHtml(e.target)}</code>${e.label ? ` <span class="text-muted">(${escapeHtml(e.label)})</span>` : ""}</li>`
    ).join("");
    const edgesHtml = edges
      ? `<ul class="small mb-0">${edgeList}${edges > 50 ? `<li class="text-muted">… ещё ${edges - 50}</li>` : ""}</ul>`
      : "<p class=\"text-muted mb-0\">Связи не найдены</p>";
    host.innerHTML = `
      <p class="mb-1"><strong>${nodes}</strong> узлов, <strong>${edges}</strong> связей (NetBox cables)</p>
      ${edgesHtml}
    `;
  } catch (e) {
    host.innerHTML = `<span class="text-danger">${escapeHtml(e.message)}</span>`;
    showAlert(alertId, e.message, "error");
  }
}

async function refreshTotpSettings() {
  const card = qs("#totp-settings-card");
  if (!card || !currentUser) return;
  let me;
  try {
    me = await api("/api/auth/me");
  } catch {
    return;
  }
  const status = qs("#totp-status-text");
  const beginBtn = qs("#btn-totp-begin");
  const setupPanel = qs("#totp-setup-panel");
  const disablePanel = qs("#totp-disable-panel");
  if (!me.totp_available) {
    if (status) status.textContent = "2FA доступна только для локальных пользователей.";
    if (beginBtn) beginBtn.style.display = "none";
    if (setupPanel) setupPanel.style.display = "none";
    if (disablePanel) disablePanel.style.display = "none";
    return;
  }
  if (me.totp_enabled) {
    if (status) status.textContent = "2FA включена для вашей учётной записи.";
    if (beginBtn) beginBtn.style.display = "none";
    if (setupPanel) setupPanel.style.display = "none";
    if (disablePanel) disablePanel.style.display = "";
  } else {
    if (status) status.textContent = "2FA не включена.";
    if (beginBtn) beginBtn.style.display = "";
    if (setupPanel) setupPanel.style.display = "none";
    if (disablePanel) disablePanel.style.display = "none";
  }
}

async function beginTotpSetup() {
  totpSetupPending = await api("/api/auth/totp/setup");
  const uriEl = qs("#totp-uri");
  const recoveryEl = qs("#totp-recovery-codes");
  if (uriEl) uriEl.textContent = totpSetupPending.provisioning_uri || "";
  if (recoveryEl) {
    recoveryEl.textContent = (totpSetupPending.recovery_codes || []).join("\n");
    recoveryEl.style.display = "";
  }
  const beginBtn = qs("#btn-totp-begin");
  const setupPanel = qs("#totp-setup-panel");
  if (beginBtn) beginBtn.style.display = "none";
  if (setupPanel) setupPanel.style.display = "";
  const codeEl = qs("#totp-enable-code");
  if (codeEl) {
    codeEl.value = "";
    codeEl.focus();
  }
}

async function confirmTotpEnable() {
  if (!totpSetupPending?.secret) throw new Error("Сначала начните настройку 2FA");
  const code = qs("#totp-enable-code")?.value.trim();
  if (!code) throw new Error("Введите код из приложения");
  await api("/api/auth/totp/enable", {
    method: "POST",
    body: JSON.stringify({
      secret: totpSetupPending.secret,
      code,
      recovery_codes: totpSetupPending.recovery_codes || [],
    }),
  });
  totpSetupPending = null;
  showAlert("users-alert", "2FA включена. Сохраните recovery codes — они больше не отобразятся.", "success");
  await refreshTotpSettings();
}

async function disableTotp() {
  await api("/api/auth/totp/disable", {
    method: "POST",
    body: JSON.stringify({
      password: qs("#totp-disable-password")?.value || "",
      code: qs("#totp-disable-code")?.value.trim() || "",
    }),
  });
  const pwd = qs("#totp-disable-password");
  const code = qs("#totp-disable-code");
  if (pwd) pwd.value = "";
  if (code) code.value = "";
  showAlert("users-alert", "2FA отключена", "success");
  await refreshTotpSettings();
}

function renderUsersTable(users) {
  const tbody = qs("#users-table");
  if (!tbody) return;
  const query = globalSearchQuery;
  const filtered = (users || []).filter(u =>
    matchesSearch([u.username, u.role, u.auth_source, u.is_active ? "active" : "inactive"], query)
  );

  if (!users?.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted">Нет пользователей</td></tr>`;
    return;
  }
  if (!filtered.length) {
    tbody.innerHTML = searchEmptyRow(9, query);
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
          <option value="compliance_auditor" ${u.role === "compliance_auditor" ? "selected" : ""}>compliance_auditor</option>
          <option value="operator" ${u.role === "operator" ? "selected" : ""}>operator</option>
          <option value="admin" ${u.role === "admin" ? "selected" : ""}>admin</option>
        </select>
      </td>
      <td>
        <select class="form-control form-control-sm user-custom-role-select" data-id="${u.id}" ${u.id === currentUser.id ? "disabled" : ""}>
          ${customRoleSelectOptions(u.custom_role_id)}
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
    ? `<input type="checkbox" class="user-role-locked" data-id="${u.id}" ${u.role_locked ? "checked" : ""} title="Не обновлять роль из LDAP">
       <input type="checkbox" class="user-scope-locked" data-id="${u.id}" ${u.scope_locked ? "checked" : ""} title="Не обновлять scope из LDAP">`
    : "—"}
      </td>
      <td class="text-center">
        <input type="checkbox" class="user-active-check" data-id="${u.id}" ${u.is_active ? "checked" : ""} ${u.id === currentUser.id ? "disabled" : ""}>
      </td>
      <td class="text-nowrap">
        ${u.role !== "admin" ? `<button type="button" class="btn btn-primary btn-sm btn-save-user-scope" data-id="${u.id}" title="Сохранить scope"><i class="fas fa-save"></i></button>` : ""}
        ${u.id !== currentUser.id ? `    <button class="btn btn-danger btn-sm btn-delete-user" data-id="${u.id}" title="Удалить пользователя" aria-label="Удалить пользователя"><i class="fas fa-trash"></i></button>` : "—"}
      </td>
    </tr>
  `;
  }).join("");

  tbody.querySelectorAll(".user-custom-role-select").forEach(sel => {
    sel.addEventListener("change", async () => {
      const val = sel.value;
      try {
        await api(`/api/auth/users/${sel.dataset.id}`, {
          method: "PUT",
          body: JSON.stringify(
            val
              ? { custom_role_id: parseInt(val, 10) }
              : { custom_role_id: 0, clear_custom_role: true }
          ),
        });
        showAlert("users-alert", "Custom RBAC обновлён", "success");
        loadUsers();
      } catch (e) {
        showAlert("users-alert", e.message, "error");
        loadUsers();
      }
    });
  });

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

  tbody.querySelectorAll(".user-scope-locked").forEach(chk => {
    chk.addEventListener("change", async () => {
      try {
        await api(`/api/auth/users/${chk.dataset.id}`, {
          method: "PUT",
          body: JSON.stringify({ scope_locked: chk.checked }),
        });
        showAlert("users-alert", "Фиксация scope обновлена", "success");
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

async function loadHealth(opts = {}) {
  const { includeCompliance = true } = opts;
  try {
    const [health, oxHealth, trends] = await Promise.all([
      api("/health"),
      api("/api/oxidized/health").catch(() => ({ reachable: false })),
      api("/api/scan/trends?days=30").catch(() => ({ points: [] })),
    ]);

    dashboardStatsState.warningHtml = "";
    if (oxHealth.models === "python-fallback") {
      dashboardStatsState.warningHtml = `
        <div class="alert alert-warning py-2 mb-0">
          <i class="fas fa-exclamation-triangle me-1"></i>
          Ruby bridge недоступен — без gem доступны Python-модели: ${nativeModelsHintHtml()}. Остальные — через Ruby Oxidized.
        </div>`;
    }

    const latest = trends.latest || {};
    dashboardStatsState.platform = [
      dashboardStatItem("Устройств в inventory", health.inventory_devices ?? "—"),
      dashboardStatItem("Подсетей", health.networks ?? "—"),
      dashboardStatItem(
        "Oxidized",
        oxHealth.reachable ? "OK" : "OFF",
        oxHealth.reachable ? "success" : "danger",
      ),
      dashboardStatItem("Узлов Oxidized", oxHealth.nodes_count || 0),
    ];
    dashboardStatsState.scan = [
      dashboardStatItem("Online (последний scan)", latest.online ?? "—", "success"),
      dashboardStatItem("Offline (последний scan)", latest.offline ?? "—", "danger"),
      dashboardStatItem("Последний scan", formatDate(health.last_scan) || "—"),
    ];

    const updatedEl = qs("#dashboard-stats-updated");
    if (updatedEl) updatedEl.textContent = formatDate(new Date().toISOString());

    renderDashboardStatsTable();
    renderScanTrends(trends);
    if (includeCompliance) {
      await loadComplianceDashboard();
    }
  } catch (e) {
    showAlert("dashboard-alert", e.message, "error");
  }
}

function complianceBySiteFromNodes(nodes) {
  const buckets = {};
  for (const node of nodes || []) {
    const site = (node.site || "").trim() || "(без site)";
    const bucket = buckets[site] || { site, total: 0, ok: 0, failed: 0, critical: 0 };
    bucket.total += 1;
    if (node.state === "ok") bucket.ok += 1;
    else bucket.failed += 1;
    if (node.critical) bucket.critical += 1;
    buckets[site] = bucket;
  }
  return Object.values(buckets)
    .sort((a, b) => a.site.localeCompare(b.site, undefined, { sensitivity: "base" }))
    .map(bucket => ({
      ...bucket,
      compliance_pct: bucket.total ? Math.round((100 * bucket.ok) / bucket.total * 10) / 10 : 100,
    }));
}

function complianceFilterQuery() {
  const params = new URLSearchParams();
  const site = qs("#cf-site")?.value.trim();
  const role = qs("#cf-role")?.value.trim();
  const group = qs("#cf-group")?.value.trim();
  const state = qs("#cf-state")?.value.trim();
  const critical = qs("#cf-critical")?.value.trim();
  const tags = qs("#cf-tags")?.value.trim();
  if (site) params.set("site", site);
  if (role) params.set("role", role);
  if (group) params.set("group", group);
  if (state) params.set("state", state);
  if (critical) params.set("critical", critical);
  if (tags) params.set("tags", tags);
  const q = params.toString();
  return q ? `?${q}` : "";
}

function inventoryLocalFilters() {
  const site = qs("#inv-filter-site")?.value.trim().toLowerCase();
  const group = qs("#inv-filter-group")?.value.trim().toLowerCase();
  const tagList = (qs("#inv-filter-tags")?.value || "").split(",").map(t => t.trim().toLowerCase()).filter(Boolean);
  return { site, group, tagList };
}

function deviceMatchesInventoryFilters(device) {
  const { site, group, tagList } = inventoryLocalFilters();
  if (site && !(device.site || "").toLowerCase().includes(site)) return false;
  if (group && !(device.group || "").toLowerCase().includes(group)) return false;
  if (tagList.length) {
    const dt = new Set((device.tags || []).map(t => String(t).toLowerCase()));
    if (!tagList.some(t => dt.has(t))) return false;
  }
  return true;
}

async function refreshSiteDatalists() {
  try {
    const data = await api("/api/sites");
    const options = (data.sites || []).map(s =>
      `<option value="${escapeHtml(s.slug)}">${escapeHtml(s.name || s.slug)}</option>`
    ).join("");
    const cf = qs("#cf-site-list");
    const inv = qs("#inv-site-list");
    if (cf) cf.innerHTML = options;
    if (inv) inv.innerHTML = options;
  } catch {}
}

async function loadComplianceDashboard() {
  const compliance = await api(`/api/compliance/summary${complianceFilterQuery()}`).catch(() => null);
  if (!compliance) return;

  const counts = compliance.counts || {};
  const pct = compliance.compliance_pct ?? 0;
  dashboardStatsState.compliance = [
    dashboardStatItem("Compliance", `${pct}%`, pct >= 90 ? "success" : pct >= 70 ? "warning" : "danger"),
    dashboardStatItem("OK", counts.ok || 0, "success"),
    dashboardStatItem("Ошибки бэкапа", counts.failed || 0, counts.failed ? "danger" : ""),
    dashboardStatItem("Просрочено", counts.overdue || 0, counts.overdue ? "warning" : ""),
    dashboardStatItem(`Stale >${compliance.stale_days_threshold}д`, counts.stale || 0, counts.stale ? "warning" : ""),
    dashboardStatItem("Offline", counts.unreachable || 0, counts.unreachable ? "danger" : ""),
    dashboardStatItem("Нет бэкапа", counts.never || 0, counts.never ? "secondary" : ""),
  ];
  dashboardStatsState.sites = complianceBySiteFromNodes(compliance.nodes);
  renderDashboardStatsTable();

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
  await downloadComplianceExport("csv");
}

async function exportCompliancePdf() {
  await downloadComplianceExport("pdf");
}

async function downloadComplianceExport(format) {
  try {
    const q = complianceFilterQuery();
    const sep = q ? "&" : "?";
    const res = await fetch(`/api/compliance/export${q}${sep}format=${format}`, { credentials: "include" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const blob = await res.blob();
    const cd = res.headers.get("content-disposition") || "";
    const match = cd.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : `compliance.${format}`;
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

async function sendComplianceReport() {
  try {
    const res = await fetch(`/api/compliance/report/send${complianceFilterQuery()}`, {
      method: "POST",
      credentials: "include",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.message || data.detail || res.statusText);
    const msg = (data.messages || []).join("; ") || "Отправлено";
    showAlert("dashboard-alert", msg, data.ok ? "success" : "warning");
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

function securityFilterQuery() {
  const params = new URLSearchParams();
  const severity = qs("#security-severity-filter")?.value;
  const ack = qs("#security-ack-filter")?.value;
  if (severity) params.set("severity", severity);
  if (ack) params.set("acknowledged", ack);
  const q = params.toString();
  return q ? `?${q}` : "";
}

function securityFindingsQuery(offset = 0) {
  const params = new URLSearchParams(securityFilterQuery().replace(/^\?/, ""));
  params.set("limit", "50");
  params.set("offset", String(Math.max(0, offset)));
  const q = params.toString();
  return q ? `?${q}` : "";
}

let securityFindingsOffset = 0;
let securityAuditLoadSeq = 0;

function renderSecurityFindingsRows(findings) {
  const tbody = qs("#security-findings-table");
  const empty = qs("#security-findings-empty");
  if (!tbody) return;
  if (!findings.length) {
    tbody.innerHTML = "";
    if (empty) empty.style.display = "";
    return;
  }
  if (empty) empty.style.display = "none";
  tbody.innerHTML = findings.map(f => `
    <tr data-finding-id="${f.id}">
      <td><span class="${badgeCls(SECURITY_SEVERITY_BADGE[f.severity] || "secondary")}">${escapeHtml(f.severity)}</span></td>
      <td><strong>${escapeHtml(f.device_name)}</strong><div class="text-muted small">${escapeHtml(f.device_model || "")}</div></td>
      <td>${escapeHtml(f.device_ip || "—")}</td>
      <td>${escapeHtml(f.category)}</td>
      <td>
        <div>${escapeHtml(f.title)}</div>
        <code class="small text-muted">${escapeHtml(f.rule_id)}</code>
        ${f.remediation ? `<div class="small text-muted mt-1">${escapeHtml(f.remediation)}</div>` : ""}
      </td>
      <td class="text-sm"><code>${escapeHtml(f.evidence || "—")}</code>${f.line_number ? ` <span class="text-muted">:${f.line_number}</span>` : ""}</td>
      <td class="text-nowrap">
        ${f.acknowledged
    ? `<span class="${badgeCls("success", "badge-tag")}">ack</span>`
    : (can("security:run")
      ? `<button type="button" class="btn btn-outline-success btn-sm btn-security-ack" data-id="${f.id}" title="Подтвердить"><i class="fas fa-check"></i></button>`
      : "")}
      </td>
    </tr>
  `).join("");

  tbody.querySelectorAll(".btn-security-ack").forEach(btn => {
    btn.addEventListener("click", async () => {
      try {
        await api(`/api/security/audit/findings/${btn.dataset.id}/ack`, {
          method: "POST",
          body: JSON.stringify({ acknowledged: true }),
        });
        loadSecurityAudit({ keepOffset: true });
      } catch (e) {
        showAlert("security-alert", e.message, "error");
      }
    });
  });
}

function updateSecurityFindingsPager(total, offset, limit) {
  const pager = qs("#security-findings-pager");
  const meta = qs("#security-findings-pager-meta");
  const prev = qs("#btn-security-findings-prev");
  const next = qs("#btn-security-findings-next");
  if (!pager) return;
  if (!total) {
    pager.style.display = "none";
    return;
  }
  pager.style.display = "";
  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  if (meta) meta.textContent = `Показано ${from}–${to} из ${total}`;
  if (prev) prev.disabled = offset <= 0;
  if (next) next.disabled = offset + limit >= total;
}

let provisionTemplatesCache = [];
let editingProvisionTemplateId = null;
let provisionFiltersCache = { groups: [], sites: [], models: [], devices: [] };

function resetProvisionTemplateForm() {
  editingProvisionTemplateId = null;
  const slugEl = qs("#pt-slug");
  const nameEl = qs("#pt-name");
  const bodyEl = qs("#pt-body");
  if (slugEl) {
    slugEl.value = "";
    slugEl.readOnly = false;
    slugEl.classList.remove("bg-light");
  }
  if (nameEl) nameEl.value = "";
  if (bodyEl) bodyEl.value = "";
  qs("#btn-prov-template-create")?.classList.remove("d-none");
  qs("#btn-prov-template-save")?.classList.add("d-none");
  qs("#btn-prov-template-cancel")?.classList.add("d-none");
  const title = qs("#prov-template-panel-title");
  if (title) title.textContent = "Новый шаблон";
}

function openProvisionTemplateEditor(t) {
  if (!t) return;
  editingProvisionTemplateId = t.id;
  const slugEl = qs("#pt-slug");
  if (slugEl) {
    slugEl.value = t.slug;
    slugEl.readOnly = true;
    slugEl.classList.add("bg-light");
  }
  qs("#pt-name").value = t.name;
  if (qs("#pt-model")) qs("#pt-model").value = t.model;
  qs("#pt-body").value = t.body;
  qs("#btn-prov-template-create")?.classList.add("d-none");
  qs("#btn-prov-template-save")?.classList.remove("d-none");
  qs("#btn-prov-template-cancel")?.classList.remove("d-none");
  const title = qs("#prov-template-panel-title");
  if (title) title.textContent = `Редактирование: ${t.slug}`;
  qs("#provision-template-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function saveProvisionTemplate() {
  if (!editingProvisionTemplateId) return;
  const name = qs("#pt-name")?.value?.trim();
  const body = qs("#pt-body")?.value;
  if (!name || !body?.trim()) {
    showAlert("provision-alert", "Заполните название и тело шаблона", "error");
    return;
  }
  await api(`/api/provisioning/templates/${editingProvisionTemplateId}`, {
    method: "PUT",
    body: JSON.stringify({
      name,
      model: qs("#pt-model")?.value?.trim() || "routeros",
      body,
    }),
  });
  showAlert("provision-alert", "Шаблон сохранён", "success");
  resetProvisionTemplateForm();
  loadProvisionPage();
}

function fillProvisionFilterSelect(selId, items, { allLabel = "все" } = {}) {
  const sel = qs(selId);
  if (!sel) return;
  const current = sel.value;
  const normalized = (items || []).map(it => {
    if (typeof it === "string") return { id: it, label: it };
    return { id: it.id, label: it.label || it.id };
  });
  const opts = normalized
    .map(it => `<option value="${escapeHtml(it.id)}">${escapeHtml(it.label)}</option>`)
    .join("");
  sel.innerHTML = `<option value="">${escapeHtml(allLabel)}</option>${opts}`;
  if (current && normalized.some(it => it.id === current)) sel.value = current;
}

function fillProvisionFilterSelects(filters) {
  if (filters) provisionFiltersCache = filters;
  const f = provisionFiltersCache;
  fillProvisionFilterSelect("#prov-gen-group", f.groups);
  fillProvisionFilterSelect("#prov-gen-site", f.sites);
  fillProvisionFilterSelect("#prov-gen-model", f.models);
  fillProvisionFilterSelect("#prov-bulk-group", f.groups);
  fillProvisionFilterSelect("#prov-bulk-site", f.sites);
  fillProvisionFilterSelect("#prov-bulk-model", f.models);
  const ptModel = qs("#pt-model");
  if (ptModel?.tagName === "SELECT") {
    const models = f.template_models?.length ? f.template_models : f.models;
    fillProvisionFilterSelect("#pt-model", models?.length ? models : [{ id: "routeros", label: "routeros" }], { allLabel: "—" });
    if (!ptModel.value || ptModel.value === "все") {
      const defaultModel = models?.find(m => (m.id || m) === "routeros")?.id || models?.[0]?.id || "routeros";
      ptModel.value = defaultModel;
    }
  }
}

function provisionDevicesForTemplate(templateId) {
  const devices = provisionFiltersCache.devices?.length
    ? provisionFiltersCache.devices
    : (inventory?.devices || []).filter(d => d.enabled);
  if (!templateId) return devices;
  const tpl = provisionTemplatesCache.find(t => t.id === templateId);
  if (!tpl || tpl.model === "*") return devices;
  return devices.filter(d => (d.model || "routeros") === tpl.model);
}

async function loadProvisionPage() {
  try {
    const [tplRes, runsRes, bulkRes, filtersRes] = await Promise.all([
      api("/api/provisioning/templates"),
      api("/api/provisioning/runs?limit=30"),
      api("/api/provisioning/bulk?limit=20"),
      api("/api/provisioning/filters"),
    ]);
    provisionTemplatesCache = tplRes.items || [];
    fillProvisionFilterSelects(filtersRes);
    renderProvisionTemplates(provisionTemplatesCache);
    renderProvisionRuns(runsRes.items || []);
    renderProvisionBulkRuns(bulkRes.items || []);
    fillProvisionSelects();
  } catch (e) {
    showAlert("provision-alert", e.message, "error");
  }
}

function renderProvisionTemplates(rows) {
  const tbody = qs("#provision-templates-table tbody");
  if (!tbody) return;
  if (!rows?.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="text-muted">Нет шаблонов</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(t => {
    const scope = [t.scope_group, t.scope_site].filter(Boolean).join(" / ") || "—";
    const srcBadge = t.source === "generated"
      ? '<span class="badge badge-warning ml-1">auto</span>'
      : "";
    const complexCount = (t.meta?.complex_devices || []).length;
    const complexBadge = complexCount
      ? `<span class="badge badge-danger ml-1" title="сложные устройства">${complexCount}</span>`
      : "";
    return `
    <tr>
      <td><code>${escapeHtml(t.slug)}</code>${srcBadge}${complexBadge}
        <div class="small text-muted">${escapeHtml(t.name)}</div></td>
      <td class="small">${escapeHtml(scope)}</td>
      <td>${escapeHtml(t.model)}</td>
      <td class="text-nowrap">
        <button type="button" class="btn btn-link btn-sm p-0 btn-prov-edit" data-id="${t.id}">edit</button>
        ${can("provision:run") ? `<button type="button" class="btn btn-link btn-sm text-danger p-0 btn-prov-del" data-id="${t.id}">del</button>` : ""}
      </td>
    </tr>`;
  }).join("");
  tbody.querySelectorAll(".btn-prov-edit").forEach(btn => {
    btn.addEventListener("click", () => {
      const t = provisionTemplatesCache.find(x => String(x.id) === btn.dataset.id);
      openProvisionTemplateEditor(t);
    });
  });
  tbody.querySelectorAll(".btn-prov-del").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm("Удалить шаблон?")) return;
      try {
        await api(`/api/provisioning/templates/${btn.dataset.id}`, { method: "DELETE" });
        showAlert("provision-alert", "Шаблон удалён", "success");
        loadProvisionPage();
      } catch (e) {
        showAlert("provision-alert", e.message, "error");
      }
    });
  });
}

function renderProvisionRuns(rows) {
  const tbody = qs("#provision-runs-table tbody");
  if (!tbody) return;
  if (!rows?.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="text-muted">Нет запусков</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td class="small text-nowrap">${escapeHtml((r.created_at || "").replace("T", " ").slice(0, 19))}</td>
      <td><code>${escapeHtml(r.template_slug || "—")}</code></td>
      <td>${escapeHtml(r.device_name)}</td>
      <td><span class="${badgeCls(r.status === "completed" ? "success" : r.status === "failed" ? "danger" : "secondary")}">${escapeHtml(r.status)}</span></td>
    </tr>`).join("");
}

function provisionGenParams() {
  return {
    group: qs("#prov-gen-group")?.value?.trim() || "",
    site: qs("#prov-gen-site")?.value?.trim() || "",
    model: qs("#prov-gen-model")?.value?.trim() || "",
    threshold: parseFloat(qs("#prov-gen-threshold")?.value || "0.85"),
    min_devices: parseInt(qs("#prov-gen-min")?.value || "2", 10),
  };
}

function renderProvisionComplexDevices(items) {
  const tbody = qs("#provision-complex-table tbody");
  if (!tbody) return;
  if (!items?.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="text-muted">Сложных устройств не найдено</td></tr>';
    return;
  }
  tbody.innerHTML = items.map(d => `
    <tr>
      <td><code>${escapeHtml(d.name)}</code></td>
      <td class="small">${escapeHtml(d.group || "")} / ${escapeHtml(d.site || "")}</td>
      <td>${d.similarity != null ? (d.similarity * 100).toFixed(0) + "%" : "—"}</td>
      <td class="small text-muted">${escapeHtml(d.reason || "")}</td>
    </tr>`).join("");
}

function provClusterLabel(c) {
  const g = c.group || "—";
  const s = c.site || "—";
  const m = c.model || "—";
  return `${g} / ${s} / ${m}`;
}

function buildProvisionAnalysisLogEntries(res, source = "analyze") {
  const lines = [];
  const ts = new Date().toLocaleString("ru-RU");
  const clusters = res.clusters || [];
  const p = res.filters || provisionGenParams();

  lines.push({
    level: "info",
    text: `[${ts}] ${source === "generate" ? "Генерация шаблонов" : "Анализ кластеров"} | group=${p.group || "*"} site=${p.site || "*"} model=${p.model || "*"} threshold=${p.threshold ?? res.threshold ?? "—"} min=${p.min_devices ?? res.min_devices ?? "—"}`,
  });

  if (!clusters.length) {
    lines.push({ level: "warn", text: "Кластеры не найдены — проверьте фильтры и наличие конфигов в Oxidized." });
    return lines;
  }

  for (const c of clusters) {
    const label = provClusterLabel(c);
    if (c.skipped_reason) {
      lines.push({ level: "warn", text: `▸ ${label} — пропущен: ${c.skipped_reason}` });
      const errs = (c.devices || []).filter(d => d.error);
      for (const d of errs) {
        lines.push({ level: "error", text: `    ✗ ${d.name}: ${d.error}` });
      }
      continue;
    }

    lines.push({
      level: "info",
      text: `▸ ${label} | устройств с конфигом: ${c.device_count ?? "—"} | baseline: ${c.baseline_device || "—"} (${c.baseline_similarity != null ? (c.baseline_similarity * 100).toFixed(1) + "%" : "—"})`,
    });

    const simple = c.simple_devices || [];
    if (simple.length) {
      lines.push({ level: "success", text: `    простые (${simple.length}): ${simple.join(", ")}` });
    }

    const complex = c.complex_devices || [];
    for (const d of complex) {
      const sim = d.similarity != null ? ` ${(d.similarity * 100).toFixed(1)}%` : "";
      lines.push({ level: "warn", text: `    ⚠ сложное: ${d.name}${sim}${d.reason ? ` — ${d.reason}` : ""}` });
    }

    if (c.template_body) {
      const linesCount = String(c.template_body).split("\n").length;
      lines.push({ level: "success", text: `    шаблон готов (${linesCount} строк)` });
    }

    const loadErrs = (c.devices || []).filter(d => d.error);
    for (const d of loadErrs) {
      lines.push({ level: "error", text: `    ✗ ${d.name}: нет конфига — ${d.error}` });
    }
  }

  if (source === "generate") {
    const created = (res.created || []).length;
    const updated = (res.updated || []).length;
    const skipped = (res.skipped || []).length;
    lines.push({
      level: created || updated ? "success" : "info",
      text: `Итог генерации: создано ${created}, обновлено ${updated}, пропущено ${skipped}`,
    });
  } else {
    const ready = clusters.filter(c => c.template_body && !c.skipped_reason).length;
    const skipped = clusters.filter(c => c.skipped_reason).length;
    lines.push({
      level: "info",
      text: `Итог: кластеров ${clusters.length}, готовых к шаблону ${ready}, пропущено ${skipped}, сложных устройств ${(res.complex_devices || []).length}`,
    });
  }

  return lines;
}

function appendAnalysisLogViewer(hostSel, entries, { replace = false } = {}) {
  const host = typeof hostSel === "string" ? qs(hostSel) : hostSel;
  if (!host || !entries?.length) return;
  const html = entries.map(e =>
    `<div class="analysis-log-line log-${e.level || "info"}">${escapeHtml(e.text)}</div>`
  ).join("");
  if (replace) {
    host.innerHTML = html;
  } else {
    host.insertAdjacentHTML("beforeend", html);
  }
  host.scrollTop = host.scrollHeight;
}

function appendProvisionAnalysisLog(entries, opts) {
  appendAnalysisLogViewer("#prov-analysis-log", entries, opts);
}

function appendBulkProvisionLog(entries, opts) {
  appendAnalysisLogViewer("#prov-bulk-log", entries, opts);
}

function clearProvisionAnalysisLog(message) {
  provAnalysisLogSeen = 0;
  const host = qs("#prov-analysis-log");
  if (!host) return;
  host.innerHTML = `<div class="analysis-log-line log-muted">${escapeHtml(message || "Лог очищен.")}</div>`;
}

function clearBulkProvisionLog(message) {
  provBulkLogSeen = 0;
  const host = qs("#prov-bulk-log");
  if (!host) return;
  host.innerHTML = `<div class="analysis-log-line log-muted">${escapeHtml(message || "Лог очищен.")}</div>`;
}

function renderProvisionClustersTable(clusters) {
  const tbody = qs("#provision-clusters-table tbody");
  if (!tbody) return;
  if (!clusters?.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="text-muted">Нет данных — запустите анализ</td></tr>';
    return;
  }
  tbody.innerHTML = clusters.map(c => {
    let status = "готов";
    let statusCls = "success";
    if (c.skipped_reason) {
      status = c.skipped_reason;
      statusCls = "warning";
    } else if (!c.template_body) {
      status = "нет шаблона";
      statusCls = "secondary";
    }
    const sim = c.baseline_similarity != null ? (c.baseline_similarity * 100).toFixed(0) + "%" : "—";
    return `
    <tr>
      <td><code>${escapeHtml(c.group || "—")}</code></td>
      <td>${escapeHtml(c.site || "—")}</td>
      <td>${escapeHtml(c.model || "—")}</td>
      <td class="text-end">${c.device_count ?? "—"}</td>
      <td class="small">${escapeHtml(c.baseline_device || "—")}</td>
      <td class="text-end">${sim}</td>
      <td class="text-end">${(c.simple_devices || []).length}</td>
      <td class="text-end">${(c.complex_devices || []).length}</td>
      <td class="small"><span class="${badgeCls(statusCls)}">${escapeHtml(status)}</span></td>
    </tr>`;
  }).join("");
}

function renderProvisionAnalysisResult(res, source = "analyze", { preserveLog = false } = {}) {
  const clusters = res.clusters || [];
  const ready = clusters.filter(c => c.template_body && !c.skipped_reason);
  const skipped = clusters.filter(c => c.skipped_reason);
  const summaryEl = qs("#prov-analysis-summary");
  if (summaryEl) {
    summaryEl.textContent =
      `Кластеров: ${clusters.length}, готовых к шаблону: ${ready.length}, пропущено: ${skipped.length}, сложных устройств: ${(res.complex_devices || []).length}`;
  }
  renderProvisionClustersTable(clusters);
  renderProvisionComplexDevices(res.complex_devices || []);
  if (!preserveLog) {
    const entries = res.log?.length
      ? res.log
      : buildProvisionAnalysisLogEntries(res, source);
    appendProvisionAnalysisLog(entries, { replace: true });
  }
}

let provAnalysisLogSeen = 0;
let provBulkLogSeen = 0;

function resetProvisionAnalysisLogProgress(message) {
  provAnalysisLogSeen = 0;
  appendProvisionAnalysisLog([{ level: "info", text: message }], { replace: true });
  provAnalysisLogSeen = 1;
}

function ingestProvisionAnalysisPollLog(log) {
  if (!Array.isArray(log) || log.length <= provAnalysisLogSeen) return;
  const chunk = log.slice(provAnalysisLogSeen);
  provAnalysisLogSeen = log.length;
  appendProvisionAnalysisLog(chunk, { replace: false });
}

async function pollProvisionAnalysisRun(runId) {
  for (;;) {
    const st = await api(`/api/provisioning/analysis/runs/${encodeURIComponent(runId)}`);
    ingestProvisionAnalysisPollLog(st.log);
    if (st.status === "completed" && st.result) {
      const result = { ...st.result, filters: st.result.filters || st.filters };
      renderProvisionAnalysisResult(result, "analyze", { preserveLog: true });
      return result;
    }
    if (st.status === "failed") {
      throw new Error(st.error || "Анализ завершился с ошибкой");
    }
    await new Promise(resolve => window.setTimeout(resolve, 600));
  }
}

async function provisionAnalyze() {
  const p = provisionGenParams();
  resetProvisionAnalysisLogProgress("Запуск анализа…");
  const btn = qs("#btn-prov-analyze");
  if (btn) btn.disabled = true;
  try {
    const start = await api("/api/provisioning/analysis/run", {
      method: "POST",
      body: JSON.stringify(p),
    });
    if (start.run_id) {
      return await pollProvisionAnalysisRun(start.run_id);
    }
    const q = new URLSearchParams();
    if (p.group) q.set("group", p.group);
    if (p.site) q.set("site", p.site);
    if (p.model) q.set("model", p.model);
    q.set("threshold", String(p.threshold));
    q.set("min_devices", String(p.min_devices));
    const res = await api(`/api/provisioning/analysis?${q}`);
    res.filters = p;
    renderProvisionAnalysisResult(res, "analyze");
    return res;
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function pollProvisionGenerateRun(runId) {
  for (;;) {
    const st = await api(`/api/provisioning/templates/generate/runs/${encodeURIComponent(runId)}`);
    ingestProvisionAnalysisPollLog(st.log);
    if (st.status === "completed" && st.result) {
      const result = { ...st.result, filters: st.filters };
      result.complex_devices = (result.clusters || []).flatMap(c =>
        (c.complex_devices || []).map(d => ({
          ...d,
          group: c.group,
          site: c.site,
        }))
      );
      renderProvisionAnalysisResult(result, "generate", { preserveLog: true });
      return result;
    }
    if (st.status === "failed") {
      throw new Error(st.error || "Генерация завершилась с ошибкой");
    }
    await new Promise(resolve => window.setTimeout(resolve, 600));
  }
}

async function provisionGenerateFromConfigs() {
  const p = provisionGenParams();
  const upsert = qs("#prov-gen-upsert")?.checked !== false;
  resetProvisionAnalysisLogProgress("Запуск генерации шаблонов…");
  const btn = qs("#btn-prov-generate");
  if (btn) btn.disabled = true;
  try {
    const start = await api("/api/provisioning/templates/generate/run", {
      method: "POST",
      body: JSON.stringify({
        group: p.group,
        site: p.site,
        model: p.model,
        complexity_threshold: p.threshold,
        min_devices: p.min_devices,
        upsert,
      }),
    });
    const res = await pollProvisionGenerateRun(start.run_id);
    const created = (res.created || []).length;
    const updated = (res.updated || []).length;
    showAlert(
      "provision-alert",
      `Создано: ${created}, обновлено: ${updated}, пропущено: ${(res.skipped || []).length}`,
      "success"
    );
    loadProvisionPage();
    return res;
  } finally {
    if (btn) btn.disabled = false;
  }
}

function fillProvisionSelects() {
  const tplSel = qs("#prov-template-select");
  const bulkTplSel = qs("#prov-bulk-template-select");
  const devSel = qs("#prov-device-select");
  const tplOptions = provisionTemplatesCache
    .filter(t => t.is_active !== false)
    .map(t => `<option value="${t.id}">${escapeHtml(t.slug)} (${escapeHtml(t.model)})</option>`)
    .join("");
  if (tplSel) tplSel.innerHTML = tplOptions;
  if (bulkTplSel) bulkTplSel.innerHTML = tplOptions;
  const templateId = parseInt(tplSel?.value || "0", 10);
  const devices = provisionDevicesForTemplate(templateId);
  if (devSel) {
    devSel.innerHTML = devices.length
      ? devices.map(d => `<option value="${escapeHtml(d.name)}">${escapeHtml(d.name)} (${escapeHtml(d.ip)})</option>`).join("")
      : '<option value="">— нет устройств —</option>';
  }
}

function applyProvisionBulkTemplateScope() {
  const tplId = parseInt(qs("#prov-bulk-template-select")?.value || "0", 10);
  const tpl = provisionTemplatesCache.find(t => t.id === tplId);
  if (!tpl) return;
  const groupSel = qs("#prov-bulk-group");
  const siteSel = qs("#prov-bulk-site");
  const modelSel = qs("#prov-bulk-model");
  if (tpl.scope_group && groupSel) groupSel.value = tpl.scope_group;
  if (tpl.scope_site && siteSel) siteSel.value = tpl.scope_site;
  if (tpl.model && tpl.model !== "*" && modelSel) modelSel.value = tpl.model;
}

function provisionBulkParams() {
  return {
    template_id: parseInt(qs("#prov-bulk-template-select")?.value || "0", 10),
    group: qs("#prov-bulk-group")?.value?.trim() || "",
    site: qs("#prov-bulk-site")?.value?.trim() || "",
    model: qs("#prov-bulk-model")?.value?.trim() || "",
    dry_run: qs("#prov-bulk-dry-run")?.checked !== false,
    exclude_complex: qs("#prov-bulk-exclude-complex")?.checked === true,
  };
}

function renderProvisionBulkTargets(devices) {
  const tbody = qs("#provision-bulk-targets-table tbody");
  if (!tbody) return;
  if (!devices?.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="text-muted">Нет устройств</td></tr>';
    return;
  }
  tbody.innerHTML = devices.map(d => `
    <tr>
      <td><code>${escapeHtml(d.name)}</code></td>
      <td class="small">${escapeHtml(d.ip || "")}</td>
      <td class="small">${escapeHtml(d.group || "")} / ${escapeHtml(d.site || "")}</td>
    </tr>`).join("");
}

function renderProvisionBulkRuns(rows) {
  const tbody = qs("#provision-bulk-runs-table tbody");
  if (!tbody) return;
  if (!rows?.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-muted">Нет bulk-задач</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const scope = [r.scope_group, r.scope_site].filter(Boolean).join(" / ") || "—";
    const progress = `${r.devices_completed || 0}/${r.devices_total || 0}`;
    const statusCls = r.status === "completed" ? "success" : r.status === "failed" ? "danger" : "secondary";
    return `
    <tr>
      <td class="small text-nowrap">${escapeHtml((r.created_at || "").replace("T", " ").slice(0, 19))}</td>
      <td><code>${escapeHtml(r.template_slug || "—")}</code>${r.dry_run ? ' <span class="badge badge-secondary">dry</span>' : ""}</td>
      <td class="small">${escapeHtml(scope)}</td>
      <td>${escapeHtml(progress)}${r.devices_failed ? ` <span class="text-danger">(${r.devices_failed} err)</span>` : ""}</td>
      <td><span class="${badgeCls(statusCls)}">${escapeHtml(r.status)}</span></td>
    </tr>`;
  }).join("");
}

async function provisionBulkPreview() {
  const p = provisionBulkParams();
  if (!p.template_id) throw new Error("Выберите шаблон");
  const q = new URLSearchParams({
    action: "preview",
    template_id: String(p.template_id),
    exclude_complex: String(p.exclude_complex),
  });
  if (p.group) q.set("group", p.group);
  if (p.site) q.set("site", p.site);
  if (p.model) q.set("model", p.model);
  const res = await api(`/api/provisioning/bulk?${q}`);
  const scope = [p.group, p.site, p.model].filter(Boolean).join(" / ") || "все устройства";
  const summaryEl = qs("#prov-bulk-preview-summary");
  if (summaryEl) {
    summaryEl.textContent = `${scope}: ${res.device_count} устройств${res.skipped_complex?.length ? `, исключено сложных: ${res.skipped_complex.length}` : ""}`;
  }
  renderProvisionBulkTargets(res.devices || []);
  return res;
}

function resetBulkProvisionLogProgress(message) {
  provBulkLogSeen = 0;
  appendBulkProvisionLog([{ level: "info", text: message }], { replace: true });
  provBulkLogSeen = 1;
}

function ingestBulkProvisionPollLog(log) {
  if (!Array.isArray(log) || log.length <= provBulkLogSeen) return;
  const chunk = log.slice(provBulkLogSeen);
  provBulkLogSeen = log.length;
  appendBulkProvisionLog(chunk, { replace: false });
}

function updateBulkProgressSummary(st) {
  const el = qs("#prov-bulk-preview-summary");
  if (!el || !st) return;
  const scope = [st.scope_group, st.scope_site, st.scope_model].filter(Boolean).join(" / ") || "все";
  el.textContent = `Bulk #${st.id} (${scope}): ${st.devices_completed || 0}/${st.devices_total || 0} — ${st.status}`;
}

async function pollProvisionBulkRun(bulkId) {
  for (;;) {
    const st = await api(`/api/provisioning/bulk/${bulkId}`);
    ingestBulkProvisionPollLog(st.log);
    updateBulkProgressSummary(st);
    if (st.status === "completed") return st;
    if (st.status === "failed") {
      if (st.error) {
        appendBulkProvisionLog([{ level: "error", text: st.error }], { replace: false });
      }
      throw new Error(st.error || "Bulk завершился с ошибкой");
    }
    await new Promise(resolve => window.setTimeout(resolve, 800));
  }
}

async function provisionBulkRun() {
  const p = provisionBulkParams();
  if (!p.template_id) throw new Error("Выберите шаблон");
  const scope = [p.group, p.site, p.model].filter(Boolean).join(" / ") || "все устройства";
  if (!p.dry_run && !confirm(`Применить шаблон на ${scope}?`)) return;
  resetBulkProvisionLogProgress("Запуск bulk…");
  const btn = qs("#btn-prov-bulk-run");
  if (btn) btn.disabled = true;
  try {
    const res = await api("/api/provisioning/bulk/run", {
      method: "POST",
      body: JSON.stringify({
        template_id: p.template_id,
        group: p.group,
        site: p.site,
        model: p.model,
        dry_run: p.dry_run,
        exclude_complex: p.exclude_complex,
        async: true,
      }),
    });
    if (res.id) {
      const final = await pollProvisionBulkRun(res.id);
      showAlert(
        "provision-alert",
        `Bulk #${final.id}: ${final.devices_completed}/${final.devices_total}`
          + (final.devices_failed ? `, ошибок ${final.devices_failed}` : ""),
        final.devices_failed ? "warning" : "success"
      );
    } else {
      showAlert(
        "provision-alert",
        `Bulk завершён: ${res.devices_completed}/${res.devices_total}`,
        "success"
      );
    }
    loadProvisionPage();
    return res;
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function provisionPreview() {
  const template_id = parseInt(qs("#prov-template-select")?.value || "0", 10);
  const device_name = qs("#prov-device-select")?.value || "";
  const out = qs("#prov-preview-output");
  if (!template_id || !device_name) throw new Error("Выберите шаблон и устройство");
  const res = await api("/api/provisioning/preview", {
    method: "POST",
    body: JSON.stringify({ template_id, device_name }),
  });
  if (out) out.textContent = res.rendered_config || "";
  return res;
}

async function provisionApply() {
  const template_id = parseInt(qs("#prov-template-select")?.value || "0", 10);
  const device_name = qs("#prov-device-select")?.value || "";
  const dry_run = qs("#prov-dry-run")?.checked ?? true;
  if (!template_id || !device_name) throw new Error("Выберите шаблон и устройство");
  if (!dry_run && !confirm(`Применить конфигурацию на ${device_name}?`)) return;
  const res = await api("/api/provisioning/run", {
    method: "POST",
    body: JSON.stringify({ template_id, device_name, dry_run }),
  });
  const out = qs("#prov-preview-output");
  if (out) {
    out.textContent = res.rendered_config || "";
    if (res.output) out.textContent += `\n\n--- output ---\n${res.output}`;
    if (res.error) out.textContent += `\n\n--- error ---\n${res.error}`;
  }
  showAlert("provision-alert", dry_run ? "Dry-run выполнен" : "Конфигурация применена", "success");
  loadProvisionPage();
}

async function loadSecurityAudit(opts = {}) {
  const loadSeq = ++securityAuditLoadSeq;
  if (!opts.keepOffset) securityFindingsOffset = 0;
  const alertEl = qs("#security-alert");
  if (alertEl) alertEl.innerHTML = "";

  try {
    const [data, findingsData] = await Promise.all([
      api(`/api/security/audit/summary${securityFilterQuery()}`),
      api(`/api/security/audit/findings${securityFindingsQuery(securityFindingsOffset)}`),
    ]);
    if (loadSeq !== securityAuditLoadSeq) return;

    const counts = data.counts || {};
    const run = data.run;
    qs("#security-stats").innerHTML = `
      <div class="col-12 stats-row">
        <div class="row">
          ${smallBox(counts.critical || 0, "Critical", "bg-danger", "fa-skull-crossbones")}
          ${smallBox(counts.high || 0, "High", "bg-danger", "fa-exclamation-triangle")}
          ${smallBox(counts.medium || 0, "Medium", "bg-warning", "fa-exclamation-circle")}
          ${smallBox(counts.low || 0, "Low", "bg-info", "fa-info-circle")}
          ${smallBox(data.devices_with_findings || 0, "Устройств с нарушениями", "bg-dark", "fa-server")}
          ${smallBox(data.rules_total || 0, "Правил", "bg-secondary", "fa-list-check")}
        </div>
      </div>`;

    const meta = qs("#security-run-meta");
    if (meta) {
      if (run) {
        meta.textContent = `Последний аудит #${run.id}: ${formatDate(run.finished_at || run.started_at)} · `
          + `сканировано ${run.devices_scanned}/${run.devices_total} · нарушений ${run.findings_count}`
          + (run.error ? ` · ${run.error}` : "");
      } else {
        meta.textContent = "Аудит ещё не запускался. Нажмите «Запустить аудит».";
      }
    }

    const findings = findingsData.items || [];
    renderSecurityFindingsRows(findings);
    updateSecurityFindingsPager(
      findingsData.total || 0,
      findingsData.offset || 0,
      findingsData.limit || 50,
    );

    const runsData = await api("/api/security/audit/runs?limit=10").catch(() => ({ runs: [] }));
    if (loadSeq !== securityAuditLoadSeq) return;
    const runsBody = qs("#security-runs-table");
    if (runsBody) {
      const runs = runsData.runs || [];
      runsBody.innerHTML = runs.length
        ? runs.map(r => `
          <tr>
            <td class="text-sm">${formatDate(r.finished_at || r.started_at)}</td>
            <td><span class="${badgeCls(r.status === "completed" ? "success" : r.status === "failed" ? "danger" : "warning")}">${escapeHtml(r.status)}</span></td>
            <td>${escapeHtml(r.triggered_by)}</td>
            <td>${r.devices_scanned}/${r.devices_total}</td>
            <td>${r.findings_count}</td>
            <td class="text-sm text-muted">${escapeHtml(r.error || "—")}</td>
          </tr>`).join("")
        : `<tr><td colspan="6" class="text-muted text-center">Нет запусков</td></tr>`;
    }
  } catch (e) {
    if (loadSeq !== securityAuditLoadSeq) return;
    showAlert("security-alert", e.message || "Ошибка загрузки аудита", "error");
  }
}

async function runSecurityAudit() {
  if (!can("security:run")) return;
  const btn = qs("#btn-security-run");
  if (btn) btn.disabled = true;
  try {
    showAlert("security-alert", "Аудит запущен (фоновая задача)…", "info");
    const res = await api("/api/security/audit/run", {
      method: "POST",
      body: JSON.stringify({ async: true }),
    });
    showAlert(
      "security-alert",
      res.status === "queued"
        ? `Аудит #${res.run_id} в очереди`
        : `Аудит завершён: ${res.run?.findings_count ?? 0} нарушений`,
      "success",
    );
    window.setTimeout(() => loadSecurityAudit(), 2000);
  } catch (e) {
    showAlert("security-alert", e.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function exportSecurityCsv() {
  try {
    const q = securityFilterQuery();
    const res = await fetch(`/api/security/audit/export${q}`, { credentials: "include" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const blob = await res.blob();
    const cd = res.headers.get("content-disposition") || "";
    const match = cd.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : "security-audit.csv";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showAlert("security-alert", e.message, "error");
  }
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
    refreshSiteDatalists();
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
    matchesSearch([n.network, n.group_name, n.site, n.role, n.environment_name, n.gateway], query)
  );

  if (!networks.length) {
    netsTable.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Нет подсетей</td></tr>`;
    return;
  }
  if (!filtered.length) {
    netsTable.innerHTML = searchEmptyRow(7, query);
    return;
  }

  const canWrite = can("inventory:write");
  const canEdit = can("inventory:write") || can("inventory:devices");

  netsTable.innerHTML = filtered.map(n => {
    const netKey = encodeURIComponent(n.network);
    return `
    <tr data-network="${netKey}" class="${canEdit ? "network-row-editable" : ""}" title="${canEdit ? "Нажмите для редактирования" : ""}">
      <td><code class="network-cidr-link">${escapeHtml(n.network)}</code></td>
      <td>${escapeHtml(n.group_name)}</td>
      <td>${escapeHtml(n.site || "—")}</td>
      <td>${escapeHtml(n.role || "—")}</td>
      <td>${escapeHtml(n.environment_name || "—")}</td>
      <td>${escapeHtml(n.gateway || "—")}</td>
      <td class="text-nowrap text-end">
        ${canEdit ? `<button type="button" class="btn btn-primary btn-sm btn-edit-network" data-network="${netKey}" title="Изменить"><i class="fas fa-edit"></i></button>` : ""}
        ${canWrite ? `<button type="button" class="btn btn-danger btn-sm btn-remove-network" data-network="${netKey}" title="Удалить"><i class="fas fa-trash"></i></button>` : ""}
      </td>
    </tr>`;
  }).join("");

  function networkKeyFromEl(el) {
    const raw = el?.dataset?.network;
    return raw ? decodeURIComponent(raw) : "";
  }

  netsTable.querySelectorAll("tr[data-network]").forEach(row => {
    row.addEventListener("click", e => {
      if (!canEdit) return;
      if (e.target.closest("button")) return;
      openNetworkModal(networkKeyFromEl(row));
    });
  });

  netsTable.querySelectorAll(".btn-edit-network").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      openNetworkModal(networkKeyFromEl(btn));
    });
  });

  netsTable.querySelectorAll(".btn-remove-network").forEach(btn => {
    btn.addEventListener("click", async e => {
      e.stopPropagation();
      const network = networkKeyFromEl(btn);
      if (!confirm(`Удалить подсеть ${network}?`)) return;
      inventory.networks = inventory.networks.filter(n => n.network !== network);
      await api("/inventory", { method: "PUT", body: JSON.stringify(inventory) });
      loadInventory();
    });
  });
}

function openNetworkModal(networkKey = null) {
  if (networkKey && !(can("inventory:write") || can("inventory:devices"))) return;
  editingNetworkKey = networkKey;
  const net = networkKey ? inventory?.networks?.find(n => n.network === networkKey) : null;
  const titleEl = qs("#network-modal-title");
  if (titleEl) {
    titleEl.innerHTML = networkKey
      ? '<i class="fas fa-edit me-2 text-muted"></i>Редактировать подсеть'
      : '<i class="fas fa-plus me-2 text-muted"></i>Добавить подсеть';
  }
  updateGroupSelects(net?.group_name || getGroupNames()[0]);
  const groupSel = qs("#network-modal-group");
  if (groupSel && net?.group_name) groupSel.value = net.group_name;
  qs("#network-modal-cidr").value = net?.network || "";
  qs("#network-modal-site").value = net?.site || "";
  qs("#network-modal-role").value = net?.role || "";
  qs("#network-modal-environment").value = net?.environment_name || "";
  qs("#network-modal-gateway").value = net?.gateway || "";
  refreshSiteDatalists();
  showModal("network-modal");
}

function closeNetworkModal() {
  hideModal("network-modal");
  editingNetworkKey = null;
}

async function saveNetwork() {
  const entry = {
    network: qs("#network-modal-cidr").value.trim(),
    group_name: qs("#network-modal-group").value.trim() || "default",
    site: qs("#network-modal-site")?.value.trim() || "",
    role: qs("#network-modal-role")?.value.trim() || "",
    environment_name: qs("#network-modal-environment").value.trim() || null,
    gateway: qs("#network-modal-gateway").value.trim() || null,
  };
  if (!entry.network) {
    showAlert("inventory-alert", "Укажите подсеть (CIDR)", "error");
    return;
  }
  try {
    if (!inventory) inventory = await api("/inventory");
    const wasEdit = !!editingNetworkKey;
    if (editingNetworkKey) {
      inventory.networks = inventory.networks.filter(n => n.network !== editingNetworkKey);
    }
    if (inventory.networks.some(n => n.network === entry.network)) {
      showAlert("inventory-alert", "Такая подсеть уже есть", "error");
      return;
    }
    inventory.networks.push(entry);
    await api("/inventory", { method: "PUT", body: JSON.stringify(inventory) });
    closeNetworkModal();
    loadInventory();
    showAlert("inventory-alert", wasEdit ? "Подсеть обновлена" : "Подсеть добавлена", "success");
  } catch (e) {
    showAlert("inventory-alert", e.message, "error");
  }
}

function updateDevicesBulkUi() {
  const toolbar = qs("#devices-bulk-toolbar");
  const countEl = qs("#devices-bulk-count");
  const n = selectedDeviceNames.size;
  if (toolbar && can("inventory:devices")) {
    toolbar.classList.toggle("d-none", !n);
    toolbar.classList.toggle("d-flex", !!n);
  }
  if (countEl) countEl.textContent = `${n} выбрано`;
  const selectAll = qs("#devices-select-all");
  if (selectAll) {
    const visible = qsa("#devices-table .device-select-cb");
    selectAll.checked = visible.length > 0 && visible.every(cb => cb.checked);
    selectAll.indeterminate = visible.some(cb => cb.checked) && !selectAll.checked;
  }
}

async function runBulkDeviceUpdate(payload) {
  if (!can("inventory:devices") || !selectedDeviceNames.size) return;
  try {
    inventory = await api("/inventory/devices/bulk", {
      method: "POST",
      body: JSON.stringify({ names: [...selectedDeviceNames], ...payload }),
    });
    selectedDeviceNames.clear();
    updateDevicesBulkUi();
    renderDevicesTable();
    loadHealth();
    showAlert("inventory-alert", "Массовое обновление выполнено", "success");
  } catch (e) {
    showAlert("inventory-alert", e.message, "error");
  }
}

function renderDevicesTable() {
  const tbody = qs("#devices-table");
  if (!tbody) return;
  const devices = inventory?.devices || [];
  const query = globalSearchQuery;
  const filtered = devices.filter(d =>
    deviceMatchesInventoryFilters(d) &&
    matchesSearch([d.name, d.ip, d.model, d.group, d.site, d.role, (d.tags || []).join(" "), d.critical ? "critical" : "", (d.ports || []).join(" "), d.enabled ? "yes enabled" : "no disabled"], query)
  );

  updateSearchCountBadge(filtered.length, devices.length, "devices-count-badge");
  const bulkGroup = qs("#bulk-group-select");
  if (bulkGroup) {
    const groups = getGroupNames();
    bulkGroup.innerHTML = (groups.length ? groups : ["default"]).map(g =>
      `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`
    ).join("");
  }

  const colSpan = can("inventory:devices") ? 9 : 8;
  if (!inventory) {
    tbody.innerHTML = tableLoadingRow(colSpan);
    return;
  }
  if (!devices.length) {
    tbody.innerHTML = `<tr><td colspan="${colSpan}" class="text-center text-muted">Нет устройств</td></tr>`;
    return;
  }
  if (!filtered.length) {
    tbody.innerHTML = searchEmptyRow(colSpan, query);
    return;
  }

  const showBulk = can("inventory:devices");
  tbody.innerHTML = filtered.map(d => `
    <tr>
      ${showBulk ? `<td><input type="checkbox" class="form-check-input device-select-cb" data-name="${escapeHtml(d.name)}" ${selectedDeviceNames.has(d.name) ? "checked" : ""}></td>` : ""}
      <td><strong>${escapeHtml(d.name)}</strong></td>
      <td>${escapeHtml(d.ip)}</td>
      <td><span class="oxidized-model-label">${escapeHtml(formatOxidizedModelLabel(d.model))}</span></td>
      <td>${escapeHtml(d.group)}</td>
      <td>${deviceTagsHtml(d)}</td>
      <td>${escapeHtml((d.ports || []).join(", "))}</td>
      <td>${d.enabled ? badgeSpan("on", "success") : badgeSpan("off", "secondary")}</td>
      <td>
        ${can("inventory:devices") ? `<button class="btn btn-info btn-sm btn-edit-device" data-name="${escapeHtml(d.name)}" title="Изменить" aria-label="Изменить"><i class="fas fa-edit"></i></button>` : ""}
        ${can("inventory:devices") ? `<button class="btn btn-danger btn-sm btn-delete-device" data-name="${escapeHtml(d.name)}" title="Удалить" aria-label="Удалить"><i class="fas fa-trash"></i></button>` : ""}
      </td>
    </tr>
  `).join("");

  tbody.querySelectorAll(".device-select-cb").forEach(cb => {
    cb.addEventListener("change", () => {
      if (cb.checked) selectedDeviceNames.add(cb.dataset.name);
      else selectedDeviceNames.delete(cb.dataset.name);
      updateDevicesBulkUi();
    });
  });
  updateDevicesBulkUi();

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
  if (can("settings:read")) {
    await loadIntegrationSettings();
  }
  if (can("users:manage")) {
    await loadSystemSettings();
  }
  if (can("inventory:write")) {
    await loadScanSettings();
  }
  if (can("oxidized:read") || can("oxidized:write")) {
    await loadGroupPolicies();
    populateGroupPolicyModelSelect();
  }
  refreshSettingsBaseline();
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
    markSettingsSaved();
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
  if (qs("#nt-error-slack")) qs("#nt-error-slack").checked = !!cfg.error_notify_slack;
  if (qs("#nt-error-teams")) qs("#nt-error-teams").checked = !!cfg.error_notify_teams;
  if (qs("#nt-report-telegram")) qs("#nt-report-telegram").checked = !!cfg.report_send_telegram;
  if (qs("#nt-report-email")) qs("#nt-report-email").checked = !!cfg.report_send_email;
  if (qs("#nt-report-slack")) qs("#nt-report-slack").checked = !!cfg.report_send_slack;
  if (qs("#nt-report-teams")) qs("#nt-report-teams").checked = !!cfg.report_send_teams;
  if (qs("#nt-degrade-telegram")) qs("#nt-degrade-telegram").checked = !!cfg.degrade_notify_telegram;
  if (qs("#nt-degrade-email")) qs("#nt-degrade-email").checked = !!cfg.degrade_notify_email;
  if (qs("#nt-degrade-slack")) qs("#nt-degrade-slack").checked = !!cfg.degrade_notify_slack;
  if (qs("#nt-degrade-teams")) qs("#nt-degrade-teams").checked = !!cfg.degrade_notify_teams;
  if (qs("#nt-stale-days")) qs("#nt-stale-days").value = cfg.stale_days_threshold ?? 30;
  if (qs("#nt-alert-cooldown")) qs("#nt-alert-cooldown").value = cfg.alert_cooldown_hours ?? 24;
  if (qs("#nt-degrade-interval")) qs("#nt-degrade-interval").value = cfg.degrade_check_interval_sec ?? 3600;
  if (qs("#nt-compliance-telegram")) qs("#nt-compliance-telegram").checked = !!cfg.compliance_report_telegram;
  if (qs("#nt-compliance-email")) qs("#nt-compliance-email").checked = !!cfg.compliance_report_email;
  if (qs("#nt-compliance-slack")) qs("#nt-compliance-slack").checked = !!cfg.compliance_report_slack;
  if (qs("#nt-compliance-teams")) qs("#nt-compliance-teams").checked = !!cfg.compliance_report_teams;
  if (qs("#nt-compliance-hour")) qs("#nt-compliance-hour").value = cfg.compliance_report_hour_utc ?? 7;
  const lastSentEl = qs("#nt-compliance-last-sent");
  if (lastSentEl) {
    lastSentEl.textContent = cfg.compliance_report_last_sent_at
      ? `Последний: ${formatDate(cfg.compliance_report_last_sent_at)}`
      : "Последний: —";
  }
  if (qs("#nt-webhook-enabled")) qs("#nt-webhook-enabled").checked = !!cfg.degrade_webhook_enabled;
  if (qs("#nt-webhook-url")) qs("#nt-webhook-url").value = cfg.degrade_webhook_url || "";
  if (qs("#nt-slack-webhook")) qs("#nt-slack-webhook").value = cfg.slack_webhook_url || "";
  if (qs("#nt-teams-webhook")) qs("#nt-teams-webhook").value = cfg.teams_webhook_url || "";
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
    error_notify_slack: qs("#nt-error-slack")?.checked === true,
    error_notify_teams: qs("#nt-error-teams")?.checked === true,
    report_send_telegram: qs("#nt-report-telegram")?.checked === true,
    report_send_email: qs("#nt-report-email")?.checked === true,
    report_send_slack: qs("#nt-report-slack")?.checked === true,
    report_send_teams: qs("#nt-report-teams")?.checked === true,
    degrade_notify_telegram: qs("#nt-degrade-telegram")?.checked === true,
    degrade_notify_email: qs("#nt-degrade-email")?.checked === true,
    degrade_notify_slack: qs("#nt-degrade-slack")?.checked === true,
    degrade_notify_teams: qs("#nt-degrade-teams")?.checked === true,
    stale_days_threshold: parseInt(qs("#nt-stale-days")?.value, 10) || 30,
    alert_cooldown_hours: parseInt(qs("#nt-alert-cooldown")?.value, 10) || 24,
    degrade_check_interval_sec: parseInt(qs("#nt-degrade-interval")?.value, 10) || 3600,
    compliance_report_telegram: qs("#nt-compliance-telegram")?.checked === true,
    compliance_report_email: qs("#nt-compliance-email")?.checked === true,
    compliance_report_slack: qs("#nt-compliance-slack")?.checked === true,
    compliance_report_teams: qs("#nt-compliance-teams")?.checked === true,
    compliance_report_hour_utc: parseInt(qs("#nt-compliance-hour")?.value, 10) || 7,
    degrade_webhook_enabled: qs("#nt-webhook-enabled")?.checked === true,
    degrade_webhook_url: qs("#nt-webhook-url")?.value.trim() || "",
    slack_webhook_url: qs("#nt-slack-webhook")?.value.trim() || "",
    teams_webhook_url: qs("#nt-teams-webhook")?.value.trim() || "",
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
    error_notify_slack: qs("#nt-error-slack")?.checked === true,
    error_notify_teams: qs("#nt-error-teams")?.checked === true,
    report_send_telegram: qs("#nt-report-telegram")?.checked === true,
    report_send_email: qs("#nt-report-email")?.checked === true,
    report_send_slack: qs("#nt-report-slack")?.checked === true,
    report_send_teams: qs("#nt-report-teams")?.checked === true,
    degrade_notify_telegram: qs("#nt-degrade-telegram")?.checked === true,
    degrade_notify_email: qs("#nt-degrade-email")?.checked === true,
    degrade_notify_slack: qs("#nt-degrade-slack")?.checked === true,
    degrade_notify_teams: qs("#nt-degrade-teams")?.checked === true,
    slack_webhook_url: qs("#nt-slack-webhook")?.value.trim() || "",
    teams_webhook_url: qs("#nt-teams-webhook")?.value.trim() || "",
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
    markSettingsSaved();
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

let integrationSettingsCache = null;

function fillIntegrationSettingsForm(cfg) {
  integrationSettingsCache = cfg;
  if (qs("#int-snow-enabled")) qs("#int-snow-enabled").checked = !!cfg.snow_enabled;
  if (qs("#int-snow-url")) qs("#int-snow-url").value = cfg.snow_instance_url || "";
  if (qs("#int-snow-user")) qs("#int-snow-user").value = cfg.snow_username || "";
  if (qs("#int-snow-group")) qs("#int-snow-group").value = cfg.snow_assignment_group || "";
  const snowPass = qs("#int-snow-password");
  if (snowPass) {
    snowPass.value = "";
    snowPass.placeholder = cfg.snow_password_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "Password";
  }
  if (qs("#int-jira-enabled")) qs("#int-jira-enabled").checked = !!cfg.jira_enabled;
  if (qs("#int-jira-url")) qs("#int-jira-url").value = cfg.jira_url || "";
  if (qs("#int-jira-user")) qs("#int-jira-user").value = cfg.jira_username || "";
  if (qs("#int-jira-project")) qs("#int-jira-project").value = cfg.jira_project_key || "";
  if (qs("#int-jira-type")) qs("#int-jira-type").value = cfg.jira_issue_type || "Task";
  const jiraTok = qs("#int-jira-token");
  if (jiraTok) {
    jiraTok.value = "";
    jiraTok.placeholder = cfg.jira_api_token_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "API token";
  }
  if (qs("#int-ticket-backup-failed")) qs("#int-ticket-backup-failed").checked = cfg.ticket_on_backup_failed !== false;
  if (qs("#int-ticket-device-offline")) qs("#int-ticket-device-offline").checked = cfg.ticket_on_device_offline !== false;
  if (qs("#int-ticket-cooldown")) qs("#int-ticket-cooldown").value = cfg.ticket_cooldown_hours ?? 24;
  if (qs("#int-audit-enabled")) qs("#int-audit-enabled").checked = !!cfg.audit_webhook_enabled;
  if (qs("#int-audit-url")) qs("#int-audit-url").value = cfg.audit_webhook_url || "";
  if (qs("#int-audit-prefix")) qs("#int-audit-prefix").value = cfg.audit_webhook_action_prefix || "";
  const auditSecret = qs("#int-audit-secret");
  if (auditSecret) {
    auditSecret.value = "";
    auditSecret.placeholder = cfg.audit_webhook_secret_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "HMAC secret";
  }
  if (qs("#int-netbox-url")) qs("#int-netbox-url").value = cfg.netbox_url || "";
  if (qs("#int-netbox-group")) qs("#int-netbox-group").value = cfg.netbox_default_group || "default";
  const netboxTok = qs("#int-netbox-token");
  if (netboxTok) {
    netboxTok.value = "";
    netboxTok.placeholder = cfg.netbox_token_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "API token";
  }
  if (qs("#int-librenms-url")) qs("#int-librenms-url").value = cfg.librenms_url || "";
  if (qs("#int-librenms-group")) qs("#int-librenms-group").value = cfg.librenms_default_group || "default";
  const libreTok = qs("#int-librenms-token");
  if (libreTok) {
    libreTok.value = "";
    libreTok.placeholder = cfg.librenms_token_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "API token";
  }
  if (qs("#int-sync-enabled")) qs("#int-sync-enabled").checked = !!cfg.inventory_sync_enabled;
  if (qs("#int-sync-source")) qs("#int-sync-source").value = cfg.inventory_sync_source || "netbox";
  if (qs("#int-sync-interval")) qs("#int-sync-interval").value = cfg.inventory_sync_interval_hours ?? 24;
  const syncLast = qs("#int-sync-last-run");
  if (syncLast) {
    syncLast.textContent = cfg.inventory_sync_last_run_at
      ? `Последний sync: ${formatDate(cfg.inventory_sync_last_run_at)}`
      : "Последний sync: —";
  }
  if (qs("#int-zabbix-api-enabled")) qs("#int-zabbix-api-enabled").checked = !!cfg.zabbix_api_enabled;
  if (qs("#int-zabbix-api-url")) qs("#int-zabbix-api-url").value = cfg.zabbix_api_url || "";
  const zabbixTok = qs("#int-zabbix-api-token");
  if (zabbixTok) {
    zabbixTok.value = "";
    zabbixTok.placeholder = cfg.zabbix_api_token_set
      ? "Установлен — оставьте пустым, чтобы не менять"
      : "API token";
  }
}

function collectIntegrationSettingsForm() {
  const snowVal = qs("#int-snow-password")?.value.trim();
  const jiraVal = qs("#int-jira-token")?.value.trim();
  const auditVal = qs("#int-audit-secret")?.value.trim();
  const netboxVal = qs("#int-netbox-token")?.value.trim();
  const libreVal = qs("#int-librenms-token")?.value.trim();
  const zabbixVal = qs("#int-zabbix-api-token")?.value.trim();
  return {
    snow_enabled: qs("#int-snow-enabled")?.checked === true,
    snow_instance_url: qs("#int-snow-url")?.value.trim() || "",
    snow_username: qs("#int-snow-user")?.value.trim() || "",
    snow_password: snowVal || (integrationSettingsCache?.snow_password_set ? SETTINGS_PASSWORD_MASK : ""),
    snow_assignment_group: qs("#int-snow-group")?.value.trim() || "",
    jira_enabled: qs("#int-jira-enabled")?.checked === true,
    jira_url: qs("#int-jira-url")?.value.trim() || "",
    jira_username: qs("#int-jira-user")?.value.trim() || "",
    jira_api_token: jiraVal || (integrationSettingsCache?.jira_api_token_set ? SETTINGS_PASSWORD_MASK : ""),
    jira_project_key: qs("#int-jira-project")?.value.trim() || "",
    jira_issue_type: qs("#int-jira-type")?.value.trim() || "Task",
    ticket_on_backup_failed: qs("#int-ticket-backup-failed")?.checked !== false,
    ticket_on_device_offline: qs("#int-ticket-device-offline")?.checked !== false,
    ticket_cooldown_hours: parseInt(qs("#int-ticket-cooldown")?.value, 10) || 24,
    audit_webhook_enabled: qs("#int-audit-enabled")?.checked === true,
    audit_webhook_url: qs("#int-audit-url")?.value.trim() || "",
    audit_webhook_secret: auditVal || (integrationSettingsCache?.audit_webhook_secret_set ? SETTINGS_PASSWORD_MASK : ""),
    audit_webhook_action_prefix: qs("#int-audit-prefix")?.value.trim() || "",
    netbox_url: qs("#int-netbox-url")?.value.trim() || "",
    netbox_token: netboxVal || (integrationSettingsCache?.netbox_token_set ? SETTINGS_PASSWORD_MASK : ""),
    netbox_default_group: qs("#int-netbox-group")?.value.trim() || "default",
    librenms_url: qs("#int-librenms-url")?.value.trim() || "",
    librenms_token: libreVal || (integrationSettingsCache?.librenms_token_set ? SETTINGS_PASSWORD_MASK : ""),
    librenms_default_group: qs("#int-librenms-group")?.value.trim() || "default",
    inventory_sync_enabled: qs("#int-sync-enabled")?.checked === true,
    inventory_sync_source: qs("#int-sync-source")?.value || "netbox",
    inventory_sync_interval_hours: parseInt(qs("#int-sync-interval")?.value, 10) || 24,
    zabbix_api_enabled: qs("#int-zabbix-api-enabled")?.checked === true,
    zabbix_api_url: qs("#int-zabbix-api-url")?.value.trim() || "",
    zabbix_api_token: zabbixVal || (integrationSettingsCache?.zabbix_api_token_set ? SETTINGS_PASSWORD_MASK : ""),
  };
}

async function loadIntegrationSettings() {
  try {
    const cfg = await api("/api/settings/integrations");
    fillIntegrationSettingsForm(cfg);
  } catch (e) {
    showAlert("settings-alert", `Интеграции: ${e.message}`, "error");
  }
}

async function saveIntegrationSettings(e) {
  e.preventDefault();
  if (!can("settings:notify")) return;
  try {
    const saved = await api("/api/settings/integrations", {
      method: "PUT",
      body: JSON.stringify(collectIntegrationSettingsForm()),
    });
    fillIntegrationSettingsForm(saved);
    showAlert("settings-alert", "Интеграции сохранены", "success");
    markSettingsSaved();
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
  }
}

async function testAuditWebhook() {
  if (!can("settings:notify")) return;
  try {
    const res = await api("/api/settings/integrations/test-audit-webhook", { method: "POST" });
    showAlert("settings-alert", res.message || (res.ok ? "Webhook OK" : "Ошибка"), res.ok ? "success" : "error");
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
  }
}

function fillSystemSettingsForm(cfg) {
  if (qs("#sys-oxidized-engine")) qs("#sys-oxidized-engine").value = cfg.oxidized_engine || "python";
  if (qs("#sys-oxidized-url")) qs("#sys-oxidized-url").value = cfg.oxidized_external_url || "";
  if (qs("#sys-zabbix-enabled")) qs("#sys-zabbix-enabled").checked = cfg.zabbix_monitoring_enabled !== false;
  if (qs("#sys-zabbix-key")) qs("#sys-zabbix-key").value = "";
  if (qs("#sys-audit-retention")) qs("#sys-audit-retention").value = cfg.audit_retention_days ?? 365;
  if (qs("#sys-token-ttl")) qs("#sys-token-ttl").value = cfg.access_token_expire_minutes ?? 480;
  if (qs("#sys-backup-dir")) qs("#sys-backup-dir").value = cfg.backup_data_dir || "/data/backups";
  if (qs("#sys-worker-poll")) qs("#sys-worker-poll").value = cfg.task_worker_poll_sec ?? 30;
  if (qs("#sys-metrics-enabled")) qs("#sys-metrics-enabled").checked = cfg.metrics_enabled !== false;
  if (qs("#sys-worker-enabled")) qs("#sys-worker-enabled").checked = cfg.task_worker_enabled !== false;
  if (qs("#sys-https-proxy")) qs("#sys-https-proxy").checked = !!cfg.behind_https_proxy;
  const hint = qs("#sys-settings-restart-hint");
  if (hint) {
    hint.textContent = cfg.zabbix_auth_key_set
      ? "Zabbix auth key задан. После смены движка или HTTPS proxy перезапустите scanner."
      : "Задайте Zabbix auth key для шаблона мониторинга. Секреты JWT и БД остаются в .env.";
  }
}

function collectSystemSettingsForm() {
  const key = qs("#sys-zabbix-key")?.value?.trim() || "";
  const payload = {
    oxidized_engine: qs("#sys-oxidized-engine")?.value || "python",
    oxidized_external_url: qs("#sys-oxidized-url")?.value?.trim() || "",
    zabbix_monitoring_enabled: qs("#sys-zabbix-enabled")?.checked === true,
    audit_retention_days: parseInt(qs("#sys-audit-retention")?.value, 10) || 0,
    access_token_expire_minutes: parseInt(qs("#sys-token-ttl")?.value, 10) || 480,
    backup_data_dir: qs("#sys-backup-dir")?.value?.trim() || "/data/backups",
    task_worker_poll_sec: parseInt(qs("#sys-worker-poll")?.value, 10) || 30,
    metrics_enabled: qs("#sys-metrics-enabled")?.checked === true,
    task_worker_enabled: qs("#sys-worker-enabled")?.checked === true,
    behind_https_proxy: qs("#sys-https-proxy")?.checked === true,
  };
  if (key) payload.zabbix_auth_key = key;
  return payload;
}

async function loadSystemSettings() {
  try {
    const cfg = await api("/api/settings/system");
    fillSystemSettingsForm(cfg);
  } catch (e) {
    showAlert("settings-alert", `Система: ${e.message}`, "error");
  }
}

async function saveSystemSettings(e) {
  e.preventDefault();
  if (!can("users:manage")) return;
  try {
    const saved = await api("/api/settings/system", {
      method: "PUT",
      body: JSON.stringify(collectSystemSettingsForm()),
    });
    fillSystemSettingsForm(saved);
    showAlert("settings-alert", "Системные настройки сохранены. Перезапустите scanner при смене движка.", "success");
    markSettingsSaved();
    if (can("oxidized:read") || can("oxidized:write")) {
      await loadOxidizedSettings();
    }
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
  }
}

async function runInventoryImport(source) {
  if (!can("inventory:write")) return;
  const path = source === "librenms" ? "/api/inventory/import/librenms" : "/api/inventory/import/netbox";
  try {
    const res = await api(path, { method: "POST" });
    showAlert(
      "settings-alert",
      `${source}: создано ${res.created}, обновлено ${res.updated}, пропущено ${res.skipped}`,
      "success",
    );
    loadInventory();
    loadIntegrationSettings();
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
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
    markSettingsSaved();
  } catch (err) {
    showAlert("settings-alert", err.message, "error");
  }
}

function fillScanSettingsForm(cfg) {
  scanSettingsCache = cfg;
  if (qs("#scan-concurrency")) qs("#scan-concurrency").value = cfg.scan_concurrency ?? 50;
  if (qs("#scan-discover-max")) qs("#scan-discover-max").value = cfg.discover_max_hosts ?? 4096;
  if (qs("#scan-ping-workers")) qs("#scan-ping-workers").value = cfg.discover_ping_workers ?? 100;
  if (qs("#scan-schedule-enabled")) qs("#scan-schedule-enabled").checked = !!cfg.schedule_enabled;
  if (qs("#scan-schedule-interval")) qs("#scan-schedule-interval").value = cfg.schedule_interval_hours ?? 24;
  if (qs("#scan-schedule-discover")) qs("#scan-schedule-discover").checked = cfg.schedule_discover !== false;
  const lastRun = qs("#scan-schedule-last-run");
  if (lastRun) {
    lastRun.textContent = cfg.schedule_last_run_at
      ? `Последний scheduled scan: ${formatDate(cfg.schedule_last_run_at)}`
      : "Scheduled scan ещё не выполнялся";
  }
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
    schedule_enabled: !!qs("#scan-schedule-enabled")?.checked,
    schedule_interval_hours: parseInt(qs("#scan-schedule-interval")?.value, 10) || 24,
    schedule_discover: !!qs("#scan-schedule-discover")?.checked,
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
    markSettingsSaved();
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
    markSettingsSaved();
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
    markSettingsSaved();
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
  renderLdapScopeMappings(cfg.scope_mappings || []);
  updateLdapPresetHint();
}

function renderLdapScopeMappings(rows) {
  const tbody = qs("#ldap-scope-mappings-body");
  if (!tbody) return;
  const data = rows?.length ? rows : [{ ldap_group: "", allowed_groups: [], allowed_sites: [] }];
  tbody.innerHTML = data.map((row, idx) => `
    <tr data-idx="${idx}">
      <td><input type="text" class="form-control form-control-sm ldap-scope-group" value="${escapeHtml(row.ldap_group || "")}" placeholder="CN=NetOps,..."></td>
      <td><input type="text" class="form-control form-control-sm ldap-scope-groups" value="${escapeHtml((row.allowed_groups || []).join(", "))}" placeholder="hex, us"></td>
      <td><input type="text" class="form-control form-control-sm ldap-scope-sites" value="${escapeHtml((row.allowed_sites || []).join(", "))}" placeholder="msk, spb"></td>
      <td><button type="button" class="btn btn-outline-danger btn-sm btn-ldap-scope-remove" title="Удалить"><i class="fas fa-trash"></i></button></td>
    </tr>
  `).join("");
  tbody.querySelectorAll(".btn-ldap-scope-remove").forEach(btn => {
    btn.addEventListener("click", () => {
      btn.closest("tr")?.remove();
      if (!tbody.querySelector("tr")) renderLdapScopeMappings([]);
    });
  });
}

function collectLdapScopeMappings() {
  return [...(qs("#ldap-scope-mappings-body")?.querySelectorAll("tr") || [])].map(tr => ({
    ldap_group: tr.querySelector(".ldap-scope-group")?.value.trim() || "",
    allowed_groups: (tr.querySelector(".ldap-scope-groups")?.value || "").split(",").map(s => s.trim()).filter(Boolean),
    allowed_sites: (tr.querySelector(".ldap-scope-sites")?.value || "").split(",").map(s => s.trim()).filter(Boolean),
  })).filter(row => row.ldap_group);
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
    scope_mappings: collectLdapScopeMappings(),
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
    markSettingsSaved();
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
  const info = vendorCatalog[model];
  if (info?.label) {
    return info.vendor && info.vendor !== "Unknown"
      ? `${info.label}`
      : info.label;
  }
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
    vendorCatalog = data.catalog || data.model_info || {};
  } catch {
    oxidizedModels = ["routeros"];
    vendorCatalog = {};
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
  populateDeviceModelSelect(device?.model || oxidizedSettingsCache?.default_model || "routeros");
  if (device?.group) qs("#device-group").value = device.group;
  const ports = device?.ports?.length ? device.ports : defaultPortsForModel(qs("#device-model")?.value);
  qs("#device-ports").value = ports.join(", ");
  qs("#device-enabled").checked = device ? device.enabled : true;
  if (qs("#device-site")) qs("#device-site").value = device?.site || "";
  if (qs("#device-role")) qs("#device-role").value = device?.role || "";
  if (qs("#device-tags")) qs("#device-tags").value = (device?.tags || []).join(", ");
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
    ports: ports.length ? ports : defaultPortsForModel(qs("#device-model")?.value),
    site: qs("#device-site")?.value.trim() || "",
    role: qs("#device-role")?.value.trim() || "",
    tags: (qs("#device-tags")?.value || "").split(",").map(t => t.trim()).filter(Boolean),
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
  /* Основные кнопки получают спиннер, быстрые — только блокировку */
  ["btn-scan", "btn-scan-discover"].forEach(id => setBtnLoading(qs(`#${id}`), disabled));
  ["btn-quick-scan", "btn-quick-discover"].forEach(id => {
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
          `<i class="fas fa-exclamation-triangle me-1"></i> Ruby bridge недоступен — Python fallback: ${nativeModelsHintHtml()}. MikroTik binary — только routeros.`;
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
  const canRestore = isPythonEngine() && can("oxidized:write");
  return `<ul class="list-unstyled mb-0">${files.map(f => `
    <li class="mb-1 d-flex flex-wrap align-items-center gap-2">
      <a href="${backupDownloadUrl(name, type, f.name)}" class="btn btn-link btn-sm p-0" download>
        <i class="fas fa-download me-1"></i>${escapeHtml(f.name)}
      </a>
      <span class="text-muted small">${formatBytes(f.size)} · ${formatDate(f.mtime ? new Date(f.mtime * 1000).toISOString() : null)}</span>
      ${canRestore ? `<button type="button" class="btn btn-outline-warning btn-sm btn-restore-backup" data-name="${escapeHtml(name)}" data-type="${type}" data-file="${escapeHtml(f.name)}"><i class="fas fa-undo me-1"></i>Restore</button>` : ""}
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
    qsa("#oxidized-backups-modal .btn-restore-backup").forEach(btn => {
      btn.addEventListener("click", () => restoreMikrotikBackup(btn.dataset.name, btn.dataset.type, btn.dataset.file));
    });
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

async function restoreMikrotikBackup(name, type, file) {
  if (!confirm(`Восстановить ${file} на устройство ${name}? Текущая конфигурация может быть перезаписана.`)) {
    return;
  }
  try {
    showAlert("oxidized-alert", `Restore ${name}…`, "info");
    const res = await api(`/api/oxidized/nodes/${encodeURIComponent(name)}/backups/restore`, {
      method: "POST",
      body: JSON.stringify({ type, file }),
    });
    showAlert("oxidized-alert", `Restore выполнен: ${res.action || "ok"}`, "success");
  } catch (e) {
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
  window.addEventListener("hashchange", () => {
    if (!currentUser) return;
    const h = location.hash.replace(/^#/, "");
    if (!h) {
      navigateToPage("dashboard");
      updateLocationHash("dashboard");
      return;
    }
    handleRouteHash();
  });
  qs("#password-change-form")?.addEventListener("submit", submitPasswordChange);

  qs("#devices-select-all")?.addEventListener("change", e => {
    const checked = e.target.checked;
    qsa("#devices-table .device-select-cb").forEach(cb => {
      cb.checked = checked;
      if (checked) selectedDeviceNames.add(cb.dataset.name);
      else selectedDeviceNames.delete(cb.dataset.name);
    });
    updateDevicesBulkUi();
  });
  qs("#btn-bulk-enable")?.addEventListener("click", () => runBulkDeviceUpdate({ enabled: true }));
  qs("#btn-bulk-disable")?.addEventListener("click", () => runBulkDeviceUpdate({ enabled: false }));
  qs("#btn-bulk-maint-on")?.addEventListener("click", () => runBulkDeviceUpdate({ maintenance: true }));
  qs("#btn-bulk-maint-off")?.addEventListener("click", () => runBulkDeviceUpdate({ maintenance: false }));
  qs("#btn-bulk-group")?.addEventListener("click", () => {
    const group = qs("#bulk-group-select")?.value;
    if (group) runBulkDeviceUpdate({ group });
  });

  qs("#device-model")?.addEventListener("change", () => {
    const ports = defaultPortsForModel(qs("#device-model")?.value);
    if (qs("#device-ports")) qs("#device-ports").value = ports.join(", ");
  });

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
  qs("#integration-settings-form")?.addEventListener("submit", saveIntegrationSettings);
  qs("#system-settings-form")?.addEventListener("submit", saveSystemSettings);
  qs("#btn-test-audit-webhook")?.addEventListener("click", testAuditWebhook);
  qs("#btn-import-netbox")?.addEventListener("click", () => runInventoryImport("netbox"));
  qs("#btn-import-librenms")?.addEventListener("click", () => runInventoryImport("librenms"));
  ["#inv-filter-site", "#inv-filter-group", "#inv-filter-tags"].forEach(sel => {
    qs(sel)?.addEventListener("input", () => renderDevicesTable());
  });
  qs("#btn-inv-filter-clear")?.addEventListener("click", () => {
    ["#inv-filter-site", "#inv-filter-group", "#inv-filter-tags"].forEach(id => {
      const el = qs(id);
      if (el) el.value = "";
    });
    renderDevicesTable();
  });
  qs("#audit-action-filter")?.addEventListener("change", () => loadAudit());
  qs("#btn-security-refresh")?.addEventListener("click", () => loadSecurityAudit());
  qs("#security-severity-filter")?.addEventListener("change", () => loadSecurityAudit());
  qs("#security-ack-filter")?.addEventListener("change", () => loadSecurityAudit());
  qs("#btn-security-findings-prev")?.addEventListener("click", () => {
    securityFindingsOffset = Math.max(0, securityFindingsOffset - 50);
    loadSecurityAudit({ keepOffset: true });
  });
  qs("#btn-security-findings-next")?.addEventListener("click", () => {
    securityFindingsOffset += 50;
    loadSecurityAudit({ keepOffset: true });
  });
  qs("#btn-security-run")?.addEventListener("click", runSecurityAudit);
  qs("#btn-security-export")?.addEventListener("click", exportSecurityCsv);
  qs("#btn-test-notify-report")?.addEventListener("click", () => testBackupNotify("report"));
  qs("#btn-test-notify-error")?.addEventListener("click", () => testBackupNotify("error"));
  qs("#btn-test-notify-degrade")?.addEventListener("click", () => testBackupNotify("degrade"));
  qs("#btn-test-compliance-report")?.addEventListener("click", testComplianceReport);
  qs("#btn-degrade-check-now")?.addEventListener("click", runDegradeCheckNow);
  qs("#btn-compliance-export")?.addEventListener("click", exportComplianceCsv);
  qs("#btn-compliance-export-pdf")?.addEventListener("click", exportCompliancePdf);
  qs("#btn-compliance-send")?.addEventListener("click", sendComplianceReport);
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
  qs("#btn-ldap-scope-add")?.addEventListener("click", () => {
    const tbody = qs("#ldap-scope-mappings-body");
    const rows = collectLdapScopeMappings();
    rows.push({ ldap_group: "", allowed_groups: [], allowed_sites: [] });
    renderLdapScopeMappings(rows);
  });
  qs("#btn-totp-begin")?.addEventListener("click", () => beginTotpSetup().catch(err => showAlert("users-alert", err.message, "error")));
  qs("#btn-totp-enable-confirm")?.addEventListener("click", () => confirmTotpEnable().catch(err => showAlert("users-alert", err.message, "error")));
  qs("#btn-totp-disable")?.addEventListener("click", () => disableTotp().catch(err => showAlert("users-alert", err.message, "error")));

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
      if (inventory.networks.some(n => n.network === net)) {
        showAlert("inventory-alert", "Такая подсеть уже есть", "error");
        return;
      }
      inventory.networks.push({
        network: net,
        group_name: group,
        site: qs("#network-site")?.value.trim() || "",
        role: qs("#network-role")?.value.trim() || "",
        environment_name: null,
        gateway: null,
      });
      await api("/inventory", { method: "PUT", body: JSON.stringify(inventory) });
      qs("#network-input").value = "";
      if (qs("#network-site")) qs("#network-site").value = "";
      if (qs("#network-role")) qs("#network-role").value = "";
      loadInventory();
      showAlert("inventory-alert", "Подсеть добавлена", "success");
    });
  }

  qs("#network-form")?.addEventListener("submit", async e => {
    e.preventDefault();
    await saveNetwork();
  });

  qs("#btn-network-modal-add")?.addEventListener("click", () => openNetworkModal());

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
      const totpBlock = qs("#login-totp-block");
      if (totpBlock && totpBlock.style.display !== "none") {
        await verifyLoginTotp();
      } else {
        await login(qs("#login-username").value.trim(), qs("#login-password").value);
      }
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

  qs("#custom-role-create-form")?.addEventListener("submit", async e => {
    e.preventDefault();
    const perms = selectedCustomRolePermissions();
    if (!perms.length) {
      showAlert("users-alert", "Выберите хотя бы одно permission", "error");
      return;
    }
    try {
      await api("/api/auth/custom-roles", {
        method: "POST",
        body: JSON.stringify({
          slug: qs("#cr-slug").value.trim().toLowerCase(),
          label: qs("#cr-label").value.trim(),
          description: qs("#cr-description").value.trim(),
          permissions: perms,
        }),
      });
      qs("#cr-slug").value = "";
      qs("#cr-label").value = "";
      qs("#cr-description").value = "";
      qsa("#cr-permissions-picker .cr-perm-check").forEach(c => { c.checked = false; });
      showAlert("users-alert", "Пользовательская роль создана", "success");
      await loadCustomRoles();
      loadRbacMatrix();
    } catch (err) {
      showAlert("users-alert", err.message, "error");
    }
  });

  qs("#btn-custom-role-refresh")?.addEventListener("click", () => {
    loadRbacMatrix().then(() => loadCustomRoles());
  });
  qs("#btn-topology-netbox")?.addEventListener("click", () => loadNetboxTopology());
  qs("#btn-zabbix-api-test")?.addEventListener("click", async () => {
    const out = qs("#int-zabbix-tags-result");
    try {
      const res = await api("/api/integrations/zabbix/test", { method: "POST" });
      if (out) out.textContent = JSON.stringify(res, null, 2);
      showAlert("settings-alert", `Zabbix API OK (v${res.version})`, "success");
    } catch (e) {
      if (out) out.textContent = e.message;
      showAlert("settings-alert", e.message, "error");
    }
  });
  qs("#btn-zabbix-tags-lookup")?.addEventListener("click", async () => {
    const name = qs("#int-zabbix-tags-lookup")?.value?.trim();
    const out = qs("#int-zabbix-tags-result");
    if (!name) {
      showAlert("settings-alert", "Укажите имя хоста", "error");
      return;
    }
    try {
      const res = await api(`/api/integrations/zabbix/tags?name=${encodeURIComponent(name)}`);
      if (out) out.textContent = JSON.stringify(res, null, 2);
    } catch (e) {
      if (out) out.textContent = e.message;
      showAlert("settings-alert", e.message, "error");
    }
  });

  qs("#btn-provision-refresh")?.addEventListener("click", () => loadProvisionPage());
  qs("#btn-prov-analyze")?.addEventListener("click", async () => {
    try {
      await provisionAnalyze();
    } catch (e) {
      showAlert("provision-alert", e.message, "error");
      appendProvisionAnalysisLog([{ level: "error", text: `Ошибка анализа: ${e.message}` }], { replace: true });
    }
  });
  qs("#btn-prov-analysis-log-clear")?.addEventListener("click", () => {
    clearProvisionAnalysisLog("Лог очищен. Запустите анализ снова.");
  });
  qs("#btn-prov-bulk-log-clear")?.addEventListener("click", () => {
    clearBulkProvisionLog("Лог очищен.");
  });
  qs("#btn-prov-template-save")?.addEventListener("click", async () => {
    try {
      await saveProvisionTemplate();
    } catch (e) {
      showAlert("provision-alert", e.message, "error");
    }
  });
  qs("#btn-prov-template-cancel")?.addEventListener("click", () => resetProvisionTemplateForm());
  qs("#btn-prov-generate")?.addEventListener("click", async () => {
    if (!confirm("Сгенерировать шаблоны из конфигов Oxidized?")) return;
    try {
      await provisionGenerateFromConfigs();
    } catch (e) {
      showAlert("provision-alert", e.message, "error");
    }
  });
  qs("#btn-prov-template-create")?.addEventListener("click", async () => {
    const slug = qs("#pt-slug")?.value?.trim();
    const name = qs("#pt-name")?.value?.trim();
    const body = qs("#pt-body")?.value;
    if (!slug || !name || !body?.trim()) {
      showAlert("provision-alert", "Заполните slug, название и тело шаблона", "error");
      return;
    }
    try {
      await api("/api/provisioning/templates", {
        method: "POST",
        body: JSON.stringify({
          slug,
          name,
          model: qs("#pt-model")?.value?.trim() || "routeros",
          body,
        }),
      });
      showAlert("provision-alert", "Шаблон создан", "success");
      loadProvisionPage();
    } catch (err) {
      showAlert("provision-alert", err.message, "error");
    }
  });
  qs("#prov-bulk-template-select")?.addEventListener("change", () => applyProvisionBulkTemplateScope());
  qs("#prov-template-select")?.addEventListener("change", () => fillProvisionSelects());
  qs("#btn-prov-preview")?.addEventListener("click", async () => {
    try {
      await provisionPreview();
    } catch (e) {
      showAlert("provision-alert", e.message, "error");
    }
  });
  qs("#btn-prov-apply")?.addEventListener("click", async () => {
    try {
      await provisionApply();
    } catch (e) {
      showAlert("provision-alert", e.message, "error");
    }
  });
  qs("#btn-prov-bulk-preview")?.addEventListener("click", async () => {
    try {
      await provisionBulkPreview();
    } catch (e) {
      showAlert("provision-alert", e.message, "error");
    }
  });
  qs("#btn-prov-bulk-run")?.addEventListener("click", async () => {
    try {
      await provisionBulkRun();
    } catch (e) {
      showAlert("provision-alert", e.message, "error");
    }
  });
}

async function bootstrapApp(uiConfig = {}) {
  try {
    if (uiConfig.oxidized_engine !== undefined) {
      setOxidizedLinks(uiConfig.oxidized_public_url, uiConfig.oxidized_proxy_url, uiConfig.oxidized_engine);
      if (uiConfig.auth) updateLoginAuthHint(uiConfig.auth);
    } else {
      const cfg = await api("/api/ui/config");
      setOxidizedLinks(cfg.oxidized_public_url, cfg.oxidized_proxy_url, cfg.oxidized_engine);
      updateLoginAuthHint(cfg.auth || {});
      uiConfig = cfg;
      window.__uiConfig = cfg;
    }
  } catch {}

  const page = currentAppPage();
  const tasks = [loadInventory(), loadOxidizedModels()];
  if (page === "dashboard") {
    tasks.push(loadHealth());
  }

  await Promise.all(tasks);

  api("/scan/latest")
    .then(latest => renderScanResults(latest))
    .catch(() => null);
  resumeScanIfRunning();
}

async function init() {
  initNavigation();
  bindEvents();
  bindGlobalSearch();

  let uiConfig = {};
  try {
    uiConfig = await api("/api/ui/config").catch(() => ({}));
    window.__uiConfig = uiConfig;
    updateLoginAuthHint(uiConfig.auth || {});
  } catch {}

  try {
    currentUser = await api("/api/auth/me");
    showApp();
    syncAppRouteFromHash();
    bootstrapApp(uiConfig).catch(err => {
      console.error("bootstrap failed", err);
    });
    if (currentUser?.must_change_password) {
      showPasswordChangeModal();
    }
  } catch {
    showLogin();
  }
}

init();
