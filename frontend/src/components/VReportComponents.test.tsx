// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { VReportComponents, VWrittenJudgments } from './VReportComponents'
import type { WrittenAssertion } from '../types'

afterEach(cleanup)

describe('planned report components', () => {
  it('renders selected components independently of chapter IDs and links caption citations', () => {
    const onCite = vi.fn()
    render(<VReportComponents onCite={onCite} evIndex={new Map([['e_1234', 1]])} components={[
      { kind: 'feature_tree', ref: 'features-for-purchasers', data: [{ brand: 'Acme', modules: [] }],
        caption: 'Capabilities under the evaluated plan [e_1234].' },
      { kind: 'data_grid', ref: 'cost-options', title: 'Purchase options',
        data: { columns: ['Option', 'Cost'], rows: [{ name: 'Annual purchase', value: '$120', metric: 'Cost', source: 'Acme', source_url: '' }] } },
    ]} />)
    expect(screen.getByText('Acme · feature tree')).toBeTruthy()
    expect(screen.getByText('Annual purchase')).toBeTruthy()
    fireEvent.click(screen.getByTitle('Jump to this source'))
    expect(onCite).toHaveBeenCalledWith(['e_1234'])
  })

  it('distinguishes inferences and recommendations with applicability conditions', () => {
    const base = { section_id: 'purchase', quote: '', evidence_ids: [], premise_claim_ids: [] }
    const assertions: WrittenAssertion[] = [
      { ...base, assertion_id: 'a1', kind: 'fact', text: 'Private fact metadata' },
      { ...base, assertion_id: 'a2', kind: 'inference', text: 'Annual billing reduces the modeled cost.', conditions: 'Constant seats for a year' },
      { ...base, assertion_id: 'a3', kind: 'recommendation', text: 'Pilot before committing.' },
    ]
    render(<VWrittenJudgments assertions={assertions} />)
    expect(screen.getByText('Inferences and recommendations (2)')).toBeTruthy()
    expect(screen.getByText('Inference:')).toBeTruthy()
    expect(screen.getByText('Recommendation:')).toBeTruthy()
    expect(screen.getByText('Applies when: Constant seats for a year')).toBeTruthy()
    expect(screen.queryByText('Private fact metadata')).toBeNull()
  })

  it('keeps absent metadata compatible with historical sections', () => {
    const { container } = render(<><VReportComponents onCite={vi.fn()} evIndex={new Map()} /><VWrittenJudgments /></>)
    expect(container.textContent).toBe('')
  })
})
