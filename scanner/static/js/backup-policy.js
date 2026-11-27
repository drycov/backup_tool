(function(){
  "use strict";
  let deps, generation=0;
  async function load(name){
    const ticket=++generation, root=document.getElementById("backup-policy-summary");
    root.textContent="";
    if(!name||!deps?.can("oxidized:read"))return;
    try{
      const query=encodeURIComponent(name);
      const p=await deps.api("/api/backup/policy?device="+query);
      if(ticket!==generation||!deps.can("oxidized:read"))return;
      root.textContent="Политика: "+p.group+" · интервал "+p.interval_sec+" сек ("+p.interval_source+") · Binary "+(p.binary_enabled?"вкл":"выкл")+" · RSC "+(p.export_enabled?"вкл":"выкл")+" · ротация "+(p.retention_enabled?p.retention_keep:"выкл")+" · SLA "+(p.sla_hours??"—")+" ч · расписание "+(p.scheduled_paused?"приостановлено":"активно");
      try {
        const result=await deps.api("/api/backup/integrity?device="+query);
        if(ticket===generation && deps.can("oxidized:read")) root.textContent+=" · Git SHA-256: "+({verified:"OK",mismatch:"Несовпадение",missing:"Нет файла",untracked:"Нет версии"}[result.status]||result.status);
      } catch (_) { if(ticket===generation && deps.can("oxidized:read")) root.textContent+=" · Проверка Git недоступна"; }
    }catch(e){if(ticket===generation)root.textContent="Политика недоступна: "+e.message;}
  }
  window.BackupPolicy={init(adapters){deps=adapters;},load};
})();
