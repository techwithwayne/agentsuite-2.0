;
(() => {
  // assets/js/src/config.js
  var CFG = window.PPA || {};
  var AJAX_URL = CFG.ajax_url || CFG.ajaxUrl || (typeof ajaxurl !== "undefined" ? ajaxurl : "/wp-admin/admin-ajax.php");
  var NONCE = CFG.nonce || "";
  var DEBUG = !!CFG.debug;
  var $ = (sel, root) => (root || document).querySelector(sel);
  var $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  function log(...args) {
    if (DEBUG && window.console) console.log("[PPA]", ...args);
  }
  function warn(...args) {
    if (window.console) console.warn("[PPA]", ...args);
  }
  function getNonce() {
    if (NONCE) return NONCE;
    var dom = $("#ppa-nonce");
    return dom ? String(dom.value || "") : "";
  }
  function resolveAssetUrl(rel) {
    var r = String(rel || "").replace(/^\/+/, "");
    if (CFG.assets_url) return CFG.assets_url.replace(/\/+$/, "/") + r;
    if (CFG.pluginUrl) return CFG.pluginUrl.replace(/\/+$/, "/") + r;
    if (CFG.plugin_url) return CFG.plugin_url.replace(/\/+$/, "/") + r;
    var PLUGIN_SEG = "/wp-content/plugins/postpress-ai/";
    try {
      var cs = document.currentScript && document.currentScript.src;
      if (cs && cs.includes(PLUGIN_SEG)) {
        var u = new URL(cs, window.location.origin);
        var base = u.origin + u.pathname.slice(0, u.pathname.indexOf(PLUGIN_SEG) + PLUGIN_SEG.length);
        return base.replace(/\/+$/, "/") + r;
      }
    } catch (_) {
    }
    try {
      var scripts = document.getElementsByTagName("script");
      for (var i = scripts.length - 1; i >= 0; i--) {
        var src = scripts[i].src || "";
        if (!src) continue;
        if (src.includes(PLUGIN_SEG)) {
          var u = new URL(src, window.location.origin);
          var base = u.origin + u.pathname.slice(0, u.pathname.indexOf(PLUGIN_SEG) + PLUGIN_SEG.length);
          return base.replace(/\/+$/, "/") + r;
        }
      }
    } catch (_) {
    }
    try {
      return window.location.origin.replace(/\/+$/, "") + PLUGIN_SEG + r;
    } catch (_) {
      return PLUGIN_SEG + r;
    }
  }

  // assets/js/src/fields.js
  function collectFields(input) {
    if (!input) return {};
    var out = /* @__PURE__ */ Object.create(null);
    function pushKey(k, v) {
      if (out[k] === void 0) {
        out[k] = v;
      } else if (Array.isArray(out[k])) {
        out[k].push(v);
      } else {
        out[k] = [out[k], v];
      }
    }
    try {
      if (typeof FormData !== "undefined" && input instanceof FormData) {
        for (var pair of input.entries()) {
          var k = pair[0];
          var v = pair[1];
          var m = k.match(/^fields\[(.+)\]$/);
          if (m) {
            pushKey(m[1], String(v));
          } else {
            pushKey(k, String(v));
          }
        }
        return out;
      }
    } catch (e) {
    }
    try {
      if (typeof URLSearchParams !== "undefined" && input instanceof URLSearchParams) {
        for (var [k, v] of input.entries()) {
          var m = k.match(/^fields\[(.+)\]$/);
          if (m) {
            pushKey(m[1], String(v));
          } else {
            pushKey(k, String(v));
          }
        }
        return out;
      }
    } catch (e) {
    }
    if (typeof input === "object") {
      for (var k of Object.keys(input)) {
        var v = input[k];
        if (Array.isArray(v)) {
          out[k] = v.map((x) => x == null ? "" : String(x));
        } else if (v == null) {
          out[k] = "";
        } else {
          out[k] = String(v);
        }
      }
      return out;
    }
    return {};
  }
  function appendFieldsToFormData(fd, fields = {}) {
    if (!fd || typeof fd.append !== "function") return;
    for (var key of Object.keys(fields)) {
      var val = fields[key];
      if (Array.isArray(val)) {
        for (var v of val) {
          fd.append(`fields[${key}]`, v == null ? "" : String(v));
        }
      } else {
        fd.append(`fields[${key}]`, val == null ? "" : String(val));
      }
    }
    var existing = /* @__PURE__ */ new Set();
    try {
      for (var pair of fd.entries()) {
        existing.add(pair[0]);
      }
    } catch (e) {
    }
    for (var key of Object.keys(fields)) {
      if (existing.has(key)) continue;
      var val = fields[key];
      if (Array.isArray(val)) {
        for (var v of val) {
          try {
            fd.append(String(key), v == null ? "" : String(v));
          } catch (_) {
          }
        }
      } else {
        try {
          fd.append(String(key), val == null ? "" : String(val));
        } catch (_) {
        }
      }
    }
    var hasTitle = existing.has("title");
    if (!hasTitle) {
      if ("title" in fields && fields.title !== void 0 && fields.title !== null && String(fields.title) !== "") {
        try {
          fd.append("title", String(fields.title));
        } catch (_) {
        }
        hasTitle = true;
      }
    }
    if (!hasTitle) {
      var subjectVal = fields.subject || fields.headline || null;
      if (subjectVal != null && String(subjectVal) !== "") {
        try {
          fd.append("title", Array.isArray(subjectVal) ? String(subjectVal[0]) : String(subjectVal));
        } catch (_) {
        }
      }
    }
  }

  // assets/js/src/ajax.js
  async function postAjax(action, extra = {}) {
    var nonce = getNonce();
    if (!nonce) throw new Error("Missing nonce");
    var fd = new FormData();
    fd.append("action", action);
    fd.append("nonce", nonce);
    fd.append("security", nonce);
    if (extra.mode) fd.append("mode", String(extra.mode));
    appendFieldsToFormData(fd, extra.fields || {});
    var res = await fetch(AJAX_URL, {
      method: "POST",
      credentials: "same-origin",
      body: fd,
      headers: { "X-Requested-With": "XMLHttpRequest" }
    });
    var text = await res.text().catch(() => "");
    var parsed;
    try {
      var trimmed = text.trim();
      if (trimmed === "") {
        parsed = "";
      } else {
        parsed = JSON.parse(trimmed);
      }
    } catch (err) {
      parsed = text;
    }
    if (!res.ok) {
      var snippet = typeof parsed === "object" ? JSON.stringify(parsed).slice(0, 280) : String(parsed).slice(0, 280);
      throw new Error(`HTTP ${res.status}: ${snippet}`);
    }
    return parsed;
  }

  // assets/js/src/preview.js
  function findPreviewPane() {
    var cands = [".ppa-generated-preview", "#ppa-preview-html", "#ppa_preview_html", "#ppa-preview-window", "#ppa-preview-pane", ".ppa-preview-pane", "#ppa-preview", ".ppa-preview"];
    for (var sel of cands) {
      var el = $(sel);
      if (el) return el;
    }
    return null;
  }
  function extractPreviewHTML(json) {
    if (!json) return "";
    if (typeof json === "string") return json;
    var g = (obj, path) => {
      try {
        return path.split(".").reduce((a, k) => a && a[k] != null ? a[k] : void 0, obj);
      } catch (_) {
        return void 0;
      }
    };
    var candidates = [
      "result.html",
      "result.content",
      "result.body",
      "data.html",
      "html",
      "wp_body",
      "body",
      "payload.output.html",
      "output.html",
      "content.rendered",
      "rendered",
      "markup",
      "preview_html"
    ];
    for (var p of candidates) {
      var v = g(json, p);
      if (typeof v === "string" && v.trim()) return v;
    }
    if (json.result && typeof json.result === "object") {
      for (var v of Object.values(json.result)) {
        if (typeof v === "string" && /<\/(p|div|h\d|article|section)>/i.test(v)) return v;
      }
    }
    var msg = g(json, "message") || g(json, "error") || g(json, "result.message");
    if (typeof msg === "string" && msg.trim()) return `<p><em>${msg}</em></p>`;
    return "";
  }
  function renderPreviewHTMLFromJSON(json) {
  // pick pane (prefer your existing block)
  var pane = document.querySelector('.ppa-generated-preview');
  if (!pane && typeof findPreviewPane === 'function') pane = findPreviewPane();
  if (!pane) {
    var host = document.querySelector('#wpbody-content') || document.body;
    pane = document.createElement('div');
    pane.className = 'ppa-generated-preview';
    host.appendChild(pane);
  }

  // resolve HTML string
  var html = '';
  try {
    if (typeof extractPreviewHTML === 'function') {
      html = extractPreviewHTML(json) || '';
    } else if (json && typeof json === 'object') {
      // try common envelopes
      if (json.success && json.data)       html = json.data.html || '';
      else if (json.ok && json.result)     html = json.result.html || '';
      else                                 html = json.html || '';
    } else {
      html = String(json || '');
    }
  } catch(e) { html = ''; }
  if (!html || !html.trim()) html = "<p><em>No preview HTML returned.</em></p>";

  // preserve existing <h1>, replace everything below it
  var titleEl = pane.querySelector('h1');
  if (titleEl) {
    while (titleEl.nextSibling) titleEl.nextSibling.remove();
    var wrap = document.createElement('div');
    wrap.className = 'ppa-preview-body';
    wrap.innerHTML = html;
    titleEl.insertAdjacentElement('afterend', wrap);
  } else {
    pane.innerHTML = html;
  }

  // ensure visible
  pane.hidden = false;
  pane.style.display = '';
  pane.classList?.remove('hidden','is-hidden');
}

  // Resolve HTML from JSON or raw string (use existing helper if present)
  var html = '';
  try {
    if (typeof extractPreviewHTML === 'function') {
      html = extractPreviewHTML(json) || '';
    } else if (json && typeof json === 'object') {
      html = json.html || '';
    } else {
      html = String(json||'');
    }
  } catch (e) {
    html = '';
  }
  if (!html || !html.trim()) {
    html = "<p><em>No preview HTML returned.</em></p>";
  }

  // If there is a <h1> title in the pane, preserve it and replace everything after it.
  var titleEl = pane.querySelector('h1');
  if (titleEl) {
    // remove all siblings after the <h1>
    while (titleEl.nextSibling) titleEl.nextSibling.remove();
    var wrap = document.createElement('div');
    wrap.className = 'ppa-preview-body';
    wrap.innerHTML = html;
    titleEl.insertAdjacentElement('afterend', wrap);
  } else {
    // no title: replace entire pane
    pane.innerHTML = html;
  }

  // ensure visible if some admin CSS hid it
  pane.hidden = false;
  pane.style.display = '';
  pane.classList.remove('hidden','is-hidden');
}
    var html = extractPreviewHTML(json);
    pane.innerHTML = html && html.trim() ? html : "<p><em>No preview HTML returned.</em></p>";
  }

  // assets/js/src/loader.js
  function ensurePreviewLoader() {
    var pane = findPreviewPane();
    if (!pane) return null;
    var overlay = pane.querySelector(".ppa-preloader");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "ppa-preloader";
      overlay.setAttribute("aria-hidden", "true");
      var spinner = document.createElement("div");
      spinner.className = "ppa-lds-spinner";
      for (var i = 0; i < 12; i++) spinner.appendChild(document.createElement("div"));
      var label = document.createElement("div");
      label.className = "ppa-preloader-label";
      label.textContent = "Generating preview\u2026";
      overlay.appendChild(spinner);
      overlay.appendChild(label);
      pane.appendChild(overlay);
    }
    return overlay;
  }
  function setPreviewLoaderLabel(text) {
    var pane = findPreviewPane();
    if (!pane) return;
    var overlay = ensurePreviewLoader();
    if (!overlay) return;
    var label = overlay.querySelector(".ppa-preloader-label");
    if (!label) {
      label = document.createElement("div");
      label.className = "ppa-preloader-label";
      overlay.appendChild(label);
    }
    label.textContent = String(text || "").trim() || "Working\u2026";
  }
  function showPreviewLoader(labelText) {
    var pane = findPreviewPane();
    if (!pane) return;
    ensurePreviewLoader();
    if (labelText) setPreviewLoaderLabel(labelText);
    pane.classList.add("ppa-is-loading");
    pane.setAttribute("aria-busy", "true");
  }
  function hidePreviewLoader() {
    var pane = findPreviewPane();
    if (!pane) return;
    pane.classList.remove("ppa-is-loading");
    pane.removeAttribute("aria-busy");
  }

  // assets/js/src/workingTab.js
  var BRAND_BG = "#121212";
  var BRAND_ACCENT = "#ff6c00";
  function writeWorkingHTML(doc, heading, sub) {
    doc.open();
    doc.write(`<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>PostPress AI \u2014 ${heading ? String(heading) : "Working\u2026"}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root { --bg:${BRAND_BG}; --accent:${BRAND_ACCENT}; --text:#f2f2f2; --muted:#bcbcbc; }
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Ubuntu,"Helvetica Neue",Arial,sans-serif;display:grid;place-items:center}
.wrap{max-width:720px;padding:24px;text-align:center}
h1{margin:0 0 8px;font-size:22px;letter-spacing:.2px}
p{margin:8px 0 0;color:var(--muted)}
.ring{position:relative;width:58px;height:58px;margin:20px auto 14px;border-radius:50%;
border:3px solid rgba(255,255,255,.12);border-top-color:var(--accent);border-right-color:#ff8a33;animation:spin .8s linear infinite;box-shadow:0 0 0 2px rgba(0,0,0,.18) inset}
.dots::after{content:".";animation:dots 1.2s steps(3,end) infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes dots{0%{content:"."}33%{content:".."}66%{content:"..."}100%{content:"."}}
.brand{display:inline-block;margin-top:6px;font-weight:700;color:#ffb27a}
</style></head>
<body><div class="wrap">
<div class="ring" aria-hidden="true"></div>
<h1 id="ppa-status">${heading ? String(heading) : "Working"}<span class="dots"></span></h1>
<p id="ppa-sub">${sub ? String(sub) : "Please keep this tab open \u2014 we will take you to the WordPress editor as soon as your post is ready."}</p>
<div class="brand">PostPress&nbsp;AI</div>
</div></body></html>`);
    doc.close();
  }
  function openWorkingTab() {
    var w = null;
    try {
      w = window.open("about:blank", "_blank");
      if (w && w.document) writeWorkingHTML(w.document, "Preparing", "Initializing\u2026");
    } catch (_) {
    }
    return w;
  }
  function updateWorkingTab(w, heading, sub) {
    if (!w || w.closed) return;
    try {
      var d = w.document, s = d.getElementById("ppa-status"), p = d.getElementById("ppa-sub");
      if (s && heading) s.textContent = String(heading);
      if (p && sub) p.textContent = String(sub);
      if (s) {
        var span = d.createElement("span");
        span.className = "dots";
        s.appendChild(span);
      }
    } catch (_) {
    }
  }

  // assets/js/src/actions.js
  async function onPreviewClick(ev) {
    ev && ev.preventDefault && ev.preventDefault();
    showPreviewLoader("Generating preview\u2026");
    try {
      var formEl = document.querySelector(".ppa-form") || document.querySelector("form");
      var fd = (formEl var fields = collectFields();var fields = collectFields(); typeof FormData !== "undefined") ? new FormData(formEl) : null;
      var fields = collectFields(fd || {});
      var json = await postAjax("ppa_preview", { fields });
      renderPreviewHTMLFromJSON(json);
    } catch (e) {
      warn("Preview error", e);
      setPreviewLoaderLabel("Something went wrong \u2014 see console.");
    } finally {
      hidePreviewLoader();
    }
  }
  async function onStoreClick(mode, ev) {
    ev && ev.preventDefault && ev.preventDefault();
    var openedTab = openWorkingTab();
    showPreviewLoader("Generating preview\u2026");
    try {
      var formEl = document.querySelector(".ppa-form") || document.querySelector("form");
      var fd = (formEl var fieldsBase = collectFields();var fieldsBase = collectFields(); typeof FormData !== "undefined") ? new FormData(formEl) : null;
      var fieldsBase = collectFields(fd || {});
      var fields = Object.assign({}, fieldsBase, { quality: "final", mode });
      try {
        updateWorkingTab(openedTab, "Generating preview", "Asking AI for final content\u2026");
        var previewJson = await postAjax("ppa_preview", { fields });
        renderPreviewHTMLFromJSON(previewJson);
        var rr = previewJson && previewJson.result || {};
        fields = Object.assign({}, fields, {
          title: rr.title || fields.title || fieldsBase.title || fieldsBase.subject || "",
          html: rr.html || fields.html || fieldsBase.html || "",
          summary: rr.summary || fields.summary || fieldsBase.summary || ""
        });
      } catch (e) {
        log("Final-quality preview failed; continuing to store.", e);
      }
      setPreviewLoaderLabel("Saving draft\u2026");
      updateWorkingTab(openedTab, "Saving draft", "Creating your post in WordPress\u2026");
      var json = await postAjax("ppa_store", { mode, fields });
      var editUrl = json && (json.edit_url || json.edit_url_note) || "";
      if (!editUrl) {
        try {
          var id = json && json.result && json.result.id;
          var base = ((window == null ? void 0 : window.ajaxurl) || AJAX_URL || "").replace(/\/admin-ajax\.php$/, "/post.php");
          if (id && base) editUrl = `${base}?post=${encodeURIComponent(id)}&action=edit`;
        } catch (_) {
        }
      }
      if (editUrl) {
        setPreviewLoaderLabel("Opening editor\u2026");
        updateWorkingTab(openedTab, "Opening editor", "Redirecting to the WordPress post editor\u2026");
        try {
          if (openedTab && !openedTab.closed) {
            openedTab.location.replace(editUrl);
            openedTab.focus();
          } else {
            window.open(editUrl, "_blank", "noopener");
          }
        } catch (_) {
          window.open(editUrl, "_blank", "noopener");
        }
      } else {
        log("Store completed without edit_url.");
      }
    } catch (e) {
      warn("Store error", e);
      setPreviewLoaderLabel("Something went wrong \u2014 see console.");
    } finally {
      hidePreviewLoader();
    }
  }

  // assets/js/src/autocomplete.js
  var AC_TARGET_IDS = ["ppa-tone", "ppa-audience", "ppa-keywords"];
  var DEBOUNCE_MS = 180;
  var AUTOCOMPLETE_DATA = null;
  var DEFAULT_AUTOCOMPLETE = {
    tone: [
      "Friendly",
      "Professional",
      "Persuasive",
      "Technical",
      "Casual",
      "Storytelling",
      "Inspirational",
      "Luxury",
      "Minimalist",
      "Playful",
      "Serious",
      "Conversational",
      "Educational",
      "Authoritative"
    ],
    audience: [
      "Small Business Owners",
      "Entrepreneurs",
      "Students",
      "Iowa Residents",
      "Marketers",
      "Developers",
      "Designers",
      "Executives",
      "Local Community",
      "Ecommerce Owners",
      "Parents",
      "Nonprofits"
    ],
    keywords: [
      "WordPress",
      "SEO",
      "Content Marketing",
      "AI",
      "Iowa Web Design",
      "Small Business Growth",
      "Luxury Branding",
      "Website Redesign",
      "Conversion Optimization",
      "Social Media Strategy",
      "Email Marketing",
      "Page Speed"
    ]
  };
  async function loadAutocompleteData() {
    if (AUTOCOMPLETE_DATA) return AUTOCOMPLETE_DATA;
    try {
      var url = resolveAssetUrl("assets/data/autocomplete.json");
      var res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      AUTOCOMPLETE_DATA = await res.json();
      if (!AUTOCOMPLETE_DATA || typeof AUTOCOMPLETE_DATA !== "object") {
        throw new Error("Bad JSON payload");
      }
    } catch (e) {
      warn("Autocomplete data load failed, using defaults.", e);
      AUTOCOMPLETE_DATA = DEFAULT_AUTOCOMPLETE;
    }
    return AUTOCOMPLETE_DATA;
  }
  function acGetList(input) {
    var sib = input && input.nextElementSibling;
    if (sib && sib.classList && sib.classList.contains("ppa-autocomplete-list")) return sib;
    if (input && input.parentElement) return input.parentElement.querySelector(".ppa-autocomplete-list");
    return null;
  }
  function acGetItems(list) {
    return Array.from(list ? list.querySelectorAll("li") : []);
  }
  function acEnsureARIA(input) {
    if (!input) return;
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-haspopup", "listbox");
    if (!input.hasAttribute("aria-expanded")) input.setAttribute("aria-expanded", "false");
  }
  function acWireListARIA(input, list) {
    if (!input) return;
    if (!list) {
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      input.removeAttribute("aria-controls");
      return;
    }
    if (!list.id) list.id = "ppa-ac-" + (input.id || Math.random().toString(36).slice(2));
    input.setAttribute("aria-controls", list.id);
    input.setAttribute("aria-expanded", "true");
    var items = acGetItems(list);
    items.forEach((li, i) => {
      if (!li.id) li.id = `${list.id}-opt-${i}`;
      if (li.getAttribute("aria-selected") === "true") {
        input.setAttribute("aria-activedescendant", li.id);
      }
    });
    if (!input.getAttribute("aria-activedescendant") && items[0]) {
      input.setAttribute("aria-activedescendant", items[0].id);
    }
  }
  function acSyncAriaActiveFromHighlight(input) {
    var list = acGetList(input);
    if (!list) return;
    var active = list.querySelector('li[aria-selected="true"]');
    if (active && active.id) input.setAttribute("aria-activedescendant", active.id);
  }
  function acSetActiveIndex(input, idx) {
    var list = acGetList(input);
    if (!list) return -1;
    var items = acGetItems(list);
    items.forEach((li, i) => {
      if (i === idx) {
        li.setAttribute("aria-selected", "true");
        try {
          li.scrollIntoView({ block: "nearest" });
        } catch (_) {
        }
      } else {
        li.removeAttribute("aria-selected");
      }
    });
    input.setAttribute("data-ppa-ac-index", String(idx));
    acSyncAriaActiveFromHighlight(input);
    return idx;
  }
  function acEnsureFirstActive(input) {
    var list = acGetList(input);
    if (!list) return;
    var already = list.querySelector('[aria-selected="true"]');
    var idxAttr = parseInt(input.getAttribute("data-ppa-ac-index") || "-1", 10);
    if (!already && (isNaN(idxAttr) || idxAttr < 0)) {
      var items = acGetItems(list);
      if (items.length) acSetActiveIndex(input, 0);
    }
  }
  function acMove(input, dir) {
    var list = acGetList(input);
    if (!list) return;
    var items = acGetItems(list);
    if (!items.length) return;
    var idx = parseInt(input.getAttribute("data-ppa-ac-index") || "-1", 10);
    if (isNaN(idx)) idx = -1;
    idx += dir;
    if (idx < 0) idx = items.length - 1;
    if (idx >= items.length) idx = 0;
    acSetActiveIndex(input, idx);
  }
  function acAcceptHighlighted(input) {
    var list = acGetList(input);
    if (!list) return false;
    var li = list.querySelector('li[aria-selected="true"]') || list.querySelector("li");
    if (!li) return false;
    input.value = (li.textContent || "").trim();
    try {
      list.remove();
    } catch (_) {
    }
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    try {
      input.dispatchEvent(new Event("change", { bubbles: true }));
    } catch (_) {
    }
    input.removeAttribute("data-ppa-ac-index");
    return true;
  }
  function acClose(input) {
    var list = acGetList(input);
    if (list && list.parentNode) list.parentNode.removeChild(list);
    input.removeAttribute("data-ppa-ac-index");
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }
  function acHideAllLists() {
    document.querySelectorAll(".ppa-autocomplete-list").forEach((el) => el.remove());
  }
  function acShowListFor(input, fieldType) {
    acHideAllLists();
    if (!AUTOCOMPLETE_DATA || !AUTOCOMPLETE_DATA[fieldType]) return;
    var val = String(input.value || "").trim().toLowerCase();
    if (!val) return;
    var matches = AUTOCOMPLETE_DATA[fieldType].filter((opt) => opt.toLowerCase().includes(val)).slice(0, 8);
    if (!matches.length) return;
    var ul = document.createElement("ul");
    ul.className = "ppa-autocomplete-list";
    ul.setAttribute("role", "listbox");
    matches.forEach((opt) => {
      var li = document.createElement("li");
      li.textContent = opt;
      li.setAttribute("role", "option");
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        input.value = opt;
        acClose(input);
      });
      ul.appendChild(li);
    });
    input.insertAdjacentElement("afterend", ul);
    acEnsureFirstActive(input);
    acWireListARIA(input, ul);
  }
  function acIsTypingKey(k) {
    return !(k === "ArrowDown" || k === "ArrowUp" || k === "Enter" || k === "Escape" || k === "Tab" || k === "Debounced");
  }
  function acDispatchDebouncedKeyup(input) {
    try {
      var ev = new KeyboardEvent("keyup", { key: "Debounced", bubbles: true, cancelable: true });
      input.dispatchEvent(ev);
    } catch (_) {
      var ev2 = document.createEvent("Event");
      ev2.initEvent("keyup", true, true);
      ev2.key = "Debounced";
      input.dispatchEvent(ev2);
    }
  }
  function bindAutocomplete() {
    AC_TARGET_IDS.forEach((id) => {
      var input = document.getElementById(id);
      if (!input) return;
      input.setAttribute("autocomplete", "off");
      acEnsureARIA(input);
      input._ppaDebTimer = null;
      input.addEventListener("keydown", (ev) => {
        var k = ev.key;
        if (k === "ArrowDown") {
          ev.preventDefault();
          acMove(input, 1);
        } else if (k === "ArrowUp") {
          ev.preventDefault();
          acMove(input, -1);
        } else if (k === "Enter") {
          var accepted = acAcceptHighlighted(input);
          if (accepted) {
            ev.preventDefault();
            ev.stopPropagation();
          }
        } else if (k === "Tab") {
          var list = acGetList(input);
          if (list && acAcceptHighlighted(input)) {
            ev.preventDefault();
            ev.stopPropagation();
          }
        } else if (k === "Escape") {
          acClose(input);
        }
      });
      input.addEventListener("keyup", (ev) => {
        var k = ev.key;
        if (!acIsTypingKey(k)) return;
        ev.stopPropagation();
        if (input._ppaDebTimer) {
          clearTimeout(input._ppaDebTimer);
          input._ppaDebTimer = null;
        }
        var sib = input.nextElementSibling;
        if (sib && sib.classList && sib.classList.contains("ppa-autocomplete-list")) {
          try {
            sib.remove();
          } catch (_) {
          }
        }
        input._ppaDebTimer = setTimeout(() => {
          input._ppaDebTimer = null;
          acDispatchDebouncedKeyup(input);
        }, DEBOUNCE_MS);
      }, true);
      input.addEventListener("keyup", async (ev) => {
        var k = ev.key;
        if (k === "Escape") {
          acClose(input);
          return;
        }
        if (acIsTypingKey(k) && k !== "Debounced") return;
        await loadAutocompleteData();
        acShowListFor(input, id.replace("ppa-", ""));
      });
      input.addEventListener("input", () => {
        input.setAttribute("data-ppa-ac-index", "-1");
      });
      input.addEventListener("blur", () => setTimeout(() => acClose(input), 120));
      input.addEventListener("focus", () => setTimeout(() => acEnsureFirstActive(input), 0));
    });
    try {
      var mo = new MutationObserver((muts) => {
        muts.forEach((m) => {
          Array.prototype.forEach.call(m.addedNodes || [], (node) => {
            if (!(node instanceof HTMLElement)) return;
            if (node.classList && node.classList.contains("ppa-autocomplete-list")) {
              var input = node.previousElementSibling && node.previousElementSibling.tagName === "INPUT" ? node.previousElementSibling : node.parentElement && node.parentElement.querySelector("input");
              if (input) {
                acEnsureARIA(input);
                acWireListARIA(input, node);
                acSyncAriaActiveFromHighlight(input);
              }
            }
          });
        });
      });
      mo.observe(document.body, { childList: true, subtree: true });
    } catch (_) {
    }
  }

  // assets/js/src/selects.js
  function wrapSelects() {
    $$(".ppa-form select").forEach((sel) => {
      if (!sel.parentElement.classList.contains("ppa-select-wrap")) {
        var wrap = document.createElement("div");
        wrap.className = "ppa-select-wrap";
        sel.parentNode.insertBefore(wrap, sel);
        wrap.appendChild(sel);
      }
    });
  }

  // assets/js/src/boot.js
  function findButton(role) {
    var byData = $(`[data-ppa-action="${role}"]`);
    if (byData) return byData;
    var map = {
      preview: ["#ppa-preview-btn", "#ppa-btn-preview"],
      draft: ["#ppa-save-btn", "#ppa-btn-draft"],
      publish: ["#ppa-publish-btn", "#ppa-btn-publish"]
    };
    for (var sel of map[role] || []) {
      var el = $(sel);
      if (el) return el;
    }
    return null;
  }
  function boot() {
    if (!getNonce()) {
      warn("PPA nonce missing; admin-ajax calls may fail.");
    }
    var btnPreview = findButton("preview");
    var btnDraft = findButton("draft");
    var btnPublish = findButton("publish");
    if (btnPreview) btnPreview.addEventListener("click", onPreviewClick, false);
    if (btnDraft) btnDraft.addEventListener("click", onStoreClick.bind(null, "draft"), false);
    if (btnPublish) btnPublish.addEventListener("click", onStoreClick.bind(null, "publish"), false);
    bindAutocomplete();
    wrapSelects();
  }

  // assets/js/src/index.js
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
//# sourceMappingURL=admin.js.map


