import { ClaimComposer } from './ClaimComposer'
import { ExampleVerdict } from './landing/ExampleVerdict'
import { HowItWorks } from './landing/HowItWorks'
import { TrustSection } from './landing/TrustSection'
import { VerdictLegend } from './landing/VerdictLegend'

/** Real claims, not marketing copy. Two Bangla, one English — each a plausible thing
 *  someone would actually want checked. */
const EXAMPLES = [
  { text: 'গতকাল ঢাকায় ৭ মাত্রার ভূমিকম্প হয়েছে', lang: 'bn' as const },
  { text: 'Bangladesh won the ICC Champions Trophy in 2017', lang: 'en' as const },
  { text: 'গরম পানি খেলে ডেঙ্গু সেরে যায়', lang: 'bn' as const },
]

interface Props {
  onSubmitClaim: (claim: string) => void
  onSubmitScreenshot: (file: File) => void
  onShowAbout: () => void
}

export function LandingPage({ onSubmitClaim, onSubmitScreenshot, onShowAbout }: Props) {
  return (
    <div>
      {/* ── Hero ─────────────────────────────────────────────────────────────
          The composer sits in the hero rather than below it: the product is one
          input away, and a landing page that makes you scroll to use it is a
          brochure. */}
      <section className="relative overflow-hidden border-b border-hairline">
        <div
          aria-hidden="true"
          className="dot-grid pointer-events-none absolute inset-0 opacity-70"
        />

        <div className="relative mx-auto max-w-shell px-4 sm:px-6 pt-10 pb-12 sm:pt-16 sm:pb-16">
          <div className="grid gap-10 lg:grid-cols-[1.15fr_0.85fr] lg:items-center lg:gap-12">
            <div>
              <p className="inline-flex items-center gap-2 rounded-full border border-hairline bg-card px-3 py-1 text-micro font-semibold text-ink-soft">
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-accent" />
                বাংলা <span className="text-ink-muted">·</span> English
              </p>

              <h1 className="mt-5 max-w-[20ch] font-display text-display font-bold">
                Is it <span className="text-accent">true</span>?
              </h1>

              <p className="mt-4 max-w-measure text-h3 text-ink-soft">
                Paste a claim or a screenshot. Shotti? AI searches the web in Bangla and
                English, reads the sources, and shows you the evidence on both sides — then
                tells you how confident it is.
              </p>

              <div className="mt-7">
                <ClaimComposer
                  onSubmitClaim={onSubmitClaim}
                  onSubmitScreenshot={onSubmitScreenshot}
                />
              </div>

              <div className="mt-5">
                <p className="label-micro mb-2.5">Try one of these</p>
                <ul className="flex flex-wrap gap-2">
                  {EXAMPLES.map((example) => (
                    <li key={example.text}>
                      <button
                        onClick={() => onSubmitClaim(example.text)}
                        lang={example.lang}
                        className="rounded-full border border-hairline bg-card px-3.5 py-2 text-small text-ink-soft
                                   transition-colors duration-micro hover:border-hairline-strong hover:text-ink"
                      >
                        {example.text}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Shows the actual output shape before the visitor spends 30 seconds
                waiting for their own. */}
            <div>
              <ExampleVerdict />
            </div>
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-shell space-y-16 px-4 sm:px-6 py-14 sm:space-y-20 sm:py-16">
        <HowItWorks />

        <section aria-labelledby="verdicts-heading">
          <h2 id="verdicts-heading" className="label-micro">
            Four possible verdicts
          </h2>
          <p className="mt-2 max-w-measure text-h3 text-ink-soft">
            Including two ways of not saying yes or no — because most misinformation is neither
            plainly true nor plainly false.
          </p>
          <div className="mt-6">
            <VerdictLegend />
          </div>
        </section>

        <TrustSection />

        {/* Closing section points at the limitations rather than a hard sell: on a
            fact-checking product, admitting the edges is the more persuasive move. */}
        <section className="rounded-lg border border-hairline bg-card p-6 sm:p-8">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <h2 className="font-display text-h2 font-bold">Check something now</h2>
              <p className="mt-2 max-w-measure text-body text-ink-soft">
                A verification takes about thirty seconds because it genuinely searches and
                reads pages. It can still be wrong — so it shows you every source it used.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => {
                  document.getElementById('claim')?.focus()
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
                className="rounded bg-accent px-5 py-2.5 text-small font-semibold text-white
                           transition-opacity duration-micro hover:opacity-90 min-h-[44px]"
              >
                Verify a claim
              </button>
              <button
                onClick={onShowAbout}
                className="rounded border border-hairline-strong bg-card px-5 py-2.5 text-small font-semibold
                           transition-colors duration-micro hover:bg-sunken min-h-[44px]"
              >
                What it cannot do
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
