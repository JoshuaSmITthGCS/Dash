/**
 * Deterministic seeding for every medium's material randomness — rough.js roughness/bowing,
 * Poster's registration offset, Chalkboard's erasure-smudge geometry, Beige Box's dither
 * phase, Gallery's bristle displacement. All of it must be a pure function of the metric id,
 * so a screenshot of the same metric never churns between runs (Phase 3 baseline stability)
 * and two viewers never see different sketchy geometry for the same row.
 *
 * `Math.random()` is banned anywhere under src/mediums/** — every source of "organic" variation
 * in a renderer must go through `seedFor()` below.
 */

// FNV-1a, 32-bit. Small, fast, good-enough distribution for a handful of derived doubles per
// chart — this is decorative jitter, not a security or statistics primitive.
function fnv1a(str) {
  let hash = 0x811c9dc5
  for (let i = 0; i < str.length; i += 1) {
    hash ^= str.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return hash >>> 0
}

// mulberry32 — a tiny, fast PRNG with a 32-bit state, seeded from the FNV hash above.
function mulberry32(seed) {
  let state = seed >>> 0
  return function next() {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/**
 * Returns a seeded PRNG function (`() => number` in [0, 1)) for the given id — a metric id,
 * capability id, or any other stable string key. Same id, same sequence, every render, every
 * machine, forever.
 */
export function seedFor(id) {
  const key = String(id ?? 'unseeded')
  return mulberry32(fnv1a(key))
}

/** Convenience: one deterministic float in [min, max) for `id`, without exposing the RNG. */
export function seededRange(id, min, max, salt = '') {
  const rng = seedFor(salt ? `${id}:${salt}` : id)
  return min + rng() * (max - min)
}

/** Convenience: one deterministic integer in [min, max] inclusive. */
export function seededInt(id, min, max, salt = '') {
  return Math.floor(seededRange(id, min, max + 1, salt))
}
