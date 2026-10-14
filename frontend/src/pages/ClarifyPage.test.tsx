// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { TaskDetail } from '../types'
import { fetchTask, submitClarify, submitScope } from '../lib/api'
import ClarifyPage from './ClarifyPage'

vi.mock('../lib/api', () => ({ fetchTask: vi.fn(), submitScope: vi.fn(), submitClarify: vi.fn() }))

const initial: TaskDetail = {
  taskId: 't_test', query: 'compare Claude Code and Codex', mode: 'quick', status: 'created',
  reportId: null, error: '', terminalSeq: 0, clarificationStage: 'scope', scopeRevision: 1,
  researchBrief: 'Compare terminal coding tools', answers: { products: ['Claude Code', 'Codex'] },
  clarificationRevision: 1, clarificationError: '', questionDraft: {}, researchContext: {},
  canStartResearch: false, researchReady: false, productChangeRequested: false,
  clarifyQuestions: [{ id: 'scope', type: 'single', question: 'Is this about terminal coding tools?',
    options: ['Yes, continue', 'Roughly right', 'No'] }],
}
const products: TaskDetail = { ...initial, clarificationStage: 'products', clarificationRevision: 2,
  clarifyQuestions: [{ id: 'products', type: 'multi', question: 'Which products should we research?',
    options: ['Claude Code', 'Codex', 'Aider', 'Continue'], defaultSelected: ['Claude Code', 'Codex'] }] }
const market: TaskDetail = { ...products, clarificationStage: 'market', clarificationRevision: 3,
  clarifyQuestions: [{ id: 'market', type: 'single', question: 'Which market should we focus on?',
    options: ['United States', 'North America', 'Global', 'EMEA', 'APAC', 'No preference'] }] }
const followup: TaskDetail = { ...market, clarificationStage: 'clarify', clarificationRevision: 4,
  canStartResearch: true, answers: { products: ['Claude Code', 'Codex'], market: 'Global' },
  clarifyQuestions: [{ id: 'followup_4', field: 'purpose', type: 'single',
    question: 'What decision will this research support?', options: ['Choose for myself', 'Choose for a team', 'Competitive research'],
    hint: 'This shapes the decision criteria and recommendations in your report.' }] }
const ready: TaskDetail = { ...followup, clarificationStage: 'ready', clarificationRevision: 5,
  clarifyQuestions: [], researchContext: { purpose: 'Choose for a team', audience: 'Five developers' } }

function correction(revision: number, question: string): TaskDetail {
  return { ...initial, scopeRevision: revision, researchBrief: question,
    clarifyQuestions: [{ ...initial.clarifyQuestions[0], question }] }
}
function openPage() {
  return render(<MemoryRouter initialEntries={['/clarify/t_test']}><Routes>
    <Route path="/clarify/:taskId" element={<ClarifyPage />} />
    <Route path="/workspace/:taskId" element={<p>Research workspace</p>} />
  </Routes></MemoryRouter>)
}
beforeEach(() => { vi.resetAllMocks(); sessionStorage.clear(); vi.mocked(fetchTask).mockResolvedValue(initial) })
afterEach(cleanup)

