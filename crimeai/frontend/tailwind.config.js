/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // CrimeAI dark theme palette — Palantir Gotham inspired
        bg: {
          primary:   '#0a0c10',   // deepest background
          secondary: '#0f1117',   // card backgrounds
          tertiary:  '#161b22',   // elevated surfaces
          elevated:  '#1c2128',   // modals, dropdowns
          hover:     '#222831',   // hover states
        },
        border: {
          subtle:  '#21262d',
          default: '#30363d',
          strong:  '#484f58',
        },
        text: {
          primary:   '#e6edf3',
          secondary: '#8b949e',
          muted:     '#484f58',
          inverse:   '#0a0c10',
        },
        accent: {
          blue:    '#1f6feb',
          cyan:    '#39d353',
          purple:  '#8957e5',
          amber:   '#d29922',
        },
        // Alert severity colours
        severity: {
          low:      { DEFAULT: '#3fb950', bg: '#0d2119' },
          medium:   { DEFAULT: '#d29922', bg: '#271d00' },
          high:     { DEFAULT: '#f85149', bg: '#2d0f12' },
          critical: { DEFAULT: '#ff7b72', bg: '#3d0814' },
        },
        // Status colours
        status: {
          online:  '#3fb950',
          offline: '#f85149',
          idle:    '#d29922',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],
      },
      animation: {
        'pulse-slow':  'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in':     'fadeIn 0.2s ease-in-out',
        'slide-up':    'slideUp 0.3s ease-out',
        'blink':       'blink 1s step-end infinite',
      },
      keyframes: {
        fadeIn:  { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        slideUp: { '0%': { transform: 'translateY(8px)', opacity: '0' }, '100%': { transform: 'translateY(0)', opacity: '1' } },
        blink:   { '0%, 100%': { opacity: '1' }, '50%': { opacity: '0' } },
      },
      boxShadow: {
        'inner-sm': 'inset 0 1px 2px rgba(0,0,0,0.4)',
        'card':     '0 1px 3px rgba(0,0,0,0.5), 0 0 0 1px rgba(48,54,61,0.5)',
        'elevated': '0 8px 24px rgba(0,0,0,0.6)',
        'glow-blue': '0 0 12px rgba(31,111,235,0.4)',
        'glow-red':  '0 0 12px rgba(248,81,73,0.4)',
      },
    },
  },
  plugins: [],
}
