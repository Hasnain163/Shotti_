import { verdictStyle } from '../../lib/verdict'

/** A real result this app produced, shown so the landing page can demonstrate the
 *  output without spending API quota on every visit.
 *
 *  Everything here is transcribed from an actual verification run — the verdict, the
 *  confidence, the quote, the publishers. It is labelled as an example so nobody
 *  mistakes it for a live check, and it is not a testimonial or a statistic. */
const EXAMPLE = {
  claim: 'গরম পানি খেলে ডেঙ্গু সেরে যায়',
  verdict: 'LIKELY_FALSE' as const,
  confidence: 0.95,
  quote: 'There is no specific antiviral treatment for dengue.',
  quoteSource: 'cdc.gov',
  publishers: ['cdc.gov', 'who.int'],
}

export function ExampleVerdict() {
  const style = verdictStyle(EXAMPLE.verdict)
  const percent = Math.round(EXAMPLE.confidence * 100)

  return (
    <figure className="card overflow-hidden">
      <figcaption className="flex items-center justify-between gap-2 border-b border-hairline bg-sunken px-4 py-2">
        <span className="label-micro">Example result</span>
        <span className="text-micro text-ink-muted">from a real check</span>
      </figcaption>

      <div className="p-4">
        <p lang="bn" className="text-small text-ink-soft">
          “{EXAMPLE.claim}”
        </p>

        <div className={`mt-3 rounded border-2 ${style.edge} ${style.fill} p-3`}>
          <div className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className={`grid h-7 w-7 shrink-0 place-items-center rounded-full border-2 ${style.edge} ${style.text} text-small font-bold`}
            >
              {style.icon}
            </span>
            <span className={`font-display text-h3 font-bold ${style.text}`}>{style.label}</span>
          </div>

          <div className="mt-3">
            <div className="flex items-baseline justify-between">
              <span className="label-micro">Confidence</span>
              <span className="text-small font-semibold tabular-nums">{percent}%</span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-black/10 dark:bg-white/15">
              <div className={`h-full rounded-full ${style.ring}`} style={{ width: `${percent}%` }} />
            </div>
          </div>
        </div>

        {/* The rail and serif quote are the same treatment the real result page uses. */}
        <div className="mt-3 flex overflow-hidden rounded border border-hairline">
          <div aria-hidden="true" className="w-[3px] shrink-0 bg-false-edge" />
          <div className="p-3">
            <blockquote className="font-quote text-small text-ink">“{EXAMPLE.quote}”</blockquote>
            <p className="mt-1.5 text-micro text-ink-muted">{EXAMPLE.quoteSource}</p>
          </div>
        </div>

        <p className="mt-3 text-micro text-ink-muted">
          Checked against {EXAMPLE.publishers.join(' and ')} · every quote traced back to its page
        </p>
      </div>
    </figure>
  )
}
