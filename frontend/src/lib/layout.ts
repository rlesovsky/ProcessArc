// Single source of truth for the app shell's horizontal layout.
//
// Every band of the chrome (header, tab bar, step bar, footer) and the
// main content container of each screen use the same `container` class
// so they line up vertically. The container is uncapped — it fills the
// full viewport width — so content uses the full monitor on wide
// displays. Padding scales with the viewport via clamp() so the chrome
// breathes on wide monitors and stays compact on phones.
//
// (Note: no max-width cap. A previous version capped at 1800px to
// protect prose line length, but the wizard and Tag Builder screens
// host cards/tables/tree views rather than long-form prose, so the
// cap created visible empty gutters on ultrawide monitors with no
// readability benefit.)
//
// Usage:
//   import { container, screen } from '@/lib/layout';
//   <div className={container}>...</div>            // bands of chrome
//   <div className={screen}>...</div>               // page content

// Horizontal-padding clamp: 1rem on phones, scales smoothly with vw,
// caps at 4rem on ultrawide screens so content doesn't pin to the
// absolute edge of a 5K display.
const _padding = '[padding-inline:clamp(1rem,3vw,4rem)]';

export const container = `w-full ${_padding}`;

// `screen` adds vertical padding on top of the horizontal container —
// used by the main content slot inside each tab/screen.
export const screen = `${container} [padding-block:clamp(1rem,2vw,2rem)]`;

// Fluid type ramps. Use on screen H1s so headings scale with viewport
// width without ballooning on very wide monitors.
//   h1: 1.25rem (20px) on phones → 1.75rem (28px) at ~1600px
//   h2: 1rem    (16px) on phones → 1.25rem (20px) at ~1600px
//   body large: 0.875rem (14px) → 1rem (16px)
export const h1Fluid = 'font-semibold text-ink-900 dark:text-ink-50 [font-size:clamp(1.25rem,1.4vw,1.75rem)] [line-height:1.25]';
export const h2Fluid = 'font-semibold text-ink-900 dark:text-ink-50 [font-size:clamp(1rem,1.1vw,1.25rem)] [line-height:1.3]';
export const subtleFluid = 'text-ink-500 dark:text-ink-400 [font-size:clamp(0.8125rem,0.9vw,0.9375rem)]';
