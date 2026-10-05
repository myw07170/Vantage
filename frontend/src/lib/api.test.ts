import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { deleteSubscription, openTaskStream, setApiErrorListener, submitClarify, submitFeedback, createTask } from './api'
import { useTaskStore } from '../store/taskStore'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  onopen: (() => void) | null = null
  onerror: ((event: Event) => void) | null = null
  closed = false
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {}
  url: string
  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  addEventListener(type: string, handler: (event: MessageEvent) => void) {
    this.listeners[type] = [...(this.listeners[type] ?? []), handler]
  }
  close() { this.closed = true }
  emit(type: string, data: unknown, id: number) {
    const event = new MessageEvent(type, { data: JSON.stringify(data), lastEventId: String(id) })
    for (const handler of this.listeners[type] ?? []) handler(event)
    if (type === 'error') this.onerror?.(event)
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.stubGlobal('window', globalThis)
})
afterEach(() => {
  setApiErrorListener(null)
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('failed mutations', () => {
  it('never reports failed clarification, feedback or deletion as successful', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Backend down')))
    const errors = vi.fn()
    setApiErrorListener(errors)
    expect(await submitClarify('t_1', {})).toEqual({ ok: false })
    expect(await submitFeedback('r_1', 1, 4)).toEqual({ ok: false })
    expect(await deleteSubscription('sub_1')).toEqual({ ok: false })
    expect(errors).toHaveBeenCalledTimes(3)
  })
  it('surfaces server failure and submits subscription association', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: false, status: 503,
      json: async () => ({ detail: 'Configure a model key' }) })
    vi.stubGlobal('fetch', fetch)
    const error = vi.fn()
    setApiErrorListener(error)
    expect((await createTask('Notion', 'quick', 'sub_1')).taskId).toBe('')
    expect(JSON.parse(fetch.mock.calls[0][1].body).subscription_id).toBe('sub_1')
    expect(error).toHaveBeenCalledWith(expect.stringContaining('Configure a model key'))
  })
})

describe('SSE subscribers', () => {
  it('resumes with a cursor and suppresses duplicates', () => {
    const onEvent = vi.fn()
    const close = openTaskStream('t_1', { onEvent })
    let source = FakeEventSource.instances[0]
    source.emit('progress', { percent: 1 }, 8)
    source.onerror?.(new Event('error'))
    vi.runOnlyPendingTimers()
    source = FakeEventSource.instances[1]
    expect(source.url).toContain('after=8')
    source.emit('progress', { percent: 1 }, 8)
    source.emit('progress', { percent: 2 }, 9)
    expect(onEvent).toHaveBeenCalledTimes(2)
    close()
  })
  it('caps retries even if every connection opens before dropping', () => {
    const onEvent = vi.fn()
    openTaskStream('t_1', { onEvent })
    for (let attempt = 0; attempt < 4; attempt++) {
      const source = FakeEventSource.instances.at(-1)!
      source.onopen?.()
      source.onerror?.(new Event('error'))
      vi.runOnlyPendingTimers()
    }
    expect(FakeEventSource.instances).toHaveLength(4)
    expect(onEvent).toHaveBeenCalledWith('error', expect.any(Object), 0)
  })
  it.each(['done', 'error'])('closes on terminal %s without retrying', (type) => {
    const onEvent = vi.fn(), onStatus = vi.fn()
    openTaskStream('t_1', { onEvent, onStatus })
    const source = FakeEventSource.instances[0]
    source.emit(type, { reportId: 'r_1', message: 'Failed' }, 11)
    source.onerror?.(new Event('error'))
    vi.runOnlyPendingTimers()
    expect(source.closed).toBe(true)
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onStatus).toHaveBeenLastCalledWith('closed')
  })
  it('cleanup cancels pending retries and ignores late events', () => {
    const onEvent = vi.fn()
    const close = openTaskStream('t_1', { onEvent })
    const source = FakeEventSource.instances[0]
    source.onerror?.(new Event('error'))
    close()
    source.emit('done', { reportId: 'r_1' }, 12)
    vi.runOnlyPendingTimers()
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(onEvent).not.toHaveBeenCalled()
  })
  it('task store deduplicates replay and treats errors as terminal', () => {
    const store = useTaskStore.getState()
    store.reset('t_1', 'Notion')
    store.ingest('progress', { percent: 30 }, 5)
    store.ingest('progress', { percent: 1 }, 4)
    expect(useTaskStore.getState().progress.percent).toBe(30)
    store.ingest('error', { message: 'Interrupted' }, 6)
    expect(useTaskStore.getState().running).toBe(false)
    expect(useTaskStore.getState().streamStatus).toBe('closed')
  })
})
