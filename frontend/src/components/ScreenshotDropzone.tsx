import { useCallback, useEffect, useRef, useState } from 'react'

const ACCEPTED = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
const MAX_BYTES = 5 * 1024 * 1024

interface Props {
  file: File | null
  onSelect: (file: File | null) => void
  disabled?: boolean
}

/** Screenshot picker: click, drag, or paste.
 *
 *  Paste matters more than it looks — pasting from the clipboard is how people
 *  actually move a screenshot they just took, on desktop and on Android alike.
 *
 *  Type and size are checked here as well as on the server. The client check is only
 *  to give instant feedback; the server's check is the one that counts. */
export function ScreenshotDropzone({ file, onSelect, disabled }: Props) {
  const [dragging, setDragging] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!file) {
      setPreview(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const accept = useCallback(
    (candidate: File | undefined) => {
      if (!candidate) return
      if (!ACCEPTED.includes(candidate.type)) {
        setLocalError('That file is not a PNG, JPEG, WebP, or GIF image.')
        return
      }
      if (candidate.size > MAX_BYTES) {
        setLocalError('That image is larger than 5 MB. Try a smaller screenshot.')
        return
      }
      setLocalError(null)
      onSelect(candidate)
    },
    [onSelect],
  )

  // Paste anywhere on the page while the composer is open.
  useEffect(() => {
    if (disabled) return
    const onPaste = (event: ClipboardEvent) => {
      const image = Array.from(event.clipboardData?.files ?? []).find((item) =>
        item.type.startsWith('image/'),
      )
      if (image) {
        event.preventDefault()
        accept(image)
      }
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [accept, disabled])

  if (file && preview) {
    return (
      <div className="rounded-lg border border-hairline bg-sunken p-3">
        <div className="flex items-start gap-3">
          <img
            src={preview}
            alt={`Selected screenshot: ${file.name}`}
            className="h-20 w-20 rounded object-cover border border-hairline"
          />
          <div className="min-w-0 flex-1">
            <p className="text-small font-medium truncate">{file.name}</p>
            <p className="text-small text-ink-muted">
              {(file.size / 1024).toFixed(0)} KB · will be read for a claim
            </p>
          </div>
          <button
            onClick={() => onSelect(null)}
            disabled={disabled}
            className="text-small font-medium text-ink-soft hover:text-ink px-2 py-1 rounded disabled:opacity-50"
          >
            Remove
          </button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          if (!disabled) accept(event.dataTransfer.files[0])
        }}
        className={`rounded-lg border-2 border-dashed p-6 text-center transition-colors duration-micro ${
          dragging ? 'border-accent bg-accent-soft' : 'border-hairline-strong bg-sunken'
        }`}
      >
        <p className="text-small text-ink-soft">
          Drop a screenshot here, paste it, or{' '}
          <button
            onClick={() => inputRef.current?.click()}
            disabled={disabled}
            className="font-semibold text-accent underline underline-offset-2 rounded-sm disabled:opacity-50"
          >
            browse files
          </button>
        </p>
        <p className="mt-1 text-micro text-ink-muted">PNG, JPEG, WebP or GIF · up to 5 MB</p>

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(',')}
          className="sr-only"
          disabled={disabled}
          onChange={(event) => accept(event.target.files?.[0])}
        />
      </div>

      {localError && (
        <p role="alert" className="mt-2 text-small text-false-text">
          {localError}
        </p>
      )}
    </div>
  )
}
