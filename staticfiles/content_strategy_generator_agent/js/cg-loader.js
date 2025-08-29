// Content Strategy Loader (like WA): shows overlay on submit; hides on results or error.
(function () {
  'use strict';

  const CFG = {
    appSelector:   '#cg-app, main, body',
    formSelector:  'form',                         // your page has a single form
    resultsSel:    '#result, .cg-results, [data-cg-results]',
    minShowMs:     800,
    maxWaitMs:     45000,
    ariaLive:      true
  };

  let overlay, live, startedAt = 0, hideTimer = null, maxTimer = null, formEl, resultsEl, submitBtn;

  function $(root, sel){ return (root || document).querySelector(sel); }

  function buildOverlay(){
    overlay = document.createElement('div');
    overlay.className = 'cg-busy';
    overlay.setAttribute('role','dialog');
    overlay.setAttribute('aria-modal','true');
    overlay.innerHTML = `
      <div class="cg-busy-card">
        <h2 class="cg-busy-title">Generating your content strategy…</h2>
        <p class="cg-busy-subtle">We’re compiling topics, keywords, and outlines. Hang tight.</p>
        <div class="cg-progress" aria-hidden="true"></div>
      </div>
      <span class="cg-sr" id="cg-live"></span>
    `;
    document.body.appendChild(overlay);
    live = overlay.querySelector('#cg-live');
  }

  function announce(msg){
    if (!CFG.ariaLive || !live) return;
    live.textContent = '';
    setTimeout(()=>{ live.textContent = msg; }, 30);
  }

  function disableSubmit(disabled){
    if (!submitBtn) submitBtn = document.querySelector('[type="submit"]');
    if (!submitBtn) return;
    submitBtn.disabled = !!disabled;
    submitBtn.setAttribute('aria-busy', disabled ? 'true' : 'false');
  }

  function show(){
    startedAt = Date.now();
    overlay.classList.add('active');
    disableSubmit(true);
    announce('Strategy generation started. Please wait.');
    if (maxTimer) clearTimeout(maxTimer);
    maxTimer = setTimeout(hide, CFG.maxWaitMs);
    window.dispatchEvent(new CustomEvent('cg:busy'));
  }

  function hide(){
    const elapsed = Date.now() - startedAt;
    const wait = Math.max(0, CFG.minShowMs - elapsed);
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(()=>{
      overlay.classList.remove('active');
      disableSubmit(false);
      announce('Strategy generation finished.');
      if (maxTimer) clearTimeout(maxTimer);
      window.dispatchEvent(new CustomEvent('cg:idle'));
    }, wait);
  }

  function attachMutationObserver(){
    resultsEl = $(document, CFG.resultsSel);
    if (!resultsEl || !window.MutationObserver) return;
    let baseline = resultsEl.textContent.length;
    const mo = new MutationObserver(()=>{
      const now = resultsEl.textContent.length;
      if (now > baseline + 20) hide();
    });
    mo.observe(resultsEl, { childList:true, subtree:true, characterData:true });
  }

  function bind(){
    const app = $(document, CFG.appSelector) || document.body;
    formEl = $(app, CFG.formSelector) || $('body', CFG.formSelector);
    if (!formEl){ console.warn('[CG Loader] No form found.'); return; }

    // Universal: show on submit, regardless of AJAX or full POST.
    formEl.addEventListener('submit', ()=> show(), { capture:true });

    // Optional hooks from your AJAX code:
    window.addEventListener('cg:job:done', hide);
    window.addEventListener('cg:job:error', hide);

    attachMutationObserver();
  }

  function init(){
    buildOverlay();
    bind();
    window.addEventListener('pageshow', ()=> {
      const r = $(document, CFG.resultsSel);
      if (r && r.textContent.trim().length > 0) overlay.classList.remove('active');
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  window.CG_Loader = { show, hide }; // optional manual API
})();
