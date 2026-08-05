import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  ShieldCheck,
  Database,
  FileText,
  Sparkles,
  Search,
  Bell,
  BellPlus,
  Trash2,
  Users,
  ExternalLink,
  Layers,
  Activity,
  Radar,
  Crosshair,
  PieChart,
  TrendingUp,
  Target,
  Clock,
  Zap,
  Network,
  Gauge,
} from 'lucide-react'
import {
  fetchDashboard,
  fetchEvidences,
  fetchSubscriptions,
  createSubscription,
  deleteSubscription,
  fetchWorkload,
} from '../lib/api'
import type {
  DashboardStats,
  EvidenceQueryResp,
  EvidenceRecord,
  Subscription,
  ExpertWorkload,
} from '../types'
import { VCard, VCountUp, VEmpty, VFilterChip } from '../components/ui'
import { VAvatar } from '../components/VAvatar'
import { fadeUp, stagger } from '../lib/motion'
import { CATEGORY_LABEL, SOURCE_CATEGORY, sourceLabel } from '../lib/labels'
import { num, plural } from '../lib/format'
import { ACCENT_FILL, ACCENT_TEXT } from '../lib/accents'

function fmtSaved(min: number): { value: number; unit: string } {
  if (min >= 60) return { value: Math.round((min / 60) * 10) / 10, unit: 'hours' }
  return { value: Math.round(min), unit: 'minutes' }
}

const CATEGORY_COLOR: Record<string, string> = {
  primary: ACCENT_FILL.blue,
  media: ACCENT_FILL.violet,
  social: ACCENT_FILL.pink,
}
const CATEGORY_ORDER = ['primary', 'media', 'social'] as const

interface BrandIntel {
  brand: string
  count: number
  sourceTypes: number
  avgCred: number
  lastAt: string
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [ev, setEv] = useState<EvidenceQueryResp>({
    items: [],
    facets: { total: 0, by_type: {}, by_brand: {} },
  })
  const [subs, setSubs] = useState<Subscription[]>([])
  const [workload, setWorkload] = useState<ExpertWorkload[]>([])
  const [loading, setLoading] = useState(true)

  const [brandFilter, setBrandFilter] = useState<string>('')
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [subQuery, setSubQuery] = useState('')

