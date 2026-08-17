/** Single place that talks to the backend.
 *
 *  Every failure becomes an ApiError carrying the backend's own message, so the UI
 *  can show what actually went wrong instead of a generic "something failed". */

import type {
  ApiErrorBody,
  HealthResponse,
  ScreenshotExtractionResponse,
  ScreenshotVerifyResponse,
  VerifyResponse,
} from '../types'

const BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly retryable: boolean

  constructor(message: string, code: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    // 429 and 502 are worth another attempt; a 415 or 422 will fail identically.
    this.retryable = status === 429 || status === 502 || status === 504 || status === 0
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: Partial<ApiErrorBody> = {}
  try {
    body = (await response.json()) as ApiErrorBody
  } catch {
    // Non-JSON error (a proxy or gateway page); fall through to the default.
  }
  return new ApiError(
    body.message ?? 'Something went wrong. Please try again.',
    body.error ?? 'unknown_error',
    response.status,
  )
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, init)
  } catch {
    // Network-level failure: no response at all. Status 0 marks it retryable.
    throw new ApiError(
      'Could not reach the server. Check your connection and try again.',
      'network_error',
      0,
    )
  }

  if (!response.ok) throw await toApiError(response)
  return (await response.json()) as T
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/api/health', { signal })
}

export function verifyClaim(claim: string, signal?: AbortSignal): Promise<VerifyResponse> {
  return request<VerifyResponse>('/api/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ claim }),
    signal,
  })
}

/** Reads a screenshot without verifying it — one cheap call, so the user can
 *  correct a misread claim before the expensive research runs. */
export function extractScreenshot(
  file: File,
  signal?: AbortSignal,
): Promise<ScreenshotExtractionResponse> {
  const form = new FormData()
  form.append('image', file)
  return request<ScreenshotExtractionResponse>('/api/screenshot/extract', {
    method: 'POST',
    body: form,
    signal,
  })
}

export function verifyScreenshot(
  file: File,
  signal?: AbortSignal,
): Promise<ScreenshotVerifyResponse> {
  const form = new FormData()
  form.append('image', file)
  return request<ScreenshotVerifyResponse>('/api/verify/screenshot', {
    method: 'POST',
    body: form,
    signal,
  })
}
