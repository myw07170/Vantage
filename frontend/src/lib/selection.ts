/**
 * Anchoring a reader's text selection back onto the source prose.
 *
 * The report is written as plain strings that carry inline citation markers
 * (`[e_2a862152]`); the DOM shows those markers as numbered chips and collapses
 * whitespace. So `Selection.toString()` is *not* a substring of the paragraph it
 * came from, and re-finding a highlight by searching its text fails as soon as
 * the passage touches a citation or a line break.
 *
 * Instead a selection is resolved to character offsets into the source string,
 * reconstructed by walking the rendered block: text nodes contribute their
 * `textContent` verbatim, and a citation chip contributes the raw marker it
 * replaced (kept on the element as `data-cite-raw`). Highlights therefore
 * survive citation chips, collapsed whitespace and repeated phrases.
 */

const CITE_PATTERN = String.raw`\[(e_[0-9a-f]{4,20}(?:\s*,\s*e_[0-9a-f]{4,20})*)\]`

/** A fresh matcher each call — a shared `/g` regex carries `lastIndex` between callers. */
export const citeRe = () => new RegExp(CITE_PATTERN, 'gi')

/** Source prose with its citation markers removed, for display outside the article. */
export function stripCitations(value: string): string {
  return value
    .replace(citeRe(), '')
    .replace(/\s+([,.;:!?)\]])/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Marks the element that owns one editable/annotatable string of prose. */
export const BLOCK_ATTR = 'data-block-id'
/** Set on a citation chip, holding the raw marker text it stands in for. */
export const CITE_ATTR = 'data-cite-raw'

export interface SelectionHit {
  blockId: string
  sectionId: string
  /** Offsets into the block's *source* string, citation markers included. */
  start: number
  end: number
  /** The source slice — what `value.slice(start, end)` returns. */
  text: string
}

/**
 * Rebuild a block's source string while recording where a range's endpoints
 * land in it. Returns -1 for an endpoint that lies outside this block.
 */
function measure(block: HTMLElement, range: Range): { src: string; start: number; end: number } {
  let src = ''
  let start = -1
  let end = -1

  // A range endpoint can be given as (element, childIndex) rather than
  // (textNode, charOffset), so both forms have to be checked.
  const noteBoundary = (node: Node, childIndex: number) => {
    if (node === range.startContainer && range.startOffset === childIndex) start = src.length
    if (node === range.endContainer && range.endOffset === childIndex) end = src.length
  }

  const visit = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent ?? ''
      if (node === range.startContainer) start = src.length + Math.min(range.startOffset, text.length)
      if (node === range.endContainer) end = src.length + Math.min(range.endOffset, text.length)
      src += text
      return
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return
    const el = node as HTMLElement
    const raw = el.getAttribute(CITE_ATTR)
    if (raw !== null) {
      // A chip is opaque: it stands for the whole marker, so a selection that
      // clips it still counts the marker once.
      noteBoundary(el, 0)
      src += raw
      noteBoundary(el, el.childNodes.length)
      return
    }
    const children = Array.from(el.childNodes)
    for (let i = 0; i < children.length; i++) {
      noteBoundary(el, i)
      visit(children[i])
    }
    noteBoundary(el, children.length)
  }

  visit(block)
  return { src, start, end }
}

/** Narrow `range` to the part of it that falls inside `block`. */
function clampToBlock(block: HTMLElement, range: Range): Range {
  const r = document.createRange()
  r.selectNodeContents(block)
  if (range.compareBoundaryPoints(Range.START_TO_START, r) > 0) {
    r.setStart(range.startContainer, range.startOffset)
  }
  if (range.compareBoundaryPoints(Range.END_TO_END, r) < 0) {
    r.setEnd(range.endContainer, range.endOffset)
  }
  return r
}

/**
 * Resolve the current selection into one hit per annotatable block it covers.
 * A selection dragged across three paragraphs yields three hits, so each one
 * can be marked in place. Returns `[]` when the selection covers no block.
 */
export function resolveSelection(root: HTMLElement, range: Range): SelectionHit[] {
  const hits: SelectionHit[] = []
  const blocks = Array.from(root.querySelectorAll<HTMLElement>(`[${BLOCK_ATTR}]`))
  for (const block of blocks) {
    if (!range.intersectsNode(block)) continue
    let clamped: Range
    try {
      clamped = clampToBlock(block, range)
    } catch {
      continue // endpoints in a detached or reordered tree
    }
    if (clamped.collapsed) continue
    const { src, start, end } = measure(block, clamped)
    if (start < 0 || end < 0 || end <= start) continue
    const text = src.slice(start, end)
    if (stripCitations(text).length < 2) continue
    hits.push({
      blockId: block.getAttribute(BLOCK_ATTR) || '',
      sectionId: block.closest('[data-section-id]')?.getAttribute('data-section-id') || '',
      start,
      end,
      text,
    })
  }
  return hits
}

/**
 * A whitespace-collapsed, citation-free view of `value` plus a map from each
 * character back to its index in `value`. Used to re-find highlights that
 * carry no offsets — ones saved before offsets existed, or whose paragraph has
 * since been edited.
 */
export function flatten(value: string): { plain: string; map: number[] } {
  const skips: [number, number][] = []
  const re = citeRe()
  let m: RegExpExecArray | null
  while ((m = re.exec(value)) !== null) skips.push([m.index, m.index + m[0].length])

  const chars: string[] = []
  const map: number[] = []
  let i = 0
  let pendingSpace = false
  while (i < value.length) {
    const skip = skips.find(([from]) => from === i)
    if (skip) {
      i = skip[1]
      continue
    }
    const ch = value[i]
    if (/\s/.test(ch)) {
      pendingSpace = chars.length > 0
    } else {
      if (pendingSpace) {
        // Kept in step with stripCitations: a removed marker must not leave a
        // space stranded in front of the punctuation that followed it.
        if (!/[,.;:!?)\]]/.test(ch)) {
          chars.push(' ')
          map.push(i)
        }
        pendingSpace = false
      }
      chars.push(ch)
      map.push(i)
    }
    i++
  }
  return { plain: chars.join(''), map }
}
