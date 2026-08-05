import { create } from 'zustand'
import type { Report, ReportCard } from '../types'
import { fetchReport, fetchReports } from '../lib/api'

interface ReportState {
  cache: Record<string, Report>
  current: Report | null
  loading: boolean
  error: string | null
  load: (id: string) => Promise<void>

  /** The report list, shared by the sidebar and the library so a delete in one
   *  is reflected in the other. Held in a store rather than in each view's own
   *  state: the sidebar outlives the library, so a locally-filtered list there
   *  would leave a phantom entry in the sidebar pointing at a deleted report. */
  cards: ReportCard[]
  cardsLoading: boolean
  loadCards: () => Promise<void>
  removeCard: (id: string) => void
}

/** The sidebar and the library both mount at once and both want the list; this
 *  shares the request instead of firing it twice. */
let cardsInFlight: Promise<void> | null = null

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

  cards: [],
  // True only while there is nothing to show yet. A refetch behind an existing
  // list must not blank it — the sidebar refetches every time the shell
  // remounts, and swapping the list for skeletons each time would flicker.
  cardsLoading: true,
  loadCards: () => {
    if (cardsInFlight) return cardsInFlight
    cardsInFlight = fetchReports()
      .then((cards) => set({ cards }))
      .finally(() => {
        set({ cardsLoading: false })
        cardsInFlight = null
      })
    return cardsInFlight
  },
  removeCard: (id) =>
    set((s) => ({
      cards: s.cards.filter((c) => c.id !== id),
      // Drop the detail cache too, or reopening the id would serve the deleted
      // report from memory instead of reporting it gone.
      cache: Object.fromEntries(Object.entries(s.cache).filter(([k]) => k !== id)),
    })),
}))
