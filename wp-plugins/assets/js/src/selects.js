/**
 * Auto-wrap <select> elements (for Rodeo arrow CSS)
 */
import { $$ } from './config.js';

export function wrapSelects() {
  $$('.ppa-form select').forEach(sel => {
    if (!sel.parentElement.classList.contains('ppa-select-wrap')) {
      const wrap = document.createElement('div');
      wrap.className = 'ppa-select-wrap';
      sel.parentNode.insertBefore(wrap, sel);
      wrap.appendChild(sel);
    }
  });
}
