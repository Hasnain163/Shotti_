import { useCallback, useEffect, useRef, useState } from 'react'
import { AboutPage } from './components/AboutPage'
import { AppShell } from './components/AppShell'
import { ClaimComposer } from './components/ClaimComposer'
import { ErrorState } from './components/ErrorState'
import { LandingPage } from './components/LandingPage'
import { ProgressPanel } from './components/ProgressPanel'
import { ResultPage } from './components/ResultPage'
import { useVerify } from './hooks/useVerify'

type View = 'home' | 'about'

export default function App() {
  const [view, setView] = useState<View>('home')
  const {
    phase,
    result,
    error,
    stageIndex,
    elapsedMs,
    isImage,
    submitClaim,
    submitScreenshot,
    reset,
  } = useVerify()

  // Kept so a failed run can be retried, and so the claim is visible while waiting.
  const lastInput = useRef<{ claim: string; file: File | null }>({ claim: '', file: null })

  const handleClaim = useCallback(
    (claim: string) => {
      lastInput.current = { claim, file: null }
      setView('home')
      submitClaim(claim)
    },
    [submitClaim],
  )

  const handleScreenshot = useCallback(
    (file: File) => {
      lastInput.current = { claim: '', file }
      setView('home')
      submitScreenshot(file)
    },
    [submitScreenshot],
  )

  const retry = useCallback(() => {
    const { claim, file } = lastInput.current
    if (file) submitScreenshot(file)
    else if (claim) submitClaim(claim)
  }, [submitClaim, submitScreenshot])

  // Move focus to the result when it lands, so keyboard and screen reader users are
  // taken to the answer rather than left at the top of the page.
  useEffect(() => {
    if (phase !== 'done') return
    const heading = document.getElementById('verdict-label')
    heading?.scrollIntoView({ block: 'center' })
    // preventScroll: scrollIntoView above already placed it; focusing must not fight it.
    heading?.focus({ preventScroll: true })
  }, [phase])

  if (view === 'about') {
    return (
      <AppShell onShowAbout={() => setView('about')} onHome={() => setView('home')}>
        <AboutPage onBack={() => setView('home')} />
      </AppShell>
    )
  }

  return (
    <AppShell onShowAbout={() => setView('about')} onHome={reset}>
      {phase === 'idle' && (
        <LandingPage
          onSubmitClaim={handleClaim}
          onSubmitScreenshot={handleScreenshot}
          onShowAbout={() => setView('about')}
        />
      )}

      {phase === 'verifying' && (
        <div className="mx-auto max-w-3xl px-4 sm:px-6 py-8 sm:py-12">
          <ProgressPanel
            claim={lastInput.current.claim || 'Reading the claim from your screenshot…'}
            stageIndex={stageIndex}
            elapsedMs={elapsedMs}
            isImage={isImage}
          />
        </div>
      )}

      {phase === 'error' && error && (
        <div className="mx-auto max-w-3xl px-4 sm:px-6 py-8 space-y-6">
          <ErrorState error={error} onRetry={retry} onReset={reset} />
          <ClaimComposer
            onSubmitClaim={handleClaim}
            onSubmitScreenshot={handleScreenshot}
            initialClaim={lastInput.current.claim}
          />
        </div>
      )}

      {phase === 'done' && result && <ResultPage result={result} onNewClaim={reset} />}
    </AppShell>
  )
}
