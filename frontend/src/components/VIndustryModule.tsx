import type { IndustryModule } from '../types'

/** Research methods are displayed without avatars or analyst headcounts. */
export function VIndustryModule({ module, compact = false }: { module: IndustryModule; compact?: boolean }) {
  return <article className={`rounded-card border border-line/60 bg-card shadow-card ${compact ? 'p-3' : 'p-5'}`}>
    <h3 className={`${compact ? 'text-aux' : 'text-body'} font-semibold text-ink`}>{module.name}</h3>
    {!compact && <p className="mt-2 text-aux leading-relaxed text-ink-2">{module.summary}</p>}
    <details className="mt-3 text-tag text-ink-2">
      <summary className="cursor-pointer font-medium text-primary-deep focus-visible:outline focus-visible:outline-primary">Sources, checks and searches</summary>
      {([
        ['Preferred evidence', module.preferred_sources],
        ['Research checks', module.checks],
        ['Search directions', module.search_angles],
      ] as const).map(([label, items]) => <div key={label} className="mt-3">
        <div className="font-semibold text-ink">{label}</div>
        <ul className="mt-1 list-disc space-y-1 pl-4 leading-relaxed">
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </div>)}
    </details>
  </article>
}
