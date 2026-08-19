import { VERDICTS } from '../../lib/verdict'
import type { Verdict } from '../../types'

const ORDER: Verdict[] = ['LIKELY_TRUE', 'LIKELY_FALSE', 'MISLEADING', 'UNVERIFIED']

interface Props {
  /** Compact drops the explanatory sentence, for tighter placements. */
  compact?: boolean
}

/** The four verdicts, shared by the landing page and the about page.
 *
 *  Extracted rather than duplicated: these are the product's core vocabulary, and two
 *  copies would eventually disagree with each other. */
export function VerdictLegend({ compact = false }: Props) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {ORDER.map((verdict) => {
        const style = VERDICTS[verdict]
        return (
          <li
            key={verdict}
            className={`rounded-lg border-2 ${style.edge} ${style.fill} p-4
                        transition-transform duration-panel hover:-translate-y-0.5`}
          >
            <div className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={`grid h-7 w-7 shrink-0 place-items-center rounded-full
                            border-2 ${style.edge} ${style.text} text-small font-bold`}
              >
                {style.icon}
              </span>
              <h3 className={`font-display text-h3 font-bold ${style.text}`}>{style.label}</h3>
              <span lang="bn" className={`text-small ${style.text} opacity-75`}>
                {style.labelBn}
              </span>
            </div>
            {!compact && <p className="mt-2 text-small text-ink">{style.meaning}</p>}
          </li>
        )
      })}
    </ul>
  )
}
