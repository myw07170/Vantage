import { create } from 'zustand'
import type { Report } from '../types'
import { fetchReport } from '../lib/api'

interface ReportState {
  cache: Record<string, Report>
  current: Report | null
  loading: boolean
  error: string | null
  load: (id: string) => Promise<void>
}

export const useReportStore = create<ReportState>((set, get) => ({
  cache: {},
  current: null,
  loading: false,
  error: null,
  load: async (id) => {
    const cached = get().cache[id]
    if (cached) {
      set({ current: cached, error: null })
      return
    }
    set({ loading: true, error: null, current: null })
    try {
      const report = await fetchReport(id)
      if (report && report.id) {
        set((s) => ({
          current: report,
          loading: false,
          cache: { ...s.cache, [id]: report },
        }))
      } else {
        set({ loading: false, error: 'This report does not exist or has expired.' })
      }
    } catch {
      set({ loading: false, error: 'Could not load the report.' })
    }
  },
}))
