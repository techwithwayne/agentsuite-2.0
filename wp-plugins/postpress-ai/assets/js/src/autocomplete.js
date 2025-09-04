/**
 * Autocomplete: data load + debounce + keyboard nav + ARIA + Tab accept
 */
import { resolveAssetUrl, warn } from './config.js';

const AC_TARGET_IDS = ['ppa-tone','ppa-audience','ppa-keywords'];
const DEBOUNCE_MS   = 180;

let AUTOCOMPLETE_DATA = null;
const DEFAULT_AUTOCOMPLETE = {
  tone: [
    'Friendly','Professional','Persuasive','Technical','Casual','Storytelling','Inspirational',
    'Luxury','Minimalist','Playful','Serious','Conversational','Educational','Authoritative'
  ],
  audience: [
    'Small Business Owners','Entrepreneurs','Students','Iowa Residents','Marketers','Developers',
    'Designers','Executives','Local Community','Ecommerce Owners','Parents','Nonprofits'
  ],
  keywords: [
    'WordPress','SEO','Content Marketing','AI','Iowa Web Design','Small Business Growth',
    'Luxury Branding','Website Redesign','Conversion Optimization','Social Media Strategy',
    'Email Marketing','Page Speed'
  ]
};

async function loadAutocompleteData() {
  if (AUTOCOMPLETE_DATA) return AUTOCOMPLETE_DATA;
  try {
    const url = resolveAssetUrl('assets/data/autocomplete.json');
    const res = await fetch(url, { credentials: 'same-origin' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    AUTOCOMPLETE_DATA = await res.json();
    if (!AUTOCOMPLETE_DATA || typeof AUTOCOMPLETE_DATA !== 'object') {
      throw new Error('Bad JSON payload');
    }
  } catch (e) {
    warn('Autocomplete data load failed, using defaults.', e);
    AUTOCOMPLETE_DATA = DEFAULT_AUTOCOMPLETE;
  }
  return AUTOCOMPLETE_DATA;
}

// DOM helpers
function acGetList(input) {
  const sib = input && input.nextElementSibling;
  if (sib && sib.classList && sib.classList.contains('ppa-autocomplete-list')) return sib;
  if (input && input.parentElement) return input.parentElement.querySelector('.ppa-autocomplete-list');
  return null;
}
function acGetItems(list) {
  return Array.from(list ? list.querySelectorAll('li') : []);
}

// ARIA utilities
function acEnsureARIA(input) {
  if (!input) return;
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-haspopup', 'listbox');
  if (!input.hasAttribute('aria-expanded')) input.setAttribute('aria-expanded', 'false');
}
function acWireListARIA(input, list) {
  if (!input) return;
  if (!list) {
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    input.removeAttribute('aria-controls');
    return;
  }
  if (!list.id) list.id = 'ppa-ac-' + (input.id || Math.random().toString(36).slice(2));
  input.setAttribute('aria-controls', list.id);
  input.setAttribute('aria-expanded', 'true');

  const items = acGetItems(list);
  items.forEach((li, i) => {
    if (!li.id) li.id = `${list.id}-opt-${i}`;
    if (li.getAttribute('aria-selected') === 'true') {
      input.setAttribute('aria-activedescendant', li.id);
    }
  });
  if (!input.getAttribute('aria-activedescendant') && items[0]) {
    input.setAttribute('aria-activedescendant', items[0].id);
  }
}
function acSyncAriaActiveFromHighlight(input) {
  const list = acGetList(input); if (!list) return;
  const active = list.querySelector('li[aria-selected="true"]');
  if (active && active.id) input.setAttribute('aria-activedescendant', active.id);
}

// Highlight management
function acSetActiveIndex(input, idx) {
  const list = acGetList(input);
  if (!list) return -1;
  const items = acGetItems(list);
  items.forEach((li, i) => {
    if (i === idx) {
      li.setAttribute('aria-selected', 'true');
      try { li.scrollIntoView({ block: 'nearest' }); } catch (_) {}
    } else {
      li.removeAttribute('aria-selected');
    }
  });
  input.setAttribute('data-ppa-ac-index', String(idx));
  acSyncAriaActiveFromHighlight(input);
  return idx;
}
function acEnsureFirstActive(input) {
  const list = acGetList(input);
  if (!list) return;
  const already = list.querySelector('[aria-selected="true"]');
  const idxAttr = parseInt(input.getAttribute('data-ppa-ac-index') || '-1', 10);
  if (!already && (isNaN(idxAttr) || idxAttr < 0)) {
    const items = acGetItems(list);
    if (items.length) acSetActiveIndex(input, 0);
  }
}
function acMove(input, dir) {
  const list = acGetList(input); if (!list) return;
  const items = acGetItems(list); if (!items.length) return;
  let idx = parseInt(input.getAttribute('data-ppa-ac-index') || '-1', 10);
  if (isNaN(idx)) idx = -1;
  idx += dir;
  if (idx < 0) idx = items.length - 1;
  if (idx >= items.length) idx = 0;
  acSetActiveIndex(input, idx);
}
function acAcceptHighlighted(input) {
  const list = acGetList(input); if (!list) return false;
  const li = list.querySelector('li[aria-selected="true"]') || list.querySelector('li');
  if (!li) return false;
  input.value = (li.textContent || '').trim();
  try { list.remove(); } catch(_) {}
  input.setAttribute('aria-expanded', 'false');
  input.removeAttribute('aria-activedescendant');
  try { input.dispatchEvent(new Event('change', { bubbles: true })); } catch (_) {}
  input.removeAttribute('data-ppa-ac-index');
  return true;
}
function acClose(input) {
  const list = acGetList(input);
  if (list && list.parentNode) list.parentNode.removeChild(list);
  input.removeAttribute('data-ppa-ac-index');
  input.setAttribute('aria-expanded', 'false');
  input.removeAttribute('aria-activedescendant');
}

// Data/UI build
function acHideAllLists() {
  document.querySelectorAll('.ppa-autocomplete-list').forEach(el => el.remove());
}
function acShowListFor(input, fieldType) {
  acHideAllLists();
  if (!AUTOCOMPLETE_DATA || !AUTOCOMPLETE_DATA[fieldType]) return;
  const val = String(input.value || '').trim().toLowerCase();
  if (!val) return;

  const matches = AUTOCOMPLETE_DATA[fieldType]
    .filter(opt => opt.toLowerCase().includes(val))
    .slice(0, 8);
  if (!matches.length) return;

  const ul = document.createElement('ul');
  ul.className = 'ppa-autocomplete-list';
  ul.setAttribute('role', 'listbox');

  matches.forEach(opt => {
    const li = document.createElement('li');
    li.textContent = opt;
    li.setAttribute('role', 'option');
    li.addEventListener('mousedown', e => {
      e.preventDefault();
      input.value = opt;
      acClose(input);
    });
    ul.appendChild(li);
  });

  input.insertAdjacentElement('afterend', ul);
  acEnsureFirstActive(input);
  acWireListARIA(input, ul);
}

// Debounce typing to avoid flicker
function acIsTypingKey(k) {
  return !(k === 'ArrowDown' || k === 'ArrowUp' || k === 'Enter' || k === 'Escape' || k === 'Tab' || k === 'Debounced');
}
function acDispatchDebouncedKeyup(input) {
  try {
    const ev = new KeyboardEvent('keyup', { key: 'Debounced', bubbles: true, cancelable: true });
    input.dispatchEvent(ev);
  } catch (_) {
    const ev2 = document.createEvent('Event');
    ev2.initEvent('keyup', true, true);
    ev2.key = 'Debounced';
    input.dispatchEvent(ev2);
  }
}

export function bindAutocomplete() {
  AC_TARGET_IDS.forEach(id => {
    const input = document.getElementById(id);
    if (!input) return;

    input.setAttribute('autocomplete', 'off');
    acEnsureARIA(input);
    input._ppaDebTimer = null;

    // KEYDOWN: navigation + accept/close
    input.addEventListener('keydown', (ev) => {
      const k = ev.key;
      if (k === 'ArrowDown') { ev.preventDefault(); acMove(input, +1); }
      else if (k === 'ArrowUp') { ev.preventDefault(); acMove(input, -1); }
      else if (k === 'Enter') {
        const accepted = acAcceptHighlighted(input);
        if (accepted) { ev.preventDefault(); ev.stopPropagation(); }
      }
      else if (k === 'Tab') {
        const list = acGetList(input);
        if (list && acAcceptHighlighted(input)) { ev.preventDefault(); ev.stopPropagation(); }
      }
      else if (k === 'Escape') { acClose(input); }
    });

    // KEYUP (capture): smooth debounce for typing keys
    input.addEventListener('keyup', (ev) => {
      const k = ev.key;
      if (!acIsTypingKey(k)) return;     // arrows/enter/esc/tab pass through
      ev.stopPropagation();              // prevent immediate rebuilds upstream
      if (input._ppaDebTimer) { clearTimeout(input._ppaDebTimer); input._ppaDebTimer = null; }
      const sib = input.nextElementSibling;
      if (sib && sib.classList && sib.classList.contains('ppa-autocomplete-list')) {
        try { sib.remove(); } catch(_) {}
      }
      input._ppaDebTimer = setTimeout(() => {
        input._ppaDebTimer = null;
        acDispatchDebouncedKeyup(input);
      }, DEBOUNCE_MS);
    }, true); // capture

    // KEYUP (bubble): actual render on our synthetic 'Debounced'
    input.addEventListener('keyup', async (ev) => {
      const k = ev.key;
      if (k === 'Escape') { acClose(input); return; }
      if (acIsTypingKey(k) && k !== 'Debounced') return; // wait for the debounced event
      await loadAutocompleteData();
      acShowListFor(input, id.replace('ppa-',''));
    });

    input.addEventListener('input', () => {
      input.setAttribute('data-ppa-ac-index', '-1');
    });

    input.addEventListener('blur', () => setTimeout(() => acClose(input), 120));
    input.addEventListener('focus', () => setTimeout(() => acEnsureFirstActive(input), 0));
  });

  // Optional: keep ARIA in sync when lists appear via MutationObserver
  try {
    const mo = new MutationObserver((muts) => {
      muts.forEach((m) => {
        Array.prototype.forEach.call(m.addedNodes || [], (node) => {
          if (!(node instanceof HTMLElement)) return;
          if (node.classList && node.classList.contains('ppa-autocomplete-list')) {
            const input = node.previousElementSibling && node.previousElementSibling.tagName === 'INPUT'
              ? node.previousElementSibling
              : node.parentElement && node.parentElement.querySelector('input');
            if (input) { acEnsureARIA(input); acWireListARIA(input, node); acSyncAriaActiveFromHighlight(input); }
          }
        });
      });
    });
    mo.observe(document.body, { childList: true, subtree: true });
  } catch (_) {}
}
