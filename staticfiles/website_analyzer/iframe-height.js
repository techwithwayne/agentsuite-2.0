// static/website_analyzer/iframe-height.js
// Website Analyzer Iframe Height Manager
// Measures full document height, posts to parent, and announces "widget-ready".

(function () {
  'use strict';

  // Keep MIN small; DO NOT clamp with a tiny MAX here.
  const MIN = 420;       // small floor so empty states aren't microscopic
  const BUFFER = 24;     // a little breathing room to avoid constant reflows
  const CHANGE_PX = 6;   // only post if the delta is meaningful
  const POST_ORIGIN = "*"; // parent should validate origin on its side

  let last = 0;
  let ro = null;
  let mo = null;
  let t = null;

  function docHeight() {
    const b = document.body;
    const d = document.documentElement;
    // take the biggest value we can find
    const h = Math.max(
      b.scrollHeight, d.scrollHeight,
      b.offsetHeight, d.offsetHeight,
      b.clientHeight, d.clientHeight
    );
    return Math.max(MIN, h + BUFFER);
  }

  function post(h) {
    try {
      window.parent.postMessage({ type: 'iframeResize', height: h, ts: Date.now() }, POST_ORIGIN);
    } catch (_) { /* ignore */ }
  }

  function measureAndPost() {
    const h = docHeight();
    if (Math.abs(h - last) >= CHANGE_PX) {
      last = h;
      post(h);
    }
  }

  function schedule() {
    if (t) cancelAnimationFrame(t);
    t = requestAnimationFrame(measureAndPost);
  }

  function observe() {
    if (window.ResizeObserver) {
      ro = new ResizeObserver(schedule);
      ro.observe(document.body);
    }
    mo = new MutationObserver(schedule);
    mo.observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: true });
  }

  // ---- boot ----
  // Let parent know we're alive, then start watching and send an initial size
  try { window.parent.postMessage({ type: 'widget-ready', ts: Date.now() }, POST_ORIGIN); } catch (_) {}
  observe();
  // initial nudge after layout settles
  setTimeout(measureAndPost, 200);
  window.addEventListener('load', () => setTimeout(measureAndPost, 200));
  window.addEventListener('resize', schedule);

  // Manual hook for debugging
  window.waChild = { force: () => { last = 0; measureAndPost(); } };
})();
