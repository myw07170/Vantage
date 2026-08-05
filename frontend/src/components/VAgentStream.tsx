import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Compass, Users, Settings, Lightbulb, Search, type LucideIcon } from 'lucide-react'
import type { ThoughtItem, ThoughtKind } from '../types'
import { useExpertStore } from '../store/expertStore'
import { THOUGHT_LABEL } from '../lib/labels'
import { ACCENT_CHIP, type Accent } from '../lib/accents'
import { VAvatar } from './VAvatar'

// One accent per kind, so a glance down the stream reads as rhythm rather than
// as a wall of one colour. These are categorical, not status — a `reflect` is
// not worse than a `finding`.
const KIND_META: Record<ThoughtKind, { icon: LucideIcon; accent: Accent }> = {
  plan: { icon: Compass, accent: 'blue' },
  dispatch: { icon: Users, accent: 'violet' },
  action: { icon: Settings, accent: 'amber' },
  finding: { icon: Lightbulb, accent: 'green' },
  reflect: { icon: Search, accent: 'rose' },
}

/** Live thought stream, auto-scrolled to the newest entry. */
export function VAgentStream({ thoughts }: { thoughts: ThoughtItem[] }) {
  const byId = useExpertStore((s) => s.byId)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [thoughts.length])

  return (
    <div className="flex flex-col gap-3">
      {thoughts.map((t) => {
        const meta = KIND_META[t.kind] ?? KIND_META.action
        const Icon = meta.icon
        const expert = t.expert ? byId(t.expert) : undefined
        return (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="flex gap-2.5"
          >
            {expert ? (
              <VAvatar expert={expert} size={28} className="mt-0.5 shadow-card" />
            ) : (
              <span
                className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full ${ACCENT_CHIP[meta.accent]}`}
              >
                <Icon size={14} />
              </span>
            )}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span
                  className={`inline-flex items-center gap-1 rounded-chip px-2 h-5 text-tag font-medium ${ACCENT_CHIP[meta.accent]}`}
                >
                  <Icon size={11} />
                  {THOUGHT_LABEL[t.kind] ?? t.kind}
                </span>
                {expert && <span className="text-tag text-ink-3">{expert.name}</span>}
              </div>
              <p className="mt-1 text-aux leading-relaxed text-ink-2">{t.text}</p>
            </div>
          </motion.div>
        )
      })}
      <div ref={endRef} />
    </div>
  )
}
