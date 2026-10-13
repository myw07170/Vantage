import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { FileText, Plus, Clock, Network, Users, Gauge, Trash2 } from 'lucide-react'
import { deleteReport } from '../lib/api'
import type { ReportCard } from '../types'
import { fadeUp, stagger } from '../lib/motion'
import { VConfirm, VEmpty, VSkeleton } from '../components/ui'
import { formatDate, num } from '../lib/format'
import { MODE_LABEL } from '../lib/labels'
import { ACCENT_CHIP, accentSet } from '../lib/accents'
import { useReportStore } from '../store/reportStore'

/** Products named on a card before the rest are counted off. Four fills two
 *  rows at the narrowest column without pushing the meta line down. */
const CARD_BRANDS = 4

/** The shown brands paired with the hue each gets.
 *
 *  Hashed on a case-folded name so "TikTok" and "Tiktok" — the pipeline records
 *  whichever spelling the sources used — are one product wearing one colour,
 *  while the chip still reads with the spelling the report actually found. */
function brandChips(brands: string[]) {
  const shown = brands.slice(0, CARD_BRANDS)
  const accents = accentSet(shown.map((b) => b.trim().toLowerCase()))
  return shown.map((name, i) => ({ name, accent: accents[i] }))
}

export default function LibraryPage() {
  const navigate = useNavigate()
  // Shared with the sidebar's recents list, so a delete here removes the entry
  // there too instead of leaving a link to a report that no longer exists.
  const reports = useReportStore((s) => s.cards)
  const loading = useReportStore((s) => s.cardsLoading)
  const loadCards = useReportStore((s) => s.loadCards)
  const removeCard = useReportStore((s) => s.removeCard)
  const [pendingDelete, setPendingDelete] = useState<ReportCard | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    loadCards()
  }, [loadCards])

  const confirmDelete = async () => {
    if (!pendingDelete) return
    setDeleting(true)
    const res = await deleteReport(pendingDelete.id)
    setDeleting(false)
    setPendingDelete(null)
    // Drop it locally on success rather than refetching — one less round trip,
    // and a failed delete leaves the card in place instead of silently
    // vanishing it from a list the server still has.
    if (res.ok) removeCard(pendingDelete.id)
  }

  return (
    <div className="mx-auto max-w-content px-8 py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-serif text-h1 text-ink">My reports</h1>
          <p className="mt-1 text-aux text-ink-2">
            Every completed analysis, with its sources kept for verification.
          </p>
        </div>
        <button
          onClick={() => navigate('/')}
          className="inline-flex h-11 items-center gap-2 rounded-btn bg-primary-deep px-5 font-medium text-white shadow-card transition-all hover:bg-primary-deeper hover:shadow-float"
        >
          <Plus size={18} /> New research
        </button>
      </header>

      {loading ? (
        <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {/* Tracks the real card height — 168px of content plus the evidence
              graph footer — so the grid does not jump when the cards land. */}
          {Array.from({ length: 3 }).map((_, i) => (
            <VSkeleton key={i} className="h-[200px]" />
          ))}
        </div>
      ) : reports.length === 0 ? (
        <VEmpty
          icon={<FileText size={32} strokeWidth={1.4} />}
          title="No research yet"
          hint="Start your first competitive analysis — the director will assemble a team and the report will cite every source it uses."
          action={
            <button
              onClick={() => navigate('/')}
              className="inline-flex h-11 items-center gap-2 rounded-btn bg-primary-deep px-6 font-medium text-white shadow-card hover:bg-primary-deeper"
            >
              <Plus size={18} /> Start research
            </button>
          }
        />
      ) : (
        <motion.div
          variants={stagger}
          initial="initial"
          animate="animate"
          className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3"
        >
          {reports.map((r) => (
            <motion.div
              key={r.id}
              variants={fadeUp}
              className="group relative flex flex-col overflow-hidden rounded-card border border-line/60 bg-card text-left shadow-card transition-all hover:-translate-y-0.5 hover:shadow-float"
            >
              {/* Sibling of the card's own button, not a child — nesting one
                  button inside another is invalid and swallows the click.

                  It used to sit on the cover image, where white-on-dark was
                  legible; on the card surface it needs the opposite treatment —
                  quiet until the card is hovered or the button itself is
                  focused, so a grid of cards is not a grid of delete buttons. */}
              <button
                onClick={() => setPendingDelete(r)}
                aria-label={`Delete report: ${r.title}`}
                title="Delete report"
                className="absolute right-2 top-2 z-10 grid h-8 w-8 place-items-center rounded-btn text-ink-3 opacity-0 transition-all hover:bg-risk-tint hover:text-risk-deep focus-visible:opacity-100 group-hover:opacity-100"
              >
                <Trash2 size={14} />
              </button>
              <button
                onClick={() => navigate(`/report/${r.id}`)}
                className="flex flex-1 flex-col text-left"
              >
                {/* `min-h` holds the card at the height it had when it carried a
                    subtitle as well. Without it, dropping that line would shrink
                    every card; with it, the spare space falls to the `mt-auto`
                    meta row and the grid keeps its rhythm. */}
                <div className="flex min-h-[168px] flex-1 flex-col p-5">
                  {/* `pr-8` keeps the second line of a long title clear of the
                      delete button, which is now over the text rather than over
                      an image band. */}
                  <div className="line-clamp-2 pr-8 text-aux font-semibold text-ink">
                    {r.title}
                  </div>

                  {/* The products the report compares. The hue is hashed from
                      the name, so a product keeps one colour everywhere it
                      appears — an identity rather than decoration. */}
                  {r.brands.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {brandChips(r.brands).map(({ name, accent }) => (
                        <span
                          key={name}
                          className={`inline-flex max-w-full items-center rounded-chip px-2 py-0.5 text-tag font-medium ${ACCENT_CHIP[accent]}`}
                        >
                          <span className="truncate">{name}</span>
                        </span>
                      ))}
                      {r.brands.length > CARD_BRANDS && (
                        <span
                          title={r.brands.slice(CARD_BRANDS).join(', ')}
                          className="inline-flex items-center rounded-chip bg-line/60 px-2 py-0.5 text-tag font-medium text-ink-3"
                        >
                          +{r.brands.length - CARD_BRANDS}
                        </span>
                      )}
                    </div>
                  )}

                  {/* One line: when, how much, who, how deep. Each item is
                      `whitespace-nowrap` so it breaks between items rather than
                      inside one, and the row may wrap at the narrowest column
                      instead of overflowing the card. */}
                  <div className="mt-auto flex flex-wrap items-center gap-x-2.5 gap-y-1 pt-3 text-tag text-ink-3">
                    <span className="inline-flex items-center gap-1 whitespace-nowrap">
                      <Clock size={11} /> {formatDate(r.created_at)}
                    </span>
                    <span className="inline-flex items-center gap-1 whitespace-nowrap">
                      <FileText size={11} /> {num(r.evidence_count)} sources
                    </span>
                    <span className="inline-flex items-center gap-1 whitespace-nowrap">
                      <Users size={11} /> {num(r.experts.length)} analysts
                    </span>
                    {r.mode && (
                      <span
                        title={`${MODE_LABEL[r.mode] ?? r.mode} research mode`}
                        className="inline-flex items-center gap-1 whitespace-nowrap text-primary-deep"
                      >
                        <Gauge size={11} /> {MODE_LABEL[r.mode] ?? r.mode}
                      </span>
                    )}
                  </div>
                </div>
              </button>
              <button
                onClick={() => navigate(`/graph/${r.id}`)}
                className="flex items-center justify-center gap-1.5 border-t border-line/60 py-2 text-tag text-ink-3 transition-colors hover:bg-primary-tint/40 hover:text-primary-deep"
              >
                <Network size={12} /> Evidence graph
              </button>
            </motion.div>
          ))}
        </motion.div>
      )}

      <VConfirm
        open={pendingDelete !== null}
        title="Delete this report?"
        message={
          <>
            <span className="font-medium text-ink">{pendingDelete?.title}</span> and
            its {num(pendingDelete?.evidence_count ?? 0)} collected sources will be
            removed permanently. This cannot be undone.
          </>
        }
        confirmLabel="Yes, delete"
        busyLabel="Deleting…"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => !deleting && setPendingDelete(null)}
      />
    </div>
  )
}
