import { useEffect, useState, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ChevronLeft,
  Network,
  Download,
  BookOpen,
  Quote,
  Users,
  Calendar,
  Lightbulb,
  Sparkles,
  Link2,
  FileText,
  Database,
  ShieldCheck,
  Layers,
  Image as ImageIcon,
  ExternalLink,
  Pencil,
  Eye,
  Highlighter,
  Trash2,
  BookmarkPlus,
} from 'lucide-react'
import { useReportStore } from '../store/reportStore'
import { useAnnotationStore } from '../store/annotationStore'
import type { HighlightColor } from '../store/annotationStore'
import { VChart } from '../components/VChart'
import { VClaimCard } from '../components/VClaimCard'
import { VSentimentPanel } from '../components/VSentimentPanel'
import { VEvidenceCard } from '../components/VEvidenceFeed'
import { VEditableBlock, VCitedText } from '../components/VEditableBlock'
import { VSelectionToolbar } from '../components/VSelectionToolbar'
import { VMetricsPanel } from '../components/VMetricsPanel'
import { VQualityGate } from '../components/VQualityGate'
import { VAuditReview } from '../components/VAuditReview'
import { VVerifyReport } from '../components/VVerifyReport'
import { VDecisionReplay } from '../components/VDecisionReplay'
import { VDataGrid } from '../components/VDataGrid'
import { VFeatureMatrix, VPricingTable, VPersonaCards } from '../components/VStructured'
import { refineSection, submitFeedback } from '../lib/api'
import { VSkeleton, VCountUp } from '../components/ui'
import { formatDate, plural, truncate } from '../lib/format'

const HL_DOT: Record<HighlightColor, string> = {
  sun: 'bg-sun',
  ok: 'bg-ok',
  risk: 'bg-risk',
  info: 'bg-info',
}
const HL_LABEL: Record<HighlightColor, string> = {
  sun: 'Important',
  ok: 'Agree',
  risk: 'Questionable',
  info: 'Follow up',
}

/** Sections that have no body text to deepen. */
const NON_REFINABLE = ['sentiment', 'trace_note', 'figures']

