import type { Anchor } from '../types'

/** Resolve DOM ranges to UTF-16 offsets in individual saved item strings. */
export function resolveSelection(root: HTMLElement, range: Range): Anchor[] {
  const anchors: Anchor[] = []
  for (const block of root.querySelectorAll<HTMLElement>('[data-item-text]')) {
    if (!range.intersectsNode(block)) continue
    const part = document.createRange()
    part.selectNodeContents(block)
    if (range.compareBoundaryPoints(Range.START_TO_START, part) > 0) part.setStart(range.startContainer, range.startOffset)
    if (range.compareBoundaryPoints(Range.END_TO_END, part) < 0) part.setEnd(range.endContainer, range.endOffset)
    if (part.collapsed) continue
    const prefix = document.createRange()
    prefix.selectNodeContents(block); prefix.setEnd(part.startContainer, part.startOffset)
    const start = prefix.toString().length, end = start + part.toString().length
    const text = block.textContent || '', quote = text.slice(start, end)
    if (!quote.trim()) continue
    anchors.push({ item_id: block.dataset.itemText!, start, end, quote, prefix: text.slice(Math.max(0, start-32), start), suffix: text.slice(end, end+32) })
  }
  return anchors
}

export function highlightedSegments(text: string, anchors: { start: number; end: number; color: string; id: string }[]) {
  const boundaries = [...new Set([0, text.length, ...anchors.flatMap(a => [Math.max(0,a.start), Math.min(text.length,a.end)])])].sort((a,b) => a-b)
  return boundaries.slice(0,-1).map((start,i) => {
    const end = boundaries[i+1], matches = anchors.filter(a => a.start <= start && a.end >= end)
    return { text: text.slice(start,end), start, color: matches.at(-1)?.color, ids: matches.map(a => a.id) }
  })
}
