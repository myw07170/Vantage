import {
  ShieldCheck,
  AlertTriangle,
  Lightbulb,
  ArrowRight,
  CheckCircle2,
} from 'lucide-react'
import type { AuditReview, AuditOpinion } from '../types'
import { plural } from '../lib/format'

/**
 * The quality officer's verdict: per-dimension scores, the problems found, the
 * fixes proposed, and the improvement after rework.
 *
 * Score dimension names come straight from the backend (audit.py), so they are
 * rendered as-is rather than mapped.
 */
export function VAuditReview({ review }: { review?: AuditReview }) {
  if (!review || (!review.before && !review.after)) return null
  const before = review.before
  const after = review.after
  const hasRework = (review.rework_rounds ?? 0) > 0 && after && after !== before
  const main: AuditOpinion = (hasRework || !before?.verdict ? after : before) || {}
  const scoreKeys = Object.keys(main.scores ?? {})
  const verdictPass = review.status === 'pass' || (!review.status && main.verdict === 'pass')
  const verdictLabel = review.simulated || review.status === 'simulated' ? 'Simulated · not verified'
    : review.status === 'blocked' ? 'Blocked · serious issues remain'
      : review.status === 'unavailable' ? 'Review unavailable · writing stopped'
        : review.status === 'pass_with_warnings' ? 'Approved with warnings'
          : review.status === 'reviewing' ? 'Review in progress'
            : verdictPass ? '✓ Approved' : '⟲ Rework required'

  const scoreColor = (v: number) =>
    v >= 80 ? 'text-ok-deep' : v >= 60 ? 'text-warn-deep' : 'text-risk-deep'
  const barColor = (v: number) => (v >= 80 ? 'bg-ok' : v >= 60 ? 'bg-warn' : 'bg-risk')

  return (
    <div className="my-6 rounded-card border border-line bg-card p-5 shadow-card">
      <div className="flex flex-wrap items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-btn bg-primary-tint text-primary-deep">
          <ShieldCheck size={17} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-aux font-semibold text-ink">Quality review</div>
          <div className="text-tag text-ink-3">
            The L3 quality officer scores each dimension, names the problems and
            proposes fixes before the report is signed off.
          </div>
        </div>
        <span
          className={`rounded-chip px-3 py-1 text-tag font-semibold ${
            verdictPass ? 'bg-ok/15 text-ok-deep' : 'bg-risk/15 text-risk-deep'
          }`}
        >
          {verdictLabel}
        </span>
      </div>

      {scoreKeys.length > 0 && (
        <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {scoreKeys.map((k) => {
            const cur = Math.round(main.scores![k] ?? 0)
            const prev = hasRework ? Math.round(before?.scores?.[k] ?? cur) : null
            const up = prev != null && cur > prev
            return (
              <div key={k} className="rounded-card border border-line/60 bg-bg p-3">
                <div className="flex items-center justify-between gap-2 text-tag">
                  <span className="min-w-0 truncate text-ink-2">{k}</span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    {prev != null && cur !== prev && (
                      <>
                        <span className="text-ink-3 line-through">{prev}</span>
                        <ArrowRight size={11} className="text-ink-3" />
                      </>
                    )}
                    <span className={`font-bold ${scoreColor(cur)}`}>{cur}</span>
                    {up && <span className="text-ok-deep">↑</span>}
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-chip bg-line">
                  <div
                    className={`h-full rounded-chip ${barColor(cur)} transition-all`}
                    style={{ width: `${cur}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}

      {main.review && (
        <p className="mt-4 rounded-card border-l-[3px] border-primary bg-primary-tint/30 p-3 text-aux leading-relaxed text-ink-2">
          {main.review}
        </p>
      )}

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        {main.issues && main.issues.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-tag font-semibold text-risk-deep">
              <AlertTriangle size={13} /> {plural(main.issues.length, 'problem')} found
            </div>
            <ul className="mt-2 space-y-1.5">
              {main.issues.map((it, i) => (
                <li key={i} className="flex gap-2 text-tag leading-relaxed text-ink-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-risk" />
                  <span>{it}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {main.suggestions && main.suggestions.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-tag font-semibold text-primary-deep">
              <Lightbulb size={13} /> {plural(main.suggestions.length, 'recommendation')}
            </div>
            <ul className="mt-2 space-y-1.5">
              {main.suggestions.map((it, i) => (
                <li key={i} className="flex gap-2 text-tag leading-relaxed text-ink-2">
                  <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-ok-deep" />
                  <span>{it}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {hasRework && (
        <div className="mt-4 flex items-start gap-2 rounded-card bg-sun-soft p-3 text-tag text-ink-2">
          <ShieldCheck size={14} className="mt-0.5 shrink-0 text-warn-deep" />
          <span>
            The review triggered {plural(review.rework_rounds ?? 0, 'round')} of rework,
            resolving {plural(review.issues_resolved ?? 0, 'issue')} on re-review.
          </span>
        </div>
      )}
      {!!review.history?.length && <details className="mt-4 text-tag text-ink-2">
        <summary className="cursor-pointer font-semibold">Review history ({review.history.length})</summary>
        {review.history.map((entry) => <div key={entry.round} className="mt-2 rounded-btn border border-line p-3">
          <div className="font-semibold">{entry.round === 0 ? 'Initial review' : `Repair round ${entry.round}`} · {entry.review.verdict}</div>
          <p className="mt-1 whitespace-pre-wrap">{entry.review.review}</p>
          <ul className="mt-1 space-y-1">{entry.review.issues?.map((text, i) => <li key={i}>{text}</li>)}</ul>
        </div>)}
      </details>}
      {!!review.issue_outcomes?.length && <details className="mt-4 text-tag text-ink-2">
        <summary className="cursor-pointer font-semibold">Issue outcomes</summary>
        <ul className="mt-2 space-y-2">{review.issue_outcomes.map((item, i) => <li key={`${item.issue_id}-${i}`}>
          <span className="font-semibold">{item.status?.replaceAll('_', ' ')} · {item.severity === 'high' ? 'Serious' : 'Minor'}</span>
          <p>{item.brand} {item.dimension}: {item.reason}</p>
          {item.resolution && <p>{item.resolution}</p>}
        </li>)}</ul>
      </details>}
      {!!review.unknowns?.length && <div className="mt-4 rounded-btn border border-warn/40 p-3 text-tag text-ink-2">
        <div className="font-semibold">Unknown or undisclosed · excluded from scoring and recommendations</div>
        <ul className="mt-2 space-y-1">{review.unknowns.map((item, i) => <li key={i}>{item.brand} · {item.dimension}: {item.reason}</li>)}</ul>
      </div>}
    </div>
  )
}
