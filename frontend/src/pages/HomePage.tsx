import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { ArrowUp, Sparkles, Layers, CreditCard, ShieldCheck, Laptop } from 'lucide-react'
import { createTask, prepareTask } from '../lib/api'
import { VLogo } from '../components/VLogo'

const examples = [
  { icon: Layers, color: 'blue', title: 'Feature benchmark', desc: 'Compare Notion, Obsidian and Craft', query: 'Compare Notion, Obsidian and Craft on features and limitations for a research team' },
  { icon: CreditCard, color: 'violet', title: 'Pricing teardown', desc: 'See how Figma and Sketch package and price', query: 'Compare Figma and Sketch on plans, billing and eligibility for a five-person design team' },
  { icon: ShieldCheck, color: 'orchid', title: 'Team collaboration', desc: 'Slack and Microsoft Teams, side by side', query: 'Compare Slack and Microsoft Teams on collaboration, permissions and billing for a small SaaS company' },
  { icon: Laptop, color: 'pink', title: 'Offline workflows', desc: 'Notion and Obsidian for independent research', query: 'Compare Notion and Obsidian for offline research, portability and personal use costs' },
]
const fade = { initial: { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 } }
export default function HomePage() {
  const reducedMotion = useReducedMotion()
  const enter = reducedMotion ? { initial: false as const, animate: { opacity: 1, y: 0 } } : fade
  const [query, setQuery] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const input = useRef<HTMLTextAreaElement>(null), navigate = useNavigate()
  async function submit() {
    if (!query.trim() || busy) return
    setBusy(true); setError('')
    try {
      const task = await createTask(query)
      try { await prepareTask(task.task_id, 0, {}) } catch { /* The clarification page offers explicit retry and manual entry. */ }
      navigate('/clarify/' + task.task_id)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  function fill(text: string) {
    setQuery(text); input.current?.focus()
    requestAnimationFrame(() => input.current?.setSelectionRange(text.length, text.length))
  }
  return <div className="home-restored">
    <div className="sun-glow" aria-hidden="true" />
    <div className="home-assurance"><span><Sparkles size={14} />Every claim carries its source</span></div>
    <div className="home-center">
      <motion.h1 {...enter}>What are we researching? <VLogo size={42} /></motion.h1>
      <motion.p {...enter} className="home-tagline">Live web research · evidence you can inspect · questions you can follow up</motion.p>
      <motion.form {...enter} className="home-composer" onSubmit={e => { e.preventDefault(); void submit() }}>
        <textarea ref={input} aria-label="What do you want to compare?" rows={5} value={query} maxLength={4000} onChange={e => setQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void submit() } }} placeholder="Which software products or competitive question? For example: compare Notion, Obsidian and Craft on features and pricing" required />
        <div className="home-send-row"><div><span className="unified-chip"><Sparkles size={13} />Guided comparison</span><span className="muted text-sm">We’ll suggest a scope for you to confirm.</span></div><button type="submit" className="home-send" disabled={busy || !query.trim()} aria-label="Start research"><ArrowUp size={21} /></button></div>
        {error && <p className="error" role="alert">{error}</p>}
      </motion.form>
      <p className="home-example-label">Or start from an example</p>
      <div className="home-example-grid">{examples.map(({ icon: Icon, ...ex }, index) => <motion.button {...enter} transition={reducedMotion ? { duration: 0 } : { delay: index * .05 }} type="button" key={ex.title} onClick={() => fill(ex.query)} title="Put this question in the box above"><span className={'example-icon accent-' + ex.color}><Icon size={18} /></span><strong>{ex.title}</strong><span>{ex.desc}</span></motion.button>)}</div>
    </div>
  </div>
}
