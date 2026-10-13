import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Suspense, lazy, useEffect } from 'react'
import AppLayout, { RouteFallback } from './layout/AppLayout'
import VShellFallback from './layout/VShellFallback'
import HomePage from './pages/HomePage'
import { useExpertStore } from './store/expertStore'

// Home is eager — it is the entry point and must paint immediately. Everything
// else loads on navigation, which keeps ECharts (~1MB) and D3 (~250kB) out of
// the first request; neither is needed until a report or graph is opened.
const ClarifyPage = lazy(() => import('./pages/ClarifyPage'))
const WorkspacePage = lazy(() => import('./pages/WorkspacePage'))
const ReportPage = lazy(() => import('./pages/ReportPage'))
const GraphPage = lazy(() => import('./pages/GraphPage'))
const TracePage = lazy(() => import('./pages/TracePage'))
const ExpertsPage = lazy(() => import('./pages/ExpertsPage'))
const ExpertDetailPage = lazy(() => import('./pages/ExpertDetailPage'))
const LibraryPage = lazy(() => import('./pages/LibraryPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const KnowledgePage = lazy(() => import('./pages/KnowledgePage'))

export default function App() {
  const load = useExpertStore((s) => s.load)
  useEffect(() => {
    load()
  }, [load])

  return (
    <BrowserRouter>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          {/* Pages inside the sidebar shell */}
          <Route element={<AppLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/experts" element={<ExpertsPage />} />
            <Route path="/experts/:id" element={<ExpertDetailPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
          </Route>

          {/* Full-screen pages: clarify, live run, report, graph, trace */}
          <Route path="/clarify/:taskId" element={<ClarifyPage />} />
          <Route path="/workspace/:taskId" element={<WorkspacePage />} />
          {/* The report carries the sidebar itself, so its chunk waits behind
              the shell fallback — the nearest boundary wins, and the rail stays
              painted instead of the window going blank. */}
          <Route
            path="/report/:reportId"
            element={
              <Suspense fallback={<VShellFallback />}>
                <ReportPage />
              </Suspense>
            }
          />
          <Route path="/graph/:reportId" element={<GraphPage />} />
          <Route path="/trace/:reportId" element={<TracePage />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
