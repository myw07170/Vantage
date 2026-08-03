import { useEffect, useState } from 'react'
import { Highlighter, BookmarkPlus, MessageSquarePlus } from 'lucide-react'
import type { HighlightColor } from '../store/annotationStore'

interface Sel {
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
  onHighlight: (sectionId: string, text: string, color: HighlightColor) => void
  onComment: (sectionId: string, text: string) => void
  onSaveKB: (sectionId: string, text: string) => void
}) {
  const [sel, setSel] = useState<Sel | null>(null)

  useEffect(() => {
    if (!enabled) return
    function onUp() {
      const s = window.getSelection()
      if (!s || s.isCollapsed || !s.toString().trim()) {
        setSel(null)
        return
      }
      const text = s.toString().trim()
      if (text.length < 2) return
      const range = s.getRangeAt(0)
      const node = range.startContainer.parentElement?.closest('[data-section-id]')
      const container = containerRef.current
      if (!node || !container || !container.contains(node)) {
        setSel(null)
        return
      }
      const rect = range.getBoundingClientRect()
      const cRect = container.getBoundingClientRect()
      setSel({
        text,
        sectionId: node.getAttribute('data-section-id') || '',
        x: rect.left + rect.width / 2 - cRect.left,
        y: rect.top - cRect.top - 8,
      })
    }
    document.addEventListener('mouseup', onUp)
    return () => document.removeEventListener('mouseup', onUp)
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
              onHighlight(sel.sectionId, sel.text, c.key)
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
            onComment(sel.sectionId, sel.text)
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
