import { Fragment, useEffect, useRef, useState } from 'react'
import { Check, X } from 'lucide-react'
import type { HighlightColor } from '../store/annotationStore'

export interface InlineHighlight {
  text: string
  color: HighlightColor
  comment?: string
}

const MARK_CLS: Record<HighlightColor, string> = {
  sun: 'bg-sun/70',
  ok: 'bg-ok/40',
  risk: 'bg-risk/40',
  info: 'bg-info/40',
}

/**
 * Inline citation markers as the writer emits them: `[e_2a862152]`, or several
 * ids in one bracket. The verify stage has already dropped any id that matches
 * no evidence, so anything reaching here resolves.
 */
const CITE_RE = /\[(e_[0-9a-f]{4,20}(?:\s*,\s*e_[0-9a-f]{4,20})*)\]/gi

/** Replace citation markers in a plain string with clickable source chips. */
function renderCitations(
  value: string,
  evIndex: Map<string, number>,
  onCite: (ids: string[]) => void,
  keyPrefix: string,
): React.ReactNode {
  CITE_RE.lastIndex = 0
  const out: React.ReactNode[] = []
  let pos = 0
  let m: RegExpExecArray | null
  while ((m = CITE_RE.exec(value)) !== null) {
    // An id this report does not carry stays as written rather than becoming a
    // link that goes nowhere — reports written before the verify stage existed
    // can still contain fabricated ones.
    const ids = m[1]
      .split(',')
      .map((s) => s.trim().toLowerCase())
      .filter((id) => evIndex.has(id))
    if (ids.length === 0) continue
    if (m.index > pos) out.push(value.slice(pos, m.index))
    out.push(
      <button
        key={`${keyPrefix}-${m.index}`}
        onClick={() => onCite(ids)}
        title={`Jump to ${ids.length > 1 ? 'these sources' : 'this source'}`}
        className="mx-0.5 rounded-chip bg-primary-tint px-1.5 align-super text-[10px] font-semibold leading-tight text-primary-deep transition-colors hover:bg-primary-soft/50"
      >
        {ids.map((id) => evIndex.get(id)).join(',')}
      </button>,
    )
    pos = m.index + m[0].length
  }
  if (out.length === 0) return value
  if (pos < value.length) out.push(value.slice(pos))
  return out
}

/** Read-only prose with its citation markers turned into source chips. */
export function VCitedText({
  text,
  evIndex,
  onCite,
}: {
  text: string
  evIndex: Map<string, number>
  onCite: (ids: string[]) => void
}) {
  return <>{renderCitations(text, evIndex, onCite, 'ct')}</>
}

/** Slice the paragraph against saved highlights and wrap the matches in <mark>. */
function renderWithHighlights(value: string, highlights: InlineHighlight[]) {
  const hits: {
    start: number
    end: number
    color: HighlightColor
    comment?: string
  }[] = []
  for (const h of highlights) {
    const needle = (h.text || '').trim()
    if (needle.length < 2) continue
    let from = 0
    // The same highlighted phrase can occur more than once; mark every instance.
    while (from <= value.length) {
      const idx = value.indexOf(needle, from)
      if (idx === -1) break
      hits.push({ start: idx, end: idx + needle.length, color: h.color, comment: h.comment })
      from = idx + needle.length
    }
  }
  if (hits.length === 0) return value
  // Sort by position and drop overlaps, keeping the first.
  hits.sort((a, b) => a.start - b.start || b.end - a.end)
  const merged: typeof hits = []
  let cursor = 0
  for (const h of hits) {
    if (h.start < cursor) continue
    merged.push(h)
    cursor = h.end
  }
  const out: React.ReactNode[] = []
  let pos = 0
  merged.forEach((h, i) => {
    if (h.start > pos) out.push(value.slice(pos, h.start))
    out.push(
      <mark
        key={i}
        className={`${MARK_CLS[h.color]} rounded-[2px] px-0.5 text-ink`}
        title={h.comment || undefined}
      >
        {value.slice(h.start, h.end)}
      </mark>,
    )
    pos = h.end
  })
  if (pos < value.length) out.push(value.slice(pos))
  return out
}

/** Editable paragraph: double-click to edit, Cmd/Ctrl+Enter to save. */
export function VEditableBlock({
  value,
  editable,
  onSave,
  className = '',
  as = 'p',
  highlights,
  evIndex,
  onCite,
}: {
  value: string
  editable: boolean
  onSave: (text: string) => void
  className?: string
  as?: 'p' | 'div'
  highlights?: InlineHighlight[]
  /** evidence_id → its number in the report's source list. Enables citation chips. */
  evIndex?: Map<string, number>
  onCite?: (ids: string[]) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (editing && ref.current) {
      ref.current.focus()
      ref.current.style.height = 'auto'
      ref.current.style.height = `${ref.current.scrollHeight}px`
    }
  }, [editing])

  function commit() {
    setEditing(false)
    if (draft.trim() !== value.trim()) onSave(draft.trim())
  }
  function cancel() {
    setDraft(value)
    setEditing(false)
  }

  if (editing) {
    return (
      <div className="relative">
        <textarea
          ref={ref}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value)
            e.target.style.height = 'auto'
            e.target.style.height = `${e.target.scrollHeight}px`
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) commit()
            if (e.key === 'Escape') cancel()
          }}
          className="w-full resize-none rounded-card border border-primary/40 bg-primary-tint/20 p-3 text-body leading-relaxed text-ink outline-none focus:border-primary"
        />
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <button
            onClick={commit}
            className="inline-flex items-center gap-1 rounded-btn bg-primary px-2.5 h-7 text-tag font-medium text-white hover:bg-primary-deep"
          >
            <Check size={12} /> Save
          </button>
          <button
            onClick={cancel}
            className="inline-flex items-center gap-1 rounded-btn bg-line/60 px-2.5 h-7 text-tag font-medium text-ink-2 hover:bg-line"
          >
            <X size={12} /> Cancel
          </button>
          <span className="text-tag text-ink-3">⌘/Ctrl + Enter to save · Esc to cancel</span>
        </div>
      </div>
    )
  }

  const Tag = as
  // Highlights first, then citations over whatever plain text is left, so a
  // reader's highlight and a source chip can coexist in the same sentence.
  let content: React.ReactNode =
    highlights && highlights.length > 0 ? renderWithHighlights(value, highlights) : value
  if (evIndex && onCite) {
    const cite = (node: React.ReactNode, key: string) =>
      typeof node === 'string' ? renderCitations(node, evIndex, onCite, key) : node
    content = Array.isArray(content) ? (
      content.map((n, i) => <Fragment key={i}>{cite(n, `c${i}`)}</Fragment>)
    ) : (
      cite(content, 'c0')
    )
  }
  return (
    <Tag
      className={`${className} ${
        editable ? 'cursor-text rounded transition-colors hover:bg-primary-tint/30' : ''
      }`}
      onDoubleClick={() => editable && setEditing(true)}
      title={editable ? 'Double-click to edit' : undefined}
    >
      {content}
    </Tag>
  )
}
