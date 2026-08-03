import type {
  CreateTaskResp,
  DashboardStats,
  EvidenceQueryResp,
  Expert,
  ExpertWorkload,
  Report,
  ReportCard,
  ReportSection,
  SSEEventType,
  StreamStatus,
  Subscription,
  TraceSpan,
} from '../types'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

/** Set by `safeJson` when a request fails; the UI surfaces it in a toast. */
export type ApiErrorListener = (message: string) => void
let onApiError: ApiErrorListener | null = null
export function setApiErrorListener(fn: ApiErrorListener | null) {
  onApiError = fn
}

/**
 * Fetch JSON, falling back rather than throwing.
 *
 * The fallback keeps a failed request from blanking the screen, but unlike a
 * silent catch it also reports the failure so a broken backend is visible
 * instead of looking like an empty database.
 */
async function safeJson<T>(path: string, init?: RequestInit, fallback?: T): Promise<T> {
  try {
    const r = await fetch(`${API_BASE}${path}`, init)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return (await r.json()) as T
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    onApiError?.(`Request failed: ${path} (${msg})`)
    if (fallback !== undefined) return fallback
    throw e
  }
}

/** The roster, from the backend or the bundled copy if it is unreachable. */
export async function fetchExperts(): Promise<Expert[]> {
  try {
    const r = await fetch(`${API_BASE}/api/experts`)
    if (r.ok) {
      const data = await r.json()
      if (Array.isArray(data) && data.length) return data
      if (data?.experts?.length) return data.experts
    }
  } catch {
    /* fall through to the bundled copy */
  }
  const local = await fetch('/assets/experts.json')
  return (await local.json()) as Expert[]
}

export async function createTask(
  query: string,
  mode: string = 'deep',
): Promise<CreateTaskResp> {
  return safeJson<CreateTaskResp>(
    '/api/tasks',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, mode }),
    },
    { taskId: '', needClarify: false },
  )
}

export async function submitClarify(
  taskId: string,
  answers: Record<string, unknown>,
): Promise<{ ok: boolean }> {
  return safeJson(
    `/api/tasks/${taskId}/clarify`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers }),
    },
    { ok: true },
  )
}

export async function fetchReport(reportId: string): Promise<Report | null> {
  return safeJson<Report | null>(`/api/reports/${reportId}`, undefined, null)
}

export async function fetchReportTrace(reportId: string): Promise<{ spans: TraceSpan[] }> {
  return safeJson<{ spans: TraceSpan[] }>(`/api/reports/${reportId}/trace`, undefined, {
    spans: [],
  })
}

export async function submitFeedback(
  reportId: string,
  editedBlocks: number,
  totalBlocks: number,
  data: Record<string, unknown> = {},
): Promise<{ ok: boolean }> {
  return safeJson(
    `/api/reports/${reportId}/feedback`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        edited_blocks: editedBlocks,
        total_blocks: totalBlocks,
        data,
      }),
    },
    { ok: true },
  )
}

export async function refineSection(
  reportId: string,
  sectionId: string,
  annotations: string[],
): Promise<{ ok: boolean; section?: ReportSection; message?: string }> {
  return safeJson(
    `/api/reports/${reportId}/refine`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section_id: sectionId, annotations }),
    },
    { ok: false, message: 'Request failed' },
  )
}

export async function fetchReports(): Promise<ReportCard[]> {
  return safeJson<ReportCard[]>('/api/reports', undefined, [])
}

/** Deletes the report and everything derived from it: evidence, traces, feedback. */
export async function deleteReport(
  reportId: string,
): Promise<{ ok: boolean; message?: string }> {
  return safeJson(`/api/reports/${reportId}`, { method: 'DELETE' }, {
    ok: false,
    message: 'Request failed',
  })
}

export async function fetchDashboard(): Promise<DashboardStats | null> {
  return safeJson<DashboardStats | null>('/api/dashboard', undefined, null)
}

