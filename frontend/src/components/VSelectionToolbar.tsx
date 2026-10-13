import { useEffect, useState } from 'react'
import { Highlighter, BookmarkPlus, MessageSquarePlus } from 'lucide-react'
import type { HighlightColor } from '../store/annotationStore'
import { resolveSelection, stripCitations } from '../lib/selection'
import type { SelectionHit } from '../lib/selection'

interface Sel {
  /** One per annotatable block the selection covers. Empty when it covers none. */
  hits: SelectionHit[]
  /** Plain reading text of the whole selection, for notes and the knowledge base. */
  text: string
  sectionId: string
  x: number
  y: number
}

const COLORS: { key: HighlightColor; cls: string; label: string }[] = [
  { key: 'sun', cls: 'bg-sun', label: 'Important' },
  { key: 'ok', cls: 'bg-ok', label: 'Agree' },
  { key: 'risk', cls: 'bg-risk', label: 'Questionable' },
  { key: 'info', cls: 'bg-info', label: 'Follow up' },
]

/** Popup that appears on text selection: highlight, annotate, or save. */
export function VSelectionToolbar({
  containerRef,
  enabled,
  onHighlight,
  onComment,
  onSaveKB,
}: {
  containerRef: React.RefObject<HTMLElement | null>
  enabled: boolean
  /** Receives one anchor per block covered; empty when the passage can't be marked inline. */
  onHighlight: (hits: SelectionHit[], text: string, sectionId: string, color: HighlightColor) => void
  onComment: (hits: SelectionHit[], text: string, sectionId: string) => void
  onSaveKB: (sectionId: string, text: string) => void
}) {
  const [sel, setSel] = useState<Sel | null>(null)

  useEffect(() => {
    if (!enabled) return

    function read() {
      const container = containerRef.current
      const s = window.getSelection()
      if (!container || !s || s.rangeCount === 0 || s.isCollapsed) {
        setSel(null)
        return
      }
      const range = s.getRangeAt(0)
      // Both endpoints must sit inside the article; a selection that started in
      // the sidebar and dragged in is not an annotation.
      if (
        !container.contains(range.commonAncestorContainer) &&
        range.commonAncestorContainer !== container
      ) {
        setSel(null)
        return
      }
      const text = stripCitations(s.toString())
      if (text.length < 2) {
        setSel(null)
        return
      }
      const hits = resolveSelection(container, range)
      const sectionId =
        hits[0]?.sectionId ||
        (range.startContainer.nodeType === Node.ELEMENT_NODE
          ? (range.startContainer as HTMLElement)
          : range.startContainer.parentElement
        )
          ?.closest('[data-section-id]')
          ?.getAttribute('data-section-id') ||
        ''
      const rect = range.getBoundingClientRect()
      if (rect.width === 0 && rect.height === 0) {
        setSel(null)
        return
      }
      const cRect = container.getBoundingClientRect()
      setSel({
        hits,
        text,
        sectionId,
        x: rect.left + rect.width / 2 - cRect.left,
        y: rect.top - cRect.top - 8,
      })
    }

    // `mouseup` covers dragging; `keyup` covers shift+arrow and Ctrl+A. Both are
    // read on the next frame so the browser has settled the final range.
    const schedule = () => window.requestAnimationFrame(read)
    document.addEventListener('mouseup', schedule)
    document.addEventListener('keyup', schedule)
    return () => {
      document.removeEventListener('mouseup', schedule)
      document.removeEventListener('keyup', schedule)
    }
  }, [enabled, containerRef])

  if (!enabled || !sel) return null

  const clear = () => {
    setSel(null)
    window.getSelection()?.removeAllRanges()
  }

  return (
    <div
      className="absolute z-30 -translate-x-1/2 -translate-y-full"
      style={{ left: sel.x, top: sel.y }}
      onMouseDown={(e) => e.preventDefault()}
    >
      <div className="flex items-center gap-1.5 rounded-card border border-line bg-card px-2 py-1.5 shadow-float">
        <Highlighter size={14} className="text-ink-3" />
        {COLORS.map((c) => (
          <button
            key={c.key}
            title={`Highlight · ${c.label}`}
            aria-label={`Highlight as ${c.label}`}
            onClick={() => {
              onHighlight(sel.hits, sel.text, sel.sectionId, c.key)
              clear()
            }}
            className={`h-5 w-5 rounded-full ${c.cls} ring-1 ring-black/5 transition-transform hover:scale-110`}
          />
        ))}
        <span className="mx-0.5 h-4 w-px bg-line" />
        <button
          title="Add a note"
          aria-label="Add a note"
          onClick={() => {
            onComment(sel.hits, sel.text, sel.sectionId)
            clear()
          }}
          className="grid h-6 w-6 place-items-center rounded-btn text-ink-2 hover:bg-primary-tint hover:text-primary-deep"
        >
          <MessageSquarePlus size={14} />
        </button>
        <button
          title="Save to knowledge base"
          aria-label="Save to knowledge base"
          onClick={() => {
            onSaveKB(sel.sectionId, sel.text)
            clear()
          }}
          className="grid h-6 w-6 place-items-center rounded-btn text-ink-2 hover:bg-primary-tint hover:text-primary-deep"
        >
          <BookmarkPlus size={14} />
        </button>
      </div>
    </div>
  )
}
