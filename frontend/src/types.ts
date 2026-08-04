/**
 * The API contract shared with the FastAPI backend.
 *
 * Naming is mixed on purpose: task creation uses camelCase (`taskId`,
 * `needClarify`) while everything else is snake_case, matching what the backend
 * actually sends. Normalizing would mean changing both sides for no gain.
 */

/* ── Experts ─────────────────────────────────────────────────────────────── */
export type ExpertLevel = 'L1' | 'L2' | 'L3'
export type ExpertGroup = 'decision' | 'strategy' | 'industry' | 'function'
export type ExpertStatus = 'idle' | 'working' | 'done' | 'rework'

export interface Expert {
  id: string
  level: ExpertLevel
  group: ExpertGroup
  name: string
  nickname: string
  role_title: string
  one_liner: string
  skills: string[]
  knowledge_base: string
  knowledge_tags: string[]
  avatar: string
  badge_color: string
  domain_icon: string
  gender: 'male' | 'female'
  status: ExpertStatus
  stats: { missions: number; avg_evidence: number }
}

/* ── Task creation and clarification ─────────────────────────────────────── */
export interface ClarifyQuestion {
  id: string
  question: string
  hint?: string
  type: 'single' | 'multi' | 'text' | 'slider'
  options?: string[]
}

export interface CreateTaskResp {
  taskId: string
  needClarify: boolean
  clarifyQuestions?: ClarifyQuestion[]
}

/* ── SSE stream ──────────────────────────────────────────────────────────── */
export type SSEEventType =
  | 'node_update'
  | 'thought'
  | 'message'
  | 'evidence'
  | 'chart'
  | 'image'
  | 'progress'
  | 'trace'
  | 'report_ready'
  | 'done'
  | 'error'

/** Connection state of the research stream, surfaced in the workspace UI. */
export type StreamStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

export interface DAGNode {
  id: string
  label: string
  status: ExpertStatus
  expert?: string
}

export type ThoughtKind = 'plan' | 'dispatch' | 'action' | 'finding' | 'reflect'

export interface ThoughtItem {
  id: string
  kind: ThoughtKind
  expert?: string
  text: string
  ts: number
}

export interface ProgressInfo {
  percent: number
  evidence_count: number
  token_used: number
  stage: string
  /** Sections still waiting on the model's rate limiter. */
  queued?: number
}

/* ── Observability ───────────────────────────────────────────────────────── */
export interface TraceSpan {
  span_id: string
  seq: number
  agent_id: string
  stage: string
  purpose: string
  model: string
  prompt: string
  response: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  latency_ms: number
  decision?: string
  evidence_ids?: string[]
  ts: string
}

/* ── Evidence and claims ─────────────────────────────────────────────────── */
/** Matches SourceType in backend/app/core/models.py. */
export type SourceType =
  | 'official'
  | 'sec_filing'
  | 'analyst'
  | 'news'
  | 'review'
  | 'reddit'
  | 'hackernews'
  | 'youtube'
  | 'x'
  | 'forum'
  | 'web'
  | 'unknown'

export interface Evidence {
  evidence_id: string
  source_url: string
  source_type: string
  title: string
  excerpt: string
  screenshot_path?: string
  image_urls?: string[]
  captured_at: string
  credibility: number
  collected_by: string
  brand?: string
  domain?: string
  freshness_days?: number | null
}

export type Confidence = 'high' | 'medium' | 'low' | 'unverified'

export interface Claim {
  claim_id: string
  text: string
  field: string
  evidence_ids: string[]
  confidence: Confidence
  cross_validated: boolean
  author: string
}

/* ── Charts and structured data ──────────────────────────────────────────── */
export interface ChartSpec {
  chart_id: string
  type: string
  title?: string
  /** ECharts option, built server-side — labels originate in charts.py. */
  option: Record<string, unknown>
  png?: string
  evidence_ids?: string[]
}

export interface DataGrid {
  columns: string[]
  rows: {
    name: string
    value: string | number
    metric: string
    source: string
    source_url: string
    evidence_id?: string
  }[]
}

export interface StructuredBlock {
  type: 'feature_tree' | 'pricing_model' | 'user_persona'
  data: Record<string, unknown>[]
}

/* ── Report ──────────────────────────────────────────────────────────────── */
export interface ReportSection {
  id: string
  title: string
  level: number
  key_takeaway?: string
  highlights?: string[]
  paragraphs?: string[]
  claims?: Claim[]
  charts?: ChartSpec[]
  source_evidence_ids?: string[]
  structured?: StructuredBlock | null
  data_grid?: DataGrid | null
  refined?: boolean
  /** Rewritten by the verify stage after a defect was found in the first draft. */
  rewritten?: boolean
}

export interface ReportMetrics {
  efficiency?: Record<string, unknown>
  coverage?: Record<string, unknown>
  consistency?: Record<string, unknown>
  business?: Record<string, unknown>
}

