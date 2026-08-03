import { create } from 'zustand'

/**
 * Reader annotations and a personal knowledge base.
 *
 * Persisted to localStorage only — clearing site data loses it. That is a
 * deliberate scope choice: annotations are personal working notes, not report
 * content, and keeping them client-side avoids a user model on the backend.
 */

export type HighlightColor = 'sun' | 'ok' | 'risk' | 'info'

export interface Highlight {
  id: string
  sectionId: string
  text: string
  color: HighlightColor
  comment: string
  createdAt: number
}

export interface ReportAnnotations {
  edits: Record<string, string> // blockId -> edited text
  highlights: Highlight[]
}

export type KBKind = 'claim' | 'evidence' | 'quote' | 'figure' | 'note' | 'highlight'

export interface KBEntry {
  id: string
  reportId: string
  reportTitle: string
  kind: KBKind
  title: string
  content: string
  sourceUrl?: string
  evidenceId?: string
  brand?: string
  imageSrc?: string
  tags: string[]
  createdAt: number
}

interface AnnotationState {
  annotations: Record<string, ReportAnnotations>
  knowledge: KBEntry[]
  setEdit: (reportId: string, blockId: string, text: string) => void
  getEdit: (reportId: string, blockId: string) => string | undefined
  addHighlight: (reportId: string, h: Omit<Highlight, 'id' | 'createdAt'>) => void
  updateHighlight: (reportId: string, id: string, patch: Partial<Highlight>) => void
  removeHighlight: (reportId: string, id: string) => void
  addToKB: (entry: Omit<KBEntry, 'id' | 'createdAt'>) => boolean
  removeFromKB: (id: string) => void
  isInKB: (reportId: string, content: string, kind: KBKind) => boolean
}

const LS_KEY = 'vantage.annotations.v1'
const LS_KB = 'vantage.knowledge.v1'

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* quota exceeded — annotations are best-effort */
  }
}

function uid(p: string) {
  return `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`
}

export const useAnnotationStore = create<AnnotationState>((set, get) => ({
  annotations: load<Record<string, ReportAnnotations>>(LS_KEY, {}),
  knowledge: load<KBEntry[]>(LS_KB, []),

  setEdit: (reportId, blockId, text) =>
    set((s) => {
      const cur = s.annotations[reportId] ?? { edits: {}, highlights: [] }
      const next = {
        ...s.annotations,
        [reportId]: { ...cur, edits: { ...cur.edits, [blockId]: text } },
      }
      save(LS_KEY, next)
      return { annotations: next }
    }),

  getEdit: (reportId, blockId) => get().annotations[reportId]?.edits[blockId],

  addHighlight: (reportId, h) =>
    set((s) => {
      const cur = s.annotations[reportId] ?? { edits: {}, highlights: [] }
      const hl: Highlight = { ...h, id: uid('hl'), createdAt: Date.now() }
      const next = {
        ...s.annotations,
        [reportId]: { ...cur, highlights: [...cur.highlights, hl] },
      }
      save(LS_KEY, next)
      return { annotations: next }
    }),

  updateHighlight: (reportId, id, patch) =>
    set((s) => {
      const cur = s.annotations[reportId]
      if (!cur) return s
      const next = {
        ...s.annotations,
        [reportId]: {
          ...cur,
          highlights: cur.highlights.map((h) => (h.id === id ? { ...h, ...patch } : h)),
        },
      }
      save(LS_KEY, next)
      return { annotations: next }
    }),

  removeHighlight: (reportId, id) =>
    set((s) => {
      const cur = s.annotations[reportId]
      if (!cur) return s
      const next = {
        ...s.annotations,
        [reportId]: { ...cur, highlights: cur.highlights.filter((h) => h.id !== id) },
      }
      save(LS_KEY, next)
      return { annotations: next }
    }),

  addToKB: (entry) => {
    if (get().isInKB(entry.reportId, entry.content, entry.kind)) return false
    set((s) => {
      const e: KBEntry = { ...entry, id: uid('kb'), createdAt: Date.now() }
      const next = [e, ...s.knowledge]
      save(LS_KB, next)
      return { knowledge: next }
    })
    return true
  },

  removeFromKB: (id) =>
    set((s) => {
      const next = s.knowledge.filter((k) => k.id !== id)
      save(LS_KB, next)
      return { knowledge: next }
    }),

  // Matches on kind as well as content, so saving the same text as both a quote
  // and a note is allowed while a true duplicate is not.
  isInKB: (reportId, content, kind) =>
    get().knowledge.some(
      (k) => k.reportId === reportId && k.content === content && k.kind === kind,
    ),
}))
