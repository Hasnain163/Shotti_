/** Small formatting helpers. */

/** Detects Bangla so we can set `lang` on the node.
 *
 *  This matters for more than fonts: it drives line-height, tells the browser how
 *  to hyphenate, and lets a screen reader switch to a Bangla voice. */
export function detectLanguage(text: string): 'bn' | 'en' {
  return /[ঀ-৿]/.test(text) ? 'bn' : 'en'
}

export function isBangla(text: string): boolean {
  return detectLanguage(text) === 'bn'
}

/** Publication dates arrive in whatever shape the page exposed — an ISO stamp,
 *  "2 days ago", or nothing. Show what we have; never invent precision. */
export function formatPublishedDate(raw: string | null): string | null {
  if (!raw) return null
  const trimmed = raw.trim()
  if (!trimmed) return null

  const parsed = Date.parse(trimmed)
  if (Number.isNaN(parsed)) return trimmed // already human-readable, e.g. "2 days ago"

  return new Date(parsed).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)}s`
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`
}
