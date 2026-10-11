import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import { Badge, EvidenceCard, ItemView } from './Research'
import { ReportReview } from './ReportReview'
import type { Content, Evidence, Item } from '../types'
const evidence: Evidence = { evidence_id: 'ev', product_id: 'product', topic_id: 'pricing', source_type: 'external', source_url: 'https://review.test/pricing', title: 'Review', context: 'Full source context', excerpt: 'Original excerpt', captured_at: '2026-10-10T12:00:00Z', published_at: null, published_date_basis: '', attribution: 'External experience', limitation: 'Search excerpt only', degraded: true }
const item: Item = { id: 'fact', product_id: 'product', topic_id: 'pricing', kind: 'fact', text: 'Original', citations: [{ evidence_id: 'ev', quote: 'Cited passage' }], depends_on: ['other-fact'], conditions: {}, effective_date: null, review: { status: 'supported', citation_valid: true, support_checked: true, reason: 'Supported by evidence', evidence_ids: ['ev'], checked_at: null, quotes: [{ evidence_id: 'ev', quote: 'Reviewer passage' }, { evidence_id: 'missing', quote: 'Unavailable passage' }] } }
it('renders four distinct review states without a quality score', () => {
  for (const [status, label] of [['supported', 'Supported'], ['unknown', 'Unknown'], ['conflicting', 'Conflicting'], ['pending_review', 'Pending review']] as const) {
    expect(renderToStaticMarkup(<Badge status={status} />)).toContain(label)
  }
})
it('separates source publication and verification dates and shows fetch limitations', () => {
  const html = renderToStaticMarkup(<EvidenceCard evidence={evidence} />)
  expect(html).toContain('Published: Unknown')
  expect(html).toContain('External source')
  expect(html).toContain('Search excerpt only')
})
it('opens each source directly and distinguishes unknown provenance from external sources', () => {
  for (const [source_type, label] of [['official', 'Vendor source'], ['external', 'External source'], ['unknown', 'Unknown source']] as const) {
    const html = renderToStaticMarkup(<EvidenceCard evidence={{ ...evidence, source_type }} index={0} active />)
    expect(html).toContain('href="https://review.test/pricing"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noreferrer"')
    expect(html).toContain('source-' + source_type)
    expect(html).toContain(label)
    expect(html).toContain('review.test')
    expect(html).not.toContain('<details')
    expect(html.match(/<a /g)).toHaveLength(1)
  }
})
it('marks unsaved edits pending without changing the stored status', () => {
  const html = renderToStaticMarkup(<ItemView item={item} edit="Human correction" editing />)
  expect(html).toContain('Pending review')
  expect(html).toContain('Human correction')
  expect(item.review.status).toBe('supported')
})
it('edits passages only in report edit mode, without per-item actions or reviews', () => {
  const reading = renderToStaticMarkup(<ItemView item={item} />)
  expect(reading).toContain('data-item-text="fact"')
  expect(reading).not.toContain('<textarea')
  expect(reading).not.toContain('<button')
  expect(reading).not.toContain('Review and evidence')
  expect(reading).not.toContain('Supported by evidence')
  const editing = renderToStaticMarkup(<ItemView item={item} editing disabled />)
  expect(editing).toContain('<textarea')
  expect(editing).toContain('disabled=""')
  expect(editing).not.toContain('data-item-text')
})
it('retains review reasons, reviewer-only quotes, missing sources and full context in the central review', () => {
  const content = { comparison: [item], brief: [], changes: [], evidence: [evidence], products: [], topics: [], review_summary: {}, limitations: ['Overall limitation'] } as unknown as Content
  const html = renderToStaticMarkup(<ReportReview content={content} />)
  for (const text of ['Supported by evidence', 'Citation: Valid', 'Support: Checked', 'Cited passage', 'Reviewer passage', 'Missing source: missing', 'Full source context', 'External experience', 'Search excerpt only', 'Overall limitation']) expect(html).toContain(text)
  expect(html).toContain('href="#item-fact"')
  expect(html).toContain('href="#item-other-fact"')
  expect(html).not.toContain('data-item-text')
})
