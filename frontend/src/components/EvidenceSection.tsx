import { detectLanguage, formatPublishedDate } from '../lib/format'
import { RELIABILITY_META, STANCE_STYLES } from '../lib/verdict'
import type { EvidenceItem, Source, SourceAssessment, Stance } from '../types'

interface CardProps {
  item: EvidenceItem
  source: Source | undefined
  assessment: SourceAssessment | undefined
  stance: Stance
  onJumpToSource: (index: number) => void
}

/** One quote, with a coloured rail showing its stance.
 *
 *  The quote is set in a serif and marked up as a blockquote — a semantic choice, not
 *  a decorative one. It signals "these are someone else's words, not ours" both
 *  visually and to a screen reader. */
function EvidenceCard({ item, source, assessment, stance, onJumpToSource }: CardProps) {
  const style = STANCE_STYLES[stance]
  const reliability = assessment ? RELIABILITY_META[assessment.reliability] : null
  const date = formatPublishedDate(source?.published_date ?? null)

  return (
    <li className="group flex gap-0 overflow-hidden rounded border border-hairline bg-card">
      <div
        aria-hidden="true"
        className={`w-[3px] shrink-0 ${style.rail} transition-[width] duration-micro group-hover:w-[4px]`}
      />

      <div className="min-w-0 flex-1 p-3.5">
        <blockquote
          lang={detectLanguage(item.quote)}
          className="font-quote text-body text-ink"
        >
          “{item.quote}”
        </blockquote>

        <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-small text-ink-muted">
          {source ? (
            <>
              <button
                onClick={() => onJumpToSource(item.source_index)}
                className="font-medium text-accent hover:underline underline-offset-2 rounded-sm"
              >
                {source.domain}
              </button>
              {date && (
                <>
                  <span aria-hidden="true">·</span>
                  <span>{date}</span>
                </>
              )}
              {reliability && (
                <>
                  <span aria-hidden="true">·</span>
                  <span>{reliability.label}</span>
                </>
              )}
              {assessment?.is_outdated && (
                <>
                  <span aria-hidden="true">·</span>
                  <span className="font-medium text-misleading-text">May be outdated</span>
                </>
              )}
            </>
          ) : (
            <span>Source unavailable</span>
          )}
        </div>
      </div>
    </li>
  )
}

interface Props {
  supporting: EvidenceItem[]
  contradicting: EvidenceItem[]
  sources: Source[]
  assessments: SourceAssessment[]
  onJumpToSource: (index: number) => void
}

/** Two symmetrical columns with counts.
 *
 *  Equal width is the point: if contradicting evidence outnumbers supporting, the
 *  reader should see that shape instantly. A fact-checker whose layout favours one
 *  side is not one. */
export function EvidenceSection({
  supporting,
  contradicting,
  sources,
  assessments,
  onJumpToSource,
}: Props) {
  const byIndex = new Map(assessments.map((item) => [item.source_index, item]))

  const columns: Array<{ stance: Stance; title: string; items: EvidenceItem[] }> = [
    { stance: 'supports', title: 'Supporting evidence', items: supporting },
    { stance: 'contradicts', title: 'Contradicting evidence', items: contradicting },
  ]

  if (supporting.length === 0 && contradicting.length === 0) {
    return (
      <section aria-labelledby="evidence-heading">
        <h2 id="evidence-heading" className="label-micro mb-3">
          Evidence
        </h2>
        <p className="rounded border border-dashed border-hairline-strong p-4 text-body text-ink-muted">
          No quote from the sources directly addressed this claim. That is why the verdict
          is not stronger than it is.
        </p>
      </section>
    )
  }

  return (
    <section aria-labelledby="evidence-heading">
      <h2 id="evidence-heading" className="sr-only">
        Evidence
      </h2>

      <div className="grid gap-4 md:grid-cols-2">
        {columns.map((column) => (
          <div key={column.stance}>
            <h3 className="label-micro mb-2.5 flex items-center gap-2">
              <span
                aria-hidden="true"
                className={`h-2.5 w-2.5 rounded-sm ${STANCE_STYLES[column.stance].rail}`}
              />
              {column.title}
              <span className="tabular-nums">({column.items.length})</span>
            </h3>

            {column.items.length === 0 ? (
              <p className="rounded border border-dashed border-hairline-strong p-3 text-small text-ink-muted">
                None found.
              </p>
            ) : (
              <ul className="space-y-2.5">
                {column.items.map((item, index) => (
                  <EvidenceCard
                    key={`${item.source_index}-${index}`}
                    item={item}
                    source={sources[item.source_index]}
                    assessment={byIndex.get(item.source_index)}
                    stance={column.stance}
                    onJumpToSource={onJumpToSource}
                  />
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
