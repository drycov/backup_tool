(function (global) {
  "use strict";

  const editors = new Map();

  function defineRouterOsMode() {
    if (!global.CodeMirror || global.CodeMirror.modes.routeros) return;
    global.CodeMirror.defineSimpleMode("routeros", {
      start: [
        { regex: /#.*/, token: "comment" },
        { regex: /^\/[\w/.-]+/, token: "header" },
        {
          regex: /\b(add|set|remove|enable|disable|move|copy|drop|find|print|export|import)\b/,
          token: "keyword",
        },
        { regex: /"(?:[^\\"]|\\.)*"/, token: "string" },
        { regex: /\b(?:true|false|yes|no)\b/, token: "atom" },
        { regex: /\b\d+(?:\.\d+)*\/\d+\b/, token: "number" },
        { regex: /\b\d+(?:\.\d+)+\b/, token: "number" },
        { regex: /\[[^\]]+\]/, token: "variable-2" },
        { regex: /=[\w/.:@%-]+/, token: "def" },
      ],
    });
  }

  function detectMode(text, modelHint) {
    if (modelHint && /routeros|mikrotik|ros/i.test(String(modelHint))) {
      return "routeros";
    }
    if (/^\/[\w/.-]+/m.test(text || "")) return "routeros";
    return "routeros";
  }

  function getEditor(textareaId) {
    if (editors.has(textareaId)) return editors.get(textareaId);
    const el = document.getElementById(textareaId);
    if (!el || !global.CodeMirror) return null;

    defineRouterOsMode();
    const cm = global.CodeMirror.fromTextArea(el, {
      mode: "routeros",
      theme: "dracula",
      readOnly: true,
      lineNumbers: true,
      lineWrapping: true,
      viewportMargin: Infinity,
      scrollbarStyle: "native",
    });
    editors.set(textareaId, cm);
    return cm;
  }

  function setContent(textareaId, text, options) {
    const opts = options || {};
    const value = text || "Пустой конфиг";
    const cm = getEditor(textareaId);
    if (!cm) {
      const el = document.getElementById(textareaId);
      if (el) {
        el.classList.remove("d-none");
        el.value = value;
      }
      return;
    }
    cm.setOption("mode", detectMode(value, opts.model));
    cm.setValue(value);
    window.setTimeout(() => cm.refresh(), 30);
  }

  function refreshAll() {
    editors.forEach(cm => cm.refresh());
  }

  global.ConfigEditor = {
    setContent,
    refreshAll,
    getEditor,
  };
})(window);
