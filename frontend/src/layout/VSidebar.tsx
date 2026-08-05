import { useEffect, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { Home, BarChart3, Users, Radar, Compass, Library } from 'lucide-react'
import { fetchDashboard } from '../lib/api'
import { formatDate, num, plural } from '../lib/format'
import { ACCENT_NAV, ROUTE_ACCENT } from '../lib/accents'
import { useReportStore } from '../store/reportStore'
import { VSkeleton } from '../components/ui'

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

export default function VSidebar() {
  const navigate = useNavigate()
  const [reports, setReports] = useState(0)
  const [evidence, setEvidence] = useState(0)
  const cards = useReportStore((s) => s.cards)
  const cardsLoading = useReportStore((s) => s.cardsLoading)
  const loadCards = useReportStore((s) => s.loadCards)

  useEffect(() => {
    fetchDashboard().then((d) => {
      if (d) {
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

  const recent = cards.slice(0, RECENT_LIMIT)

  return (
    <aside className="relative flex h-full w-[268px] shrink-0 flex-col border-r border-line bg-card/70">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-2.5 px-6 pt-6 pb-7"
      >
        <span className="grid h-9 w-9 place-items-center rounded-btn bg-primary-tint text-primary">
          <Compass size={22} strokeWidth={1.8} />
        </span>
        <span className="text-[20px] font-semibold tracking-tight text-ink">Vantage</span>
      </button>

      <nav className="flex flex-col gap-1 px-3">
        {navItems.map((item) => {
          // Each destination owns a hue, carried through to its page header.
          const nav = ACCENT_NAV[ROUTE_ACCENT[item.to] ?? 'blue']
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                [
                  'flex h-11 items-center gap-3 rounded-btn px-3.5 text-[15px] transition-all ease-vantage',
                  isActive ? nav.active : nav.idle,
                ].join(' ')
              }
            >
              <item.icon size={19} strokeWidth={1.8} />
              <span className="truncate">{item.label}</span>
            </NavLink>
          )
        })}
      </nav>

      {/* Recent reports. Deliberately a tier below the nav — smaller type,
          shorter rows, no icons — so the five destinations above stay the
          primary structure and this reads as their contents. */}
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
            recent.map((r) => (
              <Link
                key={r.id}
                to={`/report/${r.id}`}
                title={`${r.title} · ${formatDate(r.created_at)}`}
                className={`flex h-9 items-center rounded-btn px-3.5 text-aux transition-colors ease-vantage ${REPORT_NAV.idle}`}
              >
                <span className="truncate">{r.title}</span>
              </Link>
            ))
          )}
        </div>
      </section>

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
    </aside>
  )
}
