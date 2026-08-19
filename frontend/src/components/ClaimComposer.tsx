import { useEffect, useRef, useState } from 'react'
import { detectLanguage } from '../lib/format'
import { ScreenshotDropzone } from './ScreenshotDropzone'
import { ImageIcon } from './icons'

const MAX_CLAIM = 1000

interface Props {
  onSubmitClaim: (claim: string) => void
  onSubmitScreenshot: (file: File) => void
  disabled?: boolean
  initialClaim?: string
}

/** The centrepiece: one box that takes a typed claim or a screenshot.
 *
 *  Deliberately not a chat input. There is no message history, no send-arrow, no
 *  assistant bubble — this is a form that starts an investigation. */
export function ClaimComposer({
  onSubmitClaim,
  onSubmitScreenshot,
  disabled,
  initialClaim = '',
}: Props) {
  const [claim, setClaim] = useState(initialClaim)
  const [showUpload, setShowUpload] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (initialClaim) setClaim(initialClaim)
  }, [initialClaim])

  // Autosize, so a long Bangla claim is never trapped in a 3-line box.
  useEffect(() => {
    const node = textareaRef.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.min(node.scrollHeight, 320)}px`
  }, [claim])

  const language = detectLanguage(claim)
  const trimmed = claim.trim()
  const canSubmitText = trimmed.length >= 3 && trimmed.length <= MAX_CLAIM
  const canSubmit = file ? true : canSubmitText

  const submit = () => {
    if (disabled || !canSubmit) return
    if (file) onSubmitScreenshot(file)
    else onSubmitClaim(trimmed)
  }

  return (
    <div className="card p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <label htmlFor="claim" className="label-micro">
          Claim to verify
        </label>
        {trimmed.length > 0 && (
          <span
            className="text-micro font-semibold px-2 py-0.5 rounded-sm bg-sunken text-ink-soft transition-opacity duration-micro"
            aria-live="polite"
          >
            {language === 'bn' ? 'বাংলা' : 'English'}
          </span>
        )}
      </div>

      <textarea
        ref={textareaRef}
        id="claim"
        value={claim}
        onChange={(event) => setClaim(event.target.value.slice(0, MAX_CLAIM))}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') submit()
        }}
        disabled={disabled}
        rows={3}
        lang={language}
        placeholder="Paste a claim in Bangla or English — for example a Facebook post or a headline you are unsure about"
        aria-describedby="claim-hint"
        className="w-full resize-none bg-transparent text-body placeholder:text-ink-muted
                   focus:outline-none disabled:opacity-60"
      />

      {showUpload && (
        <div className="mt-3">
          <ScreenshotDropzone file={file} onSelect={setFile} disabled={disabled} />
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowUpload((value) => !value)}
            disabled={disabled}
            aria-expanded={showUpload}
            className="inline-flex items-center gap-1.5 rounded px-2.5 py-2 text-small font-medium
                       text-ink-soft hover:bg-sunken hover:text-ink transition-colors duration-micro
                       disabled:opacity-50 min-h-[44px]"
          >
            <ImageIcon /> Screenshot
          </button>
          {/* When an image is attached the typed text is not used. That hint must show
              on mobile too — hiding it there let text be silently discarded. */}
          <span
            id="claim-hint"
            className={`text-micro text-ink-muted ${file ? '' : 'hidden sm:inline'}`}
          >
            {file
              ? trimmed
                ? 'Typed text is ignored — the claim is read from your image'
                : 'The claim will be read from your image'
              : 'Ctrl + Enter to verify'}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {trimmed.length > MAX_CLAIM - 100 && (
            <span className="text-micro text-ink-muted tabular-nums">
              {trimmed.length}/{MAX_CLAIM}
            </span>
          )}
          <button
            onClick={submit}
            disabled={disabled || !canSubmit}
            className="rounded bg-accent px-5 py-2.5 text-small font-semibold text-white
                       transition-opacity duration-micro hover:opacity-90
                       disabled:cursor-not-allowed disabled:opacity-40 min-h-[44px] w-full sm:w-auto"
          >
            {file ? 'Read & verify' : 'Verify'}
          </button>
        </div>
      </div>
    </div>
  )
}
