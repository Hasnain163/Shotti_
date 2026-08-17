import { detectLanguage, formatPublishedDate } from '../lib/format'
import { RELIABILITY_META, SOURCE_TYPE_LABELS, STANCE_STYLES } from '../lib/verdict'
import type { Source, SourceAssessment } from '../types'
import { ExternalIcon } from './icons'

interface ReliabilityMeterProps {
  filled: number
  label: string
}

/** Three segments plus a word. Never a coloured dot alone — the word is what makes
 *  this readable without colour vision. */
function ReliabilityMeter({ filled, label }: ReliabilityMeterProps) {
  return (
    <span className="inline-flex items-center gap-1.5" title={label}>
      <span aria-hidden="true" className="inline-flex gap-0.5">
        {[1, 2, 3].map((segment) => (
          <span
            key={segment}
            className={`h-1.5 w-3 rounded-sm ${
              segment <= filled ? 'bg-ink-soft' : 'bg-hairline-strong'
            }`}
          />
        ))}
      </span>
      <span className="text-small text-ink-muted">{label}</span>
    </span>
  )
}

interface CardProps {
  index: number
  source: Source
  assessment: SourceAssessment | undefined
  highlighted: boolean
}

function SourceCard({ index, source, assessment, highlighted }: CardProps) {
  const date = formatPublishedDate(source.published_date)
  const stance = assessment ? STANCE_STYLES[assessment.stance] : null
  const reliability = assessment ? RELIABILITY_META[assessment.reliability] : null
  const typeLabel = source.source_type ? SOURCE_TYPE_LABELS[source.source_type] : null

  return (
    <li
      id={`source-${index}`}
      className={`scroll-mt-20 rounded border bg-card p-3.5 transition-colors duration-panel ${
        highlighted ? 'border-accent bg-accent-soft' : 'border-hairline'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          lang={detectLanguage(source.title)}
          className="min-w-0 flex-1 text-body font-medium text-ink hover:text-accent hover:underline underline-offset-2 rounded-sm"
        >
          {source.title}
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
        <ExternalIcon className="mt-1 text-ink-muted" />
      </div>

      <p className="mt-1 truncate text-small text-ink-muted">{source.domain}</p>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {typeLabel && (
          <span className="rounded-sm bg-sunken px-1.5 py-0.5 text-micro font-semibold text-ink-soft">
            {typeLabel}
          </span>
        )}
        {reliability && <ReliabilityMeter filled={reliability.filled} label={reliability.label} />}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-small text-ink-muted">
        {/* Missing dates are common and stated plainly rather than hidden: an undated
            page cannot be assumed current. */}
        <span>{date ? `Published ${date}` : 'No publication date available'}</span>
        {assessment?.is_outdated && (
          <>
            <span aria-hidden="true">·</span>
            <span className="font-medium text-misleading-text">May be outdated</span>
          </>
        )}
        {stance && (
          <>
            <span aria-hidden="true">·</span>
            <span className={`font-medium ${stance.text}`}>{stance.sentence}</span>
          </>
        )}
      </div>

      {assessment?.note && (
        <p lang={detectLanguage(assessment.note)} className="mt-2 text-small text-ink-soft">
          {assessment.note}
        </p>
      )}
    </li>
  )
}

interface Props {
  sources: Source[]
  assessments: SourceAssessment[]
  highlightedIndex: number | null
}

export function SourceSection({ sources, assessments, highlightedIndex }: Props) {
  const byIndex = new Map(assessments.map((item) => [item.source_index, item]))

  return (
    <section aria-labelledby="sources-heading">
      <h2 id="sources-heading" className="label-micro mb-3">
        Sources <span className="tabular-nums">({sources.length})</span>
      </h2>

      {sources.length === 0 ? (
        <p className="rounded border border-dashed border-hairline-strong p-4 text-body text-ink-muted">
          No sources could be retrieved for this claim.
        </p>
      ) : (
        <ul className="space-y-2.5">
          {sources.map((source, index) => (
            <SourceCard
              key={source.url}
              index={index}
              source={source}
              assessment={byIndex.get(index)}
              highlighted={highlightedIndex === index}
            />
          ))}
        </ul>
      )}
    </section>
  )
}
