import { useMemo, useState } from 'react'
import { ACCENT_CHIP } from '../lib/accents'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Library,
  Search,
  Trash2,
  ExternalLink,
  Quote,
  FileText,
  Lightbulb,
  Image as ImageIcon,
  StickyNote,
  Tag as TagIcon,
} from 'lucide-react'
import { useAnnotationStore } from '../store/annotationStore'
import type { KBKind } from '../store/annotationStore'
import { VEmpty, VFilterChip } from '../components/ui'
import { plural } from '../lib/format'

const KIND_META: Record<
  KBKind,
  { label: string; icon: typeof FileText; cls: string }
> = {
  // A distinct accent each. Previously `warn` covered both quotes and excerpts
  // and `risk` doubled as highlights, so half the library looked alike.
  claim: { label: 'Claims', icon: Lightbulb, cls: ACCENT_CHIP.green },
  evidence: { label: 'Evidence', icon: FileText, cls: ACCENT_CHIP.blue },
  quote: { label: 'Quotes', icon: Quote, cls: ACCENT_CHIP.amber },
  figure: { label: 'Images', icon: ImageIcon, cls: ACCENT_CHIP.teal },
  note: { label: 'Excerpts', icon: StickyNote, cls: ACCENT_CHIP.rose },
  highlight: { label: 'Highlights', icon: TagIcon, cls: ACCENT_CHIP.violet },
}

export default function KnowledgePage() {
  const navigate = useNavigate()
  const { knowledge, removeFromKB } = useAnnotationStore()
  const [q, setQ] = useState('')
  const [kind, setKind] = useState<KBKind | 'all'>('all')

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    return knowledge.filter((k) => {
      if (kind !== 'all' && k.kind !== kind) return false
      if (!t) return true
      return (
        k.content.toLowerCase().includes(t) ||
        k.reportTitle.toLowerCase().includes(t) ||
        k.tags.some((tg) => tg.toLowerCase().includes(t))
      )
    })
  }, [knowledge, q, kind])

  const grouped = useMemo(() => {
    const map = new Map<string, { title: string; items: typeof filtered }>()
    for (const k of filtered) {
      const g = map.get(k.reportId) ?? { title: k.reportTitle, items: [] }
      g.items.push(k)
      map.set(k.reportId, g)
    }
    return Array.from(map.entries())
  }, [filtered])

  const kindCounts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const k of knowledge) c[k.kind] = (c[k.kind] ?? 0) + 1
    return c
  }, [knowledge])

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="flex items-center gap-3">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-card bg-primary-tint text-primary">
          <Library size={24} strokeWidth={1.8} />
        </span>
        <div>
          <h1 className="font-serif text-h1 text-ink">Knowledge base</h1>
          <p className="text-aux text-ink-2">
            {plural(knowledge.length, 'saved insight')} from your reports — each one
            links back to where it came from.
          </p>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <div className="relative min-w-[240px] flex-1">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3"
          />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search saved content, reports or tags…"
            className="h-11 w-full rounded-btn border border-line bg-card pl-9 pr-3 text-aux text-ink outline-none transition-all focus:border-primary focus:shadow-glow"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <VFilterChip
            active={kind === 'all'}
            onClick={() => setKind('all')}
            count={knowledge.length}
          >
            All
          </VFilterChip>
          {(Object.keys(KIND_META) as KBKind[]).map((k) =>
            kindCounts[k] ? (
              <VFilterChip
                key={k}
                active={kind === k}
                onClick={() => setKind(k)}
                count={kindCounts[k]}
              >
                {KIND_META[k].label}
              </VFilterChip>
            ) : null,
          )}
        </div>
      </div>

      {filtered.length === 0 ? (
        <VEmpty
          icon={<Library size={36} strokeWidth={1.4} />}
          title={knowledge.length === 0 ? 'Nothing saved yet' : 'No matches'}
          hint={
            knowledge.length === 0
              ? 'Open any report, select text or use "Save to knowledge base" to collect the parts worth keeping.'
              : 'Try a different search term or clear the filter.'
          }
        />
      ) : (
        <div className="mt-8 flex flex-col gap-8">
          {grouped.map(([reportId, g]) => (
            <div key={reportId}>
              <button
                onClick={() => navigate(`/report/${reportId}`)}
                className="mb-3 inline-flex items-center gap-1.5 text-left text-aux font-semibold text-ink hover:text-primary-deep"
              >
                {g.title}
                <ExternalLink size={13} className="shrink-0 text-ink-3" />
              </button>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {g.items.map((k) => {
                  const meta = KIND_META[k.kind]
                  return (
                    <motion.div
                      key={k.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="group relative flex flex-col rounded-card border border-line/60 bg-card p-4 shadow-card transition-shadow hover:shadow-float"
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={`inline-flex h-6 items-center gap-1 rounded-chip px-2 text-tag font-medium ${meta.cls}`}
                        >
                          <meta.icon size={12} /> {meta.label}
                        </span>
                        {k.brand && <span className="text-tag text-ink-3">{k.brand}</span>}
                        <button
                          onClick={() => removeFromKB(k.id)}
                          className="ml-auto text-ink-3 opacity-0 transition-opacity hover:text-risk-deep group-hover:opacity-100"
                          title="Remove from knowledge base"
                          aria-label="Remove from knowledge base"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                      {k.imageSrc && (
                        <img
                          src={k.imageSrc}
                          alt=""
                          referrerPolicy="no-referrer"
                          className="mt-3 aspect-[16/9] w-full rounded-btn object-cover"
                          onError={(e) =>
                            ((e.target as HTMLImageElement).style.display = 'none')
                          }
                        />
                      )}
                      <p className="mt-3 flex-1 text-aux leading-relaxed text-ink-2">
                        {k.content}
                      </p>
                      {k.tags.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {k.tags.map((t, i) => (
                            <span
                              key={i}
                              className="rounded-chip bg-primary-tint px-2 py-0.5 text-tag text-primary-deep"
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      )}
                      {k.sourceUrl && (
                        <a
                          href={k.sourceUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-3 inline-flex items-center gap-1 text-tag font-medium text-primary-deep hover:underline"
                        >
                          <ExternalLink size={12} /> View source
                        </a>
                      )}
                    </motion.div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
