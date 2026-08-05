import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Search } from 'lucide-react'
import { useExpertStore } from '../store/expertStore'
import { DomainIcon } from '../components/DomainIcon'
import { VAvatar } from '../components/VAvatar'
import { VEmpty } from '../components/ui'
import { ACCENT_CHIP, LEVEL_ACCENT } from '../lib/accents'
import { fadeUp, stagger } from '../lib/motion'
import type { Expert, ExpertLevel } from '../types'

// Headcounts are rendered from the loaded roster rather than written in — the
// team grows, and a hardcoded number here silently starts lying when it does.
const LEVEL_TABS: {
  key: ExpertLevel | 'all'
  label: string
  desc: (n: number) => string
}[] = [
  { key: 'all', label: 'Everyone', desc: (n) => `${n} analysts` },
  { key: 'L3', label: 'Decision', desc: (n) => `${n} · direction and sign-off` },
  { key: 'L2', label: 'Strategy', desc: (n) => `${n} · method advisors` },
  { key: 'L1', label: 'Specialist', desc: (n) => `${n} · industry and function` },
]

// One accent per tier. Three tints of the same colour made the roster look
// uniform; three hues make the decision, strategy and specialist tiers legible
// at a glance across the grid.
const LEVEL_BG: Record<ExpertLevel, string> = {
  L1: ACCENT_CHIP[LEVEL_ACCENT.L1],
  L2: ACCENT_CHIP[LEVEL_ACCENT.L2],
  L3: ACCENT_CHIP[LEVEL_ACCENT.L3],
}

function ExpertCard({ expert, onClick }: { expert: Expert; onClick: () => void }) {
  return (
    <motion.button
      variants={fadeUp}
      onClick={onClick}
      className="group relative flex flex-col items-center rounded-card border border-line/60 bg-card p-4 text-center shadow-card transition-all hover:-translate-y-0.5 hover:shadow-float"
    >
      <span
        className={`absolute right-2.5 top-2.5 inline-flex h-5 items-center gap-1 rounded-chip px-2 text-tag font-medium ${
          LEVEL_BG[expert.level]
        }`}
      >
        {expert.level}
      </span>
      <div className="relative">
        <VAvatar expert={expert} size={64} className="shadow-card ring-2 ring-card" />
        <span className="absolute -bottom-1 -right-1 grid h-6 w-6 place-items-center rounded-full bg-card text-primary shadow-card">
          <DomainIcon name={expert.domain_icon} size={13} />
        </span>
      </div>
      <div className="mt-3 text-aux font-semibold text-ink">{expert.name}</div>
      <div className="line-clamp-1 text-tag text-primary-deep">{expert.role_title}</div>
      <p className="mt-1.5 line-clamp-3 text-tag leading-relaxed text-ink-3">
        {expert.one_liner}
      </p>
    </motion.button>
  )
}

export default function ExpertsPage() {
  const navigate = useNavigate()
  const experts = useExpertStore((s) => s.experts)
  const [tab, setTab] = useState<ExpertLevel | 'all'>('all')
  const [kw, setKw] = useState('')

  const counts = useMemo(() => {
    const by: Record<string, number> = { all: experts.length }
    for (const e of experts) by[e.level] = (by[e.level] ?? 0) + 1
    return by
  }, [experts])

  const filtered = useMemo(() => {
    const q = kw.trim().toLowerCase()
    return experts.filter((e) => {
      const okLevel = tab === 'all' || e.level === tab
      if (!q) return okLevel
      // Case-insensitive across name, role, tags and skills.
      const haystack = [
        e.name,
        e.nickname,
        e.role_title,
        e.one_liner,
        ...e.knowledge_tags,
        ...e.skills,
      ]
        .join(' ')
        .toLowerCase()
      return okLevel && haystack.includes(q)
    })
  }, [experts, tab, kw])

  return (
    <div className="mx-auto max-w-content px-8 py-8">
      <header className="flex flex-col gap-1">
        <h1 className="font-serif text-h1 text-ink">Analyst team</h1>
        <p className="text-aux text-ink-2">
          {experts.length > 0 ? `${experts.length} specialists` : 'Specialists'} across
          three tiers — decision, strategy and execution. The director assembles the
          right team for each brief.
        </p>
      </header>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <div className="flex h-10 items-center gap-2 rounded-btn border border-line bg-card px-3 shadow-card transition-all focus-within:border-primary focus-within:shadow-glow">
          <Search size={16} className="text-ink-3" />
          <input
            value={kw}
            onChange={(e) => setKw(e.target.value)}
            placeholder="Search by name, skill or expertise"
            className="w-64 bg-transparent text-aux text-ink outline-none placeholder:text-ink-3"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {LEVEL_TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex flex-col items-start rounded-btn px-3.5 py-1.5 text-left transition-all ${
                tab === t.key
                  ? 'bg-primary-deep text-white shadow-card'
                  : 'bg-card text-ink-2 hover:bg-primary-tint'
              }`}
            >
              <span className="text-aux font-medium leading-tight">{t.label}</span>
              <span
                className={`text-tag ${tab === t.key ? 'text-white/80' : 'text-ink-3'}`}
              >
                {t.desc(counts[t.key] ?? 0)}
              </span>
            </button>
          ))}
        </div>
      </div>

      <motion.div
        key={tab + kw}
        variants={stagger}
        initial="initial"
        animate="animate"
        className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
      >
        {filtered.map((e) => (
          <ExpertCard
            key={e.id}
            expert={e}
            onClick={() => navigate(`/experts/${e.id}`)}
          />
        ))}
      </motion.div>

      {filtered.length === 0 && (
        <VEmpty
          icon={<Search size={28} strokeWidth={1.5} />}
          title="No analysts match that search"
          hint="Try a broader term, or clear the filter to see the full roster."
        />
      )}
    </div>
  )
}
