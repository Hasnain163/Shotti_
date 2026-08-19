const STEPS = [
  {
    n: 1,
    title: 'Understand',
    body: 'The claim is restated as a checkable proposition, with search queries in Bangla and English.',
  },
  {
    n: 2,
    title: 'Search',
    body: 'Both languages are searched together, so local reporting is not missed.',
  },
  {
    n: 3,
    title: 'Read',
    body: 'The most credible pages are fetched and stripped down to their substance.',
  },
  {
    n: 4,
    title: 'Weigh',
    body: 'Each source is judged on stance, reliability, and whether it is current.',
  },
]

export function HowItWorks() {
  return (
    <section aria-labelledby="how-heading">
      <h2 id="how-heading" className="label-micro">
        How a verification works
      </h2>
      <p className="mt-2 max-w-measure text-h3 text-ink-soft">
        Four stages, about thirty seconds. Nothing is answered from memory.
      </p>

      <ol className="relative mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {/* A single hairline tying the four stages together, so they read as one
            sequence rather than four unrelated cards. Decorative, desktop only. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-0 right-0 top-[15px] hidden h-px bg-hairline lg:block"
        />

        {STEPS.map((step) => (
          <li key={step.n} className="relative">
            <span
              className="relative z-10 grid h-8 w-8 place-items-center rounded-full border
                         border-hairline-strong bg-card text-small font-bold text-ink-soft"
            >
              {step.n}
            </span>
            <h3 className="mt-3 text-h3 font-semibold">{step.title}</h3>
            <p className="mt-1.5 text-small text-ink-soft">{step.body}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}
