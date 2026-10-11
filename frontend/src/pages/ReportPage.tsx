import { ReportReader } from '../components/ReportReader'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Check, History, Save, ShieldCheck, X } from 'lucide-react'
import { applyCandidate, fetchVersion, fetchVersions, followup, restoreVersion, reviewReport, saveEdits, updateReport } from '../lib/api'
import { loadDraft, saveDraft } from '../lib/drafts'
import { useReportStore } from '../store/reportStore'
import { Badge, EvidenceCard, ItemView, UsageInfo } from '../components/Research'
import { ReportReview } from '../components/ReportReview'
import type { Content, Item, Report, Version, VersionMeta } from '../types'

const items = (c: Content) => [...c.comparison, ...c.brief, ...c.changes]
function changedItems(base: Content, next: Content): { before?: Item; after?: Item }[] {
  const before = new Map(items(base).map(i => [i.id, i])), after = new Map(items(next).map(i => [i.id, i]))
  const signature = (i?: Item) => i ? JSON.stringify([i.text, i.citations, i.conditions, i.effective_date, i.depends_on, i.review.status, i.review.reason]) : ''
  return [...new Set([...before.keys(), ...after.keys()])].filter(id => signature(before.get(id)) !== signature(after.get(id))).map(id => ({ before: before.get(id), after: after.get(id) }))
}

