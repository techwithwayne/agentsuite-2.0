/**
 * Field collection and helpers
 */
import { $, $$ } from './config.js';

export function findFormRoot() {
  return $('#ppa-composer') || $('.ppa-composer') || $('#ppa-composer-form') || document;
}

export function collectFields() {
  const root = findFormRoot();
  const out  = {};
  const set  = (k, v) => {
    if (v == null) return;
    const s = String(v).trim();
    if (s !== '') out[k] = s;
  };

  const idMap = {
    subject: ['#ppa-subject','#ppa_subject','[name="subject"]','[name="ppa_subject"]'],
    genre:   ['#ppa-genre','#ppa_genre','[name="genre"]','[name="ppa_genre"]'],
    tone:    ['#ppa-tone','#ppa_tone','[name="tone"]','[name="ppa_tone"]'],
    title:   ['#ppa-title','[name="title"]','[name="post_title"]','[name="ppa_title"]'],
    keywords:['#ppa-keywords','[name="keywords"]','[name="ppa_keywords"]'],
    audience:['#ppa-audience','[name="audience"]','[name="target_audience"]','[name="ppa_audience"]'],
    length:  ['#ppa-length','[name="length"]','[name="ppa_length"]'],
    cta:     ['#ppa-cta','[name="cta"]','[name="call_to_action"]','[name="ppa_cta"]'],
    summary: ['#ppa-summary','[name="summary"]','[name="ppa_summary"]'],
    description:['#ppa-description','[name="description"]','[name="ppa_description"]'],
    excerpt: ['#ppa-excerpt','[name="excerpt"]','[name="post_excerpt"]','[name="ppa_excerpt"]'],
    slug:    ['#ppa-slug','[name="slug"]','[name="post_name"]','[name="ppa_slug"]'],
    content: ['#ppa-content','[name="content"]','[name="post_content"]','[name="ppa_content"]'],
  };

  for (const [key, sels] of Object.entries(idMap)) {
    for (const sel of sels) {
      const el = $(sel, root);
      if (!el) continue;
      if (key === 'content') {
        try {
          if (window.tinymce && tinymce.get && el.id && tinymce.get(el.id)) {
            const ed = tinymce.get(el.id);
            set('content', ed.getContent({ format: 'html' }));
            break;
          }
        } catch (_) {}
      }
      const val = (el.value != null ? String(el.value) : el.textContent) || '';
      set(key, val);
      break;
    }
  }

  $$('[data-field]', root).forEach(el => {
    const k = String(el.getAttribute('data-field') || '').trim();
    if (!k || out[k]) return;
    const v = (el.value != null ? String(el.value) : el.textContent) || '';
    set(k, v);
  });

  if (out.subject && !out.title)  out.title  = out.subject;
  if (out.title   && !out.subject) out.subject = out.title;
  return out;
}

export function appendFieldsToFormData(fd, fields) {
  if (!fields || typeof fields !== 'object') return;
  Object.keys(fields).forEach(k => {
    const v = fields[k];
    if (v == null) return;
    fd.append(`fields[${k}]`, String(v));
  });
}
