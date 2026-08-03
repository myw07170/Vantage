import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { Home, BarChart3, Users, Radar, Compass, Library } from 'lucide-react'
import { fetchDashboard } from '../lib/api'
import { num, plural } from '../lib/format'

const navItems = [
  { to: '/', label: 'New research', icon: Home, end: true },
  { to: '/library', label: 'My reports', icon: BarChart3 },
  { to: '/knowledge', label: 'Knowledge base', icon: Library },
  { to: '/experts', label: 'Analyst team', icon: Users },
  { to: '/dashboard', label: 'Intelligence center', icon: Radar },
]

export default function VSidebar() {
  const navigate = useNavigate()
  const [reports, setReports] = useState(0)
  const [evidence, setEvidence] = useState(0)

  useEffect(() => {
    fetchDashboard().then((d) => {
      if (d) {
        setReports(d.reports)
        setEvidence(d.evidence_total)
      }
    })
  }, [])

  return (
    <aside className="relative flex h-full w-[236px] shrink-0 flex-col border-r border-line bg-card/70">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-2.5 px-6 pt-6 pb-7"
      >
        <span className="grid h-9 w-9 place-items-center rounded-btn bg-primary-tint text-primary">
          <Compass size={22} strokeWidth={1.8} />
        </span>
        <span className="text-[20px] font-semibold tracking-tight text-ink">Vantage</span>
      </button>

      <nav className="flex flex-1 flex-col gap-1 px-3">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              [
                'flex h-11 items-center gap-3 rounded-btn px-3.5 text-[15px] transition-all ease-vantage',
                isActive
                  ? 'bg-primary-tint font-medium text-primary-deep'
                  : 'text-ink-2 hover:bg-primary-tint/50',
              ].join(' ')
            }
          >
            <item.icon size={19} strokeWidth={1.8} />
            <span className="truncate">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="mx-3 mb-4 rounded-card border border-line/70 bg-primary-tint/40 p-4">
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
