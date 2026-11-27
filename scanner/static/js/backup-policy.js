(function(){
  "use strict";
  let deps, generation=0, selected=null, editorGeneration=0;
  const get=id=>document.getElementById(id);
  const fields={interval_sec:"Интервал, сек",sla_hours:"SLA, ч",binary_enabled:"Binary",export_enabled:"RSC",notify_telegram:"Telegram (ошибки)",notify_email:"Email (ошибки)",maintenance_override:"Пауза расписания"};
  const numeric=new Set(["interval_sec","sla_hours"]);
  const url=(p)=>"/api/backup/overrides?"+new URLSearchParams({scope:get("backup-policy-scope").value,target:get("backup-policy-scope").value==="site"?p.site:p.device});
  async function editor(p,ticket){
    const editTicket=++editorGeneration;
    const root=get("backup-policy-editor"), scope=get("backup-policy-scope"), msg=get("backup-policy-message"), button=get("backup-policy-save");
    button.disabled=true;
    if(!deps.can("oxidized:write")){root.hidden=true;return;}
    scope.options[1].disabled=!p.site;
    if(!p.site)scope.value="device";
    const endpoint=url(p);
    let data;
    try{data=await deps.api(endpoint);}catch(_){if(editTicket===editorGeneration)root.hidden=true;return;}
    if(ticket!==generation || selected!==p || editTicket!==editorGeneration)return;
    root.hidden=false;
    const container=get("backup-policy-fields");
    container.replaceChildren();
    for(const [key,title] of Object.entries(fields)){
      const label=document.createElement("label"); label.className="dk-field"; label.textContent=title+" ("+p.sources[key]+")";
      const input=document.createElement(numeric.has(key)?"input":"select");
      input.dataset.field=key; input.className="form-control";
      if(numeric.has(key)){input.type="number";input.min=key==="interval_sec"?60:1;input.max=key==="interval_sec"?604800:8760;input.placeholder="Наследовать";}
      else for(const [v,t] of [["","Наследовать"],["true","Включить"],["false","Выключить"]])input.add(new Option(t,v));
      input.value=data.values[key]??"";label.append(input);container.append(label);
    }
    msg.textContent="";button.disabled=false;
  }
  async function changes(name,ticket){
    const rows=get("backup-change-rows");rows.replaceChildren();
    if(!name)return;
    try{
      const data=await deps.api("/api/backup/changes?device="+encodeURIComponent(name));
      if(ticket!==generation)return;
      for(const item of data.items){
        const tr=rows.insertRow();
        for(const value of [item.created_at,item.commit_oid.slice(0,12),item.severity,item.categories.join(", "),item.added+" / "+item.removed])tr.insertCell().textContent=value;
      }
      if(!data.items.length){const cell=rows.insertRow().insertCell();cell.colSpan=5;cell.textContent="Нет зарегистрированных изменений";}
    }catch(_){if(ticket===generation){const cell=rows.insertRow().insertCell();cell.colSpan=5;cell.textContent="Журнал недоступен";}}
  }
  async function load(name){
    const ticket=++generation, root=get("backup-policy-summary");
    selected=null;root.textContent="";get("backup-policy-editor").hidden=true;get("backup-change-rows").replaceChildren();
    if(!name||!deps?.can("oxidized:read"))return;
    changes(name,ticket);
    try{
      const query=encodeURIComponent(name);
      const p=await deps.api("/api/backup/policy?device="+query);
      if(ticket!==generation||!deps.can("oxidized:read"))return;
      selected=p;
      root.textContent="Политика: "+p.group+" · интервал "+p.interval_sec+" сек ("+p.interval_source+") · Binary "+(p.binary_enabled?"вкл":"выкл")+" · RSC "+(p.export_enabled?"вкл":"выкл")+" · ротация "+(p.retention_enabled?p.retention_keep:"выкл")+" · SLA "+(p.sla_hours??"—")+" ч · расписание "+(p.scheduled_paused?"приостановлено":"активно");
      editor(p,ticket);
      try{
        const result=await deps.api("/api/backup/integrity?device="+query);
        if(ticket===generation&&deps.can("oxidized:read"))root.textContent+=" · Git SHA-256: "+result.status;
      }catch(_){if(ticket===generation)root.textContent+=" · Проверка Git недоступна";}
    }catch(e){if(ticket===generation)root.textContent="Политика недоступна: "+e.message;}
  }
  function init(adapters){
    deps=adapters;
    get("backup-policy-scope").addEventListener("change",()=>{if(selected)editor(selected,generation);});
    get("backup-policy-save").addEventListener("click",async()=>{
      const p=selected,ticket=generation,button=get("backup-policy-save");
      if(!p||!deps.can("oxidized:write"))return;
      const values={};
      for(const input of get("backup-policy-fields").querySelectorAll("[data-field]")){
        if(!input.reportValidity())return;
        values[input.dataset.field]=input.value===""?null:numeric.has(input.dataset.field)?Number(input.value):input.value==="true";
      }
      button.disabled=true;
      try{await deps.api(url(p),{method:"PUT",body:JSON.stringify(values)});if(ticket===generation)await load(p.device);}
      catch(e){if(ticket===generation){get("backup-policy-message").textContent=e.message;button.disabled=false;}}
    });
  }
  window.BackupPolicy={init,load};
})();
