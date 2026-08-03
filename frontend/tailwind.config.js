/** @type {import('tailwindcss').Config} */

// The single source of truth for Vantage's design tokens. index.css mirrors
// these as CSS custom properties for the few places that need raw values;
// nothing else should hardcode a hex.
const palette = {
  primary: '#7C9885',
  'primary-soft': '#A8C0A8',
  'primary-tint': '#EAF1EA',
  'primary-deep': '#5E7A66',
  sun: '#F4E2B8',
  'sun-soft': '#FBF6E9',
  ink: '#3A413C',
  'ink-2': '#6B746C',
  'ink-3': '#9AA39C',
  line: '#E3E8E3',
  bg: '#FAFBF9',
  card: '#FFFFFF',
  // Inset surface — sits one step back from `card`, used for code blocks,
  // trace panels, data grids and quote wells.
  paper: '#F4F6F3',
  ok: '#8AB58A',
  warn: '#E0B775',
  risk: '#CE9A92',
  // Deepened `risk`, same hue. Needed because white text on `risk` itself only
  // reaches 2.4:1 — fine as a tint behind dark text, not as a button fill.
  'risk-deep': '#A8635A',
  info: '#8FA8C0',
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
        card: '0 4px 24px rgba(124,152,133,0.08)',
        float: '0 8px 40px rgba(124,152,133,0.14)',
        glow: '0 0 0 4px rgba(124,152,133,0.12)',
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
          '0%,100%': { boxShadow: '0 0 0 0 rgba(124,152,133,.4)' },
          '50%': { boxShadow: '0 0 0 8px rgba(124,152,133,0)' },
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
