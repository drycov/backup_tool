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

  function defineIosMode() {
    if (!global.CodeMirror || global.CodeMirror.modes.ioslike) return;
    global.CodeMirror.defineSimpleMode("ioslike", {
      start: [
        { regex: /!.*/, token: "comment" },
        { regex: /\b(interface|hostname|ip|router|line|snmp-server|username|enable|no)\b/, token: "keyword" },
        { regex: /"(?:[^\\"]|\\.)*"/, token: "string" },
        { regex: /\b\d+\.\d+\.\d+\.\d+\b/, token: "number" },
      ],
    });
  }

  function defineJunosMode() {
    if (!global.CodeMirror || global.CodeMirror.modes.junoslike) return;
    global.CodeMirror.defineSimpleMode("junoslike", {
      start: [
        { regex: /#.*/, token: "comment" },
        { regex: /\b(system|interfaces|routing-options|protocols)\b/, token: "keyword" },
        { regex: /"(?:[^\\"]|\\.)*"/, token: "string" },
        { regex: /\{|\}/, token: "bracket" },
      ],
    });
  }

  function detectMode(text, modelHint) {
    const hint = String(modelHint || "").toLowerCase();
    if (/routeros|mikrotik|ros/.test(hint) || /^\/[\w/.-]+/m.test(text || "")) {
      return "routeros";
    }
    if (/junos|juniper/.test(hint) || /\{\s*$/.test(text || "") || /^\s*system\s*\{/m.test(text || "")) {
      return "junoslike";
    }
    if (/ios|eos|nxos|asa|cisco|arista/.test(hint) || /^interface /m.test(text || "")) {
      return "ioslike";
    }
    return "routeros";
  }

  function getEditor(textareaId) {
    if (editors.has(textareaId)) return editors.get(textareaId);
    const el = document.getElementById(textareaId);
    if (!el || !global.CodeMirror) return null;

    defineRouterOsMode();
    defineIosMode();
    defineJunosMode();
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
