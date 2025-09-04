/**
 * Preview pane helpers and rendering
 */
import { $, warn } from './config.js';

export function findPreviewPane() {
  const cands = ['#ppa-preview-window', '#ppa-preview-pane', '.ppa-preview-pane', '#ppa-preview', '.ppa-preview'];
  for (const sel of cands) { const el = $(sel); if (el) return el; }
  return null;
}

export function extractPreviewHTML(json) {
  if (!json) return '';
  if (typeof json === 'string') return json;
  const g = (obj, path) => {
    try { return path.split('.').reduce((a, k) => (a && a[k] != null ? a[k] : undefined), obj); }
    catch (_) { return undefined; }
  };
  const candidates = [
    'result.html','result.content','result.body',
    'data.html','html','wp_body','body',
    'payload.output.html','output.html','content.rendered','rendered','markup','preview_html'
  ];
  for (const p of candidates) {
    const v = g(json, p);
    if (typeof v === 'string' && v.trim()) return v;
  }
  if (json.result && typeof json.result === 'object') {
    for (const v of Object.values(json.result)) {
      if (typeof v === 'string' && /<\/(p|div|h\d|article|section)>/i.test(v)) return v;
    }
  }
  const msg = g(json, 'message') || g(json, 'error') || g(json, 'result.message');
  if (typeof msg === 'string' && msg.trim()) return `<p><em>${msg}</em></p>`;
  return '';
}

export function renderPreviewHTMLFromJSON(json) {
  const pane = findPreviewPane();
  if (!pane) { warn('Preview pane not found'); return; }
  const html = extractPreviewHTML(json);
  pane.innerHTML = html && html.trim() ? html : '<p><em>No preview HTML returned.</em></p>';
}
