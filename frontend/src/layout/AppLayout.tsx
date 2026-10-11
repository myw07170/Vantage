import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Plus, History, PanelLeftClose, PanelLeftOpen, ArrowUpRight } from 'lucide-react'
import { VLogo } from '../components/VLogo'
import { useReportStore } from '../store/reportStore'
import { useUIStore } from '../store/uiStore'

export default function AppLayout() {
  const location = useLocation()
  const cards = useReportStore(s => s.cards), loadCards = useReportStore(s => s.loadCards)
  const collapsed = useUIStore(s => s.sidebarCollapsed), toggle = useUIStore(s => s.toggleSidebar)
  const [error, setError] = useState('')
  useEffect(() => { void loadCards().catch(e => setError(String(e.message))) }, [loadCards])
  if (location.pathname.startsWith('/workspace/')) return <Outlet />
  return <div className={'app-shell ' + (collapsed ? 'rail-compact' : '')}>
    <aside className="sidebar">
      <Link to="/" className="brand"><VLogo size={36} /><span>Vantage<small>Product comparisons</small></span></Link>
      <nav aria-label="Main navigation">
        <NavLink to="/" end><Plus size={18} /><span>New comparison</span></NavLink>
        <NavLink to="/library"><History size={18} /><span>History</span></NavLink>
      </nav>
      <div className="recents"><p className="eyebrow">Recent comparisons</p>
        {cards.slice(0, 8).map(c => <Link key={c.report_id} to={'/report/' + c.report_id} title={c.title}>{c.title}<ArrowUpRight size={13} /></Link>)}
        {!cards.length && <p className="muted text-sm">Your comparisons will appear here.</p>}
        {error && <p className="error text-sm">{error}</p>}
      </div>
      <div className="sidebar-foot"><span>Local workspace · Single user</span><button className="icon-button" onClick={toggle} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>{collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}</button></div>
    </aside>
    <main className="main-content"><Outlet /></main>
  </div>
}
