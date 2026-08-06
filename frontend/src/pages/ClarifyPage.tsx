import { useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, SkipForward } from 'lucide-react'
import type { ClarifyQuestion } from '../types'
import { submitClarify } from '../lib/api'
import { VSunGlow } from '../components/ui'
import { VLogo } from '../components/VLogo'
import { fadeUp, stagger } from '../lib/motion'

interface NavState {
  query?: string
  clarify?: ClarifyQuestion[]
}

export default function ClarifyPage() {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const { state } = useLocation() as { state: NavState | null }
  const query = state?.query ?? ''
  const questions = state?.clarify ?? []
  const [answers, setAnswers] = useState<Record<string, unknown>>({})
  const [submitting, setSubmitting] = useState(false)
  const [customInputs, setCustomInputs] = useState<Record<string, string>>({})

  // Landing here directly (e.g. a refresh) means there is nothing to clarify.
  if (!taskId || questions.length === 0) {
    navigate(`/workspace/${taskId}`, { replace: true, state: { query } })
    return null
  }

  function setSingle(qid: string, val: string) {
    setAnswers((a) => ({ ...a, [qid]: val }))
  }

  function toggleMulti(qid: string, val: string) {
    setAnswers((a) => {
      const cur = (a[qid] as string[]) ?? []
      return {
        ...a,
        [qid]: cur.includes(val) ? cur.filter((v) => v !== val) : [...cur, val],
      }
    })
  }

  /** Add competitors the discovery step missed. Accepts a comma-separated list. */
  function addCustom(qid: string) {
    const raw = (customInputs[qid] ?? '').trim()
    if (!raw) return
    const items = raw
      .split(/[,;]+/)
      .map((s) => s.trim())
      .filter(Boolean)
    setAnswers((a) => {
      const cur = (a[qid] as string[]) ?? []
      const merged = [...cur]
      for (const it of items) if (!merged.includes(it)) merged.push(it)
      return { ...a, [qid]: merged }
    })
    setCustomInputs((c) => ({ ...c, [qid]: '' }))
  }

  async function go() {
    if (submitting || !taskId) return
    setSubmitting(true)
    try {
      await submitClarify(taskId, answers)
    } finally {
      navigate(`/workspace/${taskId}`, { state: { query } })
    }
  }

  return (
    <div className="relative min-h-screen overflow-y-auto bg-bg">
      <VSunGlow className="opacity-40" />
      <div className="relative z-10 mx-auto flex min-h-screen max-w-[720px] flex-col justify-center px-6 py-16">
        <motion.div
          variants={fadeUp}
          initial="initial"
          animate="animate"
          className="flex items-center gap-2.5"
        >
          <VLogo size={40} alt="Vantage" />
          <div>
            <div className="text-h3 text-ink">A few questions before we start</div>
            <div className="text-aux text-ink-2">
              These narrow the scope so the team researches the right thing.
            </div>
          </div>
        </motion.div>

        {query && (
          <motion.div
            variants={fadeUp}
            initial="initial"
            animate="animate"
            className="mt-5 rounded-card border border-line/60 bg-card p-4 text-aux text-ink-2 shadow-card"
          >
            <span className="text-tag text-ink-3">Your request</span>
            <p className="mt-1 text-body text-ink">{query}</p>
          </motion.div>
        )}

        <motion.div
          variants={stagger}
          initial="initial"
          animate="animate"
          className="mt-6 flex flex-col gap-5"
        >
          {questions.map((q) => (
            <motion.div
              key={q.id}
              variants={fadeUp}
              className="rounded-card border border-line/60 bg-card p-5 shadow-card"
            >
              <p className="text-body font-medium text-ink">{q.question}</p>
              {q.hint && <p className="mt-1 text-tag text-ink-3">{q.hint}</p>}

              {q.type === 'text' ? (
                <textarea
                  rows={2}
                  value={(answers[q.id] as string) ?? ''}
                  onChange={(e) => setSingle(q.id, e.target.value)}
                  placeholder="Optional — anything else we should know"
                  className="mt-3 w-full resize-none rounded-btn border border-line bg-bg px-3 py-2 text-aux text-ink outline-none transition-all focus:border-primary focus:shadow-glow"
                />
              ) : (
                <div className="mt-3 flex flex-wrap gap-2">
                  {Array.from(
                    new Set([
                      ...(q.options ?? []),
                      ...(q.type === 'multi' ? ((answers[q.id] as string[]) ?? []) : []),
                    ]),
                  ).map((opt) => {
                    const selected =
                      q.type === 'multi'
                        ? ((answers[q.id] as string[]) ?? []).includes(opt)
                        : answers[q.id] === opt
                    return (
                      <button
                        key={opt}
                        onClick={() =>
                          q.type === 'multi' ? toggleMulti(q.id, opt) : setSingle(q.id, opt)
                        }
                        className={`h-9 rounded-chip px-4 text-aux font-medium transition-all ${
                          selected
                            ? 'bg-primary-deep text-white shadow-card'
                            : 'bg-primary-tint text-primary-deep hover:bg-primary-soft/40'
                        }`}
                      >
                        {opt}
                      </button>
                    )
                  })}
                </div>
              )}

              {q.id === 'competitors' && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <input
                    value={customInputs[q.id] ?? ''}
                    onChange={(e) =>
                      setCustomInputs((c) => ({ ...c, [q.id]: e.target.value }))
                    }
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addCustom(q.id)
                      }
                    }}
                    placeholder="Add a competitor we missed — press Enter (comma-separate several)"
                    className="h-9 min-w-[240px] flex-1 rounded-btn border border-line bg-bg px-3 text-aux text-ink outline-none transition-all focus:border-primary focus:shadow-glow"
                  />
                  <button
                    onClick={() => addCustom(q.id)}
                    className="h-9 shrink-0 rounded-btn bg-primary-deep px-4 text-aux font-medium text-white hover:bg-primary-deeper"
                  >
                    Add
                  </button>
                </div>
              )}
            </motion.div>
          ))}
        </motion.div>

        <div className="mt-7 flex flex-wrap items-center justify-between gap-3">
          <button
            onClick={go}
            className="inline-flex items-center gap-1.5 text-aux text-ink-3 transition-colors hover:text-ink-2"
          >
            <SkipForward size={15} /> Skip and start now
          </button>
          <button
            onClick={go}
            disabled={submitting}
            className="inline-flex h-12 items-center justify-center gap-2 rounded-btn bg-primary-deep px-6 font-medium text-white shadow-card transition-all hover:bg-primary-deeper hover:shadow-float active:scale-95 disabled:opacity-50"
          >
            {submitting ? 'Assembling the team…' : 'Start research'}
            <ArrowRight size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
