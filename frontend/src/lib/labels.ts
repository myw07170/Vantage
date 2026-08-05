/**
 * Shared display labels.
 *
 * In the original these maps were duplicated across three components each,
 * which meant renaming a pipeline stage required finding all three. Everything
 * user-facing that maps a backend enum to text lives here.
 */
import type { Confidence } from '../types'

/* ── Pipeline stages ─────────────────────────────────────────────────────── */
export const STAGE_LABEL: Record<string, string> = {
  intake: 'Understand',
  orchestrator: 'Assemble',
  collect: 'Collect',
  analyze: 'Analyze',
  write: 'Write',
  audit: 'Review',
  verify: 'Verify',
  done: 'Deliver',
}

export const stageLabel = (s: string) => STAGE_LABEL[s] ?? s

/* ── Evidence source types ───────────────────────────────────────────────── */
/** Keys match SourceType in backend/app/core/models.py. */
export const SOURCE_LABEL: Record<string, string> = {
  official: 'Official',
  sec_filing: 'SEC filing',
  analyst: 'Analyst',
  news: 'News',
  review: 'Review site',
  reddit: 'Reddit',
  hackernews: 'Hacker News',
  youtube: 'YouTube',
  x: 'X',
  forum: 'Forum',
  web: 'Web',
  unknown: 'Unknown',
}

export const sourceLabel = (s: string) => SOURCE_LABEL[s] ?? s

/** Tailwind classes per source type, for evidence badges.
 *
 * Pill backgrounds are the light tone; labels are the matching `-deep` tone.
 * A badge set in its own base colour measures under 2.2:1 against its pill,
 * which is the least readable text in the product on the elements carrying its
 * most important signal.
 */
export const SOURCE_STYLE: Record<string, string> = {
  // First-hand documentation, in the brand colour: these are the sources the
  // product is arguing you should trust most.
  official: 'bg-primary-tint text-primary-deep',
  sec_filing: 'bg-teal/15 text-teal-deep',
  // Commentary.
  analyst: 'bg-violet/15 text-violet-deep',
  news: 'bg-amber/15 text-amber-deep',
  // User voice. The three platforms with strong brand colours keep them —
  // recognising a Reddit badge at a glance beats palette purity.
  review: 'bg-green/15 text-green-deep',
  reddit: 'bg-[#FDEDE8] text-[#9C3F1E]',
  hackernews: 'bg-[#FBF0E6] text-[#8A4A1F]',
  youtube: 'bg-[#FBEAEA] text-[#8E3532]',
  x: 'bg-[#EDEEF0] text-ink-2',
  forum: 'bg-rose/15 text-rose-deep',
  web: 'bg-paper text-ink-2',
  unknown: 'bg-paper text-ink-2',
}

/** Three buckets used by the dashboard's source-mix breakdown. */
export const SOURCE_CATEGORY: Record<string, 'primary' | 'media' | 'social'> = {
  official: 'primary',
  sec_filing: 'primary',
  analyst: 'media',
  news: 'media',
  review: 'social',
  reddit: 'social',
  hackernews: 'social',
  youtube: 'social',
  x: 'social',
  forum: 'social',
  web: 'media',
  unknown: 'media',
}

export const CATEGORY_LABEL = {
  primary: 'Primary sources',
  media: 'Press and analysts',
  social: 'User voice',
} as const

/* ── Social platforms ────────────────────────────────────────────────────── */
/** Keys match the registry in backend/app/core/platforms.py. */
export const PLATFORM_LABEL: Record<string, string> = {
  reddit: 'Reddit',
  hackernews: 'Hacker News',
  g2: 'G2',
  trustpilot: 'Trustpilot',
  capterra: 'Capterra',
  youtube: 'YouTube',
  x: 'X',
  web: 'Web',
}

/** Each platform's brand colour, for the sentiment wall. */
export const PLATFORM_STYLE: Record<string, { bg: string; fg: string }> = {
  reddit: { bg: '#FF4500', fg: '#FFFFFF' },
  hackernews: { bg: '#FF6600', fg: '#FFFFFF' },
  g2: { bg: '#FF492C', fg: '#FFFFFF' },
  trustpilot: { bg: '#00B67A', fg: '#FFFFFF' },
  capterra: { bg: '#FF9D28', fg: '#FFFFFF' },
  youtube: { bg: '#FF0000', fg: '#FFFFFF' },
  x: { bg: '#0F1419', fg: '#FFFFFF' },
  web: { bg: '#6C7A8C', fg: '#FFFFFF' },
}

export const platformLabel = (p: string) => PLATFORM_LABEL[p] ?? p

/* ── Claim confidence ────────────────────────────────────────────────────── */
export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: 'High confidence',
  medium: 'Medium confidence',
  low: 'Low confidence',
  unverified: 'Unverified',
}

export const CONFIDENCE_STYLE: Record<Confidence, string> = {
  high: 'bg-primary-tint text-primary-deep',
  medium: 'bg-sun-soft text-warn-deep',
  low: 'bg-risk/15 text-risk-deep',
  unverified: 'bg-paper text-ink-2',
}

/* ── Thought stream kinds ────────────────────────────────────────────────── */
export const THOUGHT_LABEL: Record<string, string> = {
  plan: 'Planning',
  dispatch: 'Assigning',
  action: 'Working',
  finding: 'Finding',
  reflect: 'Reviewing',
}

/* ── Sentiment ───────────────────────────────────────────────────────────── */
export const SENTIMENT_LABEL: Record<string, string> = {
  pos: 'Positive',
  neu: 'Neutral',
  neg: 'Negative',
}

/* ── Research modes ──────────────────────────────────────────────────────── */
export const MODE_LABEL: Record<string, string> = {
  quick: 'Quick',
  deep: 'Deep',
  expert: 'Expert',
}
