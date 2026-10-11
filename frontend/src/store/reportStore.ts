import { create } from 'zustand'
import type { Report, ReportCard } from '../types'
import { fetchReport, fetchReports } from '../lib/api'
interface State {
  cards: ReportCard[]; reports: Record<string, Report>
  loadCards: () => Promise<void>; load: (id: string) => Promise<Report>; invalidate: (id: string) => void
}
export const useReportStore = create<State>((set) => ({
  cards: [], reports: {},
  loadCards: async () => { const cards = await fetchReports(); set({ cards }) },
  // Always fetch the current pointer; an old cached version must never hide a conflict.
  load: async id => { const report = await fetchReport(id); set(s => ({ reports: { ...s.reports, [id]: report } })); return report },
  invalidate: id => set(s => ({ reports: Object.fromEntries(Object.entries(s.reports).filter(([key]) => key !== id)) })),
}))