/* === PPA preview render fallback (inline, no extra requests) === */
(function(){
  if (window.__PPA_PANE_FALLBACK__) return; window.__PPA_PANE_FALLBACK__=true;

  function ensurePane() {
    var pane = document.querySelector('.ppa-generated-preview')
            || document.querySelector('#ppa-preview-html')
            || document.querySelector('#ppa_preview_html');
    if (!pane) {
      var host = document.querySelector('#wpbody-content') || document.body;
      pane = document.createElement('div');
      pane.className = 'ppa-generated-preview';
      host.appendChild(pane);
    }
    pane.hidden = false; pane.style.display=''; pane.classList?.remove('hidden','is-hidden');
    return pane;
  }

  function renderIntoPane(html) {
    var pane = ensurePane();
    var safe = (html && html.trim()) ? html : "<p><em>No preview HTML returned.</em></p>";
    var h1 = pane.querySelector('h1');
    if (h1) {
      while (h1.nextSibling) h1.nextSibling.remove();
      var wrap = document.createElement('div');
      wrap.className = 'ppa-preview-body';
      wrap.innerHTML = safe;
      h1.insertAdjacentElement('afterend', wrap);
    } else {
      pane.innerHTML = safe;
    }
  }

  function extractHTML(json){
    try {
      // Existing helpers first if present
      if (typeof window.extractPreviewHTML === 'function') return window.extractPreviewHTML(json) || '';
      // Common envelopes
      if (json && json.success && json.data) return json.data.html || '';
      if (json && json.ok && json.result)    return json.result.html || '';
      if (json && typeof json === 'object')  return json.html || '';
    } catch(e){}
    return (typeof json === 'string') ? json : '';
  }

  // Monkey-patch the site's renderer to always target your pane
  function hook() {
    if (typeof window.renderPreviewHTMLFromJSON !== 'function') return;
    var orig = window.renderPreviewHTMLFromJSON;
    window.renderPreviewHTMLFromJSON = function(json){
      var html = extractHTML(json);
      if (html && html.trim()) { renderIntoPane(html); return; }
      // Fallback to original if nothing extracted
      return orig.apply(this, arguments);
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hook);
  } else {
    hook();
  }
})();
 /* === end PPA preview render fallback === */

