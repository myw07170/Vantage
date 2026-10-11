import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Star, Trash2, ArrowUpRight } from 'lucide-react'
import { deleteReport, fetchTasks, updateReport } from '../lib/api'
import { useReportStore } from '../store/reportStore'
import type { Task } from '../types'
export default function LibraryPage() {
  const cards = useReportStore(s => s.cards), load = useReportStore(s => s.loadCards), invalidate = useReportStore(s => s.invalidate)
  const [tasks, setTasks] = useState<Task[]>([]), [error, setError] = useState(''), [loading, setLoading] = useState(true)
  useEffect(() => { void Promise.all([load(), fetchTasks().then(setTasks)]).catch(e => setError(e.message)).finally(() => setLoading(false)) }, [load])
  async function remove(id: string) {
    if (!window.confirm('Delete this comparison and all its versions, evidence, and diagnostics?')) return
    try { await deleteReport(id); invalidate(id); await load(); setTasks(await fetchTasks()) } catch (e) { setError((e as Error).message) }
  }
  async function star(id: string, starred: boolean) { try { await updateReport(id, { starred }); await load() } catch (e) { setError((e as Error).message) } }
  return <div className="page"><div className="section-heading"><div><div className="eyebrow">Your workspace</div><h1>Comparison history</h1></div><Link className="button primary" to="/"><Plus size={16} />New comparison</Link></div><p className="intro">Applied reports, saved versions, and follow-up candidates stay connected.</p>
    {error && <p className="error" role="alert">{error}</p>}{loading && <p className="muted">Loading history…</p>}
    {!loading && !cards.length && <section className="panel empty-state"><h2>Start with a product question.</h2><p>Your comparisons and versions will appear here.</p><Link className="button primary" to="/">Create a comparison</Link></section>}
    <div className="history-grid">{cards.map(c => <article className="panel history-card" key={c.report_id}><div className="section-heading"><span className="eyebrow">{new Date(c.created_at).toLocaleDateString('en-US')}</span><button className="icon-button" aria-label={c.starred ? 'Unstar comparison' : 'Star comparison'} onClick={() => void star(c.report_id, !c.starred)}><Star size={17} fill={c.starred ? 'currentColor' : 'none'} /></button></div><Link to={'/report/' + c.report_id}><h2>{c.title}</h2></Link><p className="muted">Current report with version history</p><div className="section-heading"><Link className="text-button" to={'/report/' + c.report_id}>Open comparison<ArrowUpRight size={14} /></Link><button className="icon-button" aria-label={'Delete ' + c.title} onClick={() => void remove(c.report_id)}><Trash2 size={15} /></button></div></article>)}</div>
    <section className="task-history"><h2>Tasks and follow-ups</h2>{tasks.map(t => <Link className="task-row" key={t.task_id} to={['created', 'preparing', 'awaiting_confirmation'].includes(t.status) && t.kind === 'research' ? '/clarify/' + t.task_id : t.status === 'done' && t.report_id ? '/report/' + t.report_id + (t.kind !== 'research' ? '?version=' + t.version_id : '') : '/workspace/' + t.task_id}><div><strong>{t.query}</strong><span>{t.kind} · {new Date(t.created_at).toLocaleString('en-US')}</span></div><span className={'status-badge ' + (t.status === 'done' ? 'status-supported' : 'status-pending_review')}>{t.status === 'done' && t.kind !== 'research' ? 'Candidate ready' : t.status}</span></Link>)}{!tasks.length && <p className="muted">No tasks yet.</p>}</section>
  </div>
}
