// @vitest-environment jsdom
import { cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchTask, fetchTaskAudit, openTaskStream } from '../lib/api'
import { useTaskStore } from '../store/taskStore'
import { useTaskStream } from './useTaskStream'
import type { TaskDetail } from '../types'

vi.mock('../lib/api', () => ({ fetchTask: vi.fn(), fetchTaskAudit: vi.fn(), openTaskStream: vi.fn() }))

beforeEach(() => {
  vi.clearAllMocks()
  useTaskStore.getState().reset('old', '')
  vi.mocked(fetchTaskAudit).mockResolvedValue({ task_id: 't', audit_review: { status: 'blocked' }, evidence: [], trace: [], analysis: { claims: [] } })
  vi.mocked(openTaskStream).mockReturnValue(vi.fn())
})
afterEach(cleanup)

describe('restoring audited tasks', () => {
  it('restores failed writing drafts and verification after refresh', async () => {
    vi.mocked(fetchTask).mockResolvedValue({ taskId: 't', query: 'Acme', status: 'failed',
      error: 'verify_blocked: Unsupported price' } as TaskDetail)
    vi.mocked(fetchTaskAudit).mockResolvedValue({ task_id: 't', writing_status: 'blocked',
      drafts: { purchasing: { paragraphs: ['Complete preserved draft'] } },
      writing_verification: { findings: [{ section_id: 'purchasing', detail: 'Unsupported price' }] } })
    renderHook(() => useTaskStream('t', ''))
    await waitFor(() => expect(useTaskStore.getState().writingDrafts?.purchasing.paragraphs).toEqual(['Complete preserved draft']))
    expect(openTaskStream).not.toHaveBeenCalled()
    expect(useTaskStore.getState().researchSnapshot?.writing_status).toBe('blocked')
    expect(useTaskStore.getState().error).toContain('verify_blocked')
  })
  it('loads failed research after refresh without opening a new stream', async () => {
    vi.mocked(fetchTask).mockResolvedValue({ taskId: 't', query: 'Acme', status: 'failed',
      error: 'audit_blocked: Unsupported claim', auditSummary: { status: 'blocked' } } as TaskDetail)
    renderHook(() => useTaskStream('t', ''))
    await waitFor(() => expect(useTaskStore.getState().researchSnapshot?.task_id).toBe('t'))
    expect(fetchTaskAudit).toHaveBeenCalledWith('t')
    expect(openTaskStream).not.toHaveBeenCalled()
    expect(useTaskStore.getState().error).toContain('audit_blocked')
    expect(useTaskStore.getState().reportId).toBeNull()
  })

  it('retrieves persisted materials when a live task is blocked', async () => {
    vi.mocked(fetchTask).mockResolvedValue({ taskId: 't', query: 'Acme', status: 'running' } as TaskDetail)
    renderHook(() => useTaskStream('t', ''))
    await waitFor(() => expect(openTaskStream).toHaveBeenCalledOnce())
    const handlers = vi.mocked(openTaskStream).mock.calls[0][1]
    handlers.onEvent('error', { message: 'audit_blocked: Missing source' }, 12)
    await waitFor(() => expect(useTaskStore.getState().auditReview?.status).toBe('blocked'))
    expect(useTaskStore.getState().running).toBe(false)
    expect(useTaskStore.getState().finished).toBe(false)
  })
})
