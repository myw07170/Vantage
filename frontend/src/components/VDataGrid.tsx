import { useState } from 'react'
import { Table2, Download, ChevronDown, ExternalLink } from 'lucide-react'
import type { DataGrid } from '../types'
import { plural } from '../lib/format'

/** Expandable data table with CSV export. */
export function VDataGrid({
  grid,
  title = 'Data',
}: {
  grid: DataGrid
  title?: string
}) {
  const [open, setOpen] = useState(false)
  if (!grid?.rows?.length) return null
  const preview = open ? grid.rows : grid.rows.slice(0, 3)

  const exportCsv = () => {
    const head = grid.columns.join(',')
    const lines = grid.rows.map((r) =>
      [r.name, r.value, r.metric, r.source, r.source_url]
        .map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`)
        .join(','),
    )
    const csv = [head, ...lines].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${title.replace(/\s+/g, '-').toLowerCase()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="mt-4 overflow-hidden rounded-card border border-line bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 bg-paper px-4 py-2">
        <div className="flex items-center gap-1.5 text-aux font-semibold text-ink">
          <Table2 size={14} className="text-primary" /> {title} ·{' '}
          {plural(grid.rows.length, 'row')}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={exportCsv}
            className="flex items-center gap-1 rounded-chip bg-primary-tint px-2 py-1 text-tag text-primary-deep hover:bg-primary-soft/40"
          >
            <Download size={12} /> Export CSV
          </button>
          <button
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-1 rounded-chip px-2 py-1 text-tag text-ink-3"
          >
            {open ? 'Collapse' : 'Expand all'}{' '}
            <ChevronDown
              size={12}
              className={open ? 'rotate-180 transition' : 'transition'}
            />
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-tag">
          <thead>
            <tr className="border-b border-line text-ink-3">
              {grid.columns.map((c) => (
                <th key={c} className="px-3 py-1.5 text-left font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.map((r, i) => (
              <tr key={i} className="border-b border-line/60 last:border-0">
                <td className="px-3 py-1.5 font-medium text-ink">{r.name}</td>
                <td className="px-3 py-1.5 text-primary-deep">{r.value}</td>
                <td className="px-3 py-1.5 text-ink-2">{r.metric}</td>
                <td className="px-3 py-1.5 text-ink-2">{r.source}</td>
                <td className="px-3 py-1.5">
                  {r.source_url ? (
                    <a
                      href={r.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-0.5 text-primary hover:underline"
                    >
                      Link <ExternalLink size={10} />
                    </a>
                  ) : (
                    <span className="text-ink-3">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!open && grid.rows.length > 3 && (
        <button
          onClick={() => setOpen(true)}
          className="w-full bg-paper/60 py-1.5 text-tag text-ink-3 hover:text-primary-deep"
        >
          Show all {grid.rows.length} rows →
        </button>
      )}
    </div>
  )
}
