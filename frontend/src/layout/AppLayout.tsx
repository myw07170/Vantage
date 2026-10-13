import { Suspense } from 'react'
import { Outlet } from 'react-router-dom'
import VSidebar from './VSidebar'
import { VToast } from './VToast'
import { VSkeleton } from '../components/ui'

/** Placeholder while a route chunk arrives. Mirrors the page rhythm — header
 *  band then content — so the layout does not jump when the real page lands. */
export function RouteFallback() {
  return (
    <div className="mx-auto max-w-content px-8 py-8">
      <VSkeleton className="h-8 w-56" />
      <VSkeleton className="mt-3 h-4 w-96" />
      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <VSkeleton key={i} className="h-36 w-full rounded-card" />
        ))}
      </div>
    </div>
  )
}

export default function AppLayout() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg">
      <VSidebar />
      {/* The boundary sits inside the shell, not around it: a lazy page's chunk
          should replace the content column only, leaving the rail and the toast
          host mounted. Hoisting it back up to <Routes> blanks the whole window
          on every first visit to a route. */}
      <main className="relative min-w-0 flex-1 overflow-y-auto">
        <Suspense fallback={<RouteFallback />}>
          <Outlet />
        </Suspense>
      </main>
      <VToast />
    </div>
  )
}
