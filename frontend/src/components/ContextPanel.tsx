import { detectLanguage } from '../lib/format'
import { InfoIcon } from './icons'

interface Props {
  notes: string[]
}

/** Important context sits above the evidence, not below it.
 *
 *  A MISLEADING verdict is mostly context — burying the caveats under two columns of
 *  quotes would misinform by layout. */
export function ContextPanel({ notes }: Props) {
  if (notes.length === 0) return null

  return (
    <section
      aria-labelledby="context-heading"
      className="rounded-lg border border-hairline bg-sunken p-4 sm:p-5"
    >
      <h2 id="context-heading" className="label-micro mb-3 flex items-center gap-2">
        <InfoIcon /> Important context
      </h2>

      <ul className="space-y-2">
        {notes.map((note, index) => (
          <li
            key={index}
            lang={detectLanguage(note)}
            className="flex gap-2.5 text-body text-ink-soft max-w-measure"
          >
            <span aria-hidden="true" className="text-ink-muted">
              ·
            </span>
            <span>{note}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
