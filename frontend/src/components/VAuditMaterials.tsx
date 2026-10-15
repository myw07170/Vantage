import type { AuditSnapshot } from '../types'
import { VFeatureMatrix, VPricingTable, VPersonaCards } from './VStructured'

const rows = (value: unknown): Record<string, unknown>[] => Array.isArray(value) ? value : []

/** Research preserved before writing. It is deliberately labelled as unapproved. */
export function VAuditMaterials({ snapshot }: { snapshot: AuditSnapshot }) {
  const verification = snapshot.writing_verification
  const findings = rows(verification?.findings ?? (verification?.review as Record<string, unknown> | undefined)?.findings)
  return <details className="my-4 rounded-card border border-line bg-card p-4 text-aux text-ink-2">
    <summary className="cursor-pointer font-semibold">View preserved research · not an approved report</summary>
    <p className="mt-2 text-tag">Materials and analysis remain available even when writing is stopped.</p>
    {snapshot.writing_status && <div className="mt-3 rounded-btn border border-line p-3">
      <div className="font-semibold">Writing: {snapshot.writing_status}</div>
      {snapshot.writing_error && <p className="mt-1 text-risk-deep">{snapshot.writing_error}</p>}
      {!!findings.length && <details className="mt-2">
        <summary className="cursor-pointer">Writing verification issues ({findings.length})</summary>
        <ul className="mt-2 space-y-2">{findings.map((f, i) => <li key={i}>
          <span className="font-semibold">{String(f.section_id ?? 'Report')} · {String(f.severity ?? 'Review')}: </span>
          {String(f.detail ?? '')}
          {!!f.fix && <p className="text-tag text-ink-3">Correction: {String(f.fix)}</p>}
        </li>)}</ul>
      </details>}
      {snapshot.writing_plan && <details className="mt-2">
        <summary className="cursor-pointer">Writing plan · {snapshot.writing_plan.title}</summary>
        <p className="mt-2">{snapshot.writing_plan.purpose}</p>
        {!!snapshot.writing_plan.core_questions?.length && <ul className="mt-2 list-inside list-disc">
          {snapshot.writing_plan.core_questions.map((q, i) => <li key={i}>{q}</li>)}
        </ul>}
        <p className="mt-1">{snapshot.writing_plan.thesis}</p>
        <ol className="mt-2 space-y-2">{snapshot.writing_plan.chapters.map((c) => <li key={c.id}>
          <span className="font-semibold">{c.title}</span> · {c.goal}
          <div className="text-tag text-ink-3">Builds on: {c.depends_on.join(', ') || 'Independent topic'}</div>
        </li>)}</ol>
      </details>}
      {!!snapshot.drafts && <details className="mt-2">
        <summary className="cursor-pointer">Preserved chapter drafts ({Object.keys(snapshot.drafts).length})</summary>
        {Object.entries(snapshot.drafts).map(([sid, draft]) => <details key={sid} className="mt-2 border-t border-line pt-2">
          <summary className="cursor-pointer">{snapshot.writing_plan?.chapters.find((c) => c.id === sid)?.title ?? sid}</summary>
          <p className="mt-2 font-semibold">{draft.key_takeaway}</p>
          {draft.paragraphs?.map((p, i) => <p className="mt-2 whitespace-pre-wrap" key={i}>{p}</p>)}
        </details>)}
      </details>}
      {!!snapshot.material_usage?.length && <details className="mt-2">
        <summary className="cursor-pointer">Material allocation and use</summary>
        <ul className="mt-2 space-y-1 text-tag">{snapshot.material_usage.map((u) => <li key={u.id}>
          {u.id} · {u.chapters.length ? `Assigned: ${u.chapters.join(', ')}` : u.reason} · Read by: {u.read_by.join(', ') || 'Not read by a chapter'}
        </li>)}</ul>
      </details>}
      {!!snapshot.writing_history?.length && <details className="mt-2">
        <summary className="cursor-pointer">Writing and repair history ({snapshot.writing_history.length})</summary>
        {snapshot.writing_history.map((h, i) => <details key={i} className="mt-2 border-t border-line pt-2">
          <summary className="cursor-pointer">{h.stage} {h.section_id ?? ''}{h.round ? ` · Round ${h.round}` : ''}
            {h.accepted === false ? ' · Candidate not accepted' : ''}</summary>
          {h.error && <p className="mt-2 text-risk-deep">{h.error}</p>}
          {h.draft?.paragraphs?.map((p, j) => <p className="mt-2 whitespace-pre-wrap" key={j}>{p}</p>)}
          {Object.entries(h.drafts ?? {}).map(([sid, draft]) => <div key={sid} className="mt-2">
            <div className="font-semibold">{sid}</div>
            {draft.paragraphs?.map((p, j) => <p className="mt-2 whitespace-pre-wrap" key={j}>{p}</p>)}
          </div>)}
        </details>)}
      </details>}
    </div>}
    <details className="mt-3">
      <summary className="cursor-pointer">Latest analysis ({snapshot.analysis?.claims?.length ?? 0} claims)</summary>
      <ul className="mt-2 space-y-2">{snapshot.analysis?.claims?.map((claim) => <li key={claim.claim_id}>
        {claim.text} <span className="text-tag text-ink-3">({claim.confidence})</span>
      </li>)}</ul>
      <VFeatureMatrix data={rows(snapshot.structured?.feature_tree)} />
      <VPricingTable data={rows(snapshot.structured?.pricing_model)} />
      <VPersonaCards data={rows(snapshot.structured?.user_persona)} />
    </details>
    <details className="mt-3">
      <summary className="cursor-pointer">Sources and saved text ({snapshot.evidence?.length ?? 0})</summary>
      {snapshot.evidence?.map((ev) => <details key={ev.evidence_id} className="mt-2 rounded-btn border border-line p-3">
        <summary className="cursor-pointer">{ev.brand} · {ev.title} · {ev.content_kind ?? 'excerpt'}</summary>
        <a href={ev.source_url} target="_blank" rel="noreferrer" className="mt-1 block break-all text-primary">{ev.source_url}</a>
        <p className="mt-2 whitespace-pre-wrap text-tag">{ev.full_text || ev.excerpt}</p>
      </details>)}
    </details>
    <details className="mt-3">
      <summary className="cursor-pointer">Search history ({snapshot.searches?.length ?? 0})</summary>
      <ul className="mt-2 space-y-2">{snapshot.searches?.map((s) => <li key={s.search_id}>
        {s.query} · {s.status === 'success' ? `${s.result_count ?? 0} results` : `Failed: ${s.error ?? 'unavailable'}`}
      </li>)}</ul>
    </details>
  </details>
}
