import { Check, Minus, X } from 'lucide-react'

type Row = Record<string, unknown>

const s = (v: unknown): string => (v == null ? '' : String(v))
const arr = (v: unknown): Row[] => (Array.isArray(v) ? (v as Row[]) : [])
const strArr = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []

/** Feature tree: modules and how fully each brand supports them. */
export function VFeatureMatrix({ data }: { data: Row[] }) {
  if (!data?.length) return null
  return (
    <div className="mt-4 space-y-4">
      {data.map((brand, bi) => (
        <div key={bi} className="rounded-card border border-line bg-white p-4">
          <div className="mb-2 text-aux font-semibold text-ink">
            {s(brand.brand)} · feature tree
          </div>
          <div className="space-y-2.5">
            {arr(brand.modules).map((m, mi) => (
              <div key={mi}>
                <div className="text-tag font-medium text-primary-deep">
                  {m.category ? `${s(m.category)} · ` : ''}
                  {s(m.name)}
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {arr(m.sub_features).map((sf, si) => {
                    const Icon =
                      sf.support === 'full' ? Check : sf.support === 'none' ? X : Minus
                    const tint =
                      sf.support === 'full'
                        ? 'bg-ok/10 text-ok'
                        : sf.support === 'none'
                          ? 'bg-risk/10 text-risk'
                          : 'bg-sun-soft text-warn'
                    return (
                      <span
                        key={si}
                        title={s(sf.note)}
                        className={`inline-flex items-center gap-1 rounded-chip px-2 py-0.5 text-tag ${tint}`}
                      >
                        <Icon size={11} /> {s(sf.name)}
                      </span>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function formatPrice(price: unknown, currency: unknown, period: unknown): string {
  if (price == null) return 'Not published'
  const cur = s(currency) || 'USD'
  const symbol = cur === 'USD' ? '$' : `${cur} `
  const per = s(period) || 'month'
  return `${symbol}${price}/${per}`
}

/** Pricing tiers per brand. */
export function VPricingTable({ data }: { data: Row[] }) {
  if (!data?.length) return null
  return (
    <div className="mt-4 space-y-4">
      {data.map((brand, bi) => (
        <div
          key={bi}
          className="overflow-hidden rounded-card border border-line bg-white"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 bg-paper px-4 py-2">
            <span className="text-aux font-semibold text-ink">{s(brand.brand)}</span>
            <span className="rounded-chip bg-primary-tint px-2 py-0.5 text-tag text-primary-deep">
              {s(brand.model_type)}
              {brand.free_tier ? ' · has free tier' : ''}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-tag">
              <thead>
                <tr className="border-b border-line text-ink-3">
                  <th className="px-4 py-1.5 text-left font-medium">Tier</th>
                  <th className="px-2 py-1.5 text-left font-medium">Price</th>
                  <th className="px-2 py-1.5 text-left font-medium">For</th>
                  <th className="px-4 py-1.5 text-left font-medium">Includes</th>
                </tr>
              </thead>
              <tbody>
                {arr(brand.tiers).map((t, ti) => (
                  <tr key={ti} className="border-b border-line/60 last:border-0">
                    <td className="px-4 py-1.5 font-medium text-ink">{s(t.name)}</td>
                    <td className="px-2 py-1.5 text-primary-deep">
                      {formatPrice(t.price, brand.currency, t.period)}
                    </td>
                    <td className="px-2 py-1.5 text-ink-2">{s(t.target_user) || '—'}</td>
                    <td className="px-4 py-1.5 text-ink-2">
                      {strArr(t.includes).slice(0, 3).join(', ') || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}

/** User personas per brand. */
export function VPersonaCards({ data }: { data: Row[] }) {
  if (!data?.length) return null
  return (
    <div className="mt-4 space-y-3">
      {data.map((brand, bi) =>
        arr(brand.personas).map((p, pi) => {
          const needs = strArr(p.needs)
          const scenarios = strArr(p.scenarios)
          const painPoints = strArr(p.pain_points)
          const decisionFactors = strArr(p.decision_factors)
          return (
            <div
              key={`${bi}-${pi}`}
              className="rounded-card border border-line bg-white p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-aux font-semibold text-ink">{s(p.name)}</span>
                <span className="rounded-chip bg-paper px-2 py-0.5 text-tag text-ink-3">
                  {s(brand.brand)}
                </span>
                {p.segment ? (
                  <span className="text-tag text-ink-3">· {s(p.segment)}</span>
                ) : null}
              </div>
              <div className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1.5 text-tag sm:grid-cols-2">
                {needs.length > 0 && <Field label="Needs" items={needs} />}
                {scenarios.length > 0 && <Field label="Scenarios" items={scenarios} />}
                {painPoints.length > 0 && <Field label="Pain points" items={painPoints} />}
                {decisionFactors.length > 0 && (
                  <Field label="Decision factors" items={decisionFactors} />
                )}
              </div>
              {p.migration_cost ? (
                <p className="mt-2 rounded-btn bg-paper px-2.5 py-1.5 text-tag text-ink-2">
                  <span className="text-ink-3">Switching cost: </span>
                  {s(p.migration_cost)}
                </p>
              ) : null}
            </div>
          )
        }),
      )}
    </div>
  )
}

function Field({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <div className="text-ink-3">{label}</div>
      <div className="text-ink-2">{items.slice(0, 4).join(', ')}</div>
    </div>
  )
}
