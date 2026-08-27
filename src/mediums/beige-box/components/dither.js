/**
 * 1-bit dither density as the confidence channel (DESIGN.md §10, distinct from state/value
 * encodings). Higher confidence = denser dots = a fill that reads closer to solid; lower
 * confidence = sparser dots. A small precomputed set of spacing buckets, not a continuous CSS
 * value, per the "cheap, interpolated by density" performance plan.
 */
const BUCKETS = [10, 7, 5, 3, 2] // px spacing, sparse -> dense

export function ditherBucket(level = 1) {
  const index = Math.min(BUCKETS.length - 1, Math.max(0, Math.round(level * (BUCKETS.length - 1))))
  return BUCKETS[index]
}

/** A repeating 1px-dot pattern at the given spacing, drawn with hard-edged radial gradients (no blur). */
export function ditherBackground(level, color = 'currentColor') {
  const spacing = ditherBucket(level)
  return {
    backgroundImage: `radial-gradient(circle, ${color} 1px, transparent 1px)`,
    backgroundSize: `${spacing}px ${spacing}px`,
  }
}
