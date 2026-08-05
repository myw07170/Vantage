import { useNavigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ChevronLeft, BookText, Sparkles, Target, Award } from 'lucide-react'
import { useExpertStore } from '../store/expertStore'
import { DomainIcon } from '../components/DomainIcon'
import { VAvatar } from '../components/VAvatar'
import { VCard } from '../components/ui'
import { num } from '../lib/format'
import { ACCENT_CHIP, LEVEL_ACCENT } from '../lib/accents'

const LEVEL_LABEL: Record<string, string> = {
  L1: 'Specialist tier · industry and function',
  L2: 'Strategy tier · method advisors',
  L3: 'Decision tier · direction and sign-off',
}

export default function ExpertDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const byId = useExpertStore((s) => s.byId)
  const experts = useExpertStore((s) => s.experts)
  const expert = id ? byId(id) : undefined

  if (!expert) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-ink-2">
        <p>Analyst not found.</p>
        <button
          onClick={() => navigate('/experts')}
          className="h-10 rounded-btn bg-primary-deep px-5 text-aux font-medium text-white"
        >
          Back to the team
        </button>
      </div>
    )
  }

  const peers = experts
    .filter((e) => e.group === expert.group && e.id !== expert.id)
    .slice(0, 6)

  return (
    <div className="mx-auto max-w-4xl px-8 py-8">
      <button
        onClick={() => navigate('/experts')}
        className="inline-flex items-center gap-1.5 text-aux text-ink-2 transition-colors hover:text-primary-deep"
      >
        <ChevronLeft size={16} /> Back to the team
      </button>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="mt-5 flex flex-col gap-6 rounded-card border border-line/60 bg-card p-7 shadow-card sm:flex-row sm:items-center"
      >
        <div className="relative shrink-0">
          <VAvatar
            expert={expert}
            size={112}
            className="!rounded-card shadow-float"
          />
          <span className="absolute -bottom-2 -right-2 grid h-9 w-9 place-items-center rounded-full bg-card text-primary shadow-card">
            <DomainIcon name={expert.domain_icon} size={18} />
          </span>
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-serif text-h1 text-ink">{expert.name}</h1>
            <span
              className={`inline-flex h-6 items-center rounded-chip px-2.5 text-tag font-medium ${
                ACCENT_CHIP[LEVEL_ACCENT[expert.level]]
              }`}
            >
              {expert.level}
            </span>
          </div>
          <div className="mt-1 text-body text-primary-deep">{expert.role_title}</div>
          <div className="text-tag text-ink-3">{LEVEL_LABEL[expert.level]}</div>
          <p className="mt-3 text-aux leading-relaxed text-ink-2">{expert.one_liner}</p>
        </div>
      </motion.div>

      <div className="mt-5 grid grid-cols-1 gap-5 md:grid-cols-2">
        <VCard hover={false}>
          <div className="flex items-center gap-2 text-aux font-semibold text-ink">
            <Sparkles size={16} className="text-primary" /> Core skills
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {expert.skills.map((s) => (
              <span
                key={s}
                className="inline-flex h-7 items-center rounded-chip bg-primary-tint px-3 text-tag font-medium text-primary-deep"
              >
                {s}
              </span>
            ))}
          </div>
        </VCard>

        <VCard hover={false}>
          <div className="flex items-center gap-2 text-aux font-semibold text-ink">
            <Target size={16} className="text-primary" /> Expertise
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {expert.knowledge_tags.map((t) => (
              <span
                key={t}
                className="inline-flex h-7 items-center rounded-chip border border-line px-3 text-tag text-ink-2"
              >
                {t}
              </span>
            ))}
          </div>
        </VCard>

        <VCard hover={false} className="md:col-span-2">
          <div className="flex items-center gap-2 text-aux font-semibold text-ink">
            <BookText size={16} className="text-primary" /> Background
          </div>
          <p className="mt-3 text-body leading-relaxed text-ink-2">
            {expert.knowledge_base}
          </p>
        </VCard>

        <VCard hover={false} className="md:col-span-2">
          <div className="flex items-center gap-2 text-aux font-semibold text-ink">
            <Award size={16} className="text-primary" /> Track record
          </div>
          <div className="mt-3 flex gap-8">
            <div>
              <div className="font-serif text-h2 text-primary-deep">
                {num(expert.stats.missions)}
              </div>
              <div className="text-tag text-ink-3">Engagements</div>
            </div>
            <div>
              <div className="font-serif text-h2 text-primary-deep">
                {expert.stats.avg_evidence || '—'}
              </div>
              <div className="text-tag text-ink-3">Avg. sources cited</div>
            </div>
          </div>
        </VCard>
      </div>

      {peers.length > 0 && (
        <div className="mt-8">
          <div className="mb-3 text-aux font-semibold text-ink">Works alongside</div>
          <div className="flex flex-wrap gap-3">
            {peers.map((p) => (
              <button
                key={p.id}
                onClick={() => navigate(`/experts/${p.id}`)}
                className="flex items-center gap-2.5 rounded-card border border-line/60 bg-card p-2.5 pr-4 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-float"
              >
                <VAvatar expert={p} size={36} />
                <div className="text-left">
                  <div className="text-aux font-medium text-ink">{p.name}</div>
                  <div className="text-tag text-ink-3">{p.nickname}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
