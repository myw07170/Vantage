export type ReviewStatus = 'supported' | 'unknown' | 'conflicting' | 'pending_review'
export interface Product { id: string; name: string; website: string; category: string; own_product: boolean; confirmed: boolean }
export interface Topic { id: string; name: string; focus: string[] }
export interface Scope { products: Product[]; topics: Topic[]; changes_days: 90; scope_acknowledged: boolean; limitations: string }
export interface Citation { evidence_id: string; quote: string }
export interface Review { status: ReviewStatus; citation_valid: boolean | null; support_checked: boolean; reason: string; evidence_ids: string[]; quotes?: Citation[]; checked_at: string | null }
export interface Item { id: string; kind: 'fact' | 'inference' | 'change'; product_id: string; topic_id: string; text: string; citations: Citation[]; depends_on: string[]; conditions: Record<string, string | number | boolean | null>; effective_date: string | null; review: Review }
export interface Evidence { evidence_id: string; product_id: string; topic_id: string; source_url: string; source_type: 'official' | 'external' | 'unknown'; attribution: string; title: string; excerpt: string; context: string; captured_at: string; published_at: string | null; published_date_basis: string; degraded: boolean; limitation: string }
export interface Usage { tokens: number; token_limit: number; usage_estimated: boolean; elapsed_seconds: number; remaining_seconds: number }
export interface Chart { id: string; conditions: Record<string, string>; checked_at: string; points: { product_id: string; item_id: string; value: number; citations: Citation[] }[] }
export interface Content { products: Product[]; topics: Topic[]; checked_at: string; changes_since: string; comparison: Item[]; brief: Item[]; changes: Item[]; evidence: Evidence[]; charts: Chart[]; review_summary: { counts?: Record<ReviewStatus, number>; issues?: (Review & { item_id: string })[]; meaning?: string; changes_message?: string; rework_rounds?: number; usage?: Usage; run_limitation?: string }; limitations: string[]; is_mock: boolean; llm_provider: string }
export interface VersionMeta { version_id: string; report_id: string; base_version_id: string | null; kind: string; state: 'candidate' | 'applied'; task_id: string; metadata: { question?: string; selected_text?: string; target_ids?: string[]; usage?: Usage; affected_ids?: string[]; source_task_id?: string; candidate_version_id?: string }; created_at: string }
export interface Version extends VersionMeta { content: Content }
export interface ReportCard { report_id: string; title: string; current_version_id: string; starred: boolean; created_at: string }
export interface Report extends ReportCard { version: Version }
export interface SuggestedProduct extends Product { mentioned_as: string; website_status: string; identity_note: string }
export interface Preparation { revision: number; status: 'running' | 'ready' | 'failed' | 'interrupted'; answers: Record<string, string | string[]>; error?: string; usage?: Usage; proposal?: { summary: string; products: SuggestedProduct[]; topics: Topic[]; questions: { id: string; question: string; type: string; options: string[]; required: boolean }[]; limitations: string } }
export interface Activity { id: number; kind: string; role: string; text: string; at: string }
export interface Visualization { roles: Record<string, { role: string; status: string; detail: string }>; activity: Activity[]; percent: number; rework_rounds: number }
export interface Task { task_id: string; kind: 'research' | 'followup' | 'review'; query: string; payload: { scope?: Scope; preparation?: Preparation; base_version_id?: string; target_ids?: string[]; question?: string; selected_text?: string }; status: 'created' | 'preparing' | 'awaiting_confirmation' | 'running' | 'done' | 'failed' | 'interrupted'; created_at: string; report_id: string | null; version_id: string | null; terminal_seq: number; error: string; checkpoint: { stage?: string; content?: Content; usage?: Usage; rework_rounds?: number; visualization?: Visualization } }
export interface TraceSpan { span_id: string; seq: number; agent_id: string; stage: string; purpose: string; model: string; prompt: string; response: string; total_tokens: number; latency_ms: number; decision?: string }
export type SSEEventType = 'role' | 'handoff' | 'evidence' | 'progress' | 'notice' | 'activity' | 'done' | 'error'
export type StreamStatus = 'connecting' | 'open' | 'reconnecting' | 'closed'
export type HighlightColor = 'sun' | 'ok' | 'risk' | 'info'
export interface Anchor { item_id: string; start: number; end: number; quote: string; prefix: string; suffix: string }
export interface Annotation { annotation_id: string; report_id: string; version_id: string; anchors: Anchor[]; color: HighlightColor; comment: string; revision: number; anchor_status: 'active' | 'unanchored'; created_at: string; updated_at: string }
