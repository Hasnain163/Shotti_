/** Tailwind maps onto the semantic tokens defined in src/index.css.
 *  Components reference token names only — never a raw hex value — so dark mode and
 *  any future rebrand are a token change, not a component sweep. */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        page: 'rgb(var(--surface-page) / <alpha-value>)',
        card: 'rgb(var(--surface-card) / <alpha-value>)',
        sunken: 'rgb(var(--surface-sunken) / <alpha-value>)',
        hairline: 'rgb(var(--border-subtle) / <alpha-value>)',
        'hairline-strong': 'rgb(var(--border-strong) / <alpha-value>)',
        ink: 'rgb(var(--text-primary) / <alpha-value>)',
        'ink-soft': 'rgb(var(--text-secondary) / <alpha-value>)',
        'ink-muted': 'rgb(var(--text-muted) / <alpha-value>)',
        accent: 'rgb(var(--accent) / <alpha-value>)',
        'accent-soft': 'rgb(var(--accent-soft) / <alpha-value>)',

        // Verdict semantics. UNVERIFIED is intentionally neutral: "we don't know"
        // must not read as a soft verdict.
        true: {
          fill: 'rgb(var(--verdict-true-fill) / <alpha-value>)',
          edge: 'rgb(var(--verdict-true-edge) / <alpha-value>)',
          text: 'rgb(var(--verdict-true-text) / <alpha-value>)',
        },
        false: {
          fill: 'rgb(var(--verdict-false-fill) / <alpha-value>)',
          edge: 'rgb(var(--verdict-false-edge) / <alpha-value>)',
          text: 'rgb(var(--verdict-false-text) / <alpha-value>)',
        },
        misleading: {
          fill: 'rgb(var(--verdict-misleading-fill) / <alpha-value>)',
          edge: 'rgb(var(--verdict-misleading-edge) / <alpha-value>)',
          text: 'rgb(var(--verdict-misleading-text) / <alpha-value>)',
        },
        unverified: {
          fill: 'rgb(var(--verdict-unverified-fill) / <alpha-value>)',
          edge: 'rgb(var(--verdict-unverified-edge) / <alpha-value>)',
          text: 'rgb(var(--verdict-unverified-text) / <alpha-value>)',
        },
      },
      fontFamily: {
        ui: ['Inter', 'Noto Sans Bengali', 'system-ui', 'sans-serif'],
        bn: ['Noto Sans Bengali', 'Hind Siliguri', 'sans-serif'],
        display: ['Inter Tight', 'Inter', 'Noto Sans Bengali', 'sans-serif'],
        quote: ['Source Serif 4', 'Noto Serif Bengali', 'Georgia', 'serif'],
      },
      fontSize: {
        // Fluid scale. Body never drops below 16px — Bangla needs the pixels.
        display: ['clamp(2.25rem, 1.5rem + 3vw, 3.5rem)', { lineHeight: '1.1', letterSpacing: '-0.02em' }],
        h1: ['clamp(1.75rem, 1.4rem + 1.5vw, 2.25rem)', { lineHeight: '1.2', letterSpacing: '-0.01em' }],
        h2: ['clamp(1.25rem, 1.1rem + 0.6vw, 1.625rem)', { lineHeight: '1.3' }],
        h3: ['1.125rem', { lineHeight: '1.4' }],
        body: ['1.0625rem', { lineHeight: '1.6' }],
        small: ['0.875rem', { lineHeight: '1.5' }],
        micro: ['0.75rem', { lineHeight: '1.4', letterSpacing: '0.04em' }],
      },
      borderRadius: { sm: '4px', DEFAULT: '8px', md: '8px', lg: '12px' },
      boxShadow: {
        sm: '0 1px 2px rgb(0 0 0 / 0.04), 0 1px 1px rgb(0 0 0 / 0.03)',
        md: '0 4px 16px rgb(0 0 0 / 0.08)',
      },
      maxWidth: { measure: '68ch', 'measure-bn': '60ch', shell: '1200px' },
      transitionDuration: { micro: '120ms', panel: '200ms' },
      keyframes: {
        'slide-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'rise-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'stage-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.55' },
        },
      },
      animation: {
        'slide-in': 'slide-in 200ms ease-out both',
        'rise-in': 'rise-in 200ms ease-out both',
        'stage-pulse': 'stage-pulse 1.8s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
