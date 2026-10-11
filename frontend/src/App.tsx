import { BrowserRouter, Navigate, Route, Routes, useParams, useSearchParams } from 'react-router-dom'
import AppLayout from './layout/AppLayout'
import HomePage from './pages/HomePage'
import ClarifyPage from './pages/ClarifyPage'
import WorkspacePage from './pages/WorkspacePage'
import ReportPage from './pages/ReportPage'
import LibraryPage from './pages/LibraryPage'
import { clearLegacyStorage } from './lib/drafts'
clearLegacyStorage()
function ReportRoute() {
  const { reportId } = useParams(), [params] = useSearchParams()
  return <ReportPage key={reportId + ':' + params.toString()} />
}
function WorkspaceRoute() {
  const { taskId } = useParams()
  return <WorkspacePage key={taskId} />
}
export default function App() {
  return <BrowserRouter><Routes><Route element={<AppLayout />}>
    <Route path="/" element={<HomePage />} />
    <Route path="/clarify/:taskId" element={<ClarifyPage />} />
    <Route path="/workspace/:taskId" element={<WorkspaceRoute />} />
    <Route path="/report/:reportId" element={<ReportRoute />} />
    <Route path="/library" element={<LibraryPage />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Route></Routes></BrowserRouter>
}
