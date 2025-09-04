/**
 * Loader overlay in the preview pane
 */
import { findPreviewPane } from './preview.js';

export function ensurePreviewLoader() {
  const pane = findPreviewPane();
  if (!pane) return null;
  let overlay = pane.querySelector('.ppa-preloader');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.className = 'ppa-preloader';
    overlay.setAttribute('aria-hidden', 'true');
    const spinner = document.createElement('div');
    spinner.className = 'ppa-lds-spinner';
    for (let i = 0; i < 12; i++) spinner.appendChild(document.createElement('div'));
    const label = document.createElement('div');
    label.className = 'ppa-preloader-label';
    label.textContent = 'Generating preview…';
    overlay.appendChild(spinner);
    overlay.appendChild(label);
    pane.appendChild(overlay);
  }
  return overlay;
}

export function setPreviewLoaderLabel(text) {
  const pane = findPreviewPane();
  if (!pane) return;
  const overlay = ensurePreviewLoader();
  if (!overlay) return;
  let label = overlay.querySelector('.ppa-preloader-label');
  if (!label) {
    label = document.createElement('div');
    label.className = 'ppa-preloader-label';
    overlay.appendChild(label);
  }
  label.textContent = String(text || '').trim() || 'Working…';
}

export function showPreviewLoader(labelText) {
  const pane = findPreviewPane(); if (!pane) return;
  ensurePreviewLoader();
  if (labelText) setPreviewLoaderLabel(labelText);
  pane.classList.add('ppa-is-loading');
  pane.setAttribute('aria-busy', 'true');
}

export function hidePreviewLoader() {
  const pane = findPreviewPane(); if (!pane) return;
  pane.classList.remove('ppa-is-loading');
  pane.removeAttribute('aria-busy');
}
