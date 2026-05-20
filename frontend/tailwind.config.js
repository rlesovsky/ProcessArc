/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        brand:  { 50: '#eef5ff', 100: '#dbeaff', 500: '#2563eb', 600: '#1d4ed8', 700: '#1e40af' },
        ok:     { 50: '#ecfdf5', 500: '#10b981', 600: '#059669', 700: '#047857' },
        warn:   { 50: '#fffbeb', 500: '#f59e0b', 600: '#d97706', 700: '#b45309' },
        danger: { 50: '#fef2f2', 500: '#ef4444', 600: '#dc2626', 700: '#b91c1c' },
        ink:    { 50: '#f8fafc', 100: '#f1f5f9', 200: '#e2e8f0', 300: '#cbd5e1',
                  400: '#94a3b8', 500: '#64748b', 600: '#475569', 700: '#334155',
                  800: '#1e293b', 900: '#0f172a' },
      },
      borderRadius: { card: '0.5rem' },
    },
  },
  plugins: [],
};
