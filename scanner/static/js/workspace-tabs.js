/* Workspace tabs reuse existing page controllers and permission-filtered links. */
(function () {
  "use strict";
  let deps, root, opened = [], selected = null;
  const maxTabs = 10;
  const get = id => document.getElementById(id);
  function render() {
    if (!root) return;
    const focused = document.activeElement?.dataset?.workspacePage;
    root.replaceChildren();
    for (const page of opened) {
      const link = deps.allowed(page);
      if (!link) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "workspace-tab";
      button.id = "workspace-tab-" + page;
      button.dataset.workspacePage = page;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-controls", "page-" + page);
      button.setAttribute("aria-selected", String(page === selected));
      button.tabIndex = page === selected ? 0 : -1;
      const icon = link.querySelector("i")?.cloneNode(true);
      if (icon) { icon.setAttribute("aria-hidden","true"); button.append(icon); }
      const label = document.createElement("span");
      label.textContent = link.querySelector("p")?.textContent.trim() || link.textContent.trim();
      button.append(label);
      button.addEventListener("click", () => deps.open(page));
      root.append(button);
      const panel = get("page-" + page);
      panel?.setAttribute("role", "tabpanel");
      panel?.setAttribute("aria-labelledby", button.id);
    }
    get("workspace-tab-close").disabled = opened.length < 2;
    get("workspace-tab-refresh").disabled = !selected;
    if (focused) get("workspace-tab-" + focused)?.focus({preventScroll:true});
    if (selected) get("workspace-tab-" + selected)?.scrollIntoView({block:"nearest",inline:"nearest"});
  }
  function activate(page) {
    if (!deps?.allowed(page)) return;
    if (!opened.includes(page)) {
      if (opened.length >= maxTabs) opened = opened.filter(p => p !== opened.find(x => x !== selected));
      opened.push(page);
    }
    selected = page;
    render();
  }
  function close() {
    if (opened.length < 2) return;
    const old = selected;
    const i = opened.indexOf(old);
    const next = opened[i-1] || opened[i+1];
    if (deps.open(next)) { opened = opened.filter(p => p !== old); render(); get("workspace-tab-" + next)?.focus(); }
  }
  function reconcile() {
    if (!deps) return;
    opened = opened.filter(p => deps.allowed(p));
    if (!opened.includes(selected)) selected = null;
    render();
  }
  function reset() { opened = []; selected = null; render(); }
  function init(adapters) {
    deps = adapters; root = get("workspace-tablist");
    get("workspace-tab-refresh").addEventListener("click", () => deps.refresh());
    get("workspace-tab-close").addEventListener("click", close);
    root.addEventListener("keydown", e => {
      if (!["ArrowLeft","ArrowRight","Home","End","Delete"].includes(e.key)) return;
      e.preventDefault();
      if (e.key === "Delete") { close(); return; }
      const i = opened.indexOf(selected);
      const next = e.key === "Home" ? opened[0] : e.key === "End" ? opened.at(-1) : opened[(i + (e.key === "ArrowLeft" ? -1 : 1) + opened.length) % opened.length];
      if (next && deps.open(next)) get("workspace-tab-" + next)?.focus();
    });
    render();
  }
  window.WorkspaceTabs = {init,activate,reconcile,reset};
})();