export interface SentimentResult {
  overall: { pos: number; neu: number; neg: number }
  overall_count?: { pos: number; neu: number; neg: number }
  by_platform: Record<string, { pos: number; neu: number; neg: number }>
  by_brand?: { brand: string; sample: number; pos: number; neu: number; neg: number }[]
  timeline: { date: string; pos: number; neu: number; neg: number }[]
  camps: {
    title: string
    ratio: number
    summary: string
    quotes: { text: string; url: string; platform?: string }[]
  }[]
  voices?: {
    platform: string
    platform_label: string
    text: string
    sentiment: string
    url: string
    title?: string
  }[]
  highlights?: {
    phrase: string
    platform: string
    platform_label: string
    sentiment: string
    url: string
  }[]
  sample_size: number
}

export interface AuditOpinion {
  verdict?: string
  scores?: Record<string, number>
  review?: string
  issues?: string[]
  suggestions?: string[]
}

export interface AuditReview {
  before?: AuditOpinion
  after?: AuditOpinion
  rework_rounds?: number
  issues_resolved?: number
}

/* ── Post-write verification ─────────────────────────────────────────────── */
/** Keys match Finding in backend/app/core/verify.py. */
export interface VerifyFinding {
  finding_id: string
  section_id: string
  severity: 'cosmetic' | 'minor' | 'major'
  kind: string
  detail: string
  fix?: string
  auto_fixed?: boolean
  raised_by?: string
}

export interface VerifyReview {
  /** `pass` clean · `revised` defects found and dealt with · `flagged` some survived. */
  verdict?: 'pass' | 'revised' | 'flagged'
  scores?: Record<string, number>
  review?: string
  /** Still open at sign-off — surfaced rather than hidden. */
  findings?: VerifyFinding[]
  /** Repaired automatically during the check. */
  fixed?: VerifyFinding[]
  rewritten_sections?: string[]
  rounds?: number
  checks?: {
    sections_checked?: number
    paragraphs_checked?: number
    citations_resolved?: number
    citations_dropped?: number
    auto_fixed?: number
    open_findings?: number
  }
}

export interface ReportFigure {
  src: string
  alt?: string
  title?: string
  source_url: string
  domain?: string
  source_type?: string
  brand?: string
  evidence_id?: string
}

export interface Report {
  id: string
  title: string
  subtitle: string
  query?: string
  brands?: string[]
  mode?: string
  created_at: string
  experts: string[]
  dispatch?: { id: string; reason: string }[]
  cover_image?: string
  toc: { id: string; title: string; level: number }[]
  sections: ReportSection[]
  charts: ChartSpec[]
  evidence: Evidence[]
  claims: Claim[]
  sentiment?: SentimentResult
  glossary: { term: string; definition: string; source?: string }[]
  figures?: ReportFigure[]
  structured?: Record<string, Record<string, unknown>[]>
  metrics?: ReportMetrics
  quality_before?: Record<string, unknown>
  quality_after?: Record<string, unknown>
  audit_review?: AuditReview
  verify_review?: VerifyReview
  trace?: TraceSpan[]
}

/** History list item — no full text, to keep the list light. */
export interface ReportCard {
  id: string
  report_id: string
  title: string
  subtitle: string
  query: string
  brands: string[]
  experts: string[]
  cover_image?: string
  evidence_count: number
  claim_count: number
  high_conf_count: number
  created_at: string
}

/* ── Dashboard ───────────────────────────────────────────────────────────── */
export interface ResearchCard {
  id: string
  title: string
  query: string
  brands: string[]
  evidence_count: number
  claim_count: number
  high_conf_count: number
  created_at: string
  efficiency_multiple?: number | null
  coverage_multiple?: number | null
  elapsed_minutes?: number | null
  minutes_saved?: number | null
  tokens_used?: number | null
}

export interface DashboardStats {
  reports: number
  evidence_total: number
  claim_total: number
  high_conf_total: number
  avg_evidence_per_report: number
  fact_accuracy: number
  platform_distribution: Record<string, number>
  brand_distribution: Record<string, number>
  minutes_saved?: number
  avg_efficiency?: number
  avg_coverage?: number
  total_tokens?: number
  research_cards?: ResearchCard[]
}

/* ── Evidence library ────────────────────────────────────────────────────── */
export interface EvidenceRecord {
  evidence_id: string
  report_id: string
  source_url: string
  source_type: string
  domain: string
  title: string
  excerpt: string
  credibility: number
  collected_by: string
  brand: string
  captured_at: string
}

export interface EvidenceFacets {
  total: number
  by_type: Record<string, number>
  by_brand: Record<string, number>
}

export interface EvidenceQueryResp {
  items: EvidenceRecord[]
  facets: EvidenceFacets
}

/* ── Subscriptions and workload ──────────────────────────────────────────── */
export interface Subscription {
  sub_id: string
  query: string
  brands: string[]
  created_at: string
  last_run_at: string
  last_report_id: string
  run_count: number
}

export interface ExpertWorkload {
  id: string
  name: string
  title: string
  layer: string
  avatar: string
  missions: number
  claims_authored: number
  evidence_collected: number
  last_active: string
}
