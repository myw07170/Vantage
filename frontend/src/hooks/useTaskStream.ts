import { useEffect } from 'react'
import { openTaskStream } from '../lib/api'
import { useTaskStore } from '../store/taskStore'

/**
 * Subscribe to a task's SSE stream: reset the store, then ingest events.
 *
 * Deliberately no `startedRef` guard — React StrictMode unmounts and remounts
 * in development, and a guard would close the connection without reopening it.
 * Duplicate events from a genuine reconnect are handled by id de-duplication in
 * the store instead.
 */
export function useTaskStream(taskId: string | undefined, query: string) {
  const reset = useTaskStore((s) => s.reset)
  const ingest = useTaskStore((s) => s.ingest)
  const setStreamStatus = useTaskStore((s) => s.setStreamStatus)

  useEffect(() => {
    if (!taskId) return

    reset(taskId, query)
    const close = openTaskStream(taskId, {
      onEvent: (type, data, id) => ingest(type, data, id),
      onStatus: (status) => setStreamStatus(status),
    })
    return () => close()
  }, [taskId, query, reset, ingest, setStreamStatus])
}
