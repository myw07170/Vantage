import { create } from 'zustand'
import type { Expert } from '../types'
import { fetchExperts } from '../lib/api'

interface ExpertState {
  experts: Expert[]
  index: Record<string, Expert>
  loaded: boolean
  loading: boolean
  load: () => Promise<void>
  byId: (id: string) => Expert | undefined
}

export const useExpertStore = create<ExpertState>((set, get) => ({
  experts: [],
  index: {},
  loaded: false,
  loading: false,
  load: async () => {
    if (get().loaded || get().loading) return
    set({ loading: true })
    try {
      const experts = await fetchExperts()
      // Indexed on load — `byId` is called per row in several long lists, and a
      // linear scan over the whole roster per row adds up.
      const index = Object.fromEntries(experts.map((e) => [e.id, e]))
      set({ experts, index, loaded: true, loading: false })
    } catch {
      set({ loading: false })
    }
  },
  byId: (id) => get().index[id],
}))
