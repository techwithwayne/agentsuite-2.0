/**
 * Config, globals, small helpers
 */
export const CFG      = (window.PPA || {});
export const AJAX_URL = CFG.ajax_url || CFG.ajaxUrl || (typeof ajaxurl !== 'undefined' ? ajaxurl : '/wp-admin/admin-ajax.php');
export const NONCE    = CFG.nonce || '';
export const DEBUG    = !!CFG.debug;

export const $  = (sel, root) => (root || document).querySelector(sel);
export const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

export function log(...args)  { if (DEBUG && window.console) console.log('[PPA]', ...args); }
export function warn(...args) { if (window.console) console.warn('[PPA]', ...args); }

export function getNonce() {
  if (NONCE) return NONCE;
  const dom = $('#ppa-nonce');
  return dom ? String(dom.value || '') : '';
}

/**
 * Resolve a plugin-relative asset URL (works even if script is concatenated/moved).
 */
export function resolveAssetUrl(rel) {
  const r = String(rel || '').replace(/^\/+/, '');
  if (CFG.assets_url) return CFG.assets_url.replace(/\/+$/, '/') + r;
  if (CFG.pluginUrl)  return CFG.pluginUrl.replace(/\/+$/, '/')  + r;
  if (CFG.plugin_url) return CFG.plugin_url.replace(/\/+$/, '/') + r;

  const PLUGIN_SEG = '/wp-content/plugins/postpress-ai/';
  try {
    const cs = document.currentScript && document.currentScript.src;
    if (cs && cs.includes(PLUGIN_SEG)) {
      const u = new URL(cs, window.location.origin);
      const base = u.origin + u.pathname.slice(0, u.pathname.indexOf(PLUGIN_SEG) + PLUGIN_SEG.length);
      return base.replace(/\/+$/, '/') + r;
    }
  } catch (_) {}
  try {
    const scripts = document.getElementsByTagName('script');
    for (let i = scripts.length - 1; i >= 0; i--) {
      const src = scripts[i].src || '';
      if (!src) continue;
      if (src.includes(PLUGIN_SEG)) {
        const u = new URL(src, window.location.origin);
        const base = u.origin + u.pathname.slice(0, u.pathname.indexOf(PLUGIN_SEG) + PLUGIN_SEG.length);
        return base.replace(/\/+$/, '/') + r;
      }
    }
  } catch (_) {}
  try {
    return window.location.origin.replace(/\/+$/, '') + PLUGIN_SEG + r;
  } catch (_) {
    return PLUGIN_SEG + r;
  }
}
