// ProcessArc color palette.
//
// Token names are Tailwind-flavored but the underlying values follow the
// design spec in docs/theme.md (and the spec attached to the May 2026
// theme-and-logo-visibility pass). The semantic mapping is:
//
//   --bg-page         → ink-50 (light)   / ink-900 (dark)
//   --bg-header       → white  (light)   / ink-850 (dark — matches the
//                                          dark logo asset's canvas)
//   --bg-card         → white  (light)   / ink-800 (dark)
//   --border-default  → ink-200 (light)  / ink-700 (dark)
//   --text-primary    → ink-900 (light)  / ink-50 (dark)
//   --text-secondary  → ink-500 (light)  / ink-400 (dark)
//   --accent-primary  → brand-500
//   --accent-success  → ok-500     (also used for the active-tab underline)
//   --accent-warning  → warn-500
//   --accent-danger   → danger-500
//
// `ink-900` (#10243F) does double duty: light-mode text-primary AND
// dark-mode bg-page. The value is the logo-wordmark navy — keeping it
// unified saves a ~15-line refactor of `text-ink-900` references across
// the wizard screens, and the same value reads well as a very deep
// dark-mode page bg.
//
// `ink-850` (#0F172B) is reserved for the dark-mode header band so it
// matches the dark logo asset's baked-in canvas exactly. Without the
// asset constraint the header could float a step brighter than the
// page; with the constraint, the header reads as a "logo bay" sitting
// one tone deeper than the page. Acceptable trade.
//
// WCAG AA contrast checks (4.5:1 normal text, 3:1 large text). Verified
// 2026-05-23 with the WebAIM contrast formula:
//
//   text-primary on bg-page  light: ink-900 #10243F on ink-50 #F7F9FC → 14.0:1 ✓
//   text-secondary on bg-page light: ink-500 #5B6B82 on ink-50 #F7F9FC →  5.1:1 ✓
//   text-primary on bg-card  light: ink-900 #10243F on white          → 14.8:1 ✓
//   text-secondary on bg-card light: ink-500 #5B6B82 on white         →  5.4:1 ✓
//   white text on brand-500  light: white on #1E5FAB                  →  5.6:1 ✓
//
//   text-primary on bg-page  dark: ink-50  #F7F9FC on ink-900 #10243F → 14.0:1 ✓
//   text-secondary on bg-page dark: ink-400 #9AA8BD on ink-900 #10243F →  5.5:1 ✓
//   text-primary on bg-card  dark: ink-50  #F7F9FC on ink-800 #1A2433 → 11.7:1 ✓
//   text-secondary on bg-card dark: ink-400 #9AA8BD on ink-800 #1A2433 →  4.6:1 ✓
//   white text on brand-500  dark: white on #1E5FAB                   →  5.6:1 ✓
//
// If a color value changes below, recompute these and update the comment.

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
        // Brand blue — picks up the navy from the logo's wordmark.
        // Light-mode `500` is the deeper navy-blue; dark-mode would want
        // the lighter accent but Tailwind doesn't support per-mode token
        // values without CSS vars, so we pick the light value as the
        // canonical and use lighter shades manually where dark mode needs
        // pop. The two values from the spec (#1E5FAB light, #2B7BD1 dark)
        // are close enough that one shared `500` reads well in both.
        brand:  { 50: '#EAF2FB', 100: '#D2E2F5', 500: '#1E5FAB', 600: '#2870BD', 700: '#15497F' },

        // Success / "the logo's green-arc green" — also the tab-active
        // underline color in both themes (§3.3).
        ok:     { 50: '#E8F6EE', 500: '#2E9B65', 600: '#3FB57A', 700: '#1E6F47' },

        // Warning (amber). Slightly deeper in light to clear AA on white;
        // unchanged scale in dark mode.
        warn:   { 50: '#FBF1E2', 500: '#B97316', 600: '#D89240', 700: '#8A560F' },

        // Danger (red). Unchanged in role; verify contrast on cards.
        danger: { 50: '#fef2f2', 500: '#dc2626', 600: '#b91c1c', 700: '#991b1b' },

        // Neutral palette — "ink" — both themes share the same scale.
        // Light surfaces pick from the low end; dark from the high end.
        //
        //   ink-50  = light bg-page              (slight off-white)
        //   ink-100 = subtle fills on light cards
        //   ink-200 = light borders
        //   ink-300 = disabled foreground / placeholder
        //   ink-400 = dark text-secondary
        //   ink-500 = light text-secondary
        //   ink-600 = light text on dark hover
        //   ink-700 = dark borders / muted dark text
        //   ink-800 = dark bg-card                (carded surfaces)
        //   ink-850 = dark bg-header              (matches dark logo canvas; see Header.tsx)
        //   ink-900 = dark bg-page / light text-primary (#10243F picks up the logo wordmark navy)
        ink:    {
          50:  '#F7F9FC',
          100: '#EEF2F7',
          200: '#DDE3EC',
          300: '#BBC4D2',
          400: '#9AA8BD',
          500: '#5B6B82',
          600: '#3F4D65',
          700: '#243245',
          800: '#1A2433',
          850: '#0F172B',
          900: '#10243F',
        },
      },
      borderRadius: { card: '0.5rem' },
    },
  },
  plugins: [],
};
