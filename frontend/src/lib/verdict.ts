/** Verdict presentation, centralised so all four look consistent everywhere.
 *
 *  Every verdict carries an icon and a text label alongside its colour. Colour never
 *  carries meaning alone — that rule is what makes the result readable to a
 *  colourblind user, in greyscale, or in a printed screenshot. */

import type { Reliability, SourceType, Stance, Verdict } from '../types'

export interface VerdictStyle {
  label: string
  labelBn: string
  /** Single glyph, chosen to be distinguishable by shape alone. */
  icon: string
  /** What the verdict means, in plain words. */
  meaning: string
  fill: string
  edge: string
  text: string
  ring: string
}

export const VERDICTS: Record<Verdict, VerdictStyle> = {
  LIKELY_TRUE: {
    label: 'Likely true',
    labelBn: 'সম্ভবত সত্য',
    icon: '✓',
    meaning: 'Reliable, current sources confirm this claim.',
    fill: 'bg-true-fill',
    edge: 'border-true-edge',
    text: 'text-true-text',
    ring: 'bg-true-edge',
  },
  LIKELY_FALSE: {
    label: 'Likely false',
    labelBn: 'সম্ভবত মিথ্যা',
    icon: '✕',
    meaning: 'Reliable, current sources contradict this claim.',
    fill: 'bg-false-fill',
    edge: 'border-false-edge',
    text: 'text-false-text',
    ring: 'bg-false-edge',
  },
  MISLEADING: {
    label: 'Misleading',
    labelBn: 'বিভ্রান্তিকর',
    icon: '⚠',
    meaning: 'Something here is accurate, but it is framed to mislead.',
    fill: 'bg-misleading-fill',
    edge: 'border-misleading-edge',
    text: 'text-misleading-text',
    ring: 'bg-misleading-edge',
  },
  UNVERIFIED: {
    label: 'Unverified',
    labelBn: 'যাচাই করা যায়নি',
    icon: '?',
    meaning: 'The available sources do not settle this claim either way.',
    fill: 'bg-unverified-fill',
    edge: 'border-unverified-edge',
    text: 'text-unverified-text',
    ring: 'bg-unverified-edge',
  },
}

export function verdictStyle(verdict: Verdict): VerdictStyle {
  return VERDICTS[verdict] ?? VERDICTS.UNVERIFIED
}

/** Describes the number rather than restating it, so the meter is not read as a
 *  precision instrument it is not. */
export function confidenceLabel(score: number): string {
  if (score >= 0.8) return 'Strong evidence'
  if (score >= 0.5) return 'Moderate evidence'
  if (score >= 0.2) return 'Weak evidence'
  return 'Almost no evidence'
}

export const STANCE_STYLES: Record<Stance, { label: string; rail: string; text: string }> = {
  supports: { label: 'Supports', rail: 'bg-true-edge', text: 'text-true-text' },
  contradicts: { label: 'Contradicts', rail: 'bg-false-edge', text: 'text-false-text' },
  neutral: { label: 'Neutral', rail: 'bg-hairline-strong', text: 'text-ink-muted' },
}

/** Reliability renders as a 3-segment meter plus this label — never a colour dot
 *  on its own. */
export const RELIABILITY_META: Record<Reliability, { label: string; filled: number }> = {
  high: { label: 'High reliability', filled: 3 },
  medium: { label: 'Medium reliability', filled: 2 },
  low: { label: 'Low reliability', filled: 1 },
}

export const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  fact_check: 'Fact-check',
  news: 'News',
  government: 'Official',
  academic: 'Academic',
  encyclopedia: 'Reference',
  social: 'Social media',
  blog: 'Blog',
  other: 'Other',
}
