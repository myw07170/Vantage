import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  Home,
  BarChart3,
  Users,
  Radar,
  Compass,
  Library,
  PanelLeftClose,
  PanelLeftOpen,
  MoreVertical,
  Star,
  StarOff,
  Pencil,
  Trash2,
} from 'lucide-react'
import { deleteReport, fetchDashboard, updateReport } from '../lib/api'
import { formatDate, num, plural } from '../lib/format'
import { ACCENT_NAV, ROUTE_ACCENT } from '../lib/accents'
import { useReportStore } from '../store/reportStore'
import { useUIStore } from '../store/uiStore'
import { VConfirm, VSkeleton } from '../components/ui'
import { VLogo } from '../components/VLogo'
import type { ReportCard } from '../types'

const navItems = [
  { to: '/', label: 'New research', icon: Home, end: true },
  { to: '/library', label: 'My reports', icon: BarChart3 },
  { to: '/knowledge', label: 'Knowledge base', icon: Library },
  { to: '/experts', label: 'Analyst team', icon: Users },
  { to: '/dashboard', label: 'Intelligence center', icon: Radar },
]

/** How many reports the sidebar lists before deferring to the library. Enough
 *  to cover the run you just finished and the handful around it; past that a
 *  scroll list is a worse way to find something than the library's grid. */
const RECENT_LIMIT = 8

// The recents list belongs to /library, so it borrows that route's hue. Colour
// is wayfinding here, not decoration: the section and the nav item that opens
// its full view read as the same place.
const REPORT_NAV = ACCENT_NAV[ROUTE_ACCENT['/library']]

// Last-known workspace totals, kept outside the component. The rail remounts on
// every move between the shell and the full-screen pages; without this the two
// counters would drop to zero and count back up each time, which reads as the
// workspace briefly emptying. Seeded state, still refetched on mount.
let lastTotals = { reports: 0, evidence: 0 }

/** Row-menu geometry. Fixed rather than absolute: the list it opens from is a
 *  scroll container, and an absolutely positioned menu is clipped by it. */
const MENU_W = 168
const MENU_H = 124

