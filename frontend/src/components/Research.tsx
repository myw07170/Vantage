import { CitedText } from './ReportReader'
import { ArrowUpRight } from 'lucide-react'
import type { Evidence, Item, ReviewStatus, TraceSpan, Usage } from '../types'
const labels: Record<ReviewStatus, string> = { supported: 'Supported', unknown: 'Unknown', conflicting: 'Conflicting', pending_review: 'Pending review' }
export function Badge({ status }: { status: ReviewStatus }) { return <span className={'status-badge status-' + status}>{labels[status]}</span> }
export function UsageInfo({ usage }: { usage?: Usage }) {
  return usage ? <div className="usage"><span>{usage.tokens.toLocaleString('en-US')} / {usage.token_limit.toLocaleString('en-US')} tokens{usage.usage_estimated ? ' (estimated)' : ''}</span><span>{Math.round(usage.elapsed_seconds)} seconds elapsed</span></div> : null
}
export function EvidenceCard({ evidence, index, active = false }: { evidence: Evidence; index?: number; active?: boolean }) {
  let domain = evidence.source_url
  try { domain = new URL(evidence.source_url).hostname } catch { /* Keep the original address visible. */ }
  const kind = { official: { label: 'Vendor source', className: 'source-official' }, external: { label: 'External source', className: 'source-external' }, unknown: { label: 'Unknown source', className: 'source-unknown' } }[evidence.source_type]
  return <a className={'source-card ' + kind.className + (active ? ' source-active' : '')} data-evidence-id={evidence.evidence_id} href={evidence.source_url} target="_blank" rel="noreferrer">
    <span className="source-card-meta"><span className="source-kind">{kind.label}</span>{index !== undefined && <span className="source-number">[{index + 1}]</span>}<ArrowUpRight size={14} aria-hidden="true" /></span>
    <strong className="source-title">{evidence.title || domain}</strong>
    <span className="source-domain">{domain}</span>
    <span className="source-excerpt">{evidence.excerpt}</span>
    <span className="source-dates"><span>Captured: <time dateTime={evidence.captured_at}>{new Date(evidence.captured_at).toLocaleDateString('en-US')}</time></span><span>Published: {evidence.published_at ? <time dateTime={evidence.published_at}>{evidence.published_at}</time> : 'Unknown'}</span></span>
    {evidence.limitation && <span className="source-limitation">{evidence.limitation}</span>}
  </a>
}
export function ItemView({ item, edit, onEdit, editing = false, disabled = false }: { item: Item; edit?: string; onEdit?: (id: string, text: string) => void; editing?: boolean; disabled?: boolean }) {
  const conditions = Object.entries(item.conditions).filter(([, v]) => v !== null)
  return <article className="report-item" id={'item-' + item.id}>
    <div className="item-meta"><Badge status={edit !== undefined && edit !== item.text ? 'pending_review' : item.review.status} /><span>{item.kind === 'inference' ? 'Judgment' : item.kind === 'change' ? 'Change' : 'Fact'}</span>{item.effective_date && <time>{item.effective_date}</time>}</div>
    {editing ? <textarea aria-label="Edit item" className="item-editor" rows={5} disabled={disabled} value={edit ?? item.text} onChange={e => onEdit?.(item.id, e.target.value)} /> : <CitedText item={item} text={edit ?? item.text} />}
    {conditions.length > 0 && <dl className="conditions">{conditions.map(([k, v]) => <div key={k}><dt>{k.replaceAll('_', ' ')}</dt><dd>{String(v)}</dd></div>)}</dl>}
  </article>
}
export function TraceDetails({ spans }: { spans: TraceSpan[] }) {
  return <div className="trace-list">{spans.map(s => <details key={s.span_id}><summary><span>{s.agent_id || s.stage} · {s.purpose}</span><span className="muted">{s.total_tokens} tokens · {s.latency_ms} ms</span></summary><p className="muted">{s.model}</p><pre>{s.prompt}</pre><pre>{s.response}</pre></details>)}{!spans.length && <p className="muted">No diagnostic calls recorded yet.</p>}</div>
}
