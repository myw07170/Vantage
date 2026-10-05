import { beforeEach, expect, it } from 'vitest'
import type { Report, ReportCard } from '../types'
import { useReportStore } from './reportStore'

const report: Report = { id: 'r_1', title: 'Before', subtitle: 'Real report', created_at: '',
  experts: [], toc: [], sections: [], charts: [], evidence: [], claims: [], glossary: [] }

beforeEach(() => {
  useReportStore.setState({ current: report, cache: { r_1: report },
    cards: [{ id: 'r_1', title: report.title, subtitle: report.subtitle, starred: true } as ReportCard] })
})

it('updates mock metadata, details and list together after refinement', () => {
  const updated = { ...report, subtitle: '[MOCK] 模拟报告', is_mock: true, llm_provider: 'mock' as const }
  useReportStore.getState().replaceReport(updated)
  const state = useReportStore.getState()
  expect(state.current?.is_mock).toBe(true)
  expect(state.cache.r_1.subtitle).toContain('[MOCK]')
  expect(state.cards[0].subtitle).toContain('[MOCK]')
  expect(state.cards[0].starred).toBe(true)
})

it('keeps rename consistent and drops a deleted report from all caches', () => {
  useReportStore.getState().patchCard('r_1', { title: 'After' })
  expect(useReportStore.getState().current?.title).toBe('After')
  expect(useReportStore.getState().cache.r_1.title).toBe('After')
  useReportStore.getState().removeCard('r_1')
  expect(useReportStore.getState().current).toBeNull()
  expect(useReportStore.getState().cards).toEqual([])
  expect(useReportStore.getState().cache).toEqual({})
})
