import { create } from 'zustand'
import type {
  ChartSpec,
  Claim,
  DAGNode,
  Evidence,
  ProgressInfo,
  SSEEventType,
  StreamStatus,
  ThoughtItem,
  TraceSpan,
} from '../types'

export interface ImageItem {
  src: string
  alt?: string
  source_url?: string
  brand?: string
}

export interface StreamMessage {
  id: string
  kind: string
  expert?: string
  text?: string
  members?: string[]
  claim?: Claim
  reason?: string
  diff?: { before: string; after: string }
  metrics_before?: Record<string, number>
  metrics_after?: Record<string, number>
  issues_resolved?: number
  envelope?: {
    sender?: string
    receiver?: string
    task_type?: string
    payload?: unknown
    issues?: unknown[]
  }
  mode?: string
  // audit_review / verify_review payload
  stage?: string
  verdict?: string
  scores?: Record<string, number>
  review?: string
  issues?: string[]
  suggestions?: string[]
  // verify_rewrite payload
  sections?: string[]
}

const BASE_NODES: DAGNode[] = [
  { id: 'intake', label: 'Understand', status: 'idle' },
  { id: 'orchestrator', label: 'Assemble', status: 'idle' },
  { id: 'collect', label: 'Collect', status: 'idle' },
  { id: 'analyze', label: 'Analyze', status: 'idle' },
  { id: 'write', label: 'Write', status: 'idle' },
  { id: 'audit', label: 'Review', status: 'idle' },
  { id: 'verify', label: 'Verify', status: 'idle' },
  { id: 'done', label: 'Deliver', status: 'idle' },
]

interface TaskState {
  taskId: string | null
  query: string
  running: boolean
  finished: boolean
  reportId: string | null
  nodes: DAGNode[]
  activeNode: string | null
  thoughts: ThoughtItem[]
  messages: StreamMessage[]
  evidences: Evidence[]
  images: ImageItem[]
  charts: ChartSpec[]
  claims: Claim[]
  traces: TraceSpan[]
  progress: ProgressInfo
  teamMembers: string[]
  error: string | null
  streamStatus: StreamStatus
  /** Highest server event id ingested — everything at or below is a replay. */
  lastEventId: number

  reset: (taskId: string, query: string) => void
  ingest: (type: SSEEventType, data: unknown, id?: number) => void
  setStreamStatus: (status: StreamStatus) => void
}

const initProgress: ProgressInfo = {
  percent: 0,
  evidence_count: 0,
  token_used: 0,
  stage: 'intake',
}

/** SSE payloads are dynamic JSON; narrow to an indexable object first. */
type LooseRecord = Record<string, unknown>
function asObj(d: unknown): LooseRecord {
  return (d ?? {}) as LooseRecord
}

export const useTaskStore = create<TaskState>((set, get) => ({
  taskId: null,
  query: '',
  running: false,
  finished: false,
  reportId: null,
  nodes: BASE_NODES.map((n) => ({ ...n })),
  activeNode: null,
  thoughts: [],
  messages: [],
  evidences: [],
  images: [],
  charts: [],
  claims: [],
  traces: [],
  progress: { ...initProgress },
  teamMembers: [],
  error: null,
  streamStatus: 'idle',
  lastEventId: 0,

  reset: (taskId, query) =>
    set({
      taskId,
      query,
      running: true,
      finished: false,
      reportId: null,
      nodes: BASE_NODES.map((n) => ({ ...n })),
      activeNode: null,
      thoughts: [],
      messages: [],
      evidences: [],
      images: [],
      charts: [],
      claims: [],
      traces: [],
      progress: { ...initProgress },
      teamMembers: [],
      error: null,
      streamStatus: 'connecting',
      lastEventId: 0,
    }),

  setStreamStatus: (streamStatus) => set({ streamStatus }),

  ingest: (type, data, id = 0) => {
    const s = get()
    // On reconnect the server replays from the start of the run. Anything at or
    // below the highest id we have already appended would otherwise show up
    // twice in the thought stream and evidence feed.
    if (id > 0 && id <= s.lastEventId) return
    const d = asObj(data)
    const seq = id > 0 ? { lastEventId: id } : {}

    switch (type) {
      case 'node_update': {
        if (Array.isArray(d.nodes)) {
          set({ nodes: d.nodes as DAGNode[], ...seq })
          return
        }
        const node = d.node as string
        const status = d.status as DAGNode['status']
        const expert = d.expert as string | undefined
        const nodes = s.nodes.map((n) =>
          n.id === node ? { ...n, status, expert: expert ?? n.expert } : n,
        )
        set({
          nodes,
          activeNode: status === 'working' ? node : s.activeNode,
          ...seq,
        })
        return
      }
      case 'thought':
        set({ thoughts: [...s.thoughts, d as unknown as ThoughtItem], ...seq })
        return
      case 'message': {
        const msg = d as unknown as StreamMessage
        const patch: Partial<TaskState> = { messages: [...s.messages, msg], ...seq }
        if (msg.kind === 'team' && msg.members) patch.teamMembers = msg.members
        if (msg.kind === 'claim' && msg.claim) patch.claims = [...s.claims, msg.claim]
        set(patch)
        return
      }
      case 'evidence':
        set({ evidences: [...s.evidences, d as unknown as Evidence], ...seq })
        return
      case 'image':
        set({ images: [...s.images, d as unknown as ImageItem], ...seq })
        return
      case 'chart':
        set({ charts: [...s.charts, d as unknown as ChartSpec], ...seq })
        return
      case 'progress':
        set({ progress: d as unknown as ProgressInfo, ...seq })
        return
      case 'trace':
        set({ traces: [...s.traces, d as unknown as TraceSpan], ...seq })
        return
      case 'report_ready':
        set({ reportId: d.reportId as string, ...seq })
        return
      case 'done':
        set({
          running: false,
          finished: true,
          streamStatus: 'closed',
          reportId: (d.reportId as string) ?? s.reportId,
          ...seq,
        })
        return
      case 'error':
        set({
          error: (d.message as string) ?? 'An unknown error occurred.',
          running: false,
          ...seq,
        })
        return
    }
  },
}))
