import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowUp,
  Sparkles,
  ShieldCheck,
  Layers,
  TrendingUp,
  Zap,
  Gem,
  Crown,
  CreditCard,
} from 'lucide-react'
import { VSunGlow } from '../components/ui'
import { VAvatar } from '../components/VAvatar'
import { VLogo } from '../components/VLogo'
import { fadeUp, stagger } from '../lib/motion'
import { useExpertStore } from '../store/expertStore'
import { createTask } from '../lib/api'
import { ACCENT_WELL, type Accent } from '../lib/accents'

const MODE_OPTIONS = [
  { key: 'quick', icon: Zap, label: 'Quick', desc: '5 sections · a few minutes' },
  { key: 'deep', icon: Gem, label: 'Deep', desc: '9 sections · includes a rework pass' },
  {
    key: 'expert',
    icon: Crown,
    label: 'Expert',
    desc: '12+ sections · deepest, with contrarian analysis',
  },
]

// One accent each, so the four entry points read as four different kinds of
// question rather than as one card repeated.
const EXAMPLES: {
  icon: typeof Layers
  accent: Accent
  title: string
  desc: string
  q: string
}[] = [
  {
    icon: Layers,
    accent: 'blue',
    title: 'Feature benchmark',
    desc: 'Compare Notion, Obsidian and Craft head to head',
    q: 'Compare Notion, Obsidian and Craft on features and pricing for research teams',
  },
  {
    icon: CreditCard,
    accent: 'violet',
    title: 'Pricing teardown',
    desc: 'How Figma, Sketch and Framer package and price',
    q: 'Analyze how Figma, Sketch and Framer structure their pricing and packaging',
  },
  {
    icon: ShieldCheck,
    accent: 'orchid',
    title: 'SWOT analysis',
    desc: 'Structured SWOT across Slack, Teams and Discord',
    q: 'Build a structured SWOT comparison of Slack, Microsoft Teams and Discord',
  },
  {
    icon: TrendingUp,
    accent: 'pink',
    title: 'Market trends',
    desc: 'Where the AI coding assistant market is heading',
    q: 'What are the key trends and leading players in the AI coding assistant market in 2026?',
  },
]

// The avatar wall and its "Meet all N analysts" link at the foot of the page.
// Off for now — flip to `true` to bring the row back; nothing else changes.
const SHOW_ANALYST_WALL = false

