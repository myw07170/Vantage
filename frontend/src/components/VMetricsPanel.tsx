import { Gauge, Layers, ShieldCheck, TrendingUp } from 'lucide-react'
import type { ReportMetrics } from '../types'
import { asNum, asStr, duration, num } from '../lib/format'

function pct(v: unknown): string {
  const n = asNum(v)
  return n == null ? '—' : `${Math.round(n * 100)}%`
}

/**
 * Impact and business-outcome metrics.
 *
 * Every card carries its formula in a tooltip — the numbers are meant to be
 * checkable, not taken on faith.
 */
export function VMetricsPanel({ metrics }: { metrics?: ReportMetrics }) {
  if (!metrics) return null
  const eff = metrics.efficiency || {}
  const cov = metrics.coverage || {}
  const con = metrics.consistency || {}
  const biz = metrics.business || {}

  const cards = [
    {
      icon: TrendingUp,
      label: 'Time saved',
      tint: 'text-primary',
      value: asNum(eff.efficiency_multiple) != null ? `${eff.efficiency_multiple}×` : '—',
      sub: `${duration(asNum(eff.elapsed_minutes))} actual vs ${duration(
        asNum(eff.manual_estimate_minutes),
      )} manual`,
      tip: asStr(eff.formula),
    },
    {
      icon: Layers,
      label: 'Source coverage',
      tint: 'text-info-deep',
      value: asNum(cov.coverage_multiple) != null ? `${cov.coverage_multiple}×` : '—',
      sub: `${num(asNum(cov.independent_sources))} independent domains · ${num(
        asNum(cov.platforms_covered),
      )} source types`,
      tip: asStr(cov.formula),
    },
    {
      icon: ShieldCheck,
      label: 'Consistency',
      tint: 'text-ok-deep',
      value: pct(con.value),
      sub: `${pct(con.claims_with_evidence_ratio)} of claims sourced · ${pct(
        con.schema_completeness,
      )} structured`,
      tip: asStr(con.formula),
    },
    {
      icon: Gauge,
      label: 'High confidence',
      tint: 'text-warn-deep',
      value: pct(biz.accuracy),
      sub: `${pct(biz.cross_validated_ratio)} cross-validated · ${num(
        asNum(biz.rework_rounds),
      )} rework round(s)`,
      tip: asStr(biz.formula),
    },
  ]

  return (
    <div className="my-6">
      <div className="mb-3 flex items-center gap-1.5 text-aux font-semibold text-ink">
        <Gauge size={15} className="text-primary" /> Impact metrics
        <span className="font-normal text-ink-3">
          — measured against a manual analysis baseline; hover for the formula
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {cards.map((c) => {
          const Icon = c.icon
          return (
            <div
              key={c.label}
              title={c.tip}
              className="rounded-card border border-line bg-white p-3.5"
            >
              <div className={`flex items-center gap-1.5 text-tag ${c.tint}`}>
                <Icon size={13} /> {c.label}
              </div>
              <div className="mt-1 text-2xl font-bold text-ink">{c.value}</div>
              <div className="mt-0.5 text-tag leading-snug text-ink-3">{c.sub}</div>
            </div>
          )
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-tag">
        <Pill label="Dimension coverage" value={pct(biz.dimension_coverage)} />
        <Pill label="Brand coverage" value={pct(biz.brand_coverage)} />
        <Pill
          label="Reader corrections"
          value={asNum(biz.correction_rate) != null ? pct(biz.correction_rate) : 'No feedback yet'}
        />
        <Pill label="Tokens" value={num(asNum(eff.tokens_used))} />
      </div>
    </div>
  )
}

function Pill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-chip bg-paper px-2.5 py-1 text-ink-2">
      <span className="text-ink-3">{label}</span>
      <span className="font-semibold text-primary-deep">{value}</span>
    </span>
  )
}
