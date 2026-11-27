(function(){
  "use strict";
  let deps, generation=0;
  async function load(name){
    const ticket=++generation, root=document.getElementById("backup-policy-summary");
    root.textContent="";
    if(!name||!deps?.can("oxidized:read"))return;
    try{
      const p=await deps.api("/api/backup/policy?device="+encodeURIComponent(name));
      if(ticket!==generation||!deps.can("oxidized:read"))return;
      root.textContent="Политика: "+p.group+" · интервал "+p.interval_sec+" сек ("+p.interval_source+") · Binary "+(p.binary_enabled?"вкл":"выкл")+" · RSC "+(p.export_enabled?"вкл":"выкл")+" · ротация "+(p.retention_enabled?p.retention_keep:"выкл")+" · SLA "+(p.sla_hours??"—")+" ч · расписание "+(p.scheduled_paused?"приостановлено":"активно");
    }catch(e){if(ticket===generation)root.textContent="Политика недоступна: "+e.message;}
  }
  window.BackupPolicy={init(adapters){deps=adapters;},load};
})();
