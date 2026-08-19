import { IMAGE_STAGE, STAGES } from '../hooks/useVerify'
import { detectLanguage } from '../lib/format'

interface Props {
  claim: string
  stageIndex: number
  elapsedMs: number
  isImage: boolean
}

/** The wait, made legible.
 *
 *  Verification genuinely takes 25–35 seconds, and that is an asset rather than a
 *  problem: showing the named stages of an investigation is what distinguishes this
 *  from a black box that guessed. So no spinner, and no percentage — a percentage
 *  would be invented, and inventing numbers is the one thing this product cannot do. */
export function ProgressPanel({ claim, stageIndex, elapsedMs, isImage }: Props) {
  const stages = isImage ? [IMAGE_STAGE, ...STAGES] : STAGES
  const seconds = Math.floor(elapsedMs / 1000)

  return (
    <section className="card p-5 sm:p-6" aria-labelledby="progress-heading">
      <h2 id="progress-heading" className="label-micro mb-4">
        Investigating
      </h2>

      {claim && (
        <p
          lang={detectLanguage(claim)}
          className="mb-5 text-body text-ink-soft border-l-2 border-hairline-strong pl-3 max-w-measure"
        >
          {claim}
        </p>
      )}

      {/* One small live region announcing only the current stage. Putting aria-live on
          the list itself made a screen reader re-read all four stages on every change. */}
      <p className="sr-only" aria-live="polite">
        {stages[stageIndex]?.label ?? 'Working'}
      </p>

      <ol className="space-y-3">
        {stages.map((stage, index) => {
          const done = index < stageIndex
          const active = index === stageIndex

          return (
            <li key={stage.id} className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className={`grid h-6 w-6 shrink-0 place-items-center rounded-full border text-micro font-bold ${
                  done
                    ? 'border-accent bg-accent text-white'
                    : active
                      ? 'border-accent text-accent animate-stage-pulse'
                      : 'border-hairline-strong text-ink-muted'
                }`}
              >
                {done ? '✓' : index + 1}
              </span>
              <span
                className={`text-body ${
                  done ? 'text-ink-muted' : active ? 'font-medium text-ink' : 'text-ink-muted'
                }`}
              >
                {stage.label}
                {active && <span className="sr-only"> — in progress</span>}
                {done && <span className="sr-only"> — done</span>}
              </span>
            </li>
          )
        })}
      </ol>

      <p className="mt-5 border-t border-hairline pt-3 text-small text-ink-muted">
        <span className="tabular-nums">{seconds}s</span> elapsed. Checking real sources
        usually takes 25–40 seconds.
      </p>
    </section>
  )
}
