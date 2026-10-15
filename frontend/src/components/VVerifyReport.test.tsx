// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { VVerifyReport } from './VVerifyReport'

afterEach(cleanup)

describe('written report verification', () => {
  it('never presents simulated verification as real approval', () => {
    render(<VVerifyReport review={{ verdict: 'pass', simulated: true, findings: [] }} />)
    expect(screen.getByText('Simulated · not verified')).toBeTruthy()
    expect(screen.getByText(/Real evidence support/)).toBeTruthy()
    expect(screen.queryByText('✓ Verified')).toBeNull()
  })

  it('keeps every remaining minor finding visible', () => {
    render(<VVerifyReport review={{ verdict: 'flagged', findings: Array.from({ length: 12 }, (_, i) => ({
      finding_id: `f${i}`, section_id: 'purchasing', severity: 'minor', kind: 'vague', detail: `Clarify condition ${i}`, auto_fixed: false,
    })) }} />)
    expect(screen.getByText('Clarify condition 11')).toBeTruthy()
  })
})
