/* Unified history for one scoped node. Existing API remains authoritative. */
(function () {
  "use strict";
  const el = id => document.getElementById("backup-center-" + id);
  let deps, nodes = [], rows = [], generation = 0, busy = false, errors = [];
  const pending = new Set();
  const selected = () => nodes.find(n => n.name === el("node").value);
  const supported = n => deps.isPythonEngine() && deps.isRouterOsModel(n.model);
  const allowed = () => Boolean(deps?.can("oxidized:read"));
  const path = (n, suffix) => "/api/oxidized/nodes/" + encodeURIComponent(n.name) + suffix;
  function button(label, action, parent, danger = false) {
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "dk-btn dk-btn--sm " + (danger ? "dk-btn--danger" : "dk-btn--secondary");
    btn.textContent = label; btn.addEventListener("click", action); parent.append(btn); return btn;
  }
  function message(text) { el("status").textContent = text; }
  function render() {
    const root = el("history"); root.replaceChildren();
    const filter = el("type").value;
    const filtered = rows.filter(r => filter === "all" || r.type === filter);
    for (const r of filtered) {
      const tr = document.createElement("tr");
      for (const value of [r.date, {config:"Git / Config",bin:"Binary",rsc:"RSC Export"}[r.type],r.name,r.size]) {
        const td = document.createElement("td"); td.textContent = value; tr.append(td);
      }
      const actions = document.createElement("td");
      actions.className = "backup-center-row-actions";
      const n = selected();
      if (n && allowed()) {
        if (r.type === "config") {
          button("Просмотр", () => {if(allowed()) deps.showVersion(n.name,r.url,r.date);}, actions);
        } else {
          const a = document.createElement("a"); a.className = "dk-btn dk-btn--secondary dk-btn--sm";
          a.href = deps.backupDownloadUrl(n.name,r.type,r.name); a.download = ""; a.textContent = "Скачать"; actions.append(a);
          if (deps.can("oxidized:write") && supported(n)) button("Восстановить", () => {
            if (deps.can("oxidized:write") && supported(n)) deps.restore(n.name,r.type,r.name);
          }, actions, true);
        }
      }
      tr.append(actions); root.append(tr);
    }
    if (!busy) message((selected() ? "Записей: " + filtered.length + " из " + rows.length : "Выберите устройство.") + (errors.length ? " · " + errors.join(" · ") : ""));
  }
  function renderActions() {
    const n = selected(), root = el("actions"); root.replaceChildren();
    el("refresh").disabled = !n || !allowed() || busy;
    if (!n || !allowed()) return;
    button("Текущая конфигурация", () => {if(allowed()) deps.showConfig(n.name,n.model);},root);
    button("Версии / Diff", () => {if(allowed()) deps.showVersions(n.name);},root);
    if (!deps.can("oxidized:write")) return;
    const run = (label,suffix) => {
      const key = n.name + suffix;
      const btn = button(label, async () => {
        if (!allowed() || !deps.can("oxidized:write") || pending.has(key) || (suffix === "/backups/run" && !supported(n))) return;
        pending.add(key); btn.disabled = true;
        const ticket = generation;
        try {
          await deps.api("/api/backup/jobs",{method:"POST",body:JSON.stringify({device:n.name,kind:suffix==="/fetch"?"config":"mikrotik"})});
          if (ticket === generation && allowed()) { await load(); message("Задание принято в очередь. Обновите историю для проверки результата."); }
        } catch (e) { if (ticket === generation && allowed()) message(e.message); }
        finally { pending.delete(key); if (allowed()) renderActions(); }
      },root);
      btn.disabled = pending.has(key);
    };
    if (!deps.isPythonEngine()) return;
    run("Получить конфигурацию","/fetch");
    if (supported(n)) run("Создать Binary / RSC","/backups/run");
  }
  async function load() {
    const n = selected(), ticket = ++generation;
    rows = []; errors = []; el("jobs").textContent = ""; busy = Boolean(n && allowed());
    render(); renderActions();
    if (!busy) return;
    message("Загрузка истории…");
    const requests = [deps.api(path(n,"/versions"))];
    if (supported(n)) requests.push(deps.api(path(n,"/backups")));
    const jobsPromise = deps.api("/api/backup/jobs?device="+encodeURIComponent(n.name)).catch(()=>null);
    const results = await Promise.allSettled(requests);
    const jobs = await jobsPromise;
    if (ticket !== generation || !allowed()) return;
    el("jobs").textContent = jobs ? "Последние задания: " + (jobs.items || []).slice(0,5).map(j=>"#"+j.id+" "+j.kind+" — "+j.status).join(" · ") : "Журнал заданий недоступен";
    const versions = results[0];
    if (versions.status === "fulfilled") {
      for (const v of versions.value.versions || []) {
        if (typeof v.view_url !== "string" || !v.view_url.startsWith("/") || v.view_url.startsWith("//")) continue;
        rows.push({type:"config",name:String(v.oid || "—"),url:v.view_url,date:deps.formatDate(v.time),epoch:Number(v.epoch)||0,size:"—"});
      }
    } else errors.push("Git: " + versions.reason.message);
    if (results[1]?.status === "fulfilled") {
      for (const [key,type] of [["binary","bin"],["export","rsc"]]) {
        for (const f of results[1].value.backups?.[key] || []) {
          rows.push({type,name:f.name,date:f.mtime?deps.formatDate(new Date(f.mtime*1000).toISOString()):"—",epoch:Number(f.mtime)||0,size:deps.formatBytes(f.size)});
        }
      }
    } else if (results[1]) errors.push("MikroTik: " + results[1].reason.message);
    rows.sort((a,b)=>b.epoch-a.epoch);
    busy = false; render(); renderActions();
  }
  function reset() {
    generation++; nodes=[]; rows=[]; errors=[]; busy=false;
    if (!deps) return;
    el("node").replaceChildren(new Option("Выберите устройство",""));
    el("jobs").textContent=""; el("type").value="all"; render(); renderActions();
  }
  function setNodes(items) {
    if (!allowed()) return reset();
    const previous = el("node").value;
    nodes = Array.isArray(items) ? items.slice() : [];
    el("node").replaceChildren(new Option("Выберите устройство",""), ...nodes.map(n=>new Option(n.name,n.name)));
    if (nodes.some(n=>n.name===previous)) el("node").value=previous;
    load();
  }
  function init(adapters) {
    deps=adapters;
    el("node").addEventListener("change",load);
    el("type").addEventListener("change",render);
    el("refresh").addEventListener("click",load);
    reset();
  }
  window.BackupCenter={init,setNodes,reset};
})();
