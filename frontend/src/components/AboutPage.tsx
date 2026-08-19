import { VerdictLegend } from './landing/VerdictLegend'


const LIMITS = [
  'It only reads public web pages. Private posts, closed groups, and messages are out of reach.',
  'It cannot detect an edited screenshot. A name or date inside an image is only what the image claims.',
  'It cannot verify claims that live in video or audio — only text it can read.',
  'Local Bangladeshi topics sometimes have thin online coverage, which produces Unverified rather than an answer.',
  'The AI can misread evidence. The sources are listed so you can check the reasoning yourself.',
  'A verification takes 25–40 seconds, because it really does search and read pages.',
]

interface Props {
  onBack: () => void
}

export function AboutPage({ onBack }: Props) {
  return (
    <div className="mx-auto max-w-shell px-4 sm:px-6 py-10">
      <button
        onClick={onBack}
        className="mb-6 text-small font-medium text-accent hover:underline underline-offset-2 rounded-sm"
      >
        ← Back
      </button>

      <h1 className="font-display text-h1 font-bold">How Shotti? AI works</h1>

      <section className="mt-8 max-w-measure">
        <h2 className="text-h2 font-semibold">The method</h2>
        <p className="mt-3 text-body text-ink-soft">
          A claim goes through four stages. First it is read and restated as a checkable
          proposition, with search queries in both Bangla and English. Then those queries are
          run against the web, and the most credible results are fetched and cleaned. Finally
          the evidence is weighed — each source assessed for what it says about the claim, how
          reliable it is, and whether it is current enough to matter.
        </p>
        <p className="mt-3 text-body text-ink-soft">
          The AI that weighs evidence never sees a URL it could invent. It refers to sources
          only by number, and every quote it produces is checked, character by character,
          against the page it was taken from. Quotes that cannot be found are discarded, and
          the count of discarded quotes is reported with each result.
        </p>
      </section>

      <section className="mt-10">
        <h2 className="text-h2 font-semibold">The four verdicts</h2>
        <div className="mt-4">
          <VerdictLegend />
        </div>

        <p className="mt-4 max-w-measure text-body text-ink-soft">
          <strong className="font-semibold text-ink">Misleading and Unverified are not the
          same thing.</strong>{' '}
          Misleading means we found evidence and the claim distorts it — a real statistic from
          the wrong year, a real quote stripped of context. Unverified means we did not find
          enough to say either way. The second is an honest gap, not a soft verdict.
        </p>
      </section>

      <section className="mt-10 max-w-measure">
        <h2 className="text-h2 font-semibold">What this cannot do</h2>
        <ul className="mt-3 space-y-2">
          {LIMITS.map((limit) => (
            <li key={limit} className="flex gap-2.5 text-body text-ink-soft">
              <span aria-hidden="true" className="text-ink-muted">
                ·
              </span>
              <span>{limit}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-10 max-w-measure">
        <h2 className="text-h2 font-semibold">Built with</h2>
        <p className="mt-3 text-body text-ink-soft">
          Gemini for claim understanding, image reading, and evidence analysis. Firecrawl for
          web search and page retrieval. React, Vite, and Tailwind on the front; FastAPI and
          Pydantic on the back.
        </p>
      </section>
    </div>
  )
}
