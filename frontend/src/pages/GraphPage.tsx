import { useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import * as d3 from 'd3'
import { ChevronLeft, Network } from 'lucide-react'
import { useReportStore } from '../store/reportStore'
import { truncate } from '../lib/format'

interface GNode extends d3.SimulationNodeDatum {
  id: string
  label: string
  type: 'report' | 'claim' | 'evidence'
  conf?: string
}
interface GLink extends d3.SimulationLinkDatum<GNode> {
  source: string | GNode
  target: string | GNode
}

// D3 needs raw colour values rather than classes. These read the same custom
// properties Tailwind resolves against, so the graph re-themes with everything
// else instead of drifting from the palette it was copied from.
const COLOR: Record<string, string> = {
  report: 'var(--v-primary-deep-color)',
  claim: 'var(--v-primary-color)',
  evidence: 'var(--v-warn-color)',
}
const RADIUS: Record<string, number> = { report: 22, claim: 13, evidence: 8 }

// English runs roughly half as dense as CJK, so labels get more characters.
const LABEL_MAX = { report: 48, claim: 42, evidence: 36 }

export default function GraphPage() {
  const { reportId } = useParams()
  const navigate = useNavigate()
  const { current, load } = useReportStore()
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (reportId) load(reportId)
  }, [reportId, load])

  useEffect(() => {
    if (!current || !svgRef.current) return
    const r = current

    const nodes: GNode[] = [
      { id: r.id, label: truncate(r.title, LABEL_MAX.report), type: 'report' },
      ...r.claims.map((c) => ({
        id: c.claim_id,
        label: truncate(c.text, LABEL_MAX.claim),
        type: 'claim' as const,
        conf: c.confidence,
      })),
      ...r.evidence.map((e) => ({
        id: e.evidence_id,
        label: truncate(e.title, LABEL_MAX.evidence),
        type: 'evidence' as const,
      })),
    ]
    const links: GLink[] = []
    for (const c of r.claims) {
      links.push({ source: r.id, target: c.claim_id })
      for (const eid of c.evidence_ids) {
        if (r.evidence.some((e) => e.evidence_id === eid))
          links.push({ source: c.claim_id, target: eid })
      }
    }

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    const width = svgRef.current.clientWidth
    const height = svgRef.current.clientHeight
    const g = svg.append('g')

    svg.call(
      d3
        .zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 3])
        .on('zoom', (e) => g.attr('transform', e.transform)) as never,
    )

    const sim = d3
      .forceSimulation<GNode>(nodes)
      .force(
        'link',
        d3
          .forceLink<GNode, GLink>(links)
          .id((d) => d.id)
          .distance((l) =>
            typeof l.target !== 'string' && (l.target as GNode).type === 'evidence'
              ? 80
              : 150,
          ),
      )
      .force('charge', d3.forceManyBody().strength(-320))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide<GNode>().radius((d) => RADIUS[d.type] + 10))

    const link = g
      .append('g')
      .attr('stroke', 'var(--v-line-color)')
      .attr('stroke-width', 1.4)
      .selectAll('line')
      .data(links)
      .join('line')

    const node = g
      .append('g')
      .selectAll<SVGGElement, GNode>('g')
      .data(nodes)
      .join('g')
      .style('cursor', 'pointer')
      .call(
        d3
          .drag<SVGGElement, GNode>()
          .on('start', (e, d) => {
            if (!e.active) sim.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (e, d) => {
            d.fx = e.x
            d.fy = e.y
          })
          .on('end', (e, d) => {
            if (!e.active) sim.alphaTarget(0)
            d.fx = null
            d.fy = null
          }) as never,
      )

    node
      .append('circle')
      .attr('r', (d) => RADIUS[d.type])
      .attr('fill', (d) => COLOR[d.type])
      .attr('stroke', 'var(--v-card-color)')
      .attr('stroke-width', 2)
      .attr('opacity', 0.92)

    node
      .append('text')
      .text((d) => d.label)
      .attr('x', (d) => RADIUS[d.type] + 5)
      .attr('y', 4)
      .attr('font-size', (d) => (d.type === 'report' ? 14 : 11))
      .attr('fill', 'var(--v-ink-color)')

    node.append('title').text((d) => d.label)

    sim.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as GNode).x ?? 0)
        .attr('y1', (d) => (d.source as GNode).y ?? 0)
        .attr('x2', (d) => (d.target as GNode).x ?? 0)
        .attr('y2', (d) => (d.target as GNode).y ?? 0)
      node.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })

    return () => {
      sim.stop()
    }
  }, [current])

  return (
    <div className="flex h-screen w-screen flex-col bg-bg">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-card/80 px-5 backdrop-blur">
        <button
          onClick={() => navigate(reportId ? `/report/${reportId}` : '/')}
          className="grid h-9 w-9 shrink-0 place-items-center rounded-btn text-ink-2 hover:bg-primary-tint"
          aria-label="Back to report"
        >
          <ChevronLeft size={20} />
        </button>
        <Network size={18} className="shrink-0 text-primary" />
        <span className="truncate text-aux font-semibold text-ink">
          Evidence graph — how each conclusion traces back to its sources
        </span>
        <div className="ml-auto hidden items-center gap-4 text-tag text-ink-2 sm:flex">
          <span className="inline-flex items-center gap-1.5">
            <i
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: COLOR.report }}
            />{' '}
            Report
          </span>
          <span className="inline-flex items-center gap-1.5">
            <i
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: COLOR.claim }}
            />{' '}
            Claim
          </span>
          <span className="inline-flex items-center gap-1.5">
            <i
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: COLOR.evidence }}
            />{' '}
            Evidence
          </span>
        </div>
      </header>
      <div className="relative min-h-0 flex-1">
        <svg ref={svgRef} className="h-full w-full" />
        <div className="pointer-events-none absolute bottom-4 left-4 text-tag text-ink-3">
          Scroll to zoom · drag to pan · drag a node to reposition it
        </div>
      </div>
    </div>
  )
}
