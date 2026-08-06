import { useEffect } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Compass,
  ChevronLeft,
  Users,
  Activity,
  FileText,
  RotateCcw,
  Sparkles,
  CheckCircle2,
  WifiOff,
  Loader2,
} from 'lucide-react'
import { useTaskStream } from '../hooks/useTaskStream'
import { useTaskStore } from '../store/taskStore'
import { useExpertStore } from '../store/expertStore'
import { VFlowDag } from '../components/VFlowDag'
import { VAgentStream } from '../components/VAgentStream'
import { VEvidenceFeed } from '../components/VEvidenceFeed'
import { VTracePanel } from '../components/VTracePanel'
import { VAvatar } from '../components/VAvatar'
import { VLogo } from '../components/VLogo'
import { VCountUp } from '../components/ui'
import { plural } from '../lib/format'
import { ACCENT_TEXT } from '../lib/accents'

export default function WorkspacePage() {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const { state } = useLocation() as { state: { query?: string } | null }
  const query = state?.query ?? ''

  useTaskStream(taskId, query)

  const {
    nodes,
    thoughts,
    evidences,
    images,
    messages,
    progress,
    teamMembers,
    traces,
    reportId,
    finished,
    error,
    streamStatus,
  } = useTaskStore()
  const byId = useExpertStore((s) => s.byId)

  const reworkMsg = messages.find((m) => m.kind === 'rework')

  useEffect(() => {
    if (finished && reportId) {
      const t = setTimeout(() => navigate(`/report/${reportId}`), 1600)
      return () => clearTimeout(t)
    }
  }, [finished, reportId, navigate])

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-bg">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-card/80 px-5 backdrop-blur">
        <button
          onClick={() => navigate('/')}
          className="grid h-9 w-9 shrink-0 place-items-center rounded-btn text-ink-2 transition-colors hover:bg-primary-tint hover:text-primary-deep"
          aria-label="Back"
        >
          <ChevronLeft size={20} />
        </button>
        <VLogo size={32} alt="Vantage" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-aux font-medium text-ink">
            {query || 'Competitive research'}
          </div>
          <div className="truncate text-tag text-ink-3">Task {taskId}</div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <div className="hidden items-center gap-1.5 text-tag text-ink-2 sm:flex">
            <FileText size={13} /> <VCountUp value={progress.evidence_count} /> sources
          </div>
          <div className="flex w-40 items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded-chip bg-line">
              <motion.div
                className="h-full rounded-chip bg-primary"
                animate={{ width: `${progress.percent}%` }}
                transition={{ duration: 0.4 }}
              />
            </div>
            <span className="text-tag font-medium text-primary-deep">
              {progress.percent}%
            </span>
          </div>
        </div>
      </header>

      {streamStatus === 'reconnecting' && (
        <div className="flex items-center gap-2 bg-warn/10 px-5 py-2 text-aux text-warn-deep">
          <Loader2 size={14} className="animate-spin" /> Connection dropped —
          reconnecting…
        </div>
      )}
      {streamStatus === 'closed' && !finished && !error && (
        <div className="flex items-center gap-2 bg-risk/10 px-5 py-2 text-aux text-risk-deep">
          <WifiOff size={14} /> Disconnected from the research stream. The run may
          still be finishing — check My reports in a moment.
        </div>
      )}
      {error && (
        <div className="bg-risk/10 px-5 py-2 text-aux text-risk-deep">{error}</div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[300px_1fr_360px]">
        {/* Pipeline and team take whatever height they need and scroll only if
            the viewport is too short; the decision log below them is fixed. */}
        <aside className="hidden min-h-0 flex-col border-r border-line bg-card/40 lg:flex">
          <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-5">
            <div>
              <div className="mb-3 flex items-center gap-1.5 text-aux font-semibold text-ink">
                <Activity size={15} className={ACCENT_TEXT.blue} /> Pipeline
              </div>
              <VFlowDag nodes={nodes} />
            </div>

            <div>
              <div className="mb-2 flex items-center gap-1.5 text-aux font-semibold text-ink">
                <Users size={15} className={ACCENT_TEXT.violet} /> Team ({teamMembers.length})
              </div>
              <div className="flex flex-wrap gap-1.5">
                {teamMembers.map((id) => {
                  const ex = byId(id)
                  if (!ex) return null
                  return (
                    <VAvatar
                      key={id}
                      expert={ex}
                      size={32}
                      title={`${ex.name} · ${ex.role_title}`}
                      className="border border-card shadow-card"
                    />
                  )
                })}
              </div>
            </div>
          </div>

          <VTracePanel traces={traces} />
        </aside>

        <section className="flex min-h-0 flex-col">
          <div className="flex items-center gap-1.5 border-b border-line px-6 py-3 text-aux font-semibold text-ink">
            {/* Breathes only while the stream is open, so the header carries
                the same signal as the pipeline dots: this is still running. */}
            <Sparkles
              size={15}
              className={`text-primary ${finished ? '' : 'animate-breath'}`}
            />{' '}
            Live reasoning
            {progress.queued ? (
              <span className="ml-auto text-tag font-normal text-ink-3">
                {progress.queued} section(s) queued on the model's rate limit
              </span>
            ) : null}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
            {thoughts.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-ink-3">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 3, ease: 'linear' }}
                >
                  <Compass size={32} className="text-primary-soft" />
                </motion.div>
                <p className="text-aux">Assembling the team…</p>
              </div>
            ) : (
              <VAgentStream thoughts={thoughts} />
            )}

            <AnimatePresence>
              {reworkMsg && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="mt-4 rounded-card border border-warn/40 bg-sun-soft p-4"
                >
                  <div className="flex items-center gap-1.5 text-aux font-semibold text-warn-deep">
                    <RotateCcw size={14} /> Sent back for rework
                  </div>
                  <p className="mt-1 text-tag text-ink-2">{reworkMsg.reason}</p>
                  {reworkMsg.diff && (
                    <div className="mt-2 space-y-1.5 text-tag">
                      <div className="rounded-btn bg-risk/10 px-3 py-1.5 text-ink-2 line-through decoration-risk/50">
                        {reworkMsg.diff.before}
                      </div>
                      <div className="rounded-btn bg-ok/10 px-3 py-1.5 text-ink">
                        {reworkMsg.diff.after}
                      </div>
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>

            <AnimatePresence>
              {finished && reportId && (
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-5 flex flex-wrap items-center gap-3 rounded-card border border-primary-soft bg-primary-tint p-4"
                >
                  <CheckCircle2 size={22} className="text-primary" />
                  <div className="min-w-0 flex-1">
                    <div className="text-aux font-semibold text-ink">
                      Report ready — opening it now
                    </div>
                    <div className="text-tag text-ink-2">
                      If it does not open automatically, use the button.
                    </div>
                  </div>
                  <button
                    onClick={() => navigate(`/report/${reportId}`)}
                    className="h-9 rounded-btn bg-primary-deep px-4 text-aux font-medium text-white hover:bg-primary-deeper"
                  >
                    Open report
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </section>

        <aside className="hidden min-h-0 flex-col border-l border-line bg-card/40 lg:flex">
          <div className="flex items-center gap-1.5 border-b border-line px-5 py-3 text-aux font-semibold text-ink">
            <FileText size={15} className={ACCENT_TEXT.pink} /> Evidence (
            {evidences.length})
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {images.length > 0 && (
              <div className="mb-4 grid grid-cols-3 gap-1.5">
                {images.slice(0, 6).map((im, i) => (
                  <img
                    key={`${im.src}-${i}`}
                    src={im.src}
                    alt={im.alt ?? ''}
                    className="aspect-square w-full rounded-btn border border-line object-cover"
                    onError={(e) =>
                      ((e.target as HTMLImageElement).style.display = 'none')
                    }
                  />
                ))}
              </div>
            )}
            <VEvidenceFeed evidences={evidences} />
          </div>
        </aside>
      </div>

      <span className="sr-only">
        {plural(evidences.length, 'source')} collected so far
      </span>
    </div>
  )
}