describe('adaptive clarification', () => {
  it('supports repeated topic corrections and confirms products before showing market', async () => {
    openPage()
    await screen.findByText('Is this about terminal coding tools?')
    expect(screen.queryByText('Which market should we focus on?')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Start research' })).toBeNull()
    const input = screen.getByLabelText('Describe a correction') as HTMLTextAreaElement
    expect(input.rows).toBe(1)
    fireEvent.click(screen.getByRole('button', { name: 'Roughly right' }))
    expect(document.activeElement).toBe(input)
    expect((screen.getByRole('button', { name: 'Submit correction' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(input, { target: { value: 'Include IDE and cloud' } })
    expect((screen.getByRole('button', { name: 'Yes, continue' }) as HTMLButtonElement).disabled).toBe(true)
    let finish!: (value: TaskDetail & { ok: true }) => void
    vi.mocked(submitScope).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit correction' }))
    expect((screen.getByRole('button', { name: 'Updating our understanding…' }) as HTMLButtonElement).disabled).toBe(true)
    await act(async () => { finish({ ok: true, ...correction(2, 'Is this about IDE and cloud workflows?') }) })
    expect((screen.getByLabelText('Describe a correction') as HTMLTextAreaElement).value).toBe('')
    for (const label of ['Yes, continue', 'Roughly right', 'No']) {
      expect(screen.getByRole('button', { name: label }).getAttribute('aria-pressed')).toBe('false')
    }
    fireEvent.click(screen.getByRole('button', { name: 'No' }))
    fireEvent.change(screen.getByLabelText('Describe a correction'), { target: { value: 'Focus on cloud' } })
    vi.mocked(submitScope).mockResolvedValueOnce({ ok: true, ...correction(3, 'Is this about cloud workflows?') })
    fireEvent.click(screen.getByRole('button', { name: 'Submit correction' }))
    await screen.findByText('Is this about cloud workflows?')
    vi.mocked(submitScope).mockResolvedValueOnce({ ok: true, ...products, scopeRevision: 3 })
    fireEvent.click(screen.getByRole('button', { name: 'Yes, continue' }))
    await screen.findByText('Which products should we research?')
    expect(screen.queryByText('Which market should we focus on?')).toBeNull()
    expect(submitClarify).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Claude Code' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: 'Aider' }).getAttribute('aria-pressed')).toBe('false')
  })

  it('submits unadded product input on Continue and combines market choices with free text', async () => {
    vi.mocked(fetchTask).mockResolvedValue(products)
    openPage()
    await screen.findByText('Which products should we research?')
    fireEvent.change(screen.getByLabelText('Add another product'), { target: { value: 'Custom Product, Other Tool' } })
    vi.mocked(submitClarify).mockResolvedValueOnce({ ok: true, ...market })
    fireEvent.click(screen.getByRole('button', { name: /^(Confirm products|Confirm market|Submit answer)$/ }))
    await screen.findByText('Which market should we focus on?')
    expect(submitClarify).toHaveBeenNthCalledWith(1, 't_test', { products: ['Claude Code', 'Codex'] },
      { action: 'answer', clarificationRevision: 2, text: 'Custom Product, Other Tool' })
    fireEvent.click(screen.getByRole('button', { name: 'Global' }))
    fireEvent.change(screen.getByLabelText('Your answer or additional details'), { target: { value: 'English-speaking teams' } })
    vi.mocked(submitClarify).mockResolvedValueOnce({ ok: true, ...followup })
    fireEvent.click(screen.getByRole('button', { name: /^(Confirm products|Confirm market|Submit answer)$/ }))
    await screen.findByText('What decision will this research support?')
    expect(submitClarify).toHaveBeenNthCalledWith(2, 't_test', { market: 'Global' },
      { action: 'answer', clarificationRevision: 3, text: 'English-speaking teams' })
    expect(screen.queryByText('Whose perspective should the report be written from?')).toBeNull()
    expect(screen.getByRole('button', { name: 'Start with current information' })).toBeTruthy()
  })

  it('accepts an option-only answer, stops when ready, and starts only on the final action', async () => {
    vi.mocked(fetchTask).mockResolvedValue(followup)
    openPage()
    await screen.findByText('What decision will this research support?')
    fireEvent.click(screen.getByRole('button', { name: 'Choose for a team' }))
    vi.mocked(submitClarify).mockResolvedValueOnce({ ok: true, ...ready })
    fireEvent.click(screen.getByRole('button', { name: /^(Confirm products|Confirm market|Submit answer)$/ }))
    await screen.findByText('We have enough information to begin.')
    expect(submitClarify).toHaveBeenCalledTimes(1)
    expect(submitClarify).toHaveBeenCalledWith('t_test', { followup_4: 'Choose for a team' },
      { action: 'answer', clarificationRevision: 4, text: '' })
    vi.mocked(submitClarify).mockResolvedValueOnce({ ok: true, ...ready, researchReady: true, status: 'clarified' })
    fireEvent.click(screen.getByRole('button', { name: 'Start research' }))
    await screen.findByText('Research workspace')
    expect(submitClarify).toHaveBeenLastCalledWith('t_test', {}, { action: 'start', clarificationRevision: 5, text: '' })
  })

  it('accepts text-only answers and grows the initially one-line input', async () => {
    vi.mocked(fetchTask).mockResolvedValue(followup)
    openPage()
    await screen.findByText('What decision will this research support?')
    const input = screen.getByLabelText('Your answer or additional details') as HTMLTextAreaElement
    expect(input.rows).toBe(1)
    Object.defineProperty(input, 'scrollHeight', { configurable: true, value: 72 })
    fireEvent.change(input, { target: { value: 'Choose for a five-person team with strict permissions' } })
    expect(input.style.height).toBe('72px')
    vi.mocked(submitClarify).mockResolvedValueOnce({ ok: true, ...ready })
    fireEvent.click(screen.getByRole('button', { name: /^(Confirm products|Confirm market|Submit answer)$/ }))
    await screen.findByText('We have enough information to begin.')
    expect(submitClarify).toHaveBeenCalledWith('t_test', { followup_4: '' }, {
      action: 'answer', clarificationRevision: 4, text: 'Choose for a five-person team with strict permissions',
    })
  })

  it('restores unsubmitted product selections and one-line input after a reload', async () => {
    vi.mocked(fetchTask).mockResolvedValue(products)
    const first = openPage()
    await screen.findByText('Which products should we research?')
    fireEvent.click(screen.getByRole('button', { name: 'Claude Code' }))
    fireEvent.change(screen.getByLabelText('Add another product'), { target: { value: 'Unsubmitted Product' } })
    first.unmount()
    openPage()
    await screen.findByText('Which products should we research?')
    expect(screen.getByRole('button', { name: 'Claude Code' }).getAttribute('aria-pressed')).toBe('false')
    expect((screen.getByLabelText('Add another product') as HTMLTextAreaElement).value).toBe('Unsubmitted Product')
  })

  it('retains selected and custom answers on model failure, and permits a retry', async () => {
    vi.mocked(fetchTask).mockResolvedValue(followup)
    openPage()
    await screen.findByText('What decision will this research support?')
    fireEvent.click(screen.getByRole('button', { name: 'Choose for a team' }))
    fireEvent.change(screen.getByLabelText('Your answer or additional details'), { target: { value: 'Five developers' } })
    vi.mocked(submitClarify).mockResolvedValueOnce({ ok: true, ...followup, clarificationRevision: 5,
      clarificationError: 'Your answers are saved. Retry or start research.',
      questionDraft: { selected: ['Choose for a team'], text: 'Five developers' } })
    fireEvent.click(screen.getByRole('button', { name: /^(Confirm products|Confirm market|Submit answer)$/ }))
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: 'Choose for a team' }).getAttribute('aria-pressed')).toBe('true')
    expect((screen.getByLabelText('Your answer or additional details') as HTMLTextAreaElement).value).toBe('Five developers')
    expect(screen.getByRole('button', { name: 'Start with current information' })).toBeTruthy()
    vi.mocked(submitClarify).mockResolvedValueOnce({ ok: true, ...ready, clarificationRevision: 6 })
    fireEvent.click(screen.getByRole('button', { name: 'Retry question generation' }))
    await screen.findByText('We have enough information to begin.')
    expect(submitClarify).toHaveBeenLastCalledWith('t_test', { followup_4: 'Choose for a team' },
      { action: 'retry', clarificationRevision: 5, text: '' })
  })

  it('returns to product confirmation when a dynamic answer changes products', async () => {
    vi.mocked(fetchTask).mockResolvedValue(followup)
    openPage()
    await screen.findByText('What decision will this research support?')
    fireEvent.change(screen.getByLabelText('Your answer or additional details'), { target: { value: 'Compare Cursor instead' } })
    vi.mocked(submitClarify).mockResolvedValueOnce({ ok: true, ...products,
      clarificationRevision: 5, productChangeRequested: true })
    fireEvent.click(screen.getByRole('button', { name: /^(Confirm products|Confirm market|Submit answer)$/ }))
    await screen.findByText('Which products should we research?')
    expect(screen.getByRole('status').textContent).toContain('Confirm the updated selections')
    expect(screen.queryByRole('button', { name: 'Start with current information' })).toBeNull()
  })

  it('keeps the current question on stale or failed requests', async () => {
    vi.mocked(fetchTask).mockResolvedValue(followup)
    openPage()
    await screen.findByText('What decision will this research support?')
    fireEvent.change(screen.getByLabelText('Your answer or additional details'), { target: { value: 'A decision' } })
    vi.mocked(submitClarify).mockResolvedValueOnce({ ok: false, message: 'The question changed. Reload it.' })
    fireEvent.click(screen.getByRole('button', { name: /^(Confirm products|Confirm market|Submit answer)$/ }))
    await screen.findByRole('alert')
    expect((screen.getByLabelText('Your answer or additional details') as HTMLTextAreaElement).value).toBe('A decision')
    expect(screen.queryByText('We have enough information to begin.')).toBeNull()
  })
})
