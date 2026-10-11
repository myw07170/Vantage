import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowRight, Loader2, Plus, Sparkles, Trash2 } from 'lucide-react'
import { fetchTask, prepareTask, startTask } from '../lib/api'
import type { Preparation, Product, Scope, SuggestedProduct, Topic } from '../types'
import { VLogo } from '../components/VLogo'
const defaults: Topic[] = [{ id: 'features', name: 'Features and limitations', focus: [] }, { id: 'pricing', name: 'Plans and billing', focus: [] }, { id: 'positioning', name: 'Audience and positioning', focus: [] }]
const empty = (): SuggestedProduct => ({ id: crypto.randomUUID(), name: '', mentioned_as: '', website: '', category: 'Software / SaaS', own_product: false, confirmed: false, website_status: 'unverified', identity_note: '' })
type ScopeDraft = { products: SuggestedProduct[]; topics: Topic[]; notes: string; answers: Record<string, string | string[]>; revision: number }
export default function ClarifyPage() {
  const { taskId = '' } = useParams(), navigate = useNavigate()
  const [query, setQuery] = useState(''), [prep, setPrep] = useState<Preparation>(), [products, setProducts] = useState<SuggestedProduct[]>([]), [topics, setTopics] = useState<Topic[]>(defaults)
  const [notes, setNotes] = useState(''), [answers, setAnswers] = useState<Record<string, string | string[]>>({}), [manual, setManual] = useState(false), [ack, setAck] = useState(false), [error, setError] = useState(''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true)
  const hydrated = useRef(-1)
  useEffect(() => {
    let disposed = false
    async function restore() {
      const t = await fetchTask(taskId)
      if (disposed) return
      if (!['created', 'preparing', 'awaiting_confirmation'].includes(t.status)) { navigate('/workspace/' + taskId, { replace: true }); return }
      setQuery(t.query); setLoading(false)
      const p = t.payload.preparation
      setPrep(p)
      if (p?.proposal && p.status !== 'running' && p.revision !== hydrated.current) {
        let saved: ScopeDraft | undefined
        try { saved = JSON.parse(localStorage.getItem('vantage.scope.' + taskId) || 'null') || undefined } catch { /* Optional draft. */ }
        const d = saved?.revision === p.revision ? saved : undefined
        setProducts(d?.products ?? p.proposal.products); setTopics(d?.topics ?? p.proposal.topics)
        setNotes(d?.notes ?? p.proposal.limitations); setAnswers(d?.answers ?? p.answers)
        hydrated.current = p.revision
      }
    }
    void restore().catch(e => { if (!disposed) { setError(e.message); setLoading(false) } })
    const poll = setInterval(() => { void restore().catch(() => {}) }, 1500)
    return () => { disposed = true; clearInterval(poll) }
  }, [taskId, navigate])
  useEffect(() => {
    if (hydrated.current < 0) return
    try { localStorage.setItem('vantage.scope.' + taskId, JSON.stringify({ products, topics, notes, answers, revision: hydrated.current })) } catch { /* Draft remains in memory. */ }
  }, [products, topics, notes, answers, taskId])
  const preparing = prep?.status === 'running', broad = topics.length > 6 || topics.reduce((n, t) => n + Math.max(1, t.focus.length), 0) * products.length > 24
  const strategic = topics.some(t => /swot|five forces|market share|growth|sentiment|persona|forecast/i.test(t.name + ' ' + t.focus.join(' ')))
  const unanswered = !manual && !!prep?.proposal?.questions.some(q => q.required && !(Array.isArray(answers[q.id]) ? answers[q.id].length : String(answers[q.id] || '').trim()))
  const answersChanged = !manual && JSON.stringify(answers) !== JSON.stringify(prep?.answers ?? {})
  function patch(id: string, value: Partial<SuggestedProduct>) { setProducts(list => list.map(p => p.id === id ? { ...p, ...value, confirmed: value.confirmed ?? false, website_status: value.website !== undefined ? 'unverified' : p.website_status } : p)) }
  async function prepare() {
    if (busy || preparing) return
    setBusy(true); setError('')
    try {
      const t = await prepareTask(taskId, prep?.revision ?? 0, answers, { products, topics, limitations: notes })
      setPrep(t.payload.preparation)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function start() {
    if (busy || preparing) return
    setBusy(true); setError('')
    const scope: Scope = { products: products.map(({ id, name, website, category, own_product, confirmed }): Product => ({ id, name, website, category, own_product, confirmed })), topics, changes_days: 90, scope_acknowledged: ack, limitations: notes }
    try { await startTask(taskId, scope); try { localStorage.removeItem('vantage.scope.' + taskId) } catch { /* Navigation is independent of optional browser storage. */ } navigate('/workspace/' + taskId) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  if (loading) return <div className="page">Loading your request…</div>
  return <div className="page setup-page guided-setup"><div className="sun-glow" aria-hidden="true" />
    <div className="guided-heading"><VLogo size={40} /><div><h1>A few questions before we start</h1><p className="muted">Confirm what we understood. We’ll only ask about things that change the research.</p></div></div>
    <section className="panel"><span className="eyebrow">Your request</span><p>{query}</p></section>
    {preparing && <section className="panel preparation-state" role="status"><Loader2 className="animate-spin" size={24} /><div><h2>Understanding your request…</h2><p className="muted">Identifying named products, checking proposed websites, and preparing relevant questions. Research has not started.</p></div></section>}
    {prep?.proposal && <section className="panel understanding"><span className="eyebrow"><Sparkles size={14} />Our understanding</span><p>{prep.proposal.summary}</p></section>}
    {(prep?.error || error) && <p className="notice error" role="alert">{error || prep?.error}</p>}
    {!preparing && (!prep || ['failed', 'interrupted'].includes(prep.status)) && <div className="button-row"><button className="button primary" disabled={busy} onClick={() => void prepare()}>{prep ? 'Retry understanding' : 'Understand my request'}</button><button className="text-button" onClick={() => { setManual(true); if (!products.length) setProducts([empty()]) }}>Edit scope manually</button></div>}
    {!preparing && (prep?.proposal || manual) && <>
      {!!prep?.proposal?.questions.length && <section className="clarify-questions">{prep.proposal.questions.map(q => <div className="panel" key={q.id}><h2>{q.question}</h2>{q.options.length ? <div className="choice-chips">{q.options.map(option => {
        const chosen = Array.isArray(answers[q.id]) ? answers[q.id].includes(option) : answers[q.id] === option
        return <button type="button" key={option} aria-pressed={chosen} className={chosen ? 'selected' : ''} onClick={() => setAnswers(a => ({ ...a, [q.id]: q.type === 'multi' ? chosen ? (a[q.id] as string[]).filter(v => v !== option) : [...(Array.isArray(a[q.id]) ? a[q.id] : []), option] : option }))}>{option}</button>
      })}</div> : <label>Your answer<input value={String(answers[q.id] || '')} onChange={e => setAnswers(a => ({ ...a, [q.id]: e.target.value }))} /></label>}</div>)}<button className="button secondary" disabled={busy || unanswered} onClick={() => void prepare()}>Update suggestions from my answers<ArrowRight size={15} /></button></section>}
      <form onSubmit={e => { e.preventDefault(); void start() }}>
        <div className="section-heading"><h2>Are these the right products? <span className="muted">{products.length}/4</span></h2><button type="button" className="text-button" disabled={products.length >= 4} onClick={() => setProducts(p => [...p, empty()])}><Plus size={15} />Add product</button></div>
        <div className="product-cards">{products.map((p, index) => <fieldset className="panel" key={p.id}><legend>Product {index + 1}</legend><label>Product name<input value={p.name} required onChange={e => patch(p.id, { name: e.target.value })} /></label><p className="identity-note">{p.website_status === 'verified' ? 'Public website found · Please confirm ownership' : 'Website needs confirmation'}</p>{p.website && <a href={p.website} target="_blank" rel="noreferrer">{p.website}</a>}<p className="muted text-sm">{p.identity_note}</p>
          <details open={manual || !p.website}><summary>Edit product details</summary><label>Vendor website<input type="url" value={p.website} required onChange={e => patch(p.id, { website: e.target.value })} /></label><label>Product category<input value={p.category} required onChange={e => patch(p.id, { category: e.target.value })} /></label><label className="check"><input type="checkbox" checked={p.own_product} onChange={e => patch(p.id, { own_product: e.target.checked })} />My product</label></details>
          <div className="product-actions"><label className="check confirmation"><input type="checkbox" checked={p.confirmed} required onChange={e => patch(p.id, { confirmed: e.target.checked })} />I confirm this product's identity and vendor website.</label><button type="button" className="icon-button" aria-label={'Remove ' + (p.name || 'product')} disabled={products.length === 1} onClick={() => setProducts(list => list.filter(x => x.id !== p.id))}><Trash2 size={15} /></button></div>
        </fieldset>)}</div>
        <section className="panel"><div className="section-heading"><h2>Research focus</h2><button type="button" className="text-button" onClick={() => setTopics(t => [...t, { id: crypto.randomUUID(), name: '', focus: [] }])}><Plus size={15} />Add topic</button></div>{topics.map(t => <div className="guided-topic" key={t.id}><label>Topic<input required value={t.name} onChange={e => setTopics(list => list.map(x => x.id === t.id ? { ...x, name: e.target.value } : x))} /></label><label>Focus points (one per line)<textarea rows={2} value={t.focus.join('\n')} onChange={e => setTopics(list => list.map(x => x.id === t.id ? { ...x, focus: e.target.value.split('\n') } : x))} onBlur={() => setTopics(list => list.map(x => ({ ...x, focus: x.focus.map(f => f.trim()).filter(Boolean) })))} /></label><button type="button" className="text-button" disabled={topics.length === 1} onClick={() => setTopics(list => list.filter(x => x.id !== t.id))}>Remove topic</button></div>)}</section>
        <section className="panel"><h2>Current state + the last 90 days</h2><label>Scope notes and question boundaries<textarea value={notes} required={strategic} rows={3} onChange={e => setNotes(e.target.value)} /></label>{(broad || strategic) && <div className="notice"><p>{broad ? 'This scope may take longer. Consider splitting it into smaller comparisons.' : 'Bound strategic questions to what public sources can establish.'}</p><label className="check"><input type="checkbox" checked={ack} required onChange={e => setAck(e.target.checked)} />I confirm this scope and its public-source limitations.</label></div>}{answersChanged && <p className="notice">Update suggestions from your answers before confirming the scope.</p>}<p className="muted text-sm">Your own product counts toward the four-product limit. Research starts only after confirmation.</p><button className="button primary" disabled={busy || preparing || unanswered || answersChanged || !products.length || products.some(p => !p.confirmed)}>{busy ? 'Starting…' : 'Confirm scope & start'}<ArrowRight size={16} /></button></section>
      </form>
    </>}
  </div>
}
