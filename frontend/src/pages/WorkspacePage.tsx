import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { Activity as ActivityIcon, ArrowLeft, Check, CheckCircle2, Compass, FileText, Loader2, RotateCcw, Users } from 'lucide-react'
import { fetchTask, fetchTrace, openTaskStream, retryTask } from '../lib/api'
import type { Activity, Evidence, StreamStatus, Task, TraceSpan, Usage, Visualization } from '../types'
import { EvidenceCard, TraceDetails, UsageInfo } from '../components/Research'
import { VLogo } from '../components/VLogo'
const initial: Visualization = { roles: {}, activity: [], percent: 0, rework_rounds: 0 }
const roles = [{ id: 'collector', label: 'Collector', detail: 'Find sources and preserve context.' }, { id: 'analyst', label: 'Analyst', detail: 'Compare atomic facts and write a short brief.' }, { id: 'reviewer', label: 'Reviewer', detail: 'Check evidence support and direct rework.' }]
export default function WorkspacePage() {
  const reducedMotion = useReducedMotion()
  const { taskId = '' } = useParams(), navigate = useNavigate(), [params] = useSearchParams(), inspect = params.has('inspect')
  const [task, setTask] = useState<Task | null>(null), [visual, setVisual] = useState(initial), [usage, setUsage] = useState<Usage>(), [sources, setSources] = useState<Evidence[]>([]), [traces, setTraces] = useState<TraceSpan[]>([])
  const [error, setError] = useState(''), [connection, setConnection] = useState<StreamStatus>('connecting'), [tab, setTab] = useState('activity')
  const log = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let disposed = false, close = () => {}
    let redirect: ReturnType<typeof setTimeout> | undefined
    function openResult(t: Task) {
      if (!inspect && !redirect && t.status === 'done') redirect = setTimeout(() => navigate('/report/' + t.report_id + (t.kind !== 'research' ? '?version=' + t.version_id : ''), { replace: true }), 1600)
    }
    async function restore() {
      const t = await fetchTask(taskId)
      if (disposed) return t
      setTask(t); setUsage(t.checkpoint.usage)
      if (t.checkpoint.content) setSources(t.checkpoint.content.evidence)
      if (t.checkpoint.visualization) setVisual(t.checkpoint.visualization)
      if (['created','preparing','awaiting_confirmation'].includes(t.status)) navigate('/clarify/' + taskId, { replace: true })
      if (t.status === 'done') { setConnection('closed'); openResult(t) }
      if (['failed','interrupted'].includes(t.status)) { setConnection('closed'); setError(t.error) }
      return t
    }
    async function diagnostics() {
      const r = await fetchTrace(taskId)
      if (disposed) return
      setTraces(r.spans)
      setVisual(v => v.activity.length || !r.spans.length ? v : { ...v, roles: Object.fromEntries(roles.map(role => [role.id, { role: role.id, status: r.spans.some(s => s.agent_id === role.id) ? 'done' : 'waiting', detail: role.detail }])), activity: r.spans.filter(s => s.agent_id).map((s,index) => ({ id: -index-1, kind: 'activity', role: s.agent_id, text: s.purpose, at: '' })) })
    }
    void restore().then(t => {
      if (disposed) return
      void diagnostics().catch(() => {})
      if (t.status !== 'running') return
      close = openTaskStream(taskId, { onStatus: setConnection, onEvent: (kind, raw, id) => {
        if (disposed) return
        const data = raw as Record<string, unknown>
        if (kind === 'evidence') { const e = raw as Evidence; setSources(s => s.some(old => old.evidence_id === e.evidence_id) ? s : [...s,e]) }
        if (kind === 'progress') { setVisual(v => ({ ...v, percent: Math.max(v.percent, Number(data.percent)) })); setUsage(data.usage as Usage) }
        if (kind === 'role') setVisual(v => ({ ...v, roles: { ...v.roles, [String(data.role)]: data as unknown as Visualization['roles'][string] } }))
        if (kind === 'handoff') setVisual(v => ({ ...v, rework_rounds: Number(data.round) }))
        const text = kind === 'role' ? String(data.detail) : kind === 'activity' ? String(data.text) : kind === 'notice' || kind === 'error' ? String(data.message) : kind === 'handoff' ? 'Reviewer → Collector · Targeted rework ' + data.round + '/2' : ''
        if (text) { const entry: Activity = { id, kind, role: String(data.role || ''), text, at: new Date().toISOString() }; setVisual(v => ({ ...v, activity: [...v.activity.filter(a => a.id !== id),entry].slice(-200) })) }
        if (kind === 'done') void restore().catch(e => setError(e.message))
        if (kind === 'error') { setError(String(data.message)); void restore().catch(() => {}) }
      } })
    }).catch(e => { if (!disposed) setError(e.message) })
    const poll = setInterval(() => { void restore().catch(() => {}); void diagnostics().catch(() => {}) }, 2500)
    return () => { disposed = true; close(); clearInterval(poll); clearTimeout(redirect) }
  }, [taskId, navigate, inspect])
  useEffect(() => { const el = log.current; if (el && el.scrollHeight-el.scrollTop-el.clientHeight < 180) el.scrollTop = el.scrollHeight }, [visual.activity.length])
  async function retry() { try { const t = await retryTask(taskId); navigate('/workspace/' + t.task_id) } catch (e) { setError((e as Error).message) } }
  const done = task?.status === 'done', result = '/report/' + task?.report_id + (task?.kind !== 'research' ? '?version=' + task?.version_id : '')
  return <div className="visual-workspace">
    <header className="workspace-header"><Link to="/" className="icon-button" aria-label="Back"><ArrowLeft size={19} /></Link><VLogo size={32} /><div className="workspace-title"><strong>{task?.query || 'Preparing the workspace…'}</strong><small>{task?.kind === 'research' ? 'Product research' : 'Candidate research'} · {connection}</small></div><span className="workspace-source-count"><FileText size={14} />{sources.length} sources</span><div className="workspace-meter"><progress max={100} value={done ? 100 : visual.percent} aria-label="Overall progress" /><span>{done ? 100 : visual.percent}%</span></div></header>
    <div className="workspace-tabs" role="tablist" aria-label="Workspace panels">{['pipeline','activity','sources'].map(id => <button role="tab" aria-selected={tab === id} aria-controls={'workspace-' + id} id={'tab-' + id} key={id} onClick={() => setTab(id)}>{id[0].toUpperCase()+id.slice(1)}</button>)}</div>
    {error && <div className="workspace-alert" role="alert">{error}{['failed','interrupted'].includes(task?.status || '') && <button className="text-button" onClick={() => void retry()}>Retry as a new task</button>}<Link to="/library" className="text-button">Open history</Link></div>}
    <div className={'workspace-columns active-' + tab}>
      <aside id="workspace-pipeline" role="tabpanel" aria-labelledby="tab-pipeline" className="workspace-pipeline"><div className="workspace-panel-title"><ActivityIcon size={15} /><h2>Pipeline</h2></div><div className="pipeline-scroll"><div className="flow-timeline">{roles.map((r,index) => { const current = visual.roles[r.id], status = current?.status || 'waiting'; return <div className={'flow-node flow-' + status} key={r.id}><div className="flow-track"><span>{status === 'done' ? <Check size={13} /> : status === 'working' ? <Loader2 size={14} className="animate-spin" /> : index+1}</span>{index < 2 && <i />}</div><div><h3>{r.label}</h3><p>{current?.detail || r.detail}</p><small>{status}</small></div></div> })}</div>{visual.rework_rounds > 0 && <div className="rework-chip"><RotateCcw size={14} />Targeted rework {visual.rework_rounds}/2</div>}<h3 className="team-heading"><Users size={15} />Three fixed roles</h3><p className="muted text-sm">Collector → Analyst → Reviewer. A single confirmed scope, with independent responsibilities.</p><details className="workspace-details"><summary>Tokens and elapsed time</summary><UsageInfo usage={usage} /></details><details className="workspace-details"><summary>Call diagnostics</summary><TraceDetails spans={traces} /></details></div></aside>
      <section id="workspace-activity" role="tabpanel" aria-labelledby="tab-activity" className="workspace-activity"><div className="workspace-panel-title"><ActivityIcon size={15} /><h2>Research activity</h2></div><div className="activity-scroll" ref={log}>{!visual.activity.length && !done && <div className="activity-empty"><Compass size={32} className="animate-spin" /><p>Preparing the research handoff…</p><span>Research continues if you close this page.</span></div>}{visual.activity.map(entry => <motion.article initial={reducedMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={'activity-entry kind-' + entry.kind} key={entry.id}><span className={'activity-icon accent-' + (entry.role === 'reviewer' ? 'pink' : entry.role === 'analyst' ? 'violet' : 'blue')}>{entry.kind === 'handoff' ? <RotateCcw size={15} /> : <ActivityIcon size={15} />}</span><div><span className="activity-label">{entry.role || (entry.kind === 'handoff' ? 'Rework' : 'Research update')}{entry.at && <time>{new Date(entry.at).toLocaleTimeString('en-US')}</time>}</span><p>{entry.text}</p></div></motion.article>)}{task?.checkpoint.content?.review_summary.issues?.length ? <details className="panel"><summary>Review issues ({task.checkpoint.content.review_summary.issues.length})</summary>{task.checkpoint.content.review_summary.issues.map(issue => <p key={issue.item_id}><strong>{issue.item_id}</strong> · {issue.reason}</p>)}</details> : null}{task?.checkpoint.content?.limitations.map((lim,index) => <p className="notice" key={index}>{lim}</p>)}{done && <div className="workspace-ready"><CheckCircle2 size={24} /><div><h2>Research complete</h2><p>The saved result includes individual review states and unresolved questions.</p></div><Link className="button primary" to={result}>Open saved result</Link></div>}{task?.checkpoint.content && ['failed','interrupted'].includes(task.status) && <details className="panel"><summary>Retained draft and collected material</summary><p className="muted">This checkpoint may contain unreviewed content.</p><pre className="source-context">{JSON.stringify(task.checkpoint.content,null,2)}</pre></details>}</div></section>
      <aside id="workspace-sources" role="tabpanel" aria-labelledby="tab-sources" className="workspace-sources"><div className="workspace-panel-title"><FileText size={15} /><h2>Evidence ({sources.length})</h2></div><div className="evidence-scroll">{sources.map(e => <EvidenceCard evidence={e} key={e.evidence_id} />)}{!sources.length && <p className="muted text-sm">Public sources will appear here as they are collected.</p>}</div></aside>
    </div>
  </div>
}
