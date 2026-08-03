import { useCallback, useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Activity, ChevronDown, ChevronUp, Cpu, Clock } from 'lucide-react'
import type { TraceSpan } from '../types'
import { useExpertStore } from '../store/expertStore'
import { stageLabel } from '../lib/labels'
import { num } from '../lib/format'

/** How tall the log stays, regardless of how many calls the run makes. */
const LOG_HEIGHT = 256

/**
 * Live log of every model call, docked at the foot of the workspace sidebar.
 *
 * The height is fixed rather than content-driven: the pipeline and team above
 * it have to stay readable however long the run gets, so the log holds its
 * footprint and scrolls internally instead of growing.
 */
export function VTracePanel({ traces }: { traces: TraceSpan[] }) {
  const byId = useExpertStore((s) => s.byId)
  const [collapsed, setCollapsed] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)

  /* Follow the tail, but only while the user is already at it — otherwise a new
     span would yank them away from whatever they scrolled back to read.
     scrollTop rather than scrollIntoView: the latter also scrolls the sidebar
     that contains this panel. */
  useEffect(() => {
    const el = scrollRef.current
    if (el && !collapsed && pinned.current) el.scrollTop = el.scrollHeight
  }, [traces.length, collapsed])

  const onScroll = useCallback(() => {
    const el = scrollRef.current
    if (el) pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
  }, [])

  const totalTokens = traces.reduce((a, s) => a + (s.total_tokens || 0), 0)

  return (
    <div className="flex shrink-0 flex-col border-t border-line">
      {/* Same treatment as the Pipeline and Team headings above it. */}
      <button
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
        className="flex shrink-0 items-center gap-1.5 px-5 py-3 text-left text-aux font-semibold text-ink"
      >
        <Activity size={15} className="shrink-0 text-primary" />
        Decision log ({traces.length})
        <span className="ml-auto text-ink-3">
          {collapsed ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </span>
      </button>

      {!collapsed && (
        <>
          <div className="flex shrink-0 items-center gap-3 border-y border-line bg-paper px-5 py-2 text-tag text-ink-3">
            <span className="flex items-center gap-1">
              <Cpu size={11} /> {num(totalTokens)} tokens
            </span>
            <span className="flex items-center gap-1">
              <Clock size={11} /> {traces.length} calls
            </span>
          </div>
          <div
            ref={scrollRef}
            onScroll={onScroll}
            style={{ height: LOG_HEIGHT }}
            className="overflow-y-auto px-3 py-2.5"
          >
            {traces.length === 0 ? (
              <p className="px-2 py-6 text-center text-aux text-ink-3">
                Waiting for the first call…
              </p>
            ) : (
              <div className="flex flex-col gap-1.5">
                <AnimatePresence initial={false}>
                  {traces.map((sp) => {
                    const ex = sp.agent_id ? byId(sp.agent_id) : undefined
                    const isOpen = expandedId === sp.span_id
                    return (
                      <motion.div
                        key={sp.span_id}
                        initial={{ opacity: 0, x: 10 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="rounded-lg border border-line bg-white px-2.5 py-2"
                      >
                        <button
                          onClick={() => setExpandedId(isOpen ? null : sp.span_id)}
                          className="flex w-full items-center gap-2 text-left"
                        >
                          <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-primary-tint text-tag font-bold text-primary-deep">
                            {sp.seq}
                          </span>
                          <span className="shrink-0 rounded-chip bg-paper px-1.5 py-0.5 text-tag text-ink-3">
                            {stageLabel(sp.stage)}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-tag text-ink-2">
                            {sp.purpose || sp.decision || 'Call'}
                          </span>
                          <span className="shrink-0 text-tag text-ink-3">
                            {(sp.latency_ms / 1000).toFixed(1)}s
                          </span>
                        </button>
                        <div className="mt-1 flex flex-wrap items-center gap-2 pl-7 text-tag text-ink-3">
                          <span className="rounded bg-ok/10 px-1 text-ok">{sp.model}</span>
                          <span>{num(sp.total_tokens)} tok</span>
                          {ex && <span>· {ex.name}</span>}
                        </div>
                        {isOpen && (
                          <div className="mt-2 space-y-1.5 border-t border-line pt-2 pl-1">
                            <div>
                              <div className="text-tag font-medium text-ink-3">Prompt</div>
                              <p className="mt-0.5 max-h-24 overflow-y-auto rounded bg-paper p-1.5 text-tag leading-relaxed text-ink-2">
                                {sp.prompt}
                              </p>
                            </div>
                            <div>
                              <div className="text-tag font-medium text-ink-3">Output</div>
                              <p className="mt-0.5 max-h-24 overflow-y-auto rounded bg-paper p-1.5 text-tag leading-relaxed text-ink-2">
                                {sp.response}
                              </p>
                            </div>
                            <div className="text-tag text-ink-3">
                              Tokens: {num(sp.prompt_tokens)} in · {num(sp.completion_tokens)} out
                              · {num(sp.total_tokens)} total
                            </div>
                          </div>
                        )}
                      </motion.div>
                    )
                  })}
                </AnimatePresence>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
