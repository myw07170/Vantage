import type { ReactNode, ButtonHTMLAttributes, HTMLAttributes } from 'react'
import {
  motion,
  AnimatePresence,
  useMotionValue,
  useTransform,
  animate,
} from 'framer-motion'
import { useEffect, useId, useRef } from 'react'

/* ── Card ────────────────────────────────────────────────────────────────── */
export function VCard({
  children,
  className = '',
  hover = true,
  ...rest
}: { children: ReactNode; className?: string; hover?: boolean } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`bg-card rounded-card shadow-card p-6 border border-line/60 transition-all duration-300 ease-vantage ${
        hover ? 'hover:shadow-float hover:-translate-y-0.5' : ''
      } ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}

/* ── Button ──────────────────────────────────────────────────────────────── */
export function VButton({
  children,
  variant = 'primary',
  className = '',
  ...p
}: {
  children: ReactNode
  variant?: 'primary' | 'ghost' | 'soft'
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  const base =
    'inline-flex items-center justify-center gap-2 px-5 h-11 rounded-btn font-medium text-sm transition-all duration-200 ease-vantage active:scale-95 disabled:opacity-50 disabled:pointer-events-none'
  const styles =
    variant === 'primary'
      ? 'bg-primary-deep text-white hover:bg-primary-deeper shadow-card hover:shadow-float'
      : variant === 'soft'
        ? 'bg-primary-tint text-primary-deep hover:bg-primary-soft/40'
        : 'bg-transparent text-ink-2 hover:bg-primary-tint hover:text-primary-deep'
  return (
    <button className={`${base} ${styles} ${className}`} {...p}>
      {children}
    </button>
  )
}

/* ── Chip ────────────────────────────────────────────────────────────────── */
// Light tone behind, `-deep` tone on top. A chip set in its own base colour
// measures around 2:1 against its pill — unreadable, on the elements carrying
// the product's central signal.
const tone = {
  high: 'bg-ok/15 text-ok-deep',
  medium: 'bg-warn/15 text-warn-deep',
  low: 'bg-risk/15 text-risk-deep',
  unverified: 'bg-paper text-ink-2',
  neutral: 'bg-primary-tint text-primary-deep',
} as const

export function VChip({
  label,
  level = 'neutral',
  icon,
  className = '',
}: {
  label: ReactNode
  level?: keyof typeof tone
  icon?: ReactNode
  className?: string
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-3 h-7 rounded-chip text-xs font-medium ${tone[level]} ${className}`}
    >
      {icon}
      {label}
    </span>
  )
}

/* ── Filter chip ─────────────────────────────────────────────────────────── */
/** Toggleable filter pill. Previously redefined in two separate pages. */
export function VFilterChip({
  active,
  onClick,
  children,
  count,
}: {
  active: boolean
  onClick: () => void
  children: ReactNode
  count?: number
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-chip border px-3 text-aux transition-colors ${
        active
          ? 'border-primary bg-primary-tint font-medium text-primary-deep'
          : 'border-line text-ink-2 hover:border-primary-soft hover:text-primary-deep'
      }`}
    >
      {children}
      {count != null && <span className="text-tag text-ink-3">{count}</span>}
    </button>
  )
}

/* ── Ambient glow ────────────────────────────────────────────────────────── */
export function VSunGlow({ className = '' }: { className?: string }) {
  return (
    <div
      className={`pointer-events-none absolute -z-0 ${className}`}
      style={{
        width: 520,
        height: 520,
        top: -160,
        right: -120,
        background: 'radial-gradient(circle, rgb(var(--v-sun)) 0%, rgb(var(--v-sun) / 0) 70%)',
        opacity: 0.5,
        filter: 'blur(8px)',
      }}
    />
  )
}

/* ── Animated number ─────────────────────────────────────────────────────── */
export function VCountUp({
  value,
  className = '',
}: {
  value: number
  className?: string
}) {
  const mv = useMotionValue(0)
  const rounded = useTransform(mv, (v) => Math.round(v).toLocaleString('en-US'))
  useEffect(() => {
    const c = animate(mv, value, { duration: 0.8, ease: 'easeOut' })
    return () => c.stop()
  }, [value, mv])
  return <motion.span className={className}>{rounded}</motion.span>
}

/* ── Skeleton ────────────────────────────────────────────────────────────── */
export function VSkeleton({ className = '' }: { className?: string }) {
  return <div className={`v-skeleton ${className}`} />
}

/* ── Confirmation dialog ─────────────────────────────────────────────────── */
/**
 * Blocking yes/no prompt for actions that cannot be undone.
 *
 * `window.confirm` would do the job but is styled by the browser and blocks the
 * event loop, so it cannot show the pending state while the request is in
 * flight. Escape and a backdrop click both cancel — the safe direction.
 */
export function VConfirm({
  open,
  title,
  message,
  confirmLabel = 'Yes',
  cancelLabel = 'Cancel',
  busy = false,
  busyLabel,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  message?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** Disables both buttons while the action is running. */
  busy?: boolean
  /** Replaces `confirmLabel` while `busy`. */
  busyLabel?: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const titleId = useId()
  const confirmRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    confirmRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onClick={onCancel}
          className="fixed inset-0 z-50 grid place-items-center bg-ink/30 p-6 backdrop-blur-sm"
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.16, ease: [0.4, 0, 0.2, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-sm rounded-card border border-line bg-card p-6 shadow-float"
          >
            <h2 id={titleId} className="text-h3 text-ink">
              {title}
            </h2>
            {message && <div className="mt-2 text-aux text-ink-2">{message}</div>}
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={onCancel}
                disabled={busy}
                className="h-10 rounded-btn px-4 text-aux font-medium text-ink-2 transition-colors hover:bg-paper hover:text-ink disabled:opacity-50"
              >
                {cancelLabel}
              </button>
              <button
                ref={confirmRef}
                onClick={onConfirm}
                disabled={busy}
                className="h-10 rounded-btn bg-risk-deep px-4 text-aux font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {busy ? (busyLabel ?? confirmLabel) : confirmLabel}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/* ── Empty state ─────────────────────────────────────────────────────────── */
export function VEmpty({
  icon,
  title,
  hint,
  action,
}: {
  icon?: ReactNode
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="grid place-items-center px-6 py-20 text-center">
      {icon && <div className="mb-4 text-ink-3">{icon}</div>}
      <div className="text-h3 text-ink">{title}</div>
      {hint && <p className="mt-2 max-w-md text-aux text-ink-3">{hint}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}