export default function VSidebar() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [reports, setReports] = useState(lastTotals.reports)
  const [evidence, setEvidence] = useState(lastTotals.evidence)
  const cards = useReportStore((s) => s.cards)
  const cardsLoading = useReportStore((s) => s.cardsLoading)
  const loadCards = useReportStore((s) => s.loadCards)
  const patchCard = useReportStore((s) => s.patchCard)
  const removeCard = useReportStore((s) => s.removeCard)
  const collapsed = useUIStore((s) => s.sidebarCollapsed)
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)

  // Row actions. One menu for the whole list rather than one per row: only ever
  // one is open, and it is positioned from the button that opened it.
  const [menu, setMenu] = useState<{ card: ReportCard; top: number; left: number } | null>(
    null,
  )
  const [renaming, setRenaming] = useState<{ id: string; value: string } | null>(null)
  const [pendingDelete, setPendingDelete] = useState<ReportCard | null>(null)
  const [deleting, setDeleting] = useState(false)
  const renameRef = useRef<HTMLInputElement>(null)
  // One edit resolves once. Enter commits and unmounts the field, which can also
  // fire its blur handler, and Escape unmounts it while a stale blur closure
  // still holds the abandoned value — either path would otherwise send a second
  // PATCH, or undo the cancel.
  const renameSettled = useRef(false)

  useEffect(() => {
    fetchDashboard().then((d) => {
      if (d) {
        lastTotals = { reports: d.reports, evidence: d.evidence_total }
        setReports(d.reports)
        setEvidence(d.evidence_total)
      }
    })
  }, [])

  // Refetched on every mount rather than once: the run and report views live
  // outside this shell, so remounting is exactly when a new report has landed.
  useEffect(() => {
    loadCards()
  }, [loadCards])

  // Dismiss the menu on anything that would move it: a click elsewhere, Escape,
  // a scroll of the list underneath it, a resize. Registered only while open.
  useEffect(() => {
    if (!menu) return
    const close = () => setMenu(null)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('pointerdown', close)
    window.addEventListener('keydown', onKey)
    window.addEventListener('resize', close)
    // Capture phase: the list scrolls, and a scroll on a nested element does
    // not bubble to window.
    window.addEventListener('scroll', close, true)
    return () => {
      window.removeEventListener('pointerdown', close)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', close, true)
    }
  }, [menu])

  // Focus the field the moment a rename starts, and select the whole title —
  // renaming usually means replacing, not appending.
  //
  // Keyed on the id, never on `renaming` itself: that object is rebuilt on every
  // keystroke, so depending on it re-ran `select()` after each character and the
  // next one overwrote the whole field.
  const renamingId = renaming?.id ?? null
  useEffect(() => {
    if (!renamingId) return
    // Focus explicitly: the menu button that started the rename has just been
    // unmounted, so focus has fallen back to the body.
    renameRef.current?.focus()
    renameRef.current?.select()
  }, [renamingId])

  function openMenu(e: React.MouseEvent<HTMLButtonElement>, card: ReportCard) {
    if (menu?.card.id === card.id) return setMenu(null)
    const r = e.currentTarget.getBoundingClientRect()
    setMenu({
      card,
      // Flip above the button when there is no room below, so the last rows in
      // a long list do not open a menu off the bottom of the screen.
      top:
        r.bottom + MENU_H + 8 > window.innerHeight ? r.top - MENU_H - 6 : r.bottom + 6,
      left: Math.min(r.right - MENU_W, window.innerWidth - MENU_W - 8),
    })
  }

  async function toggleStar(card: ReportCard) {
    setMenu(null)
    const next = !card.starred
    const res = await updateReport(card.id, { starred: next })
    // Applied only on success: an optimistic flip would leave the star showing
    // a state the server never accepted, and `safeJson` has already surfaced
    // the failure in a toast.
    if (res.ok) patchCard(card.id, { starred: next })
  }

  async function commitRename() {
    if (!renaming || renameSettled.current) return
    renameSettled.current = true
    const card = cards.find((c) => c.id === renaming.id)
    const next = renaming.value.trim()
    setRenaming(null)
    if (!card || !next || next === card.title) return
    const res = await updateReport(card.id, { title: next })
    if (res.ok) patchCard(card.id, { title: next })
  }

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeleting(true)
    const res = await deleteReport(pendingDelete.id)
    setDeleting(false)
    setPendingDelete(null)
    if (!res.ok) return
    // Leave before the row does, if the deleted report is the one on screen —
    // otherwise the reader is left looking at a report the server no longer has.
    const open = pathname === `/report/${pendingDelete.id}`
    removeCard(pendingDelete.id)
    if (open) navigate('/library')
  }

  // Starred first, everything else in the order the server sent (newest first).
  // `sort` is stable, so within each group the recency ordering is preserved —
  // and a starred report cannot fall off the end of the list as it ages.
  const recent = useMemo(
    () =>
      [...cards]
        .sort((a, b) => Number(!!b.starred) - Number(!!a.starred))
        .slice(0, RECENT_LIMIT),
    [cards],
  )

  return (
    <aside
      className={`relative flex h-full shrink-0 flex-col border-r border-line bg-card/70 transition-[width] duration-200 ease-vantage ${
        // Expanded / collapsed rail width. The single knob for how much of the
        // window the sidebar takes; every page beside it is `flex-1`, so widening
        // here narrows the content column and nothing else has to change.
        collapsed ? 'w-[68px]' : 'w-[312px]'
      }`}
    >
      {/* Wordmark and the collapse control. Side by side at full width; stacked
          into the rail when collapsed, where there is only one column to use. */}
      <div
        className={
          collapsed
            ? 'flex flex-col items-center gap-1 pt-4 pb-5'
            : 'flex items-center gap-2.5 px-6 pt-6 pb-7'
        }
      >
        <button
          onClick={() => navigate('/')}
          title={collapsed ? 'Vantage · new research' : undefined}
          className="flex items-center gap-2.5"
        >
          {/* Labelled only in the rail: at full width the wordmark beside it
              already names the app, and two readings of "Vantage" in a row is
              a worse result than a decorative image. */}
          <VLogo size={36} alt={collapsed ? 'Vantage' : ''} />
          {!collapsed && (
            <span className="text-[20px] font-semibold tracking-tight text-ink">
              Vantage
            </span>
          )}
        </button>
        <button
          onClick={toggleSidebar}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
          className={`grid h-8 w-8 shrink-0 place-items-center rounded-btn text-ink-3 transition-colors hover:bg-primary-tint hover:text-primary-deep ${
            collapsed ? '' : 'ml-auto'
          }`}
        >
          {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
        </button>
      </div>

      <nav className="flex flex-col gap-1 px-3">
        {navItems.map((item) => {
          // Each destination owns a hue, carried through to its page header.
          const nav = ACCENT_NAV[ROUTE_ACCENT[item.to] ?? 'blue']
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              title={collapsed ? item.label : undefined}
              className={({ isActive }) =>
                [
                  'flex h-11 items-center rounded-btn text-[15px] transition-all ease-vantage',
                  collapsed ? 'w-11 justify-center' : 'gap-3 px-3.5',
                  isActive ? nav.active : nav.idle,
                ].join(' ')
              }
            >
              <item.icon size={19} strokeWidth={1.8} />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </NavLink>
          )
        })}
      </nav>

      {/* Recent reports. Deliberately a tier below the nav — smaller type,
          shorter rows, no icons — so the five destinations above stay the
          primary structure and this reads as their contents.

          It is the one block with no icon form, so collapsing drops it entirely
          rather than inventing eight indistinguishable glyphs; the flexer below
          holds the workspace card at the foot of the rail in its place. */}
      {collapsed ? (
        <div className="flex-1" />
      ) : (
        <section className="mt-7 flex min-h-0 flex-1 flex-col px-3">
          <div className="flex items-baseline justify-between gap-2 px-3.5 pb-1.5">
            <h2 className="text-tag font-semibold uppercase tracking-[0.08em] text-ink-3">
              Recent reports
            </h2>
            {cards.length > RECENT_LIMIT && (
              <Link
                to="/library"
                className="shrink-0 text-tag text-ink-3 transition-colors hover:text-indigo-deep"
              >
                All {num(cards.length)}
              </Link>
            )}
          </div>

          <div className="-mr-1 min-h-0 flex-1 space-y-0.5 overflow-y-auto pr-1">
            {cardsLoading && cards.length === 0 ? (
              // Uneven widths, because what is arriving is a list of titles. One
              // element rather than four, so the scroll list's own `space-y` does
              // not fight the spacing here.
              <div className="space-y-3.5 px-3.5 py-2">
                {['w-full', 'w-4/5', 'w-full', 'w-3/5'].map((w) => (
                  <VSkeleton key={w} className={`h-3.5 rounded-chip ${w}`} />
                ))}
              </div>
            ) : recent.length === 0 ? (
              <p className="px-3.5 py-1 text-tag leading-relaxed text-ink-3">
                No reports yet. Your finished research lands here.
              </p>
            ) : (
              recent.map((r) =>
                renaming?.id === r.id ? (
                  // The row becomes the field, so the title stays exactly where
                  // it was and the list does not reflow while editing.
                  <input
                    key={r.id}
                    ref={renameRef}
                    value={renaming.value}
                    onChange={(e) => setRenaming({ id: r.id, value: e.target.value })}
                    onBlur={commitRename}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') commitRename()
                      // Escape has to clear the state before blur fires, or the
                      // blur handler would commit the edit being abandoned.
                      if (e.key === 'Escape') {
                        renameSettled.current = true
                        setRenaming(null)
                      }
                    }}
                    maxLength={200}
                    aria-label={`Rename report: ${r.title}`}
                    className="h-9 w-full rounded-btn border border-primary bg-card px-3 text-aux text-ink outline-none"
                  />
                ) : (
                  <div
                    key={r.id}
                    className={`group relative flex h-9 items-center rounded-btn text-aux transition-colors ease-vantage ${REPORT_NAV.idle}`}
                  >
                    <Link
                      to={`/report/${r.id}`}
                      title={`${r.title} · ${formatDate(r.created_at)}`}
                      className="flex min-w-0 flex-1 items-center gap-1.5 py-2 pl-3.5 pr-9"
                    >
                      {r.starred && (
                        <Star
                          size={12}
                          className="shrink-0 fill-sun text-sun"
                          aria-label="Starred"
                        />
                      )}
                      <span className="truncate">{r.title}</span>
                    </Link>
                    {/* Sibling of the link, not a child — a button inside an
                        anchor is invalid and the anchor swallows its click.
                        Hidden until the row is hovered or the control itself is
                        focused, so the list stays a list of titles; it also
                        stays visible while its own menu is open. */}
                    <button
                      // The dismiss listener sits on window's bubble phase, so
                      // the trigger has to stop its own pointerdown from
                      // reaching it — otherwise the menu closes on press and
                      // reopens on release, and can never be toggled shut.
                      onPointerDown={(e) => e.stopPropagation()}
                      onClick={(e) => openMenu(e, r)}
                      aria-label={`Actions for ${r.title}`}
                      aria-haspopup="menu"
                      aria-expanded={menu?.card.id === r.id}
                      title="More"
                      className={`absolute right-1 grid h-7 w-7 place-items-center rounded-btn text-ink-3 transition-opacity hover:bg-line/60 hover:text-ink focus-visible:opacity-100 group-hover:opacity-100 ${
                        menu?.card.id === r.id ? 'bg-line/60 text-ink opacity-100' : 'opacity-0'
                      }`}
                    >
                      <MoreVertical size={15} />
                    </button>
                  </div>
                ),
              )
            )}
          </div>
        </section>
      )}

      {collapsed ? (
        <button
          onClick={() => navigate('/library')}
          title={`Workspace · ${plural(reports, 'report')} completed · ${num(evidence)} sources archived`}
          aria-label="Workspace"
          className="mx-auto mb-4 grid h-11 w-11 place-items-center rounded-btn border border-line/70 bg-primary-tint/40 text-primary transition-colors hover:bg-primary-tint"
        >
          <Compass size={18} strokeWidth={2} />
        </button>
      ) : (
        <div className="mx-3 mb-4 mt-4 rounded-card border border-line/70 bg-primary-tint/40 p-4">
          <div className="flex items-center gap-2">
            <Compass size={16} className="text-primary" strokeWidth={2} />
            <span className="text-aux font-semibold text-ink">Workspace</span>
          </div>
          <p className="mt-1 text-tag text-ink-3">{plural(reports, 'report')} completed</p>
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-chip bg-line">
            <div
              className="h-full rounded-chip bg-primary transition-all"
              style={{ width: `${Math.min(100, reports * 10)}%` }}
            />
          </div>
          <p className="mt-1.5 text-right text-tag text-ink-3">
            {num(evidence)} sources archived
          </p>
        </div>
      )}

      {/* Row menu. Fixed to the viewport at the trigger's coordinates so the
          scrolling list cannot clip it, and stopping its own pointerdown so the
          dismiss listener does not tear it down before a click lands. */}
      {menu && (
        <div
          role="menu"
          aria-label={`Actions for ${menu.card.title}`}
          onPointerDown={(e) => e.stopPropagation()}
          style={{ top: menu.top, left: menu.left, width: MENU_W }}
          className="fixed z-50 overflow-hidden rounded-card border border-line bg-card py-1 shadow-float"
        >
          <button
            role="menuitem"
            onClick={() => toggleStar(menu.card)}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-aux text-ink-2 transition-colors hover:bg-primary-tint hover:text-primary-deep"
          >
            {menu.card.starred ? <StarOff size={15} /> : <Star size={15} />}
            {menu.card.starred ? 'Unstar' : 'Star'}
          </button>
          <button
            role="menuitem"
            onClick={() => {
              renameSettled.current = false
              setRenaming({ id: menu.card.id, value: menu.card.title })
              setMenu(null)
            }}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-aux text-ink-2 transition-colors hover:bg-primary-tint hover:text-primary-deep"
          >
            <Pencil size={15} /> Rename
          </button>
          <button
            role="menuitem"
            onClick={() => {
              setPendingDelete(menu.card)
              setMenu(null)
            }}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-aux text-risk-deep transition-colors hover:bg-risk/10"
          >
            <Trash2 size={15} /> Delete
          </button>
        </div>
      )}

      {/* Same wording and cascade warning as the library's delete, because it is
          the same irreversible action reached from a different place. */}
      <VConfirm
        open={pendingDelete !== null}
        title="Delete this report?"
        message={
          <>
            <span className="font-medium text-ink">{pendingDelete?.title}</span> and its{' '}
            {num(pendingDelete?.evidence_count ?? 0)} collected sources will be removed
            permanently. This cannot be undone.
          </>
        }
        confirmLabel="Yes, delete"
        busyLabel="Deleting…"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => !deleting && setPendingDelete(null)}
      />
    </aside>
  )
}