export default function ReportPage() {
  const { reportId = '' } = useParams(), [params, setParams] = useSearchParams(), navigate = useNavigate()
  const selectedId = params.get('version'), load = useReportStore(s => s.load), loadCards = useReportStore(s => s.loadCards), invalidate = useReportStore(s => s.invalidate)
  const [report, setReport] = useState<Report | null>(null), [version, setVersion] = useState<Version | null>(null), [base, setBase] = useState<Version | null>(null), [versions, setVersions] = useState<VersionMeta[]>([])
  const [edits, setEdits] = useState<Record<string, string>>({}), [annotation, setAnnotation] = useState<{ item: Item; selected: string } | null>(null), [question, setQuestion] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false), [exitRequested, setExitRequested] = useState(false), [noteSaving, setNoteSaving] = useState(false)
  useEffect(() => {
    let active = true
    void (async () => {
      const r = await load(reportId)
      const v = selectedId ? await fetchVersion(reportId, selectedId) : r.version
      const history = await fetchVersions(reportId)
      const b = v.state === 'candidate' && v.base_version_id ? await fetchVersion(reportId, v.base_version_id) : null
      if (active) {
        setReport(r); setVersion(v); setVersions(history); setBase(b)
        const draft = v.version_id === r.current_version_id && v.state !== 'candidate' ? loadDraft(reportId, v.version_id) : {}
        setEdits(draft); setEditing(Object.keys(draft).length > 0); setExitRequested(false); setAnnotation(null)
      }
      await loadCards()
    })().catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [reportId, selectedId, load, loadCards])
  if (!report || !version) return <div className="page">{error ? <p className="error" role="alert">{error}</p> : 'Loading comparison…'}<Link to="/library" className="text-button">Open history</Link></div>

  const content = version.content, isCurrent = version.version_id === report.current_version_id, candidate = version.state === 'candidate'
  const appliedCandidate = candidate ? versions.find(v => v.kind === 'apply' && v.metadata.candidate_version_id === version.version_id) : undefined
  const dirty = Object.keys(edits).length > 0
  const canModify = isCurrent && !candidate
  const controlsBusy = busy || noteSaving
  function edit(id: string, text: string) {
    const original = items(content).find(i => i.id === id)?.text
    setEdits(previous => {
      const next = { ...previous }
      if (text === original) delete next[id]; else next[id] = text
      saveDraft(reportId, version!.version_id, next)
      return next
    })
  }
  async function mutation(action: () => Promise<unknown>, clear = false) {
    if (controlsBusy) return
    setBusy(true); setError('')
    try {
      await action()
      invalidate(reportId)
      const r = await load(reportId)
      const history = await fetchVersions(reportId)
      await loadCards()
      if (clear) saveDraft(reportId, version!.version_id, {})
      setEdits({}); setEditing(false); setExitRequested(false)
      setReport(r); setVersion(r.version); setBase(null); setVersions(history); setParams({})
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function startFollowup() {
    if (!annotation || !question.trim() || busy) return
    setBusy(true); setError('')
    try {
      const task = await followup(reportId, version!.version_id, annotation.item.id, question, annotation.selected)
      navigate('/workspace/' + task.task_id)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function startReview() {
    setBusy(true); setError('')
    try { const t = await reviewReport(reportId, version!.version_id); navigate('/workspace/' + t.task_id) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  function annotate(item: Item, selected: string) {
    if (!canModify || editing || controlsBusy) return
    if (dirty) { setError('Save or discard your edits before starting a follow-up. Your draft has been kept.'); return }
    setQuestion(''); setAnnotation({ item, selected })
  }
  function changeMode(next: boolean) {
    if (controlsBusy || !canModify) return
    window.getSelection()?.removeAllRanges()
    if (!next && dirty) { setExitRequested(true); return }
    setEditing(next)
  }
  function discardEdits() {
    saveDraft(reportId, version!.version_id, {})
    setEdits({}); setEditing(false); setExitRequested(false)
  }
  async function rename() {
    const title = window.prompt('Comparison title', report!.title)
    if (!title?.trim()) return
    try { const r = await updateReport(reportId, { title: title.trim() }); setReport(r); await loadCards() }
    catch (e) { setError((e as Error).message) }
  }
  return <ReportReader key={version.version_id} reportId={reportId} versionId={version.version_id} content={content} canAnnotate={canModify && !busy && !exitRequested && !annotation} editing={editing} onError={setError} onFollowup={annotate} onSavingChange={setNoteSaving}><div className="page report-page">
    <Link className="text-button" to="/library"><ArrowLeft size={14} />History</Link>
    <div className="report-heading"><div><div className="eyebrow">{candidate ? appliedCandidate ? 'Applied candidate · Historical preview' : 'Candidate preview · Not applied' : isCurrent ? 'Current comparison' : 'Historical version'}</div><h1>{report.title}</h1><p className="muted text-sm">Checked {new Date(content.checked_at).toLocaleString('en-US')} · Changes since {content.changes_since}</p></div><button className="text-button" disabled={controlsBusy} onClick={() => void rename()}>Rename</button></div>
    {content.is_mock && <div className="notice">[MOCK] Simulated report. Source notes and simulated review do not establish analytical conclusions.</div>}
    {error && <div className="notice error" role="alert">{error}<button className="text-button" onClick={() => setError('')}>Dismiss</button></div>}
    <div className="report-toolbar">
      <label><History size={15} />Version<select disabled={controlsBusy} value={version.version_id} onChange={e => { if (dirty && !window.confirm('Keep your unsaved draft and switch versions?')) return; setParams(e.target.value === report.current_version_id ? {} : { version: e.target.value }) }}>{versions.map(v => <option key={v.version_id} value={v.version_id}>{v.state === 'candidate' ? 'Candidate' : v.version_id === report.current_version_id ? 'Current' : 'Saved'} · {v.kind} · {new Date(v.created_at).toLocaleString('en-US')}</option>)}</select></label>
      {canModify ? <div className="report-mode" role="group" aria-label="Report mode"><button aria-pressed={!editing} disabled={controlsBusy} onClick={() => changeMode(false)}>Read only</button><button aria-pressed={editing} disabled={controlsBusy} onClick={() => changeMode(true)}>Edit</button></div> : <span className="muted text-sm">Read only</span>}
      {canModify && !editing && <button className="button secondary" disabled={controlsBusy || dirty} onClick={() => void startReview()}><ShieldCheck size={15} />Review current report</button>}
      {canModify && editing && <><button className="button primary" disabled={controlsBusy || !dirty} onClick={() => void mutation(() => saveEdits(reportId, version.version_id, edits), true)}><Save size={15} />{busy ? 'Saving…' : 'Save edits'}</button><button className="text-button" disabled={controlsBusy} onClick={discardEdits}>Discard edits</button></>}
    </div>
    {dirty && <p className="notice">Unsaved draft. Saving marks edited content and dependent judgments as Pending review.</p>}
    {candidate && <section className="panel candidate-banner"><div className="eyebrow">{appliedCandidate ? 'Candidate application recorded' : 'Review before applying'}</div><h2>{version.metadata.question || 'Review candidate'}</h2><p>{appliedCandidate ? 'This candidate was applied on ' + new Date(appliedCandidate.created_at).toLocaleString('en-US') + '. This preview retains the original research snapshot.' : 'This candidate was researched from version ' + version.base_version_id + '. Applying it is a separate action.'}</p>{!appliedCandidate && version.base_version_id !== report.current_version_id && <p className="error">The current version has changed since this task began. This candidate cannot overwrite those edits; start a new follow-up from the current version.</p>}<div className="button-row">{!appliedCandidate && <button className="button primary" disabled={busy || version.base_version_id !== report.current_version_id} onClick={() => void mutation(() => applyCandidate(reportId, report.current_version_id, version.version_id))}><Check size={15} />Apply candidate</button>}<button className="button secondary" onClick={() => setParams({})}>Return to current report</button></div>
      {base && <div className="candidate-diffs">{changedItems(base.content, content).map((d, index) => <div className="diff-row" key={index}><div><span className="eyebrow">Before</span><p>{d.before?.text || 'New item'}</p>{d.before && <Badge status={d.before.review.status} />}</div><div><span className="eyebrow">After</span><p>{d.after?.text || 'Removed item'}</p>{d.after && <Badge status={d.after.review.status} />}</div></div>)}{!changedItems(base.content, content).length && <p className="muted">No content changes. Review results and new source material are retained in this candidate.</p>}</div>}
      {base && <section className="candidate-sources"><h3>Newly collected sources</h3>{content.evidence.filter(e => !base.content.evidence.some(old => old.evidence_id === e.evidence_id)).map(e => <EvidenceCard key={e.evidence_id} evidence={e} />)}</section>}
    </section>}
    {!candidate && !isCurrent && <section className="notice"><p>You are viewing a historical version. Restoring creates a new current version and retains all history.</p><button className="button secondary" disabled={busy} onClick={() => void mutation(() => restoreVersion(reportId, report.current_version_id, version.version_id))}>Restore this version</button><button className="text-button" onClick={() => setParams({})}>Return to current</button></section>}
    <section className="panel review-summary"><div><h2>Review summary</h2><p className="muted">{content.review_summary.meaning || 'Review status is shown for each fact and key conclusion.'}</p></div><div className="review-counts">{(['supported', 'unknown', 'conflicting', 'pending_review'] as const).map(s => <div key={s}><strong>{content.review_summary.counts?.[s] || 0}</strong><Badge status={s} /></div>)}</div><UsageInfo usage={content.review_summary.usage} />{content.review_summary.run_limitation && <p className="notice">{content.review_summary.run_limitation}</p>}</section>
    <nav className="report-toc" aria-label="Report contents"><a href="#comparison">Comparison</a><a href="#brief">Short brief</a><a href="#changes">Recent changes</a><a href="#review">Review & limitations</a></nav>
    <section id="comparison"><div className="section-heading"><h2>Product comparison</h2><span className="muted text-sm">Sources and status on every item</span></div><div className="comparison-wrap"><table className="comparison-table"><thead><tr><th scope="col">Topic</th>{content.products.map(p => <th scope="col" key={p.id}><a href={p.website} target="_blank" rel="noreferrer">{p.name}</a>{p.own_product && <small>Your product</small>}<small>{p.category}</small></th>)}</tr></thead><tbody>{content.topics.map(t => <tr key={t.id}><th scope="row">{t.name}{t.focus.map(f => <small key={f}>{f}</small>)}</th>{content.products.map(p => <td key={p.id}>{content.comparison.filter(i => i.product_id === p.id && i.topic_id === t.id).map(i => <ItemView key={i.id} item={i} edit={edits[i.id]} onEdit={edit} editing={canModify && editing} disabled={controlsBusy || exitRequested} />)}</td>)}</tr>)}</tbody></table></div></section>
    <section id="brief" className="report-section"><div className="eyebrow">Key differences & conditions</div><h2>Short brief</h2>{content.brief.map(i => <ItemView key={i.id} item={i} edit={edits[i.id]} onEdit={edit} editing={canModify && editing} disabled={controlsBusy || exitRequested} />)}{!content.brief.length && <p className="muted">No sufficiently supported brief conclusions were produced.</p>}</section>
    <section id="changes" className="report-section"><div className="eyebrow">Last 90 days</div><h2>Recent changes</h2>{content.changes.map(i => <ItemView key={i.id} item={i} edit={edits[i.id]} onEdit={edit} editing={canModify && editing} disabled={controlsBusy || exitRequested} />)}{!content.changes.length && <p className="muted">No relevant public changes found. This does not establish that no changes occurred.</p>}</section>
    {content.charts.length > 0 && <section className="report-section"><h2>Comparable sourced data</h2>{content.charts.map(chart => <div className="panel sourced-chart" key={chart.id}><p className="muted text-sm">{Object.entries(chart.conditions).map(([k, v]) => k + ': ' + v).join(' · ')}</p>{chart.points.map(point => <div className="chart-point" key={point.item_id}><a href={'#item-' + point.item_id}>{content.products.find(p => p.id === point.product_id)?.name}</a><div className="bar-track"><div style={{ width: (point.value / Math.max(1, ...chart.points.map(p => p.value)) * 100) + '%' }} /></div><span>{point.value}</span></div>)}<p className="muted text-sm">Checked {new Date(chart.checked_at).toLocaleDateString('en-US')}. Each bar links to its reviewed fact and sources.</p></div>)}</section>}
    <ReportReview content={content} />
    {(version.task_id || version.metadata.source_task_id) && <Link className="text-button" to={'/workspace/' + (version.task_id || version.metadata.source_task_id) + '?inspect=1'}>Task progress and diagnostics</Link>}
    {exitRequested && <div className="modal-backdrop"><section className="panel annotation-modal" role="dialog" aria-modal="true" aria-labelledby="exit-edit-heading" onKeyDown={e => { if (e.key === 'Escape' && !busy) setExitRequested(false) }}><h2 id="exit-edit-heading">Save your edits?</h2><p>Save your changes before returning to read only, or discard them.</p>{error && <p className="notice error" role="alert">{error}</p>}<div className="button-row"><button className="button primary" disabled={controlsBusy} onClick={() => void mutation(() => saveEdits(reportId, version.version_id, edits), true)}>{busy ? 'Saving…' : 'Save and exit'}</button><button className="button secondary" disabled={controlsBusy} onClick={discardEdits}>Discard and exit</button><button autoFocus className="text-button" disabled={controlsBusy} onClick={() => setExitRequested(false)}>Continue editing</button></div></section></div>}
    {annotation && <div className="modal-backdrop"><section className="panel annotation-modal" role="dialog" aria-modal="true" aria-labelledby="followup-heading"><div className="section-heading"><h2 id="followup-heading">Follow up with new evidence</h2><button className="icon-button" aria-label="Close follow-up" onClick={() => setAnnotation(null)}><X size={18} /></button></div><blockquote>{annotation.selected || annotation.item.text}</blockquote><p className="muted text-sm">Base version: {version.version_id}. This creates a candidate for your review.</p><label>What should we check?<textarea autoFocus rows={4} value={question} maxLength={4000} onChange={e => setQuestion(e.target.value)} placeholder="Is this price for annual billing? Check the current vendor pricing page." /></label><div className="button-row"><button className="button primary" disabled={busy || !question.trim()} onClick={() => void startFollowup()}>Start targeted follow-up</button><button className="button secondary" onClick={() => setAnnotation(null)}>Cancel</button></div></section></div>}
  </div></ReportReader>
}
