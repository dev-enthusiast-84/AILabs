/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
          950: '#082f49',
        },
        surface: {
          50:  '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
          950: '#020617',
        },
        glow: {
          sky:    'rgba(14, 165, 233, 0.25)',
          indigo: 'rgba(99, 102, 241, 0.25)',
          rose:   'rgba(244, 63, 94, 0.25)',
          emerald:'rgba(16, 185, 129, 0.25)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'float':      'float 4s ease-in-out infinite',
        'shimmer':    'shimmer 2.2s linear infinite',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%':      { transform: 'translateY(-6px)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% center' },
          '100%': { backgroundPosition:  '200% center' },
        },
      },
      boxShadow: {
        'glow-sky':    '0 0 20px rgba(14, 165, 233, 0.25)',
        'glow-indigo': '0 0 20px rgba(99, 102, 241, 0.25)',
        'glow-rose':   '0 0 20px rgba(244, 63, 94, 0.25)',
      },
      backgroundSize: {
        '200': '200%',
      },
    },
  },
  plugins: [],
}
