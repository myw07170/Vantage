import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, applyCandidate, createTask, openTaskStream, saveEdits, startTask } from './api'
import { clearLegacyStorage, loadDraft, saveDraft } from './drafts'
import { useReportStore } from '../store/reportStore'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  onopen: (() => void) | null = null
  onerror: ((event: Event) => void) | null = null
  closed = false
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {}
  url: string
  constructor(url: string) { this.url = url; FakeEventSource.instances.push(this) }
  addEventListener(type: string, handler: (event: MessageEvent) => void) { this.listeners[type] = [...(this.listeners[type] || []), handler] }
  close() { this.closed = true }
  emit(type: string, data: unknown, id: number) { for (const h of this.listeners[type] || []) h(new MessageEvent(type, { data: JSON.stringify(data), lastEventId: String(id) })) }
}
beforeEach(() => { vi.useFakeTimers(); FakeEventSource.instances = []; vi.stubGlobal('EventSource', FakeEventSource); vi.stubGlobal('window', globalThis) })
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('mutation contracts', () => {
  it('creates a local draft without retired parameters', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ task_id: 't1' }) })
    vi.stubGlobal('fetch', fetch)
    expect((await createTask('Notion vs Obsidian')).task_id).toBe('t1')
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ query: 'Notion vs Obsidian' })
  })
  it('never treats a failed save as success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail: 'Backend unavailable' }) }))
    await expect(saveEdits('r', 'v', { item: 'edit' })).rejects.toThrow('Backend unavailable')
  })
  it('preserves a version conflict as a typed failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ detail: 'Current version changed' }) }))
    await expect(applyCandidate('r', 'base', 'candidate')).rejects.toMatchObject({ status: 409 })
    await expect(applyCandidate('r', 'base', 'candidate')).rejects.toBeInstanceOf(ApiError)
  })
  it('surfaces structured scope validation messages', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: [{ msg: 'Duplicate product names' }] }) }))
    await expect(startTask('t', { products: [], topics: [], changes_days: 90, scope_acknowledged: false, limitations: '' })).rejects.toThrow('Duplicate product names')
  })
})

describe('read-only stream subscriptions', () => {
  it('resumes by cursor and ignores duplicate events', () => {
    const onEvent = vi.fn(), close = openTaskStream('t', { onEvent })
    let source = FakeEventSource.instances[0]
    source.emit('progress', { percent: 2 }, 8)
    source.onerror?.(new Event('error')); vi.runOnlyPendingTimers()
    source = FakeEventSource.instances[1]
    expect(source.url).toContain('after=8')
    source.emit('progress', { percent: 2 }, 8); source.emit('progress', { percent: 3 }, 9)
    expect(onEvent).toHaveBeenCalledTimes(2)
    close()
    expect(source.closed).toBe(true)
  })
  it('caps retries even when every connection opens', () => {
    const onEvent = vi.fn()
    openTaskStream('t', { onEvent })
    for (let i = 0; i < 4; i++) { const s = FakeEventSource.instances.at(-1)!; s.onopen?.(); s.onerror?.(new Event('error')); vi.runOnlyPendingTimers() }
    expect(FakeEventSource.instances).toHaveLength(4)
    expect(onEvent).toHaveBeenCalledWith('error', expect.objectContaining({ message: expect.stringContaining('may still be running') }), 0)
  })
  it.each(['done', 'error'])('closes on terminal %s without reconnecting', type => {
    const onEvent = vi.fn()
    openTaskStream('t', { onEvent })
    const s = FakeEventSource.instances[0]
    s.emit(type, {}, 4); s.onerror?.(new Event('error')); vi.runAllTimers()
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(s.closed).toBe(true)
  })
  it('ignores events from an abandoned connection', () => {
    const onEvent = vi.fn(), close = openTaskStream('t', { onEvent })
    const old = FakeEventSource.instances[0]
    old.onerror?.(new Event('error')); vi.runOnlyPendingTimers()
    old.emit('progress', {}, 99)
    expect(onEvent).not.toHaveBeenCalled()
    close()
  })
  it('disposing cancels a pending reconnect', () => {
    const close = openTaskStream('t', { onEvent: vi.fn() })
    FakeEventSource.instances[0].onerror?.(new Event('error'))
    close(); vi.runAllTimers()
    expect(FakeEventSource.instances).toHaveLength(1)
  })
})

describe('current versions and local drafts', () => {
  it('always reloads the server current pointer', async () => {
    const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ report_id: 'r', current_version_id: 'old' }) }).mockResolvedValueOnce({ ok: true, json: async () => ({ report_id: 'r', current_version_id: 'new' }) })
    vi.stubGlobal('fetch', fetch)
    await useReportStore.getState().load('r')
    expect((await useReportStore.getState().load('r')).current_version_id).toBe('new')
    expect(fetch).toHaveBeenCalledTimes(2)
    useReportStore.getState().invalidate('r')
    expect(useReportStore.getState().reports.r).toBeUndefined()
  })
  it('clears only legacy business storage once and protects new drafts', () => {
    const data = new Map<string, string>([['vantage.annotations.v1', '{}'], ['vantage.knowledge.v1', '[]'], ['vantage.sidebar-collapsed', '1']])
    vi.stubGlobal('localStorage', { getItem: (k: string) => data.get(k) || null, setItem: (k: string, v: string) => data.set(k, v), removeItem: (k: string) => data.delete(k) })
    saveDraft('r', 'base', { fact: 'Unsaved correction' })
    clearLegacyStorage(); clearLegacyStorage()
    expect(data.has('vantage.annotations.v1')).toBe(false)
    expect(data.has('vantage.knowledge.v1')).toBe(false)
    expect(data.get('vantage.sidebar-collapsed')).toBe('1')
    expect(loadDraft('r', 'base')).toEqual({ fact: 'Unsaved correction' })
    expect(loadDraft('r', 'different-base')).toEqual({})
    saveDraft('r', 'base', {})
    expect(loadDraft('r', 'base')).toEqual({})
  })
})
