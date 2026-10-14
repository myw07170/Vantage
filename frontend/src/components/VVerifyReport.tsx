import {
  BadgeCheck,
  AlertTriangle,
  Wrench,
  Link2,
  RefreshCw,
  FileCheck,
} from 'lucide-react'
import type { VerifyReview, VerifyFinding } from '../types'
import { plural } from '../lib/format'

/**
 * What the verify stage did to the finished report: citations resolved against
 * real evidence, defects repaired in place, sections rewritten — and anything
 * still open at sign-off.
 *
 * Unresolved findings are shown, not hidden. A report that shipped with a known
 * weakness says so here; that is the point of running the check at all.
 *
 * Score dimension names come straight from the backend (verify.py), so they are
 * rendered as-is rather than mapped.
 */
export function VVerifyReport({ review }: { review?: VerifyReview }) {
  if (!review || (!review.checks && !review.verdict)) return null

  const checks = review.checks ?? {}
  const open = review.findings ?? []
  const fixed = review.fixed ?? []
  const rewritten = review.rewritten_sections ?? []
  const majors = open.filter((f) => f.severity === 'major')
  const verdict = review.verdict ?? 'pass'
  const scoreKeys = Object.keys(review.scores ?? {})

  const badge = {
    pass: { cls: 'bg-ok/15 text-ok-deep', text: '✓ Verified' },
    revised: { cls: 'bg-primary-tint text-primary-deep', text: '✎ Corrected before delivery' },
    flagged: { cls: 'bg-warn/15 text-warn-deep', text: '⚠ Shipped with open issues' },
  }[verdict]

  const stats = [
    {
      icon: Link2,
      value: checks.citations_resolved ?? 0,
      label: 'citations resolved to real sources',
    },
    {
      icon: AlertTriangle,
      value: checks.citations_dropped ?? 0,
      label: 'dead citation markers removed',
    },
    { icon: Wrench, value: fixed.length, label: 'defects repaired in place' },
    { icon: RefreshCw, value: rewritten.length, label: 'sections rewritten' },
  ]

  return (
    <div className="my-6 rounded-card border border-line bg-card p-5 shadow-card">
      <div className="flex flex-wrap items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-btn bg-primary-tint text-primary-deep">
          <BadgeCheck size={17} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-aux font-semibold text-ink">Report verification</div>
          <div className="text-tag text-ink-3">
            After writing, every inline citation is checked against the collected
            evidence and the sections are read against each other for
            contradictions and unsupported claims.
          </div>
        </div>
        <span className={`rounded-chip px-3 py-1 text-tag font-semibold ${badge.cls}`}>
          {badge.text}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2.5 md:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon
          return (
            <div key={s.label} className="rounded-card border border-line/60 bg-bg p-3">
              <div className="flex items-center gap-1.5 text-tag text-ink-3">
                <Icon size={13} /> {s.value}
              </div>
              <div className="mt-0.5 text-tag leading-snug text-ink-2">{s.label}</div>
            </div>
          )
        })}
      </div>

      {scoreKeys.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {scoreKeys.map((k) => {
            const v = Math.round(review.scores![k] ?? 0)
            const tone = v >= 80 ? 'text-ok-deep' : v >= 60 ? 'text-warn-deep' : 'text-risk-deep'
            return (
              <span
                key={k}
                className="inline-flex items-center gap-1.5 rounded-chip bg-bg px-2.5 py-1 text-tag text-ink-2"
              >
                {k} <b className={tone}>{v}</b>
              </span>
            )
          })}
        </div>
      )}

      {review.review && (
        <p className="mt-4 rounded-card border-l-[3px] border-primary bg-primary-tint/30 p-3 text-aux leading-relaxed text-ink-2">
          {review.review}
        </p>
      )}

      {rewritten.length > 0 && (
        <div className="mt-4 flex items-start gap-2 rounded-card bg-primary-tint/40 p-3 text-tag text-ink-2">
          <RefreshCw size={14} className="mt-0.5 shrink-0 text-primary-deep" />
          <span>
            {plural(rewritten.length, 'section')} failed verification and{' '}
            {rewritten.length === 1 ? 'was' : 'were'} rewritten against the same
            evidence: {rewritten.join(', ')}.
          </span>
        </div>
      )}

      {open.length > 0 && (
        <div className="mt-4">
          <div
            className={`flex items-center gap-1.5 text-tag font-semibold ${
              majors.length > 0 ? 'text-risk-deep' : 'text-warn-deep'
            }`}
          >
            <AlertTriangle size={13} /> {plural(open.length, 'issue')} still open at
            sign-off
          </div>
          <ul className="mt-2 space-y-1.5">
            {open.slice(0, 8).map((f) => (
              <FindingRow key={f.finding_id} finding={f} />
            ))}
          </ul>
        </div>
      )}

      {fixed.length > 0 && (
        <details className="mt-4 rounded-card bg-bg p-3">
          <summary className="cursor-pointer text-tag font-semibold text-ink-2">
            <FileCheck size={13} className="mr-1 inline" />
            {plural(fixed.length, 'defect')} repaired automatically
          </summary>
          <ul className="mt-2 space-y-1.5">
            {fixed.map((f) => (
              <li key={f.finding_id} className="flex gap-2 text-tag leading-relaxed text-ink-3">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ok" />
                <span>{f.detail}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function FindingRow({ finding }: { finding: VerifyFinding }) {
  const major = finding.severity === 'major'
  return (
    <li className="flex gap-2 text-tag leading-relaxed text-ink-2">
      <span
        className={`mt-0.5 shrink-0 rounded-chip px-1.5 font-semibold ${
          major ? 'bg-risk/15 text-risk-deep' : 'bg-sun-soft text-warn-deep'
        }`}
      >
        {finding.severity}
      </span>
      <span>
        {finding.detail}
        {finding.fix && <span className="text-ink-3"> — {finding.fix}</span>}
      </span>
    </li>
  )
}
