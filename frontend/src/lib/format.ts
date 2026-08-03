/** Shared formatting helpers. Locale-aware where it matters. */

const numberFmt = new Intl.NumberFormat('en-US')
const dateFmt = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
})
const dateTimeFmt = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})

export const num = (n: number | null | undefined) =>
  n == null || Number.isNaN(n) ? '—' : numberFmt.format(n)

/** Backend timestamps are naive local ISO strings (`2026-07-31T15:04:05`). */
export function formatDate(iso: string | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : dateFmt.format(d)
}

export function formatDateTime(iso: string | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : dateTimeFmt.format(d)
}

/** `1` -> "1 source", `3` -> "3 sources". */
export function plural(n: number, one: string, many?: string): string {
  return `${numberFmt.format(n)} ${n === 1 ? one : (many ?? `${one}s`)}`
}

export function percent(v: number | null | undefined, digits = 0): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

/** Coerce the loosely-typed metrics payload without throwing. */
export const asNum = (v: unknown): number | null =>
  typeof v === 'number' && !Number.isNaN(v) ? v : null

export const asStr = (v: unknown): string => (typeof v === 'string' ? v : '')

export function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`
}

/** Minutes as a human duration: 95 -> "1h 35m". */
export function duration(minutes: number | null | undefined): string {
  if (minutes == null || Number.isNaN(minutes)) return '—'
  if (minutes < 1) return `${Math.round(minutes * 60)}s`
  if (minutes < 60) return `${Math.round(minutes)}m`
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return m ? `${h}h ${m}m` : `${h}h`
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}
