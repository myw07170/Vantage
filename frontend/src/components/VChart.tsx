import ReactECharts from 'echarts-for-react'
import type { ChartSpec } from '../types'
import { plural } from '../lib/format'

/**
 * ECharts wrapper. The `option` comes from the backend verbatim — every axis
 * name, legend and tooltip label originates in backend/app/core/charts.py.
 */
export function VChart({
  spec,
  height = 280,
  onCite,
}: {
  spec: ChartSpec
  height?: number
  onCite?: (ids: string[]) => void
}) {
  const ids = spec.evidence_ids ?? []
  return (
    <div className="rounded-card border border-line/60 bg-card p-4 shadow-card">
      {spec.title && (
        <div className="mb-2 text-aux font-semibold text-ink">{spec.title}</div>
      )}
      <div className="overflow-x-auto">
        <ReactECharts
          option={spec.option}
          style={{ height, width: '100%', minWidth: 280 }}
          opts={{ renderer: 'svg' }}
          notMerge
        />
      </div>
      {ids.length > 0 && (
        <button
          onClick={() => onCite?.(ids)}
          className="mt-2 inline-flex items-center gap-1 text-tag text-primary-deep hover:underline"
          title="Jump to the evidence behind this chart"
        >
          Source: {plural(ids.length, 'item')} of evidence →
        </button>
      )}
    </div>
  )
}
