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

/** Tailwind classes per source type, for evidence badges. */
export const SOURCE_STYLE: Record<string, string> = {
  official: 'bg-primary-tint text-primary-deep',
  sec_filing: 'bg-primary-tint text-primary-deep',
  analyst: 'bg-sun-soft text-warn',
  news: 'bg-sun-soft text-warn',
  review: 'bg-[#EEF2F6] text-info',
  reddit: 'bg-[#FDEDE8] text-[#C4552C]',
  hackernews: 'bg-[#FBF0E6] text-[#B4622A]',
  youtube: 'bg-[#FBEAEA] text-[#B5433F]',
  x: 'bg-[#EDEEF0] text-ink-2',
  forum: 'bg-[#EEF2F6] text-info',
  web: 'bg-[#F0F2F0] text-ink-3',
  unknown: 'bg-[#F0F2F0] text-ink-3',
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
  web: { bg: '#8FA8C0', fg: '#FFFFFF' },
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
  medium: 'bg-sun-soft text-warn',
  low: 'bg-[#F5EDEC] text-risk',
  unverified: 'bg-[#F0F2F0] text-ink-3',
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
