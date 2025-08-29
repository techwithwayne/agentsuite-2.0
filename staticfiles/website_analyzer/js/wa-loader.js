// Website Analyzer Loader Controller
// - Shows a sleek overlay on "Scan Website" submit
// - Auto-hides when results land or on error
// - No inline JS required: auto-inits with sensible defaults
// - Emits CustomEvents: 'wa:busy' and 'wa:idle'

(function () {
  'use strict';

  const CFG = {
    // Try to auto-detect, but you can override via data attributes on <form>
    appSelector:   '#wa-app, main, body',
    formSelector:  'form#wa-form, form[data-wa-form], form.wa-form, form',
    urlSelector:   'input#wa-url, input[name="url"], input[type="url"]',
    submitSelector:'[type="submit"], button.wa-submit',
    resultsSelector: '#wa-results, [data-wa-results], .wa-results',
    minShowMs: 800,          // keep it visible at least this long (feels responsive)
    maxWaitMs: 45000,        // hard fail-safe
    ariaLive: true           // announce start/end for screen readers
  };

  let overlay, live, startedAt = 0, hideTimer = null, maxTimer = null, formEl, submitBtn, urlInput, resultsEl;

  function $(root, sel) { return (root || document).querySelector(sel); }

  function buildOverlay() {
    overlay = document.createElement('div');
    overlay.className = 'wa-busy';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.innerHTML = `
      <div class="wa-busy-card">
        <h2 class="wa-busy-title">Scanning your site…</h2>
        <p class="wa-busy-subtle">We’re analyzing structure, meta tags, and accessibility. Hang tight.</p>
        <div class="wa-progress" aria-hidden="true"></div>
      </div>
      <span class="wa-sr" id="wa-live"></span>
    `;
    document.body.appendChild(overlay);
    live = overlay.querySelector('#wa-live');
  }

  function announce(msg) {
    if (!CFG.ariaLive || !live) return;
    live.textContent = ''; // force re-announce
    // small delay so screen readers pick it up
    setTimeout(() => { live.textContent = msg; }, 30);
  }

  function domainFromInput() {
    try {
      const v = (urlInput && urlInput.value || '').trim();
      if (!v) return '';
      const u = new URL(v.startsWith('http') ? v : `https://${v}`);
      return u.hostname.replace(/^www\./, '');
    } catch (_) { return ''; }
  }

  function disableSubmit(disabled) {
    if (!submitBtn) return;
    submitBtn.disabled = !!disabled;
    submitBtn.setAttribute('aria-busy', disabled ? 'true' : 'false');
  }

  function show() {
    startedAt = Date.now();
    overlay.classList.add('active');
    disableSubmit(true);

    const d = domainFromInput();
    const title = overlay.querySelector('.wa-busy-title');
    if (d) title.textContent = `Scanning ${d}…`;

    announce('Scanning started. Please wait.');

    // fail-safe to auto-hide if something goes sideways
    if (maxTimer) clearTimeout(maxTimer);
    maxTimer = setTimeout(hide, CFG.maxWaitMs);

    window.dispatchEvent(new CustomEvent('wa:busy'));
  }

  function hide() {
    const elapsed = Date.now() - startedAt;
    const wait = Math.max(0, CFG.minShowMs - elapsed);

    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      overlay.classList.remove('active');
      disableSubmit(false);
      announce('Scan finished.');
      if (maxTimer) clearTimeout(maxTimer);
      window.dispatchEvent(new CustomEvent('wa:idle'));
    }, wait);
  }

  function attachMutationObserver() {
    resultsEl = $(document, CFG.resultsSelector);
    if (!resultsEl || !window.MutationObserver) return;

    let baseline = resultsEl.textContent.length;
    const mo = new MutationObserver(() => {
      const now = resultsEl.textContent.length;
      if (now > baseline + 20) { // content expanded meaningfully
        hide();
      }
    });
    mo.observe(resultsEl, { childList: true, subtree: true, characterData: true });
  }

  function bind() {
    const app = $(document, CFG.appSelector) || document.body;
    formEl = $(app, CFG.formSelector) || $('body', CFG.formSelector);
    if (!formEl) {
      console.warn('[WA Loader] No form found. Auto-init skipped.');
      return;
    }
    urlInput = $(formEl, CFG.urlSelector);
    submitBtn = $(formEl, CFG.submitSelector);

    // If your app uses fetch/AJAX, this still shows immediately on submit.
    formEl.addEventListener('submit', () => show(), { capture: true });

    // Optional: if your existing code fires custom events, we’ll listen too
    window.addEventListener('wa:job:done', hide);
    window.addEventListener('wa:job:error', hide);

    attachMutationObserver();
  }

  function init() {
    buildOverlay();
    bind();

    // In case results render after load without a submit (e.g., back/forward cache)
    window.addEventListener('pageshow', () => {
      if (resultsEl && resultsEl.textContent.trim().length > 0) {
        overlay.classList.remove('active');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Public API (optional)
  window.WA_Loader = { show, hide };
})();
