// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import catalogText from '../../public/assets/experts.json?raw'
import modulesText from '../../public/assets/industry_modules.json?raw'
import type { Expert, IndustryModule } from '../types'
import { useExpertStore } from '../store/expertStore'
import { useTaskStore } from '../store/taskStore'
import ExpertsPage from './ExpertsPage'
import ExpertDetailPage from './ExpertDetailPage'

const catalog = JSON.parse(catalogText) as Expert[]
const modules = JSON.parse(modulesText) as IndustryModule[]
const active = catalog.filter((e) => e.catalog_status === 'active')

beforeEach(() => {
  useExpertStore.setState({ experts: active, industryModules: modules,
    index: Object.fromEntries(catalog.map((e) => [e.id, e])), loaded: true, loading: false })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('research expertise catalog', () => {
  it('shows core analysts separately from searchable industry methods', () => {
    render(<MemoryRouter><ExpertsPage /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'Core Analysts (12)' })).toBeTruthy()
    const archived = catalog.find((e) => e.id === 'L1-008')!
    expect(screen.queryByText(archived.name)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Industry Modules (28)' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Search research expertise' }), { target: { value: 'cloud' } })
    expect(screen.getByRole('heading', { name: 'Cloud & infrastructure' })).toBeTruthy()
    expect(screen.queryByText(active[0].name)).toBeNull()
    expect(screen.getByText(modules.find((m) => m.id === 'cloud-infrastructure')!.checks[0])).toBeTruthy()
  })

  it('resolves archived analysts for historical links and marks their status', () => {
    const archived = useExpertStore.getState().byId('L1-008')!
    useExpertStore.setState({ index: { ...useExpertStore.getState().index,
      'L1-008': { ...archived, stats: { missions: 4, avg_evidence: 0, evidence_collected: 12, claims_authored: 7 } } } })
    render(<MemoryRouter initialEntries={['/experts/L1-008']}><Routes>
      <Route path="/experts/:id" element={<ExpertDetailPage />} />
    </Routes></MemoryRouter>)
    expect(screen.getByText('Archived analyst')).toBeTruthy()
    expect(screen.getByRole('heading', { name: catalog.find((e) => e.id === 'L1-008')!.name })).toBeTruthy()
    expect(screen.queryByText('Analyst not found.')).toBeNull()
    expect(screen.getByText('Claims authored')).toBeTruthy()
    expect(screen.getByText('7')).toBeTruthy()
  })

  it('retains archived identities in the index when loading offline catalogs', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.startsWith('/api/')) throw new Error('offline')
      return { json: async () => url.includes('industry_modules') ? modules : catalog }
    }))
    useExpertStore.setState({ experts: [], index: {}, industryModules: [], loaded: false })
    await useExpertStore.getState().load()
    expect(useExpertStore.getState().experts).toHaveLength(12)
    expect(useExpertStore.getState().industryModules).toHaveLength(28)
    expect(useExpertStore.getState().byId('L1-008')?.catalog_status).toBe('archived')
  })

  it('restores industry methods from team events without adding analyst headcount', () => {
    const task = useTaskStore.getState()
    task.reset('catalog_task', 'Cloud comparison')
    task.ingest('message', { kind: 'team', id: 'team', members: active.slice(0, 6).map((e) => e.id), industry_modules: modules.slice(0, 2) }, 1)
    expect(useTaskStore.getState().teamMembers).toHaveLength(6)
    expect(useTaskStore.getState().industryModules).toHaveLength(2)
    task.reset('old_task', 'Historical run')
    task.ingest('message', { kind: 'team', id: 'old_team', members: ['L1-008'] }, 1)
    expect(useTaskStore.getState().industryModules).toEqual([])
  })
})