  useEffect(() => {
    let cancelled = false
    void (async () => {
      const [d, e, s, w] = await Promise.all([
        fetchDashboard(),
        fetchEvidences(),
        fetchSubscriptions(),
        fetchWorkload(),
      ])
      if (cancelled) return
      setStats(d)
      setEv(e)
      setSubs(s)
      setWorkload(w)
      setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const items = useMemo(() => (Array.isArray(ev.items) ? ev.items : []), [ev])

  /** How much intelligence we hold on each competitor, across all reports. */
  const brandIntel = useMemo<BrandIntel[]>(() => {
    const map = new Map<
      string,
      { count: number; types: Set<string>; cred: number; last: string }
    >()
    for (const it of items) {
      const b = (it.brand || '').trim()
      if (!b) continue
      const cur =
        map.get(b) ?? { count: 0, types: new Set<string>(), cred: 0, last: '' }
      cur.count += 1
      cur.types.add(it.source_type)
      cur.cred += it.credibility || 0
      if ((it.captured_at || '') > cur.last) cur.last = it.captured_at || ''
      map.set(b, cur)
    }
    return Array.from(map.entries())
      .map(([brand, v]) => ({
        brand,
        count: v.count,
        sourceTypes: v.types.size,
        avgCred: v.count ? v.cred / v.count : 0,
        lastAt: v.last,
      }))
      .sort((a, b) => b.count - a.count)
  }, [items])

  const maxBrandCount = useMemo(
    () => brandIntel.reduce((m, b) => Math.max(m, b.count), 1),
    [brandIntel],
  )

  /** Is the source mix balanced? Skew toward one type weakens conclusions. */
  const sourceStructure = useMemo(() => {
    const cat: Record<string, number> = { primary: 0, media: 0, social: 0 }
    for (const it of items) {
      cat[SOURCE_CATEGORY[it.source_type] ?? 'media'] += 1
    }
    const total = items.length || 1
    const pct = (n: number) => Math.round((n / total) * 100)
    const segs = CATEGORY_ORDER.map((k) => ({
      key: k,
      label: CATEGORY_LABEL[k],
      n: cat[k],
      pct: pct(cat[k]),
    }))
    const top = [...segs].sort((a, b) => b.n - a.n)[0]
    const firstHand = pct(cat.primary)
    let insight: string
    if (firstHand >= 40) {
      insight = `Primary sources make up ${firstHand}% of the evidence base — conclusions rest on filings and official documentation rather than commentary.`
    } else if (firstHand >= 20) {
      insight = `The mix leans toward ${top.label.toLowerCase()} (${top.pct}%), with primary sources at ${firstHand}%. Add official documentation or filings to firm up the load-bearing claims.`
    } else {
      insight = `Only ${firstHand}% of evidence is primary — the base is mostly ${top.label.toLowerCase()} (${top.pct}%). Key conclusions need corroboration from official or filed sources.`
    }
    return { segs, insight }
  }, [items])

  const filteredEv = useMemo<EvidenceRecord[]>(
    () =>
      items.filter(
        (it) =>
          (!brandFilter || it.brand === brandFilter) &&
          (!typeFilter || it.source_type === typeFilter),
      ),
    [items, brandFilter, typeFilter],
  )

  const facetBrands = useMemo(
    () => Object.entries(ev.facets.by_brand).slice(0, 6),
    [ev],
  )
  const facetTypes = useMemo(() => Object.entries(ev.facets.by_type).slice(0, 6), [ev])

  const activeWorkload = useMemo(
    () =>
      (Array.isArray(workload) ? workload : []).filter((w) => w.missions > 0).slice(0, 6),
    [workload],
  )

  const handleCreateSub = async () => {
    const q = subQuery.trim()
    if (!q) return
    await createSubscription(q, [])
    setSubQuery('')
    setSubs(await fetchSubscriptions())
  }
  const handleDeleteSub = async (id: string) => {
    await deleteSubscription(id)
    setSubs(await fetchSubscriptions())
  }

  const empty = !loading && (!stats || stats.reports === 0)
  const coveredBrands = brandIntel.length
  const researchCards = stats?.research_cards ?? []

  return (
    <div className="mx-auto max-w-content px-8 py-8">
      <header>
        <h1 className="font-serif text-h1 text-ink">Intelligence center</h1>
        <p className="mt-1 text-aux text-ink-2">
          Every research run compounds into reusable competitive memory — coverage per
          competitor, the quality of your source mix, and everything traced back to
          where it came from.
        </p>
      </header>

      {loading ? (
        <div className="mt-16 text-center text-aux text-ink-3">Loading…</div>
      ) : empty ? (
        <VEmpty
          icon={<Radar size={36} strokeWidth={1.4} />}
          title="No intelligence yet"
          hint="Once you complete a research run, this page fills with competitor coverage, the evidence library and your source mix."
          action={
            <button
              onClick={() => navigate('/')}
              className="inline-flex h-11 items-center gap-2 rounded-btn bg-primary-deep px-6 font-medium text-white shadow-card hover:bg-primary-deeper"
            >
              Start research
            </button>
          }
        />
      ) : (
        <>
          <motion.div
            variants={stagger}
            initial="initial"
            animate="animate"
            className="mt-6 grid grid-cols-2 gap-5 sm:grid-cols-4"
          >
            <StatCard
              icon={Target}
              value={coveredBrands}
              label="Competitors covered"
              tip="Distinct competitors with evidence on file."
            />
            <StatCard
              icon={Database}
              value={stats!.evidence_total}
              label="Sources collected"
              tip={`Averaging ${stats!.avg_evidence_per_report} per report.`}
            />
            <StatCard
              icon={Sparkles}
              value={stats!.claim_total}
              label="Claims produced"
              tip="Total analytical conclusions across all reports."
            />
            <StatCard
              icon={ShieldCheck}
              value={stats!.fact_accuracy}
              unit="%"
              color="text-ok-deep"
              label="Cross-validated"
              tip="Share of claims corroborated by two or more independent domains."
            />
          </motion.div>

          <motion.div
            variants={fadeUp}
            initial="initial"
            animate="animate"
            className="mt-6"
          >
            <VCard hover={false}>
              <div className="flex flex-wrap items-center gap-2 text-aux font-semibold text-ink">
                <Gauge size={16} className={ACCENT_TEXT.blue} /> Measured impact
                <span className="ml-1 font-normal text-tag text-ink-3">
                  versus a manual analysis baseline · hover any figure for its formula
                </span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-5 sm:grid-cols-4">
                <ImpactCard
                  icon={Clock}
                  color={ACCENT_TEXT.blue}
                  value={fmtSaved(stats!.minutes_saved ?? 0).value}
                  unit={fmtSaved(stats!.minutes_saved ?? 0).unit}
                  label="Analyst time saved"
                  tip="Sum of (manual estimate − actual elapsed), at roughly 8 analyst-minutes per source."
                />
                <ImpactCard
                  icon={Zap}
                  color={ACCENT_TEXT.violet}
                  value={stats!.avg_efficiency ?? 0}
                  unit="×"
                  label="Average speed-up"
                  tip="Mean of each report's manual estimate divided by its actual elapsed time."
                />
                <ImpactCard
                  icon={Layers}
                  color={ACCENT_TEXT.orchid}
                  value={stats!.avg_coverage ?? 0}
                  unit="×"
                  label="Source coverage"
                  tip="Mean of each report's independent domains divided by the manual baseline of 6."
                />
                <ImpactCard
                  icon={Activity}
                  color={ACCENT_TEXT.pink}
                  value={Math.round((stats!.total_tokens ?? 0) / 1000)}
                  unit="K"
                  label="Tokens used"
                  tip="Total model tokens consumed across all research."
                />
              </div>
            </VCard>
          </motion.div>

          {researchCards.length > 0 && (
            <motion.div
              variants={fadeUp}
              initial="initial"
              animate="animate"
              className="mt-6"
            >
              <VCard hover={false}>
                <div className="flex flex-wrap items-center gap-2 text-aux font-semibold text-ink">
                  <FileText size={16} className={ACCENT_TEXT.indigo} /> Research runs
                  <span className="ml-1 font-normal text-tag text-ink-3">
                    open the report, or the decision trace behind it
                  </span>
                </div>
                <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {researchCards.slice(0, 9).map((rc) => (
                    <div
                      key={rc.id}
                      className="rounded-card border border-line/60 bg-bg p-4 transition-all hover:border-primary-soft hover:bg-card"
                    >
                      <button
                        onClick={() => navigate(`/report/${rc.id}`)}
                        className="line-clamp-2 text-left text-aux font-medium text-ink hover:text-primary-deep"
                      >
                        {rc.title}
                      </button>
                      {rc.brands.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {rc.brands.slice(0, 4).map((b) => (
                            <span
                              key={b}
                              className="rounded-chip bg-primary-tint px-2 py-0.5 text-tag text-primary-deep"
                            >
                              {b}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                        <Mini label="Sources" value={num(rc.evidence_count)} />
                        <Mini label="Claims" value={num(rc.claim_count)} />
                        <Mini label="High conf." value={num(rc.high_conf_count)} />
                        <Mini
                          label="Speed-up"
                          value={rc.efficiency_multiple ? `${rc.efficiency_multiple}×` : '—'}
                          accent
                        />
                        <Mini
                          label="Saved"
                          value={rc.minutes_saved ? `${Math.round(rc.minutes_saved)}m` : '—'}
                          accent
                        />
                        <Mini
                          label="Elapsed"
                          value={rc.elapsed_minutes ? `${rc.elapsed_minutes}m` : '—'}
                        />
                      </div>
                      <div className="mt-3 flex items-center gap-2">
                        <button
                          onClick={() => navigate(`/report/${rc.id}`)}
                          className="inline-flex h-7 items-center gap-1 rounded-btn bg-primary-tint px-2.5 text-tag font-medium text-primary-deep hover:bg-primary-soft/50"
                        >
                          <FileText size={12} /> Report
                        </button>
                        <button
                          onClick={() => navigate(`/trace/${rc.id}`)}
                          className="inline-flex h-7 items-center gap-1 rounded-btn bg-bg px-2.5 text-tag font-medium text-ink-2 ring-1 ring-line hover:text-primary-deep"
                        >
                          <Network size={12} /> Trace
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </VCard>
            </motion.div>
          )}

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
            <motion.div
              variants={fadeUp}
              initial="initial"
              animate="animate"
              className="lg:col-span-2"
            >
              <VCard hover={false}>
                <div className="flex flex-wrap items-center gap-2 text-aux font-semibold text-ink">
                  <Radar size={16} className={ACCENT_TEXT.violet} /> Coverage by competitor
                  <span className="ml-1 font-normal text-tag text-ink-3">
                    click to filter the evidence library
                  </span>
                </div>
                <p className="mt-1 text-tag text-ink-3">
                  Depth (how many sources) × breadth (how many source types) ×
                  quality (average credibility) — this is where you spot the
                  competitor you know least about.
                </p>

                {brandIntel.length === 0 ? (
                  <div className="py-10 text-center text-tag text-ink-3">
                    No brand-tagged evidence yet.
                  </div>
                ) : (
                  <div className="mt-4 space-y-3">
                    {brandIntel.slice(0, 8).map((b) => {
                      const active = brandFilter === b.brand
                      return (
                        <button
                          key={b.brand}
                          onClick={() => setBrandFilter(active ? '' : b.brand)}
                          className={`block w-full rounded-card border p-3 text-left transition-all ${
                            active
                              ? 'border-primary-soft bg-primary-tint/50'
                              : 'border-line/60 bg-bg hover:border-primary-soft hover:bg-card'
                          }`}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <span className="flex items-center gap-1.5 text-aux font-medium text-ink">
                              <Crosshair size={13} className="text-primary" /> {b.brand}
                            </span>
                            <span className="text-tag text-ink-3">
                              {plural(b.count, 'source')} · {b.sourceTypes} type(s) ·
                              avg credibility {Math.round(b.avgCred)}
                            </span>
                          </div>
                          <div className="mt-2 h-2 w-full overflow-hidden rounded-chip bg-line">
                            <div
                              className="h-full rounded-chip bg-primary transition-all"
                              style={{
                                width: `${Math.max(6, (b.count / maxBrandCount) * 100)}%`,
                              }}
                            />
                          </div>
                        </button>
                      )
                    })}
                  </div>
                )}
              </VCard>
            </motion.div>

            <motion.div variants={fadeUp} initial="initial" animate="animate">
              <VCard hover={false}>
                <div className="flex items-center gap-2 text-aux font-semibold text-ink">
                  <PieChart size={16} className={ACCENT_TEXT.orchid} /> Source mix
                </div>
                <p className="mt-1 text-tag text-ink-3">
                  Whether the evidence base is balanced determines how much weight the
                  conclusions can carry.
                </p>

                <div className="mt-4 flex h-3 w-full overflow-hidden rounded-chip bg-line">
                  {sourceStructure.segs.map(
                    (s) =>
                      s.pct > 0 && (
                        <div
                          key={s.key}
                          className={CATEGORY_COLOR[s.key]}
                          style={{ width: `${s.pct}%` }}
                        />
                      ),
                  )}
                </div>
                <div className="mt-3 space-y-2">
                  {sourceStructure.segs.map((s) => (
                    <div key={s.key} className="flex items-center gap-2 text-tag">
                      <span className={`h-2.5 w-2.5 rounded-sm ${CATEGORY_COLOR[s.key]}`} />
                      <span className="text-ink-2">{s.label}</span>
                      <span className="ml-auto text-ink-3">
                        {num(s.n)} · {s.pct}%
                      </span>
                    </div>
                  ))}
                </div>
                <div className="mt-4 rounded-card border-l-2 border-primary bg-primary-tint/40 p-3">
                  <div className="flex items-center gap-1.5 text-tag font-semibold text-primary-deep">
                    <TrendingUp size={13} /> Read
                  </div>
                  <p className="mt-1 text-tag leading-relaxed text-ink-2">
                    {sourceStructure.insight}
                  </p>
                </div>
              </VCard>
            </motion.div>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
            <motion.div
              variants={fadeUp}
              initial="initial"
              animate="animate"
              className="lg:col-span-2"
            >
              <VCard hover={false}>
                <div className="flex flex-wrap items-center gap-2 text-aux font-semibold text-ink">
                  <Search size={16} className={ACCENT_TEXT.pink} /> Evidence library
                  <span className="ml-1 font-normal text-tag text-ink-3">
                    {num(ev.facets.total)} total · {num(filteredEv.length)} shown
                  </span>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  <VFilterChip
                    active={!brandFilter && !typeFilter}
                    onClick={() => {
                      setBrandFilter('')
                      setTypeFilter('')
                    }}
                  >
                    All
                  </VFilterChip>
                  {facetBrands.map(([b, n]) => (
                    <VFilterChip
                      key={b}
                      active={brandFilter === b}
                      onClick={() => setBrandFilter(brandFilter === b ? '' : b)}
                      count={n}
                    >
                      {b}
                    </VFilterChip>
                  ))}
                  {facetTypes.map(([t, n]) => (
                    <VFilterChip
                      key={t}
                      active={typeFilter === t}
                      onClick={() => setTypeFilter(typeFilter === t ? '' : t)}
                      count={n}
                    >
                      {sourceLabel(t)}
                    </VFilterChip>
                  ))}
                </div>

                <div className="mt-4 max-h-[420px] space-y-2 overflow-y-auto pr-1">
                  {filteredEv.length === 0 ? (
                    <div className="py-8 text-center text-tag text-ink-3">
                      Nothing matches those filters.
                    </div>
                  ) : (
                    filteredEv.map((it) => (
                      <a
                        key={it.evidence_id}
                        href={it.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="group block rounded-card border border-line/60 bg-bg p-3 transition-all hover:border-primary-soft hover:bg-card"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="line-clamp-2 text-aux font-medium text-ink">
                              {it.title || it.domain}
                            </div>
                            <p className="mt-0.5 line-clamp-2 text-tag text-ink-3">
                              {it.excerpt}
                            </p>
                          </div>
                          <ExternalLink
                            size={14}
                            className="mt-1 shrink-0 text-ink-3 group-hover:text-primary"
                          />
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-tag text-ink-3">
                          <span className="rounded-chip bg-primary-tint px-2 py-0.5 text-primary-deep">
                            {sourceLabel(it.source_type)}
                          </span>
                          {it.brand && (
                            <span className="rounded-chip bg-sun-soft/50 px-2 py-0.5">
                              {it.brand}
                            </span>
                          )}
                          <span className="truncate">{it.domain}</span>
                          <span className="ml-auto">
                            Credibility {Math.round(it.credibility)}
                          </span>
                        </div>
                      </a>
                    ))
                  )}
                </div>
              </VCard>
            </motion.div>

            <motion.div variants={fadeUp} initial="initial" animate="animate">
              <VCard hover={false}>
                <div className="flex items-center gap-2 text-aux font-semibold text-ink">
                  <Bell size={16} className={ACCENT_TEXT.rose} /> Watchlist
                </div>
                <p className="mt-1 text-tag text-ink-3">
                  Save a competitive question and re-run it later for what changed.
                </p>

                <div className="mt-3 flex gap-2">
                  <input
                    value={subQuery}
                    onChange={(e) => setSubQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleCreateSub()}
                    placeholder="e.g. Figma vs Framer positioning"
                    className="h-10 min-w-0 flex-1 rounded-btn border border-line bg-bg px-3 text-aux text-ink outline-none transition-all focus:border-primary focus:shadow-glow-soft"
                  />
                  <button
                    onClick={handleCreateSub}
                    className="grid h-10 w-10 shrink-0 place-items-center rounded-btn bg-primary-deep text-white hover:bg-primary-deeper"
                    aria-label="Add to watchlist"
                  >
                    <BellPlus size={16} />
                  </button>
                </div>

                <div className="mt-4 space-y-2">
                  {subs.length === 0 ? (
                    <div className="py-6 text-center text-tag text-ink-3">
                      Nothing on the watchlist.
                    </div>
                  ) : (
                    subs.map((s) => (
                      <div
                        key={s.sub_id}
                        className="rounded-card border border-line/60 bg-bg p-3"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="line-clamp-2 text-aux font-medium text-ink">
                            {s.query}
                          </div>
                          <button
                            onClick={() => handleDeleteSub(s.sub_id)}
                            className="shrink-0 text-ink-3 hover:text-warn-deep"
                            aria-label="Remove"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                        <div className="mt-2 flex items-center gap-2 text-tag text-ink-3">
                          <span>Run {plural(s.run_count, 'time')}</span>
                          {s.last_report_id && (
                            <button
                              onClick={() => navigate(`/report/${s.last_report_id}`)}
                              className="text-primary-deep hover:underline"
                            >
                              Latest report
                            </button>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </VCard>
            </motion.div>
          </div>

          {activeWorkload.length > 0 && (
            <motion.div
              variants={fadeUp}
              initial="initial"
              animate="animate"
              className="mt-6"
            >
              <VCard hover={false}>
                <div className="flex flex-wrap items-center gap-2 text-aux font-semibold text-ink">
                  <Users size={16} className={ACCENT_TEXT.indigo} /> Analyst contributions
                  <span className="ml-1 font-normal text-tag text-ink-3">
                    by engagements worked
                  </span>
                </div>
                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {activeWorkload.map((w) => (
                    <button
                      key={w.id}
                      onClick={() => navigate(`/experts/${w.id}`)}
                      className="flex items-center gap-3 rounded-card border border-line/60 bg-bg p-3 text-left transition-all hover:border-primary-soft hover:bg-card"
                    >
                      <VAvatar name={w.name} id={w.id} size={40} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate text-aux font-medium text-ink">
                            {w.name}
                          </span>
                          <span className="rounded-chip bg-primary-tint px-1.5 text-tag text-primary-deep">
                            {w.layer}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 text-tag text-ink-3">
                          <span className="inline-flex items-center gap-1">
                            <Layers size={11} /> {num(w.missions)}
                          </span>
                          <span className="inline-flex items-center gap-1">
                            <Activity size={11} /> {num(w.claims_authored)} claims
                          </span>
                          <span className="inline-flex items-center gap-1">
                            <Database size={11} /> {num(w.evidence_collected)} sources
                          </span>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </VCard>
            </motion.div>
          )}
        </>
      )}
    </div>
  )
}

function StatCard({
  icon: Icon,
  value,
  label,
  tip,
  unit,
  color = 'text-primary',
}: {
  icon: typeof FileText
  value: number
  label: string
  tip: string
  unit?: string
  color?: string
}) {
  return (
    <motion.div variants={fadeUp}>
      <VCard hover={false}>
        <span
          className={`grid h-9 w-9 place-items-center rounded-btn bg-primary-tint ${color}`}
        >
          <Icon size={18} />
        </span>
        <div className="mt-3 flex items-end gap-0.5">
          <span className="font-serif text-[32px] leading-none text-ink">
            <VCountUp value={value} />
          </span>
          {unit && <span className="mb-1 text-h3 text-ink-2">{unit}</span>}
        </div>
        <div className="mt-1 text-aux font-medium text-ink">{label}</div>
        <p className="mt-1 text-tag leading-relaxed text-ink-3">{tip}</p>
      </VCard>
    </motion.div>
  )
}

function ImpactCard({
  icon: Icon,
  value,
  label,
  tip,
  unit,
  color = 'text-primary',
}: {
  icon: typeof FileText
  value: number
  label: string
  tip: string
  unit?: string
  color?: string
}) {
  return (
    <div className="rounded-card border border-line/60 bg-bg p-4" title={tip}>
      <span
        className={`grid h-8 w-8 place-items-center rounded-btn bg-primary-tint ${color}`}
      >
        <Icon size={16} />
      </span>
      <div className="mt-2.5 flex items-end gap-0.5">
        <span className="font-serif text-[26px] leading-none text-ink">
          <VCountUp value={value} />
        </span>
        {unit && <span className="mb-0.5 text-aux text-ink-2">{unit}</span>}
      </div>
      <div className="mt-1 text-tag font-medium text-ink-2">{label}</div>
    </div>
  )
}

function Mini({
  label,
  value,
  accent = false,
}: {
  label: string
  value: string
  accent?: boolean
}) {
  return (
    <div className="rounded-btn bg-card/60 py-1.5">
      <div className={`text-aux font-semibold ${accent ? 'text-primary-deep' : 'text-ink'}`}>
        {value}
      </div>
      <div className="text-tag text-ink-3">{label}</div>
    </div>
  )
}
