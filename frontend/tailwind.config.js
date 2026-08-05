/** @type {import('tailwindcss').Config} */

// The single source of truth for Vantage's design tokens.
//
// Every colour resolves through a CSS custom property holding an "R G B"
// triplet, so a theme can be swapped by redefining the variables in index.css
// without touching a component. The `<alpha-value>` placeholder is what keeps
// Tailwind's opacity modifiers (`bg-ok/15`, `border-line/60`) working through
// the indirection.
const c = (name) => `rgb(var(--v-${name}) / <alpha-value>)`

const palette = {
  primary: c('primary'),
  'primary-soft': c('primary-soft'),
  'primary-tint': c('primary-tint'),
  // Text-on-tint and the primary button fill. `primary` itself only reaches
  // 3.1:1 under white text, so it is a surface and accent colour, not a fill
  // for anything carrying a label.
  'primary-deep': c('primary-deep'),
  'primary-deeper': c('primary-deeper'),
  sun: c('sun'),
  'sun-soft': c('sun-soft'),
  ink: c('ink'),
  'ink-2': c('ink-2'),
  'ink-3': c('ink-3'),
  line: c('line'),
  bg: c('bg'),
  card: c('card'),
  // Inset surface — sits one step back from `card`, used for code blocks,
  // trace panels, data grids and quote wells.
  paper: c('paper'),

  // The categorical arc: blue -> indigo -> violet -> orchid -> pink -> rose.
  // Reach for these when a set of things needs telling apart — thought kinds,
  // knowledge types, analyst tiers, chart series. Each hue is a `-tint` surface,
  // a base mark and a `-deep` ink. Using a base tone as text is the mistake this
  // split exists to prevent.
  'blue-tint': c('blue-tint'),
  blue: c('blue'),
  'blue-deep': c('blue-deep'),
  'indigo-tint': c('indigo-tint'),
  indigo: c('indigo'),
  'indigo-deep': c('indigo-deep'),
  'violet-tint': c('violet-tint'),
  violet: c('violet'),
  'violet-deep': c('violet-deep'),
  'orchid-tint': c('orchid-tint'),
  orchid: c('orchid'),
  'orchid-deep': c('orchid-deep'),
  'pink-tint': c('pink-tint'),
  pink: c('pink'),
  'pink-deep': c('pink-deep'),
  'rose-tint': c('rose-tint'),
  rose: c('rose'),
  'rose-deep': c('rose-deep'),

  // Status. `ok` and `warn` are the only colours off the arc; `risk` is the
  // arc's deep rose under a name that says what it means.
  'ok-tint': c('ok-tint'),
  ok: c('ok'),
  'ok-deep': c('ok-deep'),
  'warn-tint': c('warn-tint'),
  warn: c('warn'),
  'warn-deep': c('warn-deep'),
  'risk-tint': c('risk-tint'),
  risk: c('risk'),
  'risk-deep': c('risk-deep'),
  'info-tint': c('info-tint'),
  info: c('info'),
  'info-deep': c('info-deep'),
}

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ...palette,
        vantage: palette,
      },
      borderRadius: {
        card: '16px',
        btn: '12px',
        chip: '999px',
      },
      boxShadow: {
        card: '0 4px 24px rgb(var(--v-primary) / 0.08)',
        float: '0 8px 40px rgb(var(--v-primary) / 0.14)',
        glow: '0 0 0 4px rgb(var(--v-primary) / 0.12)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        serif: ['Source Serif 4', 'Georgia', 'Times New Roman', 'serif'],
        mono: ['JetBrains Mono', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      fontSize: {
        h1: ['28px', { lineHeight: '1.3', fontWeight: '600' }],
        h2: ['22px', { lineHeight: '1.35', fontWeight: '600' }],
        h3: ['18px', { lineHeight: '1.4', fontWeight: '600' }],
        body: ['15px', { lineHeight: '1.7' }],
        aux: ['13px', { lineHeight: '1.6' }],
        tag: ['11px', { lineHeight: '1.4' }],
      },
      spacing: {
        4.5: '18px',
      },
      maxWidth: {
        content: '1440px',
        read: '760px',
      },
      transitionTimingFunction: {
        vantage: 'cubic-bezier(.4,0,.2,1)',
      },
      keyframes: {
        breath: { '0%,100%': { opacity: '1' }, '50%': { opacity: '.55' } },
        floatUp: {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        glow: {
          '0%,100%': { boxShadow: '0 0 0 0 rgb(var(--v-primary) / 0.4)' },
          '50%': { boxShadow: '0 0 0 8px rgb(var(--v-primary) / 0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        spinSlow: { to: { transform: 'rotate(360deg)' } },
      },
      animation: {
        breath: 'breath 2s ease-in-out infinite',
        floatUp: 'floatUp .4s cubic-bezier(.4,0,.2,1) both',
        glow: 'glow 1.8s ease-in-out infinite',
        shimmer: 'shimmer 1.6s linear infinite',
        'spin-slow': 'spinSlow 8s linear infinite',
      },
    },
  },
  plugins: [],
}