export default function ReportPage() {
  const { reportId } = useParams()
  const navigate = useNavigate()
  const { current, loading, error, load } = useReportStore()
  const [activeSection, setActiveSection] = useState<string>('')
  const [readProgress, setReadProgress] = useState(0)
  const [editMode, setEditMode] = useState(false)
  const [highlightedEv, setHighlightedEv] = useState<string[]>([])
  const [refiningSec, setRefiningSec] = useState<string>('')
  const mainRef = useRef<HTMLElement>(null)
  const articleRef = useRef<HTMLDivElement>(null)
  const rid = reportId ?? ''
  const { annotations, setEdit, getEdit, addHighlight, removeHighlight, addToKB } =
    useAnnotationStore()
  const reportHls = annotations[rid]?.highlights ?? []

  const [toast, setToast] = useState('')
  function flash(msg: string) {
    setToast(msg)
    window.setTimeout(() => setToast(''), 1800)
  }

  useEffect(() => {
    if (reportId) load(reportId)
  }, [reportId, load])

  // Reading progress plus table-of-contents scroll-spy.
  useEffect(() => {
    const el = mainRef.current
    if (!el || !current) return
    const onScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = el
      const max = scrollHeight - clientHeight
      setReadProgress(max > 0 ? Math.min(100, (scrollTop / max) * 100) : 0)
      let cur = ''
      for (const s of current.sections) {
        const node = document.getElementById(`sec-${s.id}`)
        if (
          node &&
          node.getBoundingClientRect().top - el.getBoundingClientRect().top <= 120
        ) {
          cur = s.id
        }
      }
      if (cur) setActiveSection(cur)
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => el.removeEventListener('scroll', onScroll)
  }, [current])

  function jumpTo(id: string) {
    setActiveSection(id)
    document
      .getElementById(`sec-${id}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function jumpToEvidence(ids: string[]) {
    if (ids[0])
      document
        .getElementById(`ev-${ids[0]}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setHighlightedEv(ids)
    window.setTimeout(() => setHighlightedEv([]), 2400)
  }

  /** Re-research one section against the reader's annotations. */
  async function handleRefine(sectionId: string) {
    if (!current) return
    const notes = (annotations[rid]?.highlights ?? [])
      .filter((h) => h.sectionId === sectionId)
      .map((h) =>
        h.comment
          ? `${h.comment} (regarding: ${truncate(h.text, 60)})`
          : `Go deeper on: ${truncate(h.text, 80)}`,
      )
    if (notes.length === 0) {
      flash('Highlight or annotate something in this section first')
      return
    }
    setRefiningSec(sectionId)
    flash('Deepening this section from your notes…')
    const res = await refineSection(rid, sectionId, notes)
    setRefiningSec('')
    if (res.ok && res.section) {
      const next = {
        ...current,
        sections: current.sections.map((s) => (s.id === sectionId ? res.section! : s)),
      }
      useReportStore.setState((st) => ({
        current: next,
        cache: { ...st.cache, [rid]: next },
      }))
      flash('Section updated')
    } else {
      flash(res.message || 'Could not deepen the section — try again')
    }
  }

  function toggleEditMode() {
    setEditMode((v) => {
      const leaving = v
      if (leaving && current) {
        // Leaving edit mode reports the real correction rate back to the server,
        // which is what drives the human-correction metric.
        const edits = annotations[rid]?.edits ?? {}
        const editedBlocks = Object.keys(edits).length
        const totalBlocks = current.sections.reduce(
          (acc, s) => acc + (s.paragraphs?.length ?? 0) + (s.key_takeaway ? 1 : 0),
          0,
        )
        if (editedBlocks > 0) {
          submitFeedback(rid, editedBlocks, totalBlocks, { edits }).catch(() => {})
          flash(`Recorded ${editedBlocks} of ${totalBlocks} blocks edited`)
        }
      }
      return !v
    })
  }

  function handleHighlight(sectionId: string, text: string, color: HighlightColor) {
    addHighlight(rid, { sectionId, text, color, comment: '' })
  }

  function handleComment(sectionId: string, text: string) {
    const comment = window.prompt('Add a note:', '')
    if (comment != null)
      addHighlight(rid, { sectionId, text, color: 'info', comment: comment.trim() })
  }

  function handleSaveSelectionKB(sectionId: string, text: string) {
    if (!current) return
    const ok = addToKB({
      reportId: rid,
      reportTitle: current.title,
      kind: 'note',
      title: `Excerpt · ${sectionId}`,
      content: text,
      tags: current.brands ?? [],
    })
    flash(ok ? 'Saved to your knowledge base' : 'Already saved')
  }

  function saveClaimToKB(claimText: string, evidenceIds: string[]) {
    if (!current) return
    const ev = current.evidence.find((e) => e.evidence_id === evidenceIds[0])
    const ok = addToKB({
      reportId: rid,
      reportTitle: current.title,
      kind: 'claim',
      title: 'Key claim',
      content: claimText,
      sourceUrl: ev?.source_url,
      evidenceId: ev?.evidence_id,
      tags: current.brands ?? [],
    })
    flash(ok ? 'Claim saved to your knowledge base' : 'Already saved')
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-read px-6 py-16">
        <VSkeleton className="h-48 w-full rounded-card" />
        <VSkeleton className="mt-4 h-6 w-2/3" />
        <VSkeleton className="mt-2 h-6 w-1/2" />
      </div>
    )
  }
  if (error || !current) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-bg text-ink-2">
        <p>{error ?? 'Report not found.'}</p>
        <button
          onClick={() => navigate('/')}
          className="h-10 rounded-btn bg-primary px-5 text-aux font-medium text-white"
        >
          Back to start
        </button>
      </div>
    )
  }

  const r = current
  const evIndex = new Map(r.evidence.map((e, i) => [e.evidence_id, i + 1]))
  const indepDomains = new Set(r.evidence.map((e) => e.domain).filter(Boolean)).size
  const highConf = r.claims.filter((c) => c.confidence === 'high').length
  const confRate = r.claims.length ? Math.round((highConf / r.claims.length) * 100) : 0
  const metrics = [
    { icon: FileText, label: 'Claims', value: r.claims.length, unit: '' },
    { icon: Database, label: 'Sources', value: r.evidence.length, unit: '' },
    { icon: Layers, label: 'Independent domains', value: indepDomains, unit: '' },
    { icon: ShieldCheck, label: 'High confidence', value: confRate, unit: '%' },
  ]

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg">
      {/* Table of contents */}
      <aside className="hidden w-72 shrink-0 flex-col border-r border-line bg-card/50 lg:flex">
        <div className="flex h-14 items-center gap-2 border-b border-line px-5">
          <button
            onClick={() => navigate('/')}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-btn text-ink-2 hover:bg-primary-tint"
            aria-label="Back"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="text-aux font-semibold text-ink">Contents</span>
        </div>
        <div className="px-5 pt-3">
          <div className="flex items-center justify-between text-tag text-ink-3">
            <span>Reading progress</span>
            <span>{Math.round(readProgress)}%</span>
          </div>
          <div className="mt-1.5 h-1 w-full overflow-hidden rounded-chip bg-line">
            <div
              className="h-full rounded-chip bg-primary transition-all duration-150"
              style={{ width: `${readProgress}%` }}
            />
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto p-3">
          {r.toc.map((t, i) => {
            const active = activeSection === t.id
            return (
              <button
                key={t.id}
                onClick={() => jumpTo(t.id)}
                className={`flex w-full items-start gap-2.5 rounded-btn px-3 py-2 text-left text-aux transition-colors ${
                  active
                    ? 'bg-primary-tint font-medium text-primary-deep'
                    : 'text-ink-2 hover:bg-primary-tint/50'
                }`}
              >
                <span
                  className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-chip text-[11px] font-semibold transition-colors ${
                    active ? 'bg-primary text-white' : 'bg-line/70 text-ink-3'
                  }`}
                >
                  {i + 1}
                </span>
                <span className="leading-snug">{t.title}</span>
              </button>
            )
          })}
        </nav>
        <div className="border-t border-line p-3">
          <button
            onClick={() => navigate(`/graph/${r.id}`)}
            className="flex h-10 w-full items-center justify-center gap-2 rounded-btn bg-primary-tint px-3 text-aux font-medium text-primary-deep hover:bg-primary-soft/40"
          >
            <Network size={16} /> Evidence graph
          </button>
        </div>
      </aside>

      {/* Article */}
      <main ref={mainRef} className="min-w-0 flex-1 overflow-y-auto">
        <div className="sticky top-0 z-20 h-0.5 w-full bg-transparent">
          <div
            className="h-full bg-primary transition-all duration-150"
            style={{ width: `${readProgress}%` }}
          />
        </div>

        <div className="relative overflow-hidden">
          {r.cover_image ? (
            <img src={r.cover_image} alt="" className="h-60 w-full object-cover" />
          ) : (
            <div className="h-60 w-full bg-gradient-to-br from-primary to-primary-deep" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-ink/70 via-ink/20 to-transparent" />
          <div className="absolute bottom-0 left-0 right-0 p-8">
            <motion.h1
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="font-serif text-[32px] leading-tight text-white"
            >
              {r.title}
            </motion.h1>
            <p className="mt-2 max-w-2xl text-aux text-white/85">{r.subtitle}</p>
            <div className="mt-3 flex flex-wrap items-center gap-4 text-tag text-white/75">
              <span className="inline-flex items-center gap-1">
                <Calendar size={13} /> {formatDate(r.created_at)}
              </span>
              <span className="inline-flex items-center gap-1">
                <Users size={13} /> {plural(r.experts.length, 'analyst')}
              </span>
              <span className="inline-flex items-center gap-1">
                <Quote size={13} /> {plural(r.claims.length, 'claim')} ·{' '}
                {plural(r.evidence.length, 'source')}
              </span>
            </div>
          </div>
          <div className="absolute right-6 top-6 flex flex-wrap items-center justify-end gap-2">
            <button
              onClick={() => navigate('/knowledge')}
              className="inline-flex h-9 items-center gap-1.5 rounded-btn bg-card/90 px-3 text-aux font-medium text-ink-2 backdrop-blur hover:text-primary-deep"
            >
              <BookOpen size={15} /> Saved
            </button>
            {r.trace && r.trace.length > 0 && (
              <button
                onClick={() => navigate(`/trace/${r.id}`)}
                className="inline-flex h-9 items-center gap-1.5 rounded-btn bg-card/90 px-3 text-aux font-medium text-ink-2 backdrop-blur hover:text-primary-deep"
              >
                <Network size={15} /> Trace
              </button>
            )}
            <button
              onClick={toggleEditMode}
              className={`inline-flex h-9 items-center gap-1.5 rounded-btn px-3 text-aux font-medium backdrop-blur ${
                editMode
                  ? 'bg-primary text-white'
                  : 'bg-card/90 text-ink-2 hover:text-primary-deep'
              }`}
            >
              {editMode ? (
                <>
                  <Eye size={15} /> Read
                </>
              ) : (
                <>
                  <Pencil size={15} /> Edit
                </>
              )}
            </button>
            <button
              onClick={() => window.print()}
              className="inline-flex h-9 items-center gap-1.5 rounded-btn bg-card/90 px-3 text-aux font-medium text-ink-2 backdrop-blur hover:text-primary-deep"
            >
              <Download size={15} /> Export
            </button>
          </div>
        </div>

        <div className="border-b border-line bg-card/60">
          <div className="mx-auto grid max-w-3xl grid-cols-2 gap-px px-6 sm:grid-cols-4">
            {metrics.map((m, i) => (
              <div key={i} className="flex flex-col items-center gap-1 py-5 text-center">
                <m.icon size={16} className="text-primary" />
                <div className="flex items-baseline gap-0.5">
                  <VCountUp
                    value={m.value}
                    className="font-serif text-[26px] leading-none text-ink"
                  />
                  {m.unit && <span className="text-tag text-ink-3">{m.unit}</span>}
                </div>
                <span className="text-tag leading-tight text-ink-3">{m.label}</span>
              </div>
            ))}
          </div>
        </div>

        <article ref={articleRef} className="relative mx-auto max-w-3xl px-6 py-10">
          <VSelectionToolbar
            containerRef={articleRef}
            enabled
            onHighlight={handleHighlight}
            onComment={handleComment}
            onSaveKB={handleSaveSelectionKB}
          />

          <VMetricsPanel metrics={r.metrics} />
          <VAuditReview review={r.audit_review} />
          <VVerifyReport review={r.verify_review} />
          <VQualityGate before={r.quality_before} after={r.quality_after} />

          {r.sections.map((sec, idx) => (
            <section
              key={sec.id}
              id={`sec-${sec.id}`}
              data-section-id={sec.id}
              className="mb-12 scroll-mt-6"
            >
              <div className="flex items-start gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-card bg-primary-tint font-serif text-[18px] font-semibold text-primary-deep">
                  {idx + 1}
                </span>
                <h2 className="font-serif text-h2 text-ink">{sec.title}</h2>
                {sec.rewritten && (
                  <span
                    title="Verification found a defect in the first draft; this section was rewritten against the same evidence."
                    className="mt-1.5 shrink-0 rounded-chip bg-primary-tint px-2 py-0.5 text-tag font-medium text-primary-deep"
                  >
                    Rewritten after verification
                  </span>
                )}
              </div>

              {sec.key_takeaway && (
                <div className="mt-3 flex gap-3 rounded-card border-l-[3px] border-primary bg-primary-tint/40 p-4">
                  <Lightbulb size={18} className="mt-0.5 shrink-0 text-primary-deep" />
                  <VEditableBlock
                    as="p"
                    value={getEdit(rid, `${sec.id}-takeaway`) ?? sec.key_takeaway}
                    editable={editMode}
                    onSave={(t) => setEdit(rid, `${sec.id}-takeaway`, t)}
                    className="text-body font-medium text-ink"
                    evIndex={evIndex}
                    onCite={jumpToEvidence}
                  />
                </div>
              )}

              <div className="mt-4 space-y-3">
                {sec.paragraphs?.map((p, i) => (
                  <VEditableBlock
                    key={i}
                    as="p"
                    value={getEdit(rid, `${sec.id}-p${i}`) ?? p}
                    editable={editMode}
                    onSave={(t) => setEdit(rid, `${sec.id}-p${i}`, t)}
                    className="text-body leading-relaxed text-ink-2"
                    highlights={reportHls.filter((h) => h.sectionId === sec.id)}
                    evIndex={evIndex}
                    onCite={jumpToEvidence}
                  />
                ))}
              </div>

              {sec.highlights && sec.highlights.length > 0 && (
                <ul className="mt-4 space-y-2 rounded-card bg-card/60 p-4">
                  {sec.highlights.map((h, i) => (
                    <li key={i} className="flex gap-2 text-aux text-ink-2">
                      <Sparkles size={15} className="mt-0.5 shrink-0 text-warn" />
                      <span>
                        <VCitedText text={h} evIndex={evIndex} onCite={jumpToEvidence} />
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {sec.claims && sec.claims.length > 0 && (
                <div className="mt-5 space-y-3">
                  {sec.claims.map((c) => (
                    <div key={c.claim_id} className="group/claim relative">
                      <VClaimCard claim={c} onCite={jumpToEvidence} />
                      <button
                        onClick={() => saveClaimToKB(c.text, c.evidence_ids)}
                        title="Save to knowledge base"
                        aria-label="Save claim to knowledge base"
                        className="absolute right-3 top-3 grid h-7 w-7 place-items-center rounded-btn bg-card/80 text-ink-3 opacity-0 backdrop-blur transition-opacity hover:text-primary-deep group-hover/claim:opacity-100"
                      >
                        <BookmarkPlus size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {sec.charts && sec.charts.length > 0 && (
                <div className="mt-5 grid grid-cols-1 gap-4">
                  {sec.charts.map((c) => (
                    <VChart key={c.chart_id} spec={c} onCite={jumpToEvidence} />
                  ))}
                </div>
              )}

              {sec.structured?.type === 'feature_tree' && (
                <VFeatureMatrix data={sec.structured.data} />
              )}
              {sec.structured?.type === 'pricing_model' && (
                <VPricingTable data={sec.structured.data} />
              )}
              {sec.structured?.type === 'user_persona' && (
                <VPersonaCards data={sec.structured.data} />
              )}

              {sec.data_grid && (
                <VDataGrid grid={sec.data_grid} title={`${sec.title} · data`} />
              )}

              {sec.id === 'sentiment' && r.sentiment && (
                <div className="mt-5">
                  <VSentimentPanel sentiment={r.sentiment} />
                </div>
              )}

              {sec.source_evidence_ids && sec.source_evidence_ids.length > 0 && (
                <div className="mt-5 flex flex-wrap items-center gap-1.5 border-t border-line/60 pt-3">
                  <span className="inline-flex items-center gap-1 text-tag text-ink-3">
                    <Link2 size={13} /> Sources for this section
                  </span>
                  {sec.source_evidence_ids.map((id) => (
                    <button
                      key={id}
                      onClick={() => jumpToEvidence([id])}
                      className="rounded-chip bg-primary-tint px-2 py-0.5 text-tag font-medium text-primary-deep hover:bg-primary-soft/40"
                      title="Jump to this source"
                    >
                      [{evIndex.get(id) ?? '?'}]
                    </button>
                  ))}
                </div>
              )}

              {!NON_REFINABLE.includes(sec.id) && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => handleRefine(sec.id)}
                    disabled={refiningSec === sec.id}
                    className="inline-flex items-center gap-1.5 rounded-btn border border-primary-soft bg-primary-tint/50 px-3 py-1.5 text-tag font-medium text-primary-deep hover:bg-primary-tint disabled:opacity-50"
                  >
                    <Sparkles size={13} />
                    {refiningSec === sec.id ? 'Working…' : 'Deepen from my notes'}
                  </button>
                  {sec.refined && (
                    <span className="rounded-chip bg-ok/10 px-2 py-0.5 text-tag text-ok">
                      Updated
                    </span>
                  )}
                  <span className="text-tag text-ink-3">
                    Highlight a passage and add a note first
                  </span>
                </div>
              )}
            </section>
          ))}

          {r.figures && r.figures.length > 0 && (
            <section id="sec-figures" className="mb-12 scroll-mt-6">
              <div className="flex items-start gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-card bg-primary-tint font-serif text-[18px] font-semibold text-primary-deep">
                  <ImageIcon size={18} />
                </span>
                <h2 className="font-serif text-h2 text-ink">Collected imagery</h2>
              </div>
              <p className="mt-3 text-aux text-ink-2">
                Captured from the pages visited during research — vendor sites, press
                and community posts. Every image links back to the page it came from.
              </p>
              <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
                {r.figures.map((f, i) => (
                  <div
                    key={i}
                    className="group relative overflow-hidden rounded-card border border-line bg-card transition-shadow hover:shadow-md"
                  >
                    <a
                      href={f.source_url}
                      target="_blank"
                      rel="noreferrer"
                      title="Open the source page"
                    >
                      <div className="relative aspect-[16/9] overflow-hidden bg-primary-tint/30">
                        <img
                          src={f.src}
                          alt={f.alt || f.title || ''}
                          loading="lazy"
                          referrerPolicy="no-referrer"
                          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                          onError={(e) => {
                            const wrap = (e.target as HTMLImageElement).closest(
                              '.group',
                            ) as HTMLElement | null
                            if (wrap) wrap.style.display = 'none'
                          }}
                        />
                        {f.brand && (
                          <span className="absolute left-2 top-2 rounded-chip bg-ink/70 px-2 py-0.5 text-tag font-medium text-white backdrop-blur">
                            {f.brand}
                          </span>
                        )}
                      </div>
                    </a>
                    <button
                      onClick={() => {
                        const ok = addToKB({
                          reportId: rid,
                          reportTitle: r.title,
                          kind: 'figure',
                          title: f.title || 'Collected image',
                          content: f.alt || f.title || 'Collected image',
                          sourceUrl: f.source_url,
                          imageSrc: f.src,
                          brand: f.brand,
                          tags: f.brand ? [f.brand] : [],
                        })
                        flash(ok ? 'Image saved' : 'Already saved')
                      }}
                      title="Save to knowledge base"
                      aria-label="Save image to knowledge base"
                      className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-btn bg-card/85 text-ink-3 opacity-0 backdrop-blur transition-opacity hover:text-primary-deep group-hover:opacity-100"
                    >
                      <BookmarkPlus size={14} />
                    </button>
                    <a
                      href={f.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center justify-between gap-2 px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <div className="truncate text-aux font-medium text-ink">
                          {f.title || f.alt || 'Collected image'}
                        </div>
                        <div className="truncate text-tag text-ink-3">
                          {f.domain || f.source_url}
                        </div>
                      </div>
                      <ExternalLink
                        size={14}
                        className="shrink-0 text-ink-3 group-hover:text-primary-deep"
                      />
                    </a>
                  </div>
                ))}
              </div>
            </section>
          )}
        </article>
      </main>

      {/* Sources and notes */}
      <aside className="hidden w-80 shrink-0 flex-col border-l border-line bg-card/50 xl:flex">
        <div className="flex h-14 items-center gap-2 border-b border-line px-5">
          <BookOpen size={16} className="text-primary" />
          <span className="text-aux font-semibold text-ink">Sources &amp; notes</span>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <div className="mb-2 flex items-center gap-1.5 text-tag font-semibold text-ink-3">
            <Highlighter size={13} /> My notes ({reportHls.length})
          </div>
          {reportHls.length === 0 ? (
            <p className="mb-5 rounded-card border border-dashed border-line bg-bg/60 p-3 text-tag leading-relaxed text-ink-3">
              Select any passage to highlight it, add a note, or save it. Use Edit to
              correct the text directly.
            </p>
          ) : (
            <div className="mb-5 flex flex-col gap-2">
              {reportHls.map((h) => (
                <div
                  key={h.id}
                  className="group rounded-card border border-line/60 bg-bg p-2.5"
                >
                  <div className="flex items-start gap-2">
                    <span
                      className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${HL_DOT[h.color]}`}
                    />
                    <button
                      onClick={() => jumpTo(h.sectionId)}
                      className="flex-1 text-left text-tag leading-relaxed text-ink-2 hover:text-primary-deep"
                    >
                      <span className="line-clamp-3">{h.text}</span>
                    </button>
                    <button
                      onClick={() => removeHighlight(rid, h.id)}
                      className="shrink-0 text-ink-3 opacity-0 transition-opacity hover:text-risk group-hover:opacity-100"
                      title="Delete note"
                      aria-label="Delete note"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <div className="mt-1.5 flex items-center gap-1.5 pl-4.5">
                    <span className="rounded-chip bg-line/60 px-1.5 py-0.5 text-[10px] font-medium text-ink-3">
                      {HL_LABEL[h.color]}
                    </span>
                    {h.comment && (
                      <span className="line-clamp-1 text-[11px] italic text-ink-3">
                        “{h.comment}”
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="mb-3 text-tag font-semibold text-ink-3">
            Sources ({r.evidence.length})
          </div>
          <div className="flex flex-col gap-2.5">
            {r.evidence.map((ev, i) => (
              <VEvidenceCard
                key={ev.evidence_id}
                ev={ev}
                index={i}
                highlighted={highlightedEv.includes(ev.evidence_id)}
              />
            ))}
          </div>

          {r.glossary.length > 0 && (
            <>
              <div className="mb-3 mt-6 text-tag font-semibold text-ink-3">Glossary</div>
              <div className="flex flex-col gap-2.5">
                {r.glossary.map((g, i) => (
                  <div key={i} className="rounded-card border border-line/60 bg-bg p-3">
                    <div className="text-aux font-semibold text-ink">{g.term}</div>
                    <p className="mt-1 text-tag leading-relaxed text-ink-2">
                      {g.definition}
                    </p>
                    {g.source && (
                      <div className="mt-1 text-tag text-primary-deep">— {g.source}</div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </aside>

      {r.trace && r.trace.length > 0 && (
        <VDecisionReplay trace={r.trace} onHighlightEvidence={jumpToEvidence} />
      )}

      {toast && (
        <div className="pointer-events-none fixed bottom-8 left-1/2 z-50 -translate-x-1/2">
          <div className="flex items-center gap-2 rounded-card bg-ink/90 px-4 py-2.5 text-aux font-medium text-white shadow-float backdrop-blur">
            <BookmarkPlus size={15} /> {toast}
          </div>
        </div>
      )}
    </div>
  )
}
