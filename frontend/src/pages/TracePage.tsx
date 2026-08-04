import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, Cpu, Clock, Filter } from 'lucide-react'
import type { TraceSpan } from '../types'
import { fetchReportTrace } from '../lib/api'
import { useExpertStore } from '../store/expertStore'
import { VAvatar } from '../components/VAvatar'
import { VFilterChip } from '../components/ui'
import { stageLabel } from '../lib/labels'
import { num } from '../lib/format'

const STAGES = [
  'all',
  'intake',
  'orchestrator',
  'collect',
  'analyze',
  'write',
  'audit',
  'verify',
  'done',
]

/** Full call chain for a report: prompt, output, tokens and decision per step. */
export default function TracePage() {
  const { reportId } = useParams()
  const navigate = useNavigate()
  const byId = useExpertStore((s) => s.byId)
  const [spans, setSpans] = useState<TraceSpan[]>([])
  const [filter, setFilter] = useState('all')
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    if (reportId) fetchReportTrace(reportId).then((r) => setSpans(r.spans || []))
  }, [reportId])

  const filtered = filter === 'all' ? spans : spans.filter((s) => s.stage === filter)
  const totalTokens = spans.reduce((a, s) => a + (s.total_tokens || 0), 0)
  const totalMs = spans.reduce((a, s) => a + (s.latency_ms || 0), 0)

  const stageCounts = STAGES.reduce<Record<string, number>>((acc, s) => {
    acc[s] = s === 'all' ? spans.length : spans.filter((x) => x.stage === s).length
    return acc
  }, {})

  return (
    <div className="min-h-screen w-screen bg-bg">
      <header className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b border-line bg-card/80 px-5 backdrop-blur">
        <button
          onClick={() => navigate(`/report/${reportId}`)}
          className="grid h-9 w-9 shrink-0 place-items-center rounded-btn text-ink-2 hover:bg-primary-tint"
          aria-label="Back to report"
        >
          <ChevronLeft size={20} />
        </button>
        <div className="min-w-0 flex-1">
          <div className="text-aux font-semibold text-ink">Decision trace</div>
          <div className="truncate text-tag text-ink-3">
            Every model call — its prompt, output, token cost and decision
          </div>
        </div>
        <div className="hidden shrink-0 items-center gap-3 text-tag text-ink-2 sm:flex">
          <span className="inline-flex items-center gap-1">
            <Cpu size={13} /> {num(totalTokens)} tokens
          </span>
          <span className="inline-flex items-center gap-1">
            <Clock size={13} /> {(totalMs / 1000).toFixed(1)}s · {spans.length} steps
          </span>
        </div>
      </header>

      <div className="mx-auto max-w-4xl px-6 py-6">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Filter size={14} className="text-ink-3" />
          {STAGES.filter((s) => s === 'all' || stageCounts[s] > 0).map((s) => (
            <VFilterChip
              key={s}
              active={filter === s}
              onClick={() => setFilter(s)}
              count={stageCounts[s]}
            >
              {s === 'all' ? 'All' : stageLabel(s)}
            </VFilterChip>
          ))}
        </div>

        {filtered.length === 0 ? (
          <p className="py-16 text-center text-aux text-ink-3">
            No trace data for this report.
          </p>
        ) : (
          <div className="relative space-y-3 border-l-2 border-line pl-6">
            {filtered.map((sp) => {
              const ex = sp.agent_id ? byId(sp.agent_id) : undefined
              const isOpen = expanded === sp.span_id
              return (
                <div key={sp.span_id} className="relative">
                  <span className="absolute -left-[31px] top-3 grid h-5 w-5 place-items-center rounded-full bg-primary text-tag font-bold text-white">
                    {sp.seq}
                  </span>
                  <div className="rounded-card border border-line bg-white p-4">
                    <button
                      onClick={() => setExpanded(isOpen ? null : sp.span_id)}
                      className="flex w-full items-center gap-2 text-left"
                    >
                      {ex && <VAvatar expert={ex} size={28} />}
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="rounded-chip bg-primary-tint px-2 py-0.5 text-tag font-medium text-primary-deep">
                            {stageLabel(sp.stage)}
                          </span>
                          <span className="text-tag text-ink-3">
                            {ex?.name || sp.agent_id}
                          </span>
                        </div>
                        <div className="mt-0.5 text-aux font-medium text-ink">
                          {sp.purpose || sp.decision}
                        </div>
                      </div>
                      <div className="shrink-0 text-right text-tag text-ink-3">
                        <div className="truncate rounded bg-ok/10 px-1.5 text-ok">
                          {sp.model}
                        </div>
                        <div className="mt-0.5">
                          {num(sp.total_tokens)} tok · {(sp.latency_ms / 1000).toFixed(1)}s
                        </div>
                      </div>
                    </button>
                    {isOpen && (
                      <div className="mt-3 space-y-2 border-t border-line pt-3 text-tag">
                        <div>
                          <div className="font-medium text-ink-3">Prompt</div>
                          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-paper p-2 leading-relaxed text-ink-2">
                            {sp.prompt}
                          </pre>
                        </div>
                        <div>
                          <div className="font-medium text-ink-3">Output</div>
                          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-paper p-2 leading-relaxed text-ink-2">
                            {sp.response}
                          </pre>
                        </div>
                        <div className="flex flex-wrap gap-4 text-ink-3">
                          <span>{num(sp.prompt_tokens)} tok in</span>
                          <span>{num(sp.completion_tokens)} tok out</span>
                          <span>{num(sp.total_tokens)} tok total</span>
                          <span>{(sp.latency_ms / 1000).toFixed(2)}s</span>
                        </div>
                        {sp.evidence_ids && sp.evidence_ids.length > 0 && (
                          <div className="break-all text-ink-3">
                            Linked evidence: {sp.evidence_ids.join(', ')}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
