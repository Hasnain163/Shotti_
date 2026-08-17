import { detectLanguage } from '../lib/format'
import { verdictStyle } from '../lib/verdict'
import type { Verdict } from '../types'
import { ConfidenceMeter } from './ConfidenceMeter'

interface Props {
  verdict: Verdict
  confidence: number
  explanation: string
  degraded: boolean
}

/** The loudest element on the page, by design.
 *
 *  Colour, icon, and text label all carry the verdict, so it survives greyscale, a
 *  printed screenshot, and red-green colourblindness. UNVERIFIED is deliberately
 *  neutral-toned: "we don't know" must not read as a soft yes or no. */
export function VerdictCard({ verdict, confidence, explanation, degraded }: Props) {
  const style = verdictStyle(verdict)
  const language = detectLanguage(explanation)

  return (
    <section
      role="status"
      aria-live="polite"
      aria-labelledby="verdict-label"
      className={`animate-rise-in overflow-hidden rounded-lg border-2 ${style.edge} ${style.fill}`}
    >
      <div className={`h-1.5 w-full ${style.ring}`} aria-hidden="true" />

      <div className="p-5 sm:p-7">
        <div className="flex items-start gap-3 sm:gap-4">
          <span
            aria-hidden="true"
            className={`grid h-11 w-11 shrink-0 place-items-center rounded-full border-2 ${style.edge} ${style.text} text-h2 font-bold`}
          >
            {style.icon}
          </span>

          <div className="min-w-0 flex-1">
            <h2
              id="verdict-label"
              className={`font-display text-h1 font-bold ${style.text}`}
            >
              {style.label}
            </h2>
            <p lang="bn" className={`text-body ${style.text} opacity-80`}>
              {style.labelBn}
            </p>
          </div>
        </div>

        <div className="mt-5 grid gap-5 sm:grid-cols-[minmax(0,1fr)_200px] sm:items-start">
          <p
            lang={language}
            className="max-w-measure text-body text-ink whitespace-pre-line"
          >
            {explanation}
          </p>

          <div className="sm:pt-0.5">
            <ConfidenceMeter score={confidence} barClass={style.ring} />
          </div>
        </div>

        <p className="mt-5 border-t border-current/15 pt-3 text-small text-ink-soft">
          {style.meaning}
          {degraded && ' Part of the research was incomplete, so treat this with extra care.'}
        </p>
      </div>
    </section>
  )
}
