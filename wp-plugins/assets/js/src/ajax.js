/**
 * AJAX transport to admin-ajax.php
 */
import { AJAX_URL, getNonce } from './config.js';
import { appendFieldsToFormData } from './fields.js';

export async function postAjax(action, extra = {}) {
  const nonce = getNonce();
  if (!nonce) throw new Error('Missing nonce');

  const fd = new FormData();
  fd.append('action', action);
  fd.append('nonce',  nonce);
  if (extra.mode) fd.append('mode', String(extra.mode));
  appendFieldsToFormData(fd, extra.fields || {});

  const res = await fetch(AJAX_URL, {
    method: 'POST',
    credentials: 'same-origin',
    body: fd,
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  });

  let json;
  try { json = await res.json(); }
  catch (e) {
    const text = await res.text().catch(() => '');
    throw new Error(`Bad JSON (${res.status}): ${text.slice(0, 280)}`);
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${JSON.stringify(json).slice(0, 280)}`);
  return json;
}
