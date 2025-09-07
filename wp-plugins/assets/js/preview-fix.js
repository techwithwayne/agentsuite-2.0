// File: wp-plugins/postpress-ai/assets/js/preview-fix.js
// Defensive patch: ensure preview POSTs always include subject/title/headline.
// Inserted: 2025-09-04
// This script monkeypatches window.fetch to add title/subject/headline when sending
// POST requests to /wp-admin/admin-ajax.php?action=ppa_preview.
//
// Behavior notes:
// - If the original request body is a FormData or URLSearchParams, we append to it.
// - If the body is a string (x-www-form-urlencoded), we parse and reserialize.
// - If the request already contains 'title' we do nothing.
// - We prefer values found in the DOM (selectors below) falling back to window.PPA.nonce only for nonce (we never write secret keys).
// - Non-destructive: we call the original fetch with modified body only for matching requests.

(function () {
  if (typeof window === 'undefined') return;
  if (!window.fetch) return;

  // Try multiple selectors for the subject field in the admin UI.
  function findSubjectFromDOM() {
    const selectors = [
      '#ppa-subject',
      '[name="subject"]',
      '[name="title"]',
      '#title',               // common WP title
      '.ppa-subject',
      '.ppa-title',
      'input[name="headline"]',
    ];
    for (const sel of selectors) {
      try {
        const el = document.querySelector(sel);
        if (!el) continue;
        // Inputs or textareas
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
          const val = (el.value || '').trim();
          if (val) return val;
        } else {
          const txt = (el.textContent || '').trim();
          if (txt) return txt;
        }
      } catch (err) {
        // continue
      }
    }
    // fallback to window.PPA.title or window.PPA.subject if plugin localizes it
    if (window.PPA && typeof window.PPA === 'object') {
      if (window.PPA.title && window.PPA.title.trim()) return window.PPA.title.trim();
      if (window.PPA.subject && window.PPA.subject.trim()) return window.PPA.subject.trim();
    }
    return '';
  }

  // helper: if URLSearchParams, append key/value
  function appendToURLSearchParams(body, key, value) {
    try {
      if (body instanceof URLSearchParams) {
        if (!body.has(key)) body.append(key, value);
        return body;
      }
    } catch (e) {}
    return null;
  }

  // helper: if FormData, append key/value
  function appendToFormData(body, key, value) {
    try {
      if (body instanceof FormData) {
        if (!body.has(key)) body.append(key, value);
        return body;
      }
    } catch (e) {}
    return null;
  }

  // helper: parse urlencoded string into URLSearchParams and reserialize
  function ensureInUrlEncodedString(bodyStr, key, value) {
    try {
      const params = new URLSearchParams(bodyStr);
      if (!params.has(key)) params.append(key, value);
      return params.toString();
    } catch (e) {
      return bodyStr;
    }
  }

  // main monkeypatch
  const _fetch = window.fetch.bind(window);
  window.fetch = async function (input, init = {}) {
    try {
      // normalize URL & method
      let url = (typeof input === 'string') ? input : (input && input.url ? input.url : '');
      let method = (init && init.method) ? ('' + init.method).toUpperCase() : 'GET';

      // If input is a Request object, extract method/url/body; reconstruct later.
      let originalRequestIsRequestObject = (typeof Request !== 'undefined' && input instanceof Request);

      // Quick check: only treat requests to admin-ajax.php
      if (!url || url.indexOf('/wp-admin/admin-ajax.php') === -1) {
        // pass-through
        return _fetch(input, init);
      }

      // Only intercept POST requests
      if (method !== 'POST') return _fetch(input, init);

      // Determine the action param in body - we need to only modify ppa_preview posts
      // Examine init.body (FormData / URLSearchParams / string)
      let body = init.body;

      // If original input is Request and no init.body, attempt to read from it (can't read body stream safely here) — skip in that case.
      if (!body && originalRequestIsRequestObject) {
        // We won't attempt to read a Request's stream here to avoid breaking; pass through.
        return _fetch(input, init);
      }

      // helper to check if action=ppa_preview exists in the body
      async function bodyHasPpaPreview(b) {
        try {
          if (!b) return false;
          if (b instanceof URLSearchParams) {
            return b.get('action') === 'ppa_preview';
          }
          if (b instanceof FormData) {
            return b.get('action') === 'ppa_preview';
          }
          if (typeof b === 'string') {
            const params = new URLSearchParams(b);
            return params.get('action') === 'ppa_preview';
          }
          // For other types (ArrayBuffer, Blob), we skip
        } catch (e) {}
        return false;
      }

      const isPreview = await bodyHasPpaPreview(body);
      if (!isPreview) {
        // nothing to do
        return _fetch(input, init);
      }

      // Determine subject text from DOM/locals
      const subjectText = findSubjectFromDOM();

      // If subjectText empty, do not modify – still try to ensure 'title' exists if present in body
      // Now ensure body contains title/subject/headline as needed
      let modifiedInit = Object.assign({}, init); // shallow copy

      // Case: FormData
      let fd = appendToFormData(body, 'title', subjectText);
      if (fd) {
        // Append aliases if missing
        if (subjectText) {
          if (!fd.has('subject')) fd.append('subject', subjectText);
          if (!fd.has('headline')) fd.append('headline', subjectText);
        }
        modifiedInit.body = fd;
        return _fetch(input, modifiedInit);
      }

      // Case: URLSearchParams
      let usp = appendToURLSearchParams(body, 'title', subjectText);
      if (usp) {
        if (subjectText) {
          if (!usp.has('subject')) usp.append('subject', subjectText);
          if (!usp.has('headline')) usp.append('headline', subjectText);
        }
        modifiedInit.body = usp;
        return _fetch(input, modifiedInit);
      }

      // Case: string (x-www-form-urlencoded)
      if (typeof body === 'string') {
        let newBody = body;
        try {
          const params = new URLSearchParams(body);
          if (!params.has('title') && subjectText) params.append('title', subjectText);
          if (!params.has('subject') && subjectText) params.append('subject', subjectText);
          if (!params.has('headline') && subjectText) params.append('headline', subjectText);
          newBody = params.toString();
        } catch (e) {
          newBody = ensureInUrlEncodedString(body, 'title', subjectText);
        }
        modifiedInit.body = newBody;
        return _fetch(input, modifiedInit);
      }

      // Other body types: pass through
      return _fetch(input, init);
    } catch (err) {
      // In case of unexpected error, fallback to original fetch to avoid breaking admin UI
      return _fetch(input, init);
    }
  };

  // expose a way to run the subject detection from console if needed
  Object.defineProperty(window, 'PPA_preview_patch_detect_subject', {
    value: findSubjectFromDOM,
    writable: false,
    configurable: false,
  });
})();