export async function fetchEvidences(params?: {
  brand?: string
  source_type?: string
  min_cred?: number
}): Promise<EvidenceQueryResp> {
  const qs = new URLSearchParams()
  if (params?.brand) qs.set('brand', params.brand)
  if (params?.source_type) qs.set('source_type', params.source_type)
  if (params?.min_cred != null) qs.set('min_cred', String(params.min_cred))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return safeJson<EvidenceQueryResp>(`/api/evidences${suffix}`, undefined, {
    items: [],
    facets: { total: 0, by_type: {}, by_brand: {} },
  })
}

export async function fetchSubscriptions(): Promise<Subscription[]> {
  return safeJson<Subscription[]>('/api/subscriptions', undefined, [])
}

export async function createSubscription(
  query: string,
  brands: string[],
): Promise<Subscription | null> {
  return safeJson<Subscription | null>(
    '/api/subscriptions',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, brands }),
    },
    null,
  )
}

export async function deleteSubscription(subId: string): Promise<{ ok: boolean }> {
  return safeJson(`/api/subscriptions/${subId}`, { method: 'DELETE' }, { ok: true })
}

export async function fetchWorkload(): Promise<ExpertWorkload[]> {
  return safeJson<ExpertWorkload[]>('/api/experts/workload', undefined, [])
}

/* ── SSE research stream ─────────────────────────────────────────────────── */

export interface SSEHandlers {
  /** `id` is the server's monotonic sequence number, used for de-duplication. */
  onEvent: (type: SSEEventType, data: unknown, id: number) => void
  onStatus?: (status: StreamStatus) => void
  onOpen?: () => void
}

const SSE_TYPES: SSEEventType[] = [
  'node_update',
  'thought',
  'message',
  'evidence',
  'chart',
  'image',
  'progress',
  'trace',
  'report_ready',
  'done',
  'error',
]

/**
 * Subscribe to a task's event stream.
 *
 * Two things the browser's built-in EventSource does not give us:
 *
 * 1. **Distinguishing a clean finish from a dropped connection.** EventSource
 *    fires `error` on both. We track whether the pipeline sent `done` and treat
 *    anything else as a genuine disconnect worth showing the user.
 * 2. **Bounded reconnection.** The backend's GET *starts* the research, so an
 *    unbounded auto-retry would kick off duplicate runs. We cap attempts and
 *    then stop, leaving the UI to offer a manual retry.
 *
 * Duplicate suppression lives in the store, keyed on the `id` passed through
 * here, because a reconnect replays events the store has already ingested.
 */
export function openTaskStream(taskId: string, handlers: SSEHandlers): () => void {
  const url = `${API_BASE}/api/tasks/${taskId}/stream`
  const MAX_RETRIES = 3

  let es: EventSource | null = null
  let finished = false
  let disposed = false
  let retries = 0
  let retryTimer: number | undefined

  const connect = () => {
    if (disposed) return
    handlers.onStatus?.(retries === 0 ? 'connecting' : 'reconnecting')
    es = new EventSource(url)

    es.onopen = () => {
      retries = 0
      handlers.onStatus?.('open')
      handlers.onOpen?.()
    }

    for (const t of SSE_TYPES) {
      es.addEventListener(t, (ev) => {
        const me = ev as MessageEvent
        let parsed: unknown = me.data
        try {
          parsed = JSON.parse(me.data)
        } catch {
          /* keep the raw string */
        }
        if (t === 'done') finished = true
        handlers.onEvent(t, parsed, Number(me.lastEventId || 0))
      })
    }

    es.onerror = () => {
      es?.close()
      if (disposed) return
      if (finished) {
        // EventSource always errors when the server closes a finished stream.
        handlers.onStatus?.('closed')
        return
      }
      if (retries >= MAX_RETRIES) {
        handlers.onStatus?.('closed')
        handlers.onEvent(
          'error',
          {
            message:
              'Lost connection to the research stream and could not reconnect. ' +
              'The run may still be completing on the server — check your reports.',
          },
          0,
        )
        return
      }
      retries += 1
      handlers.onStatus?.('reconnecting')
      retryTimer = window.setTimeout(connect, Math.min(1000 * 2 ** retries, 8000))
    }
  }

  connect()

  return () => {
    disposed = true
    window.clearTimeout(retryTimer)
    es?.close()
  }
}

export { API_BASE }