/* === PPA inline preview handler (final) === */
(function(){
  if (window.__PPA_PREVIEW_BIND__) return; window.__PPA_PREVIEW_BIND__ = true;

  function pickFields() {
    var out = {};
    document.querySelectorAll(".ppa-field[data-ppa-field], [data-ppa-field]").forEach(el => {
      var k = el.getAttribute("data-ppa-field");
      if (!k) return;
      out[k] = (el.value ?? "").trim();
    });
    if (!out.title) {
      var t = document.querySelector("#title, #post-title-0");
      if (t && t.value) out.title = t.value.trim();
    }
    if (!out.title) out.title = out.subject || out.headline || "";
    return out;
  }

  function ensurePane() {
    var pane = document.querySelector(".ppa-generated-preview")
            || document.querySelector("#ppa-preview-html")
            || document.querySelector("#ppa_preview_html");
    if (!pane) {
      var host = document.querySelector("#wpbody-content") || document.body;
      pane = document.createElement("div");
      pane.className = "ppa-generated-preview";
      host.appendChild(pane);
    }
    pane.hidden = false; pane.style.display = ""; pane.classList?.remove("hidden","is-hidden");
    return pane;
  }

  function renderIntoPane(html) {
    var pane = ensurePane();
    var safe = (html && html.trim()) ? html : "<p><em>No preview HTML returned.</em></p>";
    var h1 = pane.querySelector("h1");       // ✅ preserve your title
    if (h1) {
      while (h1.nextSibling) h1.nextSibling.remove();
      var wrap = document.createElement("div");
      wrap.className = "ppa-preview-body";
      wrap.innerHTML = safe;
      h1.insertAdjacentElement("afterend", wrap);
    } else {
      pane.innerHTML = safe;
    }
  }

  function parseUpstream(text) {
    try {
      var j = JSON.parse(text);
      if (j && typeof j === "object" && "success" in j) return j.success && j.data ? j.data.html || "" : "";
      if (j && typeof j === "object" && j.ok && j.result) return j.result.html || "";
      if (j && typeof j === "object") return j.html || "";
    } catch(_) {}
    return text; // raw HTML
  }

  async function runPreview() {
    var n = (window.PPA && PPA.nonce)
           || document.querySelector("#ppa_preview_nonce")?.value
           || document.querySelector("[name=_wpnonce]")?.value || "";

    var params = new URLSearchParams();
    params.set("action", "ppa_preview");
    params.set("nonce", n);
    params.set("security", n); // cover both nonce param names

    var fields = pickFields();
    Object.entries(fields).forEach(([k, v]) => params.set(`fields[${k}]`, v ?? ""));

    var url = (window.PPA && PPA.ajaxUrl) || window.ajaxurl || "/wp-admin/admin-ajax.php";

    var res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: params
    });
    var text = await res.text();
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${text.slice(0,200)}`);
    renderIntoPane(parseUpstream(text));
  }

  function bindBtn(){
    var btn = document.querySelector("#ppa-preview-btn, [data-ppa-preview-btn]");
    if (!btn) return;
    btn.addEventListener("click", function(ev){
      ev.preventDefault();
      ev.stopImmediatePropagation?.();   // block other conflicting handlers
      runPreview().catch(err => {
        console.error("[PPA] preview error:", err);
        var pane = ensurePane();
        pane.insertAdjacentHTML("beforeend", `<p style="color:#d33">Preview failed: ${String(err.message||err)}</p>`);
      });
    }, true); // capture so we win
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindBtn);
  else bindBtn();
})();
 /* === end PPA inline preview handler === */
/* PPA v5 preview injector (idempotent) */
(function(){
  if (window.__PPA_TAP_V5__) return; window.__PPA_TAP_V5__ = true;

  function ensurePane(){
    var pane = document.querySelector('.ppa-generated-preview')
            || document.querySelector('#ppa-preview-html')
            || document.querySelector('#ppa_preview_html');
    if (!pane) {
      var host = document.querySelector('#wpbody-content') || document.body;
      pane = document.createElement('div');
      pane.className = 'ppa-generated-preview';
      var h1 = document.createElement('h1'); h1.textContent = 'Preview';
      pane.appendChild(h1);
      host.appendChild(pane);
    }
    pane.hidden = false; pane.style.display = ''; if (pane.classList){ pane.classList.remove('hidden','is-hidden'); }
    return pane;
  }
  function renderIntoPane(html){
    var pane = ensurePane();
    var safe = (html && typeof html === 'string' && html.trim()) ? html : "<p><em>No preview HTML returned.</em></p>";
    var h1 = pane.querySelector('h1');
    if (h1) {
      while (h1.nextSibling) h1.nextSibling.remove();
      var wrap = document.createElement('div'); wrap.className = 'ppa-preview-body';
      wrap.innerHTML = safe;
      h1.insertAdjacentElement('afterend', wrap);
    } else {
      pane.innerHTML = safe;
    }
  }
  function parseResp(t){
    try {
      var j = JSON.parse(t);
      if (j && typeof j==='object' && ('success' in j)) return (j.success && j.data) ? (j.data.html || '') : '';
      if (j && typeof j==='object' && j.ok && j.result) return j.result.html || '';
      if (j && typeof j==='object') return j.html || '';
    } catch(_){}
    return t; // treat as raw HTML
  }

  // Tap fetch (admin-ajax)
  if (window.fetch) {
    var _fetch = window.fetch;
    window.fetch = function(input, init){
      var url = (typeof input==='string') ? input : (input && input.url) || '';
      var opt = init || {};
      var method = String(opt.method || 'GET').toUpperCase();
      var body = opt.body;
      var isAjax = /admin-ajax\.php/i.test(url);
      var isPreview = isAjax && method==='POST' && (
        (body instanceof FormData && (body.get('action')||'')==='ppa_preview') ||
        (typeof body==='string' && /(^|&)action=ppa_preview(&|$)/.test(body)) ||
        (body && body.toString===URLSearchParams.prototype.toString && /(^|&)action=ppa_preview(&|$)/.test(body.toString()))
      );
      var p = _fetch.apply(this, arguments);
      if (isPreview) {
        p.then(function(res){ return res.clone().text().then(function(t){
          console.log('[PPA v5][fetch] len=', t.length);
          try { renderIntoPane(parseResp(t)); } catch(e){}
        }); }).catch(function(){});
      }
      return p;
    };
  }

  // Tap XHR (jQuery.ajax path)
  if (window.XMLHttpRequest) {
    var _open = XMLHttpRequest.prototype.open;
    var _send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(m,u){
      this.__ppa_isAjax = /admin-ajax\.php/i.test(String(u||''));
      this.__ppa_m = (m||'GET').toUpperCase();
      return _open.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function(b){
      var isPreview = this.__ppa_isAjax && this.__ppa_m==='POST' && (
        (b instanceof FormData && (b.get('action')||'')==='ppa_preview') ||
        (typeof b==='string' && /(^|&)action=ppa_preview(&|$)/.test(b))
      );
      if (isPreview) this.addEventListener('loadend', function(){
        try {
          var t = (this && (this.responseText||'')) || '';
          console.log('[PPA v5][xhr] len=', t.length);
          renderIntoPane(parseResp(t));
        } catch(_){}
      });
      return _send.apply(this, arguments);
    };
  }
})();
