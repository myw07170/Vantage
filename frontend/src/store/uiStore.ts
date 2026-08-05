import { create } from 'zustand'

interface UIState {
  sidebarCollapsed: boolean
  toggleSidebar: () => void
  setSidebar: (v: boolean) => void
  /** Toast message, set by the API error listener. */
  toast: string | null
  setToast: (t: string | null) => void
}

// Collapsing the rail is a workspace preference, not a per-page one: it has to
// survive navigation and reload, or every route change would undo it.
const COLLAPSE_KEY = 'vantage.sidebar-collapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1'
  } catch {
    return false // private mode, or storage disabled — expanded is the safe default
  }
}

function writeCollapsed(v: boolean) {
  try {
    localStorage.setItem(COLLAPSE_KEY, v ? '1' : '0')
  } catch {
    /* preference is not worth failing a click over */
  }
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: readCollapsed(),
  toggleSidebar: () =>
    set((s) => {
      writeCollapsed(!s.sidebarCollapsed)
      return { sidebarCollapsed: !s.sidebarCollapsed }
    }),
  setSidebar: (v) => {
    writeCollapsed(v)
    set({ sidebarCollapsed: v })
  },
  toast: null,
  setToast: (toast) => set({ toast }),
}))
