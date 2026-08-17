import { ClaimComposer } from './ClaimComposer'

/** Real examples, not fabricated marketing copy. Two Bangla, one English, each a
 *  plausible thing someone would actually want checked. */
const EXAMPLES = [
  { text: 'গতকাল ঢাকায় ৭ মাত্রার ভূমিকম্প হয়েছে', lang: 'bn' as const },
  { text: 'Bangladesh won the ICC Champions Trophy in 2017', lang: 'en' as const },
  { text: 'গরম পানি খেলে ডেঙ্গু সেরে যায়', lang: 'bn' as const },
]

const STEPS = [
  { n: 1, title: 'Understand', body: 'The claim is read and turned into checkable questions.' },
  { n: 2, title: 'Search', body: 'Bangla and English sources are searched together.' },
  { n: 3, title: 'Read', body: 'Pages are fetched and the relevant passages extracted.' },
  { n: 4, title: 'Weigh', body: 'Evidence is assessed for stance, reliability, and date.' },
]

interface Props {
  onSubmitClaim: (claim: string) => void
  onSubmitScreenshot: (file: File) => void
  onShowAbout: () => void
}

export function LandingPage({ onSubmitClaim, onSubmitScreenshot, onShowAbout }: Props) {
  return (
    <div className="mx-auto max-w-shell px-4 sm:px-6">
      <section className="pt-12 pb-8 sm:pt-20 sm:pb-10">
        <h1 className="max-w-[22ch] font-display text-display font-bold">
          Is it <span className="text-accent">true</span>?
        </h1>
        <p className="mt-4 max-w-measure text-h3 text-ink-soft">
          Shotti? AI investigates claims in Bangla and English, then shows you the evidence
          behind every verdict — including the evidence against it.
        </p>
      </section>

      <div className="max-w-3xl">
        <ClaimComposer onSubmitClaim={onSubmitClaim} onSubmitScreenshot={onSubmitScreenshot} />

        <div className="mt-5">
          <p className="label-micro mb-2.5">Try one of these</p>
          <ul className="flex flex-wrap gap-2">
            {EXAMPLES.map((example) => (
              <li key={example.text}>
                <button
                  onClick={() => onSubmitClaim(example.text)}
                  lang={example.lang}
                  className="rounded-full border border-hairline bg-card px-3.5 py-2 text-small text-ink-soft
                             hover:border-hairline-strong hover:text-ink transition-colors duration-micro"
                >
                  {example.text}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <section aria-labelledby="method-heading" className="mt-16 border-t border-hairline pt-8">
        <h2 id="method-heading" className="label-micro mb-5">
          How a verification works
        </h2>

        <ol className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step) => (
            <li key={step.n}>
              <span className="grid h-7 w-7 place-items-center rounded-full border border-hairline-strong text-small font-bold text-ink-soft">
                {step.n}
              </span>
              <h3 className="mt-2.5 text-h3 font-semibold">{step.title}</h3>
              <p className="mt-1 text-small text-ink-soft">{step.body}</p>
            </li>
          ))}
        </ol>

        <p className="mt-6 text-small text-ink-muted">
          Every quote is checked against the page it came from, and anything that cannot be
          traced back is discarded.{' '}
          <button onClick={onShowAbout} className="font-medium text-accent underline underline-offset-2 rounded-sm">
            What this cannot do
          </button>
        </p>
      </section>
    </div>
  )
}
