import { useEffect, useState, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  onShowAbout: () => void
  onHome: () => void
}

/** Header, footer, skip link, and the theme toggle. */
export function AppShell({ children, onShowAbout, onHome }: Props) {
  const [dark, setDark] = useState(
    () => window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false,
  )

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', dark ? '#18181b' : '#fafaf9')
  }, [dark])

  return (
    <div className="min-h-screen flex flex-col">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <header className="border-b border-hairline bg-card/80 backdrop-blur-[2px] sticky top-0 z-30">
        <div className="mx-auto max-w-shell px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
          <button
            onClick={onHome}
            className="flex items-baseline gap-1.5 rounded-sm"
            aria-label="Shotti? AI home"
          >
            <span className="font-display text-[1.35rem] font-bold tracking-tight">
              Shotti<span className="text-accent">?</span>
            </span>
            <span className="label-micro">AI</span>
          </button>

          <nav className="flex items-center gap-1" aria-label="Main">
            <button
              onClick={onShowAbout}
              className="px-3 py-2 text-small font-medium text-ink-soft hover:text-ink rounded transition-colors duration-micro"
            >
              How it works
            </button>
            <button
              onClick={() => setDark((value) => !value)}
              className="px-3 py-2 text-small text-ink-soft hover:text-ink rounded transition-colors duration-micro"
              aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {dark ? '☀' : '☾'}
            </button>
          </nav>
        </div>
      </header>

      <main id="main" className="flex-1">
        {children}
      </main>

      <footer className="border-t border-hairline mt-16">
        <div className="mx-auto max-w-shell px-4 sm:px-6 py-8 text-small text-ink-muted">
          <p className="max-w-measure">
            Shotti? AI researches public web sources and shows the evidence behind every
            verdict. It can be wrong, and it cannot detect an edited screenshot — read the
            sources yourself before sharing.
          </p>
        </div>
      </footer>
    </div>
  )
}
