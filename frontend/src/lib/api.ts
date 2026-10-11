import type { Annotation, Anchor, HighlightColor, Report, ReportCard, Scope, SSEEventType, StreamStatus, Task, TraceSpan, Version, VersionMeta } from '../types'
export const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}
export async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(API_BASE + path, { method, headers: body === undefined ? undefined : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) })
  const value = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = value?.detail
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: { msg: string }) => d.msg).join(' ') : 'Request failed (' + response.status + ').'
    throw new ApiError(message, response.status)
  }
  return value as T
}
export const createTask = (query: string) => request<Task>('/api/tasks', 'POST', { query })
export const prepareTask = (id: string, base_revision: number, answers: Record<string, string | string[]>, draft_scope?: unknown) => request<Task>('/api/tasks/' + id + '/prepare', 'POST', { base_revision, answers, draft_scope })
export const fetchAnnotations = (id: string, version: string) => request<Annotation[]>('/api/reports/' + id + '/annotations?version_id=' + encodeURIComponent(version))
export const addAnnotation = (id: string, version_id: string, anchors: Anchor[], color: HighlightColor, comment: string) => request<Annotation>('/api/reports/' + id + '/annotations', 'POST', { version_id, anchors, color, comment })
export const patchAnnotation = (id: string, note: Annotation, patch: { color?: HighlightColor; comment?: string }) => request<Annotation>('/api/reports/' + id + '/annotations/' + note.annotation_id, 'PATCH', { version_id: note.version_id, revision: note.revision, ...patch })
export const removeAnnotation = (id: string, note: Annotation) => request<{ ok: boolean }>('/api/reports/' + id + '/annotations/' + note.annotation_id + '?version_id=' + note.version_id + '&revision=' + note.revision, 'DELETE')
export const fetchTask = (id: string) => request<Task>('/api/tasks/' + id)
export const fetchTasks = () => request<Task[]>('/api/tasks')
export const startTask = (id: string, scope: Scope) => request<Task>('/api/tasks/' + id + '/start', 'POST', scope)
export const retryTask = (id: string) => request<Task>('/api/tasks/' + id + '/retry', 'POST')
export const fetchReports = () => request<ReportCard[]>('/api/reports')
export const fetchReport = (id: string) => request<Report>('/api/reports/' + id)
export const fetchVersions = (id: string) => request<VersionMeta[]>('/api/reports/' + id + '/versions')
export const fetchVersion = (id: string, version: string) => request<Version>('/api/reports/' + id + '/versions/' + version)
export const fetchTrace = (task: string) => request<{ spans: TraceSpan[] }>('/api/tasks/' + task + '/trace')
export const saveEdits = (id: string, base: string, edits: Record<string, string>) => request<Version>('/api/reports/' + id + '/edits', 'POST', { base_version_id: base, edits })
export const applyCandidate = (id: string, base: string, candidate: string) => request<Version>('/api/reports/' + id + '/apply', 'POST', { base_version_id: base, candidate_version_id: candidate })
export const restoreVersion = (id: string, base: string, version: string) => request<Version>('/api/reports/' + id + '/restore', 'POST', { base_version_id: base, version_id: version })
export const followup = (id: string, base: string, target: string, question: string, selected_text = '') => request<Task>('/api/reports/' + id + '/followups', 'POST', { base_version_id: base, target_ids: [target], selected_text, question })
export const reviewReport = (id: string, base: string, target_ids: string[] = []) => request<Task>('/api/reports/' + id + '/reviews', 'POST', { base_version_id: base, target_ids })
export const updateReport = (id: string, patch: { title?: string; starred?: boolean }) => request<Report>('/api/reports/' + id, 'PATCH', patch)
export const deleteReport = (id: string) => request<{ ok: boolean }>('/api/reports/' + id, 'DELETE')

export function openTaskStream(taskId: string, handlers: { onEvent: (type: SSEEventType, data: unknown, id: number) => void; onStatus?: (status: StreamStatus) => void }): () => void {
  let source: EventSource | null = null
  let finished = false, disposed = false, retries = 0, cursor = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  const connect = () => {
    if (disposed || finished) return
    handlers.onStatus?.(retries ? 'reconnecting' : 'connecting')
    const connection = new EventSource(API_BASE + '/api/tasks/' + taskId + '/stream?after=' + cursor)
    source = connection
    connection.onopen = () => { if (!disposed && !finished && source === connection) handlers.onStatus?.('open') }
    for (const type of ['role', 'handoff', 'evidence', 'progress', 'notice', 'activity', 'done', 'error'] as SSEEventType[]) {
      connection.addEventListener(type, event => {
        if (disposed || finished || source !== connection) return
        const message = event as MessageEvent
        if (typeof message.data !== 'string') return
        const id = Number(message.lastEventId || 0)
        if (id && id <= cursor) return
        let data: unknown
        try { data = JSON.parse(message.data) } catch { return }
        if (id) cursor = id
        if (type === 'done' || type === 'error') {
          finished = true
          connection.close()
          clearTimeout(timer)
          handlers.onStatus?.('closed')
        }
        handlers.onEvent(type, data, id)
      })
    }
    connection.onerror = event => {
      if (event instanceof MessageEvent || disposed || finished || source !== connection) return
      connection.close()
      if (retries >= 3) {
        handlers.onStatus?.('closed')
        handlers.onEvent('error', { message: 'Connection lost. The task may still be running. Refresh to restore its saved state.' }, 0)
        return
      }
      retries++
      handlers.onStatus?.('reconnecting')
      timer = setTimeout(connect, Math.min(1000 * 2 ** retries, 8000))
    }
  }
  connect()
  return () => { disposed = true; clearTimeout(timer); source?.close() }
}
