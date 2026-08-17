import { confidenceLabel } from '../lib/verdict'
import { formatPercent } from '../lib/format'

interface Props {
  score: number
  /** Tailwind class for the filled bar, matched to the verdict. */
  barClass: string
}

/** Confidence, shown as a meter plus a number plus words.
 *
 *  It lives inside the verdict card, never beside it: a verdict without its
 *  calibration is a half-truth. The word label carries the meaning for anyone who
 *  cannot read the bar. */
export function ConfidenceMeter({ score, barClass }: Props) {
  const percent = Math.round(Math.min(Math.max(score, 0), 1) * 100)

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="label-micro">Confidence</span>
        <span className="text-small font-semibold tabular-nums">{formatPercent(score)}</span>
      </div>

      <div
        role="meter"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Confidence: ${percent} percent, ${confidenceLabel(score)}`}
        className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-black/10 dark:bg-white/15"
      >
        <div
          className={`h-full rounded-full ${barClass} transition-[width] duration-500 ease-out`}
          style={{ width: `${percent}%` }}
        />
      </div>

      <p className="mt-1.5 text-small text-ink-soft">{confidenceLabel(score)}</p>
    </div>
  )
}
