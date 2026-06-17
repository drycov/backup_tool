document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("textarea[id^='ox-']").forEach(function (el) {
    if (!window.ConfigEditor || el.dataset.cmInit) return;
    el.dataset.cmInit = "1";
    var model = el.dataset.model || "routeros";
    ConfigEditor.setContent(el.id, el.value || "", { model: model });
  });
});
