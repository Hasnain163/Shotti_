/** Inline SVG icons.
 *
 *  Emoji were the obvious shortcut here, but they render as tofu boxes wherever the
 *  font lacks the glyph — which includes plenty of Android builds and headless
 *  browsers. An icon that sometimes shows as a hollow rectangle undermines exactly
 *  the credibility this interface is trying to earn. */

interface IconProps {
  className?: string
}

const base = 'h-4 w-4 shrink-0'

export function ImageIcon({ className = '' }: IconProps) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`${base} ${className}`}
    >
      <rect x="2.5" y="3.5" width="15" height="13" rx="2" />
      <circle cx="7" cy="8" r="1.4" />
      <path d="m3 14 4-3.5 3.5 3L14 10l3 3" />
    </svg>
  )
}

export function InfoIcon({ className = '' }: IconProps) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      aria-hidden="true"
      className={`${base} ${className}`}
    >
      <circle cx="10" cy="10" r="7.5" />
      <path d="M10 9v4.5" />
      <circle cx="10" cy="6.4" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function SunIcon({ className = '' }: IconProps) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      aria-hidden="true"
      className={`${base} ${className}`}
    >
      <circle cx="10" cy="10" r="3.6" />
      <path d="M10 2v1.8M10 16.2V18M2 10h1.8M16.2 10H18M4.3 4.3l1.3 1.3M14.4 14.4l1.3 1.3M15.7 4.3l-1.3 1.3M5.6 14.4l-1.3 1.3" />
    </svg>
  )
}

export function MoonIcon({ className = '' }: IconProps) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`${base} ${className}`}
    >
      <path d="M16 12.4A6.8 6.8 0 0 1 7.6 4a7 7 0 1 0 8.4 8.4Z" />
    </svg>
  )
}

export function ExternalIcon({ className = '' }: IconProps) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`h-3.5 w-3.5 shrink-0 ${className}`}
    >
      <path d="M11 4h5v5M15.5 4.5 9 11" />
      <path d="M15 12.5V15a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 15V6.5A1.5 1.5 0 0 1 5 5h2.5" />
    </svg>
  )
}
