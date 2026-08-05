import { motion } from 'framer-motion'
import { ShieldCheck, ShieldAlert, ShieldQuestion, Link2 } from 'lucide-react'
import type { Claim } from '../types'
import { useExpertStore } from '../store/expertStore'
import { CONFIDENCE_LABEL } from '../lib/labels'
import { plural } from '../lib/format'
import { VAvatar } from './VAvatar'

const CONF_META = {
  high: { cls: 'bg-ok/15 text-ok-deep', icon: ShieldCheck },
  medium: { cls: 'bg-warn/15 text-warn-deep', icon: ShieldCheck },
  low: { cls: 'bg-risk/15 text-risk-deep', icon: ShieldAlert },
  unverified: { cls: 'bg-ink-3/15 text-ink-3', icon: ShieldQuestion },
} as const

/** A claim with its confidence, cross-validation flag, citations and author. */
export function VClaimCard({
  claim,
  onCite,
}: {
  claim: Claim
  onCite?: (evidenceIds: string[]) => void
}) {
  const byId = useExpertStore((s) => s.byId)
  const meta = CONF_META[claim.confidence] ?? CONF_META.unverified
  const Icon = meta.icon
  const author = byId(claim.author)
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-card border border-line/60 bg-card p-4 shadow-card"
    >
      <p className="text-body text-ink">{claim.text}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 rounded-chip px-2.5 h-6 text-tag font-medium ${meta.cls}`}
        >
          <Icon size={12} /> {CONFIDENCE_LABEL[claim.confidence] ?? claim.confidence}
        </span>
        {claim.cross_validated && (
          <span
            className="inline-flex items-center gap-1 rounded-chip bg-primary-tint px-2.5 h-6 text-tag font-medium text-primary-deep"
            title="Supported by two or more independent domains"
          >
            Cross-validated
          </span>
        )}
        {claim.evidence_ids.length > 0 ? (
          <button
            onClick={() => onCite?.(claim.evidence_ids)}
            className="inline-flex items-center gap-1 rounded-chip border border-line px-2.5 h-6 text-tag text-ink-2 transition-colors hover:bg-primary-tint hover:text-primary-deep"
          >
            <Link2 size={12} /> {plural(claim.evidence_ids.length, 'source')}
          </button>
        ) : (
          <span className="text-tag text-ink-3">No citation</span>
        )}
        {author && (
          <span className="ml-auto inline-flex items-center gap-1.5 text-tag text-ink-3">
            <VAvatar expert={author} size={16} />
            {author.name}
          </span>
        )}
      </div>
    </motion.div>
  )
}
