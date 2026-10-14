import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'
import type { ClarificationAction, ClarificationStage, ScopeAnswer, TaskDetail } from '../types'
import { fetchTask, submitClarify, submitScope } from '../lib/api'
import { clarificationAnswers, mergeProductInput, questionOptionGroups, readDraft, saveDraft } from '../lib/clarification'
import { VSunGlow } from '../components/ui'
import { VLogo } from '../components/VLogo'
import { fadeUp } from '../lib/motion'

const TITLES: Record<ClarificationStage, string> = {
  scope: 'Let’s confirm the research topic', products: 'Choose the products to research',
  market: 'Choose your market', clarify: 'A question to focus the research', ready: 'Ready to research',
}

export default function ClarifyPage() {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [task, setTask] = useState<TaskDetail | null>(null)
  const [answers, setAnswers] = useState<Record<string, unknown>>({})
  const [text, setText] = useState('')
  const [scopeChoice, setScopeChoice] = useState<ScopeAnswer | ''>('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const busy = useRef(false)
  const input = useRef<HTMLTextAreaElement>(null)

  const applyTask = useCallback((next: TaskDetail) => {
    const draft = readDraft(next)
    const restored = clarificationAnswers(next.clarifyQuestions, next.answers)
    const question = next.clarifyQuestions[0]
    if (question && next.questionDraft?.selected) {
      restored[question.id] = question.type === 'multi' ? next.questionDraft.selected : next.questionDraft.selected[0] ?? ''
    }
    setTask(next)
    setAnswers({ ...restored, ...draft.answers })
    setText(draft.text ?? next.questionDraft?.text ?? '')
    setScopeChoice('')
    setError('')
  }, [])

  useEffect(() => {
    if (!taskId) return
    let disposed = false
    void fetchTask(taskId).then((next) => {
      if (disposed) return
      setLoading(false)
      if (!next) { setError('Could not load this task. Check the backend and retry.'); return }
      if (next.status === 'done' && next.reportId) navigate(`/report/${next.reportId}`, { replace: true })
      else if (!['created', 'clarified'].includes(next.status)) navigate(`/workspace/${taskId}`, { replace: true })
      else applyTask(next)
    })
    return () => { disposed = true }
  }, [taskId, location.key, navigate, applyTask])

  useEffect(() => {
    if (task) saveDraft(task, answers, text)
  }, [task, answers, text])

  useLayoutEffect(() => {
    if (!input.current) return
    input.current.style.height = 'auto'
    input.current.style.height = `${Math.max(36, Math.min(input.current.scrollHeight, 160))}px`
  }, [text, task?.clarificationStage, task?.clarificationRevision])

  async function respondToScope(answer: ScopeAnswer) {
    if (!task || busy.current) return
    if (answer === 'yes' && text.trim()) return
    if (answer !== 'yes' && !text.trim()) { input.current?.focus(); return }
    busy.current = true
    setSubmitting(true)
    setError('')
    try {
      const result = await submitScope(task.taskId, answer, task.scopeRevision, text.trim())
      if (result.ok) applyTask(result)
      else setError(result.message)
    } finally { busy.current = false; setSubmitting(false) }
  }

  async function advance(action: ClarificationAction = 'answer') {
    if (!task || busy.current) return
    busy.current = true
    setSubmitting(true)
    setError('')
    const question = task.clarifyQuestions[0]
    const currentAnswers = question ? { [question.id]: answers[question.id] ?? (question.type === 'multi' ? [] : '') } : {}
    try {
      const result = await submitClarify(task.taskId, currentAnswers, {
        action, clarificationRevision: task.clarificationRevision, text: action === 'products' || action === 'retry' ? '' : text,
      })
      if (!result.ok) { setError(result.message ?? 'Could not save your answer. Retry.'); return }
      applyTask(result)
      if (action === 'start' && result.researchReady) navigate(`/workspace/${task.taskId}`, { state: { query: task.query } })
    } finally { busy.current = false; setSubmitting(false) }
  }

  function select(value: string) {
    const question = task?.clarifyQuestions[0]
    if (!question) return
    if (question.id === 'scope') {
      const choice: ScopeAnswer = value.startsWith('Yes') ? 'yes' : value.startsWith('Roughly') ? 'roughly' : 'no'
      setScopeChoice(choice)
      if (choice === 'yes') void respondToScope('yes')
      else input.current?.focus()
      return
    }
    setAnswers((prev) => {
      if (question.type !== 'multi') return { ...prev, [question.id]: prev[question.id] === value ? '' : value }
      const selected = (prev[question.id] as string[]) ?? []
      return { ...prev, [question.id]: selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value] }
    })
  }

  function addProducts() {
    setAnswers((prev) => ({ ...prev, products: mergeProductInput((prev.products as string[]) ?? [], text) }))
    setText('')
  }

  if (loading) return <div className="p-8 text-ink-2">Loading task…</div>
  if (!task) return <div role="alert" className="p-8 text-risk-deep">{error}</div>
  const stage = task.clarificationStage
  const question = task.clarifyQuestions[0]
  const selected = question?.type === 'multi' ? ((answers[question.id] as string[]) ?? []) : []
  const hasAnswer = Boolean(text.trim() || (question && (question.type === 'multi' ? selected.length : answers[question.id])))
  const canContinue = stage === 'products'
    ? mergeProductInput((answers.products as string[]) ?? [], text).length > 0
    : stage === 'market' || hasAnswer
  const fieldLabel = stage === 'scope' ? 'Describe a correction'
    : stage === 'products' ? 'Add another product' : 'Your answer or additional details'
  const contextLabels: Record<string, string> = {
    purpose: 'Research goal', audience: 'Target users', perspective: 'Decision perspective',
    focus: 'Research priorities', constraints: 'Constraints', freshness: 'Evidence recency',
  }
  const recencyLabels: Record<string, string> = {
    day: 'Last 24 hours', week: 'Last week', month: 'Last month', year: 'Last year', any: 'No time limit',
  }

  return <div className="relative min-h-screen overflow-y-auto bg-bg">
    <VSunGlow className="opacity-40" />
    <div className="relative z-10 mx-auto flex min-h-screen max-w-[720px] flex-col justify-center px-6 py-16">
      <motion.div variants={fadeUp} initial="initial" animate="animate" className="flex items-center gap-2.5">
        <VLogo size={40} alt="Vantage" />
        <div>
          <div className="text-h3 text-ink">{TITLES[stage]}</div>
          <div className="text-aux text-ink-2">
            {stage === 'scope' ? 'Confirm our understanding before choosing products and research preferences.'
              : stage === 'clarify' ? 'We only ask for missing information that could change the research.'
                : 'Your confirmed answers guide the searches, analysis and recommendations.'}
          </div>
        </div>
      </motion.div>
      <div className="mt-5 rounded-card border border-line/60 bg-card p-4 text-aux text-ink-2 shadow-card">
        <span className="text-tag text-ink-3">Your request</span>
        <p className="mt-1 text-body text-ink">{task.query}</p>
      </div>
      {stage !== 'scope' && <div className="mt-4 rounded-card border border-line/60 bg-card p-4 text-aux text-ink-2">
        <span className="text-tag text-ink-3">Confirmed understanding</span>
        <p className="mt-1 text-body text-ink">{task.researchBrief}</p>
        {stage !== 'products' && <p className="mt-2">Products: {(task.answers.products as string[] ?? []).join(', ')}</p>}
        {task.canStartResearch && <p className="mt-1">Market: {String(task.answers.market ?? 'No preference')}{task.answers.market_notes ? ` — ${task.answers.market_notes}` : ''}</p>}
      </div>}
      {task.productChangeRequested && <p role="status" className="mt-4 text-aux text-ink-2">
        Your answer changes the products. Confirm the updated selections before we continue.
      </p>}
      {question && <div key={`${stage}:${task.scopeRevision}:${task.clarificationRevision}`}
        className="mt-6 rounded-card border border-line/60 bg-card p-5 shadow-card">
        <p className="text-body font-medium text-ink">{question.question}</p>
        {question.hint && <p className="mt-1 text-tag text-ink-3">{question.hint}</p>}
        <div className="mt-3 flex flex-col gap-3">
          {questionOptionGroups(question, selected).map((group) => <div key={group.label}>
            {group.label && <p className="mb-2 text-tag text-ink-2">{group.label}</p>}
            <div className="flex flex-wrap gap-2">{group.options.map((option) => {
              const choice = option.startsWith('Yes') ? 'yes' : option.startsWith('Roughly') ? 'roughly' : 'no'
              const pressed = stage === 'scope' ? scopeChoice === choice
                : question.type === 'multi' ? selected.includes(option) : answers[question.id] === option
              return <button key={option} type="button" aria-pressed={pressed}
                disabled={submitting || (stage === 'scope' && choice === 'yes' && Boolean(text.trim()))}
                onClick={() => select(option)}
                className={`min-h-9 rounded-chip px-4 py-2 text-aux font-medium transition-all disabled:opacity-50 ${pressed
                  ? 'bg-primary-deep text-white shadow-card' : 'bg-primary-tint text-primary-deep hover:bg-primary-soft/40'}`}>
                {option}
              </button>
            })}</div>
          </div>)}
        </div>
        <form className="mt-4" onSubmit={(event) => {
          event.preventDefault()
          if (stage === 'scope') void respondToScope(scopeChoice === 'no' ? 'no' : 'roughly')
          else if (stage === 'products') addProducts()
          else void advance()
        }}>
          <label htmlFor="clarification-text" className="text-aux text-ink-2">{fieldLabel}</label>
          <textarea id="clarification-text" ref={input} rows={1} maxLength={4000} disabled={submitting}
            value={text} onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (stage === 'products' && event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); addProducts() }
            }}
            placeholder={stage === 'products' ? 'Product names, separated by commas'
              : stage === 'scope' ? 'Describe what needs correcting'
                : 'Write your answer or add details'}
            className="mt-2 w-full resize-none overflow-y-auto rounded-btn border border-line bg-bg px-3 py-2 text-aux text-ink outline-none focus:border-primary"
          />
          {stage === 'scope' && <button type="submit" disabled={submitting || !text.trim()}
            className="mt-2 rounded-btn bg-primary-deep px-4 py-2 text-aux font-medium text-white disabled:opacity-50">
            {submitting ? 'Updating our understanding…' : 'Submit correction'}
          </button>}
          {stage === 'products' && <button type="submit" disabled={submitting || !text.trim()}
            className="mt-2 rounded-btn bg-primary-deep px-4 py-2 text-aux font-medium text-white disabled:opacity-50">Add</button>}
        </form>
      </div>}
      {stage === 'ready' && <div className="mt-6 rounded-card border border-line/60 bg-card p-5 shadow-card">
        <p className="text-body font-medium text-ink">We have enough information to begin.</p>
        <p className="mt-1 text-aux text-ink-2">The confirmed brief and your answers will guide every research stage.</p>
        {Object.entries(contextLabels).map(([key, label]) => {
          const value = task.researchContext[key]
          return value && (Array.isArray(value) ? value.length > 0 : true)
            ? <p key={key} className="mt-2 text-aux text-ink-2"><span className="font-medium">{label}:</span> {Array.isArray(value)
              ? value.join(', ') : key === 'freshness' ? recencyLabels[String(value)] ?? String(value) : String(value)}</p>
            : null
        })}
      </div>}
      {(error || task.clarificationError) && <div role="alert" className="mt-4 text-aux text-risk-deep">
        {error || task.clarificationError}
        {task.clarificationError && <button type="button" disabled={submitting} onClick={() => void advance('retry')}
          className="ml-2 underline">Retry question generation</button>}
      </div>}
      {stage !== 'scope' && <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        {(stage === 'clarify' || stage === 'ready') && <button type="button" disabled={submitting}
          onClick={() => void advance('products')} className="text-aux text-ink-2 underline">Change products</button>}
        {stage !== 'ready' && question && <button type="button" disabled={submitting || !canContinue}
          onClick={() => void advance()} className="ml-auto inline-flex min-h-11 items-center gap-2 rounded-btn bg-primary-deep px-5 py-2 font-medium text-white disabled:opacity-50">
          {submitting ? 'Saving your answer…' : stage === 'products' ? 'Confirm products'
            : stage === 'market' ? 'Confirm market' : 'Submit answer'}<ArrowRight size={17} />
        </button>}
        {task.canStartResearch && <button type="button" disabled={submitting} onClick={() => void advance('start')}
          className="inline-flex min-h-11 items-center gap-2 rounded-btn bg-primary-deep px-5 py-2 font-medium text-white disabled:opacity-50">
          {stage === 'ready' ? 'Start research' : 'Start with current information'}<ArrowRight size={17} />
        </button>}
      </div>}
    </div>
  </div>
}
