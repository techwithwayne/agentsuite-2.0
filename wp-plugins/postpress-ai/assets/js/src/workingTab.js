/**
 * Branded "Working…" tab
 */
export const BRAND_BG     = '#121212';
export const BRAND_ACCENT = '#ff6c00';

export function writeWorkingHTML(doc, heading, sub) {
  doc.open();
  doc.write(`<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>PostPress AI — ${heading ? String(heading) : 'Working…'}</title>
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
<h1 id="ppa-status">${heading ? String(heading) : 'Working'}<span class="dots"></span></h1>
<p id="ppa-sub">${sub ? String(sub) : 'Please keep this tab open — we will take you to the WordPress editor as soon as your post is ready.'}</p>
<div class="brand">PostPress&nbsp;AI</div>
</div></body></html>`);
  doc.close();
}

export function openWorkingTab() {
  let w = null;
  try { w = window.open('about:blank', '_blank'); if (w && w.document) writeWorkingHTML(w.document, 'Preparing', 'Initializing…'); } catch(_) {}
  return w;
}

export function updateWorkingTab(w, heading, sub) {
  if (!w || w.closed) return;
  try {
    const d = w.document, s = d.getElementById('ppa-status'), p = d.getElementById('ppa-sub');
    if (s && heading) s.textContent = String(heading);
    if (p && sub)     p.textContent = String(sub);
    if (s) { const span = d.createElement('span'); span.className = 'dots'; s.appendChild(span); }
  } catch(_) {}
}
