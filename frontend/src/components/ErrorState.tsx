import type { ApiError } from '../api/client'

interface Props {
  error: ApiError
  onRetry: () => void
  onReset: () => void
}

/** One card, never a red wall.
 *
 *  Each backend error code gets a plain sentence and a real next action. The claim is
 *  never lost, so nothing has to be retyped. */
export function ErrorState({ error, onRetry, onReset }: Props) {
  const guidance = guidanceFor(error)

  return (
    <section
      role="alert"
      className="rounded-lg border-2 border-false-edge bg-false-fill p-5 sm:p-6"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full border-2 border-false-edge text-false-text font-bold"
        >
          !
        </span>

        <div className="min-w-0 flex-1">
          <h2 className="font-display text-h2 font-semibold text-false-text">
            {guidance.title}
          </h2>
          <p className="mt-1.5 max-w-measure text-body text-ink">{error.message}</p>
          {guidance.hint && (
            <p className="mt-2 max-w-measure text-small text-ink-soft">{guidance.hint}</p>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {error.retryable && (
              <button
                onClick={onRetry}
                className="rounded bg-accent px-4 py-2.5 text-small font-semibold text-white hover:opacity-90 transition-opacity duration-micro min-h-[44px]"
              >
                Try again
              </button>
            )}
            <button
              onClick={onReset}
              className="rounded border border-hairline-strong bg-card px-4 py-2.5 text-small font-semibold text-ink hover:bg-sunken transition-colors duration-micro min-h-[44px]"
            >
              Start over
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}

function guidanceFor(error: ApiError): { title: string; hint?: string } {
  switch (error.code) {
    case 'rate_limited':
      return {
        title: 'Too many checks right now',
        hint: 'The AI or research service hit its rate limit. Waiting about a minute is usually enough.',
      }
    case 'service_unavailable':
      return {
        title: 'Not configured',
        hint: 'An API key is missing on the server. Check the .env file and restart the backend.',
      }
    case 'service_error':
      return {
        title: 'A service failed',
        hint: 'This is usually temporary and clears on a retry.',
      }
    case 'timeout':
      return {
        title: 'That took too long',
        hint: 'A verification normally finishes in 25–40 seconds. The AI or research service is probably overloaded.',
      }
    case 'network_error':
      return {
        title: 'Cannot reach the server',
        hint: 'Check that the backend is running on port 8000.',
      }
    case 'unsupported_media_type':
      return { title: 'That file cannot be read', hint: 'Upload a PNG, JPEG, WebP, or GIF image.' }
    case 'payload_too_large':
      return { title: 'That image is too large', hint: 'Try a screenshot under 5 MB.' }
    case 'validation_error':
      return { title: 'Check the claim', hint: 'A claim needs at least 3 characters.' }
    default:
      return { title: 'Something went wrong' }
  }
}
