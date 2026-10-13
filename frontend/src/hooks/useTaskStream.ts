import { useEffect } from 'react'
import { fetchTask, openTaskStream } from '../lib/api'
import { useTaskStore } from '../store/taskStore'

/**
 * Restore task metadata before subscribing. StrictMode may dispose a subscriber,
 * but the server still owns exactly one research run.
 */
export function useTaskStream(taskId: string | undefined, query: string) {
  const reset = useTaskStore((s) => s.reset)
  const ingest = useTaskStore((s) => s.ingest)
  const setStreamStatus = useTaskStore((s) => s.setStreamStatus)

  useEffect(() => {
    if (!taskId) return

    reset(taskId, query)
    let disposed = false
    let close: (() => void) | undefined
    void fetchTask(taskId).then((task) => {
      if (disposed) return
      if (!task) {
        ingest('error', { message: 'Could not load this task. Check the backend and try again.' })
        setStreamStatus('closed')
        return
      }
      useTaskStore.setState({ query: task.query })
      if (task.status === 'done' && task.reportId) {
        ingest('done', { reportId: task.reportId }, task.terminalSeq)
      } else if (task.status === 'failed' || task.status === 'interrupted' || task.status === 'done') {
        ingest('error', { message: task.error || 'The report was deleted. Create a new task.' })
        setStreamStatus('closed')
      } else {
        close = openTaskStream(taskId, {
          onEvent: (type, data, id) => ingest(type, data, id),
          onStatus: (status) => setStreamStatus(status),
        })
      }
    })
    return () => {
      disposed = true
      close?.()
    }
  }, [taskId, query, reset, ingest, setStreamStatus])
}