export default function HomePage() {
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [mode, setMode] = useState('deep')
  const [submitting, setSubmitting] = useState(false)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const experts = useExpertStore((s) => s.experts)
  const wall = experts.slice(0, 14)
  // Read from the roster, not written in: the copy stays true as the team grows,
  // and reads without a number for the frame before the roster loads.
  const teamSize = experts.length

  /** An example is a starting point, not a command: it loads the question into
   *  the box and hands over the caret. Nothing is sent until the reader sends
   *  it — most of these want a name or a market swapped out first. */
  function fillExample(q: string) {
    setText(q)
    const ta = taRef.current
    if (!ta) return
    ta.focus() // also scrolls the box back into view from the cards below
    // Next frame, so the caret lands after the text React is about to write in
    // rather than at the end of whatever the box held before.
    requestAnimationFrame(() => ta.setSelectionRange(q.length, q.length))
  }

  async function submit(q: string) {
    const query = q.trim()
    if (!query || submitting) return
    setSubmitting(true)
    try {
      const resp = await createTask(query, mode)
      if (!resp.taskId) return // the toast already reported the failure
      if (resp.needClarify)
        navigate(`/clarify/${resp.taskId}`, {
          state: { query, clarify: resp.clarifyQuestions },
        })
      else navigate(`/workspace/${resp.taskId}`, { state: { query } })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="relative min-h-full overflow-hidden">
      <VSunGlow className="opacity-40" />

      <div className="relative z-10 flex items-center justify-end px-8 pt-6">
        <span className="inline-flex h-9 items-center gap-1.5 rounded-chip border border-line bg-card/80 px-3 text-aux text-ink-2 backdrop-blur">
          <Sparkles size={14} className="text-primary" /> Every claim carries its source
        </span>
      </div>

      <div className="relative z-10 mx-auto flex min-h-[calc(100vh-80px)] max-w-[860px] flex-col items-center justify-center px-6 pb-20">
        <motion.h1
          variants={fadeUp}
          initial="initial"
          animate="animate"
          className="text-center font-serif text-[44px] leading-tight text-ink"
        >
          What are we researching?
          <span className="ml-2 inline-block align-middle">
            <VLogo size={42} className="inline" />
          </span>
        </motion.h1>
        <motion.p
          variants={fadeUp}
          initial="initial"
          animate="animate"
          className="mt-3 text-center text-lg text-ink-2"
        >
          {/* {teamSize > 0 ? `A team of ${teamSize} analysts` : 'A team of analysts'}{' '}
          researches the market, cross-checks every source, and writes a report you
          can audit line by line. */}
          {/* Analysts research the market, verify every source, and write an auditable report. */}
          live web research · cross-validated · no claim without evidence
        </motion.p>

        <motion.div
          variants={fadeUp}
          initial="initial"
          animate="animate"
          className="mt-9 w-full rounded-card border-2 border-transparent bg-card p-4 shadow-float transition-all focus-within:border-primary focus-within:shadow-glow"
        >
          <textarea
            ref={taRef}
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(text)
            }}
            placeholder="Which market, company or competitive question? For example: compare Notion, Obsidian and Craft on features and pricing"
            className="w-full resize-none bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-3"
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            {/* left：Depth choose */}
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
              <span className="text-tag text-ink-3">Depth</span>
              {MODE_OPTIONS.map((m) => {
                const Icon = m.icon
                const active = mode === m.key
                return (
                  <button
                    key={m.key}
                    type="button"
                    onClick={() => setMode(m.key)}
                    title={m.desc}
                    className={`inline-flex h-8 items-center gap-1.5 rounded-chip px-3 text-aux font-medium transition-colors ${
                      active
                        ? 'bg-primary-deep text-white'
                        : 'bg-primary-tint/60 text-ink-2 hover:bg-primary-tint'
                    }`}
                  >
                    <Icon size={14} /> {m.label}
                  </button>
                )
              })}
              <span className="text-tag text-ink-3">
                {MODE_OPTIONS.find((m) => m.key === mode)?.desc}
              </span>
            </div>

            {/* right：sent */}
              <button
                onClick={() => submit(text)}
                disabled={!text.trim() || submitting}
                className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-primary-deep text-white shadow-card transition-all hover:scale-105 hover:bg-primary-deeper active:scale-95 disabled:opacity-40 disabled:hover:scale-100"
                aria-label="Start research"
              >
                <ArrowUp size={20} />
              </button>
          </div>
        </motion.div>

        <p className="mt-9 text-aux text-ink-3">Or start from an example</p>
        <motion.div
          variants={stagger}
          initial="initial"
          animate="animate"
          className="mt-4 grid w-full grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          {EXAMPLES.map((ex) => (
            <motion.button
              key={ex.title}
              variants={fadeUp}
              onClick={() => fillExample(ex.q)}
              title="Put this question in the box above"
              className="group flex flex-col rounded-card border border-line/60 bg-card/80 p-4 text-left shadow-card backdrop-blur transition-all hover:-translate-y-0.5 hover:shadow-float"
            >
              <span
                className={`grid h-9 w-9 place-items-center rounded-btn ${
                  ACCENT_WELL[ex.accent]
                }`}
              >
                <ex.icon size={18} />
              </span>
              <span className="mt-3 text-aux font-semibold text-ink">{ex.title}</span>
              <span className="mt-1 text-tag leading-relaxed text-ink-3">{ex.desc}</span>
            </motion.button>
          ))}
        </motion.div>

        {SHOW_ANALYST_WALL && (
          <div className="mt-12 flex w-full flex-col items-center">
            <div className="flex flex-wrap items-center justify-center">
              <div className="flex items-center -space-x-2">
                {wall.map((e, i) => (
                  <span
                    key={e.id}
                    className="relative"
                    style={{ zIndex: wall.length - i }}
                  >
                    <VAvatar
                      expert={e}
                      size={36}
                      title={`${e.name} · ${e.role_title}`}
                      className="border-2 border-card shadow-card"
                    />
                  </span>
                ))}
              </div>
              <button
                onClick={() => navigate('/experts')}
                className="z-0 ml-2 inline-flex h-9 items-center rounded-chip bg-primary-tint px-3 text-tag font-medium text-primary-deep hover:bg-primary-soft/40"
              >
                {teamSize > 0 ? `Meet all ${teamSize} analysts →` : 'Meet the analysts →'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
