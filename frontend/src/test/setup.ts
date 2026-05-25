import '@testing-library/jest-dom/vitest';
import { afterEach, beforeAll, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// jsdom logs a "Not implemented: navigation" warning when an anchor's
// .click() triggers a navigation. The download path uses an <a> with a
// blob: URL and .click() to start the download — that's the intended
// behavior; suppress the noise.
beforeAll(() => {
  const origError = console.error;
  console.error = (...args: unknown[]) => {
    const msg = String(args[0] ?? '');
    if (msg.includes('Not implemented: navigation')) return;
    origError(...args);
  };
});

// jsdom doesn't ship matchMedia; the ThemeToggle imports a module that
// touches window.matchMedia at import time.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

afterEach(() => {
  cleanup();
});
