/**
 * Categorical accents.
 *
 * Seven hues defined in index.css that share one perceived weight, so a set of
 * them reads as a family rather than as a paint box. Use these when things need
 * telling apart — thought kinds, knowledge types, analyst tiers, source types.
 *
 * Not for status. `ok` / `warn` / `risk` are names for three of these same
 * colours and carry meaning; a chip that means "verified" should say `ok`, not
 * `green`. Reach for an accent only when the distinction is categorical.
 *
 * Tailwind scans source for complete class strings, so the pairs below are
 * written out rather than built as `bg-${name}/15`. A template literal would
 * compile but emit no CSS.
 */
export type Accent =
  | 'rose'
  | 'clay'
  | 'amber'
  | 'green'
  | 'teal'
  | 'blue'
  | 'violet'

/** Ordered for maximum separation between neighbours, so a set drawn in
 *  sequence never puts two near hues side by side. */
export const ACCENT_ORDER: Accent[] = [
  'blue',
  'amber',
  'teal',
  'rose',
  'green',
  'violet',
  'clay',
]

/** Tinted pill + matching ink. The pairing that clears 4.5:1. */
export const ACCENT_CHIP: Record<Accent, string> = {
  rose: 'bg-rose/15 text-rose-deep',
  clay: 'bg-clay/15 text-clay-deep',
  amber: 'bg-amber/15 text-amber-deep',
  green: 'bg-green/15 text-green-deep',
  teal: 'bg-teal/15 text-teal-deep',
  blue: 'bg-blue/15 text-blue-deep',
  violet: 'bg-violet/15 text-violet-deep',
}

/** Solid fill, for dots, bars and legend swatches. */
export const ACCENT_FILL: Record<Accent, string> = {
  rose: 'bg-rose',
  clay: 'bg-clay',
  amber: 'bg-amber',
  green: 'bg-green',
  teal: 'bg-teal',
  blue: 'bg-blue',
  violet: 'bg-violet',
}

/** Ink only, for icons and standalone labels. */
export const ACCENT_TEXT: Record<Accent, string> = {
  rose: 'text-rose-deep',
  clay: 'text-clay-deep',
  amber: 'text-amber-deep',
  green: 'text-green-deep',
  teal: 'text-teal-deep',
  blue: 'text-blue-deep',
  violet: 'text-violet-deep',
}

/** Analyst tiers. Shared so the roster grid and the profile page agree. */
export const LEVEL_ACCENT: Record<'L1' | 'L2' | 'L3', Accent> = {
  L1: 'teal',
  L2: 'violet',
  L3: 'amber',
}

/** Stable accent for an arbitrary key, so the same label keeps its colour
 *  across renders and across pages. */
export function accentFor(key: string): Accent {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0
  return ACCENT_ORDER[Math.abs(h) % ACCENT_ORDER.length]
}
