/** AdminLTE 4 / Bootstrap 5 UI helpers */

(function () {

  const THEME_KEY = "theme";

  function modalEl(id) {
    return document.getElementById(id);
  }

  window.showModal = function (id) {
    const el = modalEl(id);
    if (!el || !window.bootstrap?.Modal) return;
    bootstrap.Modal.getOrCreateInstance(el).show();
  };

  window.hideModal = function (id) {
    const el = modalEl(id);
    if (!el || !window.bootstrap?.Modal) return;
    const inst = bootstrap.Modal.getInstance(el);
    if (inst) inst.hide();
  };

  window.isModalOpen = function (id) {
    const el = modalEl(id);
    return !!el && el.classList.contains("show");
  };

  window.onModalEvent = function (id, eventName, handler) {
    const el = modalEl(id);
    if (el) el.addEventListener(eventName, handler);
  };

  function getStoredTheme() {
    try { return localStorage.getItem(THEME_KEY); } catch (_) { return null; }
  }

  function prefersDark() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function getPreferredTheme() {
    const stored = getStoredTheme();
    if (["light", "dark", "auto"].includes(stored)) return stored;
    return prefersDark() ? "dark" : "light";
  }

  function resolveTheme(theme) {
    if (theme !== "auto") return theme;
    return prefersDark() ? "dark" : "light";
  }

  function setTheme(theme) {
    const resolved = resolveTheme(theme);
    document.documentElement.setAttribute("data-bs-theme", resolved);
    document.documentElement.setAttribute("data-tg-theme", resolved);
  }

  /* Подсветка активной темы в выпадающем меню */
  function setThemeButtonActive(theme) {
    document.querySelectorAll("[data-bs-theme-value]").forEach(btn => {
      const val = btn.getAttribute("data-bs-theme-value");
      const active = val === theme;
      btn.classList.toggle("active", active);
      if (active) {
        btn.setAttribute("aria-current", "true");
      } else {
        btn.removeAttribute("aria-current");
      }
    });
  }

  function applyTheme(theme) {
    setTheme(theme);
    setThemeButtonActive(theme);
  }

  function initThemeToggle() {
    const preferred = getPreferredTheme();
    setTheme(preferred);
    setThemeButtonActive(preferred);

    document.querySelectorAll("[data-bs-theme-value]").forEach(btn => {
      btn.addEventListener("click", () => {
        const theme = btn.getAttribute("data-bs-theme-value");
        try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* ignore */ }
        applyTheme(theme);
      });
    });

    /* Режим «Авто»: реагируем на смену системной схемы */
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const stored = getStoredTheme();
      if (!stored || stored === "auto") applyTheme("auto");
    };
    if (media.addEventListener) media.addEventListener("change", onChange);
  }

  function initSidebarScrollbar() {
    const sidebarWrapper = document.querySelector(".sidebar-wrapper");
    const os = window.OverlayScrollbarsGlobal?.OverlayScrollbars;
    const isDark = resolveTheme(getPreferredTheme()) === "dark";
    if (sidebarWrapper && os) {
      os(sidebarWrapper, {
        scrollbars: {
          theme: isDark ? "os-theme-dark" : "os-theme-light",
          autoHide: "leave",
          clickScroll: true,
        },
      });
    }
  }

  function initWorkspaceNavigation() {
    const filter = document.getElementById("workspace-nav-filter");
    const links = [...document.querySelectorAll(".sidebar-menu .nav-page")];
    if (!filter) return;
    const update = () => {
      const term = filter.value.trim().toLocaleLowerCase();
      links.forEach(link => {
        const item = link.closest("li");
        if (item) item.classList.toggle("workspace-filtered", !link.textContent.toLocaleLowerCase().includes(term));
        if (link.classList.contains("active")) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      });
    };
    filter.addEventListener("input", update);
    filter.addEventListener("keydown", e => {
      if (e.key === "Escape") { filter.value = ""; update(); }
      if (e.key === "Enter") {
        e.preventDefault();
        const first = links.find(link => link.getClientRects().length && getComputedStyle(link).visibility !== "hidden");
        first?.click();
      }
    });
    links.forEach(link => link.addEventListener("click", () => {
      filter.value = "";
      queueMicrotask(update);
    }));
    const observer = new MutationObserver(update);
    links.forEach(link => observer.observe(link, {attributes:true, attributeFilter:["class"]}));
    update();
  }

  document.addEventListener("DOMContentLoaded", () => {
    initThemeToggle();
    initWorkspaceNavigation();
    initSidebarScrollbar();

    document.querySelectorAll("[data-bs-toggle='dropdown']").forEach(el => {
      if (window.bootstrap?.Dropdown && !bootstrap.Dropdown.getInstance(el)) {
        new bootstrap.Dropdown(el);
      }
    });
  });

})();
