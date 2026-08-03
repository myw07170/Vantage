import { Quote, ExternalLink, MessageSquareText } from 'lucide-react'
import type { ChartSpec, SentimentResult } from '../types'
import { VChart } from './VChart'
import { PLATFORM_LABEL, PLATFORM_STYLE, SENTIMENT_LABEL } from '../lib/labels'
import { plural } from '../lib/format'

const SENT_CLS: Record<string, string> = {
  pos: 'bg-ok/15 text-ok',
  neg: 'bg-risk/15 text-risk',
  neu: 'bg-ink-3/10 text-ink-3',
}

function platformChip(platform: string) {
  const style = PLATFORM_STYLE[platform]
  if (!style) return { dot: '#9AA39C', bg: 'rgba(154,163,156,0.12)', fg: '#6B746C' }
  return { dot: style.bg, bg: `${style.bg}18`, fg: style.bg }
}

/** The user-sentiment chapter: quotes, overall split, per-platform, camps. */
export function VSentimentPanel({
  sentiment,
  charts,
}: {
  sentiment: SentimentResult
  charts?: ChartSpec[]
}) {
  const { overall, by_platform, camps, voices, highlights, sample_size } = sentiment
  const total = overall.pos + overall.neu + overall.neg || 1

  if (!sample_size) {
    return (
      <p className="rounded-card border border-line bg-paper p-4 text-aux text-ink-2">
        No linked user comments were retrieved, so no sentiment breakdown is shown.
        Reporting percentages without the underlying comments would break the
        no-claim-without-evidence rule.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="text-tag text-ink-3">
        Based on {plural(sample_size, 'linked comment')} from Reddit, Hacker News,
        review sites and video.
      </div>

      {highlights && highlights.length > 0 && (
        <div className="rounded-card border border-sun/40 bg-gradient-to-br from-sun-soft to-card p-4">
          <div className="mb-3 flex items-center gap-2 text-aux font-semibold text-ink">
            <Quote size={15} className="text-warn" />
            What users actually said
          </div>
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
            {highlights.map((h, i) => {
              const ps = platformChip(h.platform)
              return (
                <a
                  key={i}
                  href={h.url}
                  target="_blank"
                  rel="noreferrer"
                  className="group flex items-start gap-2.5 rounded-card border border-line/50 bg-card/80 p-3 transition-all hover:border-primary/50 hover:shadow-card"
                >
                  <span
                    className="mt-1 h-2 w-2 shrink-0 rounded-full"
                    style={{ background: ps.dot }}
                  />
                  <div className="min-w-0">
                    <p className="text-aux font-medium leading-relaxed text-ink">
                      “{h.phrase}”
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <span
                        className="rounded-chip px-2 py-0.5 text-[11px] font-medium"
                        style={{ background: ps.bg, color: ps.fg }}
                      >
                        {h.platform_label || PLATFORM_LABEL[h.platform] || h.platform}
                      </span>
                      <span
                        className={`rounded-chip px-2 py-0.5 text-[11px] ${
                          SENT_CLS[h.sentiment] ?? SENT_CLS.neu
                        }`}
                      >
                        {SENTIMENT_LABEL[h.sentiment] ?? h.sentiment}
                      </span>
                      <ExternalLink
                        size={11}
                        className="ml-auto text-ink-3 opacity-0 transition-opacity group-hover:opacity-100"
                      />
                    </div>
                  </div>
                </a>
              )
            })}
          </div>
        </div>
      )}

      <div>
        <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2 text-tag text-ink-2">
          <span>Overall sentiment</span>
          <span>
            {Math.round((overall.pos / total) * 100)}% positive ·{' '}
            {Math.round((overall.neu / total) * 100)}% neutral ·{' '}
            {Math.round((overall.neg / total) * 100)}% negative
          </span>
        </div>
        <div className="flex h-3 w-full overflow-hidden rounded-chip">
          <div className="bg-ok" style={{ width: `${(overall.pos / total) * 100}%` }} />
          <div
            className="bg-ink-3/40"
            style={{ width: `${(overall.neu / total) * 100}%` }}
          />
          <div className="bg-risk" style={{ width: `${(overall.neg / total) * 100}%` }} />
        </div>
      </div>

      {charts && charts.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {charts.map((c) => (
            <VChart key={c.chart_id} spec={c} height={240} />
          ))}
        </div>
      )}

      <div>
        <div className="mb-2 text-aux font-semibold text-ink">By platform</div>
        <div className="flex flex-col gap-2">
          {Object.entries(by_platform).map(([plat, v]) => {
            const t = v.pos + v.neu + v.neg || 1
            return (
              <div key={plat} className="flex items-center gap-3">
                <span className="w-24 shrink-0 truncate text-tag text-ink-2">
                  {PLATFORM_LABEL[plat] ?? plat}
                </span>
                <div className="flex h-2.5 flex-1 overflow-hidden rounded-chip">
                  <div className="bg-ok" style={{ width: `${(v.pos / t) * 100}%` }} />
                  <div
                    className="bg-ink-3/40"
                    style={{ width: `${(v.neu / t) * 100}%` }}
                  />
                  <div className="bg-risk" style={{ width: `${(v.neg / t) * 100}%` }} />
                </div>
                <span className="w-8 shrink-0 text-right text-tag text-ink-3">{t}</span>
              </div>
            )
          })}
        </div>
      </div>

      {camps && camps.length > 0 && (
        <div>
          <div className="mb-2 text-aux font-semibold text-ink">Opinion camps</div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {camps.map((c, i) => (
              <div key={i} className="rounded-card border border-line/60 bg-bg p-4">
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 text-aux font-semibold text-ink">
                    {c.title}
                  </span>
                  <span className="inline-flex h-6 shrink-0 items-center rounded-chip bg-primary-tint px-2.5 text-tag font-medium text-primary-deep">
                    {Math.round(c.ratio)}%
                  </span>
                </div>
                <p className="mt-1.5 text-tag leading-relaxed text-ink-2">{c.summary}</p>
                {c.quotes?.slice(0, 1).map((q, qi) => (
                  <a
                    key={qi}
                    href={q.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 block rounded-btn bg-card px-3 py-2 text-tag italic text-ink-2 hover:text-primary-deep"
                  >
                    “{q.text}”
                  </a>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {voices && voices.length > 0 && (
        <div>
          <div className="mb-2 flex items-center gap-2 text-aux font-semibold text-ink">
            <MessageSquareText size={15} className="text-primary" />
            Verbatims · every one links to its source
          </div>
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 lg:grid-cols-3">
            {voices.map((v, i) => {
              const ps = platformChip(v.platform)
              return (
                <a
                  key={i}
                  href={v.url}
                  target="_blank"
                  rel="noreferrer"
                  className="group flex flex-col rounded-card border border-line/60 bg-bg p-3 transition-all hover:border-primary/50 hover:shadow-card"
                >
                  <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                    <span
                      className="rounded-chip px-2 py-0.5 text-[11px] font-medium"
                      style={{ background: ps.bg, color: ps.fg }}
                    >
                      {v.platform_label || PLATFORM_LABEL[v.platform] || v.platform}
                    </span>
                    <span
                      className={`rounded-chip px-2 py-0.5 text-[11px] ${
                        SENT_CLS[v.sentiment] ?? SENT_CLS.neu
                      }`}
                    >
                      {SENTIMENT_LABEL[v.sentiment] ?? v.sentiment}
                    </span>
                    <ExternalLink
                      size={11}
                      className="ml-auto text-ink-3 opacity-0 transition-opacity group-hover:opacity-100"
                    />
                  </div>
                  <p className="line-clamp-4 text-tag leading-relaxed text-ink-2">
                    “{v.text}”
                  </p>
                </a>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
