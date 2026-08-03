import { useMemo } from 'react'
import type { Expert } from '../types'

/**
 * Generated monogram avatar.
 *
 * Replaces the 48 photographic portraits the original shipped (4.4 MB of JPEGs
 * that had to be regenerated for any change to the roster). Initials on a
 * gradient derived from the expert's own id and badge colour: deterministic,
 * zero network cost, and it scales to any roster without new assets.
 */

const GRADIENTS: [string, string][] = [
  ['#7C9885', '#5E7A66'],
  ['#8FA8C0', '#5E7A9B'],
  ['#C2B59B', '#9B8C6E'],
  ['#CE9A92', '#A8746C'],
  ['#A8C0A8', '#7C9885'],
  ['#B0A8C0', '#847AA0'],
]

function hash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export function VAvatar({
  expert,
  name,
  id,
  size = 32,
  className = '',
  title,
}: {
  expert?: Expert
  /** Used when no full expert record is loaded (e.g. the workload board). */
  name?: string
  id?: string
  size?: number
  className?: string
  title?: string
}) {
  const label = expert?.name ?? name ?? id ?? '?'
  const key = expert?.id ?? id ?? label

  const [from, to] = useMemo(() => GRADIENTS[hash(key) % GRADIENTS.length], [key])
  const initials = useMemo(() => initialsOf(label), [label])

  return (
    <span
      className={`inline-grid shrink-0 place-items-center rounded-full font-medium text-white select-none ${className}`}
      style={{
        width: size,
        height: size,
        fontSize: Math.max(9, Math.round(size * 0.38)),
        background: `linear-gradient(135deg, ${from}, ${to})`,
        letterSpacing: '0.02em',
      }}
      title={title ?? label}
      aria-label={label}
    >
      {initials}
    </span>
  )
}
