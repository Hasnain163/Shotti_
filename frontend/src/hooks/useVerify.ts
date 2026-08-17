/** Owns the verification state machine: idle → verifying → result | error.
 *
 *  On progress stages: the backend returns one response at the end, so it cannot
 *  report which stage it is on. Rather than fake progress with a percentage bar, the
 *  stage list advances on timings measured from real runs (~26–34s total) and stops
 *  at the last stage until the response lands. The user sees the real sequence of
 *  work; nothing claims to be finished that is not. */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, verifyClaim, verifyScreenshot } from '../api/client'
import type { ScreenshotVerifyResponse, VerifyResponse } from '../types'

export type Phase = 'idle' | 'verifying' | 'done' | 'error'

export const STAGES = [
  { id: 'understand', label: 'Understanding the claim', afterMs: 0 },
  { id: 'search', label: 'Searching the web', afterMs: 5000 },
  { id: 'read', label: 'Reading the sources', afterMs: 12000 },
  { id: 'weigh', label: 'Weighing the evidence', afterMs: 24000 },
] as const

/** Prepended when the input is an image, since reading it really is a first step. */
export const IMAGE_STAGE = { id: 'read-image', label: 'Reading the screenshot', afterMs: 0 } as const

export interface VerifyState {
  phase: Phase
  result: VerifyResponse | ScreenshotVerifyResponse | null
  error: ApiError | null
  /** Index into the active stage list. */
  stageIndex: number
  elapsedMs: number
  isImage: boolean
}

const INITIAL: VerifyState = {
  phase: 'idle',
  result: null,
  error: null,
  stageIndex: 0,
  elapsedMs: 0,
  isImage: false,
}

export function useVerify() {
  const [state, setState] = useState<VerifyState>(INITIAL)
  const abortRef = useRef<AbortController | null>(null)
  const startedRef = useRef<number>(0)

  // Drive the elapsed clock and stage advance while a verification is in flight.
  useEffect(() => {
    if (state.phase !== 'verifying') return

    const stages = state.isImage ? [IMAGE_STAGE, ...STAGES] : STAGES
    const offset = state.isImage ? 8000 : 0

    const tick = window.setInterval(() => {
      const elapsed = Date.now() - startedRef.current
      const reached = stages.reduce(
        (acc, stage, index) =>
          elapsed >= (index === 0 ? 0 : stage.afterMs + offset) ? index : acc,
        0,
      )
      setState((prev) =>
        prev.phase === 'verifying'
          ? { ...prev, elapsedMs: elapsed, stageIndex: reached }
          : prev,
      )
    }, 250)

    return () => window.clearInterval(tick)
  }, [state.phase, state.isImage])

  const run = useCallback(
    async (task: (signal: AbortSignal) => Promise<VerifyResponse>, isImage: boolean) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      startedRef.current = Date.now()

      setState({ ...INITIAL, phase: 'verifying', isImage })

      try {
        const result = await task(controller.signal)
        setState({
          phase: 'done',
          result,
          error: null,
          stageIndex: 0,
          elapsedMs: Date.now() - startedRef.current,
          isImage,
        })
      } catch (caught) {
        if (controller.signal.aborted) return // superseded or cancelled; keep state
        const error =
          caught instanceof ApiError
            ? caught
            : new ApiError('Something went wrong. Please try again.', 'unknown_error', 0)
        setState({ ...INITIAL, phase: 'error', error, isImage })
      }
    },
    [],
  )

  const submitClaim = useCallback(
    (claim: string) => run((signal) => verifyClaim(claim, signal), false),
    [run],
  )

  const submitScreenshot = useCallback(
    (file: File) => run((signal) => verifyScreenshot(file, signal), true),
    [run],
  )

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setState(INITIAL)
  }, [])

  useEffect(() => () => abortRef.current?.abort(), [])

  return { ...state, submitClaim, submitScreenshot, reset }
}
