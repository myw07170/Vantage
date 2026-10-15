import { beforeEach, describe, expect, it } from 'vitest'
import { useTaskStore } from './taskStore'
import type { Claim, WritingPlan } from '../types'

const claim = (id: string): Claim => ({ claim_id: id, text: id, field: 'overview', evidence_ids: [],
  confidence: 'unverified', cross_validated: false, author: 'analyst' })

beforeEach(() => useTaskStore.getState().reset('task', 'Research'))

const plan: WritingPlan = { version: 2, title: 'The purchasing decision', purpose: 'Choose a tool', thesis: 'Cost depends on use',
  target_words: 1500, chapters: [], material_usage: [] }

describe('audit stream state', () => {
  it('replaces chapter drafts after integration and restores writing state after failure', () => {
    const { ingest } = useTaskStore.getState()
    ingest('message', { kind: 'writing_plan', writing_plan: plan }, 1)
    ingest('message', { kind: 'writing_draft', section_id: 'purchase', draft: { paragraphs: ['First draft'] } }, 2)
    ingest('message', { kind: 'writing_draft', section_id: 'purchase', draft: { paragraphs: ['Edited draft'] } }, 3)
    expect(useTaskStore.getState().writingDrafts?.purchase.paragraphs).toEqual(['Edited draft'])
    ingest('error', { message: 'verify_blocked: Unresolved assertion' }, 4)
    ingest('message', { kind: 'research_snapshot', snapshot: { task_id: 'task', writing_status: 'blocked',
      writing_plan: plan, drafts: { purchase: { paragraphs: ['Saved draft'] } } } })
    expect(useTaskStore.getState().writingPlan?.title).toBe(plan.title)
    expect(useTaskStore.getState().writingDrafts?.purchase.paragraphs).toEqual(['Saved draft'])
    expect(useTaskStore.getState().finished).toBe(false)
    expect(useTaskStore.getState().reportId).toBeNull()
    useTaskStore.getState().reset('next', 'Next')
    expect(useTaskStore.getState().writingPlan).toBeUndefined()
    expect(useTaskStore.getState().writingDrafts).toBeUndefined()
  })
  it('replaces earlier claims and suppresses repeated snapshots', () => {
    const { ingest } = useTaskStore.getState()
    ingest('message', { kind: 'claim', claim: claim('old') }, 1)
    ingest('message', { kind: 'analysis_snapshot', claims: [claim('new')], structured: { feature_tree: [] } }, 2)
    ingest('message', { kind: 'analysis_snapshot', claims: [claim('old')] }, 2)
    expect(useTaskStore.getState().claims.map((c) => c.claim_id)).toEqual(['new'])
    expect(useTaskStore.getState().structured).toEqual({ feature_tree: [] })
  })

  it('restores blocked research without declaring a report ready', () => {
    const { ingest } = useTaskStore.getState()
    ingest('error', { code: 'audit_blocked', message: 'audit_blocked: No support' }, 3)
    ingest('message', { kind: 'research_snapshot', snapshot: { task_id: 'task',
      audit_review: { status: 'blocked' }, evidence: [], analysis: { claims: [claim('saved')] }, trace: [] } })
    expect(useTaskStore.getState().auditReview?.status).toBe('blocked')
    expect(useTaskStore.getState().claims[0].claim_id).toBe('saved')
    expect(useTaskStore.getState().reportId).toBeNull()
    expect(useTaskStore.getState().finished).toBe(false)
    expect(useTaskStore.getState().running).toBe(false)
    useTaskStore.getState().reset('next', 'Next task')
    expect(useTaskStore.getState().auditReview).toBeUndefined()
    expect(useTaskStore.getState().researchSnapshot).toBeUndefined()
  })
})
