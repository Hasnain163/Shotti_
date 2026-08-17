import { useCallback, useEffect, useRef, useState } from 'react'
import { detectLanguage, formatDuration } from '../lib/format'
import { verdictStyle } from '../lib/verdict'
import type { ScreenshotVerifyResponse, VerifyResponse } from '../types'
import { ContextPanel } from './ContextPanel'
import { EvidenceSection } from './EvidenceSection'
import { ExtractionPanel } from './ExtractionPanel'
import { SourceSection } from './SourceSection'
import { VerdictCard } from './VerdictCard'

interface Props {
  result: VerifyResponse | ScreenshotVerifyResponse
  onNewClaim: () => void
}

function hasExtraction(
  result: VerifyResponse | ScreenshotVerifyResponse,
): result is ScreenshotVerifyResponse {
  return 'extraction' in result
}

export function ResultPage({ result, onNewClaim }: Props) {
  const [highlighted, setHighlighted] = useState<number | null>(null)
  const [showStickyBar, setShowStickyBar] = useState(false)
  const verdictRef = useRef<HTMLDivElement>(null)
  const style = verdictStyle(result.verdict)

  // Sticky summary once the verdict scrolls away, so it is never more than a glance
  // away on a long result.
  useEffect(() => {
    const node = verdictRef.current
    if (!node || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver(
      ([entry]) => setShowStickyBar(!entry?.isIntersecting),
      { threshold: 0 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const jumpToSource = useCallback((index: number) => {
    setHighlighted(index)
    document.getElementById(`source-${index}`)?.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'auto'
        : 'smooth',
      block: 'center',
    })
    window.setTimeout(() => setHighlighted(null), 1600)
  }, [])

  return (
    <div className="mx-auto max-w-shell px-4 sm:px-6 py-6 sm:py-8">
      {showStickyBar && (
        <div
          className={`fixed inset-x-0 top-14 z-20 border-b ${style.edge} ${style.fill} px-4 py-2 sm:px-6`}
        >
          <div className="mx-auto flex max-w-shell items-center gap-2">
            <span aria-hidden="true" className={`font-bold ${style.text}`}>
              {style.icon}
            </span>
            <span className={`text-small font-semibold ${style.text}`}>{style.label}</span>
            <span className="text-small text-ink-soft tabular-nums">
              · {Math.round(result.confidence_score * 100)}% confidence
            </span>
          </div>
        </div>
      )}

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-micro">Claim</p>
          <p
            lang={detectLanguage(result.claim)}
            className="mt-1 max-w-measure text-h3 font-medium"
          >
            {result.claim}
          </p>
          {result.normalized_claim &&
            result.normalized_claim !== result.claim &&
            detectLanguage(result.claim) === 'bn' && (
              <p className="mt-1 max-w-measure text-small text-ink-muted" lang="en">
                Checked as: {result.normalized_claim}
              </p>
            )}
        </div>

        <button
          onClick={onNewClaim}
          className="rounded border border-hairline-strong bg-card px-4 py-2.5 text-small font-semibold
                     hover:bg-sunken transition-colors duration-micro min-h-[44px]"
        >
          Check another claim
        </button>
      </div>

      <div ref={verdictRef}>
        <VerdictCard
          verdict={result.verdict}
          confidence={result.confidence_score}
          explanation={result.explanation}
          degraded={result.meta.degraded}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
        <div className="space-y-6">
          {hasExtraction(result) && <ExtractionPanel extraction={result.extraction} />}

          <ContextPanel notes={result.important_context} />

          <EvidenceSection
            supporting={result.supporting_evidence}
            contradicting={result.contradicting_evidence}
            sources={result.sources}
            assessments={result.source_assessments}
            onJumpToSource={jumpToSource}
          />
        </div>

        <div className="lg:sticky lg:top-20">
          <SourceSection
            sources={result.sources}
            assessments={result.source_assessments}
            highlightedIndex={highlighted}
          />
        </div>
      </div>

      {/* Stating what the run actually did, including what it threw away, is the most
          credible thing on the page. Every number here is real. */}
      <footer className="mt-10 border-t border-hairline pt-4">
        <p className="label-micro mb-2">How we checked this</p>
        <p className="text-small text-ink-muted">
          {result.meta.queries_used} search
          {result.meta.queries_used === 1 ? '' : 'es'} · {result.meta.sources_found} results
          found · {result.meta.sources_used} source
          {result.meta.sources_used === 1 ? '' : 's'} read ·{' '}
          {result.meta.dropped_evidence_count} quote
          {result.meta.dropped_evidence_count === 1 ? '' : 's'} discarded as untraceable ·{' '}
          {formatDuration(result.meta.duration_ms)}
          {result.meta.has_conflicting_evidence && ' · sources disagreed'}
          {result.meta.relies_on_speculation && ' · sources relied on speculation'}
        </p>
      </footer>
    </div>
  )
}
