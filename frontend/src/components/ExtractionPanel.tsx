import { detectLanguage } from '../lib/format'
import type { ScreenshotExtraction } from '../types'

const KIND_LABELS: Record<string, string> = {
  social_post: 'Social media post',
  news_article: 'News article',
  news_card: 'News card',
  messaging: 'Chat screenshot',
  video_frame: 'Video frame',
  document: 'Document',
  other: 'Image',
}

interface Props {
  extraction: ScreenshotExtraction
}

/** What we read from the image, shown so the user can judge whether we read it right.
 *
 *  The date and source visible *in* the image are shown separately from our own
 *  research, because a real story recirculated years later is one of the commonest
 *  forms of misinformation — and because we cannot tell whether a screenshot has been
 *  edited, which the note here says outright. */
export function ExtractionPanel({ extraction }: Props) {
  return (
    <section
      aria-labelledby="extraction-heading"
      className="rounded-lg border border-hairline bg-sunken p-4 sm:p-5"
    >
      <h2 id="extraction-heading" className="label-micro mb-3 flex items-center gap-2">
        <span aria-hidden="true">🖼</span> Read from your image
      </h2>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-small text-ink-muted">
        <span className="rounded-sm bg-card px-1.5 py-0.5 text-micro font-semibold text-ink-soft">
          {KIND_LABELS[extraction.kind] ?? 'Image'}
        </span>
        {extraction.visible_source && (
          <span>
            Shown as: <span className="font-medium text-ink-soft">{extraction.visible_source}</span>
          </span>
        )}
        {extraction.visible_date && (
          <span>
            Dated in image:{' '}
            <span className="font-medium text-ink-soft">{extraction.visible_date}</span>
          </span>
        )}
      </div>

      {extraction.extracted_text && (
        <details className="mt-3">
          <summary className="cursor-pointer text-small font-medium text-accent">
            Show the full text we read
          </summary>
          <p
            lang={detectLanguage(extraction.extracted_text)}
            className="mt-2 whitespace-pre-line rounded border border-hairline bg-card p-3 text-small text-ink-soft"
          >
            {extraction.extracted_text}
          </p>
        </details>
      )}

      {extraction.notes && (
        <p className="mt-3 text-small text-ink-soft">
          <span className="font-medium">Note:</span> {extraction.notes}
        </p>
      )}

      <p className="mt-3 border-t border-hairline pt-2.5 text-small text-ink-muted">
        A name or date inside an image is only what the image claims. We cannot tell
        whether a screenshot has been edited.
      </p>
    </section>
  )
}
