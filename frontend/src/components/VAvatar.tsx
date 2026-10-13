import { useMemo, useState } from 'react'
import type { Expert } from '../types'

/**
 * Expert avatar: the portrait from `public/assets/avatars`, over a generated
 * monogram.
 *
 * The monogram is not only an error state — it paints first and the portrait
 * loads on top of it, so a slow, missing or broken image degrades to initials
 * on a gradient rather than an empty circle, with nothing shifting when the
 * image does arrive. That also keeps the component working for any roster
 * entry that has no portrait on disk.
 */

// Spread around the palette rather than repeating the brand colour, so a wall
// of monograms still reads as a set of distinct people. White initials sit on
// top, so every stop stays dark enough to carry them.
const GRADIENTS: [string, string][] = [
  ['#5B7396', '#3E5473'],
  ['#7F92AD', '#556B8C'],
  ['#A379C8', '#7A559E'],
  ['#C99089', '#A5554B'],
  ['#7FA88C', '#4F745B'],
  ['#B8996A', '#8C6D3F'],
]

/** The roster's id scheme, which is also the avatar filename. */
const EXPERT_ID = /^L[123]-\d{3}$/

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

  /* Prefer the roster's own path, falling back to the filename convention when
     only an id is to hand. Derived from the id and never the name: building a
     URL out of arbitrary display text would just guarantee a 404. */
  const src = useMemo(() => {
    if (expert?.avatar) return expert.avatar
    const eid = expert?.id ?? id ?? ''
    return EXPERT_ID.test(eid) ? `/assets/avatars/${eid}.jpg` : ''
  }, [expert?.avatar, expert?.id, id])

  /* Remember which url failed rather than a bare "broken" flag: lists reuse DOM
     nodes across renders, and a boolean would carry one expert's failure over
     to whoever lands in the same slot next. Comparing against `src` resets
     itself. */
  const [brokenSrc, setBrokenSrc] = useState('')
  const showImage = src !== '' && src !== brokenSrc

  const [from, to] = useMemo(() => GRADIENTS[hash(key) % GRADIENTS.length], [key])
  const initials = useMemo(() => initialsOf(label), [label])

  return (
    <span
      role="img"
      aria-label={label}
      title={title ?? label}
      className={`relative inline-grid shrink-0 place-items-center overflow-hidden rounded-full font-medium text-white select-none ${className}`}
      style={{
        width: size,
        height: size,
        fontSize: Math.max(9, Math.round(size * 0.38)),
        background: `linear-gradient(135deg, ${from}, ${to})`,
        letterSpacing: '0.02em',
      }}
    >
      {initials}
      {showImage && (
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          draggable={false}
          onError={() => setBrokenSrc(src)}
          className="absolute inset-0 h-full w-full object-cover"
        />
      )}
    </span>
  )
}
