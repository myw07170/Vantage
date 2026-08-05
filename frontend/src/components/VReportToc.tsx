import { useEffect, useState, type RefObject } from 'react'

export type TocItem = { id: string; title: string; level?: number }

/**
 * Geometry of the floating rail.
 *
 * The rail lives in the gutter between the reading column and the left edge of
 * the scroll container, and the expanded panel has to stay inside that gutter —
 * it overlays the page, so anything wider would cover the prose it exists to
 * navigate. The width is therefore measured, not chosen: when the gutter is too
 * narrow to hold a legible panel the rail hides itself rather than encroaching.
 * Collapsing the sidebar hands back ~200px and is usually enough to bring it
 * back on a narrower display.
 */
const RAIL_INSET = 10 // breathing room between the container edge and the rail
const PANEL_MAX = 240
const PANEL_MIN = 104 // below this the titles wrap to unreadable slivers
const RAIL_TOP = 148 // fixed to the viewport, sitting near the top of the read

/** Floating table of contents: a column of dots in the left gutter that expands
 *  into a heading list on hover. Absolutely positioned throughout, so nothing
 *  here changes the width of the article or shifts it sideways. */
export function VReportToc({
  items,
  activeId,
  progress,
  visible,
  onJump,
  containerRef,
  articleRef,
}: {
  items: TocItem[]
  activeId: string
  /** Reading progress, 0-100. Shown in the expanded panel. */
  progress: number
  /** Hidden over the cover image, where the dots would sit on the artwork. */
  visible: boolean
  onJump: (id: string) => void
  containerRef: RefObject<HTMLElement | null>
  articleRef: RefObject<HTMLElement | null>
}) {
  const [box, setBox] = useState({ left: 0, width: 0 })

  // Remeasured whenever either box resizes — which covers window resizes, the
  // sources column appearing at the `xl` breakpoint, and the sidebar collapsing.
  useEffect(() => {
    const article = articleRef.current
    const container = containerRef.current
    if (!article || !container) return

    const measure = () => {
      const a = article.getBoundingClientRect()
      const c = container.getBoundingClientRect()
      const gutter = a.left - c.left
      const width = Math.min(PANEL_MAX, gutter - RAIL_INSET * 2)
      setBox({ left: c.left + RAIL_INSET, width: width >= PANEL_MIN ? width : 0 })
    }

    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(article)
    ro.observe(container)
    window.addEventListener('resize', measure)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [articleRef, containerRef, items.length])

  if (items.length === 0 || box.width === 0) return null

  return (
    <div
      className={`group fixed z-30 hidden lg:block ${
        visible ? 'opacity-100' : 'pointer-events-none opacity-0'
      } transition-opacity duration-300`}
      style={{ left: box.left, top: RAIL_TOP }}
    >
      {/* Resting state: dots only. They keep the rail's box the same size the
          hover target needs, and fade out under the panel rather than moving. */}
      <div
        aria-hidden
        className="flex flex-col gap-2 px-2 py-2 transition-opacity duration-200 group-hover:opacity-0 group-focus-within:opacity-0"
      >
        {items.map((t) => (
          <span
            key={t.id}
            className={`h-1.5 rounded-chip transition-all duration-200 ease-vantage ${
              activeId === t.id ? 'w-6 bg-primary-deep' : 'w-3 bg-ink-3/40'
            }`}
          />
        ))}
      </div>

      {/* Expanded state: overlays the dots at the same origin, inside the
          gutter. `absolute` keeps it out of the document flow entirely. */}
      <nav
        aria-label="Report contents"
        style={{ width: box.width }}
        className="pointer-events-none absolute left-0 top-0 origin-left -translate-x-1 scale-95 rounded-card border border-line bg-card/95 p-1.5 opacity-0 shadow-float backdrop-blur transition-all duration-200 ease-vantage group-hover:pointer-events-auto group-hover:translate-x-0 group-hover:scale-100 group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:translate-x-0 group-focus-within:scale-100 group-focus-within:opacity-100"
      >
        <div className="px-2 pb-1.5 pt-1">
          <div className="flex items-baseline justify-between gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-3">
            <span>Contents</span>
            <span className="tabular-nums">{Math.round(progress)}%</span>
          </div>
          <div className="mt-1 h-0.5 w-full overflow-hidden rounded-chip bg-line">
            <div
              className="h-full rounded-chip bg-primary transition-all duration-150"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <div className="max-h-[60vh] overflow-y-auto">
          {items.map((t, i) => {
            const active = activeId === t.id
            return (
              <button
                key={t.id}
                onClick={() => onJump(t.id)}
                className={`flex w-full items-start gap-1.5 rounded-btn px-2 py-1.5 text-left text-tag leading-snug transition-colors ${
                  active
                    ? 'bg-primary-tint font-medium text-primary-deep'
                    : 'text-ink-2 hover:bg-primary-tint/50 hover:text-primary-deep'
                }`}
              >
                <span
                  className={`w-3 shrink-0 tabular-nums ${
                    active ? 'text-primary-deep' : 'text-ink-3'
                  }`}
                >
                  {i + 1}
                </span>
                <span className="min-w-0">{t.title}</span>
              </button>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
