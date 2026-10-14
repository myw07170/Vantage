import { create } from 'zustand'
import type { Expert, IndustryModule } from '../types'
import { fetchExperts, fetchIndustryModules } from '../lib/api'

interface ExpertState {
  experts: Expert[]
  industryModules: IndustryModule[]
  index: Record<string, Expert>
  loaded: boolean
  loading: boolean
  load: () => Promise<void>
  byId: (id: string) => Expert | undefined
}

export const useExpertStore = create<ExpertState>((set, get) => ({
  experts: [],
  industryModules: [],
  index: {},
  loaded: false,
  loading: false,
  load: async () => {
    if (get().loaded || get().loading) return
    set({ loading: true })
    try {
      const [catalog, industryModules] = await Promise.all([fetchExperts(), fetchIndustryModules()])
      const experts = catalog.filter((e) => e.catalog_status !== 'archived')
      // Indexed on load — `byId` is called per row in several long lists, and a
      // linear scan over the whole roster per row adds up.
      const index = Object.fromEntries(catalog.map((e) => [e.id, e]))
      set({ experts, index, industryModules, loaded: true, loading: false })
    } catch {
      set({ loading: false })
    }
  },
  byId: (id) => get().index[id],
}))
