/**
 * Preview and Store actions
 */
import { log, warn, AJAX_URL } from './config.js';
import { collectFields } from './fields.js';
import { postAjax } from './ajax.js';
import { renderPreviewHTMLFromJSON } from './preview.js';
import { ensurePreviewLoader, setPreviewLoaderLabel, showPreviewLoader, hidePreviewLoader } from './loader.js';
import { openWorkingTab, updateWorkingTab } from './workingTab.js';

export async function onPreviewClick(ev) {
  ev && ev.preventDefault && ev.preventDefault();
  showPreviewLoader('Generating preview…');
  try {
    const fields = collectFields();
    const json   = await postAjax('ppa_preview', { fields });
    renderPreviewHTMLFromJSON(json);
  } catch (e) {
    warn('Preview error', e);
    setPreviewLoaderLabel('Something went wrong — see console.');
    // graceful message in the pane is done by render or leave as-is
  } finally {
    hidePreviewLoader();
  }
}

export async function onStoreClick(mode, ev) {
  ev && ev.preventDefault && ev.preventDefault();
  let openedTab = openWorkingTab();
  showPreviewLoader('Generating preview…');
  try {
    const fieldsBase = collectFields();
    let fields = Object.assign({}, fieldsBase, { quality: 'final', mode });

    try {
      updateWorkingTab(openedTab, 'Generating preview', 'Asking AI for final content…');
      const previewJson = await postAjax('ppa_preview', { fields });
      renderPreviewHTMLFromJSON(previewJson);
      const rr = (previewJson && previewJson.result) || {};
      fields = Object.assign({}, fields, {
        title:   rr.title   || fields.title   || fieldsBase.title   || fieldsBase.subject || '',
        html:    rr.html    || fields.html    || fieldsBase.html    || '',
        summary: rr.summary || fields.summary || fieldsBase.summary || '',
      });
    } catch (e) {
      log('Final-quality preview failed; continuing to store.', e);
    }

    setPreviewLoaderLabel('Saving draft…');
    updateWorkingTab(openedTab, 'Saving draft', 'Creating your post in WordPress…');
    const json = await postAjax('ppa_store', { mode, fields });

    let editUrl = (json && (json.edit_url || json.edit_url_note)) || '';
    if (!editUrl) {
      try {
        const id = json && json.result && json.result.id;
        const base = (window?.ajaxurl || AJAX_URL || '').replace(/\/admin-ajax\.php$/, '/post.php');
        if (id && base) editUrl = `${base}?post=${encodeURIComponent(id)}&action=edit`;
      } catch (_) {}
    }

    if (editUrl) {
      setPreviewLoaderLabel('Opening editor…');
      updateWorkingTab(openedTab, 'Opening editor', 'Redirecting to the WordPress post editor…');
      try {
        if (openedTab && !openedTab.closed) { openedTab.location.replace(editUrl); openedTab.focus(); }
        else {
          window.open(editUrl, '_blank', 'noopener');
        }
      } catch(_) {
        window.open(editUrl, '_blank', 'noopener');
      }
    } else {
      log('Store completed without edit_url.');
    }
  } catch (e) {
    warn('Store error', e);
    setPreviewLoaderLabel('Something went wrong — see console.');
  } finally {
    hidePreviewLoader();
  }
}
