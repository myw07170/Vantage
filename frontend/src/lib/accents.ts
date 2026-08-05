/**
 * Categorical accents — the blue-to-pink arc.
 *
 * Six hues defined in index.css, ~28deg apart, running blue -> indigo ->
 * violet -> orchid -> pink -> rose. They share one perceived weight, so a set
 * of them reads as a family rather than as a paint box, and because they all
 * live on one arc the page reads as two colours rather than seven.
 *
 * Use these when things need telling apart — thought kinds, knowledge types,
 * analyst tiers, source types.
 *
 * Not for status. `ok` and `warn` sit deliberately off the arc and carry
 * meaning; a chip that means "verified" should say `ok`. `risk` is this arc's
 * `rose` under a name that says what it is.
 *
 * Tailwind scans source for complete class strings, so the pairs below are
 * written out rather than built as `bg-${name}-tint`. A template literal would
 * compile but emit no CSS.
 */
export type Accent = 'blue' | 'indigo' | 'violet' | 'orchid' | 'pink' | 'rose'

/** Ordered for maximum separation between neighbours, so a set drawn in
 *  sequence never puts two adjacent hues side by side. */
export const ACCENT_ORDER: Accent[] = [
  'blue',
  'pink',
  'violet',
  'rose',
  'indigo',
  'orchid',
]

/** Tinted pill + matching ink. The pairing that clears 4.5:1. */
export const ACCENT_CHIP: Record<Accent, string> = {
  blue: 'bg-blue/15 text-blue-deep',
  indigo: 'bg-indigo/15 text-indigo-deep',
  violet: 'bg-violet/15 text-violet-deep',
  orchid: 'bg-orchid/15 text-orchid-deep',
  pink: 'bg-pink/15 text-pink-deep',
  rose: 'bg-rose/15 text-rose-deep',
}

/**
 * Pastel surface + matching ink, for the page's furniture rather than its
 * labels: header icon wells, nav items, section washes. This is the step that
 * makes a page look coloured at rest — chips alone are too small to change how
 * a screen reads.
 */
export const ACCENT_WELL: Record<Accent, string> = {
  blue: 'bg-blue-tint text-blue-deep',
  indigo: 'bg-indigo-tint text-indigo-deep',
  violet: 'bg-violet-tint text-violet-deep',
  orchid: 'bg-orchid-tint text-orchid-deep',
  pink: 'bg-pink-tint text-pink-deep',
  rose: 'bg-rose-tint text-rose-deep',
}

/** Pastel surface only, for washes that carry their own text colour. */
export const ACCENT_TINT: Record<Accent, string> = {
  blue: 'bg-blue-tint',
  indigo: 'bg-indigo-tint',
  violet: 'bg-violet-tint',
  orchid: 'bg-orchid-tint',
  pink: 'bg-pink-tint',
  rose: 'bg-rose-tint',
}

/** Solid fill, for dots, bars and legend swatches. */
export const ACCENT_FILL: Record<Accent, string> = {
  blue: 'bg-blue',
  indigo: 'bg-indigo',
  violet: 'bg-violet',
  orchid: 'bg-orchid',
  pink: 'bg-pink',
  rose: 'bg-rose',
}

/** Ink only, for icons and standalone labels. */
export const ACCENT_TEXT: Record<Accent, string> = {
  blue: 'text-blue-deep',
  indigo: 'text-indigo-deep',
  violet: 'text-violet-deep',
  orchid: 'text-orchid-deep',
  pink: 'text-pink-deep',
  rose: 'text-rose-deep',
}

/**
 * Navigation states. Written out per accent because Tailwind scans for whole
 * class strings — `hover:bg-${a}-tint/60` compiles but emits no CSS.
 */
export const ACCENT_NAV: Record<Accent, { active: string; idle: string }> = {
  blue: {
    active: 'bg-blue-tint font-medium text-blue-deep',
    idle: 'text-ink-2 hover:bg-blue-tint/60 hover:text-blue-deep',
  },
  indigo: {
    active: 'bg-indigo-tint font-medium text-indigo-deep',
    idle: 'text-ink-2 hover:bg-indigo-tint/60 hover:text-indigo-deep',
  },
  violet: {
    active: 'bg-violet-tint font-medium text-violet-deep',
    idle: 'text-ink-2 hover:bg-violet-tint/60 hover:text-violet-deep',
  },
  orchid: {
    active: 'bg-orchid-tint font-medium text-orchid-deep',
    idle: 'text-ink-2 hover:bg-orchid-tint/60 hover:text-orchid-deep',
  },
  pink: {
    active: 'bg-pink-tint font-medium text-pink-deep',
    idle: 'text-ink-2 hover:bg-pink-tint/60 hover:text-pink-deep',
  },
  rose: {
    active: 'bg-rose-tint font-medium text-rose-deep',
    idle: 'text-ink-2 hover:bg-rose-tint/60 hover:text-rose-deep',
  },
}

/**
 * One accent per destination, so a section keeps the same colour in the nav and
 * in its own page header. Colour becomes a wayfinding cue rather than
 * decoration. Walks the arc in route order.
 */
export const ROUTE_ACCENT: Record<string, Accent> = {
  '/': 'blue',
  '/library': 'indigo',
  '/knowledge': 'violet',
  '/experts': 'orchid',
  '/dashboard': 'pink',
}

/** Analyst tiers. Shared so the roster grid and the profile page agree. */
export const LEVEL_ACCENT: Record<'L1' | 'L2' | 'L3', Accent> = {
  L1: 'blue',
  L2: 'violet',
  L3: 'pink',
}

/** Stable accent for an arbitrary key, so the same label keeps its colour
 *  across renders and across pages. */
export function accentFor(key: string): Accent {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0
  return ACCENT_ORDER[Math.abs(h) % ACCENT_ORDER.length]
}
