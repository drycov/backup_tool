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

    return localStorage.getItem(THEME_KEY);

  }



  function getPreferredTheme() {

    const stored = getStoredTheme();

    if (stored) return stored;

    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";

  }



  function resolveTheme(theme) {

    if (theme !== "auto") return theme;

    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";

  }



  function setTheme(theme) {

    document.documentElement.setAttribute("data-bs-theme", resolveTheme(theme));

  }



  function initThemeToggle() {

    setTheme(getPreferredTheme());

    document.querySelectorAll("[data-bs-theme-value]").forEach(btn => {

      btn.addEventListener("click", () => {

        const theme = btn.getAttribute("data-bs-theme-value");

        localStorage.setItem(THEME_KEY, theme);

        setTheme(theme);

      });

    });

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



  document.addEventListener("DOMContentLoaded", () => {

    initThemeToggle();

    initSidebarScrollbar();

    document.querySelectorAll("[data-bs-toggle='dropdown']").forEach(el => {

      if (window.bootstrap?.Dropdown && !bootstrap.Dropdown.getInstance(el)) {

        new bootstrap.Dropdown(el);

      }

    });

  });

})();

