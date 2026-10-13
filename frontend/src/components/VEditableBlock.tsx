import { Fragment, useEffect, useRef, useState } from 'react'
import { Check, X } from 'lucide-react'
import type { HighlightColor } from '../store/annotationStore'
import { BLOCK_ATTR, CITE_ATTR, citeRe, flatten, stripCitations } from '../lib/selection'

export interface InlineHighlight {
  id?: string
  text: string
  color: HighlightColor
  comment?: string
  /** Offsets into this block's source string; absent on legacy highlights. */
  start?: number
  end?: number
}

const MARK_CLS: Record<HighlightColor, string> = {
  sun: 'bg-sun/70',
  ok: 'bg-ok/40',
  risk: 'bg-risk/40',
  info: 'bg-info/40',
}

/** Replace citation markers in a plain string with clickable source chips. */
function renderCitations(
  value: string,
  evIndex: Map<string, number>,
  onCite: (ids: string[]) => void,
  keyPrefix: string,
): React.ReactNode {
  const re = citeRe()
  const out: React.ReactNode[] = []
  let pos = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(value)) !== null) {
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
        // The raw marker travels with the chip so a text selection over it can
        // still be mapped back to an offset in the source prose.
        {...{ [CITE_ATTR]: m[0] }}
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

interface Span {
  start: number
  end: number
  color: HighlightColor
  comment?: string
  id?: string
}

/**
 * Locate each highlight inside `value`.
 *
 * Offsets recorded at selection time are authoritative and are checked against
 * the text they were taken from, so an edit to the paragraph can't shift a mark
 * onto the wrong words. Anything without usable offsets falls back to a search
 * over the citation-free, whitespace-collapsed prose — which is what a
 * highlight saved before offsets existed has to be matched against.
 */
function locate(value: string, highlights: InlineHighlight[]): Span[] {
  const spans: Span[] = []
  let flat: { plain: string; map: number[] } | null = null

  for (const h of highlights) {
    const needle = (h.text || '').trim()
    if (typeof h.start === 'number' && typeof h.end === 'number') {
      if (h.start >= 0 && h.end <= value.length && h.end > h.start) {
        if (value.slice(h.start, h.end).trim() === needle) {
          spans.push({ start: h.start, end: h.end, color: h.color, comment: h.comment, id: h.id })
          continue
        }
      }
    }
    const flatNeedle = stripCitations(needle)
    if (flatNeedle.length < 2) continue
    if (!flat) flat = flatten(value)
    // The same phrase can occur more than once; mark every instance.
    let from = 0
    for (;;) {
      const idx = flat.plain.indexOf(flatNeedle, from)
      if (idx === -1) break
      const start = flat.map[idx]
      const end = flat.map[idx + flatNeedle.length - 1] + 1
      if (start !== undefined && end !== undefined) {
        spans.push({ start, end, color: h.color, comment: h.comment, id: h.id })
      }
      from = idx + flatNeedle.length
    }
  }

  if (spans.length === 0) return spans
  // Longest-first at a shared start, then drop overlaps — a mark cannot begin
  // inside the one before it without producing nested <mark> elements.
  spans.sort((a, b) => a.start - b.start || b.end - a.end)
  const merged: Span[] = []
  let cursor = 0
  for (const s of spans) {
    if (s.start < cursor) continue
    merged.push(s)
    cursor = s.end
  }
  return merged
}

/**
 * Render one string of report prose: reader highlights become `<mark>`, and
 * citation markers become source chips — including inside a highlight, so a
 * marked sentence keeps its working citations.
 */
function renderProse(
  value: string,
  highlights: InlineHighlight[] | undefined,
  evIndex: Map<string, number> | undefined,
  onCite: ((ids: string[]) => void) | undefined,
  keyPrefix: string,
): React.ReactNode {
  const spans = highlights && highlights.length > 0 ? locate(value, highlights) : []
  const cited = (slice: string, key: string): React.ReactNode =>
    evIndex && onCite ? renderCitations(slice, evIndex, onCite, key) : slice
  if (spans.length === 0) return cited(value, `${keyPrefix}-0`)

  const out: React.ReactNode[] = []
  let pos = 0
  spans.forEach((s, i) => {
    if (s.start > pos) {
      out.push(
        <Fragment key={`t${i}`}>{cited(value.slice(pos, s.start), `${keyPrefix}-t${i}`)}</Fragment>,
      )
    }
    out.push(
      <mark
        key={`m${i}`}
        data-highlight-id={s.id}
        className={`${MARK_CLS[s.color]} rounded-[2px] px-0.5 text-ink`}
        title={s.comment || undefined}
      >
        {cited(value.slice(s.start, s.end), `${keyPrefix}-m${i}`)}
      </mark>,
    )
    pos = s.end
  })
  if (pos < value.length) {
    out.push(<Fragment key="tail">{cited(value.slice(pos), `${keyPrefix}-tail`)}</Fragment>)
  }
  return out
}

/**
 * Read-only prose with its citation markers turned into source chips, and its
 * reader highlights marked. `blockId` makes the passage annotatable.
 */
export function VCitedText({
  text,
  evIndex,
  onCite,
  blockId,
  highlights,
}: {
  text: string
  evIndex?: Map<string, number>
  onCite?: (ids: string[]) => void
  blockId?: string
  highlights?: InlineHighlight[]
}) {
  const content = renderProse(text, highlights, evIndex, onCite, 'ct')
  if (!blockId) return <>{content}</>
  return <span {...{ [BLOCK_ATTR]: blockId }}>{content}</span>
}

/** Editable paragraph: double-click to edit, Cmd/Ctrl+Enter to save. */
export function VEditableBlock({
  value,
  editable,
  onSave,
  className = '',
  as = 'p',
  blockId,
  highlights,
  evIndex,
  onCite,
}: {
  value: string
  editable: boolean
  onSave: (text: string) => void
  className?: string
  as?: 'p' | 'div'
  /** Identifies this string of prose so highlights can anchor to it. */
  blockId?: string
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
          className="w-full resize-none rounded-card border border-primary/40 bg-primary-tint/20 p-3 text-body leading-relaxed text-ink outline-none transition-all focus:border-primary focus:shadow-glow"
        />
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <button
            onClick={commit}
            className="inline-flex items-center gap-1 rounded-btn bg-primary-deep px-2.5 h-7 text-tag font-medium text-white hover:bg-primary-deeper"
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
  return (
    <Tag
      {...(blockId ? { [BLOCK_ATTR]: blockId } : {})}
      className={`${className} ${
        editable ? 'cursor-text rounded transition-colors hover:bg-primary-tint/30' : ''
      }`}
      onDoubleClick={() => editable && setEditing(true)}
      title={editable ? 'Double-click to edit' : undefined}
    >
      {renderProse(value, highlights, evIndex, onCite, blockId ?? 'b')}
    </Tag>
  )
}
