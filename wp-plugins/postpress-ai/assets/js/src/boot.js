/**
 * Boot wiring for admin Composer
 */
import { $, getNonce, warn } from './config.js';
import { onPreviewClick, onStoreClick } from './actions.js';
import { bindAutocomplete } from './autocomplete.js';
import { wrapSelects } from './selects.js';

export function findButton(role) {
  const byData = $(`[data-ppa-action="${role}"]`);
  if (byData) return byData;
  const map = {
    preview: ['#ppa-preview-btn', '#ppa-btn-preview'],
    draft:   ['#ppa-save-btn',     '#ppa-btn-draft'],
    publish: ['#ppa-publish-btn',  '#ppa-btn-publish'],
  };
  for (const sel of (map[role] || [])) { const el = $(sel); if (el) return el; }
  return null;
}

export function boot() {
  if (!getNonce()) { warn('PPA nonce missing; admin-ajax calls may fail.'); }

  const btnPreview = findButton('preview');
  const btnDraft   = findButton('draft');
  const btnPublish = findButton('publish');

  if (btnPreview) btnPreview.addEventListener('click', onPreviewClick, false);
  if (btnDraft)   btnDraft.addEventListener('click', onStoreClick.bind(null, 'draft'), false);
  if (btnPublish) btnPublish.addEventListener('click', onStoreClick.bind(null, 'publish'), false);

  bindAutocomplete();
  wrapSelects();
}
