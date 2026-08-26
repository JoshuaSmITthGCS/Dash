/**
 * Vocabulary substitution — furniture words only, never content words. A medium's manifest
 * declares `vocabulary: { section: 'room', … }` (see DESIGN.md's "Vocabulary map" per theme);
 * this module is the lookup used by `core/screens/*` to render chrome labels.
 *
 * Hard rule (master doc, "Vocabulary changes furniture words only"): a metric's `label`, its
 * `reads` line, and every disclosure are identical in all twelve mediums and NEVER pass through
 * this lookup. `t()` is for section headings, nav labels, and other structural chrome words —
 * never for a value that came out of a data file.
 */

// The canonical (Classic) furniture words every medium's vocabulary map is keyed against.
export const CANONICAL_VOCAB = Object.freeze({
  section: 'section',
  destination: 'destination',
  navigation: 'navigation',
  entry: 'entry',
  settings: 'settings',
  alerts: 'alerts',
  filter: 'filter',
  sort: 'sort',
  search: 'search',
  loading: 'loading',
  empty: 'empty',
  error: 'error',
  unavailable: 'unavailable',
  confirm: 'confirm',
  cancel: 'cancel',
  close: 'close',
})

/** Returns the medium's word for `key`, or the canonical word if the medium doesn't override it. */
export function t(vocabulary, key) {
  return vocabulary?.[key] || CANONICAL_VOCAB[key] || key
}

/** True only for keys the canonical vocabulary itself defines — guards against typoed keys. */
export function isKnownVocabKey(key) {
  return Object.prototype.hasOwnProperty.call(CANONICAL_VOCAB, key)
}
