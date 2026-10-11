import { Badge } from './Research'
import type { Citation, Content } from '../types'

export function ReportReview({ content }: { content: Content }) {
  const items = [...content.comparison, ...content.brief, ...content.changes]
  function citation(value: Citation, index: number, reviewer = false) {
    const evidence = content.evidence.find(e => e.evidence_id === value.evidence_id)
    return <div className="review-citation" key={(reviewer ? 'review-' : '') + index}>
      {reviewer && <span className="eyebrow">Reviewer evidence</span>}
      {evidence ? <a href={evidence.source_url} target="_blank" rel="noreferrer">[{content.evidence.indexOf(evidence) + 1}] {evidence.title || evidence.source_url}</a> : <p className="error">Missing source: {value.evidence_id}</p>}
      <blockquote>{value.quote}</blockquote>
      {evidence?.limitation && <p className="muted">{evidence.limitation}</p>}
    </div>
  }
  return <section id="review" className="panel report-review">
    <h2>Review & limitations</h2>
    <h3>Unresolved questions and limitations</h3>
    {content.review_summary.issues?.map((issue, index) => <p key={issue.item_id + index}><a href={'#item-' + issue.item_id}>{issue.item_id}</a> · {issue.reason}</p>)}
    {content.limitations.map((limitation, index) => <p className="muted" key={index}>{limitation}</p>)}
    {!content.limitations.length && !content.review_summary.issues?.length && <p className="muted">No unresolved items were recorded in this version.</p>}
    <details className="report-review-items"><summary>Item reviews ({items.length})</summary>
      {items.map(item => <article className="review-record" key={item.id}>
        <div className="item-meta"><Badge status={item.review.status} /><a href={'#item-' + item.id}>Back to passage · {content.products.find(p => p.id === item.product_id)?.name || item.kind} · {content.topics.find(t => t.id === item.topic_id)?.name || item.id}</a></div>
        <p>{item.text}</p><p>{item.review.reason}</p>
        <p className="muted">Citation: {item.review.citation_valid === null ? 'Not checked' : item.review.citation_valid ? 'Valid' : 'Invalid or missing'} · Support: {item.review.support_checked ? 'Checked' : 'Not established'}</p>
        {item.depends_on.length > 0 && <p className="muted">Depends on: {item.depends_on.map((id, index) => <span key={id}>{index > 0 && ', '}<a href={'#item-' + id}>{id}</a></span>)}</p>}
        {item.citations.map((value, index) => citation(value, index))}
        {!item.citations.length && <p className="muted">No supporting source was supplied.</p>}
        {item.review.quotes?.filter(q => !item.citations.some(c => c.evidence_id === q.evidence_id && c.quote === q.quote)).map((value, index) => citation(value, index, true))}
      </article>)}
    </details>
    <details className="report-source-context"><summary>Stored source context ({content.evidence.length})</summary>
      {content.evidence.map((evidence, index) => <article className="review-record" key={evidence.evidence_id}>
        <a href={evidence.source_url} target="_blank" rel="noreferrer">[{index + 1}] {evidence.title || evidence.source_url}</a>
        <p className="muted">{evidence.attribution}</p>
        <p className="muted">Captured: {new Date(evidence.captured_at).toLocaleString('en-US')} · Published: {evidence.published_at || 'Unknown'}{evidence.published_date_basis && ' · Date basis: ' + evidence.published_date_basis}</p>
        {evidence.limitation && <p className="notice">{evidence.limitation}</p>}
        <blockquote>{evidence.excerpt}</blockquote>
        <pre className="source-context" tabIndex={0} aria-label={'Stored context for ' + (evidence.title || evidence.source_url)}>{evidence.context}</pre>
      </article>)}
    </details>
  </section>
}
