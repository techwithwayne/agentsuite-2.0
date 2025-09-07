// CHANGED: 2025-09-04 - restore named export `collectFields` for compatibility; also append top-level keys when appending fields[...].
// CHANGE LOG
// 2025-09-04:
//  - RESTORED: export collectFields() so other modules importing it compile.
//  - ADDED: appendFieldsToFormData() writes both fields[<k>] and top-level <k> (and ensures title is set when subject/headline present).
//  - Defensive implementations: collectFields accepts FormData, URLSearchParams, or plain object and returns plain object.

// Helper utilities for dealing with "fields" payload shape used by the admin UI.
// Exports:
// - collectFields(input) -> Object
// - appendFieldsToFormData(fd, fields) -> void

/**
 * Collect fields into a plain object.
 *
 * Accepts:
 *  - FormData: will extract both 'fields[xxx]' entries and top-level keys.
 *  - URLSearchParams: same handling.
 *  - Plain Object: returned as-is (shallow copy).
 *  - null/undefined/other: returns {}.
 *
 * Returned object maps keys -> value (string or array if multiple entries present).
 *
 * NOTE: This is defensive and intentionally conservative to avoid breaking callers.
 *
 * @param {FormData|URLSearchParams|Object|null} input
 * @returns {Object}
 */
export function collectFields(input) {
  if (!input) return {};

  const out = Object.create(null);

  // Helper to push value into out with array coalescing
  function pushKey(k, v) {
    if (out[k] === undefined) {
      out[k] = v;
    } else if (Array.isArray(out[k])) {
      out[k].push(v);
    } else {
      out[k] = [out[k], v];
    }
  }

  // Handle FormData
  try {
    if (typeof FormData !== 'undefined' && input instanceof FormData) {
      for (const pair of input.entries()) {
        const k = pair[0];
        const v = pair[1];
        // special: fields[foo] -> foo
        const m = k.match(/^fields\[(.+)\]$/);
        if (m) {
          pushKey(m[1], String(v));
        } else {
          pushKey(k, String(v));
        }
      }
      return out;
    }
  } catch (e) {
    // fallthrough
  }

  // Handle URLSearchParams
  try {
    if (typeof URLSearchParams !== 'undefined' && input instanceof URLSearchParams) {
      for (const [k, v] of input.entries()) {
        const m = k.match(/^fields\[(.+)\]$/);
        if (m) {
          pushKey(m[1], String(v));
        } else {
          pushKey(k, String(v));
        }
      }
      return out;
    }
  } catch (e) {
    // fallthrough
  }

  // If it's a plain object, shallow copy (if nested arrays/objects, caller must handle)
  if (typeof input === 'object') {
    for (const k of Object.keys(input)) {
      const v = input[k];
      // if value is array, keep it as array of strings
      if (Array.isArray(v)) {
        out[k] = v.map((x) => (x == null ? '' : String(x)));
      } else if (v == null) {
        out[k] = '';
      } else {
        out[k] = String(v);
      }
    }
    return out;
  }

  // Fallback: return empty object
  return {};
}

/**
 * Append an object's fields to a FormData instance.
 *
 * Behavior:
 * - For each key in `fields`, append a `fields[<key>]` entry.
 * - Also append a top-level `<key>` entry (if not already present in the FormData)
 *   so that upstreams expecting top-level keys receive them.
 * - Special-case: when key is 'subject' or 'headline' and 'title' is not present,
 *   also append 'title' with that value.
 *
 * This is best-effort and tolerates environments where FormData.has() may not exist.
 *
 * @param {FormData} fd
 * @param {Object} fields
 */
export function appendFieldsToFormData(fd, fields = {}) {
  if (!fd || typeof fd.append !== 'function') return;

  // First append fields[<key>] entries
  for (const key of Object.keys(fields)) {
    const val = fields[key];

    if (Array.isArray(val)) {
      for (const v of val) {
        fd.append(`fields[${key}]`, v == null ? '' : String(v));
      }
    } else {
      fd.append(`fields[${key}]`, val == null ? '' : String(val));
    }
  }

  // Second pass: append top-level keys if not present
  // Because FormData.has() isn't universal, we enumerate existing keys once
  const existing = new Set();
  try {
    for (const pair of fd.entries()) {
      existing.add(pair[0]);
    }
  } catch (e) {
    // If enumeration fails for any reason, fall back to best-effort appends below
  }

  for (const key of Object.keys(fields)) {
    // skip if top-level already exists
    if (existing.has(key)) continue;

    const val = fields[key];
    if (Array.isArray(val)) {
      for (const v of val) {
        try { fd.append(String(key), v == null ? '' : String(v)); } catch (_) {}
      }
    } else {
      try { fd.append(String(key), val == null ? '' : String(val)); } catch (_) {}
    }
  }

  // Ensure title exists if subject/headline present and title missing
  let hasTitle = existing.has('title');
  if (!hasTitle) {
    // check entries in fields for title presence
    if ('title' in fields && fields.title !== undefined && fields.title !== null && String(fields.title) !== '') {
      try { fd.append('title', String(fields.title)); } catch (_) {}
      hasTitle = true;
    }
  }
  if (!hasTitle) {
    const subjectVal = fields.subject || fields.headline || null;
    if (subjectVal != null && String(subjectVal) !== '') {
      try { fd.append('title', Array.isArray(subjectVal) ? String(subjectVal[0]) : String(subjectVal)); } catch (_) {}
    }
  }
}
