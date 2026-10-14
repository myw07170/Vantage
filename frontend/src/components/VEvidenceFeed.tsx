import { motion } from 'framer-motion'
import { ExternalLink, FileText } from 'lucide-react'
import type { Evidence } from '../types'
import { SOURCE_LABEL, SOURCE_STYLE } from '../lib/labels'

function freshnessLabel(days: number | null | undefined): string {
  if (days == null) return ''
  if (days <= 30) return 'Past month'
  if (days <= 365) return 'Past year'
  if (days <= 730) return '1-2 years'
  return 'Older'
}

/** One piece of evidence. `credibility` is a 0-100 integer. */
export function VEvidenceCard({
  ev,
  index,
  highlighted,
}: {
  ev: Evidence
  index?: number
  highlighted?: boolean
}) {
  const label = SOURCE_LABEL[ev.source_type] ?? ev.source_type
  const cls = SOURCE_STYLE[ev.source_type] ?? 'bg-primary-tint text-primary-deep'
  const cred = Math.round(ev.credibility)
  const fresh = freshnessLabel(ev.freshness_days)
  return (
    <motion.a
      id={`ev-${ev.evidence_id}`}
      href={ev.source_url}
      target="_blank"
      rel="noreferrer"
      initial={{ opacity: 0, x: 8 }}
      animate={
        highlighted ? { opacity: 1, x: 0, scale: [1, 1.04, 1] } : { opacity: 1, x: 0 }
      }
      transition={highlighted ? { duration: 0.7 } : undefined}
      className={`group block rounded-card border bg-card p-3.5 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-float ${
        highlighted ? 'border-primary ring-2 ring-primary/40' : 'border-line/60'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center rounded-chip px-2 h-5 text-tag font-medium ${cls}`}
        >
          {label}
        </span>
        {typeof index === 'number' && (
          <span className="text-tag text-ink-3">#{index + 1}</span>
        )}
        {fresh && (
          <span className="inline-flex h-5 items-center rounded-chip bg-paper px-1.5 text-tag text-ink-3">
            {fresh}
          </span>
        )}
        <span
          className="ml-auto inline-flex items-center gap-1 text-tag text-ink-3"
          title="Credibility 0-100: source type, domain authority, recency and fetch quality"
        >
          Credibility {cred}
        </span>
      </div>
      <div className="mt-2 flex items-start gap-1.5">
        <FileText size={14} className="mt-0.5 shrink-0 text-ink-3" />
        <span className="line-clamp-2 text-aux font-medium text-ink">{ev.title}</span>
        <ExternalLink
          size={13}
          className="ml-auto shrink-0 text-ink-3 opacity-0 transition-opacity group-hover:opacity-100"
        />
      </div>
      <p className="mt-1.5 line-clamp-3 text-tag leading-relaxed text-ink-2">
        {ev.excerpt}
      </p>
      {ev.domain && (
        <div className="mt-1.5 truncate text-tag text-ink-3">{ev.domain}</div>
      )}
    </motion.a>
  )
}

/** Live evidence stream. */
export function VEvidenceFeed({ evidences }: { evidences: Evidence[] }) {
  if (evidences.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-ink-3">
        <FileText size={28} strokeWidth={1.5} />
        <p className="text-aux">Collecting evidence…</p>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      {evidences.map((ev, i) => (
        <VEvidenceCard key={ev.evidence_id} ev={ev} index={i} />
      ))}
    </div>
  )
}
