/* Scoped global manual job monitor. Poll only on the active page. */
(function(){
  "use strict";
  const el = id => document.getElementById("backup-ops-"+id);
  const labels={pending:"В очереди",running:"Выполняется",completed:"Успешно",failed:"Ошибка",cancelled:"Отменено"};
  let deps,timer=null,epoch=0,active=false,cursor=null,busy=false,pageBefore=null;
  function reset(){
    stop(); el("rows").replaceChildren();el("counts").replaceChildren();el("status").textContent="";el("more").hidden=true;
    el("state").value="";el("kind").value="";el("source").value="";
  }
  function stop(){active=false;epoch++;busy=false;clearInterval(timer);timer=null;cursor=null;pageBefore=null;}
  function start(){stop();active=true;load();timer=setInterval(()=>{if(!document.hidden && !pageBefore)load();},10000);}
  function td(row,value){const cell=document.createElement("td");cell.textContent=value??"—";row.append(cell);return cell;}
  async function load(before=null){
    if(!active||!deps.can("oxidized:read")||busy)return;
    busy=true;const ticket=++epoch;
    const params=new URLSearchParams({limit:"50",status:el("state").value,kind:el("kind").value,source:el("source").value});
    if(before)params.set("before",before);
    try{
      const data=await deps.api("/api/backup/jobs?"+params);
      if(ticket!==epoch||!active||!deps.can("oxidized:read"))return;
      pageBefore=before;cursor=data.next_before;el("more").hidden=!cursor;
      const counts=el("counts");counts.replaceChildren();
      for(const [key,label] of Object.entries(labels)){
        const card=document.createElement("div"),value=document.createElement("div"),name=document.createElement("div");
        card.className="dk-stat";value.className="dk-stat__value";name.className="dk-stat__label";
        value.textContent=data.counts?.[key]||0;name.textContent=label;card.append(value,name);counts.append(card);
      }
      const root=el("rows");root.replaceChildren();
      for(const j of data.items||[]){
        const row=document.createElement("tr");
        td(row,j.id);td(row,j.device);td(row,j.source==="automatic"?"Авто":"Ручное");td(row,j.kind==="config"?"Config":"Binary / RSC");td(row,labels[j.status]||j.status);td(row,deps.formatDate(j.created_at));td(row,deps.formatDate(j.finished_at));
        const actions=td(row,"");
        if(j.status==="pending"&&deps.can("oxidized:write")){
          const btn=document.createElement("button");btn.type="button";btn.className="dk-btn dk-btn--danger dk-btn--sm";btn.textContent="Отменить";
          btn.addEventListener("click",async()=>{
            if(!deps.can("oxidized:write")||!confirm("Отменить задание #"+j.id+"?"))return;
            btn.disabled=true;
            try{await deps.api("/api/backup/jobs/"+j.id+"/cancel",{method:"POST"});refresh();}
            catch(e){el("status").textContent=e.message;btn.disabled=false;}
          });actions.append(btn);
        }
        root.append(row);
      }
      el("status").textContent=(data.items||[]).length?"Обновлено: "+deps.formatDate(new Date().toISOString()):"Нет заданий по выбранным фильтрам";
    }catch(e){if(ticket===epoch&&active)el("status").textContent=e.message;}
    finally{if(ticket===epoch)busy=false;}
  }
  function refresh(){epoch++;busy=false;load();}
  function init(adapters){deps=adapters;el("refresh").addEventListener("click",refresh);el("state").addEventListener("change",refresh);el("kind").addEventListener("change",refresh);el("source").addEventListener("change",refresh);el("more").addEventListener("click",()=>load(cursor));}
  window.BackupOperations={init,start,stop,reset};
})();
