import type { ReportComponent, WrittenAssertion } from '../types'
import { VFeatureMatrix, VPricingTable, VPersonaCards } from './VStructured'
import { VDataGrid } from './VDataGrid'
import { VChart } from './VChart'
import { VSentimentPanel } from './VSentimentPanel'
import { VCitedText } from './VEditableBlock'

/** Only typed, server-built components can be placed by the writing plan. */
export function VReportComponents({ components, onCite, evIndex }: {
  components?: ReportComponent[]; onCite: (ids: string[]) => void; evIndex: Map<string, number>
}) {
  return <>{components?.map((c, i) => <figure key={`${c.ref}-${i}`} className="mt-5">
    {c.kind === 'feature_tree' && <VFeatureMatrix data={c.data} />}
    {c.kind === 'pricing_model' && <VPricingTable data={c.data} />}
    {c.kind === 'user_persona' && <VPersonaCards data={c.data} />}
    {c.kind === 'chart' && <VChart spec={c.chart} onCite={onCite} />}
    {c.kind === 'data_grid' && <VDataGrid grid={c.data} title={c.title} />}
    {c.kind === 'sentiment' && <VSentimentPanel sentiment={c.data} />}
    {c.caption && <figcaption className="mt-2 text-tag text-ink-2"><VCitedText text={c.caption} evIndex={evIndex} onCite={onCite} /></figcaption>}
  </figure>)}</>
}

export function VWrittenJudgments({ assertions }: { assertions?: WrittenAssertion[] }) {
  const derived = assertions?.filter((a) => a.kind !== 'fact') ?? []
  if (!derived.length) return null
  return <details className="mt-4 rounded-btn border border-line p-3 text-tag text-ink-2">
    <summary className="cursor-pointer font-semibold">Inferences and recommendations ({derived.length})</summary>
    <ul className="mt-2 space-y-2">{derived.map((a) => <li key={a.assertion_id}>
      <span className="font-semibold">{a.kind === 'inference' ? 'Inference' : 'Recommendation'}: </span>{a.text}
      {a.conditions && <p className="mt-1 text-ink-3">Applies when: {a.conditions}</p>}
    </li>)}</ul>
  </details>
}
