import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, X } from 'lucide-react'
import { setApiErrorListener } from '../lib/api'
import { useUIStore } from '../store/uiStore'

/**
 * Surfaces API failures.
 *
 * Requests fall back to empty data rather than throwing, which keeps the UI
 * from blanking — but without this, a backend that is down looks exactly like
 * an empty database. The toast makes the difference visible.
 */
export function VToast() {
  const toast = useUIStore((s) => s.toast)
  const setToast = useUIStore((s) => s.setToast)

  useEffect(() => {
    setApiErrorListener((message) => setToast(message))
    return () => setApiErrorListener(null)
  }, [setToast])

  useEffect(() => {
    if (!toast) return
    const t = window.setTimeout(() => setToast(null), 6000)
    return () => window.clearTimeout(t)
  }, [toast, setToast])

  return (
    <AnimatePresence>
      {toast && (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 16 }}
          className="fixed bottom-5 left-1/2 z-[60] flex max-w-[min(520px,92vw)] -translate-x-1/2 items-start gap-2.5 rounded-card border border-risk/40 bg-card px-4 py-3 shadow-float"
          role="status"
        >
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-risk-deep" />
          <span className="min-w-0 flex-1 text-aux leading-relaxed text-ink-2">
            {toast}
          </span>
          <button
            onClick={() => setToast(null)}
            className="shrink-0 text-ink-3 hover:text-ink"
            aria-label="Dismiss"
          >
            <X size={15} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
