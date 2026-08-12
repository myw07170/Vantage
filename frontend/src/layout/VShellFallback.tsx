import VSidebar from './VSidebar'
import { VSkeleton } from '../components/ui'

/** Loading shell for the full-screen pages that carry the sidebar themselves —
 *  today that is the report view.
 *
 *  Opening a report crosses two waits: the lazy route chunk, then the report
 *  fetch. Both used to render a bare skeleton, so the rail vanished and came
 *  back and the whole window flashed. Rendering the real `VSidebar` here holds
 *  the frame still across both: it lives in the entry chunk, and the recents
 *  list it shows comes from the store, which survives the remount.
 *
 *  The skeleton mirrors the report's own rhythm — cover band, metrics strip,
 *  then the article column — so the layout does not jump when the page lands. */
export default function VShellFallback() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg">
      <VSidebar />
      <main className="min-w-0 flex-1 overflow-y-auto">
        <VSkeleton className="h-[220px] w-full rounded-none" />
        <div className="border-b border-line bg-card/60">
          <div className="mx-auto grid max-w-article grid-cols-2 gap-px px-6 sm:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="flex flex-col items-center gap-2 py-5">
                <VSkeleton className="h-6 w-12" />
                <VSkeleton className="h-3 w-16" />
              </div>
            ))}
          </div>
        </div>
        <div className="mx-auto max-w-article px-6 py-10">
          <VSkeleton className="h-7 w-2/3" />
          <div className="mt-5 space-y-3">
            {['w-full', 'w-full', 'w-11/12', 'w-4/5'].map((w) => (
              <VSkeleton key={w} className={`h-4 ${w}`} />
            ))}
          </div>
          <VSkeleton className="mt-10 h-7 w-1/2" />
          <div className="mt-5 space-y-3">
            {['w-full', 'w-10/12', 'w-full'].map((w) => (
              <VSkeleton key={w} className={`h-4 ${w}`} />
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
