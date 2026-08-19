/** Publishers the backend's credibility table actually scores highly
 *  (see backend/app/services/domains.py). Real names from real code — not a logo
 *  wall implying a partnership that does not exist. */
const WEIGHTED_SOURCES = [
  'prothomalo.com',
  'thedailystar.net',
  'bdnews24.com',
  'rumorscanner.com',
  'bmd.gov.bd',
  'bbc.com',
  'reuters.com',
  'who.int',
  'cdc.gov',
  'bbs.gov.bd',
]

const PRINCIPLES = [
  {
    title: 'It cannot invent a source',
    body: 'The model never receives or writes a URL — only a number pointing at a page that was really fetched. A fabricated citation is structurally impossible.',
  },
  {
    title: 'Every quote is checked',
    body: 'Each quote is matched character by character against the page it came from. Anything untraceable is discarded, and the count is shown with the result.',
  },
  {
    title: 'It says when it does not know',
    body: 'Thin or conflicting evidence returns Unverified rather than a guess. A confident answer is only given when the sources support one.',
  },
]

export function TrustSection() {
  return (
    <section aria-labelledby="trust-heading" className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
      <div>
        <h2 id="trust-heading" className="label-micro">
          Why you can check its working
        </h2>
        <p className="mt-2 max-w-measure text-h3 text-ink-soft">
          Most AI answers ask you to trust them. This one hands you the evidence and its own
          limits.
        </p>

        <dl className="mt-6 space-y-5">
          {PRINCIPLES.map((item) => (
            <div key={item.title} className="border-l-2 border-accent pl-4">
              <dt className="text-h3 font-semibold">{item.title}</dt>
              <dd className="mt-1 max-w-measure text-small text-ink-soft">{item.body}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="rounded-lg border border-hairline bg-sunken p-5">
        <h3 className="label-micro">Sources weighted highest</h3>
        <p className="mt-2 text-small text-ink-soft">
          Bangladeshi outlets and fact-checkers rank alongside the international wires, because
          local stories are often only covered locally.
        </p>

        <ul className="mt-4 flex flex-wrap gap-1.5">
          {WEIGHTED_SOURCES.map((domain) => (
            <li
              key={domain}
              className="rounded-full border border-hairline bg-card px-2.5 py-1 text-micro text-ink-soft"
            >
              {domain}
            </li>
          ))}
        </ul>

        <p className="mt-4 border-t border-hairline pt-3 text-micro text-ink-muted">
          Social media and blogs are read but scored lowest — they are usually where a claim
          starts, not evidence that it is true.
        </p>
      </div>
    </section>
  )
}
