/**
 * AJAX transport to admin-ajax.php
 *
 * 2025-09-04: Robust response parsing — accept JSON or raw HTML for preview endpoint.
 *
 * Behavior:
 *  - Build FormData payload and POST to admin-ajax.php
 *  - Read response as text and try JSON.parse()
 *  - If JSON.parse fails, return a JSON-like object: { status, body: "<raw-html>" }
 *  - Preserve previous error behavior (throw on non-ok), but include parsed body in error text.
 */

import { AJAX_URL, getNonce } from './config.js';
import { appendFieldsToFormData } from './fields.js';

export async function postAjax(action, extra = {}) {
  const nonce = getNonce();
  if (!nonce) throw new Error('Missing nonce');

  const fd = new FormData();
  fd.append('action', action);
  fd.append('nonce', nonce);
  if (extra.mode) fd.append('mode', String(extra.mode));
  appendFieldsToFormData(fd, extra.fields || {});

  const res = await fetch(AJAX_URL, {
    method: 'POST',
    credentials: 'same-origin',
    body: fd,
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  });

  // Read response as text so we can safely handle both JSON and raw HTML
  const text = await res.text().catch(() => '');

  // Try to parse JSON first; if it fails, return a JSON-like object containing the raw text
  let parsed;
  try {
    const trimmed = text.trim();
    if (trimmed === '') {
      parsed = { status: res.status, body: '' };
    } else {
      parsed = JSON.parse(trimmed);
    }
  } catch (err) {
    // Not valid JSON — treat as HTML fallback
    parsed = { status: res.status, body: text };
  }

  // If response is not OK, include parsed payload in the thrown error for easier debugging
  if (!res.ok) {
    const snippet = typeof parsed === 'object' ? JSON.stringify(parsed).slice(0, 280) : String(parsed).slice(0, 280);
    throw new Error(`HTTP ${res.status}: ${snippet}`);
  }

  // Return parsed object (either the parsed JSON or {status, body: "<html>..."})
  return parsed;
}
