import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { FileText, Plus, Clock, Network, ShieldCheck, Trash2 } from 'lucide-react'
import { deleteReport, fetchReports } from '../lib/api'
import type { ReportCard } from '../types'
import { fadeUp, stagger } from '../lib/motion'
import { VConfirm, VEmpty, VSkeleton } from '../components/ui'
import { formatDate, num } from '../lib/format'

export default function LibraryPage() {
  const navigate = useNavigate()
  const [reports, setReports] = useState<ReportCard[]>([])
  const [loading, setLoading] = useState(true)
  const [pendingDelete, setPendingDelete] = useState<ReportCard | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    fetchReports()
      .then(setReports)
      .finally(() => setLoading(false))
  }, [])

  const confirmDelete = async () => {
    if (!pendingDelete) return
    setDeleting(true)
    const res = await deleteReport(pendingDelete.id)
    setDeleting(false)
    setPendingDelete(null)
    // Drop it locally on success rather than refetching — one less round trip,
    // and a failed delete leaves the card in place instead of silently
    // vanishing it from a list the server still has.
    if (res.ok) setReports((rs) => rs.filter((r) => r.id !== pendingDelete.id))
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
          className="inline-flex h-11 items-center gap-2 rounded-btn bg-primary px-5 font-medium text-white shadow-card transition-all hover:bg-primary-deep hover:shadow-float"
        >
          <Plus size={18} /> New research
        </button>
      </header>

      {loading ? (
        <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <VSkeleton key={i} className="h-56" />
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
              className="inline-flex h-11 items-center gap-2 rounded-btn bg-primary px-6 font-medium text-white shadow-card hover:bg-primary-deep"
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
              className="group relative flex flex-col overflow-hidden rounded-card border border-line/60 bg-card text-left shadow-card transition-all hover:-translate-y-1 hover:shadow-float"
            >
              {/* Sibling of the card's own button, not a child — nesting one
                  button inside another is invalid and swallows the click. */}
              <button
                onClick={() => setPendingDelete(r)}
                aria-label={`Delete report: ${r.title}`}
                title="Delete report"
                className="absolute right-2 top-2 z-10 grid h-8 w-8 place-items-center rounded-btn bg-ink/35 text-white backdrop-blur-sm transition-colors hover:bg-risk-deep focus-visible:bg-risk-deep"
              >
                <Trash2 size={14} />
              </button>
              <button
                onClick={() => navigate(`/report/${r.id}`)}
                className="flex flex-1 flex-col text-left"
              >
                <div className="relative h-32 overflow-hidden bg-primary-tint">
                  {r.cover_image && (
                    <img
                      src={r.cover_image}
                      alt=""
                      className="h-full w-full object-cover transition-transform group-hover:scale-105"
                    />
                  )}
                  <div className="absolute inset-0 bg-gradient-to-t from-ink/40 to-transparent" />
                </div>
                <div className="flex flex-1 flex-col p-4">
                  <div className="line-clamp-2 text-aux font-semibold text-ink">
                    {r.title}
                  </div>
                  <p className="mt-1 line-clamp-2 text-tag text-ink-3">{r.subtitle}</p>
                  <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 pt-3 text-tag text-ink-3">
                    <span className="inline-flex items-center gap-1">
                      <Clock size={12} /> {formatDate(r.created_at)}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <FileText size={12} /> {num(r.evidence_count)} sources
                    </span>
                    <span className="inline-flex items-center gap-1 text-primary-deep">
                      <ShieldCheck size={12} /> {num(r.high_conf_count)} high confidence
                    </span>
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
