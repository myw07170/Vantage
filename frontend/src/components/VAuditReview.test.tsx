// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { VAuditReview } from './VAuditReview'
import { VAuditMaterials } from './VAuditMaterials'

afterEach(cleanup)

describe('pre-write audit results', () => {
  it('keeps historical review cards readable', () => {
    render(<VAuditReview review={{ before: { verdict: 'pass', scores: { Coverage: 84 }, review: 'Historical approval' } }} />)
    expect(screen.getByText('✓ Approved')).toBeTruthy()
    expect(screen.getByText('Historical approval')).toBeTruthy()
  })

  it('shows blocked status, rounds and actual issue outcomes separately from scores', () => {
    render(<VAuditReview review={{ status: 'blocked', rework_rounds: 2, issues_resolved: 0,
      before: { verdict: 'rework', scores: { Coverage: 20 } },
      after: { verdict: 'rework', scores: { Coverage: 90 }, review: 'Core claim still unsupported' },
      history: [{ round: 0, review: { verdict: 'rework' } }, { round: 2, review: { verdict: 'rework' } }],
      issue_outcomes: [{ issue_id: 'i', target: 'c', brand: 'Acme', dimension: 'Pricing',
        severity: 'high', action: 'collect', reason: 'Missing price evidence', fix: 'Find original terms', status: 'still_open' }] }} />)
    expect(screen.getByText('Blocked · serious issues remain')).toBeTruthy()
    expect(screen.getByText('Review history (2)')).toBeTruthy()
    expect(screen.getByText('Acme Pricing: Missing price evidence')).toBeTruthy()
    expect(screen.getByText(/resolving 0 issues/)).toBeTruthy()
  })

  it('marks simulations and evidenced unknowns without claiming real approval', () => {
    render(<VAuditReview review={{ status: 'simulated', simulated: true,
      before: { verdict: 'pass' }, unknowns: [{ brand: 'Acme', dimension: 'Pricing', reason: 'Not disclosed' }] }} />)
    expect(screen.getByText('Simulated · not verified')).toBeTruthy()
    expect(screen.queryByText('✓ Approved')).toBeNull()
    expect(screen.getByText('Acme · Pricing: Not disclosed')).toBeTruthy()
  })

  it('makes failed research sources and saved text available', () => {
    render(<VAuditMaterials snapshot={{ task_id: 't', analysis: { claims: [] },
      evidence: [{ evidence_id: 'e', source_url: 'https://acme.example/pricing', source_type: 'official',
        title: 'Pricing', excerpt: 'Short excerpt', full_text: 'Saved longer pricing conditions', content_kind: 'body',
        captured_at: '', credibility: 70, collected_by: 'collector', brand: 'Acme' }],
      searches: [{ search_id: 's', query: 'Acme price', status: 'error', error: 'quota exhausted' }] }} />)
    expect(screen.getByText('Saved longer pricing conditions')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'https://acme.example/pricing' }).getAttribute('href')).toBe('https://acme.example/pricing')
    expect(screen.getByText(/Failed: quota exhausted/)).toBeTruthy()
    expect(screen.getByText(/not an approved report/)).toBeTruthy()
  })

  it('shows preserved writing drafts, material use and unresolved verification findings', () => {
    render(<VAuditMaterials snapshot={{ task_id: 't', writing_status: 'blocked',
      writing_error: 'Serious written-report issues remain.',
      drafts: { purchase: { paragraphs: ['Retained complete purchasing argument'] } },
      material_usage: [{ id: 'e_1234', kind: 'evidence', chapters: ['purchase'], read_by: ['purchase'], reason: 'Price conditions' }],
      writing_verification: { findings: [{ section_id: 'purchase', severity: 'major', detail: 'Unsupported annual price', fix: 'Use the published billing terms' }] } }} />)
    expect(screen.getByText('Writing: blocked')).toBeTruthy()
    expect(screen.getByText('Retained complete purchasing argument')).toBeTruthy()
    expect(screen.getByText('Writing verification issues (1)')).toBeTruthy()
    expect(screen.getByText(/Unsupported annual price/)).toBeTruthy()
    expect(screen.getByText(/Read by: purchase/)).toBeTruthy()
  })
})
